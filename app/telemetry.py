from __future__ import annotations

import random
from datetime import UTC, datetime

from app.models import TelemetryReading


class TelemetryGenerator:
    def __init__(self, thing_name: str, seed: int | None = None) -> None:
        self.thing_name = thing_name
        self._random = random.Random(seed)

    def generate(self) -> TelemetryReading:
        return TelemetryReading(
            thing_name=self.thing_name,
            timestamp=datetime.now(UTC).isoformat(),
            ambient_temp_c=round(self._random.uniform(18.0, 32.0), 2),
            cpu_temp_c=round(self._random.uniform(42.0, 68.0), 2),
            humidity_pct=round(self._random.uniform(30.0, 70.0), 2),
            battery_pct=round(self._random.uniform(25.0, 100.0), 2),
            signal_dbm=self._random.randint(-95, -45),
            firmware_version="1.0.0",
        )
