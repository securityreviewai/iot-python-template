from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.config import AppConfig


class AppConfigTests(unittest.TestCase):
    def test_from_env_uses_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = AppConfig.from_env()

        self.assertEqual(config.iot_client_id, "device-simulator-001")
        self.assertEqual(config.publish_interval_seconds, 5)
        self.assertEqual(config.missing_connection_fields(), ["IOT_ENDPOINT", "IOT_CERT_PATH", "IOT_KEY_PATH"])

    def test_from_env_reads_values(self) -> None:
        with patch.dict(
            os.environ,
            {
                "IOT_ENDPOINT": "example-ats.iot.us-east-1.amazonaws.com",
                "IOT_CLIENT_ID": "thing-001",
                "IOT_TOPIC": "devices/thing-001/telemetry",
                "IOT_CERT_PATH": "certs/device.pem.crt",
                "IOT_KEY_PATH": "certs/private.pem.key",
                "PUBLISH_INTERVAL_SECONDS": "10",
            },
            clear=True,
        ):
            config = AppConfig.from_env()

        self.assertEqual(config.iot_client_id, "thing-001")
        self.assertEqual(config.publish_interval_seconds, 10)
        self.assertEqual(config.missing_connection_fields(), [])


if __name__ == "__main__":
    unittest.main()
