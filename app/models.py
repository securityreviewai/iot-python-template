from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Final

ALWAYS_TELEMETRY_KEYS: Final[frozenset[str]] = frozenset(
    {"thing_name", "timestamp", "firmware_version"}
)


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
    alert_cpu_high: bool = False
    load_pct: float | None = None

    def to_payload(self) -> dict[str, object]:
        raw = asdict(self)
        if raw.get("load_pct") is None:
            del raw["load_pct"]
        return raw


def telemetry_payload_for_mqtt(
    reading: TelemetryReading, sensor_mask: frozenset[str] | None
) -> dict[str, object]:
    """Build MQTT JSON from a reading. When ``sensor_mask`` is None, all keys are included."""
    full = reading.to_payload()
    if sensor_mask is None:
        return full
    out: dict[str, object] = {}
    for key in ALWAYS_TELEMETRY_KEYS:
        if key in full:
            out[key] = full[key]
    for key in sensor_mask:
        if key in full:
            out[key] = full[key]
    return out
