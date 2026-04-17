from __future__ import annotations

import json
import logging
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.parse import quote

# Logical sensor ids used in remote JSON (mapped to TelemetryReading payload keys).
ALL_SENSORS: frozenset[str] = frozenset(
    {"ambient", "cpu", "humidity", "battery", "signal"}
)

SENSOR_TO_PAYLOAD_KEY: dict[str, str] = {
    "ambient": "ambient_temp_c",
    "cpu": "cpu_temp_c",
    "humidity": "humidity_pct",
    "battery": "battery_pct",
    "signal": "signal_dbm",
}


def logical_sensors_to_payload_keys(logical: frozenset[str]) -> frozenset[str]:
    return frozenset(SENSOR_TO_PAYLOAD_KEY[s] for s in logical if s in SENSOR_TO_PAYLOAD_KEY)


@dataclass(slots=True)
class RemoteConfigSnapshot:
    """Versioned config from HTTPS; merged with env defaults and optional shadow overrides."""

    version: str
    publish_interval_seconds: int | None = None
    telemetry_topic: str | None = None
    feature_flags: dict[str, bool] = field(default_factory=dict)
    thresholds: dict[str, float] = field(default_factory=dict)
    enabled_sensors: frozenset[str] | None = None
    sampling_every_n_cycles: dict[str, int] = field(default_factory=dict)


def _as_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return False


def parse_remote_config_doc(data: Mapping[str, Any]) -> RemoteConfigSnapshot:
    version = data.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("remote config must include non-empty string 'version'")

    interval: int | None = None
    raw_iv = data.get("publish_interval_seconds")
    if raw_iv is not None:
        interval = max(1, int(raw_iv))

    topic = data.get("telemetry_topic")
    topic_s = topic.strip() if isinstance(topic, str) and topic.strip() else None

    flags: dict[str, bool] = {}
    raw_flags = data.get("feature_flags")
    if isinstance(raw_flags, Mapping):
        flags = {str(k): _as_bool(v) for k, v in raw_flags.items()}

    thresholds: dict[str, float] = {}
    raw_thr = data.get("thresholds")
    if isinstance(raw_thr, Mapping):
        for k, v in raw_thr.items():
            try:
                thresholds[str(k)] = float(v)
            except (TypeError, ValueError):
                continue

    enabled: frozenset[str] | None = None
    raw_en = data.get("enabled_sensors")
    if isinstance(raw_en, list):
        cand = frozenset(str(x).strip().lower() for x in raw_en if str(x).strip())
        unknown = cand - ALL_SENSORS
        if unknown:
            cand = frozenset(x for x in cand if x in ALL_SENSORS)
        enabled = cand if cand else frozenset()

    sampling: dict[str, int] = {}
    raw_samp = data.get("sampling")
    if isinstance(raw_samp, Mapping):
        per = raw_samp.get("per_sensor")
        if isinstance(per, Mapping):
            for name, spec in per.items():
                key = str(name).strip().lower()
                if key not in ALL_SENSORS:
                    continue
                if isinstance(spec, Mapping):
                    n = spec.get("every_n_cycles", spec.get("sample_every_n_cycles", 1))
                else:
                    n = spec
                try:
                    ni = max(1, int(n))
                except (TypeError, ValueError):
                    continue
                sampling[key] = ni

    return RemoteConfigSnapshot(
        version=version.strip(),
        publish_interval_seconds=interval,
        telemetry_topic=topic_s,
        feature_flags=flags,
        thresholds=thresholds,
        enabled_sensors=enabled,
        sampling_every_n_cycles=sampling,
    )


@dataclass
class RemoteConfigCache:
    """In-memory cache + conditional GET (ETag / Last-Modified)."""

    snapshot: RemoteConfigSnapshot | None = None
    etag: str | None = None
    last_modified: str | None = None
    fetched_at_monotonic: float = 0.0
    last_error: str | None = None


class RemoteConfigFetcher:
    """
    Pull versioned JSON over HTTPS. On failure, previous snapshot remains valid (stale-if-error).
    Supports If-None-Match / If-Modified-Since when the server sends ETag / Last-Modified.
    """

    def __init__(
        self,
        *,
        url_template: str,
        thing_name: str,
        poll_interval_seconds: float,
        timeout_seconds: float,
        logger: logging.Logger,
        auth_header: str | None = None,
    ) -> None:
        self._url_template = url_template
        self._thing_name = thing_name
        self._poll_interval_seconds = max(1.0, float(poll_interval_seconds))
        self._timeout_seconds = timeout_seconds
        self._logger = logger
        self._auth_header = auth_header
        self._cache = RemoteConfigCache()

    @property
    def cache(self) -> RemoteConfigCache:
        return self._cache

    def resolved_url(self) -> str:
        return self._url_template.format(
            thing_name=quote(self._thing_name, safe=""),
            thing=self._thing_name,
        )

    def maybe_refresh(self, now_monotonic: float | None = None) -> None:
        now = time.monotonic() if now_monotonic is None else now_monotonic
        if now - self._cache.fetched_at_monotonic < self._poll_interval_seconds:
            return
        self._cache.fetched_at_monotonic = now
        self._fetch()

    def force_refresh(self) -> None:
        self._cache.fetched_at_monotonic = time.monotonic()
        self._fetch()

    def _fetch(self) -> None:
        url = self.resolved_url()
        headers = {"Accept": "application/json"}
        if self._auth_header:
            headers["Authorization"] = self._auth_header
        if self._cache.etag:
            headers["If-None-Match"] = self._cache.etag
        if self._cache.last_modified:
            headers["If-Modified-Since"] = self._cache.last_modified

        req = urllib.request.Request(url, method="GET", headers=headers)
        ctx = ssl.create_default_context()
        try:
            with urllib.request.urlopen(
                req, timeout=self._timeout_seconds, context=ctx
            ) as resp:
                self._cache.last_error = None
                etag = resp.headers.get("ETag")
                if etag:
                    self._cache.etag = etag
                lm = resp.headers.get("Last-Modified")
                if lm:
                    self._cache.last_modified = lm
                raw = resp.read()
                if resp.status == 200:
                    doc = json.loads(raw.decode("utf-8"))
                    if not isinstance(doc, dict):
                        raise ValueError("config JSON must be an object")
                    self._cache.snapshot = parse_remote_config_doc(doc)
                    self._logger.info(
                        "Loaded remote config version=%s from %s",
                        self._cache.snapshot.version,
                        url,
                    )
        except urllib.error.HTTPError as exc:
            if exc.code == 304:
                self._logger.debug("Remote config unchanged (304) url=%s", url)
                self._cache.last_error = None
                return
            self._cache.last_error = f"HTTP {exc.code}"
            self._logger.warning(
                "Remote config HTTP error %s url=%s (using cache if any)",
                exc.code,
                url,
            )
        except urllib.error.URLError as exc:
            self._cache.last_error = str(exc.reason)
            self._logger.warning(
                "Remote config fetch failed url=%s err=%s (using cache if any)",
                url,
                exc.reason,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
            self._cache.last_error = str(exc)
            self._logger.warning(
                "Remote config parse failed url=%s err=%s (using cache if any)",
                url,
                exc,
            )


def effective_publish_interval(
    *,
    env_default: int,
    remote: RemoteConfigSnapshot | None,
    shadow_interval: int | None,
) -> int:
    v = env_default
    if remote is not None and remote.publish_interval_seconds is not None:
        v = remote.publish_interval_seconds
    if shadow_interval is not None:
        v = shadow_interval
    return max(1, v)


def effective_feature_flags(
    remote: RemoteConfigSnapshot | None,
    shadow_flags: Mapping[str, bool] | None,
) -> dict[str, bool]:
    out: dict[str, bool] = {}
    if remote is not None:
        out.update(remote.feature_flags)
    if shadow_flags is not None:
        out.update(shadow_flags)
    return out


def effective_thresholds(
    remote: RemoteConfigSnapshot | None,
    shadow_thr: Mapping[str, float] | None,
) -> dict[str, float]:
    out: dict[str, float] = {}
    if remote is not None:
        out.update(remote.thresholds)
    if shadow_thr is not None:
        out.update(shadow_thr)
    return out


def effective_telemetry_topic(
    *,
    env_topic: str,
    thing_name: str,
    remote: RemoteConfigSnapshot | None,
) -> str:
    tpl = None
    if remote is not None and remote.telemetry_topic:
        tpl = remote.telemetry_topic
    if not tpl:
        return env_topic
    return tpl.format(thing_name=thing_name, thing=thing_name)


def payload_keys_for_cycle(
    *,
    cycle: int,
    remote: RemoteConfigSnapshot | None,
) -> frozenset[str] | None:
    """
    None means include all sensor columns.
    Otherwise frozenset of TelemetryReading asdict keys for sensors to include.
    """
    if remote is None:
        return None
    if remote.enabled_sensors is None:
        logical = ALL_SENSORS
    else:
        logical = remote.enabled_sensors
        if not logical:
            return frozenset()

    keys: set[str] = set()
    for s in logical:
        n = 1
        if remote is not None:
            n = remote.sampling_every_n_cycles.get(s, 1)
        if n <= 1:
            include = True
        else:
            include = ((cycle - 1) % n) == 0
        if include and s in SENSOR_TO_PAYLOAD_KEY:
            keys.add(SENSOR_TO_PAYLOAD_KEY[s])
    return frozenset(keys) if keys else frozenset()
