from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Dict, Any

from core.data_access.db_engine import DatabaseEngine


class SettingsStore:
    def __init__(self, db_engine: DatabaseEngine) -> None:
        self._db_engine = db_engine
        self._init_table()

    def _init_table(self) -> None:
        conn = self._db_engine.get_write_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    app_settings_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                INSERT OR IGNORE INTO settings (id, app_settings_json)
                VALUES (1, '{}')
            """)
            conn.commit()
        finally:
            conn.close()

    def get(self, key: str, default: Any = None) -> Any:
        conn = self._db_engine.get_read_connection()
        try:
            row = conn.execute("SELECT app_settings_json FROM settings WHERE id = 1").fetchone()
            if row is None:
                return default
            settings = json.loads(row["app_settings_json"])
            return settings.get(key, default)
        except:
            return default
        finally:
            conn.close()

    def set(self, key: str, value: Any) -> None:
        conn = self._db_engine.get_write_connection()
        try:
            row = conn.execute("SELECT app_settings_json FROM settings WHERE id = 1").fetchone()
            settings = json.loads(row["app_settings_json"]) if row else {}
            settings[key] = value
            conn.execute(
                "UPDATE settings SET app_settings_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                (json.dumps(settings),)
            )
            conn.commit()
        finally:
            conn.close()

    def get_all(self) -> Dict[str, Any]:
        conn = self._db_engine.get_read_connection()
        try:
            row = conn.execute("SELECT app_settings_json FROM settings WHERE id = 1").fetchone()
            if row is None:
                return {}
            return json.loads(row["app_settings_json"])
        except:
            return {}
        finally:
            conn.close()