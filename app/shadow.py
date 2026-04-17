from __future__ import annotations

import copy
import json
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

ShadowMessageHandler = Callable[[str, bytes], None]


def shadow_document_base(thing_name: str, shadow_name: str) -> str:
    """Return the MQTT topic prefix for classic (empty name) or named shadows."""
    name = (shadow_name or "").strip()
    if name:
        return f"$aws/things/{thing_name}/shadow/name/{name}"
    return f"$aws/things/{thing_name}/shadow"


def shadow_topics(thing_name: str, shadow_name: str) -> dict[str, str]:
    base = shadow_document_base(thing_name, shadow_name)
    return {
        "get": f"{base}/get",
        "get_accepted": f"{base}/get/accepted",
        "get_rejected": f"{base}/get/rejected",
        "update": f"{base}/update",
        "update_delta": f"{base}/update/delta",
        "update_accepted": f"{base}/update/accepted",
        "update_rejected": f"{base}/update/rejected",
    }


def deep_merge(dst: dict[str, Any], patch: Mapping[str, Any]) -> None:
    """Recursively merge patch into dst (dst is updated in place)."""
    for key, value in patch.items():
        if (
            key in dst
            and isinstance(dst[key], dict)
            and isinstance(value, Mapping)
        ):
            deep_merge(dst[key], value)
        else:
            dst[key] = copy.deepcopy(value)


def extract_shadow_state(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Return the `state` object from a get/accepted or delta document."""
    state = payload.get("state")
    if isinstance(state, dict):
        return state
    return None


def reported_device_state(
    *,
    sampling_interval_seconds: int,
    feature_flags: Mapping[str, bool],
    thresholds: Mapping[str, float],
    firmware_version: str,
    last_telemetry_timestamp: str | None = None,
) -> dict[str, Any]:
    return {
        "sampling_interval_seconds": sampling_interval_seconds,
        "feature_flags": dict(feature_flags),
        "thresholds": {k: float(v) for k, v in thresholds.items()},
        "firmware_version": firmware_version,
        **(
            {"last_telemetry_timestamp": last_telemetry_timestamp}
            if last_telemetry_timestamp
            else {}
        ),
    }


@dataclass
class ShadowRuntimeState:
    sampling_interval_seconds: int
    feature_flags: dict[str, bool] = field(default_factory=dict)
    thresholds: dict[str, float] = field(default_factory=dict)
    firmware_version: str = "1.0.0"
    last_telemetry_timestamp: str | None = None

    def snapshot_reported(self) -> dict[str, Any]:
        return reported_device_state(
            sampling_interval_seconds=self.sampling_interval_seconds,
            feature_flags=self.feature_flags,
            thresholds=self.thresholds,
            firmware_version=self.firmware_version,
            last_telemetry_timestamp=self.last_telemetry_timestamp,
        )


class DeviceShadowSync:
    """Subscribe to shadow topics, merge desired vs local state, publish reported."""

    def __init__(
        self,
        *,
        thing_name: str,
        shadow_name: str,
        default_interval_seconds: int,
        logger: logging.Logger,
    ) -> None:
        self._thing_name = thing_name
        self._shadow_name = shadow_name
        self._logger = logger
        self._lock = threading.Lock()
        self._topics = shadow_topics(thing_name, shadow_name)
        self._runtime = ShadowRuntimeState(
            sampling_interval_seconds=default_interval_seconds,
            firmware_version="1.0.0",
        )
        self._subscribe: Callable[[str, ShadowMessageHandler], None] | None = None
        self._publish: Callable[[str, dict[str, Any]], None] | None = None

    @property
    def topics(self) -> dict[str, str]:
        return self._topics

    def attach(
        self,
        subscribe: Callable[[str, ShadowMessageHandler], None],
        publish: Callable[[str, dict[str, Any]], None],
    ) -> None:
        self._subscribe = subscribe
        self._publish = publish

    def start(self) -> None:
        if self._subscribe is None or self._publish is None:
            raise RuntimeError("Shadow sync is not attached to a transport.")

        sub = self._subscribe
        sub(self._topics["get_accepted"], self._on_get_accepted)
        sub(self._topics["get_rejected"], self._on_get_rejected)
        sub(self._topics["update_delta"], self._on_delta)
        sub(self._topics["update_rejected"], self._on_update_rejected)

        self._logger.info(
            "Subscribed to device shadow topics (thing=%s named=%s)",
            self._thing_name,
            self._shadow_name or "(classic)",
        )
        self.request_full_shadow()

    def request_full_shadow(self) -> None:
        if self._publish is None:
            return
        self._publish(self._topics["get"], {"message": "GET"})

    def get_runtime(self) -> ShadowRuntimeState:
        with self._lock:
            return ShadowRuntimeState(
                sampling_interval_seconds=self._runtime.sampling_interval_seconds,
                feature_flags=dict(self._runtime.feature_flags),
                thresholds=dict(self._runtime.thresholds),
                firmware_version=self._runtime.firmware_version,
                last_telemetry_timestamp=self._runtime.last_telemetry_timestamp,
            )

    def set_last_telemetry_timestamp(self, iso_timestamp: str) -> None:
        with self._lock:
            self._runtime.last_telemetry_timestamp = iso_timestamp

    def _apply_desired_patch(self, desired: Mapping[str, Any]) -> None:
        if not desired:
            return
        patch: dict[str, Any] = {}
        if "sampling_interval_seconds" in desired:
            try:
                patch["sampling_interval_seconds"] = max(
                    1, int(desired["sampling_interval_seconds"])
                )
            except (TypeError, ValueError):
                self._logger.warning(
                    "Ignoring invalid sampling_interval_seconds in shadow desired: %s",
                    desired.get("sampling_interval_seconds"),
                )
        if "feature_flags" in desired and isinstance(desired["feature_flags"], Mapping):
            patch["feature_flags"] = desired["feature_flags"]
        if "thresholds" in desired and isinstance(desired["thresholds"], Mapping):
            clean: dict[str, float] = {}
            for k, v in desired["thresholds"].items():
                try:
                    clean[str(k)] = float(v)
                except (TypeError, ValueError):
                    self._logger.warning(
                        "Ignoring invalid threshold %s=%s", k, v
                    )
            patch["thresholds"] = clean

        if not patch:
            return

        with self._lock:
            if "sampling_interval_seconds" in patch:
                self._runtime.sampling_interval_seconds = patch[
                    "sampling_interval_seconds"
                ]
            if "feature_flags" in patch:
                deep_merge(
                    self._runtime.feature_flags,
                    {str(k): bool(v) for k, v in patch["feature_flags"].items()},
                )
            if "thresholds" in patch:
                deep_merge(self._runtime.thresholds, patch["thresholds"])

        self.publish_reported()

    def publish_reported(self) -> None:
        """Publish the current runtime snapshot as shadow reported state."""
        if self._publish is None:
            return
        with self._lock:
            reported = self._runtime.snapshot_reported()
        body: dict[str, Any] = {"state": {"reported": reported}}
        self._publish(self._topics["update"], body)
        self._logger.info(
            "Published shadow reported state sampling_interval=%s flags=%s",
            reported["sampling_interval_seconds"],
            list(reported.get("feature_flags", {}).keys()),
        )

    def _on_get_accepted(self, topic: str, payload: bytes) -> None:
        try:
            doc = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._logger.warning("Shadow get/accepted JSON parse failed: %s", exc)
            return
        state = extract_shadow_state(doc)
        if not state:
            return
        desired = state.get("desired")
        if isinstance(desired, Mapping) and desired:
            self._logger.info("Applying full shadow desired from get/accepted")
            self._apply_desired_patch(desired)
        else:
            self._logger.info("No shadow desired; publishing reported state only")
            self.publish_reported()

    def _on_get_rejected(self, topic: str, payload: bytes) -> None:
        self._logger.error("Shadow get rejected topic=%s payload=%s", topic, payload)

    def _on_delta(self, topic: str, payload: bytes) -> None:
        try:
            doc = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._logger.warning("Shadow delta JSON parse failed: %s", exc)
            return
        state = extract_shadow_state(doc)
        if not state:
            return
        self._logger.info("Applying shadow delta")
        self._apply_desired_patch(state)

    def _on_update_rejected(self, topic: str, payload: bytes) -> None:
        self._logger.error(
            "Shadow update rejected topic=%s payload=%s", topic, payload
        )
