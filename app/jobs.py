from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Any, Protocol

from awscrt import mqtt as awscrt_mqtt


class JobExecutor(Protocol):
    """Runs the job document on the device; returns terminal JobStatus and statusDetails."""

    def execute(
        self, job_id: str, job_document: dict[str, Any]
    ) -> tuple[str, dict[str, str]]: ...


@dataclass(slots=True)
class JobAuditRecord:
    job_id: str
    operation: str
    status: str
    status_details: dict[str, str]
    job_document_preview: str
    started_at_monotonic: float
    finished_at_monotonic: float
    execution_number: int | None = None
    version_number: int | None = None


class TemplateJobExecutor:
    """
    Built-in operations for fleet jobs (extend or replace with real OTA / config logic).

    Job document shape: { "operation": "echo" | "diagnostics" | "sleep" | "fail", ... }
    """

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def execute(
        self, job_id: str, job_document: dict[str, Any]
    ) -> tuple[str, dict[str, str]]:
        from awsiot import iotjobs

        op = str(job_document.get("operation", "echo")).strip().lower()
        if op == "echo":
            self._logger.info("Job echo job_id=%s payload_keys=%s", job_id, list(job_document))
            return iotjobs.JobStatus.SUCCEEDED, {
                "message": "echo_ok",
                "keys": ",".join(sorted(str(k) for k in job_document.keys()))[:400],
            }
        if op == "diagnostics":
            details = {
                "uptime_hint": "ok",
                "job_id": job_id,
            }
            self._logger.info("Job diagnostics job_id=%s", job_id)
            return iotjobs.JobStatus.SUCCEEDED, details
        if op == "sleep":
            try:
                sec = max(0, min(300, int(job_document.get("seconds", 0))))
            except (TypeError, ValueError):
                sec = 0
            if sec:
                time.sleep(sec)
            return iotjobs.JobStatus.SUCCEEDED, {"slept_seconds": str(sec)}
        if op == "fail":
            return iotjobs.JobStatus.FAILED, {
                "reason": str(job_document.get("reason", "requested_failure"))[:400]
            }
        return iotjobs.JobStatus.FAILED, {"reason": f"unknown_operation:{op}"}


class DeviceJobsRunner:
    """
    AWS IoT Jobs: subscribe to notify-next and start-next responses, run executor,
    report IN_PROGRESS then SUCCEEDED / FAILED. Keeps a short in-memory audit trail.
    """

    def __init__(
        self,
        *,
        thing_name: str,
        mqtt_connection: Any,
        logger: logging.Logger,
        executor: JobExecutor | None = None,
        audit_max: int = 64,
    ) -> None:
        from awsiot import iotjobs

        self._thing_name = thing_name
        self._logger = logger
        self._executor: JobExecutor = executor or TemplateJobExecutor(logger)
        self._jobs = iotjobs.IotJobsClient(mqtt_connection)
        self._qos = awscrt_mqtt.QoS.AT_LEAST_ONCE
        self._lock = threading.Lock()
        self._busy = False
        self._audit: deque[JobAuditRecord] = deque(maxlen=audit_max)

    def audit_records(self) -> list[JobAuditRecord]:
        return list(self._audit)

    def start(self) -> None:
        from awsiot import iotjobs

        thing = self._thing_name
        fut, _ = self._jobs.subscribe_to_next_job_execution_changed_events(
            request=iotjobs.NextJobExecutionChangedSubscriptionRequest(thing_name=thing),
            qos=self._qos,
            callback=self._on_next_job_changed,
        )
        fut.result()

        fut, _ = self._jobs.subscribe_to_start_next_pending_job_execution_accepted(
            request=iotjobs.StartNextPendingJobExecutionSubscriptionRequest(
                thing_name=thing
            ),
            qos=self._qos,
            callback=self._on_start_next_accepted,
        )
        fut.result()

        fut, _ = self._jobs.subscribe_to_start_next_pending_job_execution_rejected(
            request=iotjobs.StartNextPendingJobExecutionSubscriptionRequest(
                thing_name=thing
            ),
            qos=self._qos,
            callback=self._on_start_next_rejected,
        )
        fut.result()

        self._logger.info("AWS IoT Jobs subscriptions ready thing=%s", thing)
        self._request_start_next()

    def _request_start_next(self) -> None:
        from awsiot import iotjobs

        with self._lock:
            if self._busy:
                return
        req = iotjobs.StartNextPendingJobExecutionRequest(
            thing_name=self._thing_name,
            client_token=str(uuid.uuid4()),
        )
        try:
            self._jobs.publish_start_next_pending_job_execution(
                req, self._qos
            ).result()
        except Exception:
            self._logger.exception("publish_start_next_pending_job_execution failed")

    def _on_next_job_changed(self, event: Any) -> None:
        if getattr(event, "execution", None) is None:
            return
        self._request_start_next()

    def _on_start_next_rejected(self, error: Any) -> None:
        self._logger.error(
            "start-next rejected code=%s message=%s",
            getattr(error, "code", None),
            getattr(error, "message", None),
        )

    def _on_start_next_accepted(self, response: Any) -> None:
        ex = getattr(response, "execution", None)
        if ex is None or not getattr(ex, "job_id", None):
            return
        with self._lock:
            if self._busy:
                self._logger.warning(
                    "Skipping job %s; another execution is in progress",
                    ex.job_id,
                )
                return
            self._busy = True

        try:
            self._run_job_execution(ex)
        finally:
            with self._lock:
                self._busy = False
            self._request_start_next()

    def _run_job_execution(self, ex: Any) -> None:
        from awsiot import iotjobs

        job_id = ex.job_id
        doc = ex.job_document if isinstance(ex.job_document, dict) else {}
        exec_num = ex.execution_number
        version = ex.version_number
        preview = json.dumps(doc, default=str)[:1800]
        t0 = time.monotonic()

        token_progress = str(uuid.uuid4())
        progress_req = iotjobs.UpdateJobExecutionRequest(
            thing_name=self._thing_name,
            job_id=job_id,
            status=iotjobs.JobStatus.IN_PROGRESS,
            client_token=token_progress,
            status_details={"phase": "running"},
        )
        if exec_num is not None:
            progress_req.execution_number = exec_num

        try:
            self._jobs.publish_update_job_execution(progress_req, self._qos).result()
        except Exception:
            self._logger.exception("Failed to publish IN_PROGRESS for job_id=%s", job_id)

        final_status: str
        details: dict[str, str]
        try:
            final_status, details = self._executor.execute(job_id, doc)
        except Exception as exc:
            self._logger.exception("Job executor failed job_id=%s", job_id)
            final_status = iotjobs.JobStatus.FAILED
            details = {"error": str(exc)[:400]}

        token_done = str(uuid.uuid4())
        terminal_req = iotjobs.UpdateJobExecutionRequest(
            thing_name=self._thing_name,
            job_id=job_id,
            status=final_status,
            client_token=token_done,
            status_details=details,
        )
        if exec_num is not None:
            terminal_req.execution_number = exec_num

        try:
            self._jobs.publish_update_job_execution(terminal_req, self._qos).result()
        except Exception:
            self._logger.exception(
                "Failed to publish terminal status for job_id=%s", job_id
            )

        t1 = time.monotonic()
        op = str(doc.get("operation", "echo"))
        self._audit.append(
            JobAuditRecord(
                job_id=job_id,
                operation=op,
                status=final_status,
                status_details=dict(details),
                job_document_preview=preview,
                started_at_monotonic=t0,
                finished_at_monotonic=t1,
                execution_number=exec_num,
                version_number=version,
            )
        )
        self._logger.info(
            "Job finished job_id=%s status=%s duration_s=%.2f",
            job_id,
            final_status,
            t1 - t0,
        )
