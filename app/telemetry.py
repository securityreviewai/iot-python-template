from __future__ import annotations

import random
from collections.abc import Mapping
from datetime import UTC, datetime

from app.models import TelemetryReading


class TelemetryGenerator:
    def __init__(self, thing_name: str, seed: int | None = None) -> None:
        self.thing_name = thing_name
        self._random = random.Random(seed)

    def generate(
        self,
        *,
        feature_flags: Mapping[str, bool] | None = None,
        thresholds: Mapping[str, float] | None = None,
        firmware_version: str | None = None,
        remote_config_version: str | None = None,
    ) -> TelemetryReading:
        flags = dict(feature_flags or {})
        thr = dict(thresholds or {})
        fw = firmware_version or "1.0.0"

        ambient_hi, ambient_lo = 32.0, 18.0
        cpu_hi, cpu_lo = 68.0, 42.0
        if flags.get("eco_mode"):
            ambient_hi, ambient_lo = 28.0, 20.0
            cpu_hi, cpu_lo = 62.0, 44.0

        ambient_temp_c = round(self._random.uniform(ambient_lo, ambient_hi), 2)
        cpu_temp_c = round(self._random.uniform(cpu_lo, cpu_hi), 2)
        humidity_pct = round(self._random.uniform(30.0, 70.0), 2)
        battery_pct = round(self._random.uniform(25.0, 100.0), 2)
        signal_dbm = self._random.randint(-95, -45)

        alerts: list[str] = []
        if (m := thr.get("cpu_temp_c_max")) is not None and cpu_temp_c > m:
            alerts.append("cpu_temp_high")
        if (m := thr.get("ambient_temp_c_max")) is not None and ambient_temp_c > m:
            alerts.append("ambient_temp_high")
        if (m := thr.get("humidity_pct_max")) is not None and humidity_pct > m:
            alerts.append("humidity_high")
        if (m := thr.get("battery_pct_min")) is not None and battery_pct < m:
            alerts.append("battery_low")

        return TelemetryReading(
            thing_name=self.thing_name,
            timestamp=datetime.now(UTC).isoformat(),
            ambient_temp_c=ambient_temp_c,
            cpu_temp_c=cpu_temp_c,
            humidity_pct=humidity_pct,
            battery_pct=battery_pct,
            signal_dbm=signal_dbm,
            firmware_version=fw,
            threshold_alerts=alerts,
            remote_config_version=remote_config_version,
        )
