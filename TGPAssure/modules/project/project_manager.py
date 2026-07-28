from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal

from core.data_access.db_engine import DatabaseEngine
from core.data_access.project_repository import ProjectRepository
from core.domain.project import Project, ProjectFile
from core.infrastructure.service_container import ServiceContainer
from modules.project.project_migrator import ProjectMigrator


class RecentProjectsStore:
    """Small global index of projects recently opened by the application."""

    def __init__(self, db_engine: DatabaseEngine) -> None:
        self._db_engine = db_engine
        self._init_table()

    def _init_table(self) -> None:
        conn = self._db_engine.get_write_connection()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS recent_projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_path TEXT NOT NULL UNIQUE,
                    project_name TEXT NOT NULL,
                    last_opened TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    open_count INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def add(self, project_path: str, project_name: str) -> None:
        conn = self._db_engine.get_write_connection()
        try:
            # SQLite CURRENT_TIMESTAMP is only second-resolution; explicit UTC
            # microseconds keep rapid successive opens in the correct MRU order.
            opened_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
            conn.execute(
                "INSERT INTO recent_projects (project_path, project_name, last_opened) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(project_path) DO UPDATE SET "
                "project_name = excluded.project_name, last_opened = excluded.last_opened, "
                "open_count = open_count + 1",
                (project_path, project_name, opened_at),
            )
            conn.commit()
        finally:
            conn.close()

    def get_all(self, limit: int = 10) -> List[Dict[str, Any]]:
        conn = self._db_engine.get_read_connection()
        try:
            rows = conn.execute(
                "SELECT project_path, project_name, last_opened, open_count "
                "FROM recent_projects ORDER BY last_opened DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [
                {
                    "path": row["project_path"],
                    "name": row["project_name"],
                    "last_opened": row["last_opened"],
                    "open_count": row["open_count"],
                }
                for row in rows
            ]
        finally:
            conn.close()

    def clear(self) -> None:
        conn = self._db_engine.get_write_connection()
        try:
            conn.execute("DELETE FROM recent_projects")
            conn.commit()
        finally:
            conn.close()


class ProjectManager(QObject):
    """Owns the authoritative project database and on-disk project structure.

    The previous implementation created a small, separate schema and later tried
    to migrate it as though it had been created by the normal migration chain.
    This implementation always creates and opens projects through the same SQL
    migrations, so QC, processing, reporting and visualization modules see an
    identical schema.
    """

    project_created = Signal(object)
    project_opened = Signal(object)
    project_closed = Signal()
    project_updated = Signal(object)
    file_imported = Signal(object)
    file_removed = Signal(str)

    def __init__(self, container: ServiceContainer) -> None:
        super().__init__()
        self._container = container
        self._db_engine = container.resolve(DatabaseEngine)
        self._recent_store = RecentProjectsStore(self._db_engine)
        self._current_project: Optional[Project] = None
        self._project_path: Optional[Path] = None
        self._project_db_engine: Optional[DatabaseEngine] = None

    @staticmethod
    def _ensure_project_directories(project_folder: Path) -> None:
        relative_directories = (
            "raw/seismic",
            "raw/magnetic",
            "raw/gravity/observations",
            "raw/gravity/base",
            "raw/gravity/terrain",
            "raw/gravity/reference",
            "raw/electrical/resistivity",
            "raw/electrical/ip",
            "raw/electrical/sp",
            "raw/electrical/potential_mapping",
            "raw/electrical/telluric",
            "raw/em",
            "derived/seismic",
            "derived/magnetic",
            "derived/gravity/corrections",
            "derived/gravity/bouguer",
            "derived/gravity/grids",
            "derived/gravity/derivatives",
            "derived/electrical/processed",
            "derived/electrical/qc",
            "derived/electrical/grids",
            "derived/em",
            "exports/seismic",
            "exports/magnetic",
            "exports/gravity",
            "exports/electrical",
            "exports/em",
            "reports/seismic",
            "reports/magnetic",
            "reports/gravity",
            "reports/electrical",
            "reports/em",
            "logs",
            "backups",
            ".autosave",
        )
        for relative in relative_directories:
            (project_folder / relative).mkdir(parents=True, exist_ok=True)

    def create(self, name: str, root_folder_path: Path) -> Project:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Project name cannot be empty")

        root_folder_path = Path(root_folder_path).expanduser().resolve()
        project_folder = root_folder_path / clean_name
        project_folder.mkdir(parents=True, exist_ok=True)
        self._ensure_project_directories(project_folder)

        db_path = project_folder / f"{clean_name}.tgp-project"
        if db_path.exists() and db_path.stat().st_size > 0:
            raise FileExistsError(f"A project already exists at: {db_path}")

        project_db_engine = DatabaseEngine(db_path)
        migrator = ProjectMigrator(project_db_engine)
        migrator.migrate()

        project_repo = ProjectRepository(project_db_engine)
        project = project_repo.get_by_id()
        if project is None:
            raise RuntimeError("Project migrations completed without creating the project record")

        now = datetime.now(timezone.utc)
        project.project_uuid = str(uuid.uuid4())
        project.name = clean_name
        project.root_folder_path = project_folder
        project.root_path = project_folder
        project.database_path = db_path
        project.schema_version = migrator.get_current_version()
        project.created_at = now
        project.modified_at = now
        project.last_opened_at = now
        project_repo.update(project)

        self._activate_project(project, db_path, project_db_engine)
        self._recent_store.add(str(db_path), project.name)
        self.project_created.emit(project)
        self.project_opened.emit(project)
        return project

    def open(self, project_path: Path) -> Project:
        project_path = Path(project_path).expanduser().resolve()
        if not project_path.exists():
            raise FileNotFoundError(f"Project file not found: {project_path}")

        project_db_engine = DatabaseEngine(project_path)
        migrator = ProjectMigrator(project_db_engine)
        migrator.migrate()

        project_repo = ProjectRepository(project_db_engine)
        project = project_repo.get_by_id()
        if project is None:
            raise ValueError(f"Invalid project file: {project_path}")

        now = datetime.now(timezone.utc)
        project.schema_version = migrator.get_current_version()
        project.database_path = project_path
        project.root_folder_path = project_path.parent
        project.root_path = project_path.parent
        project.last_opened_at = now
        project.modified_at = now
        project_repo.update(project)
        self._ensure_project_directories(project_path.parent)

        self._activate_project(project, project_path, project_db_engine)
        self._recent_store.add(str(project_path), project.name)
        self.project_opened.emit(project)
        return project

    def _activate_project(
        self,
        project: Project,
        project_path: Path,
        project_db_engine: DatabaseEngine,
    ) -> None:
        self._current_project = project
        self._project_path = project_path
        self._project_db_engine = project_db_engine

    def close(self) -> None:
        if self._current_project is None:
            return
        self._current_project = None
        self._project_path = None
        self._project_db_engine = None
        self.project_closed.emit()

    def get_current_project(self) -> Optional[Project]:
        return self._current_project

    def get_project_path(self) -> Optional[Path]:
        return self._project_path

    def get_project_database_engine(self) -> Optional[DatabaseEngine]:
        return self._project_db_engine

    def _active_repo(self) -> Optional[ProjectRepository]:
        if self._project_db_engine is None:
            return None
        return ProjectRepository(self._project_db_engine)

    def get_files(self) -> List[ProjectFile]:
        repo = self._active_repo()
        return repo.list_files() if repo is not None else []

    def get_file(self, file_uuid: str) -> Optional[ProjectFile]:
        repo = self._active_repo()
        return repo.get_file_by_uuid(file_uuid) if repo is not None else None

    def remove_file(self, file_uuid: str, *, delete_managed_copy: bool = False) -> bool:
        repo = self._active_repo()
        if repo is None:
            return False
        project_file = repo.get_file_by_uuid(file_uuid)
        result = repo.delete_file(file_uuid)
        if result and delete_managed_copy and project_file and self._current_project:
            candidate = self._current_project.root_folder_path / project_file.relative_path
            try:
                if candidate.is_file() and self._current_project.root_folder_path in candidate.resolve().parents:
                    candidate.unlink()
            except OSError:
                pass
        if result:
            self.file_removed.emit(file_uuid)
        return result

    def backup(self, destination: Path | None = None) -> Path:
        if self._project_path is None or self._project_db_engine is None:
            raise RuntimeError("No project is currently open")
        conn = self._project_db_engine.get_write_connection()
        try:
            conn.execute("PRAGMA wal_checkpoint(FULL)")
        finally:
            conn.close()
        destination = destination or (
            self._project_path.parent
            / "backups"
            / f"{self._project_path.stem}.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}{self._project_path.suffix}"
        )
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self._project_path, destination)
        return destination

    def get_recent_projects(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self._recent_store.get_all(limit)

    def add_recent_project(self, path: str, name: str) -> None:
        self._recent_store.add(path, name)
