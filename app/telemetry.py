from __future__ import annotations

import random
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.models import TelemetryReading

if TYPE_CHECKING:
    from app.shadow import ShadowDeviceConfig


class TelemetryGenerator:
    def __init__(self, thing_name: str, firmware_version: str, seed: int | None = None) -> None:
        self.thing_name = thing_name
        self.firmware_version = firmware_version
        self._random = random.Random(seed)

    def generate(self, shadow: ShadowDeviceConfig | None = None) -> TelemetryReading:
        ambient = round(self._random.uniform(18.0, 32.0), 2)
        cpu = round(self._random.uniform(42.0, 68.0), 2)
        humidity = round(self._random.uniform(30.0, 70.0), 2)
        battery = round(self._random.uniform(25.0, 100.0), 2)

        alert_cpu_high = False
        load_pct: float | None = None
        if shadow is not None:
            cap = shadow.thresholds.get("cpu_temp_c_max")
            if cap is not None and cpu > cap:
                alert_cpu_high = True
            if shadow.feature_flags.get("advanced_metrics"):
                load_pct = round(self._random.uniform(1.0, 100.0), 2)

        return TelemetryReading(
            thing_name=self.thing_name,
            timestamp=datetime.now(UTC).isoformat(),
            ambient_temp_c=ambient,
            cpu_temp_c=cpu,
            humidity_pct=humidity,
            battery_pct=battery,
            signal_dbm=self._random.randint(-95, -45),
            firmware_version=self.firmware_version,
            alert_cpu_high=alert_cpu_high,
            load_pct=load_pct,
        )
