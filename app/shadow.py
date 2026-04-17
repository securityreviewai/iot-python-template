from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, replace
from threading import Lock
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from app.aws_iot import IoTClient
    from app.config import AppConfig

MAX_SHADOW_PAYLOAD_BYTES: Final[int] = 16_384
INTERVAL_MIN: Final[int] = 1
INTERVAL_MAX: Final[int] = 86_400
SHADOW_DEVICE_STATUS_MIN_INTERVAL_S: Final[float] = 30.0

ALLOWED_FLAG_KEYS: Final[frozenset[str]] = frozenset(
    {"advanced_metrics", "high_resolution_sensors"}
)
ALLOWED_THRESHOLD_KEYS: Final[frozenset[str]] = frozenset(
    {
        "cpu_temp_c_max",
        "ambient_temp_c_max",
        "humidity_pct_max",
        "battery_pct_min",
    }
)
ALLOWED_SENSOR_KEYS: Final[frozenset[str]] = frozenset(
    {
        "ambient_temp_c",
        "cpu_temp_c",
        "humidity_pct",
        "battery_pct",
        "signal_dbm",
        "alert_cpu_high",
        "load_pct",
    }
)
TELEMETRY_TOPIC_MAX_LEN: Final[int] = 256


def _valid_mqtt_publish_topic(topic: str) -> bool:
    if not topic or len(topic) > TELEMETRY_TOPIC_MAX_LEN:
        return False
    if any(ch in topic for ch in "+#\x00"):
        return False
    return True


@dataclass(slots=True)
class ShadowDeviceConfig:
    sampling_interval_seconds: int
    feature_flags: dict[str, bool]
    thresholds: dict[str, float]
    shadow_version: int | None = None
    telemetry_topic: str | None = None
    sensor_mask: frozenset[str] | None = None
    remote_config_version: int | None = None

    @classmethod
    def from_app_config(cls, config: AppConfig) -> ShadowDeviceConfig:
        return cls(
            sampling_interval_seconds=config.publish_interval_seconds,
            feature_flags={},
            thresholds={},
            shadow_version=None,
            telemetry_topic=None,
            sensor_mask=None,
            remote_config_version=None,
        )

    def to_reported_config(self) -> dict[str, object]:
        return {
            "sampling_interval_seconds": self.sampling_interval_seconds,
            "feature_flags": dict(self.feature_flags),
            "thresholds": {k: float(v) for k, v in self.thresholds.items()},
        }


def validate_and_merge_state(
    current: ShadowDeviceConfig,
    partial: object,
    logger: logging.Logger,
) -> ShadowDeviceConfig:
    if not isinstance(partial, dict):
        return current

    next_interval = current.sampling_interval_seconds
    flags = dict(current.feature_flags)
    thresh = dict(current.thresholds)
    version = current.shadow_version
    next_topic = current.telemetry_topic
    sensor_mask = current.sensor_mask
    remote_cfg_version = current.remote_config_version

    interval_raw: object | None = None
    if "sampling_interval_seconds" in partial:
        interval_raw = partial["sampling_interval_seconds"]
    elif "publish_interval_seconds" in partial:
        interval_raw = partial["publish_interval_seconds"]

    if interval_raw is not None:
        raw = interval_raw
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            logger.warning("Ignoring invalid sampling_interval_seconds type from shadow")
        else:
            iv = int(raw)
            if iv < INTERVAL_MIN or iv > INTERVAL_MAX:
                logger.warning("Clamping sampling_interval_seconds from shadow into allowed range")
                iv = max(INTERVAL_MIN, min(INTERVAL_MAX, iv))
            next_interval = iv

    raw_flags = partial.get("feature_flags")
    if raw_flags is not None:
        if isinstance(raw_flags, dict):
            for k, v in raw_flags.items():
                if k not in ALLOWED_FLAG_KEYS:
                    continue
                if isinstance(v, bool):
                    flags[k] = v
        else:
            logger.warning("Ignoring invalid feature_flags payload from shadow")

    raw_t = partial.get("thresholds")
    if raw_t is not None:
        if isinstance(raw_t, dict):
            for k, v in raw_t.items():
                if k not in ALLOWED_THRESHOLD_KEYS:
                    continue
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    continue
                thresh[k] = float(v)
        else:
            logger.warning("Ignoring invalid thresholds payload from shadow")

    if "version" in partial and isinstance(partial["version"], int):
        version = partial["version"]

    if "telemetry_topic" in partial:
        raw_tp = partial["telemetry_topic"]
        if raw_tp is None:
            next_topic = None
        elif isinstance(raw_tp, str):
            candidate = raw_tp.strip()
            if not candidate:
                next_topic = None
            elif _valid_mqtt_publish_topic(candidate):
                next_topic = candidate
            else:
                logger.warning("Ignoring invalid telemetry_topic from config partial")
        else:
            logger.warning("Ignoring invalid telemetry_topic type from config partial")

    if "sensors" in partial:
        raw_sensors = partial["sensors"]
        if raw_sensors is None:
            sensor_mask = None
        elif isinstance(raw_sensors, dict):
            enabled = frozenset(
                str(k)
                for k, v in raw_sensors.items()
                if k in ALLOWED_SENSOR_KEYS and v is True
            )
            sensor_mask = enabled if enabled else frozenset()
        else:
            logger.warning("Ignoring invalid sensors payload from config partial")

    if "config_version" in partial:
        cv = partial["config_version"]
        if isinstance(cv, bool) or not isinstance(cv, (int, float)):
            logger.warning("Ignoring invalid config_version from remote config")
        else:
            remote_cfg_version = int(cv)

    return ShadowDeviceConfig(
        sampling_interval_seconds=next_interval,
        feature_flags=flags,
        thresholds=thresh,
        shadow_version=version,
        telemetry_topic=next_topic,
        sensor_mask=sensor_mask,
        remote_config_version=remote_cfg_version,
    )


class DeviceConfigStore:
    """Thread-safe device runtime config (shadow deltas, remote HTTP config, etc.)."""

    def __init__(self, initial: ShadowDeviceConfig) -> None:
        self._lock = Lock()
        self._state = initial

    def current(self) -> ShadowDeviceConfig:
        with self._lock:
            return replace(self._state)

    def apply_partial(self, partial: dict[str, object], logger: logging.Logger) -> ShadowDeviceConfig:
        with self._lock:
            self._state = validate_and_merge_state(self._state, partial, logger)
            return replace(self._state)

    def replace_shadow_version(self, version: int | None) -> ShadowDeviceConfig:
        with self._lock:
            self._state = replace(self._state, shadow_version=version)
            return replace(self._state)


def shadow_paths(thing_name: str, shadow_name: str | None) -> dict[str, str]:
    if shadow_name:
        base = f"$aws/things/{thing_name}/shadow/name/{shadow_name}"
    else:
        base = f"$aws/things/{thing_name}/shadow"
    return {
        "base": base,
        "delta": f"{base}/update/delta",
        "update": f"{base}/update",
        "get": f"{base}/get",
        "get_accepted": f"{base}/get/accepted",
    }


class ShadowBridge:
    def __init__(
        self,
        *,
        config: AppConfig,
        client: IoTClient,
        logger: logging.Logger,
        store: DeviceConfigStore,
    ) -> None:
        self._config = config
        self._client = client
        self._logger = logger
        self._store = store
        name = config.iot_shadow_name.strip() or None
        self._paths = shadow_paths(config.iot_thing_name, name)

    def install(self) -> None:
        self._client.subscribe(self._paths["delta"], self._on_delta_raw)
        self._client.subscribe(self._paths["get_accepted"], self._on_get_accepted_raw)
        self._client.publish(self._paths["get"], {})

    def sync_device_status(self, last_telemetry_iso: str) -> None:
        snap = self._store.current()
        reported = self._build_reported_for(snap)
        device_obj = reported.get("device")
        device: dict[str, object] = dict(device_obj) if isinstance(device_obj, dict) else {}
        device["last_telemetry_iso"] = last_telemetry_iso
        reported = {**reported, "device": device}
        self._publish_reported(reported, source="device_status")

    def _build_reported_for(self, state: ShadowDeviceConfig) -> dict[str, object]:
        cfg = state.to_reported_config()
        device: dict[str, object] = {
            "firmware_version": self._config.firmware_version,
        }
        if state.shadow_version is not None:
            device["acknowledged_shadow_version"] = state.shadow_version
        return {**cfg, "device": device}

    def _publish_reported(self, reported: dict[str, object], source: str) -> None:
        token = str(uuid.uuid4())
        payload: dict[str, object] = {
            "state": {"reported": reported},
            "clientToken": token,
        }
        self._logger.info("Publishing shadow reported update source=%s", source)
        self._client.publish(self._paths["update"], payload)

    def _apply_partial(self, partial: dict[str, object], source: str) -> None:
        snap = self._store.apply_partial(partial, self._logger)
        reported = self._build_reported_for(snap)
        self._publish_reported(reported, source=source)

    def _on_delta_raw(self, topic: str, payload: bytes) -> None:
        del topic
        if len(payload) > MAX_SHADOW_PAYLOAD_BYTES:
            self._logger.warning("Shadow delta exceeded max size; ignoring")
            return
        try:
            doc = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._logger.warning("Shadow delta JSON parse failed")
            return
        if not isinstance(doc, dict):
            return
        version = doc.get("version")
        state = doc.get("state")
        if not isinstance(state, dict):
            self._logger.info("Shadow delta ignored (missing state) version=%s", version)
            return
        partial: dict[str, object] = {k: v for k, v in state.items()}
        if isinstance(version, int):
            partial["version"] = version
        self._logger.info(
            "Applying shadow delta version=%s key_count=%s",
            version,
            len(partial),
        )
        self._apply_partial(partial, source="delta")

    def _on_get_accepted_raw(self, topic: str, payload: bytes) -> None:
        del topic
        if len(payload) > MAX_SHADOW_PAYLOAD_BYTES:
            self._logger.warning("Shadow get/accepted exceeded max size; ignoring")
            return
        try:
            doc = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._logger.warning("Shadow get/accepted JSON parse failed")
            return
        if not isinstance(doc, dict):
            return
        version = doc.get("version")
        st = doc.get("state")
        if not isinstance(st, dict):
            return
        desired = st.get("desired")
        if not isinstance(desired, dict) or not desired:
            self._logger.info("Shadow get/accepted baseline sync version=%s", version)
            if isinstance(version, int):
                snap = self._store.replace_shadow_version(version)
            else:
                snap = self._store.current()
            reported = self._build_reported_for(snap)
            self._publish_reported(reported, source="get_accepted_baseline")
            return

        partial = {k: v for k, v in desired.items()}
        if isinstance(version, int):
            partial["version"] = version
        self._logger.info(
            "Applying shadow desired from get/accepted version=%s key_count=%s",
            version,
            len(partial),
        )
        self._apply_partial(partial, source="get_accepted")
