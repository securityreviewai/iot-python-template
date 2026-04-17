from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from app.aws_iot import IoTClient
from app.config import AppConfig
from app.models import telemetry_payload_for_mqtt
from app.remote_config import RemoteConfigPoller
from app.shadow import SHADOW_DEVICE_STATUS_MIN_INTERVAL_S, DeviceConfigStore
from app.telemetry import TelemetryGenerator

if TYPE_CHECKING:
    from app.iot_jobs import JobsBridge
    from app.shadow import ShadowBridge


class TelemetryService:
    def __init__(
        self,
        config: AppConfig,
        client: IoTClient,
        logger: logging.Logger,
        store: DeviceConfigStore,
        shadow: ShadowBridge | None = None,
        remote_poller: RemoteConfigPoller | None = None,
        jobs: JobsBridge | None = None,
    ) -> None:
        self.config = config
        self.client = client
        self.logger = logger
        self.store = store
        self.shadow = shadow
        self._remote_poller = remote_poller
        self._jobs = jobs
        self._last_shadow_status_mono: float | None = None
        self.generator = TelemetryGenerator(
            thing_name=config.iot_thing_name,
            firmware_version=config.firmware_version,
        )

    def run(self, max_messages: int | None = None) -> None:
        published = 0
        self.client.connect()

        try:
            if self.shadow is not None:
                self.shadow.install()
            if self._jobs is not None:
                self._jobs.install()
            if self._remote_poller is not None:
                self._remote_poller.start()

            while True:
                runtime = self.store.current()
                interval = runtime.sampling_interval_seconds
                reading = self.generator.generate(runtime)
                topic = runtime.telemetry_topic or self.config.iot_topic
                payload = telemetry_payload_for_mqtt(reading, runtime.sensor_mask)
                self.client.publish(topic, payload)
                published += 1

                if self.shadow is not None:
                    now = time.monotonic()
                    if (
                        self._last_shadow_status_mono is None
                        or now - self._last_shadow_status_mono >= SHADOW_DEVICE_STATUS_MIN_INTERVAL_S
                    ):
                        self.shadow.sync_device_status(reading.timestamp)
                        self._last_shadow_status_mono = now

                if max_messages is not None and published >= max_messages:
                    self.logger.info("Published %s message(s); stopping.", published)
                    return

                time.sleep(interval)
        finally:
            if self._remote_poller is not None:
                self._remote_poller.stop_and_join()
            if self._jobs is not None:
                self._jobs.shutdown()
            self.client.disconnect()
