from __future__ import annotations

import os
from dataclasses import dataclass


def _truthy_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


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
    iot_shadow_name: str
    firmware_version: str
    publish_interval_seconds: int
    remote_config_url: str
    remote_config_poll_seconds: int
    remote_config_request_timeout_seconds: float
    remote_config_allow_insecure_http: bool
    remote_config_allowed_hosts_raw: str
    remote_config_bearer_token: str
    iot_jobs_enabled: bool
    iot_jobs_audit_topic: str

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
            iot_shadow_name=os.getenv("IOT_SHADOW_NAME", ""),
            firmware_version=os.getenv("FIRMWARE_VERSION", "1.0.0"),
            publish_interval_seconds=int(os.getenv("PUBLISH_INTERVAL_SECONDS", "5")),
            remote_config_url=os.getenv("REMOTE_CONFIG_URL", "").strip(),
            remote_config_poll_seconds=int(os.getenv("REMOTE_CONFIG_POLL_SECONDS", "300")),
            remote_config_request_timeout_seconds=float(
                os.getenv("REMOTE_CONFIG_REQUEST_TIMEOUT_SECONDS", "10")
            ),
            remote_config_allow_insecure_http=_truthy_env("REMOTE_CONFIG_ALLOW_INSECURE_HTTP"),
            remote_config_allowed_hosts_raw=os.getenv("REMOTE_CONFIG_ALLOWED_HOSTS", ""),
            remote_config_bearer_token=os.getenv("REMOTE_CONFIG_BEARER_TOKEN", ""),
            iot_jobs_enabled=_truthy_env("IOT_JOBS_ENABLED", True),
            iot_jobs_audit_topic=os.getenv("IOT_JOBS_AUDIT_TOPIC", "").strip(),
        )

    def remote_config_allowed_hosts(self) -> frozenset[str]:
        raw = self.remote_config_allowed_hosts_raw.strip()
        if not raw:
            return frozenset()
        return frozenset(part.strip().lower() for part in raw.split(",") if part.strip())

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
