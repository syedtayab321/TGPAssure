from __future__ import annotations

import sqlite3
from pathlib import Path


class DatabaseEngine:
    def __init__(self, database_path: str | Path, timeout: float = 30.0) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        self.timeout = timeout
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect(query_only=False)
        try:
            journal_mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if str(journal_mode).lower() != "wal":
                raise sqlite3.OperationalError("SQLite failed to enable WAL journal mode")
        finally:
            connection.close()

    def _connect(self, query_only: bool) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            timeout=self.timeout,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(f"PRAGMA busy_timeout={max(0, int(self.timeout * 1000))}")
        if query_only:
            connection.execute("PRAGMA query_only=ON")
        return connection

    def get_read_connection(self) -> sqlite3.Connection:
        return self._connect(query_only=True)

    def get_write_connection(self) -> sqlite3.Connection:
        connection = self._connect(query_only=False)
        journal_mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        if str(journal_mode).lower() != "wal":
            connection.close()
            raise sqlite3.OperationalError("SQLite database is not operating in WAL mode")
        return connection