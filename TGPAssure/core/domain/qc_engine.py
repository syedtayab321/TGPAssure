from __future__ import annotations

import json
import uuid
import sqlite3
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Callable, Type, Union, TYPE_CHECKING
from enum import Enum

from core.data_access.db_engine import DatabaseEngine
if TYPE_CHECKING:
    from core.infrastructure.job_manager import JobManager
from core.infrastructure.job import Job, JobSpec, CancellationToken


class QCSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class QCStatus(Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    PENDING = "pending"
    RUNNING = "running"
    SKIPPED = "skipped"
    COMPLETED = "completed"


@dataclass
class QCFinding:
    rule_id: str
    severity: QCSeverity
    message: str
    location_ref: Optional[str] = None
    suggested_action: Optional[str] = None
    metadata_json: str = "{}"


@dataclass
class QCStageResult:
    stage_name: str
    status: QCStatus
    summary_json: str = "{}"
    findings: List[QCFinding] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None


class QCStage(ABC):
    @abstractmethod
    def run(self, context: Dict[str, Any]) -> QCStageResult:
        pass


@dataclass
class QCStageDefinition:
    stage_id: str
    stage_class: Type[QCStage]
    skippable_on_prior_failure: bool = False
    dependencies: List[str] = field(default_factory=list)


class QCPipeline:
    def __init__(self, name: str, stages: List[QCStageDefinition]) -> None:
        self.name = name
        self.stages = stages
        self._validate_dependencies()

    def _validate_dependencies(self) -> None:
        stage_ids = {s.stage_id for s in self.stages}
        for stage in self.stages:
            for dep in stage.dependencies:
                if dep not in stage_ids:
                    raise ValueError(f"Dependency '{dep}' not found in pipeline stages")

    def get_stage_order(self) -> List[str]:
        return [s.stage_id for s in self.stages]

    def get_stage(self, stage_id: str) -> Optional[QCStageDefinition]:
        for stage in self.stages:
            if stage.stage_id == stage_id:
                return stage
        return None


class QCPipelineRunner:
    def __init__(self, db_engine: DatabaseEngine, job_manager: JobManager) -> None:
        self.db_engine = db_engine
        self.job_manager = job_manager
        self._run_id: Optional[str] = None
        self._pipeline: Optional[QCPipeline] = None
        self._context: Dict[str, Any] = {}
        self.require_stage_approval = False
        self.stage_completed_callback: Optional[Callable[[str, QCStageResult], None]] = None
        self.stage_approval_requested_callback: Optional[Callable[[str], None]] = None
        self._approval_condition = threading.Condition()
        self._approved_stage: Optional[str] = None

    def run_pipeline(self, pipeline: QCPipeline, context: Dict[str, Any], assigned_to: Optional[str] = None) -> str:
        self._pipeline = pipeline
        self._context = context
        self._run_id = str(uuid.uuid4())
        
        run_id = self._create_qc_run(pipeline.name, assigned_to=assigned_to)
        
        job = QCPipelineJob(run_id, pipeline, context, self.db_engine, self)
        self.job_manager.submit(job)
        
        return run_id

    def _create_qc_run(self, pipeline_name: str, assigned_to: Optional[str] = None) -> str:
        conn = self.db_engine.get_write_connection()
        try:
            history_json = json.dumps([])
            if assigned_to:
                history_json = json.dumps([
                    {
                        "assigned_to": assigned_to,
                        "previous": None,
                        "changed_at": datetime.now(timezone.utc).isoformat()
                    }
                ])

            cursor = conn.execute(
                "INSERT INTO qc_runs (run_uuid, module, qc_profile, status, assigned_to, assignment_history_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
                (self._run_id, "qc_engine", pipeline_name, "running", assigned_to, history_json)
            )
            conn.commit()
            return self._run_id
        finally:
            conn.close()

    def execute_stage(self, stage_id: str, stage: QCStage, order: int) -> QCStageResult:
        stage_result = self._create_stage_result(stage_id, order)
        
        try:
            start_time = datetime.now(timezone.utc)
            self._update_stage_started(stage_id, start_time)
            
            result = stage.run(self._context)
            
            end_time = datetime.now(timezone.utc)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            
            self._update_stage_completed(stage_id, result, duration_ms)
            self._save_findings(stage_id, result.findings)
            if self.stage_completed_callback:
                self.stage_completed_callback(stage_id, result)
            
            return result
        except Exception as e:
            end_time = datetime.now(timezone.utc)
            start_time = self._get_stage_start_time(stage_id) or datetime.now(timezone.utc)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            
            error_result = QCStageResult(
                stage_name=stage_id,
                status=QCStatus.FAIL,
                summary_json=json.dumps({"error": str(e)}),
                findings=[
                    QCFinding(
                        rule_id="stage_execution_error",
                        severity=QCSeverity.CRITICAL,
                        message=f"Stage execution failed: {str(e)}",
                        suggested_action="Check the stage implementation and input data"
                    )
                ]
            )
            self._update_stage_failed(stage_id, error_result, duration_ms)
            raise

    def wait_for_stage_approval(self, stage_id: str) -> None:
        if not self.require_stage_approval:
            return
        with self._approval_condition:
            self._approved_stage = None
            if self.stage_approval_requested_callback:
                self.stage_approval_requested_callback(stage_id)
            while self._approved_stage != stage_id:
                self._approval_condition.wait()

    def approve_stage(self, stage_id: str) -> None:
        with self._approval_condition:
            self._approved_stage = stage_id
            self._approval_condition.notify_all()

    def _create_stage_result(self, stage_id: str, order: int) -> None:
        conn = self.db_engine.get_write_connection()
        try:
            conn.execute(
                "INSERT INTO qc_stage_results (qc_run_id, stage_key, stage_name, stage_order, status) "
                "SELECT id, ?, ?, ?, ? FROM qc_runs WHERE run_uuid = ?",
                (stage_id, stage_id, order, QCStatus.PENDING.value, self._run_id)
            )
            conn.commit()
        finally:
            conn.close()

    def _update_stage_started(self, stage_id: str, start_time: datetime) -> None:
        conn = self.db_engine.get_write_connection()
        try:
            conn.execute(
                "UPDATE qc_stage_results SET status = ?, started_at = ? "
                "WHERE qc_run_id = (SELECT id FROM qc_runs WHERE run_uuid = ?) AND stage_key = ?",
                (QCStatus.RUNNING.value, start_time.isoformat(), self._run_id, stage_id)
            )
            conn.commit()
        finally:
            conn.close()

    def _update_stage_completed(self, stage_id: str, result: QCStageResult, duration_ms: int) -> None:
        conn = self.db_engine.get_write_connection()
        try:
            conn.execute(
                "UPDATE qc_stage_results SET status = ?, result = ?, score = ?, "
                "metrics_json = ?, completed_at = ?, duration_ms = ? "
                "WHERE qc_run_id = (SELECT id FROM qc_runs WHERE run_uuid = ?) AND stage_key = ?",
                (
                    result.status.value,
                    result.status.value,
                    self._calculate_score(result),
                    result.summary_json,
                    datetime.now(timezone.utc).isoformat(),
                    duration_ms,
                    self._run_id,
                    stage_id
                )
            )
            conn.commit()
            
            self._update_run_status()
        finally:
            conn.close()

    def _update_stage_failed(self, stage_id: str, result: QCStageResult, duration_ms: int) -> None:
        conn = self.db_engine.get_write_connection()
        try:
            conn.execute(
                "UPDATE qc_stage_results SET status = ?, result = ?, "
                "metrics_json = ?, completed_at = ?, duration_ms = ?, message = ? "
                "WHERE qc_run_id = (SELECT id FROM qc_runs WHERE run_uuid = ?) AND stage_key = ?",
                (
                    QCStatus.FAIL.value,
                    QCStatus.FAIL.value,
                    result.summary_json,
                    datetime.now(timezone.utc).isoformat(),
                    duration_ms,
                    result.findings[0].message if result.findings else "Unknown error",
                    self._run_id,
                    stage_id
                )
            )
            conn.commit()
            
            self._update_run_status()
        finally:
            conn.close()

    def _get_stage_start_time(self, stage_id: str) -> Optional[datetime]:
        conn = self.db_engine.get_read_connection()
        try:
            row = conn.execute(
                "SELECT started_at FROM qc_stage_results "
                "WHERE qc_run_id = (SELECT id FROM qc_runs WHERE run_uuid = ?) AND stage_key = ?",
                (self._run_id, stage_id)
            ).fetchone()
            if row and row["started_at"]:
                return datetime.fromisoformat(row["started_at"])
            return None
        finally:
            conn.close()

    def _save_findings(self, stage_id: str, findings: List[QCFinding]) -> None:
        if not findings:
            return
        
        conn = self.db_engine.get_write_connection()
        try:
            for finding in findings:
                conn.execute(
                    "INSERT INTO qc_findings (qc_run_id, stage_result_id, finding_code, severity, "
                    "category, title, description, context_json, created_at) "
                    "SELECT (SELECT id FROM qc_runs WHERE run_uuid = ?), "
                    "(SELECT id FROM qc_stage_results WHERE qc_run_id = (SELECT id FROM qc_runs WHERE run_uuid = ?) "
                    "AND stage_key = ?), ?, ?, ?, ?, ?, ?, datetime('now')",
                    (
                        self._run_id,
                        self._run_id,
                        stage_id,
                        finding.rule_id,
                        finding.severity.value,
                        "qc",
                        finding.message,
                        finding.message,
                        finding.metadata_json
                    )
                )
            conn.commit()
        finally:
            conn.close()

    def _calculate_score(self, result: QCStageResult) -> Optional[float]:
        if result.status == QCStatus.PASS:
            return 1.0
        elif result.status == QCStatus.WARN:
            return 0.7
        elif result.status == QCStatus.FAIL:
            return 0.0
        return None

    def _update_run_status(self) -> None:
        conn = self.db_engine.get_read_connection()
        try:
            rows = conn.execute(
                "SELECT status FROM qc_stage_results "
                "WHERE qc_run_id = (SELECT id FROM qc_runs WHERE run_uuid = ?)",
                (self._run_id,)
            ).fetchall()
            
            if not rows:
                return
            
            statuses = [row["status"] for row in rows]
            
            if QCStatus.FAIL.value in statuses:
                overall = QCStatus.FAIL
            elif QCStatus.WARN.value in statuses:
                overall = QCStatus.WARN
            else:
                overall = QCStatus.PASS
            
            conn = self.db_engine.get_write_connection()
            try:
                conn.execute(
                    "UPDATE qc_runs SET status = ?, overall_result = ? "
                    "WHERE run_uuid = ?",
                    (QCStatus.COMPLETED.value, overall.value, self._run_id)
                )
                conn.commit()
            finally:
                conn.close()
        finally:
            conn.close()

    def get_run_status(self, run_uuid: str) -> Optional[Dict[str, Any]]:
        conn = self.db_engine.get_read_connection()
        try:
            row = conn.execute(
                "SELECT status, overall_result, assigned_to FROM qc_runs WHERE run_uuid = ?",
                (run_uuid,)
            ).fetchone()
            if row is None:
                return None
            return {
                "status": row["status"],
                "overall_result": row["overall_result"],
                "assigned_to": row["assigned_to"]
            }
        finally:
            conn.close()

    def get_stage_results(self, run_uuid: str) -> List[Dict[str, Any]]:
        conn = self.db_engine.get_read_connection()
        try:
            rows = conn.execute(
                "SELECT stage_key, stage_name, status, result, score, metrics_json, "
                "message, started_at, completed_at, duration_ms "
                "FROM qc_stage_results "
                "WHERE qc_run_id = (SELECT id FROM qc_runs WHERE run_uuid = ?) "
                "ORDER BY stage_order",
                (run_uuid,)
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_findings(self, run_uuid: str) -> List[Dict[str, Any]]:
        conn = self.db_engine.get_read_connection()
        try:
            rows = conn.execute(
                "SELECT finding_code, severity, category, title, description, "
                "context_json, is_resolved, created_at "
                "FROM qc_findings "
                "WHERE qc_run_id = (SELECT id FROM qc_runs WHERE run_uuid = ?)",
                (run_uuid,)
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def wait_for_completion(self, timeout_ms: int = 5000) -> bool:
        return self.job_manager.wait_for_all_jobs(timeout_ms)

    def assign_run(self, run_uuid: str, assignee: str) -> None:
        conn = self.db_engine.get_write_connection()
        try:
            row = conn.execute(
                "SELECT assigned_to, assignment_history_json FROM qc_runs WHERE run_uuid = ?",
                (run_uuid,)
            ).fetchone()
            if row is None:
                raise ValueError(f"QC run '{run_uuid}' not found")
            try:
                history = json.loads(row["assignment_history_json"] or "[]")
            except Exception:
                history = []

            history.append({
                "assigned_to": assignee,
                "prior": row["assigned_to"],
                "previous": row["assigned_to"],
                "changed_at": datetime.now(timezone.utc).isoformat()
            })

            conn.execute(
                "UPDATE qc_runs SET assigned_to = ?, assignment_history_json = ? WHERE run_uuid = ?",
                (assignee, json.dumps(history), run_uuid)
            )
            conn.commit()
        finally:
            conn.close()

    def get_assignment_info(self, run_uuid: str) -> Dict[str, Any]:
        conn = self.db_engine.get_read_connection()
        try:
            row = conn.execute(
                "SELECT assigned_to, assignment_history_json FROM qc_runs WHERE run_uuid = ?",
                (run_uuid,)
            ).fetchone()
            if row is None:
                raise ValueError(f"QC run '{run_uuid}' not found")
            try:
                history = json.loads(row["assignment_history_json"] or "[]")
            except Exception:
                history = []
            return {
                "assigned_to": row["assigned_to"],
                "history": history
            }
        finally:
            conn.close()


class QCPipelineJob(Job):
    def __init__(
        self,
        run_uuid: str,
        pipeline: QCPipeline,
        context: Dict[str, Any],
        db_engine: DatabaseEngine,
        runner: QCPipelineRunner
    ) -> None:
        spec = JobSpec(
            job_type="qc_pipeline",
            module="qc_engine",
            priority=10,
            payload_json=json.dumps({"pipeline": pipeline.name, "run_uuid": run_uuid})
        )
        super().__init__(spec)
        self.run_uuid = run_uuid
        self.pipeline = pipeline
        self.context = context
        self.db_engine = db_engine
        self.runner = runner
        self._stage_results: Dict[str, QCStageResult] = {}

    def run(self, context: Any, cancel_token: CancellationToken) -> Dict[str, Any]:
        stage_count = len(self.pipeline.stages)
        completed_stages = 0
        pipeline_failed = False
        
        for order, stage_def in enumerate(self.pipeline.stages):
            if cancel_token.is_cancelled():
                break

            # A crashing stage invalidates the assumptions of subsequent stages.
            # Explicitly skippable stages are still recorded for auditability; the
            # first non-skippable stage after the failure terminates the pipeline.
            if pipeline_failed:
                if stage_def.skippable_on_prior_failure:
                    self._mark_stage_skipped(stage_def.stage_id, order)
                    completed_stages += 1
                    continue
                break
            
            if self._should_skip_stage(stage_def, completed_stages):
                self._mark_stage_skipped(stage_def.stage_id, order)
                completed_stages += 1
                continue
            
            stage_instance = stage_def.stage_class()
            
            try:
                result = self.runner.execute_stage(
                    stage_def.stage_id,
                    stage_instance,
                    order
                )
                self._stage_results[stage_def.stage_id] = result
                completed_stages += 1
                
                progress = completed_stages / stage_count
                self.update_progress(progress)
                if context is not None and hasattr(context, 'update_progress'):
                    context.update_progress(self.get_job_id(), progress)
                if completed_stages < stage_count:
                    self.runner.wait_for_stage_approval(stage_def.stage_id)
                
            except Exception as e:
                # execute_stage already persisted the failure row. Do not insert a
                # second qc_stage_results row for the same stage.
                failed_result = QCStageResult(
                    stage_name=stage_def.stage_id,
                    status=QCStatus.FAIL,
                    summary_json=json.dumps({"error": str(e)})
                )
                self._stage_results[stage_def.stage_id] = failed_result
                pipeline_failed = True
                completed_stages += 1
                progress = completed_stages / stage_count
                self.update_progress(progress)
                if context is not None and hasattr(context, 'update_progress'):
                    context.update_progress(self.get_job_id(), progress)
                continue
        
        return {
            "run_uuid": self.run_uuid,
            "pipeline": self.pipeline.name,
            "completed_stages": completed_stages,
            "total_stages": stage_count,
            "stage_results": {
                k: {"status": v.status.value, "summary": v.summary_json}
                for k, v in self._stage_results.items()
            }
        }

    def _should_skip_stage(self, stage_def: QCStageDefinition, completed_stages: int) -> bool:
        if not stage_def.skippable_on_prior_failure:
            return False

        # Skip if any prior stage failed or if any declared dependency has failed.
        for result in self._stage_results.values():
            if result.status == QCStatus.FAIL:
                return True

        for dep in stage_def.dependencies:
            if dep in self._stage_results:
                result = self._stage_results[dep]
                if result.status == QCStatus.FAIL:
                    return True

        return False

    def _mark_stage_skipped(self, stage_id: str, order: int) -> None:
        conn = self.db_engine.get_write_connection()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO qc_stage_results "
                "(qc_run_id, stage_key, stage_name, stage_order, status, result, completed_at) "
                "SELECT (SELECT id FROM qc_runs WHERE run_uuid = ?), ?, ?, ?, ?, ?, datetime('now')",
                (self.run_uuid, stage_id, stage_id, order, QCStatus.SKIPPED.value, QCStatus.SKIPPED.value)
            )
            conn.commit()
        finally:
            conn.close()

    def _mark_stage_failed(self, stage_id: str, order: int, message: str) -> None:
        conn = self.db_engine.get_write_connection()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO qc_stage_results "
                "(qc_run_id, stage_key, stage_name, stage_order, status, result, message, completed_at) "
                "SELECT (SELECT id FROM qc_runs WHERE run_uuid = ?), ?, ?, ?, ?, ?, ?, datetime('now')",
                (
                    self.run_uuid,
                    stage_id,
                    stage_id,
                    order,
                    QCStatus.FAIL.value,
                    QCStatus.FAIL.value,
                    message
                )
            )
            conn.commit()
        finally:
            conn.close()


class QCRuleRegistry:
    def __init__(self, rule_set_version: str = "1.0.0") -> None:
        self.rule_set_version = rule_set_version
        self._rules: Dict[str, Dict[str, Any]] = {}

    def register_rule(
        self,
        rule_id: str,
        name: str,
        description: str,
        default_threshold: Optional[float] = None,
        severity: QCSeverity = QCSeverity.WARNING,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        self._rules[rule_id] = {
            "rule_id": rule_id,
            "name": name,
            "description": description,
            "default_threshold": default_threshold,
            "severity": severity.value,
            "metadata": metadata or {}
        }

    def get_rule(self, rule_id: str) -> Optional[Dict[str, Any]]:
        return self._rules.get(rule_id)

    def get_all_rules(self) -> List[Dict[str, Any]]:
        return list(self._rules.values())

    def update_threshold(self, rule_id: str, threshold: float) -> None:
        if rule_id not in self._rules:
            raise KeyError(f"Rule '{rule_id}' not found")
        self._rules[rule_id]["default_threshold"] = threshold

    def to_json(self) -> str:
        return json.dumps({
            "rule_set_version": self.rule_set_version,
            "rules": self._rules
        })

    @classmethod
    def from_json(cls, json_str: str) -> QCRuleRegistry:
        data = json.loads(json_str)
        registry = cls(data.get("rule_set_version", "1.0.0"))
        for rule_id, rule_data in data.get("rules", {}).items():
            severity = QCSeverity(rule_data.get("severity", "warning"))
            registry.register_rule(
                rule_id=rule_id,
                name=rule_data.get("name", rule_id),
                description=rule_data.get("description", ""),
                default_threshold=rule_data.get("default_threshold"),
                severity=severity,
                metadata=rule_data.get("metadata", {})
            )
        return registry
