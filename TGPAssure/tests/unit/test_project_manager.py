from __future__ import annotations

import pytest
import tempfile
import shutil
import uuid
from pathlib import Path
from datetime import datetime, timezone

from PySide6.QtCore import QCoreApplication

from core.data_access.db_engine import DatabaseEngine
from core.data_access.project_repository import ProjectRepository
from core.infrastructure.service_container import ServiceContainer
from modules.project.project_manager import ProjectManager, RecentProjectsStore
from core.domain.project import Project


@pytest.fixture
def app() -> QCoreApplication:
    return QCoreApplication.instance() or QCoreApplication([])


@pytest.fixture
def temp_dir() -> Path:
    path = Path(tempfile.mkdtemp())
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def app_db_path(temp_dir: Path) -> Path:
    return temp_dir / "app.db"


@pytest.fixture
def app_db_engine(app_db_path: Path) -> DatabaseEngine:
    return DatabaseEngine(app_db_path)


@pytest.fixture
def container(app: QCoreApplication, app_db_engine: DatabaseEngine) -> ServiceContainer:
    container = ServiceContainer()
    container.register(DatabaseEngine, app_db_engine)
    return container


@pytest.fixture
def project_manager(app: QCoreApplication, container: ServiceContainer) -> ProjectManager:
    return ProjectManager(container)


def test_create_project(project_manager: ProjectManager, temp_dir: Path) -> None:
    project = project_manager.create("TestProject", temp_dir)
    
    assert project.name == "TestProject"
    assert project.root_folder_path == temp_dir / "TestProject"
    migration_dir = Path(__file__).resolve().parents[2] / "migrations"
    latest_schema = max(int(path.name[:4]) for path in migration_dir.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    assert project.schema_version == latest_schema
    
    project_path = temp_dir / "TestProject" / "TestProject.tgp-project"
    assert project_path.exists()
    
    raw_dir = temp_dir / "TestProject" / "raw"
    assert raw_dir.exists()
    assert (raw_dir / "seismic").exists()
    assert (raw_dir / "magnetic").exists()
    assert (raw_dir / "gravity").exists()
    assert (raw_dir / "em").exists()
    
    assert (temp_dir / "TestProject" / "derived").exists()
    assert (temp_dir / "TestProject" / "exports").exists()
    assert (temp_dir / "TestProject" / "reports").exists()
    assert (temp_dir / "TestProject" / "logs").exists()
    assert (temp_dir / "TestProject" / "backups").exists()
    assert (temp_dir / "TestProject" / ".autosave").exists()


def test_recent_projects_store(app_db_engine: DatabaseEngine) -> None:
    store = RecentProjectsStore(app_db_engine)
    
    store.add("/path/to/project1.tgp", "Project 1")
    store.add("/path/to/project2.tgp", "Project 2")
    store.add("/path/to/project1.tgp", "Project 1")
    
    recent = store.get_all(10)
    assert len(recent) == 2
    assert recent[0]["path"] == "/path/to/project1.tgp"
    assert recent[0]["open_count"] == 2


def test_project_manager_open(project_manager: ProjectManager, temp_dir: Path) -> None:
    project = project_manager.create("OpenTest", temp_dir)
    project_path = temp_dir / "OpenTest" / "OpenTest.tgp-project"
    
    opened = project_manager.open(project_path)
    assert opened.name == "OpenTest"
    assert opened.id == project.id


def test_project_manager_close(project_manager: ProjectManager, temp_dir: Path) -> None:
    project_manager.create("CloseTest", temp_dir)
    assert project_manager.get_current_project() is not None
    
    project_manager.close()
    assert project_manager.get_current_project() is None


def test_get_recent_projects(project_manager: ProjectManager, temp_dir: Path) -> None:
    project_manager.create("Recent1", temp_dir)
    project_manager.create("Recent2", temp_dir)
    
    recent = project_manager.get_recent_projects()
    assert len(recent) == 2
    assert recent[0]["name"] == "Recent2"


def test_project_initialization_creates_all_dirs(project_manager: ProjectManager, temp_dir: Path) -> None:
    project = project_manager.create("TestProject", temp_dir)
    project_path = temp_dir / "TestProject"
    
    assert (project_path / "raw").exists()
    assert (project_path / "derived").exists()
    assert (project_path / "exports").exists()
    assert (project_path / "reports").exists()
    assert (project_path / "logs").exists()
    assert (project_path / "backups").exists()
    assert (project_path / ".autosave").exists()


def test_project_manager_signals(project_manager: ProjectManager, temp_dir: Path, qtbot: Any) -> None:
    created_signal = []
    opened_signal = []
    closed_signal = []
    
    project_manager.project_created.connect(lambda p: created_signal.append(p))
    project_manager.project_opened.connect(lambda p: opened_signal.append(p))
    project_manager.project_closed.connect(lambda: closed_signal.append(True))
    
    project = project_manager.create("SignalTest", temp_dir)
    assert len(created_signal) == 1
    assert len(opened_signal) == 1
    
    project_manager.close()
    assert len(closed_signal) == 1