from __future__ import annotations

import json
import mimetypes
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from core.data_access.db_engine import DatabaseEngine


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


class QcHistoryRepository:
    """Unified read/write access to QC history shared by all TGPAssure modules."""

    def __init__(self, db_engine: DatabaseEngine) -> None:
        self.db = db_engine
        self.ensure_schema()

    def ensure_schema(self) -> None:
        conn = self.db.get_write_connection()
        try:
            tables = {
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            if "qc_runs" not in tables:
                return
            self._ensure_column(conn, "qc_runs", "source_file_path", "TEXT")
            self._ensure_column(conn, "qc_runs", "source_file_name", "TEXT")
            self._ensure_column(conn, "qc_runs", "duration_ms", "INTEGER")
            if "qc_findings" in tables:
                self._ensure_column(conn, "qc_findings", "trace_index", "INTEGER")
                self._ensure_column(conn, "qc_findings", "suggested_action", "TEXT")
                self._ensure_column(conn, "qc_findings", "updated_at", "TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_qc_runs_created ON qc_runs(created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_qc_runs_module_created ON qc_runs(module, created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_qc_runs_file_created ON qc_runs(file_id, created_at DESC)")
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _ensure_column(conn: Any, table: str, column: str, definition: str) -> None:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def list_runs(
        self,
        limit: int = 500,
        module: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        conn = self.db.get_read_connection()
        try:
            where: list[str] = []
            params: list[Any] = []
            if module and module.lower() not in {"all", "*"}:
                where.append("LOWER(r.module) = LOWER(?)")
                params.append(module)
            if search and search.strip():
                token = f"%{search.strip().lower()}%"
                where.append(
                    "(LOWER(COALESCE(r.source_file_name, '')) LIKE ? OR "
                    "LOWER(COALESCE(r.source_file_path, '')) LIKE ? OR "
                    "LOWER(COALESCE(f.display_name, '')) LIKE ? OR "
                    "LOWER(COALESCE(r.qc_profile, '')) LIKE ? OR "
                    "LOWER(COALESCE(r.run_uuid, '')) LIKE ?)"
                )
                params.extend([token] * 5)
            clause = "WHERE " + " AND ".join(where) if where else ""
            params.append(max(1, min(5000, int(limit))))
            rows = conn.execute(
                "SELECT r.run_uuid, r.module, r.qc_profile, r.profile_version, r.status, r.overall_result, "
                "r.score, r.source_file_name, r.source_file_path, r.started_at, r.completed_at, r.created_at, "
                "r.duration_ms, r.summary_json, f.display_name AS file_display_name, "
                "f.absolute_path AS file_absolute_path, "
                "(SELECT COUNT(*) FROM qc_stage_results s WHERE s.qc_run_id = r.id) AS stage_count, "
                "(SELECT COUNT(*) FROM qc_findings q WHERE q.qc_run_id = r.id) AS finding_count, "
                "(SELECT COUNT(*) FROM qc_findings q WHERE q.qc_run_id = r.id AND COALESCE(q.is_resolved,0)=0) "
                "AS unresolved_count "
                "FROM qc_runs r LEFT JOIN project_files f ON f.id = r.file_id "
                f"{clause} ORDER BY COALESCE(r.completed_at, r.started_at, r.created_at) DESC LIMIT ?",
                tuple(params),
            ).fetchall()
            results: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                item["summary"] = _loads(item.get("summary_json"), {})
                item["display_file"] = (
                    item.get("source_file_name")
                    or item.get("file_display_name")
                    or Path(str(item.get("source_file_path") or item.get("file_absolute_path") or "Unknown")).name
                )
                item["file_path"] = item.get("source_file_path") or item.get("file_absolute_path") or ""
                results.append(item)
            return results
        finally:
            conn.close()

    def get_run_details(self, run_uuid: str) -> Optional[dict[str, Any]]:
        conn = self.db.get_read_connection()
        try:
            row = conn.execute(
                "SELECT r.*, f.display_name AS file_display_name, f.absolute_path AS file_absolute_path "
                "FROM qc_runs r LEFT JOIN project_files f ON f.id = r.file_id WHERE r.run_uuid = ?",
                (run_uuid,),
            ).fetchone()
            if row is None:
                return None
            run = dict(row)
            run["summary"] = _loads(run.get("summary_json"), {})
            run["parameters"] = _loads(run.get("parameters_json"), {})
            run["file_path"] = run.get("source_file_path") or run.get("file_absolute_path") or ""
            run["display_file"] = run.get("source_file_name") or run.get("file_display_name") or "Unknown"

            stage_rows = conn.execute(
                "SELECT id, stage_key, stage_name, stage_order, status, result, score, metrics_json, message, "
                "started_at, completed_at, duration_ms FROM qc_stage_results WHERE qc_run_id = ? "
                "ORDER BY stage_order, id",
                (run["id"],),
            ).fetchall()
            stages: list[dict[str, Any]] = []
            for stage_row in stage_rows:
                stage = dict(stage_row)
                stage["metrics"] = _loads(stage.get("metrics_json"), {})
                stages.append(stage)
            run["stages"] = stages

            finding_rows = conn.execute(
                "SELECT q.*, s.stage_key, s.stage_name FROM qc_findings q "
                "LEFT JOIN qc_stage_results s ON s.id = q.stage_result_id "
                "WHERE q.qc_run_id = ? ORDER BY "
                "CASE LOWER(q.severity) WHEN 'critical' THEN 0 WHEN 'error' THEN 1 WHEN 'fail' THEN 1 "
                "WHEN 'high' THEN 2 WHEN 'warning' THEN 3 WHEN 'warn' THEN 3 WHEN 'medium' THEN 4 "
                "WHEN 'info' THEN 5 ELSE 6 END, q.id",
                (run["id"],),
            ).fetchall()
            findings: list[dict[str, Any]] = []
            for finding_row in finding_rows:
                finding = dict(finding_row)
                finding["context"] = _loads(finding.get("context_json"), {})
                findings.append(finding)
            run["findings"] = findings
            return run
        finally:
            conn.close()

    def record_run(
        self,
        *,
        module: str,
        file_path: str | Path,
        profile: str,
        status: str,
        overall_result: str,
        score: Optional[float],
        summary: dict[str, Any],
        parameters: Optional[dict[str, Any]] = None,
        stages: Optional[Iterable[dict[str, Any]]] = None,
        findings: Optional[Iterable[dict[str, Any]]] = None,
        profile_version: str = "1.0",
        started_at: Optional[str] = None,
        completed_at: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> str:
        path = Path(file_path).expanduser().resolve()
        now = _utc_now()
        started = started_at or now
        completed = completed_at or now
        file_id = self._ensure_file(path, module, summary)
        run_uuid = str(uuid.uuid4())
        conn = self.db.get_write_connection()
        try:
            cursor = conn.execute(
                "INSERT INTO qc_runs (project_id, file_id, run_uuid, module, qc_profile, profile_version, "
                "status, overall_result, score, parameters_json, summary_json, source_file_path, source_file_name, "
                "started_at, completed_at, duration_ms, created_at) "
                "VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    file_id,
                    run_uuid,
                    str(module).lower(),
                    profile,
                    profile_version,
                    status,
                    overall_result,
                    score,
                    _json(parameters or {}),
                    _json(summary),
                    str(path),
                    path.name,
                    started,
                    completed,
                    duration_ms,
                    now,
                ),
            )
            run_id = int(cursor.lastrowid)
            stage_id_by_key: dict[str, int] = {}
            for order, stage in enumerate(stages or (), start=1):
                key = str(stage.get("stage_key") or stage.get("key") or f"stage_{order}")
                stage_cursor = conn.execute(
                    "INSERT INTO qc_stage_results (qc_run_id, stage_key, stage_name, stage_order, status, result, "
                    "score, metrics_json, message, started_at, completed_at, duration_ms) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        key,
                        str(stage.get("stage_name") or stage.get("name") or key.replace("_", " ").title()),
                        int(stage.get("stage_order") or order),
                        str(stage.get("status") or "completed"),
                        str(stage.get("result") or stage.get("status") or "pass"),
                        stage.get("score"),
                        _json(stage.get("metrics") or {}),
                        stage.get("message"),
                        stage.get("started_at") or started,
                        stage.get("completed_at") or completed,
                        stage.get("duration_ms"),
                    ),
                )
                stage_id_by_key[key] = int(stage_cursor.lastrowid)

            for index, finding in enumerate(findings or (), start=1):
                stage_key = str(finding.get("stage_key") or finding.get("stage") or "")
                stage_id = stage_id_by_key.get(stage_key)
                context = dict(finding.get("context") or {})
                action = finding.get("suggested_action") or finding.get("action")
                if action:
                    context.setdefault("suggested_action", action)
                conn.execute(
                    "INSERT INTO qc_findings (qc_run_id, stage_result_id, file_id, finding_code, severity, "
                    "category, title, description, metric_name, observed_value, expected_min, expected_max, unit, "
                    "station_id, line_id, trace_index, sample_index, location_x, location_y, location_z, context_json, "
                    "suggested_action, is_resolved, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
                    (
                        run_id,
                        stage_id,
                        file_id,
                        str(finding.get("finding_code") or finding.get("code") or f"QC-{index:03d}"),
                        str(finding.get("severity") or "warning"),
                        str(finding.get("category") or module),
                        str(finding.get("title") or "QC finding"),
                        str(finding.get("description") or finding.get("message") or "Review required"),
                        finding.get("metric_name"),
                        finding.get("observed_value"),
                        finding.get("expected_min"),
                        finding.get("expected_max"),
                        finding.get("unit"),
                        finding.get("station_id"),
                        finding.get("line_id"),
                        finding.get("trace_index"),
                        finding.get("sample_index"),
                        finding.get("location_x"),
                        finding.get("location_y"),
                        finding.get("location_z"),
                        _json(context),
                        action,
                        now,
                        now,
                    ),
                )
            conn.commit()
            return run_uuid
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ensure_file(self, path: Path, module: str, metadata: dict[str, Any]) -> int:
        conn = self.db.get_write_connection()
        try:
            existing = conn.execute(
                "SELECT id FROM project_files WHERE project_id = 1 AND absolute_path = ? LIMIT 1",
                (str(path),),
            ).fetchone()
            size = path.stat().st_size if path.is_file() else 0
            if existing is not None:
                conn.execute(
                    "UPDATE project_files SET size_bytes = ?, status = 'available', metadata_json = ?, "
                    "last_verified_at = ? WHERE id = ?",
                    (size, _json(metadata), _utc_now(), existing["id"]),
                )
                conn.commit()
                return int(existing["id"])

            mime_type, _ = mimetypes.guess_type(path.name)
            if path.suffix.lower() in {".segd", ".sgd", ".d"}:
                mime_type = "application/x-segd"
            cursor = conn.execute(
                "INSERT INTO project_files (project_id, file_uuid, module, file_role, original_name, display_name, "
                "absolute_path, relative_path, extension, mime_type, size_bytes, status, metadata_json, imported_at, "
                "last_verified_at) VALUES (1, ?, ?, 'input', ?, ?, ?, ?, ?, ?, ?, 'available', ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    "seismic" if module.lower() in {"segy", "segd", "seismic"} else module.lower(),
                    path.name,
                    path.name,
                    str(path),
                    str(path),
                    path.suffix.lower(),
                    mime_type,
                    size,
                    _json(metadata),
                    _utc_now(),
                    _utc_now(),
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()
