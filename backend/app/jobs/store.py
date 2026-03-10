"""In-memory job store for platform workflow jobs."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class JobType(str, Enum):
    INGEST = "ingest"
    EXTRACT = "extract"
    PIPELINE = "pipeline"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class JobRecord:
    job_id: str
    job_type: JobType
    status: JobStatus
    execution_id: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    params: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "job_id": self.job_id,
            "job_type": self.job_type.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() + "Z",
        }
        if self.execution_id is not None:
            out["execution_id"] = self.execution_id
        if self.result is not None:
            out["result"] = self.result
        if self.error is not None:
            out["error"] = self.error
        if self.started_at is not None:
            out["started_at"] = self.started_at.isoformat() + "Z"
        if self.finished_at is not None:
            out["finished_at"] = self.finished_at.isoformat() + "Z"
        if self.params is not None:
            out["params"] = self.params
        return out


class JobStore:
    """Thread-safe in-memory job store."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()

    def create(
        self,
        job_type: JobType,
        params: Optional[dict[str, Any]] = None,
    ) -> JobRecord:
        job_id = str(uuid.uuid4())
        record = JobRecord(
            job_id=job_id,
            job_type=job_type,
            status=JobStatus.PENDING,
            params=params,
        )
        with self._lock:
            self._jobs[job_id] = record
        return record

    def get(self, job_id: str) -> Optional[JobRecord]:
        with self._lock:
            return self._jobs.get(job_id)

    def set_execution_started(self, job_id: str, execution_id: str) -> None:
        with self._lock:
            rec = self._jobs.get(job_id)
            if rec:
                rec.execution_id = execution_id
                rec.status = JobStatus.RUNNING
                rec.started_at = datetime.utcnow()

    def set_completed(self, job_id: str, result: Optional[dict[str, Any]] = None) -> None:
        with self._lock:
            rec = self._jobs.get(job_id)
            if rec:
                rec.status = JobStatus.COMPLETED
                rec.finished_at = datetime.utcnow()
                if result is not None:
                    rec.result = result

    def set_failed(self, job_id: str, error: str) -> None:
        with self._lock:
            rec = self._jobs.get(job_id)
            if rec:
                rec.status = JobStatus.FAILED
                rec.finished_at = datetime.utcnow()
                rec.error = error

    def set_cancelled(self, job_id: str) -> None:
        with self._lock:
            rec = self._jobs.get(job_id)
            if rec:
                rec.status = JobStatus.CANCELLED
                rec.finished_at = datetime.utcnow()

    def list_jobs(
        self,
        limit: int = 50,
        offset: int = 0,
        job_type: Optional[JobType] = None,
    ) -> list[JobRecord]:
        with self._lock:
            records = list(self._jobs.values())
        if job_type is not None:
            records = [r for r in records if r.job_type == job_type]
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records[offset : offset + limit]
