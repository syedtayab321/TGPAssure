from __future__ import annotations

import pytest
import tempfile
import shutil
import time
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from core.data_access.db_engine import DatabaseEngine
from core.data_access.project_repository import ProjectRepository
from core.data_access.file_manager import FileManager
from core.infrastructure.service_container import ServiceContainer
from core.infrastructure.job_manager import JobManager
from modules.workspace.workspace_manager import WorkspaceManager
from ui.main_window import MainWindow


@pytest.fixture(scope="session")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def temp_dir() -> Path:
    path = Path(tempfile.mkdtemp())
    yield path
    shutil.rmtree(path, ignore_errors=True)


def create_test_sgy_file(path: Path) -> None:
    import numpy as np
    import struct

    trace_count = 10
    sample_count = 100
    dt_us = 2000
    with path.open("wb") as f:
        text = ("C01 TGPAssure foundation smoke".ljust(80) * 40).encode("ascii")[:3200]
        f.write(text.ljust(3200, b" "))
        binary_header = bytearray(400)
        struct.pack_into(">H", binary_header, 16, dt_us)
        struct.pack_into(">H", binary_header, 20, sample_count)
        struct.pack_into(">H", binary_header, 24, 5)
        struct.pack_into(">H", binary_header, 300, 0x0100)
        struct.pack_into(">H", binary_header, 302, 1)
        f.write(binary_header)
        for i in range(trace_count):
            trace_header = bytearray(240)
            struct.pack_into(">i", trace_header, 0, i + 1)
            struct.pack_into(">i", trace_header, 8, i + 1)
            struct.pack_into(">i", trace_header, 20, i // 2 + 1)
            struct.pack_into(">H", trace_header, 114, sample_count)
            struct.pack_into(">H", trace_header, 116, dt_us)
            f.write(trace_header)
            trace_data = (np.sin(np.linspace(0, 8, sample_count)) + i * 0.02).astype(">f4")
            f.write(trace_data.tobytes())


def create_test_sgd_file(path: Path) -> None:
    import numpy as np
    import struct

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


def test_foundation_smoke(app: QApplication, temp_dir: Path) -> None:
    db_path = temp_dir / "test.db"
    db_engine = DatabaseEngine(db_path)

    from main import initialize_database, setup_container
    initialize_database(db_engine)
    container = setup_container(db_engine, temp_dir)

    main_window = MainWindow(container)
    main_window.show()
    QTest.qWait(100)

    project_name = "TestProject"
    project_folder = temp_dir / project_name
    project_folder.mkdir(exist_ok=True)

    workspace_manager = container.resolve(WorkspaceManager)
    project = workspace_manager.create_project(project_name, temp_dir)
    assert project is not None

    QTest.qWait(100)

    sgy_file = temp_dir / "test.sgy"
    sgd_file = temp_dir / "test.sgd"
    create_test_sgy_file(sgy_file)
    create_test_sgd_file(sgd_file)

    file_manager = container.resolve(FileManager)
    project_repo = container.resolve(ProjectRepository)

    sgy_project_file = file_manager.import_file(sgy_file, "seismic")
    assert sgy_project_file is not None

    sgd_project_file = file_manager.import_file(sgd_file, "seismic")
    assert sgd_project_file is not None

    QTest.qWait(100)

    from modules.seismic.segd_viewer.segd_viewer_view import SegdViewerView
    viewer = SegdViewerView(container, sgd_file)
    main_window.tab_widget.addTab(viewer, "SEG-D Viewer")
    main_window.tab_widget.setCurrentIndex(main_window.tab_widget.count() - 1)
    QTest.qWait(100)

    viewer.canvas.zoom_to_fit()
    QTest.qWait(100)

    from modules.seismic.segy_viewer.segy_viewer_widget import SegyViewerWidget

    segy_view = SegyViewerWidget(str(sgy_file), main_window)
    segy_view.setProperty("module_id", "segy_viewer")
    main_window.tab_widget.addTab(segy_view, "SEG-Y Viewer")
    main_window.tab_widget.setCurrentIndex(main_window.tab_widget.count() - 1)
    QTest.qWait(100)
    assert segy_view.property("module_id") == "segy_viewer"

    main_window.close()
    QTest.qWait(100)

    main_window2 = MainWindow(container)
    main_window2.show()
    QTest.qWait(100)

    assert main_window2.tab_widget.count() >= 1

    main_window2.close()
    QTest.qWait(100)

    assert True