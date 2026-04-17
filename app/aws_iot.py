from __future__ import annotations

import json
import logging
from typing import Protocol

from app.config import AppConfig
from app.shadow import ShadowMessageHandler


class IoTClient(Protocol):
    def connect(self) -> None: ...
    def publish(self, topic: str, payload: dict[str, object]) -> None: ...
    def subscribe(self, topic: str, handler: ShadowMessageHandler) -> None: ...
    def disconnect(self) -> None: ...
    def get_mqtt_connection(self) -> object | None: ...


class ConsoleIotClient:
    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger
        self._subscriptions: dict[str, list[ShadowMessageHandler]] = {}

    def connect(self) -> None:
        self.logger.info("Dry-run mode enabled. Messages will be printed locally.")

    def publish(self, topic: str, payload: dict[str, object]) -> None:
        self.logger.info("DRY RUN publish topic=%s payload=%s", topic, json.dumps(payload))

    def subscribe(self, topic: str, handler: ShadowMessageHandler) -> None:
        self._subscriptions.setdefault(topic, []).append(handler)
        self.logger.info("DRY RUN subscribe topic=%s", topic)

    def disconnect(self) -> None:
        self.logger.info("Dry-run client disconnected.")

    def get_mqtt_connection(self) -> object | None:
        return None


class AwsIotClient:
    def __init__(self, config: AppConfig, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger
        self._connection = None
        self._subscription_callbacks: list[object] = []

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

    def subscribe(self, topic: str, handler: ShadowMessageHandler) -> None:
        if self._connection is None:
            raise RuntimeError("IoT client is not connected.")

        def _cb(topic_received: str, payload: bytes, **kwargs: object) -> None:
            handler(topic_received, payload)

        self._subscription_callbacks.append(_cb)
        fut, _packet_id = self._connection.subscribe(
            topic=topic,
            qos=self._mqtt_qos,
            callback=_cb,
        )
        fut.result()
        self.logger.info("Subscribed topic=%s", topic)

    def publish(self, topic: str, payload: dict[str, object]) -> None:
        if self._connection is None:
            raise RuntimeError("IoT client is not connected.")

        message = json.dumps(payload)
        self._connection.publish(topic=topic, payload=message, qos=self._mqtt_qos)
        thing = payload.get("thing_name")
        if thing is not None:
            self.logger.info("Published topic=%s thing=%s", topic, thing)
        else:
            self.logger.info("Published topic=%s", topic)

    def disconnect(self) -> None:
        if self._connection is None:
            return

        self.logger.info("Disconnecting from AWS IoT Core.")
        disconnect_future = self._connection.disconnect()
        disconnect_future.result()
        self._connection = None
        self.logger.info("Disconnected from AWS IoT Core.")

    def get_mqtt_connection(self) -> object | None:
        return self._connection
