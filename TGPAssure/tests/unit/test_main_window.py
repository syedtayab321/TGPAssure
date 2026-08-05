from __future__ import annotations

import pytest
import tempfile
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QDockWidget, QLabel, QTabWidget, QTabBar
from PySide6.QtTest import QTest

from core.data_access.db_engine import DatabaseEngine
from core.data_access.layout_store import LayoutStore
from core.infrastructure.service_container import ServiceContainer
from core.infrastructure.job_manager import JobManager
from modules.workspace.workspace_manager import WorkspaceManager
from ui.main_window import MainWindow
from ui.ribbon.home_ribbon import HomeRibbonProvider
from ui.docks.output_console import OutputConsole
from ui.dialogs.process_window import ProcessStage, ProcessWindow


@pytest.fixture
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def temp_db() -> Path:
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = Path(f.name)
    return db_path


@pytest.fixture
def db_engine(temp_db: Path) -> DatabaseEngine:
    db_engine = DatabaseEngine(temp_db)
    conn = db_engine.get_write_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS project (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                project_uuid TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            INSERT OR IGNORE INTO project (id, project_uuid, name)
            VALUES (1, 'test-uuid', 'Test Project')
        """)
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS project_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL DEFAULT 1,
                setting_key TEXT NOT NULL,
                setting_value TEXT NOT NULL,
                value_type TEXT NOT NULL DEFAULT 'string',
                scope TEXT NOT NULL DEFAULT 'project',
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
    return db_engine


@pytest.fixture
def container(app: QApplication, db_engine: DatabaseEngine) -> ServiceContainer:
    container = ServiceContainer()
    container.register(DatabaseEngine, db_engine)
    container.register(LayoutStore, LayoutStore(db_engine))
    container.register(WorkspaceManager, WorkspaceManager(container))
    container.register(JobManager, JobManager(db_engine))
    return container


@pytest.fixture
def main_window(app: QApplication, container: ServiceContainer) -> MainWindow:
    window = MainWindow(container)
    window.show()
    QTest.qWait(100)
    return window


def test_main_window_initial_state(main_window: MainWindow) -> None:
    assert main_window.windowTitle() == "TGPAssure E&P Software Platform"
    assert main_window.minimumSize().width() >= 900
    assert main_window.minimumSize().height() >= 540
    assert main_window.size().width() >= main_window.minimumWidth()
    assert main_window.size().height() >= main_window.minimumHeight()


def test_all_docks_present(main_window: MainWindow) -> None:
    docks = main_window.findChildren(QDockWidget)
    dock_names = [dock.windowTitle() for dock in docks]
    assert "Project Explorer" in dock_names
    assert "Properties" in dock_names
    assert "Output Console" in dock_names


def test_home_ribbon_visible(main_window: MainWindow) -> None:
    assert main_window._active_module == "home"
    assert "home" in main_window._ribbon_providers
    provider = main_window._ribbon_providers["home"]
    assert isinstance(provider, HomeRibbonProvider)
    groups = provider.build_ribbon_groups()
    assert len(groups) > 0
    assert groups[0].label == "File"


def test_professional_ribbon_navigation(main_window: MainWindow) -> None:
    labels = [main_window.ribbon_tab_bar.tabText(index) for index in range(main_window.ribbon_tab_bar.count())]
    assert labels == ["Home", "Seismic", "SEG-D", "SEG-Y", "2D/3D", "Magnetic", "Gravity", "Electrical", "Layout", "Tools", "Help"]
    assert main_window.ribbon_tab_bar.expanding() is False


def test_custom_title_bar_and_feature_badge(main_window: MainWindow) -> None:
    assert main_window.windowFlags() & Qt.FramelessWindowHint
    badges = main_window.findChildren(QLabel, "featureBadge")
    assert not any(badge.text() == "Coming Soon" for badge in badges)


def test_fit_control_restores_compact_window(main_window: MainWindow) -> None:
    main_window.showMaximized()
    main_window._fit_to_screen()
    assert not main_window.isMaximized()
    screen = main_window.screen().availableGeometry()
    assert main_window.width() <= max(screen.width(), main_window.minimumWidth())
    assert main_window.height() <= max(screen.height(), main_window.minimumHeight())
    assert main_window.width() >= main_window.minimumWidth()
    assert main_window.height() >= main_window.minimumHeight()


def test_output_console_tabs_filter_and_search(app: QApplication) -> None:
    console = OutputConsole()
    console.log("INFO", "File loaded")
    console.log("ERROR", "Validation failed")
    console.tabs.setCurrentIndex(2)
    assert "Validation failed" in console.editor.toPlainText()
    assert "File loaded" not in console.editor.toPlainText()
    console.tabs.setCurrentIndex(0)
    console.search.setText("loaded")
    assert console.editor.toPlainText().count("File loaded") == 1


def test_process_window_tracks_stages(app: QApplication) -> None:
    window = ProcessWindow("Processing")
    window.set_stages([ProcessStage("Validation", "Completed", "1.0s"), ProcessStage("Trace QC")])
    window.update_progress(45, "Reading trace headers", "Sample interval: 2ms", "2 minutes")
    assert window.progress.value() == 45
    assert window.stages.topLevelItemCount() == 2
    assert "Reading trace headers" in window.operation_label.text()


def test_tab_creation(main_window: MainWindow) -> None:
    workspace_manager = main_window.container.resolve(WorkspaceManager)
    initial_count = main_window.tab_widget.count()
    
    tab_id = workspace_manager.open_tab("test", {"title": "Test Tab"})
    QTest.qWait(50)
    
    assert main_window.tab_widget.count() == initial_count + 1
    assert tab_id in workspace_manager._tabs
    
    tab = workspace_manager._tabs[tab_id]
    assert tab.title == "Test Tab"
    assert tab.module_id == "test"


def test_close_tab_with_ctrl_w(main_window: MainWindow) -> None:
    workspace_manager = main_window.container.resolve(WorkspaceManager)
    tab_id = workspace_manager.open_tab("test", {"title": "Test Tab"})
    QTest.qWait(50)
    
    initial_count = main_window.tab_widget.count()
    main_window.tab_widget.setCurrentIndex(main_window.tab_widget.count() - 1)
    
    QTest.keySequence(main_window, QKeySequence("Ctrl+W"))
    QTest.qWait(50)
    
    assert main_window.tab_widget.count() == initial_count - 1


def test_tab_cycling(main_window: MainWindow) -> None:
    workspace_manager = main_window.container.resolve(WorkspaceManager)
    workspace_manager.open_tab("test1", {"title": "Tab 1"})
    workspace_manager.open_tab("test2", {"title": "Tab 2"})
    workspace_manager.open_tab("test3", {"title": "Tab 3"})
    QTest.qWait(50)
    
    initial_index = main_window.tab_widget.currentIndex()
    assert initial_index >= 0
    
    QTest.keySequence(main_window, QKeySequence("Ctrl+Tab"))
    QTest.qWait(50)
    assert main_window.tab_widget.currentIndex() != initial_index
    
    QTest.keySequence(main_window, QKeySequence("Ctrl+Shift+Tab"))
    QTest.qWait(50)
    assert main_window.tab_widget.currentIndex() == initial_index


def test_status_bar_present(main_window: MainWindow) -> None:
    status_bar = main_window.statusBar()
    assert status_bar is not None
    
    labels = status_bar.findChildren(QLabel)
    label_texts = [label.text() for label in labels]
    assert any("Job Progress" in text for text in label_texts)
    assert any("X:" in text for text in label_texts)
    assert any("Zoom:" in text for text in label_texts)
    assert any("Mem:" in text for text in label_texts)


def test_ribbon_action_triggers_new_project(main_window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    triggered = []
    monkeypatch.setattr(main_window, "_new_project", lambda: triggered.append(True))
    main_window._on_ribbon_action("new_project")
    assert triggered == [True]


def test_workspace_manager_get_recent_projects(main_window: MainWindow) -> None:
    workspace_manager = main_window.container.resolve(WorkspaceManager)
    recent = workspace_manager.get_recent_projects()
    assert isinstance(recent, list)


def test_layout_store_save_load(main_window: MainWindow) -> None:
    layout_store = main_window.container.resolve(LayoutStore)
    
    test_data = b"test_layout_data"
    layout_store.save_layout(test_data)
    
    loaded = layout_store.load_layout()
    assert loaded == test_data


def test_layout_store_tabs_save_load(main_window: MainWindow) -> None:
    layout_store = main_window.container.resolve(LayoutStore)
    workspace_manager = main_window.container.resolve(WorkspaceManager)
    
    workspace_manager.open_tab("test", {"title": "Test Tab 1", "data": "value1"})
    workspace_manager.open_tab("test", {"title": "Test Tab 2", "data": "value2"})
    QTest.qWait(50)
    
    tabs = workspace_manager.get_tab_contexts()
    assert len(tabs) >= 2
    
    layout_store.save_tabs(tabs)
    loaded_tabs = layout_store.load_tabs()
    
    assert len(loaded_tabs) >= 2
    assert loaded_tabs[0]["module_id"] == tabs[0]["module_id"]


def test_close_event_saves_layout(main_window: MainWindow, qtbot: Any) -> None:
    layout_store = main_window.container.resolve(LayoutStore)
    initial_state = main_window.saveState()
    
    main_window.close()
    
    saved_state = layout_store.load_layout()
    assert saved_state is not None


def test_main_window_without_container_raises() -> None:
    with pytest.raises(Exception):
        MainWindow(None)
