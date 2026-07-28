from __future__ import annotations

import pytest
import tempfile
import shutil
import hashlib
import os
import psutil
from pathlib import Path
from typing import Any

from core.data_access.db_engine import DatabaseEngine
from core.data_access.project_repository import ProjectRepository
from core.data_access.file_manager import FileManager, FormatDescriptor
from core.domain.project import ProjectFile


@pytest.fixture
def temp_dir() -> Path:
    path = Path(tempfile.mkdtemp())
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def db_engine(temp_dir: Path) -> DatabaseEngine:
    db_path = temp_dir / "test.db"
    return DatabaseEngine(db_path)


@pytest.fixture
def project_repo(db_engine: DatabaseEngine) -> ProjectRepository:
    conn = db_engine.get_write_connection()
    try:
        conn.execute("""
            CREATE TABLE project (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                project_uuid TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            INSERT INTO project (id, project_uuid, name)
            VALUES (1, 'test-uuid', 'Test Project')
        """)
        conn.execute("""
            CREATE TABLE project_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL DEFAULT 1,
                file_uuid TEXT NOT NULL UNIQUE,
                module TEXT NOT NULL,
                file_role TEXT NOT NULL,
                original_name TEXT NOT NULL,
                display_name TEXT NOT NULL,
                absolute_path TEXT,
                relative_path TEXT,
                extension TEXT,
                mime_type TEXT,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                sha256 TEXT,
                status TEXT NOT NULL DEFAULT 'available',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_verified_at TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()
    return ProjectRepository(db_engine)


@pytest.fixture
def file_manager(project_repo: ProjectRepository) -> FileManager:
    return FileManager(project_repo)


def test_detect_format_by_magic_bytes(file_manager: FileManager, temp_dir: Path) -> None:
    png_data = bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52
    ])
    png_path = temp_dir / "test.png"
    with open(png_path, "wb") as f:
        f.write(png_data)
    
    format_desc = file_manager.detect_format(png_path)
    assert format_desc.format_id == "png"
    assert format_desc.extension == ".png"
    assert format_desc.mime_type == "image/png"
    assert format_desc.detected_by == "magic"


def test_detect_format_by_extension(file_manager: FileManager, temp_dir: Path) -> None:
    txt_path = temp_dir / "test.txt"
    txt_path.write_text("This is a text file")
    
    format_desc = file_manager.detect_format(txt_path)
    assert format_desc.format_id == "text"
    assert format_desc.extension == ".txt"
    assert format_desc.mime_type == "text/plain"


def test_detect_format_mislabeled_file(file_manager: FileManager, temp_dir: Path) -> None:
    png_data = bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52
    ])
    mislabeled_path = temp_dir / "test.jpg"
    with open(mislabeled_path, "wb") as f:
        f.write(png_data)
    
    format_desc = file_manager.detect_format(mislabeled_path)
    assert format_desc.format_id == "png"
    assert format_desc.extension == ".png"
    assert format_desc.mime_type == "image/png"
    assert format_desc.detected_by == "magic"


def test_import_file_uses_relative_path(file_manager: FileManager, temp_dir: Path) -> None:
    test_file = temp_dir / "test.txt"
    test_file.write_text("Test content")
    
    project_file = file_manager.import_file(test_file, "general")
    
    assert project_file.relative_path.startswith("raw/general/")
    assert project_file.relative_path.endswith(".txt")
    assert project_file.original_name == "test.txt"
    assert project_file.size_bytes == len("Test content")
    assert project_file.sha256 is not None


def test_import_file_streaming_hash(file_manager: FileManager, temp_dir: Path) -> None:
    test_file = temp_dir / "large_file.bin"
    with open(test_file, "wb") as f:
        for i in range(1000):
            f.write(b"0123456789" * 1000)
    
    sha256_hash, size_bytes = file_manager._compute_sha256_streaming(test_file)
    assert size_bytes == 10 * 1000 * 1000
    
    import hashlib
    sha256 = hashlib.sha256()
    with open(test_file, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            sha256.update(chunk)
    assert sha256_hash == sha256.hexdigest()


def test_import_file_does_not_load_full_file_into_memory(file_manager: FileManager, temp_dir: Path) -> None:
    test_file = temp_dir / "500mb_file.bin"
    chunk_size = 1024 * 1024
    total_size = 500 * chunk_size
    
    with open(test_file, "wb") as f:
        written = 0
        while written < total_size:
            chunk = b"0" * min(chunk_size, total_size - written)
            f.write(chunk)
            written += len(chunk)
    
    process = psutil.Process()
    initial_memory = process.memory_info().rss
    
    project_file = file_manager.import_file(test_file, "general")
    
    peak_memory = process.memory_info().rss
    memory_increase = (peak_memory - initial_memory) / (1024 * 1024)
    
    assert memory_increase < 100, f"Memory increased by {memory_increase} MB, should be under 100 MB"


def test_import_file_stores_sha256(file_manager: FileManager, temp_dir: Path) -> None:
    test_file = temp_dir / "test_sha256.txt"
    content = "Hello, World!"
    test_file.write_text(content)
    
    project_file = file_manager.import_file(test_file, "general")
    
    import hashlib
    expected_hash = hashlib.sha256(content.encode()).hexdigest()
    assert project_file.sha256 == expected_hash


def test_import_file_stores_correct_metadata(file_manager: FileManager, temp_dir: Path) -> None:
    test_file = temp_dir / "test_data.csv"
    test_file.write_text("col1,col2\n1,2\n3,4")
    
    project_file = file_manager.import_file(test_file, "data")
    
    assert project_file.module == "data"
    assert project_file.file_role == "imported"
    assert project_file.display_name == "test_data"
    assert project_file.extension == ".csv"


def test_format_detection_confidence(file_manager: FileManager, temp_dir: Path) -> None:
    png_data = bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A
    ])
    png_path = temp_dir / "test.png"
    with open(png_path, "wb") as f:
        f.write(png_data)
    
    format_desc = file_manager.detect_format(png_path)
    assert format_desc.confidence >= 0.9


def test_format_detection_fallback(file_manager: FileManager, temp_dir: Path) -> None:
    unknown_path = temp_dir / "test.xyz"
    unknown_path.write_text("Unknown format content")
    
    format_desc = file_manager.detect_format(unknown_path)
    assert format_desc.format_id == "unknown"
    assert format_desc.mime_type == "application/octet-stream"
    assert format_desc.confidence < 0.5