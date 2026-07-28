from __future__ import annotations

import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from core.data_access.db_engine import DatabaseEngine


class ProjectMigrator:
    _migration_pattern = re.compile(r"^(\d+)_.*\.sql$")

    def __init__(
        self,
        database_engine: DatabaseEngine,
        migrations_directory: str | Path,
    ) -> None:
        self.database_engine = database_engine
        self.migrations_directory = Path(migrations_directory).expanduser().resolve()
        if not self.migrations_directory.is_dir():
            raise FileNotFoundError(
                f"Migrations directory does not exist: {self.migrations_directory}"
            )

    def get_current_version(self) -> int:
        connection = self.database_engine.get_read_connection()
        try:
            table_exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'project'"
            ).fetchone()
            if table_exists is None:
                return 0
            row = connection.execute(
                "SELECT schema_version FROM project ORDER BY id LIMIT 1"
            ).fetchone()
            if row is None:
                return 0
            version = int(row["schema_version"])
            if version < 0:
                raise ValueError("Project schema_version cannot be negative")
            return version
        finally:
            connection.close()

    def migrate(self) -> list[int]:
        current_version = self.get_current_version()
        applied_versions: list[int] = []
        for version, migration_path in self._pending_migrations(current_version):
            self._backup_database(version)
            self._apply_migration(version, migration_path)
            applied_versions.append(version)
            current_version = version
        return applied_versions

    def _pending_migrations(self, current_version: int) -> list[tuple[int, Path]]:
        migrations: list[tuple[int, Path]] = []
        seen_versions: set[int] = set()
        for path in self.migrations_directory.iterdir():
            if not path.is_file():
                continue
            match = self._migration_pattern.match(path.name)
            if match is None:
                continue
            version = int(match.group(1))
            if version in seen_versions:
                raise ValueError(f"Duplicate migration version detected: {version}")
            seen_versions.add(version)
            migrations.append((version, path))
        migrations.sort(key=lambda item: item[0])
        return [item for item in migrations if item[0] > current_version]

    def _backup_database(self, migration_version: int) -> Path:
        connection = self.database_engine.get_write_connection()
        try:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            connection.close()

        backups_directory = self.database_engine.database_path.parent / "backups"
        backups_directory.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        suffix = self.database_engine.database_path.suffix or ".sqlite3"
        backup_name = (
            f"{self.database_engine.database_path.stem}.before_{migration_version:04d}."
            f"{timestamp}{suffix}"
        )
        backup_path = backups_directory / backup_name
        shutil.copy2(self.database_engine.database_path, backup_path)
        return backup_path

    def _apply_migration(self, version: int, migration_path: Path) -> None:
        sql = migration_path.read_text(encoding="utf-8")
        if not sql.strip():
            raise ValueError(f"Migration file is empty: {migration_path}")
        version_update = (
            "UPDATE project "
            f"SET schema_version = {version}, "
            "updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') "
            "WHERE id = (SELECT id FROM project ORDER BY id LIMIT 1);"
        )
        wrapped_script = f"BEGIN IMMEDIATE;\n{sql}\n{version_update}\nCOMMIT;"
        connection = self.database_engine.get_write_connection()
        try:
            connection.executescript(wrapped_script)
            row = connection.execute(
                "SELECT schema_version FROM project ORDER BY id LIMIT 1"
            ).fetchone()
            if row is None or int(row["schema_version"]) != version:
                raise sqlite3.DatabaseError(
                    f"Migration {version} did not persist the expected schema_version"
                )
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()