from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class AppConfig:
    app_env: str
    log_level: str
    aws_region: str
    iot_endpoint: str
    iot_client_id: str
    iot_thing_name: str
    iot_topic: str
    iot_cert_path: str
    iot_key_path: str
    iot_ca_path: str
    publish_interval_seconds: int

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            app_env=os.getenv("APP_ENV", "development"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            aws_region=os.getenv("AWS_REGION", "us-east-1"),
            iot_endpoint=os.getenv("IOT_ENDPOINT", ""),
            iot_client_id=os.getenv("IOT_CLIENT_ID", "device-simulator-001"),
            iot_thing_name=os.getenv("IOT_THING_NAME", "device-simulator-001"),
            iot_topic=os.getenv("IOT_TOPIC", "devices/device-simulator-001/telemetry"),
            iot_cert_path=os.getenv("IOT_CERT_PATH", ""),
            iot_key_path=os.getenv("IOT_KEY_PATH", ""),
            iot_ca_path=os.getenv("IOT_CA_PATH", ""),
            publish_interval_seconds=int(os.getenv("PUBLISH_INTERVAL_SECONDS", "5")),
        )

    def missing_connection_fields(self) -> list[str]:
        missing: list[str] = []
        required = {
            "IOT_ENDPOINT": self.iot_endpoint,
            "IOT_CLIENT_ID": self.iot_client_id,
            "IOT_TOPIC": self.iot_topic,
            "IOT_CERT_PATH": self.iot_cert_path,
            "IOT_KEY_PATH": self.iot_key_path,
        }
        for name, value in required.items():
            if not value:
                missing.append(name)
        return missing
