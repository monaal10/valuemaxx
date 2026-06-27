"""Async-job store for ``async_job`` capabilities (submit returns promptly; poll later).

An ``async_job`` capability must not block the submit request. The submit route runs
the capability handler in a background thread, records a job, and returns a
``job_id`` immediately; the caller polls ``GET /jobs/{job_id}`` for the status and
(when finished) the result. Jobs are tenant-scoped so a poll only sees its own
tenant's jobs.

This is an in-memory runner (one process). The poll is non-blocking: it reports
``running`` until the background thread finishes, then ``succeeded`` (with the
serialized result) or ``failed`` (with the error message). A handler that raises is
captured as a failed job, never crashing the API.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from valuemaxx.api.errors import JobNotFoundError

if TYPE_CHECKING:
    from collections.abc import Callable

JobStatus = Literal["running", "succeeded", "failed"]


@dataclass
class _Job:
    """One background job, with its own lock guarding its mutable state."""

    job_id: str
    tenant_id: str
    status: JobStatus = "running"
    result: dict[str, object] | None = None
    error: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def mark_succeeded(self, result: dict[str, object]) -> None:
        """Record a successful result (thread-safe)."""
        with self.lock:
            self.status = "succeeded"
            self.result = result

    def mark_failed(self, message: str) -> None:
        """Record a failure message (thread-safe)."""
        with self.lock:
            self.status = "failed"
            self.error = message

    def snapshot(self) -> dict[str, object]:
        """A thread-safe copy of the job's current status/result/error."""
        with self.lock:
            return {
                "job_id": self.job_id,
                "status": self.status,
                "result": self.result,
                "error": self.error,
            }


class JobStore:
    """An in-memory, tenant-scoped store of background jobs."""

    def __init__(self) -> None:
        self._jobs: dict[str, _Job] = {}
        self._lock = threading.Lock()

    def submit(self, tenant_id: str, work: Callable[[], dict[str, object]]) -> str:
        """Start ``work`` in the background and return its job id immediately."""
        job_id = str(uuid.uuid4())
        job = _Job(job_id=job_id, tenant_id=tenant_id)
        with self._lock:
            self._jobs[job_id] = job

        def run() -> None:
            try:
                result = work()
            except Exception as exc:
                job.mark_failed(f"{type(exc).__name__}: {exc}")
            else:
                job.mark_succeeded(result)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return job_id

    def get(self, tenant_id: str, job_id: str) -> dict[str, object]:
        """Return the job's status (+ result/error) for ``tenant_id``.

        Raises :class:`JobNotFoundError` if the id is unknown OR belongs to another
        tenant (so a poll can never observe another tenant's job).
        """
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None or job.tenant_id != tenant_id:
            raise JobNotFoundError(f"no job {job_id!r} for this tenant")
        return job.snapshot()


__all__ = ["JobStatus", "JobStore"]
