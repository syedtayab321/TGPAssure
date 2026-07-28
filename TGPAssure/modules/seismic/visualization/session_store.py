from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.data_access.db_engine import DatabaseEngine
from modules.seismic.visualization.models import VisualizationSession


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class VisualizationSessionStore:
    def __init__(self, database_engine: DatabaseEngine | None = None) -> None:
        self.database_engine = database_engine
        if database_engine is not None:
            self._ensure_schema()

    def _ensure_schema(self) -> None:
        connection = self.database_engine.get_write_connection()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS seismic_visualization_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_uuid TEXT NOT NULL UNIQUE,
                    source_file_path TEXT NOT NULL,
                    session_name TEXT NOT NULL,
                    session_path TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_visualization_sessions_source "
                "ON seismic_visualization_sessions(source_file_path, updated_at DESC)"
            )
            connection.commit()
        finally:
            connection.close()

    def save(self, session: VisualizationSession, output_path: str | Path) -> Path:
        path = Path(output_path).expanduser().resolve()
        if path.suffix.lower() not in {".json", ".tgpvis"}:
            path = path.with_suffix(".tgpvis")
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = session.to_dict()
        payload["saved_at"] = _utc_now()
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        if self.database_engine is not None:
            self._save_database(session, path, payload)
        return path

    def load(self, input_path: str | Path) -> VisualizationSession:
        path = Path(input_path).expanduser().resolve()
        payload = json.loads(path.read_text(encoding="utf-8"))
        session = VisualizationSession.from_dict(payload)
        session.validate_source()
        return session

    def list_for_source(self, source_path: str | Path, limit: int = 25) -> list[dict[str, Any]]:
        if self.database_engine is None:
            return []
        resolved = str(Path(source_path).expanduser().resolve())
        connection = self.database_engine.get_read_connection()
        try:
            rows = connection.execute(
                "SELECT session_uuid, session_name, session_path, source_file_path, created_at, updated_at "
                "FROM seismic_visualization_sessions WHERE source_file_path = ? "
                "ORDER BY updated_at DESC LIMIT ?",
                (resolved, max(1, int(limit))),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            connection.close()

    def _save_database(
        self,
        session: VisualizationSession,
        path: Path,
        payload: dict[str, Any],
    ) -> None:
        now = _utc_now()
        source_path = str(Path(session.source_path).expanduser().resolve())
        connection = self.database_engine.get_write_connection()
        try:
            existing = connection.execute(
                "SELECT session_uuid, created_at FROM seismic_visualization_sessions WHERE session_path = ?",
                (str(path),),
            ).fetchone()
            session_uuid = str(existing["session_uuid"]) if existing else str(uuid.uuid4())
            created_at = str(existing["created_at"]) if existing else now
            connection.execute(
                """
                INSERT INTO seismic_visualization_sessions (
                    session_uuid, source_file_path, session_name, session_path,
                    payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_uuid) DO UPDATE SET
                    source_file_path = excluded.source_file_path,
                    session_name = excluded.session_name,
                    session_path = excluded.session_path,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    session_uuid,
                    source_path,
                    path.stem,
                    str(path),
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    created_at,
                    now,
                ),
            )
            connection.commit()
        finally:
            connection.close()
