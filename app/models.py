from __future__ import annotations

from dataclasses import asdict, dataclass, field


_SENSOR_KEYS: frozenset[str] = frozenset(
    {
        "ambient_temp_c",
        "cpu_temp_c",
        "humidity_pct",
        "battery_pct",
        "signal_dbm",
    }
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
    threshold_alerts: list[str] = field(default_factory=list)
    remote_config_version: str | None = None

    def to_payload(
        self,
        include_sensor_keys: frozenset[str] | None = None,
    ) -> dict[str, object]:
        data = asdict(self)
        if include_sensor_keys is not None:
            for k in _SENSOR_KEYS:
                if k not in include_sensor_keys:
                    del data[k]
        if data.get("remote_config_version") is None:
            del data["remote_config_version"]
        return data
