from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Protocol

from app.config import AppConfig


class IoTClient(Protocol):
    def connect(self) -> None: ...
    def publish(self, topic: str, payload: dict[str, object]) -> None: ...
    def subscribe(self, topic: str, callback: Callable[[str, bytes], None]) -> None: ...
    def disconnect(self) -> None: ...


class ConsoleIotClient:
    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger

    def connect(self) -> None:
        self.logger.info("Dry-run mode enabled. Messages will be printed locally.")

    def publish(self, topic: str, payload: dict[str, object]) -> None:
        self.logger.info("DRY RUN publish topic=%s payload=%s", topic, json.dumps(payload))

    def subscribe(self, topic: str, callback: Callable[[str, bytes], None]) -> None:
        del callback
        self.logger.info(
            "DRY RUN subscribe topic=%s (shadow messages are not delivered in dry-run)",
            topic,
        )

    def disconnect(self) -> None:
        self.logger.info("Dry-run client disconnected.")


class AwsIotClient:
    def __init__(self, config: AppConfig, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger
        self._connection = None

    def connect(self) -> None:
        if self._connection is not None:
            return

        try:
            from awscrt import mqtt
            from awsiot import mqtt_connection_builder
        except ImportError as exc:
            raise RuntimeError(
                "AWS IoT SDK is not installed. Install with `python -m pip install -e .[aws]`."
            ) from exc

        builder_kwargs = {
            "endpoint": self.config.iot_endpoint,
            "cert_filepath": self.config.iot_cert_path,
            "pri_key_filepath": self.config.iot_key_path,
            "client_id": self.config.iot_client_id,
            "clean_session": False,
            "keep_alive_secs": 30,
        }
        if self.config.iot_ca_path:
            builder_kwargs["ca_filepath"] = self.config.iot_ca_path

        self._connection = mqtt_connection_builder.mtls_from_path(**builder_kwargs)
        self.logger.info("Connecting to AWS IoT Core endpoint=%s", self.config.iot_endpoint)
        connect_future = self._connection.connect()
        connect_future.result()
        self.logger.info("Connected to AWS IoT Core.")
        self._mqtt_qos = mqtt.QoS.AT_LEAST_ONCE

    def publish(self, topic: str, payload: dict[str, object]) -> None:
        if self._connection is None:
            raise RuntimeError("IoT client is not connected.")

        message = json.dumps(payload)
        self._connection.publish(topic=topic, payload=message, qos=self._mqtt_qos)
        if topic.startswith("$aws/"):
            self.logger.info("Published IoT service topic prefix=%s", topic[: min(72, len(topic))])
        else:
            thing = payload.get("thing_name", "")
            self.logger.info("Published telemetry topic=%s thing=%s", topic, thing)

    def subscribe(self, topic: str, callback: Callable[[str, bytes], None]) -> None:
        if self._connection is None:
            raise RuntimeError("IoT client is not connected.")

        from awscrt import mqtt as mqtt_mod

        def _wrapper(
            recv_topic: str,
            recv_payload: bytes,
            _dup: bool,
            _qos: mqtt_mod.QoS,
            _retain: bool,
            **_: object,
        ) -> None:
            try:
                callback(recv_topic, recv_payload)
            except Exception:
                self.logger.exception("MQTT subscription callback failed topic=%s", recv_topic[:48])

        future, _packet_id = self._connection.subscribe(
            topic=topic, qos=self._mqtt_qos, callback=_wrapper
        )
        future.result()
        self.logger.info("Subscribed to IoT topic prefix=%s", topic[: min(72, len(topic))])

    def disconnect(self) -> None:
        if self._connection is None:
            return

        self.logger.info("Disconnecting from AWS IoT Core.")
        disconnect_future = self._connection.disconnect()
        disconnect_future.result()
        self._connection = None
        self.logger.info("Disconnected from AWS IoT Core.")
