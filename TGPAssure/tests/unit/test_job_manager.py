from __future__ import annotations

import pytest
import time
import tempfile
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QTest

from core.data_access.db_engine import DatabaseEngine
from core.infrastructure.job_manager import JobManager
from core.infrastructure.job import Job, JobSpec, JobStatus, CancellationToken, JobHandle
from modules.example.sleep_job import SleepJob, FailingJob, CancellableSleepJob

@pytest.fixture
def app() -> QCoreApplication:
    return QCoreApplication.instance() or QCoreApplication([])

@pytest.fixture
def temp_db() -> Path:
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = Path(f.name)
    return db_path

@pytest.fixture
def db_engine(temp_db: Path) -> DatabaseEngine:
    db_engine = DatabaseEngine(temp_db)
    schema_sql = """
    CREATE TABLE project (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        project_uuid TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        schema_version INTEGER NOT NULL DEFAULT 0
    );
    INSERT INTO project (id, project_uuid, name) VALUES (1, 'test-uuid', 'Test Project');
    CREATE TABLE jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL DEFAULT 1,
        file_id INTEGER,
        job_uuid TEXT NOT NULL UNIQUE,
        job_type TEXT NOT NULL,
        module TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'queued',
        priority INTEGER NOT NULL DEFAULT 0,
        progress REAL NOT NULL DEFAULT 0.0,
        message TEXT,
        payload_json TEXT NOT NULL DEFAULT '{}',
        result_json TEXT,
        error_text TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        started_at TEXT,
        finished_at TEXT,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES project(id) ON DELETE CASCADE
    );
    """
    conn = db_engine.get_write_connection()
    try:
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()
    return db_engine

@pytest.fixture
def job_manager(app: QCoreApplication, db_engine: DatabaseEngine) -> JobManager:
    manager = JobManager(db_engine)
    manager.initialize(None)
    return manager

@pytest.fixture
def mock_context() -> Any:
    return MagicMock()

def test_submit_job(job_manager: JobManager) -> None:
    job = SleepJob(0.1)
    job_id = job_manager.submit(job)
    assert job_id is not None
    assert job_id > 0
    handle = job_manager.get_job_status(job_id)
    assert handle is not None
    assert handle.job_type == "sleep"
    assert handle.module == "example"

def test_job_progress_signals(job_manager: JobManager, qtbot: Any) -> None:
    progress_values = []
    completed_event = []

    def on_progress(job_id: int, progress: float) -> None:
        progress_values.append(progress)

    def on_completed(job_id: int, result: Any) -> None:
        completed_event.append(job_id)

    job_manager.job_progress.connect(on_progress)
    job_manager.job_completed.connect(on_completed)
    job = SleepJob(0.5)
    job_id = job_manager.submit(job)
    QTest.qWait(100)
    job_manager.wait_for_all_jobs(5000)
    assert len(progress_values) > 0
    assert progress_values[-1] == 1.0
    assert completed_event == [job_id]

def test_job_persists_to_database(job_manager: JobManager) -> None:
    job = SleepJob(0.1)
    job_id = job_manager.submit(job)
    job_manager.wait_for_all_jobs(5000)
    handle = job_manager.get_job_status(job_id)
    assert handle is not None
    assert handle.status == JobStatus.COMPLETED
    assert handle.progress == 1.0
    result = json.loads(handle.result_json) if handle.result_json else {}
    assert result.get("completed") is True

def test_cancel_job(job_manager: JobManager) -> None:
    cancelled = []
    completed = []
    
    def on_cancelled(job_id: int) -> None:
        cancelled.append(job_id)
    
    def on_completed(job_id: int, result: Any) -> None:
        completed.append(job_id)
    
    job_manager.job_cancelled.connect(on_cancelled)
    job_manager.job_completed.connect(on_completed)
    job = CancellableSleepJob(2.0)
    job_id = job_manager.submit(job)
    time.sleep(0.5)
    job_manager.cancel(job_id)
    job_manager.wait_for_all_jobs(5000)
    assert job_id in cancelled
    handle = job_manager.get_job_status(job_id)
    assert handle is not None
    assert handle.status == JobStatus.CANCELLED

def test_job_failure_handling(job_manager: JobManager) -> None:
    failed = []
    
    def on_failed(job_id: int, error: str) -> None:
        failed.append((job_id, error))
    
    job_manager.job_failed.connect(on_failed)
    job = FailingJob()
    job_id = job_manager.submit(job)
    job_manager.wait_for_all_jobs(5000)
    assert len(failed) == 1
    assert failed[0][0] == job_id
    assert "fail" in failed[0][1].lower()
    handle = job_manager.get_job_status(job_id)
    assert handle is not None
    assert handle.status == JobStatus.FAILED
    assert handle.error_text is not None

def test_multiple_jobs_parallel(job_manager: JobManager) -> None:
    completed = []
    def on_completed(job_id: int, result: Any) -> None:
        completed.append(job_id)
    job_manager.job_completed.connect(on_completed)
    jobs = [SleepJob(0.3) for _ in range(5)]
    job_ids = []
    for job in jobs:
        job_ids.append(job_manager.submit(job))
    job_manager.wait_for_all_jobs(10000)
    assert len(completed) == 5
    for job_id in job_ids:
        handle = job_manager.get_job_status(job_id)
        assert handle is not None
        assert handle.status == JobStatus.COMPLETED

def test_job_manager_get_all_jobs(job_manager: JobManager) -> None:
    jobs = [SleepJob(0.1) for _ in range(3)]
    for job in jobs:
        job_manager.submit(job)
    job_manager.wait_for_all_jobs(5000)
    all_jobs = job_manager.get_all_jobs()
    assert len(all_jobs) >= 3
    for handle in all_jobs:
        assert handle.job_type == "sleep"

def test_job_progress_update_during_execution(job_manager: JobManager) -> None:
    progress_updates = []
    def on_progress(job_id: int, progress: float) -> None:
        progress_updates.append((job_id, progress))
    job_manager.job_progress.connect(on_progress)
    job = SleepJob(0.5)
    job_id = job_manager.submit(job)
    job_manager.wait_for_all_jobs(5000)
    assert len(progress_updates) > 0
    assert progress_updates[-1][1] == 1.0

def test_cancellation_token_works() -> None:
    token = CancellationToken()
    assert not token.is_cancelled()
    token.cancel()
    assert token.is_cancelled()

def test_job_handle_contains_all_fields() -> None:
    job = SleepJob(1.0)
    job_id = 123
    job.set_job_id(job_id)
    handle = JobHandle(
        job_id=job_id,
        job_uuid=job.get_job_uuid(),
        job_type=job.get_job_type(),
        module=job.get_module(),
        status=JobStatus.QUEUED,
        progress=0.0
    )
    assert handle.job_id == 123
    assert handle.job_type == "sleep"
    assert handle.module == "example"
    assert handle.status == JobStatus.QUEUED
    assert handle.progress == 0.0

def test_job_payload_serialization() -> None:
    job = SleepJob(3.0)
    payload = json.loads(job.get_payload())
    assert payload.get("sleep_seconds") == 3.0

def test_job_manager_cleanup_on_cancel(job_manager: JobManager) -> None:
    cancelled_jobs = []
    def on_cancelled(job_id: int) -> None:
        cancelled_jobs.append(job_id)
    job_manager.job_cancelled.connect(on_cancelled)
    job = CancellableSleepJob(3.0)
    job_id = job_manager.submit(job)
    time.sleep(0.3)
    job_manager.cancel_all()
    job_manager.wait_for_all_jobs(5000)
    assert job_id in cancelled_jobs
    handle = job_manager.get_job_status(job_id)
    assert handle is not None
    assert handle.status == JobStatus.CANCELLED