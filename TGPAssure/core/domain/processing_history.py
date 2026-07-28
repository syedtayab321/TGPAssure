from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from core.data_access.db_engine import DatabaseEngine
import json


class ProcessingHistoryManager:
    """Record and query processing runs (ETL, conversions, etc.).

    This manager stores lightweight records in a `processing_runs` table.
    It is intentionally small and synchronous so callers can use it from
    both UI and background threads (the underlying DB engine serializes access).
    """

    def __init__(self, db_engine: DatabaseEngine) -> None:
        self._db = db_engine
        self._ensure_table()

    def _ensure_table(self) -> None:
        conn = self._db.get_write_connection()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS processing_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_uuid TEXT NOT NULL UNIQUE,
                    project_id INTEGER NOT NULL DEFAULT 1,
                    job_id INTEGER,
                    run_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    progress REAL NOT NULL DEFAULT 0.0,
                    message TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def record_run(self, run_uuid: str, run_type: str, payload: Optional[Dict[str, Any]] = None) -> None:
        conn = self._db.get_write_connection()
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO processing_runs (run_uuid, run_type, payload_json, status)
                VALUES (?, ?, ?, 'queued')
                """,
                (run_uuid, run_type, json_safe(payload or {})),
            )
            conn.commit()
        finally:
            conn.close()

    def update_progress(self, run_uuid: str, progress: float, message: Optional[str] = None) -> None:
        conn = self._db.get_write_connection()
        try:
            conn.execute(
                """
                UPDATE processing_runs SET progress = ?, message = ?, updated_at = CURRENT_TIMESTAMP
                WHERE run_uuid = ?
                """,
                (float(progress), message, run_uuid),
            )
            conn.commit()
        finally:
            conn.close()

    def finish_run(self, run_uuid: str, result: Optional[Dict[str, Any]] = None, success: bool = True) -> None:
        status = 'finished' if success else 'failed'
        conn = self._db.get_write_connection()
        try:
            conn.execute(
                """
                UPDATE processing_runs SET status = ?, result_json = ?, finished_at = CURRENT_TIMESTAMP, progress = 1.0, updated_at = CURRENT_TIMESTAMP
                WHERE run_uuid = ?
                """,
                (status, json_safe(result or {}), run_uuid),
            )
            conn.commit()
        finally:
            conn.close()

    def get_recent_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self._db.get_read_connection()
        try:
            cur = conn.execute(
                "SELECT id, run_uuid, run_type, status, progress, message, created_at, started_at, finished_at FROM processing_runs ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
            rows = cur.fetchall()
            return [dict_from_row(r) for r in rows]
        finally:
            conn.close()

    def get_runs_by_type(self, run_type: str, limit: int = 100) -> List[Dict[str, Any]]:
        conn = self._db.get_read_connection()
        try:
            cur = conn.execute(
                "SELECT id, run_uuid, run_type, status, progress, message, created_at, started_at, finished_at FROM processing_runs WHERE run_type = ? ORDER BY created_at DESC LIMIT ?",
                (run_type, limit)
            )
            rows = cur.fetchall()
            return [dict_from_row(r) for r in rows]
        finally:
            conn.close()

    def delete_run(self, run_uuid: str) -> bool:
        conn = self._db.get_write_connection()
        try:
            cur = conn.execute("DELETE FROM processing_runs WHERE run_uuid = ?", (run_uuid,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()



def json_safe(obj: Any) -> str:
    import json

    try:
        return json.dumps(obj)
    except Exception:
        return json.dumps({})


def dict_from_row(row) -> Dict[str, Any]:
    # sqlite3.Row behaves like a mapping
    try:
        return dict(row)
    except Exception:
        # fallback for simple tuples
        return {str(i): v for i, v in enumerate(row)}
