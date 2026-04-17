from __future__ import annotations

import unittest

from app.telemetry import TelemetryGenerator


class TelemetryGeneratorTests(unittest.TestCase):
    def test_generate_returns_expected_shape(self) -> None:
        reading = TelemetryGenerator("thing-001", firmware_version="1.0.0", seed=7).generate()
        payload = reading.to_payload()

        self.assertEqual(payload["thing_name"], "thing-001")
        self.assertEqual(payload["firmware_version"], "1.0.0")
        self.assertIn("timestamp", payload)
        self.assertGreaterEqual(payload["ambient_temp_c"], 18.0)
        self.assertLessEqual(payload["ambient_temp_c"], 32.0)
        self.assertGreaterEqual(payload["battery_pct"], 25.0)
        self.assertLessEqual(payload["battery_pct"], 100.0)
        self.assertNotIn("load_pct", payload)

    def test_advanced_metrics_adds_load_pct(self) -> None:
        from app.shadow import ShadowDeviceConfig

        shadow = ShadowDeviceConfig(
            5,
            {"advanced_metrics": True},
            {},
        )
        reading = TelemetryGenerator("thing-001", firmware_version="1.0.0", seed=3).generate(
            shadow
        )
        payload = reading.to_payload()
        self.assertIn("load_pct", payload)


if __name__ == "__main__":
    unittest.main()
