from __future__ import annotations

import json
import sqlite3
from typing import Optional, List, Dict, Any

from core.data_access.db_engine import DatabaseEngine


class LayoutStore:
    def __init__(self, db_engine: DatabaseEngine) -> None:
        self._db_engine = db_engine
        self._init_tables()

    def _init_tables(self) -> None:
        conn = self._db_engine.get_write_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS layout_store (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    layout_data BLOB,
                    tabs_json TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                INSERT OR IGNORE INTO layout_store (id, layout_data, tabs_json)
                VALUES (1, NULL, '[]')
            """)
            conn.commit()
        finally:
            conn.close()

    def save_layout(self, layout_data: bytes) -> None:
        conn = self._db_engine.get_write_connection()
        try:
            conn.execute(
                "UPDATE layout_store SET layout_data = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                (layout_data,)
            )
            conn.commit()
        finally:
            conn.close()

    def load_layout(self) -> Optional[bytes]:
        conn = self._db_engine.get_read_connection()
        try:
            row = conn.execute(
                "SELECT layout_data FROM layout_store WHERE id = 1"
            ).fetchone()
            if row and row["layout_data"] is not None:
                return row["layout_data"]
            return None
        finally:
            conn.close()

    def save_tabs(self, tabs: List[Dict[str, Any]]) -> None:
        conn = self._db_engine.get_write_connection()
        try:
            tabs_json = json.dumps(tabs)
            conn.execute(
                "UPDATE layout_store SET tabs_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                (tabs_json,)
            )
            conn.commit()
        finally:
            conn.close()

    def load_tabs(self) -> List[Dict[str, Any]]:
        conn = self._db_engine.get_read_connection()
        try:
            row = conn.execute(
                "SELECT tabs_json FROM layout_store WHERE id = 1"
            ).fetchone()
            if row and row["tabs_json"]:
                try:
                    tabs = json.loads(row["tabs_json"])
                    if isinstance(tabs, list):
                        return tabs
                except:
                    pass
            return []
        finally:
            conn.close()

    def clear_layout(self) -> None:
        conn = self._db_engine.get_write_connection()
        try:
            conn.execute(
                "UPDATE layout_store SET layout_data = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = 1"
            )
            conn.commit()
        finally:
            conn.close()