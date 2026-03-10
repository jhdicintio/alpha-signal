"""Background job runner: starts pending jobs via executor and polls for completion."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

from app.executor.base import ExecutionStatus, WorkflowExecutor
from app.jobs.store import JobStatus, JobStore, JobType

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 2.0


class JobRunner:
    """Background thread that starts PENDING jobs and polls RUNNING jobs."""

    def __init__(
        self,
        executor: WorkflowExecutor,
        store: JobStore,
        get_cache_path: Callable[[], str],
    ) -> None:
        self._executor = executor
        self._store = store
        self._get_cache_path = get_cache_path
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("JobRunner started")

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        logger.info("JobRunner stopped")

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._process_pending()
                self._poll_running()
            except Exception:
                logger.exception("JobRunner loop error")
            self._stop.wait(timeout=POLL_INTERVAL_SEC)

    def _process_pending(self) -> None:
        cache_path = self._get_cache_path()
        pending = [
            rec for rec in self._store.list_jobs(limit=100)
            if rec.status == JobStatus.PENDING
        ]
        for rec in pending:
            try:
                if rec.job_type == JobType.INGEST:
                    execution_id = self._executor.start_ingest(rec.params or {}, cache_path)
                elif rec.job_type == JobType.EXTRACT:
                    execution_id = self._executor.start_extract(rec.params or {}, cache_path)
                elif rec.job_type == JobType.PIPELINE:
                    execution_id = self._executor.start_pipeline(rec.params or {}, cache_path)
                else:
                    continue
                self._store.set_execution_started(rec.job_id, execution_id)
                logger.info("Started job %s execution %s", rec.job_id, execution_id)
            except Exception as e:
                logger.exception("Failed to start job %s", rec.job_id)
                self._store.set_failed(rec.job_id, str(e))

    def _poll_running(self) -> None:
        running = [
            rec for rec in self._store.list_jobs(limit=100)
            if rec.status == JobStatus.RUNNING and rec.execution_id
        ]
        for rec in running:
            result = self._executor.get_status(rec.execution_id)
            if result.status == ExecutionStatus.COMPLETED:
                self._store.set_completed(rec.job_id, result.result)
                logger.info("Job %s completed", rec.job_id)
            elif result.status == ExecutionStatus.FAILED:
                self._store.set_failed(rec.job_id, result.error or "Unknown error")
                logger.info("Job %s failed: %s", rec.job_id, result.error)
            elif result.status == ExecutionStatus.CANCELLED:
                self._store.set_cancelled(rec.job_id)
                logger.info("Job %s cancelled", rec.job_id)
