from __future__ import annotations

import logging
import time
from typing import Any

from app.aws_iot import IoTClient
from app.config import AppConfig
from app.jobs import DeviceJobsRunner, TemplateJobExecutor
from app.remote_config import (
    RemoteConfigFetcher,
    effective_feature_flags,
    effective_publish_interval,
    effective_telemetry_topic,
    effective_thresholds,
    payload_keys_for_cycle,
)
from app.shadow import DeviceShadowSync
from app.telemetry import TelemetryGenerator


class TelemetryService:
    """
    MQTT for telemetry; optional device shadow for live overrides; optional HTTPS
    remote config (versioned JSON) for publish interval, topic template, sensors,
    and sampling rules. Precedence for overlapping keys: shadow wins over remote over env.
    AWS IoT Jobs (optional) uses the same MQTT connection for fleet job documents and status.
    """

    def __init__(
        self,
        config: AppConfig,
        client: IoTClient,
        logger: logging.Logger,
    ) -> None:
        self.config = config
        self.client = client
        self.logger = logger
        self.generator = TelemetryGenerator(thing_name=config.iot_thing_name)
        self._shadow: DeviceShadowSync | None = None
        if config.shadow_enabled:
            self._shadow = DeviceShadowSync(
                thing_name=config.iot_thing_name,
                shadow_name=config.iot_shadow_name,
                default_interval_seconds=config.publish_interval_seconds,
                logger=logger,
            )
        self._remote: RemoteConfigFetcher | None = None
        url = (config.remote_config_url or "").strip()
        if url:
            auth = (config.remote_config_auth_header or "").strip() or None
            self._remote = RemoteConfigFetcher(
                url_template=url,
                thing_name=config.iot_thing_name,
                poll_interval_seconds=float(config.remote_config_poll_seconds),
                timeout_seconds=config.remote_config_timeout_seconds,
                logger=logger,
                auth_header=auth,
            )
        self._jobs: DeviceJobsRunner | None = None

    def run(self, max_messages: int | None = None) -> None:
        published = 0
        self.client.connect()

        if self._shadow is not None:
            self._shadow.attach(self.client.subscribe, self._publish_json)
            self._shadow.start()

        mqtt_conn = self.client.get_mqtt_connection()
        if self.config.jobs_enabled and mqtt_conn is not None:
            self._jobs = DeviceJobsRunner(
                thing_name=self.config.iot_thing_name,
                mqtt_connection=mqtt_conn,
                logger=self.logger,
                executor=TemplateJobExecutor(self.logger),
            )
            self._jobs.start()

        if self._remote is not None:
            self._remote.force_refresh()

        last_shadow_report = time.monotonic()
        cycle = 0
        try:
            while True:
                cycle += 1
                now = time.monotonic()
                if self._remote is not None:
                    self._remote.maybe_refresh(now)

                rt = self._shadow.get_runtime() if self._shadow else None
                remote_snap = (
                    self._remote.cache.snapshot if self._remote is not None else None
                )

                interval = effective_publish_interval(
                    env_default=self.config.publish_interval_seconds,
                    remote=remote_snap,
                    shadow_interval=rt.sampling_interval_seconds if rt else None,
                )
                flags = effective_feature_flags(
                    remote_snap, rt.feature_flags if rt else None
                )
                thr = effective_thresholds(remote_snap, rt.thresholds if rt else None)
                topic = effective_telemetry_topic(
                    env_topic=self.config.iot_topic,
                    thing_name=self.config.iot_thing_name,
                    remote=remote_snap,
                )
                include_keys = payload_keys_for_cycle(cycle=cycle, remote=remote_snap)

                reading = self.generator.generate(
                    feature_flags=flags,
                    thresholds=thr,
                    firmware_version=rt.firmware_version if rt else None,
                    remote_config_version=remote_snap.version if remote_snap else None,
                )
                payload = reading.to_payload(include_sensor_keys=include_keys)
                self.client.publish(topic, payload)
                published += 1

                if self._shadow is not None:
                    self._shadow.set_last_telemetry_timestamp(reading.timestamp)
                    if self.config.shadow_report_interval_seconds > 0:
                        if (
                            now - last_shadow_report
                            >= self.config.shadow_report_interval_seconds
                        ):
                            self._shadow.publish_reported()
                            last_shadow_report = now

                if max_messages is not None and published >= max_messages:
                    self.logger.info("Published %s message(s); stopping.", published)
                    return

                time.sleep(interval)
        finally:
            self.client.disconnect()

    def _publish_json(self, topic: str, payload: dict[str, Any]) -> None:
        self.client.publish(topic, payload)
