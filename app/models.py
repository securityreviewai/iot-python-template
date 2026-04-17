from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class TelemetryReading:
    thing_name: str
    timestamp: str
    ambient_temp_c: float
    cpu_temp_c: float
    humidity_pct: float
    battery_pct: float
    signal_dbm: int
    firmware_version: str

    def to_payload(self) -> dict[str, object]:
        return asdict(self)
