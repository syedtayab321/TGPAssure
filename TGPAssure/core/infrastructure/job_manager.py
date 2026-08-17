from __future__ import annotations

import json
import sqlite3
import traceback
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QThreadPool, QRunnable, QCoreApplication

from core.data_access.db_engine import DatabaseEngine
from core.infrastructure.job import Job, JobSpec, JobHandle, JobStatus, CancellationToken
from core.infrastructure.task_scheduler import TaskScheduler

class _JobRunner(QRunnable):
    def __init__(self, job: Job, context: Any, callback: Any) -> None:
        super().__init__()
        self.job = job
        self.context = context
        self.callback = callback
        self.cancel_token = CancellationToken()

    def run(self) -> None:
        try:
            self.callback.on_job_started(self.job)
            result = self.job.run(self.context, self.cancel_token)
            if self.cancel_token.is_cancelled():
                self.callback.on_job_cancelled(self.job)
            else:
                self.callback.on_job_completed(self.job, result)
        except Exception as e:
            self.callback.on_job_failed(self.job, str(e), traceback.format_exc())

class JobManager(QObject):
    job_started = Signal(int)
    job_progress = Signal(int, float)
    job_completed = Signal(int, object)
    job_failed = Signal(int, str)
    job_cancelled = Signal(int)

    def __init__(self, db_engine: DatabaseEngine) -> None:
        super().__init__()
        self.db_engine = db_engine
        self.thread_pool = QThreadPool()
        self._jobs: Dict[int, Job] = {}
        self._runners: Dict[int, _JobRunner] = {}
        self._context: Optional[Any] = None
        self._running_jobs: Dict[int, bool] = {}
        self._scheduler: Optional[TaskScheduler] = None

    def initialize(self, context: Any) -> None:
        self._context = context

    def submit(self, job: Job) -> int:
        job_id = self._insert_job(job)
        job.set_job_id(job_id)
        self._jobs[job_id] = job
        self._running_jobs[job_id] = True
        job.set_progress_callback(lambda progress, jid=job_id: self._record_progress(jid, progress))
        runner = _JobRunner(job, self._context, self)
        self._runners[job_id] = runner
        self.job_started.emit(job_id)
        # Start immediately. Deferring with QTimer.singleShot created a race where
        # callers could invoke wait_for_all_jobs() before the runnable had even
        # entered the thread pool, causing false "completed" waits and leaving
        # workers alive after temporary project databases were deleted.
        self.thread_pool.start(runner)
        return job_id

    def set_task_scheduler(self, scheduler: TaskScheduler) -> None:
        """Provide an external TaskScheduler for delayed job submission."""
        self._scheduler = scheduler

    def schedule_job(self, job: Job, delay_seconds: float) -> None:
        """Schedule a job to be submitted after `delay_seconds` using the TaskScheduler.

        If no scheduler is set, the job is submitted immediately.
        """
        if self._scheduler is None:
            self.submit(job)
            return

        def _submit_wrapper():
            try:
                self.submit(job)
            except Exception:
                pass

        self._scheduler.schedule(f"job-{job.get_job_uuid()}", _submit_wrapper, delay_seconds)

    def cancel(self, job_id: int) -> bool:
        """Request cooperative cancellation without pretending the worker has stopped.

        The cancellation signal is emitted only after the runnable returns and
        acknowledges the token.  This keeps the global loader visible and avoids
        users closing/replacing datasets while scientific code is still touching
        them in a worker thread.
        """
        if job_id in self._runners:
            runner = self._runners[job_id]
            runner.cancel_token.cancel()
            return True
        return False

    def cancel_all(self) -> None:
        for job_id in list(self._runners.keys()):
            self.cancel(job_id)

    def get_job_status(self, job_id: int) -> Optional[JobHandle]:
        conn = self.db_engine.get_read_connection()
        try:
            row = conn.execute(
                "SELECT id, job_uuid, job_type, module, status, progress, message, "
                "result_json, error_text, created_at, started_at, finished_at "
                "FROM jobs WHERE id = ?",
                (job_id,)
            ).fetchone()
            if row is None:
                return None
            status = self._parse_status(row["status"])
            return JobHandle(
                job_id=row["id"],
                job_uuid=row["job_uuid"],
                job_type=row["job_type"],
                module=row["module"],
                status=status,
                progress=row["progress"],
                message=row["message"],
                result_json=row["result_json"],
                error_text=row["error_text"],
                created_at=self._parse_datetime(row["created_at"]),
                started_at=self._parse_datetime(row["started_at"]),
                finished_at=self._parse_datetime(row["finished_at"])
            )
        finally:
            conn.close()

    def get_all_jobs(self) -> List[JobHandle]:
        conn = self.db_engine.get_read_connection()
        try:
            rows = conn.execute(
                "SELECT id, job_uuid, job_type, module, status, progress, message, "
                "result_json, error_text, created_at, started_at, finished_at "
                "FROM jobs ORDER BY created_at DESC"
            ).fetchall()
            results = []
            for row in rows:
                status = self._parse_status(row["status"])
                results.append(JobHandle(
                    job_id=row["id"],
                    job_uuid=row["job_uuid"],
                    job_type=row["job_type"],
                    module=row["module"],
                    status=status,
                    progress=row["progress"],
                    message=row["message"],
                    result_json=row["result_json"],
                    error_text=row["error_text"],
                    created_at=self._parse_datetime(row["created_at"]),
                    started_at=self._parse_datetime(row["started_at"]),
                    finished_at=self._parse_datetime(row["finished_at"])
                ))
            return results
        finally:
            conn.close()

    def on_job_started(self, job: Job) -> None:
        job_id = job.get_job_id()
        if job_id is not None:
            self._update_job_started(job_id)
            self._running_jobs[job_id] = True

    def on_job_completed(self, job: Job, result: Any) -> None:
        job_id = job.get_job_id()
        if job_id is not None:
            result_json = json.dumps(result) if result is not None else None
            self._update_job_completed(job_id, result_json)
            self._running_jobs[job_id] = False
            if job.get_progress() < 1.0:
                job.update_progress(1.0)
            job.set_progress_callback(None)
            self._runners.pop(job_id, None)
            self.job_completed.emit(job_id, result)

    def on_job_failed(self, job: Job, error: str, traceback_str: str) -> None:
        job_id = job.get_job_id()
        if job_id is not None:
            full_error = f"{error}\n{traceback_str}"
            self._update_job_failed(job_id, full_error)
            self._running_jobs[job_id] = False
            job.set_progress_callback(None)
            self._runners.pop(job_id, None)
            self.job_failed.emit(job_id, error)

    def on_job_cancelled(self, job: Job) -> None:
        job_id = job.get_job_id()
        if job_id is not None:
            self._running_jobs[job_id] = False
            self._update_job_cancelled(job_id)
            job.set_progress_callback(None)
            self._runners.pop(job_id, None)
            self.job_cancelled.emit(job_id)

    def _record_progress(self, job_id: int, progress: float) -> None:
        """Persist and publish progress reported directly by a Job instance."""
        if job_id not in self._jobs:
            return
        value = max(0.0, min(1.0, float(progress)))
        self._update_job_progress(job_id, value)
        self.job_progress.emit(job_id, value)

    def update_progress(self, job_id: int, progress: float) -> None:
        """Compatibility endpoint for contexts that report via the manager."""
        if job_id in self._jobs:
            value = max(0.0, min(1.0, float(progress)))
            self._jobs[job_id].update_progress(value, notify=False)
            self._record_progress(job_id, value)

    def _insert_job(self, job: Job) -> int:
        conn = self.db_engine.get_write_connection()
        try:
            cursor = conn.execute(
                "INSERT INTO jobs (job_uuid, job_type, module, priority, payload_json, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
                (job.get_job_uuid(), job.get_job_type(), job.get_module(),
                 job.get_priority(), job.get_payload(), JobStatus.QUEUED.name)
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def _update_job_status(self, job_id: int, status: JobStatus) -> None:
        conn = self.db_engine.get_write_connection()
        try:
            conn.execute(
                "UPDATE jobs SET status = ?, updated_at = datetime('now') WHERE id = ?",
                (status.name, job_id)
            )
            conn.commit()
        finally:
            conn.close()

    def _update_job_started(self, job_id: int) -> None:
        conn = self.db_engine.get_write_connection()
        try:
            conn.execute(
                "UPDATE jobs SET status = ?, started_at = datetime('now'), updated_at = datetime('now') "
                "WHERE id = ?",
                (JobStatus.RUNNING.name, job_id)
            )
            conn.commit()
        finally:
            conn.close()

    def _update_job_progress(self, job_id: int, progress: float) -> None:
        conn = self.db_engine.get_write_connection()
        try:
            conn.execute(
                "UPDATE jobs SET progress = ?, updated_at = datetime('now') WHERE id = ?",
                (progress, job_id)
            )
            conn.commit()
        finally:
            conn.close()

    def _update_job_cancelled(self, job_id: int) -> None:
        conn = self.db_engine.get_write_connection()
        try:
            conn.execute(
                "UPDATE jobs SET status = ?, finished_at = datetime('now'), updated_at = datetime('now') WHERE id = ?",
                (JobStatus.CANCELLED.name, job_id),
            )
            conn.commit()
        finally:
            conn.close()

    def _update_job_completed(self, job_id: int, result_json: Optional[str]) -> None:
        conn = self.db_engine.get_write_connection()
        try:
            conn.execute(
                "UPDATE jobs SET status = ?, result_json = ?, finished_at = datetime('now'), "
                "progress = 1.0, updated_at = datetime('now') WHERE id = ?",
                (JobStatus.COMPLETED.name, result_json, job_id)
            )
            conn.commit()
        finally:
            conn.close()

    def _update_job_failed(self, job_id: int, error_text: str) -> None:
        conn = self.db_engine.get_write_connection()
        try:
            conn.execute(
                "UPDATE jobs SET status = ?, error_text = ?, finished_at = datetime('now'), "
                "updated_at = datetime('now') WHERE id = ?",
                (JobStatus.FAILED.name, error_text, job_id)
            )
            conn.commit()
        finally:
            conn.close()

    def _parse_status(self, status_str: str) -> JobStatus:
        try:
            return JobStatus[status_str]
        except KeyError:
            return JobStatus.QUEUED

    def _parse_datetime(self, dt_str: Optional[str]) -> Optional[datetime]:
        if dt_str is None:
            return None
        try:
            return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        except ValueError:
            return None

    def wait_for_all_jobs(self, timeout_ms: int = 30000) -> bool:
        """Wait for workers while continuing to dispatch queued Qt signals."""
        import time

        deadline = time.monotonic() + max(0, timeout_ms) / 1000.0
        app = QCoreApplication.instance()
        while True:
            remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
            slice_ms = min(25, remaining_ms)
            if self.thread_pool.waitForDone(slice_ms):
                if app is not None:
                    app.processEvents()
                return True
            if app is not None:
                app.processEvents()
            if time.monotonic() >= deadline:
                return False