from __future__ import annotations

import pytest
import tempfile
import shutil
import json
import time
from pathlib import Path
from typing import Any, Dict

from PySide6.QtCore import QCoreApplication

from core.data_access.db_engine import DatabaseEngine
from core.infrastructure.service_container import ServiceContainer
from core.infrastructure.job_manager import JobManager
from core.domain.qc_engine import (
    QCStage, QCStageResult, QCStatus, QCSeverity, QCFinding,
    QCPipeline, QCStageDefinition, QCPipelineRunner,
    QCRuleRegistry, QCPipelineJob
)

class PassingStage(QCStage):
    def run(self, context: Dict[str, Any]) -> QCStageResult:
        return QCStageResult(
            stage_name="passing",
            status=QCStatus.PASS,
            summary_json=json.dumps({"test": "passed"})
        )

class WarningStage(QCStage):
    def run(self, context: Dict[str, Any]) -> QCStageResult:
        return QCStageResult(
            stage_name="warning",
            status=QCStatus.WARN,
            summary_json=json.dumps({"test": "warning"}),
            findings=[
                QCFinding(
                    rule_id="test_warning",
                    severity=QCSeverity.WARNING,
                    message="This is a warning",
                    suggested_action="Check the data"
                )
            ]
        )

class FailingStage(QCStage):
    def run(self, context: Dict[str, Any]) -> QCStageResult:
        raise RuntimeError("This stage fails deliberately")

class ErrorStage(QCStage):
    def run(self, context: Dict[str, Any]) -> QCStageResult:
        return QCStageResult(
            stage_name="error",
            status=QCStatus.FAIL,
            summary_json=json.dumps({"error": "validation failed"}),
            findings=[
                QCFinding(
                    rule_id="test_error",
                    severity=QCSeverity.ERROR,
                    message="Validation failed",
                    suggested_action="Fix the input data"
                )
            ]
        )

@pytest.fixture
def app() -> QCoreApplication:
    return QCoreApplication.instance() or QCoreApplication([])

@pytest.fixture
def temp_dir() -> Path:
    path = Path(tempfile.mkdtemp())
    yield path
    shutil.rmtree(path, ignore_errors=True)

@pytest.fixture
def db_engine(temp_dir: Path) -> DatabaseEngine:
    db_path = temp_dir / "test.db"
    engine = DatabaseEngine(db_path)
    
    conn = engine.get_write_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS project (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                project_uuid TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            INSERT OR IGNORE INTO project (id, project_uuid, name)
            VALUES (1, 'test-uuid', 'Test Project')
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS qc_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL DEFAULT 1,
                file_id INTEGER,
                job_id INTEGER,
                run_uuid TEXT NOT NULL UNIQUE,
                module TEXT NOT NULL,
                qc_profile TEXT NOT NULL,
                profile_version TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                overall_result TEXT NOT NULL DEFAULT 'pending',
                score REAL,
                assigned_to TEXT,
                assignment_history_json TEXT NOT NULL DEFAULT '[]',
                parameters_json TEXT NOT NULL DEFAULT '{}',
                summary_json TEXT NOT NULL DEFAULT '{}',
                started_at TEXT,
                completed_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS qc_stage_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                qc_run_id INTEGER NOT NULL,
                stage_key TEXT NOT NULL,
                stage_name TEXT NOT NULL,
                stage_order INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                result TEXT NOT NULL DEFAULT 'pending',
                score REAL,
                metrics_json TEXT NOT NULL DEFAULT '{}',
                message TEXT,
                started_at TEXT,
                completed_at TEXT,
                duration_ms INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS qc_findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                qc_run_id INTEGER NOT NULL,
                stage_result_id INTEGER,
                file_id INTEGER,
                finding_code TEXT NOT NULL,
                severity TEXT NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                metric_name TEXT,
                observed_value REAL,
                expected_min REAL,
                expected_max REAL,
                unit TEXT,
                station_id TEXT,
                line_id TEXT,
                sample_index INTEGER,
                timestamp_utc TEXT,
                location_x REAL,
                location_y REAL,
                location_z REAL,
                crs TEXT,
                context_json TEXT NOT NULL DEFAULT '{}',
                is_resolved INTEGER NOT NULL DEFAULT 0,
                resolution_note TEXT,
                resolved_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
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
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    finally:
        conn.close()
    
    return engine

@pytest.fixture
def container(app: QCoreApplication, db_engine: DatabaseEngine) -> ServiceContainer:
    container = ServiceContainer()
    container.register(DatabaseEngine, db_engine)
    job_manager = JobManager(db_engine)
    container.register(JobManager, job_manager)
    return container

@pytest.fixture
def job_manager(container: ServiceContainer) -> JobManager:
    return container.resolve(JobManager)

@pytest.fixture
def qc_runner(db_engine: DatabaseEngine, job_manager: JobManager) -> QCPipelineRunner:
    return QCPipelineRunner(db_engine, job_manager)

def test_qc_pipeline_passing_stages(qc_runner: QCPipelineRunner) -> None:
    pipeline = QCPipeline(
        name="test_pipeline",
        stages=[
            QCStageDefinition("passing", PassingStage),
            QCStageDefinition("warning", WarningStage)
        ]
    )
    
    run_id = qc_runner.run_pipeline(pipeline, {})
    qc_runner.wait_for_completion(5000)
    
    status = qc_runner.get_run_status(run_id)
    assert status is not None
    assert status["overall_result"] == "warn"

def test_qc_pipeline_failing_stage(qc_runner: QCPipelineRunner) -> None:
    pipeline = QCPipeline(
        name="test_pipeline",
        stages=[
            QCStageDefinition("passing", PassingStage),
            QCStageDefinition("failing", FailingStage)
        ]
    )
    
    run_id = qc_runner.run_pipeline(pipeline, {})
    qc_runner.wait_for_completion(5000)
    
    status = qc_runner.get_run_status(run_id)
    assert status is not None
    assert status["overall_result"] == "fail"
    
    stage_results = qc_runner.get_stage_results(run_id)
    assert len(stage_results) >= 1
    assert stage_results[1]["status"] == "fail"

def test_qc_pipeline_skips_stage_on_prior_failure(qc_runner: QCPipelineRunner) -> None:
    pipeline = QCPipeline(
        name="test_pipeline",
        stages=[
            QCStageDefinition("failing", FailingStage, skippable_on_prior_failure=False),
            QCStageDefinition("skippable", PassingStage, skippable_on_prior_failure=True)
        ]
    )
    
    run_id = qc_runner.run_pipeline(pipeline, {})
    qc_runner.wait_for_completion(5000)
    
    stage_results = qc_runner.get_stage_results(run_id)
    assert len(stage_results) == 2
    assert stage_results[0]["status"] == "fail"
    assert stage_results[1]["status"] == "skipped"


def test_qc_run_assignment_and_reassign(qc_runner: QCPipelineRunner) -> None:
    pipeline = QCPipeline(
        name="test_pipeline",
        stages=[
            QCStageDefinition("passing", PassingStage)
        ]
    )

    run_id = qc_runner.run_pipeline(pipeline, {}, assigned_to="alice")
    qc_runner.wait_for_completion(5000)

    assignment = qc_runner.get_assignment_info(run_id)
    assert assignment is not None
    assert assignment["assigned_to"] == "alice"
    assert isinstance(assignment["history"], list)
    assert assignment["history"][0]["assigned_to"] == "alice"

    qc_runner.assign_run(run_id, "bob")
    reassigned = qc_runner.get_assignment_info(run_id)
    assert reassigned is not None
    assert reassigned["assigned_to"] == "bob"
    assert len(reassigned["history"]) == 2
    assert reassigned["history"][1]["prior"] == "alice"


def test_qc_pipeline_does_not_skip_when_prior_passes(qc_runner: QCPipelineRunner) -> None:
    pipeline = QCPipeline(
        name="test_pipeline",
        stages=[
            QCStageDefinition("passing", PassingStage, skippable_on_prior_failure=False),
            QCStageDefinition("skippable", PassingStage, skippable_on_prior_failure=True)
        ]
    )
    
    run_id = qc_runner.run_pipeline(pipeline, {})
    qc_runner.wait_for_completion(5000)
    
    stage_results = qc_runner.get_stage_results(run_id)
    assert len(stage_results) == 2
    assert stage_results[0]["status"] == "pass"
    assert stage_results[1]["status"] == "pass"

def test_qc_pipeline_crash_resilience(qc_runner: QCPipelineRunner) -> None:
    pipeline = QCPipeline(
        name="test_pipeline",
        stages=[
            QCStageDefinition("passing", PassingStage),
            QCStageDefinition("failing", FailingStage),
            QCStageDefinition("after_fail", PassingStage)
        ]
    )
    
    run_id = qc_runner.run_pipeline(pipeline, {})
    qc_runner.wait_for_completion(5000)
    
    stage_results = qc_runner.get_stage_results(run_id)
    assert len(stage_results) == 2
    assert stage_results[0]["status"] == "pass"
    assert stage_results[1]["status"] == "fail"

def test_qc_rule_registry() -> None:
    registry = QCRuleRegistry("1.0.0")
    
    registry.register_rule(
        rule_id="test_rule",
        name="Test Rule",
        description="This is a test rule",
        default_threshold=0.5,
        severity=QCSeverity.WARNING
    )
    
    rule = registry.get_rule("test_rule")
    assert rule is not None
    assert rule["name"] == "Test Rule"
    assert rule["default_threshold"] == 0.5
    
    registry.update_threshold("test_rule", 0.8)
    rule = registry.get_rule("test_rule")
    assert rule["default_threshold"] == 0.8

def test_qc_rule_registry_to_json() -> None:
    registry = QCRuleRegistry("1.0.0")
    registry.register_rule("rule1", "Rule One", "Description one")
    registry.register_rule("rule2", "Rule Two", "Description two", 0.7)
    
    json_str = registry.to_json()
    data = json.loads(json_str)
    assert data["rule_set_version"] == "1.0.0"
    assert "rule1" in data["rules"]
    assert "rule2" in data["rules"]

def test_qc_rule_registry_from_json() -> None:
    json_str = json.dumps({
        "rule_set_version": "2.0.0",
        "rules": {
            "rule1": {
                "rule_id": "rule1",
                "name": "Rule One",
                "description": "Description one",
                "default_threshold": 0.5,
                "severity": "warning",
                "metadata": {}
            }
        }
    })
    
    registry = QCRuleRegistry.from_json(json_str)
    assert registry.rule_set_version == "2.0.0"
    rule = registry.get_rule("rule1")
    assert rule is not None
    assert rule["name"] == "Rule One"

def test_qc_stage_result_findings(qc_runner: QCPipelineRunner) -> None:
    pipeline = QCPipeline(
        name="test_pipeline",
        stages=[
            QCStageDefinition("error", ErrorStage)
        ]
    )
    
    run_id = qc_runner.run_pipeline(pipeline, {})
    time.sleep(1)
    
    findings = qc_runner.get_findings(run_id)
    assert len(findings) > 0
    assert findings[0]["severity"] == "error"
    assert "Validation failed" in findings[0]["description"]

def test_qc_pipeline_with_dependencies(qc_runner: QCPipelineRunner) -> None:
    pipeline = QCPipeline(
        name="test_pipeline",
        stages=[
            QCStageDefinition("stage1", PassingStage),
            QCStageDefinition("stage2", PassingStage, dependencies=["stage1"]),
            QCStageDefinition("stage3", PassingStage, dependencies=["stage2"])
        ]
    )
    
    run_id = qc_runner.run_pipeline(pipeline, {})
    time.sleep(1)
    
    stage_results = qc_runner.get_stage_results(run_id)
    assert len(stage_results) == 3
    assert all(r["status"] == "pass" for r in stage_results)