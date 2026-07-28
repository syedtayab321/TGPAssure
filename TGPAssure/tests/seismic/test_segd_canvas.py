from __future__ import annotations

import pytest
import tempfile
import shutil
import numpy as np
import struct
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from core.data_access.db_engine import DatabaseEngine
from core.infrastructure.service_container import ServiceContainer
from core.infrastructure.job_manager import JobManager
from modules.seismic.segd_viewer.segd_reader import SegdReader
from modules.seismic.segd_viewer.trace_window_loader import TraceWindowLoader
from modules.seismic.segd_viewer.segd_canvas import SegdCanvas
from modules.seismic.segd_viewer.configuration_panel import ConfigurationPanel
from modules.seismic.segd_viewer.picking_tool import PickingTool


@pytest.fixture
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def temp_dir() -> Path:
    path = Path(tempfile.mkdtemp())
    yield path
    shutil.rmtree(path, ignore_errors=True)


def create_test_segd_file(path: Path) -> None:
    with open(path, "wb") as f:
        general_header_1 = bytearray(64)
        general_header_1[0:2] = struct.pack('>h', 1)
        general_header_1[2:4] = struct.pack('>h', 64)
        general_header_1[4:6] = struct.pack('>h', 32)
        general_header_1[6:8] = struct.pack('>h', 0)
        general_header_1[8:10] = struct.pack('>h', 240)
        general_header_1[10:12] = struct.pack('>h', 1)
        general_header_1[12:14] = struct.pack('>h', 10)
        general_header_1[14:16] = struct.pack('>h', 1)
        general_header_1[16:18] = struct.pack('>h', 1)
        general_header_1[18:20] = struct.pack('>h', 4)
        general_header_1[20:22] = struct.pack('>h', 2)
        f.write(general_header_1)
        
        general_header_2 = bytearray(64)
        general_header_2[0:2] = struct.pack('>h', 10)
        general_header_2[2:4] = struct.pack('>h', 1)
        general_header_2[4:6] = struct.pack('>h', 2026)
        general_header_2[6:8] = struct.pack('>h', 195)
        general_header_2[8:10] = struct.pack('>h', 8)
        general_header_2[10:12] = struct.pack('>h', 3)
        general_header_2[12:14] = struct.pack('>h', 5)
        general_header_2[14:16] = struct.pack('>h', 0)
        f.write(general_header_2)
        
        general_header_3 = bytearray(64)
        general_header_3[0:2] = struct.pack('>h', 0)
        general_header_3[2:4] = struct.pack('>h', 0)
        general_header_3[4:6] = struct.pack('>h', 32)
        general_header_3[6:8] = struct.pack('>h', 240)
        general_header_3[8:10] = struct.pack('>h', 0)
        f.write(general_header_3)
        
        channel_set_descriptor = bytearray(32)
        channel_set_descriptor[0:2] = struct.pack('>h', 1)
        channel_set_descriptor[2:4] = struct.pack('>h', 1)
        channel_set_descriptor[4:6] = struct.pack('>h', 100)
        channel_set_descriptor[6:8] = struct.pack('>h', 4)
        channel_set_descriptor[8:10] = struct.pack('>h', 2)
        f.write(channel_set_descriptor)
        
        trace_headers = bytearray(240)
        f.write(trace_headers)
        
        for i in range(10):
            trace_data = np.random.randn(100).astype(np.float32)
            f.write(trace_data.tobytes())


@pytest.fixture
def db_engine(temp_dir: Path) -> DatabaseEngine:
    db_path = temp_dir / "test.db"
    engine = DatabaseEngine(db_path)
    conn = engine.get_write_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS project (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                project_uuid TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("INSERT OR IGNORE INTO project (id, project_uuid, name) VALUES (1, 'test', 'Test')")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL DEFAULT 1,
                file_id INTEGER,
                module TEXT NOT NULL,
                bookmark_type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                target_json TEXT NOT NULL DEFAULT '{}',
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL DEFAULT 1,
                file_id INTEGER,
                job_uuid TEXT NOT NULL UNIQUE,
                job_type TEXT NOT NULL,
                module TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                priority INTEGER NOT NULL DEFAULT 0,
                progress REAL NOT NULL DEFAULT 0.0,
                message TEXT,
                payload_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT,
                error_text TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                started_at TEXT,
                finished_at TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    finally:
        conn.close()
    return engine


@pytest.fixture
def container(app: QApplication, db_engine: DatabaseEngine) -> ServiceContainer:
    container = ServiceContainer()
    container.register(DatabaseEngine, db_engine)
    job_manager = JobManager(db_engine)
    container.register(JobManager, job_manager)
    return container


def test_canvas_mode_toggle(app: QApplication, temp_dir: Path, container: ServiceContainer) -> None:
    test_file = temp_dir / "test.sgd"
    create_test_segd_file(test_file)
    
    loader = TraceWindowLoader(test_file)
    canvas = SegdCanvas()
    canvas.initialize(loader, container.resolve(JobManager))
    
    assert canvas._mode == SegdCanvas.MODE_PAN
    
    canvas.set_mode(SegdCanvas.MODE_SELECT)
    assert canvas._mode == SegdCanvas.MODE_SELECT
    
    canvas.set_mode(SegdCanvas.MODE_PICK)
    assert canvas._mode == SegdCanvas.MODE_PICK
    
    canvas.set_mode(SegdCanvas.MODE_MEASURE)
    assert canvas._mode == SegdCanvas.MODE_MEASURE


def test_config_panel_channel_selection(app: QApplication) -> None:
    panel = ConfigurationPanel()
    panel.set_channel_count(5)
    
    assert panel.channel_list.count() == 5
    assert len(panel._selected_channels) == 5


def test_config_panel_config_changed_signal(app: QApplication) -> None:
    panel = ConfigurationPanel()
    signal_emitted = False
    
    def on_config_changed():
        nonlocal signal_emitted
        signal_emitted = True
    
    panel.config_changed.connect(on_config_changed)
    
    panel.set_channel_count(3)
    panel._on_config_changed()
    
    assert signal_emitted is True


def test_picking_tool_creates_bookmark(db_engine: DatabaseEngine) -> None:
    pick_tool = PickingTool(db_engine)
    
    view_state = {
        "trace_index": 5,
        "sample_index": 42,
        "trace_start": 0,
        "trace_end": 10,
        "sample_start": 0,
        "sample_end": 100
    }
    
    pick_id = pick_tool.create_pick(view_state, {"note": "Test pick"})
    
    assert pick_id is not None
    assert len(pick_tool.get_picks()) == 1
    
    conn = db_engine.get_read_connection()
    try:
        row = conn.execute("SELECT * FROM bookmarks WHERE bookmark_type = 'pick'").fetchone()
        assert row is not None
        assert "pick" in row["bookmark_type"]
    finally:
        conn.close()