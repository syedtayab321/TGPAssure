from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from core.data_access.db_engine import DatabaseEngine
from core.data_access.project_migrator import ProjectMigrator


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INITIAL_MIGRATION = PROJECT_ROOT / "migrations" / "0001_initial.sql"
EXPECTED_TABLES = {
    "project",
    "project_files",
    "jobs",
    "qc_runs",
    "qc_stage_results",
    "qc_findings",
    "processing_runs",
    "reports",
    "bookmarks",
    "recent_files",
    "project_settings",
    "log_entries_index",
}
EXPECTED_INDEXES = {
    "idx_files_module",
    "idx_jobs_status",
    "idx_qc_findings_severity",
    "idx_processing_runs_file",
}


def test_initial_migration_creates_full_schema_and_backup(tmp_path):
    database_path = tmp_path / "project.sqlite3"
    engine = DatabaseEngine(database_path)
    migrator = ProjectMigrator(engine, PROJECT_ROOT / "migrations")

    applied_versions = migrator.migrate()

    expected_versions = sorted(int(path.name[:4]) for path in (PROJECT_ROOT / "migrations").glob("[0-9][0-9][0-9][0-9]_*.sql"))
    assert applied_versions == expected_versions
    assert migrator.get_current_version() == expected_versions[-1]

    connection = engine.get_read_connection()
    try:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        indexes = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"
            )
        }
    finally:
        connection.close()

    assert EXPECTED_TABLES.issubset(tables)
    assert EXPECTED_INDEXES.issubset(indexes)

    backups = sorted((tmp_path / "backups").glob("*.sqlite3"), key=lambda path: path.name)
    assert len(backups) == len(expected_versions)

    first_backup = next(path for path in backups if ".before_0001." in path.name)
    backup_connection = sqlite3.connect(first_backup)
    try:
        project_table = backup_connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'project'"
        ).fetchone()
    finally:
        backup_connection.close()

    assert project_table is None


def test_second_migrate_call_is_idempotent_and_creates_no_extra_backup(tmp_path):
    engine = DatabaseEngine(tmp_path / "project.sqlite3")
    migrator = ProjectMigrator(engine, PROJECT_ROOT / "migrations")

    expected_versions = sorted(int(path.name[:4]) for path in (PROJECT_ROOT / "migrations").glob("[0-9][0-9][0-9][0-9]_*.sql"))
    assert migrator.migrate() == expected_versions
    backup_count_after_first_run = len(list((tmp_path / "backups").iterdir()))

    assert migrator.migrate() == []
    backup_count_after_second_run = len(list((tmp_path / "backups").iterdir()))

    assert backup_count_after_second_run == backup_count_after_first_run


def test_pending_migrations_are_applied_in_numeric_order(tmp_path):
    migrations_directory = tmp_path / "migrations"
    migrations_directory.mkdir()
    shutil.copy2(INITIAL_MIGRATION, migrations_directory / "0001_initial.sql")
    (migrations_directory / "0003_seed_audit.sql").write_text(
        "INSERT INTO audit_sequence (value) VALUES ('third');",
        encoding="utf-8",
    )
    (migrations_directory / "0002_create_audit.sql").write_text(
        "CREATE TABLE audit_sequence ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "value TEXT NOT NULL"
        "); "
        "INSERT INTO audit_sequence (value) VALUES ('second');",
        encoding="utf-8",
    )

    engine = DatabaseEngine(tmp_path / "project.sqlite3")
    migrator = ProjectMigrator(engine, migrations_directory)

    applied_versions = migrator.migrate()

    assert applied_versions == [1, 2, 3]
    assert migrator.get_current_version() == 3

    connection = engine.get_read_connection()
    try:
        values = [
            row["value"]
            for row in connection.execute(
                "SELECT value FROM audit_sequence ORDER BY id"
            )
        ]
    finally:
        connection.close()

    assert values == ["second", "third"]
    assert len(list((tmp_path / "backups").glob("*.sqlite3"))) == 3


def test_failed_migration_rolls_back_and_keeps_previous_schema_version(tmp_path):
    migrations_directory = tmp_path / "migrations"
    migrations_directory.mkdir()
    shutil.copy2(INITIAL_MIGRATION, migrations_directory / "0001_initial.sql")
    (migrations_directory / "0002_broken.sql").write_text(
        "CREATE TABLE should_rollback (id INTEGER PRIMARY KEY); "
        "INSERT INTO table_that_does_not_exist DEFAULT VALUES;",
        encoding="utf-8",
    )

    engine = DatabaseEngine(tmp_path / "project.sqlite3")
    first_migrator = ProjectMigrator(engine, migrations_directory)

    with pytest.raises(sqlite3.Error):
        first_migrator.migrate()

    assert first_migrator.get_current_version() == 1

    connection = engine.get_read_connection()
    try:
        rolled_back_table = connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'should_rollback'"
        ).fetchone()
    finally:
        connection.close()

    assert rolled_back_table is None
    assert len(list((tmp_path / "backups").glob("*.sqlite3"))) == 2