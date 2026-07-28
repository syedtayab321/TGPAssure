from __future__ import annotations

import hashlib
import json
import mimetypes
import shutil
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import QLabel, QWidget

from core.data_access.db_engine import DatabaseEngine
from core.infrastructure.service_container import ServiceContainer
from modules.project.project_manager import ProjectManager


@dataclass
class WorkspaceTab:
    tab_id: str
    module_id: str
    widget: QWidget
    context: Dict[str, Any] = field(default_factory=dict)
    title: str = "Untitled"


@dataclass
class ImportedProjectFile:
    source_path: Path
    managed_path: Path
    relative_path: str
    module: str
    sha256: str
    size_bytes: int
    file_uuid: str


class WorkspaceManager(QObject):
    """Authoritative project/session manager used by the main application.

    ProjectManager owns the on-disk project database and migration lifecycle;
    WorkspaceManager adds UI tab/session persistence and managed-file import.
    """

    tab_changed = Signal(WorkspaceTab)
    tab_closed = Signal(str)
    tab_created = Signal(WorkspaceTab)
    project_state_changed = Signal()
    file_imported = Signal(object)

    def __init__(self, container: ServiceContainer) -> None:
        super().__init__()
        self.container = container
        self._db_engine = container.resolve(DatabaseEngine)
        self._project_manager = ProjectManager(container)
        self._tabs: Dict[str, WorkspaceTab] = {}
        self._active_tab_id: Optional[str] = None
        self._tab_handlers: Dict[str, Callable[[WorkspaceTab], None]] = {}
        self._current_project_file: Path | None = None
        self._current_project_root: Path | None = None
        self._dirty = False

    @property
    def current_project_file(self) -> Path | None:
        return self._current_project_file

    @property
    def current_project_root(self) -> Path | None:
        return self._current_project_root

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def create_project(self, name: str, root_folder_path: Path, metadata: Dict[str, Any] | None = None) -> Any:
        project = self._project_manager.create(name, Path(root_folder_path))
        self._current_project_file = Path(project.database_path)
        self._current_project_root = Path(project.root_folder_path)
        self._ensure_extended_folders(self._current_project_root)
        if metadata:
            self._write_metadata(dict(metadata))
        self._create_project_tab(project.name, self._current_project_root)
        self._dirty = True
        self.save_project()
        self.project_state_changed.emit()
        return project

    def open_project(self, project_path: Path) -> Any:
        project = self._project_manager.open(Path(project_path))
        self._current_project_file = Path(project_path).resolve()
        self._current_project_root = self._current_project_file.parent
        self._ensure_extended_folders(self._current_project_root)
        self._restore_workspace_state()
        self._create_project_tab(project.name, self._current_project_root)
        self._dirty = False
        self.project_state_changed.emit()
        return project

    def open_recent_project(self, project_path: str) -> None:
        self.open_project(Path(project_path))

    def get_recent_projects(self) -> List[str]:
        return [entry["path"] for entry in self._project_manager.get_recent_projects(5)]

    def get_project_file(self, file_uuid: str):
        """Return a file registered in the active project database."""
        return self._project_manager.get_file(file_uuid)

    def resolve_project_file_path(self, file_uuid: str) -> Path | None:
        """Resolve a registered project file to its managed absolute path."""
        project_file = self.get_project_file(file_uuid)
        if project_file is None or self._current_project_root is None:
            return None
        relative = Path(project_file.relative_path)
        candidate = (self._current_project_root / relative).resolve()
        root = self._current_project_root.resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return None
        return candidate if candidate.is_file() else None

    def create_new_project(self) -> None:
        self.create_project("Untitled Project", Path.home() / "Documents")

    def save_project(self) -> Path:
        if self._current_project_file is None or self._current_project_root is None:
            raise RuntimeError("No project is currently open")
        state = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "project_file": str(self._current_project_file),
            "active_tab_id": self._active_tab_id,
            "tabs": self.get_tab_contexts(),
        }
        state_path = self._current_project_root / "workspace_state.json"
        temp_path = state_path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
        temp_path.replace(state_path)
        self._checkpoint_project_db()
        self._write_autosave_snapshot(state)
        self._dirty = False
        self.project_state_changed.emit()
        return state_path

    def backup_project(self) -> Path:
        if self._current_project_file is None or self._current_project_root is None:
            raise RuntimeError("No project is currently open")
        self._checkpoint_project_db()
        backup_dir = self._current_project_root / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = backup_dir / f"{self._current_project_file.stem}_{stamp}{self._current_project_file.suffix}"
        shutil.copy2(self._current_project_file, target)
        return target

    def import_file(
        self,
        path: str | Path,
        module_hint: str | None = None,
        role: str = "imported",
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> ImportedProjectFile:
        if self._current_project_root is None or self._current_project_file is None:
            raise RuntimeError("Open or create a project before importing data")
        source = Path(path).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        module = module_hint or self._detect_module(source)
        destination_dir = self._managed_raw_directory(module, source, role)
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = self._unique_destination(destination_dir / source.name)
        sha256, size_bytes = self._copy_with_hash(source, destination, progress_callback)
        relative = destination.relative_to(self._current_project_root).as_posix()
        file_uuid = str(uuid.uuid4())
        mime_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        project_db = DatabaseEngine(self._current_project_file)
        conn = project_db.get_write_connection()
        try:
            conn.execute(
                """INSERT INTO project_files
                (project_id, file_uuid, module, file_role, original_name, display_name, absolute_path,
                 relative_path, extension, mime_type, size_bytes, sha256, status, metadata_json,
                 imported_at, last_verified_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'available', ?, ?, ?)""",
                (
                    file_uuid, module, role, source.name, source.stem, str(destination), relative,
                    source.suffix.lower(), mime_type, size_bytes, sha256,
                    json.dumps({"source_original_path": str(source), "managed_copy": True}),
                    datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
        except Exception:
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        finally:
            conn.close()
        record = ImportedProjectFile(source, destination, relative, module, sha256, size_bytes, file_uuid)
        self._dirty = True
        self.file_imported.emit(record)
        self.project_state_changed.emit()
        return record

    def open_tab(self, module_id: str, context: Dict[str, Any]) -> str:
        tab_id = str(uuid.uuid4())
        widget = QLabel(f"Module: {module_id}")
        widget.setAlignment(Qt.AlignCenter)
        title = context.get("title", module_id)
        tab = WorkspaceTab(tab_id, module_id, widget, context, title)
        self._add_tab(tab)
        return tab_id

    def close_tab(self, tab_id: str) -> None:
        if tab_id in self._tabs:
            if tab_id == self._active_tab_id:
                self._active_tab_id = None
            del self._tabs[tab_id]
            self._dirty = True
            self.tab_closed.emit(tab_id)
            self.project_state_changed.emit()

    def activate_tab(self, tab_id: str) -> None:
        if tab_id in self._tabs:
            self._active_tab_id = tab_id
            self.tab_changed.emit(self._tabs[tab_id])

    def restore_tab(self, tab_data: Dict[str, Any]) -> None:
        tab_id = str(tab_data.get("tab_id") or uuid.uuid4())
        module_id = str(tab_data.get("module_id") or "project")
        context = dict(tab_data.get("context") or {})
        title = str(tab_data.get("title") or context.get("title") or module_id)
        widget = QLabel(f"Restored: {title}")
        widget.setAlignment(Qt.AlignCenter)
        self._add_tab(WorkspaceTab(tab_id, module_id, widget, context, title))

    def get_tab_contexts(self) -> List[Dict[str, Any]]:
        return [
            {"tab_id": tab_id, "module_id": tab.module_id, "context": tab.context, "title": tab.title}
            for tab_id, tab in self._tabs.items()
        ]

    def get_active_tab(self) -> Optional[WorkspaceTab]:
        return self._tabs.get(self._active_tab_id) if self._active_tab_id else None

    def register_tab_handler(self, module_id: str, handler: Callable[[WorkspaceTab], None]) -> None:
        self._tab_handlers[module_id] = handler

    def _add_tab(self, tab: WorkspaceTab) -> None:
        self._tabs[tab.tab_id] = tab
        self._active_tab_id = tab.tab_id
        self._dirty = True
        self.tab_created.emit(tab)
        self.tab_changed.emit(tab)

    def _create_project_tab(self, name: str, root: Path) -> None:
        # Avoid accumulating duplicate project placeholder tabs.
        for tab_id in [key for key, value in self._tabs.items() if value.module_id == "project"]:
            self._tabs.pop(tab_id, None)
        widget = QLabel(f"Project: {name}\nLocation: {root}")
        widget.setAlignment(Qt.AlignCenter)
        tab = WorkspaceTab(str(uuid.uuid4()), "project", widget, {"project_name": name, "project_path": str(root)}, name)
        self._add_tab(tab)

    @staticmethod
    def _ensure_extended_folders(root: Path) -> None:
        folders = (
            "raw/seismic", "raw/magnetic/rover", "raw/magnetic/base", "raw/magnetic/boundaries",
            "raw/gravity/observations", "raw/gravity/base", "raw/gravity/terrain", "raw/gravity/reference",
            "raw/electrical/resistivity", "raw/electrical/ip", "raw/electrical/sp", "raw/electrical/potential_mapping", "raw/electrical/telluric",
            "raw/em", "derived/seismic", "derived/magnetic/corrections", "derived/magnetic/leveled", "derived/magnetic/grids", "derived/magnetic/targets",
            "derived/gravity/corrections", "derived/gravity/bouguer", "derived/gravity/grids", "derived/gravity/derivatives",
            "derived/electrical/processed", "derived/electrical/qc", "derived/electrical/grids",
            "exports/seismic", "exports/magnetic", "exports/gravity", "exports/electrical", "exports/em",
            "reports/seismic", "reports/magnetic", "reports/gravity", "reports/electrical", "reports/em",
            "cache/magnetic", "cache/gravity", "cache/electrical", "logs", "backups", ".autosave",
        )
        for relative in folders:
            (root / relative).mkdir(parents=True, exist_ok=True)

    def _write_metadata(self, metadata: dict[str, Any]) -> None:
        if self._current_project_root is None:
            return
        payload = dict(metadata)
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        (self._current_project_root / "project_metadata.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    def _restore_workspace_state(self) -> None:
        if self._current_project_root is None:
            return
        path = self._current_project_root / "workspace_state.json"
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        # Only restore lightweight module contexts; heavy file viewers are reopened explicitly.
        for entry in data.get("tabs", []):
            if entry.get("module_id") not in {"project"}:
                continue
            try:
                self.restore_tab(entry)
            except Exception:
                continue

    def _checkpoint_project_db(self) -> None:
        if self._current_project_file is None:
            return
        conn = sqlite3.connect(str(self._current_project_file))
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.commit()
        finally:
            conn.close()

    def _write_autosave_snapshot(self, state: dict[str, Any]) -> None:
        if self._current_project_root is None:
            return
        path = self._current_project_root / ".autosave" / "workspace_state.latest.json"
        path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")

    @staticmethod
    def _detect_module(path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix in {".sgy", ".segy", ".segd", ".sgd", ".d", ".seg2", ".segb"}:
            return "seismic"
        name = path.name.lower()
        if "grav" in name:
            return "gravity"
        if any(token in name for token in ("mag", "rover", "base_station")):
            return "magnetic"
        if any(token in name for token in ("ert", "resist", "ip", "tdip", "fdip", "sip", "ves", "sp_")):
            return "electrical"
        return "general"

    def _managed_raw_directory(self, module: str, path: Path, role: str) -> Path:
        assert self._current_project_root is not None
        if module == "gravity":
            sub = "base" if "base" in role.lower() or "base" in path.stem.lower() else "observations"
            return self._current_project_root / "raw" / "gravity" / sub
        if module == "magnetic":
            sub = "base" if "base" in role.lower() or "base" in path.stem.lower() else "rover"
            return self._current_project_root / "raw" / "magnetic" / sub
        if module == "electrical":
            return self._current_project_root / "raw" / "electrical" / "resistivity"
        return self._current_project_root / "raw" / module

    @staticmethod
    def _unique_destination(path: Path) -> Path:
        if not path.exists():
            return path
        for index in range(1, 10_000):
            candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
            if not candidate.exists():
                return candidate
        raise RuntimeError(f"Unable to allocate a unique import name for {path.name}")

    @staticmethod
    def _copy_with_hash(
        source: Path,
        destination: Path,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> tuple[str, int]:
        digest = hashlib.sha256()
        copied = 0
        total = max(1, int(source.stat().st_size))
        temporary = destination.with_name(destination.name + ".part")
        temporary.unlink(missing_ok=True)
        try:
            with source.open("rb") as src, temporary.open("wb") as dst:
                while True:
                    block = src.read(4 * 1024 * 1024)
                    if not block:
                        break
                    dst.write(block)
                    digest.update(block)
                    copied += len(block)
                    if progress_callback is not None:
                        progress_callback(
                            min(100, int(round(copied * 100 / total))),
                            f"Copying and verifying {source.name} — {copied / (1024**2):.1f} / {total / (1024**2):.1f} MB",
                        )
            shutil.copystat(source, temporary)
            temporary.replace(destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return digest.hexdigest(), copied
