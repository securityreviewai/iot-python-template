from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from queue import Empty, Queue
from typing import TYPE_CHECKING, Final

from app.shadow import DeviceConfigStore, _valid_mqtt_publish_topic

if TYPE_CHECKING:
    from app.aws_iot import IoTClient
    from app.config import AppConfig

MAX_JOB_DOCUMENT_BYTES: Final[int] = 16_384
STATUS_DETAILS_MAX_KEYS: Final[int] = 16
STATUS_DETAIL_KEY_LEN: Final[int] = 64
STATUS_DETAIL_VAL_LEN: Final[int] = 256
JOB_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

ALLOWED_OPERATIONS: Final[frozenset[str]] = frozenset(
    {"noop", "config", "diagnostic", "firmware"}
)
ALLOWED_DIAGNOSTICS: Final[frozenset[str]] = frozenset({"ping", "metrics_snapshot"})


def _job_topics(thing_name: str) -> dict[str, str]:
    base = f"$aws/things/{thing_name}/jobs"
    return {
        "notify_next": f"{base}/notify-next",
        "start_next": f"{base}/start-next",
        "start_next_accepted": f"{base}/start-next/accepted",
        "start_next_rejected": f"{base}/start-next/rejected",
        "update": f"{base}/{{job_id}}/update",
    }


def _sanitize_status_details(raw: Mapping[str, object] | None) -> dict[str, str]:
    if not raw:
        return {}
    out: dict[str, str] = {}
    for i, (k, v) in enumerate(raw.items()):
        if i >= STATUS_DETAILS_MAX_KEYS:
            break
        if not isinstance(k, str):
            continue
        key = k.strip()[:STATUS_DETAIL_KEY_LEN]
        if not key:
            continue
        val = "" if v is None else str(v)
        out[key] = val[:STATUS_DETAIL_VAL_LEN]
    return out


def _parse_job_document(raw: object) -> dict[str, object] | None:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return {}
        try:
            doc = json.loads(stripped)
        except json.JSONDecodeError:
            return None
        return dict(doc) if isinstance(doc, dict) else None
    return None


@dataclass(slots=True)
class _PendingExecution:
    job_id: str
    execution_number: int
    version_number: int
    job_document: dict[str, object]


class JobsBridge:
    """AWS IoT Jobs device workflow: notify-next, start-next, UpdateJobExecution, optional audit publish."""

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
        self._paths = _job_topics(config.iot_thing_name)
        self._queue: Queue[_PendingExecution | None] = Queue()
        self._shutdown = threading.Event()
        self._worker = threading.Thread(target=self._worker_loop, name="iot-jobs-worker", daemon=True)

    def install(self) -> None:
        self._logger.info("Installing AWS IoT Jobs subscriptions for thing=%s", self._config.iot_thing_name)
        self._client.subscribe(self._paths["notify_next"], self._on_notify_next_raw)
        self._client.subscribe(self._paths["start_next_accepted"], self._on_start_next_accepted_raw)
        self._client.subscribe(self._paths["start_next_rejected"], self._on_start_next_rejected_raw)
        self._worker.start()
        self._publish_start_next()

    def shutdown(self) -> None:
        self._shutdown.set()
        self._queue.put(None)
        self._worker.join(timeout=15.0)
        if self._worker.is_alive():
            self._logger.warning("IoT Jobs worker did not stop cleanly.")

    def _publish_start_next(self) -> None:
        if self._shutdown.is_set():
            return
        token = str(uuid.uuid4())
        self._client.publish(self._paths["start_next"], {"clientToken": token})

    def _publish_job_update(
        self,
        job_id: str,
        status: str,
        *,
        execution_number: int,
        expected_version: int,
        status_details: dict[str, str] | None = None,
    ) -> None:
        topic = self._paths["update"].format(job_id=job_id)
        payload: dict[str, object] = {
            "status": status,
            "clientToken": str(uuid.uuid4()),
            "executionNumber": execution_number,
            "expectedVersion": str(expected_version),
        }
        if status_details:
            payload["statusDetails"] = status_details
        self._client.publish(topic, payload)

    def _on_notify_next_raw(self, topic: str, payload: bytes) -> None:
        del topic
        if self._shutdown.is_set():
            return
        if len(payload) > MAX_JOB_DOCUMENT_BYTES:
            self._logger.warning("Jobs notify-next exceeded max size; requesting next via start-next only")
        self._publish_start_next()

    def _on_start_next_rejected_raw(self, topic: str, payload: bytes) -> None:
        del topic
        code = "unknown"
        if len(payload) <= MAX_JOB_DOCUMENT_BYTES:
            try:
                doc = json.loads(payload.decode("utf-8"))
                if isinstance(doc, dict) and doc.get("code"):
                    code = str(doc.get("code"))[:64]
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
        self._logger.warning("Jobs start-next rejected code=%s", code)

    def _on_start_next_accepted_raw(self, topic: str, payload: bytes) -> None:
        del topic
        if self._shutdown.is_set():
            return
        if len(payload) > MAX_JOB_DOCUMENT_BYTES:
            self._logger.warning("Jobs start-next/accepted exceeded max size; ignoring")
            return
        try:
            doc = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._logger.warning("Jobs start-next/accepted JSON parse failed")
            return
        if not isinstance(doc, dict):
            return
        execution = doc.get("execution")
        if execution is None:
            self._logger.info("Jobs start-next/accepted: no pending execution")
            return
        if not isinstance(execution, dict):
            self._logger.warning("Jobs start-next/accepted: invalid execution shape")
            return
        job_id = execution.get("jobId")
        if not isinstance(job_id, str) or not JOB_ID_PATTERN.match(job_id):
            self._logger.warning("Jobs start-next/accepted: invalid or missing jobId")
            return
        en = execution.get("executionNumber")
        vn = execution.get("versionNumber")
        if isinstance(en, bool) or not isinstance(en, int):
            self._logger.warning("Jobs execution missing executionNumber job_id=%s", job_id[:32])
            return
        if isinstance(vn, bool) or not isinstance(vn, int):
            self._logger.warning("Jobs execution missing versionNumber job_id=%s", job_id[:32])
            return
        jdoc = _parse_job_document(execution.get("jobDocument"))
        if jdoc is None:
            self._logger.warning("Jobs execution jobDocument invalid job_id=%s", job_id[:32])
            self._publish_job_update(
                job_id,
                "FAILED",
                execution_number=en,
                expected_version=vn,
                status_details=_sanitize_status_details({"reason": "invalid_job_document"}),
            )
            return
        self._queue.put(
            _PendingExecution(
                job_id=job_id,
                execution_number=en,
                version_number=vn,
                job_document=jdoc,
            )
        )

    def _worker_loop(self) -> None:
        while not self._shutdown.is_set():
            try:
                item = self._queue.get(timeout=0.5)
            except Empty:
                continue
            if item is None:
                break
            try:
                self._run_execution(item)
            except Exception:
                self._logger.exception("Unhandled error in job worker job_id=%s", item.job_id[:32])
            finally:
                if not self._shutdown.is_set():
                    self._publish_start_next()

    def _run_execution(self, pending: _PendingExecution) -> None:
        job_id = pending.job_id
        if len(json.dumps(pending.job_document, separators=(",", ":")).encode("utf-8")) > MAX_JOB_DOCUMENT_BYTES:
            self._logger.warning("Job document over size limit after parse job_id=%s", job_id[:32])
            self._publish_job_update(
                job_id,
                "FAILED",
                execution_number=pending.execution_number,
                expected_version=pending.version_number,
                status_details=_sanitize_status_details({"reason": "document_too_large"}),
            )
            return

        in_progress_details = _sanitize_status_details({"phase": "device_handler"})
        self._publish_job_update(
            job_id,
            "IN_PROGRESS",
            execution_number=pending.execution_number,
            expected_version=pending.version_number,
            status_details=in_progress_details,
        )

        ok, details, internal_reason = self._execute_job_document(pending.job_document)
        terminal = "SUCCEEDED" if ok else "FAILED"
        merged = _sanitize_status_details(details)
        if not ok and internal_reason and "reason" not in merged:
            merged = _sanitize_status_details({**merged, "reason": "job_failed"})
        self._publish_job_update(
            job_id,
            terminal,
            execution_number=pending.execution_number,
            expected_version=pending.version_number + 1,
            status_details=merged,
        )
        self._maybe_audit_publish(job_id, pending.execution_number, terminal, pending.job_document, merged)

    def _execute_job_document(
        self, doc: dict[str, object]
    ) -> tuple[bool, dict[str, object], str | None]:
        op = doc.get("operation")
        if op is None:
            op = "noop"
        if not isinstance(op, str) or op not in ALLOWED_OPERATIONS:
            return False, {"reason": "unsupported_operation"}, "bad_operation"

        if op == "noop":
            return True, {"result": "noop_applied"}, None

        if op == "config":
            patch = doc.get("patch")
            if not isinstance(patch, dict):
                return False, {"reason": "invalid_config_patch"}, "config_patch"
            self._store.apply_partial(patch, self._logger)
            return True, {"result": "config_applied"}, None

        if op == "diagnostic":
            name = doc.get("name")
            if not isinstance(name, str) or name not in ALLOWED_DIAGNOSTICS:
                return False, {"reason": "unsupported_diagnostic"}, "bad_diagnostic"
            if name == "ping":
                return True, {"diagnostic": "ping", "result": "ok"}, None
            if name == "metrics_snapshot":
                snap = self._store.current()
                keys = sorted(snap.to_reported_config().keys())
                return True, {"diagnostic": "metrics_snapshot", "reported_keys": ",".join(keys)[:200]}, None

        if op == "firmware":
            target = doc.get("target_version")
            if not isinstance(target, str):
                return False, {"reason": "invalid_target_version"}, "bad_target"
            tv = target.strip()
            if not tv or len(tv) > 64 or any(c in tv for c in {"\n", "\r", "\x00"}):
                return False, {"reason": "invalid_target_version"}, "bad_target"
            current = self._config.firmware_version
            if tv == current:
                return True, {"result": "already_current", "target_version": tv[:32]}, None
            return True, {"result": "simulated_staged", "target_version": tv[:32]}, None

        return False, {"reason": "unsupported_operation"}, "bad_operation"

    def _maybe_audit_publish(
        self,
        job_id: str,
        execution_number: int,
        terminal: str,
        document: dict[str, object],
        status_details: dict[str, str],
    ) -> None:
        topic = (self._config.iot_jobs_audit_topic or "").strip()
        if not topic:
            return
        if not _valid_mqtt_publish_topic(topic):
            self._logger.warning("Invalid IOT_JOBS_AUDIT_TOPIC; skipping audit publish")
            return
        op = document.get("operation")
        op_str = str(op) if isinstance(op, str) else "unknown"
        payload = {
            "thing_name": self._config.iot_thing_name,
            "job_id": job_id,
            "execution_number": execution_number,
            "status": terminal,
            "operation": op_str[:32],
            "completed_at": datetime.now(tz=UTC).isoformat(),
            "status_details": dict(status_details),
        }
        self._client.publish(topic, payload)
