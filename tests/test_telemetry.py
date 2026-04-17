from __future__ import annotations

import unittest

from app.telemetry import TelemetryGenerator


class TelemetryGeneratorTests(unittest.TestCase):
    def test_generate_returns_expected_shape(self) -> None:
        reading = TelemetryGenerator("thing-001", seed=7).generate()
        payload = reading.to_payload()

        self.assertEqual(payload["thing_name"], "thing-001")
        self.assertEqual(payload["firmware_version"], "1.0.0")
        self.assertIn("timestamp", payload)
        self.assertGreaterEqual(payload["ambient_temp_c"], 18.0)
        self.assertLessEqual(payload["ambient_temp_c"], 32.0)
        self.assertGreaterEqual(payload["battery_pct"], 25.0)
        self.assertLessEqual(payload["battery_pct"], 100.0)
        self.assertEqual(payload["threshold_alerts"], [])

    def test_threshold_alerts_when_over_limit(self) -> None:
        reading = TelemetryGenerator("thing-001", seed=1).generate(
            thresholds={"cpu_temp_c_max": 0.0},
        )
        self.assertIn("cpu_temp_high", reading.threshold_alerts)


if __name__ == "__main__":
    unittest.main()
