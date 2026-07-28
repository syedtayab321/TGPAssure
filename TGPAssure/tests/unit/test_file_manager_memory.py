from __future__ import annotations

import pytest
import tempfile
import shutil
import psutil
import time
from pathlib import Path

from core.data_access.db_engine import DatabaseEngine
from core.data_access.project_repository import ProjectRepository
from core.data_access.file_manager import FileManager


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


def test_streaming_hash_does_not_load_full_file(file_manager: FileManager, temp_dir: Path) -> None:
    test_file = temp_dir / "test_file.bin"
    
    chunk_size = 1024 * 1024
    total_size = 16 * chunk_size
    
    with open(test_file, "wb") as f:
        written = 0
        while written < total_size:
            chunk = b"X" * min(chunk_size, total_size - written)
            f.write(chunk)
            written += len(chunk)
    
    time.sleep(0.5)
    
    process = psutil.Process()
    initial_memory = process.memory_info().rss
    
    sha256_hash, size_bytes = file_manager._compute_sha256_streaming(test_file)
    
    import hashlib
    expected_sha256 = hashlib.sha256()
    with open(test_file, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            expected_sha256.update(chunk)
    
    assert sha256_hash == expected_sha256.hexdigest()
    assert size_bytes == total_size
    
    peak_memory = process.memory_info().rss
    memory_increase = (peak_memory - initial_memory) / (1024 * 1024)
    
    assert memory_increase < 100, f"Memory increased by {memory_increase} MB, should be under 100 MB"


def test_import_large_file_memory_efficient(file_manager: FileManager, temp_dir: Path) -> None:
    test_file = temp_dir / "large_file.txt"
    
    chunk_size = 1024 * 1024
    total_size = 16 * chunk_size
    
    with open(test_file, "wb") as f:
        written = 0
        pattern = b"Hello World\n"
        while written < total_size:
            remaining = min(chunk_size, total_size - written)
            chunk = (pattern * ((remaining + len(pattern) - 1) // len(pattern)))[:remaining]
            f.write(chunk)
            written += len(chunk)
    
    time.sleep(0.5)
    
    process = psutil.Process()
    initial_memory = process.memory_info().rss
    
    project_file = file_manager.import_file(test_file, "general")
    
    peak_memory = process.memory_info().rss
    memory_increase = (peak_memory - initial_memory) / (1024 * 1024)
    
    assert project_file.size_bytes == total_size
    assert project_file.sha256 is not None
    assert memory_increase < 100, f"Memory increased by {memory_increase} MB, should be under 100 MB"