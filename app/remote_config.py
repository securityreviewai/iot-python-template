from __future__ import annotations

import ipaddress
import json
import logging
import ssl
import threading
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Final
from urllib.parse import urlparse

if TYPE_CHECKING:
    from app.config import AppConfig
    from app.shadow import DeviceConfigStore

MAX_REMOTE_CONFIG_BYTES: Final[int] = 65_536
USER_AGENT: Final[str] = "iot-python-template/remote-config/1.0"


def _blocked_metadata_host(host_lower: str) -> bool:
    if host_lower in {"metadata.google.internal", "metadata.goog", "metadata"}:
        return True
    if host_lower == "169.254.169.254" or host_lower.startswith("169.254."):
        return True
    return False


def validate_remote_config_url(url: str, config: AppConfig) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("invalid remote config URL")
    if parsed.scheme == "http" and not config.remote_config_allow_insecure_http:
        raise ValueError("HTTP remote config disabled; use HTTPS or set REMOTE_CONFIG_ALLOW_INSECURE_HTTP")
    host = parsed.hostname
    host_lower = host.lower()
    allowed = config.remote_config_allowed_hosts()
    if allowed and host_lower not in allowed:
        raise ValueError("remote config host not in allowlist")
    if _blocked_metadata_host(host_lower):
        raise ValueError("remote config host blocked")

    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return
    if addr == ipaddress.ip_address("169.254.169.254"):
        raise ValueError("remote config IP blocked")
    if addr.is_link_local and addr != ipaddress.ip_address("127.0.0.1"):
        raise ValueError("remote config link-local IP blocked")


def fetch_remote_config_json(
    config: AppConfig,
    logger: logging.Logger,
) -> dict[str, object] | None:
    if not config.remote_config_url:
        return None
    try:
        validate_remote_config_url(config.remote_config_url, config)
    except ValueError as exc:
        logger.warning("Remote config URL rejected: %s", exc)
        return None

    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    token = config.remote_config_bearer_token.strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(
        config.remote_config_url,
        headers=headers,
        method="GET",
    )
    ctx = ssl.create_default_context()
    host_only = urlparse(config.remote_config_url).hostname or ""
    try:
        with urllib.request.urlopen(
            req,
            timeout=config.remote_config_request_timeout_seconds,
            context=ctx,
        ) as resp:
            body = resp.read(MAX_REMOTE_CONFIG_BYTES + 1)
    except urllib.error.HTTPError:
        logger.warning("Remote config HTTP error for host=%s", host_only)
        return None
    except urllib.error.URLError:
        logger.warning("Remote config network error for host=%s", host_only)
        return None
    except TimeoutError:
        logger.warning("Remote config request timed out for host=%s", host_only)
        return None

    if len(body) > MAX_REMOTE_CONFIG_BYTES:
        logger.warning("Remote config response too large for host=%s", host_only)
        return None
    try:
        doc = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("Remote config JSON parse failed for host=%s", host_only)
        return None
    if not isinstance(doc, dict):
        logger.warning("Remote config root must be an object for host=%s", host_only)
        return None
    ver = doc.get("config_version")
    if isinstance(ver, (int, float)) and not isinstance(ver, bool):
        logger.info(
            "Remote config fetched host=%s config_version=%s",
            host_only,
            int(ver),
        )
    else:
        logger.info("Remote config fetched host=%s", host_only)
    return doc


class RemoteConfigPoller:
    """Background GET of versioned JSON; merges into ``DeviceConfigStore`` (MQTT unchanged)."""

    def __init__(
        self,
        *,
        config: AppConfig,
        store: DeviceConfigStore,
        logger: logging.Logger,
    ) -> None:
        self._config = config
        self._store = store
        self._logger = logger
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self._config.remote_config_url:
            return
        self._thread = threading.Thread(target=self._run, name="remote-config", daemon=True)
        self._thread.start()

    def stop_and_join(self, timeout_s: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout_s)
            self._thread = None

    def _run(self) -> None:
        poll = max(5, int(self._config.remote_config_poll_seconds))
        while not self._stop.is_set():
            partial = fetch_remote_config_json(self._config, self._logger)
            if partial is not None:
                self._store.apply_partial(partial, self._logger)
            if self._stop.wait(timeout=float(poll)):
                break
