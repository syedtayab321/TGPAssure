from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from core.data_access.db_engine import DatabaseEngine


class DataQualityService:
    def __init__(self, db_engine: DatabaseEngine) -> None:
        self._db = db_engine

    def count_findings_by_severity(self, unresolved_only: bool = False) -> Dict[str, int]:
        conn = self._db.get_read_connection()
        try:
            where = "WHERE is_resolved = 0" if unresolved_only else ""
            rows = conn.execute(
                f"SELECT severity, COUNT(*) AS cnt FROM qc_findings {where} GROUP BY severity"
            ).fetchall()
            counts = {"critical": 0, "error": 0, "warning": 0, "info": 0}
            counts.update({str(row["severity"]): int(row["cnt"]) for row in rows})
            return counts
        finally:
            conn.close()

    def latest_qc_summary(self) -> Dict[str, Any]:
        conn = self._db.get_read_connection()
        try:
            totals = conn.execute(
                "SELECT COUNT(*) AS total_runs, "
                "SUM(CASE WHEN overall_result = 'pass' THEN 1 ELSE 0 END) AS passed_runs, "
                "SUM(CASE WHEN overall_result = 'warn' THEN 1 ELSE 0 END) AS warning_runs, "
                "SUM(CASE WHEN overall_result = 'fail' THEN 1 ELSE 0 END) AS failed_runs, "
                "SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled_runs, "
                "AVG(CASE WHEN score IS NOT NULL THEN score END) AS average_score "
                "FROM qc_runs"
            ).fetchone()
            finding_totals = conn.execute(
                "SELECT COUNT(*) AS total_findings, "
                "SUM(CASE WHEN is_resolved = 0 THEN 1 ELSE 0 END) AS unresolved_findings "
                "FROM qc_findings"
            ).fetchone()
            latest = conn.execute(
                "SELECT run_uuid, source_file_name, qc_profile, status, overall_result, score, created_at, summary_json "
                "FROM qc_runs ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            result = {
                "total_runs": int(totals["total_runs"] or 0),
                "passed_runs": int(totals["passed_runs"] or 0),
                "warning_runs": int(totals["warning_runs"] or 0),
                "failed_runs": int(totals["failed_runs"] or 0),
                "cancelled_runs": int(totals["cancelled_runs"] or 0),
                "average_score": float(totals["average_score"] or 0.0),
                "total_findings": int(finding_totals["total_findings"] or 0),
                "unresolved_findings": int(finding_totals["unresolved_findings"] or 0),
                "latest": dict(latest) if latest else None,
            }
            if result["latest"]:
                try:
                    result["latest"]["summary"] = json.loads(result["latest"].pop("summary_json") or "{}")
                except (TypeError, ValueError):
                    result["latest"]["summary"] = {}
            return result
        finally:
            conn.close()

    def recent_runs(self, limit: int = 25) -> List[Dict[str, Any]]:
        conn = self._db.get_read_connection()
        try:
            rows = conn.execute(
                "SELECT run_uuid, source_file_name, qc_profile, status, overall_result, score, created_at, completed_at, duration_ms "
                "FROM qc_runs ORDER BY created_at DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def latest_stage_scores(self) -> List[Dict[str, Any]]:
        conn = self._db.get_read_connection()
        try:
            row = conn.execute("SELECT id FROM qc_runs ORDER BY created_at DESC LIMIT 1").fetchone()
            if not row:
                return []
            rows = conn.execute(
                "SELECT stage_name, result, score, duration_ms FROM qc_stage_results WHERE qc_run_id = ? ORDER BY stage_order",
                (row["id"],),
            ).fetchall()
            return [dict(item) for item in rows]
        finally:
            conn.close()