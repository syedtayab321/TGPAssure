from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from core.data_access.db_engine import DatabaseEngine


class SeismicInterpretationStore:
    def __init__(self, database_engine: DatabaseEngine) -> None:
        self.database_engine = database_engine
        self._initialize()

    def _initialize(self) -> None:
        connection = self.database_engine.get_write_connection()
        try:
            connection.execute('CREATE TABLE IF NOT EXISTS seismic_interpretations (id INTEGER PRIMARY KEY AUTOINCREMENT, interpretation_uuid TEXT NOT NULL UNIQUE, kind TEXT NOT NULL, name TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)')
            connection.commit()
        finally:
            connection.close()

    def save_manual_pick(self, trace_index: int, sample_index: int, sample_interval_ms: float, metadata: dict[str, Any] | None = None) -> str:
        payload = {'trace_index': int(trace_index), 'sample_index': int(sample_index), 'time_ms': float(sample_index) * float(sample_interval_ms), 'metadata': metadata or {}}
        return self._save('first_break_pick', f'Pick T{trace_index}', payload)

    def save_horizon(self, name: str, points: list[dict[str, float]]) -> str:
        if not name.strip() or not points:
            raise ValueError('A horizon requires a name and at least one point')
        normalized = sorted(({'trace_index': int(point['trace_index']), 'sample_index': int(point['sample_index'])} for point in points), key=lambda point: point['trace_index'])
        return self._save('reflection_horizon', name.strip(), {'points': normalized})

    def list_interpretations(self, kind: str | None = None) -> list[dict[str, Any]]:
        connection = self.database_engine.get_read_connection()
        try:
            if kind is None:
                rows = connection.execute('SELECT interpretation_uuid, kind, name, payload_json, created_at, updated_at FROM seismic_interpretations ORDER BY created_at').fetchall()
            else:
                rows = connection.execute('SELECT interpretation_uuid, kind, name, payload_json, created_at, updated_at FROM seismic_interpretations WHERE kind = ? ORDER BY created_at', (kind,)).fetchall()
            return [{**dict(row), 'payload': json.loads(row['payload_json'])} for row in rows]
        finally:
            connection.close()

    def _save(self, kind: str, name: str, payload: dict[str, Any]) -> str:
        identifier = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        connection = self.database_engine.get_write_connection()
        try:
            connection.execute('INSERT INTO seismic_interpretations (interpretation_uuid, kind, name, payload_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)', (identifier, kind, name, json.dumps(payload), now, now))
            connection.commit()
        finally:
            connection.close()
        return identifier
