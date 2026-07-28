from __future__ import annotations

import sqlite3

import pytest

from core.data_access.db_engine import DatabaseEngine


def test_database_engine_creates_database_and_enables_wal(tmp_path):
    database_path = tmp_path / "project.sqlite3"

    engine = DatabaseEngine(database_path)

    assert database_path.exists()

    connection = engine.get_write_connection()
    try:
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
    finally:
        connection.close()

    assert str(journal_mode).lower() == "wal"
    assert foreign_keys == 1


def test_write_and_read_connections_use_the_same_real_database(tmp_path):
    engine = DatabaseEngine(tmp_path / "project.sqlite3")

    write_connection = engine.get_write_connection()
    try:
        write_connection.execute("BEGIN IMMEDIATE")
        write_connection.execute(
            "CREATE TABLE measurements (id INTEGER PRIMARY KEY, value REAL NOT NULL)"
        )
        write_connection.execute("INSERT INTO measurements (value) VALUES (?)", (42.5,))
        write_connection.commit()
    finally:
        write_connection.close()

    read_connection = engine.get_read_connection()
    try:
        row = read_connection.execute(
            "SELECT id, value FROM measurements WHERE id = 1"
        ).fetchone()
        query_only = read_connection.execute("PRAGMA query_only").fetchone()[0]
    finally:
        read_connection.close()

    assert row is not None
    assert row["id"] == 1
    assert row["value"] == pytest.approx(42.5)
    assert query_only == 1


def test_read_connection_rejects_writes(tmp_path):
    engine = DatabaseEngine(tmp_path / "project.sqlite3")

    write_connection = engine.get_write_connection()
    try:
        write_connection.execute("CREATE TABLE items (id INTEGER PRIMARY KEY)")
    finally:
        write_connection.close()

    read_connection = engine.get_read_connection()
    try:
        with pytest.raises(sqlite3.OperationalError):
            read_connection.execute("INSERT INTO items DEFAULT VALUES")
    finally:
        read_connection.close()


def test_foreign_keys_are_enforced_on_write_connections(tmp_path):
    engine = DatabaseEngine(tmp_path / "project.sqlite3")

    connection = engine.get_write_connection()
    try:
        connection.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
        connection.execute(
            "CREATE TABLE child ("
            "id INTEGER PRIMARY KEY, "
            "parent_id INTEGER NOT NULL REFERENCES parent(id)"
            ")"
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO child (parent_id) VALUES (999)")
    finally:
        connection.close()