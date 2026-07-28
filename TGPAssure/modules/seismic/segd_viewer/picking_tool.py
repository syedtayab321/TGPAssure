from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from core.data_access.db_engine import DatabaseEngine


class PickingTool:
    def __init__(self, db_engine: DatabaseEngine) -> None:
        self._db_engine = db_engine
        self._current_picks: Dict[str, Dict[str, Any]] = {}

    def create_pick(self, view_state: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> str:
        pick_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        pick = {
            "pick_id": pick_id,
            "view_state": view_state,
            "metadata": metadata or {},
            "created_at": now
        }

        self._current_picks[pick_id] = pick
        self._persist_pick(pick)

        return pick_id

    def _persist_pick(self, pick: Dict[str, Any]) -> None:
        conn = self._db_engine.get_write_connection()
        try:
            conn.execute(
                "INSERT INTO bookmarks (project_id, module, bookmark_type, title, target_json, created_at) "
                "VALUES (1, 'segd_viewer', 'pick', ?, ?, ?)",
                (
                    f"Pick {pick['pick_id'][:8]}",
                    json.dumps(pick["view_state"]),
                    pick["created_at"]
                )
            )
            conn.commit()
        finally:
            conn.close()

    def get_picks(self) -> Dict[str, Dict[str, Any]]:
        return self._current_picks

    def clear_picks(self) -> None:
        self._current_picks.clear()

    def get_measurement(self, start_pos: Dict[str, Any], end_pos: Dict[str, Any]) -> Dict[str, float]:
        time_delta = abs(end_pos.get("sample_index", 0) - start_pos.get("sample_index", 0))
        amplitude_delta = abs(end_pos.get("amplitude", 0) - start_pos.get("amplitude", 0))
        trace_delta = abs(end_pos.get("trace_index", 0) - start_pos.get("trace_index", 0))

        return {
            "time_delta_ms": time_delta,
            "amplitude_delta": amplitude_delta,
            "trace_delta": trace_delta
        }