from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from core.data_access.db_engine import DatabaseEngine
from modules.seismic.segy_qc.qc_models import SegyFinding, SegyRunSummary, SegyStageOutcome


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _loads(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


class SegyQcRepository:
    def __init__(self, db_engine: DatabaseEngine) -> None:
        self.db = db_engine
        self.ensure_schema()

    def ensure_schema(self) -> None:
        conn = self.db.get_write_connection()
        try:
            self._ensure_column(conn, "qc_findings", "trace_index", "INTEGER")
            self._ensure_column(conn, "qc_findings", "suggested_action", "TEXT")
            self._ensure_column(conn, "qc_findings", "updated_at", "TEXT")
            self._ensure_column(conn, "qc_runs", "source_file_path", "TEXT")
            self._ensure_column(conn, "qc_runs", "source_file_name", "TEXT")
            self._ensure_column(conn, "qc_runs", "duration_ms", "INTEGER")
            self._ensure_column(conn, "qc_runs", "assigned_to", "TEXT")
            self._ensure_column(conn, "qc_runs", "assignment_history_json", "TEXT NOT NULL DEFAULT '[]'")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_qc_runs_created ON qc_runs(created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_qc_runs_file ON qc_runs(file_id, created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_qc_findings_run ON qc_findings(qc_run_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_qc_findings_resolved ON qc_findings(is_resolved)")
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _ensure_column(conn: Any, table: str, column: str, definition: str) -> None:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def ensure_file(self, file_path: str | Path, metadata: Dict[str, Any]) -> int:
        path = Path(file_path).expanduser().resolve()
        conn = self.db.get_write_connection()
        try:
            row = conn.execute(
                "SELECT id FROM project_files WHERE absolute_path = ? OR relative_path = ? LIMIT 1",
                (str(path), str(path)),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE project_files SET size_bytes = ?, status = 'available', metadata_json = ?, "
                    "last_verified_at = ? WHERE id = ?",
                    (path.stat().st_size, _json(metadata), _utc_now(), row["id"]),
                )
                conn.commit()
                return int(row["id"])

            file_uuid = str(uuid.uuid4())
            cursor = conn.execute(
                "INSERT INTO project_files (project_id, file_uuid, module, file_role, original_name, "
                "display_name, absolute_path, relative_path, extension, mime_type, size_bytes, status, "
                "metadata_json, imported_at, last_verified_at) "
                "VALUES (1, ?, 'seismic', 'input', ?, ?, ?, ?, ?, 'application/x-segy', ?, 'available', ?, ?, ?)",
                (
                    file_uuid,
                    path.name,
                    path.name,
                    str(path),
                    str(path),
                    path.suffix.lower(),
                    path.stat().st_size,
                    _json(metadata),
                    _utc_now(),
                    _utc_now(),
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()

    def create_run(
        self,
        file_id: int,
        file_path: str | Path,
        profile_key: str,
        profile_version: str,
        parameters: Dict[str, Any],
        assigned_to: Optional[str] = None,
    ) -> str:
        run_uuid = str(uuid.uuid4())
        path = Path(file_path).expanduser().resolve()
        now = _utc_now()
        assignment_history: List[Dict[str, Any]] = []
        if assigned_to:
            assignment_history.append({"assigned_to": assigned_to, "previous": None, "changed_at": now})
        conn = self.db.get_write_connection()
        try:
            conn.execute(
                "INSERT INTO qc_runs (project_id, file_id, run_uuid, module, qc_profile, profile_version, "
                "status, overall_result, assigned_to, assignment_history_json, parameters_json, summary_json, "
                "source_file_path, source_file_name, started_at, created_at) "
                "VALUES (1, ?, ?, 'segy', ?, ?, 'running', 'pending', ?, ?, ?, '{}', ?, ?, ?, ?)",
                (
                    file_id,
                    run_uuid,
                    profile_key,
                    profile_version,
                    assigned_to,
                    _json(assignment_history),
                    _json(parameters),
                    str(path),
                    path.name,
                    now,
                    now,
                ),
            )
            conn.commit()
            return run_uuid
        finally:
            conn.close()

    def attach_job(self, run_uuid: str, job_id: int) -> None:
        conn = self.db.get_write_connection()
        try:
            conn.execute("UPDATE qc_runs SET job_id = ? WHERE run_uuid = ?", (job_id, run_uuid))
            conn.commit()
        finally:
            conn.close()

    def start_stage(self, run_uuid: str, stage_key: str, stage_name: str, order: int) -> int:
        conn = self.db.get_write_connection()
        try:
            run = conn.execute("SELECT id FROM qc_runs WHERE run_uuid = ?", (run_uuid,)).fetchone()
            if not run:
                raise ValueError(f"QC run not found: {run_uuid}")
            conn.execute(
                "INSERT INTO qc_stage_results (qc_run_id, stage_key, stage_name, stage_order, status, result, "
                "metrics_json, started_at) VALUES (?, ?, ?, ?, 'running', 'pending', '{}', ?) "
                "ON CONFLICT(qc_run_id, stage_key) DO UPDATE SET stage_name = excluded.stage_name, "
                "stage_order = excluded.stage_order, status = 'running', result = 'pending', "
                "metrics_json = '{}', message = NULL, started_at = excluded.started_at, completed_at = NULL, duration_ms = NULL",
                (run["id"], stage_key, stage_name, order, _utc_now()),
            )
            conn.commit()
            row = conn.execute(
                "SELECT id FROM qc_stage_results WHERE qc_run_id = ? AND stage_key = ?",
                (run["id"], stage_key),
            ).fetchone()
            return int(row["id"])
        finally:
            conn.close()

    def complete_stage(self, run_uuid: str, outcome: SegyStageOutcome) -> int:
        conn = self.db.get_write_connection()
        try:
            run = conn.execute("SELECT id, file_id FROM qc_runs WHERE run_uuid = ?", (run_uuid,)).fetchone()
            if not run:
                raise ValueError(f"QC run not found: {run_uuid}")
            row = conn.execute(
                "SELECT id FROM qc_stage_results WHERE qc_run_id = ? AND stage_key = ?",
                (run["id"], outcome.key),
            ).fetchone()
            if not row:
                raise ValueError(f"QC stage was not started: {outcome.key}")
            stage_id = int(row["id"])
            conn.execute(
                "UPDATE qc_stage_results SET status = 'completed', result = ?, score = ?, metrics_json = ?, "
                "message = ?, completed_at = ?, duration_ms = ? WHERE id = ?",
                (
                    outcome.status,
                    outcome.score,
                    _json(outcome.metrics),
                    outcome.message,
                    _utc_now(),
                    outcome.duration_ms,
                    stage_id,
                ),
            )
            for finding in outcome.findings:
                self._insert_finding(conn, int(run["id"]), stage_id, run["file_id"], finding)
            conn.commit()
            return stage_id
        finally:
            conn.close()

    @staticmethod
    def _insert_finding(conn: Any, run_id: int, stage_id: int, file_id: Any, finding: SegyFinding) -> None:
        context = dict(finding.context)
        if finding.suggested_action:
            context.setdefault("suggested_action", finding.suggested_action)
        conn.execute(
            "INSERT INTO qc_findings (qc_run_id, stage_result_id, file_id, finding_code, severity, category, "
            "title, description, metric_name, observed_value, expected_min, expected_max, unit, station_id, "
            "line_id, trace_index, sample_index, location_x, location_y, context_json, suggested_action, "
            "is_resolved, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, 0, ?, ?)",
            (
                run_id,
                stage_id,
                file_id,
                finding.code,
                finding.severity,
                finding.category,
                finding.title,
                finding.description,
                finding.metric_name,
                finding.observed_value,
                finding.expected_min,
                finding.expected_max,
                finding.unit,
                finding.station_id,
                finding.line_id,
                finding.trace_index,
                finding.location_x,
                finding.location_y,
                _json(context),
                finding.suggested_action,
                _utc_now(),
                _utc_now(),
            ),
        )

    def complete_run(self, summary: SegyRunSummary) -> None:
        conn = self.db.get_write_connection()
        try:
            conn.execute(
                "UPDATE qc_runs SET status = ?, overall_result = ?, score = ?, summary_json = ?, "
                "completed_at = ?, duration_ms = ? WHERE run_uuid = ?",
                (
                    summary.status,
                    summary.overall_result,
                    summary.score,
                    _json(summary.to_dict()),
                    summary.completed_at,
                    summary.duration_ms,
                    summary.run_uuid,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def fail_run(self, run_uuid: str, error: str) -> None:
        conn = self.db.get_write_connection()
        try:
            row = conn.execute("SELECT started_at FROM qc_runs WHERE run_uuid = ?", (run_uuid,)).fetchone()
            duration_ms = 0
            if row and row["started_at"]:
                try:
                    started = datetime.fromisoformat(row["started_at"])
                    duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
                except ValueError:
                    pass
            conn.execute(
                "UPDATE qc_runs SET status = 'failed', overall_result = 'fail', summary_json = ?, "
                "completed_at = ?, duration_ms = ? WHERE run_uuid = ?",
                (_json({"error": error}), _utc_now(), duration_ms, run_uuid),
            )
            conn.commit()
        finally:
            conn.close()

    def cancel_run(self, run_uuid: str) -> None:
        conn = self.db.get_write_connection()
        try:
            row = conn.execute("SELECT started_at FROM qc_runs WHERE run_uuid = ?", (run_uuid,)).fetchone()
            duration_ms = 0
            if row and row["started_at"]:
                try:
                    started = datetime.fromisoformat(row["started_at"])
                    duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
                except ValueError:
                    pass
            conn.execute(
                "UPDATE qc_runs SET status = 'cancelled', overall_result = 'cancelled', completed_at = ?, "
                "duration_ms = ? WHERE run_uuid = ?",
                (_utc_now(), duration_ms, run_uuid),
            )
            conn.commit()
        finally:
            conn.close()

    def get_run(self, run_uuid: str) -> Optional[Dict[str, Any]]:
        conn = self.db.get_read_connection()
        try:
            row = conn.execute(
                "SELECT r.*, f.display_name AS file_display_name, f.absolute_path AS file_absolute_path "
                "FROM qc_runs r LEFT JOIN project_files f ON f.id = r.file_id WHERE r.run_uuid = ?",
                (run_uuid,),
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            data["parameters"] = _loads(data.get("parameters_json"), {})
            data["summary"] = _loads(data.get("summary_json"), {})
            data["assignment_history"] = _loads(data.get("assignment_history_json"), [])
            return data
        finally:
            conn.close()

    def list_runs(self, limit: int = 200, file_path: Optional[str | Path] = None) -> List[Dict[str, Any]]:
        conn = self.db.get_read_connection()
        try:
            params: List[Any] = []
            where = "WHERE r.module = 'segy'"
            if file_path:
                where += " AND (r.source_file_path = ? OR f.absolute_path = ?)"
                resolved = str(Path(file_path).expanduser().resolve())
                params.extend([resolved, resolved])
            params.append(int(limit))
            rows = conn.execute(
                "SELECT r.run_uuid, r.source_file_name, r.source_file_path, r.qc_profile, r.profile_version, "
                "r.status, r.overall_result, r.score, r.assigned_to, r.started_at, r.completed_at, r.created_at, "
                "r.duration_ms, r.summary_json, f.display_name AS file_display_name "
                "FROM qc_runs r LEFT JOIN project_files f ON f.id = r.file_id "
                f"{where} ORDER BY r.created_at DESC LIMIT ?",
                tuple(params),
            ).fetchall()
            results: List[Dict[str, Any]] = []
            for row in rows:
                data = dict(row)
                data["summary"] = _loads(data.pop("summary_json", "{}"), {})
                results.append(data)
            return results
        finally:
            conn.close()

    def get_stages(self, run_uuid: str) -> List[Dict[str, Any]]:
        conn = self.db.get_read_connection()
        try:
            rows = conn.execute(
                "SELECT s.id, s.stage_key, s.stage_name, s.stage_order, s.status, s.result, s.score, "
                "s.metrics_json, s.message, s.started_at, s.completed_at, s.duration_ms, "
                "(SELECT COUNT(*) FROM qc_findings f WHERE f.stage_result_id = s.id) AS finding_count "
                "FROM qc_stage_results s JOIN qc_runs r ON r.id = s.qc_run_id "
                "WHERE r.run_uuid = ? ORDER BY s.stage_order",
                (run_uuid,),
            ).fetchall()
            results = []
            for row in rows:
                data = dict(row)
                data["metrics"] = _loads(data.pop("metrics_json", "{}"), {})
                results.append(data)
            return results
        finally:
            conn.close()

    def get_findings(
        self,
        run_uuid: str,
        severity: Optional[str] = None,
        resolved: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        conn = self.db.get_read_connection()
        try:
            where = ["r.run_uuid = ?"]
            params: List[Any] = [run_uuid]
            if severity and severity != "all":
                where.append("f.severity = ?")
                params.append(severity)
            if resolved is not None:
                where.append("f.is_resolved = ?")
                params.append(1 if resolved else 0)
            rows = conn.execute(
                "SELECT f.*, s.stage_key, s.stage_name FROM qc_findings f "
                "JOIN qc_runs r ON r.id = f.qc_run_id "
                "LEFT JOIN qc_stage_results s ON s.id = f.stage_result_id "
                f"WHERE {' AND '.join(where)} ORDER BY "
                "CASE f.severity WHEN 'critical' THEN 0 WHEN 'error' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END, f.id",
                tuple(params),
            ).fetchall()
            results = []
            for row in rows:
                data = dict(row)
                data["context"] = _loads(data.pop("context_json", "{}"), {})
                results.append(data)
            return results
        finally:
            conn.close()

    def set_finding_resolution(self, finding_id: int, resolved: bool, note: str = "") -> None:
        conn = self.db.get_write_connection()
        try:
            conn.execute(
                "UPDATE qc_findings SET is_resolved = ?, resolution_note = ?, resolved_at = ?, updated_at = ? WHERE id = ?",
                (
                    1 if resolved else 0,
                    note.strip() if resolved else None,
                    _utc_now() if resolved else None,
                    _utc_now(),
                    int(finding_id),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def assign_run(self, run_uuid: str, assignee: str) -> None:
        conn = self.db.get_write_connection()
        try:
            row = conn.execute(
                "SELECT assigned_to, assignment_history_json FROM qc_runs WHERE run_uuid = ?",
                (run_uuid,),
            ).fetchone()
            if not row:
                raise ValueError(f"QC run not found: {run_uuid}")
            history = _loads(row["assignment_history_json"], [])
            history.append(
                {
                    "assigned_to": assignee,
                    "previous": row["assigned_to"],
                    "changed_at": _utc_now(),
                }
            )
            conn.execute(
                "UPDATE qc_runs SET assigned_to = ?, assignment_history_json = ? WHERE run_uuid = ?",
                (assignee.strip(), _json(history), run_uuid),
            )
            conn.commit()
        finally:
            conn.close()

    def get_profile_overrides(self, profile_key: str) -> Dict[str, float]:
        conn = self.db.get_read_connection()
        try:
            row = conn.execute(
                "SELECT setting_value FROM project_settings WHERE project_id = 1 AND setting_key = ? AND scope = 'qc_profile'",
                (f"segy.{profile_key}",),
            ).fetchone()
            return {key: float(value) for key, value in _loads(row["setting_value"], {}).items()} if row else {}
        finally:
            conn.close()

    def save_profile_overrides(self, profile_key: str, overrides: Dict[str, float]) -> None:
        conn = self.db.get_write_connection()
        try:
            conn.execute(
                "INSERT INTO project_settings (project_id, setting_key, setting_value, value_type, scope, updated_at) "
                "VALUES (1, ?, ?, 'json', 'qc_profile', ?) "
                "ON CONFLICT(project_id, setting_key, scope) DO UPDATE SET setting_value = excluded.setting_value, "
                "value_type = 'json', updated_at = excluded.updated_at",
                (f"segy.{profile_key}", _json(overrides), _utc_now()),
            )
            conn.commit()
        finally:
            conn.close()

    def register_report(
        self,
        run_uuid: str,
        report_type: str,
        title: str,
        format_name: str,
        file_path: str | Path,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        report_uuid = str(uuid.uuid4())
        path = Path(file_path).expanduser().resolve()
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        conn = self.db.get_write_connection()
        try:
            run = conn.execute("SELECT id FROM qc_runs WHERE run_uuid = ?", (run_uuid,)).fetchone()
            if not run:
                raise ValueError(f"QC run not found: {run_uuid}")
            conn.execute(
                "INSERT INTO reports (project_id, qc_run_id, report_uuid, report_type, title, format, status, "
                "file_path, sha256, metadata_json, generated_at, created_at) "
                "VALUES (1, ?, ?, ?, ?, ?, 'completed', ?, ?, ?, ?, ?)",
                (
                    run["id"],
                    report_uuid,
                    report_type,
                    title,
                    format_name,
                    str(path),
                    digest,
                    _json(metadata or {}),
                    _utc_now(),
                    _utc_now(),
                ),
            )
            conn.commit()
            return report_uuid
        finally:
            conn.close()
