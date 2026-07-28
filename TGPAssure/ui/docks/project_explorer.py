from __future__ import annotations

from typing import Callable, Optional
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QModelIndex, QAbstractItemModel, QObject, QFileInfo
from PySide6.QtGui import QIcon, QDragEnterEvent, QDropEvent, QAction, QStandardItem, QStandardItemModel, QDesktopServices
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QTreeWidget, QTreeWidgetItem,
    QLabel, QMenu, QFileIconProvider, QTreeWidgetItemIterator, QDockWidget,
    QTreeView, QHeaderView, QMessageBox, QFileDialog, QPushButton, QSizePolicy
)
from PySide6.QtCore import QUrl

from modules.project.project_manager import ProjectManager
from core.domain.project import ProjectFile
from ui.icons import get_icon, icon_for_extension, icon_color


class ProjectExplorer(QWidget):
    file_selected = Signal(str)
    run_qc_requested = Signal(str)
    import_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setObjectName('projectExplorerPanel')
        # Force an opaque white dock body.  Without WA_StyledBackground Qt can
        # leave custom QWidget dock contents visually transparent and expose
        # the grey workspace/dock background underneath.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.setStyleSheet("""
            QWidget#projectExplorerPanel {
                background-color: #FFFFFF;
            }
            QWidget#projectExplorerPanel QLabel {
                background-color: transparent;
                color: #1F1F1F;
            }
            QWidget#projectExplorerPanel QLineEdit {
                background-color: #FFFFFF;
                color: #1F1F1F;
            }
            QWidget#projectExplorerPanel QTreeWidget {
                background-color: #FFFFFF;
                alternate-background-color: #FAFAFA;
                color: #1F1F1F;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(3)

        header = QHBoxLayout()
        header.setSpacing(6)
        self.title_label = QLabel('No Project')
        self.title_label.setObjectName('explorerTitle')
        upload = QPushButton('Import')
        upload.setProperty('variant', 'primary')
        upload.setIcon(get_icon('document-import', color='#FFFFFF', size=13))
        upload.setToolTip('Upload Data')
        upload.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        upload.setStyleSheet("""
            QPushButton[variant="primary"] {
                background: #106EBE;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
                font-weight: 600;
                font-size: 10px;
            }
            QPushButton[variant="primary"]:hover {
                background: #0D5C9E;
            }
        """)
        upload.clicked.connect(self.import_requested.emit)
        upload.setEnabled(False)
        self.upload_button = upload
        header.addWidget(self.title_label, 1)
        header.addWidget(upload, 0)
        layout.addLayout(header)

        search_bar = QLineEdit()
        search_bar.setObjectName('explorerSearch')
        search_bar.setPlaceholderText('Filter project tree')
        search_bar.setClearButtonEnabled(True)
        search_bar.textChanged.connect(self._on_search)
        layout.addWidget(search_bar)

        self.tree = QTreeWidget()
        self.tree.setObjectName('explorerTree')
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(16)
        self.tree.setAnimated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setTextElideMode(Qt.ElideRight)
        self.tree.setAlternatingRowColors(True)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.tree, 1)

        self._icon_provider = QFileIconProvider()

    def add_project(self, project_path: str):
        project = Path(project_path)
        self.title_label.setText(project.name or "Project")
        self.upload_button.setEnabled(True)
        root = QTreeWidgetItem(self.tree, [project.name])
        root.setIcon(0, get_icon('folder', color=icon_color('folder'), size=15))
        root.setToolTip(0, project_path)
        root.setData(0, Qt.UserRole, {'path': project_path, 'type': 'project'})
        data_folder = QTreeWidgetItem(root, ['Data'])
        data_folder.setIcon(0, get_icon('folder', color=icon_color('folder'), size=15))
        data_folder.setData(0, Qt.UserRole, {'path': project_path, 'type': 'folder'})
        self._populate_managed_files(data_folder, Path(project_path))
        magnetic_root = Path(project_path) / 'raw' / 'magnetic'
        if magnetic_root.exists():
            magnetic = QTreeWidgetItem(root, ['Magnetic'])
            magnetic.setIcon(0, get_icon('office-chart-line', color=icon_color('office-chart-line'), size=15))
            magnetic.setData(0, Qt.UserRole, {'path': str(magnetic_root), 'type': 'folder', 'module': 'magnetic'})
            for label, relative in (
                ('Raw Rover Data', 'raw/magnetic/rover'),
                ('Base Station Data', 'raw/magnetic/base'),
                ('Boundaries', 'raw/magnetic/boundaries'),
                ('Corrected Data', 'derived/magnetic/corrections'),
                ('Leveled Data', 'derived/magnetic/leveled'),
                ('Grids', 'derived/magnetic/grids'),
                ('Targets', 'derived/magnetic/targets'),
                ('Reports', 'reports/magnetic'),
            ):
                child_path = Path(project_path) / relative
                child = QTreeWidgetItem(magnetic, [label])
                child.setIcon(0, get_icon('folder', color=icon_color('folder'), size=14))
                child.setData(0, Qt.UserRole, {'path': str(child_path), 'type': 'folder', 'module': 'magnetic'})
            magnetic.setExpanded(True)
        electrical_root = Path(project_path) / 'raw' / 'electrical'
        if electrical_root.exists():
            electrical = QTreeWidgetItem(root, ['Electrical'])
            electrical.setIcon(0, get_icon('electrical', color=icon_color('electrical'), size=15))
            electrical.setData(0, Qt.UserRole, {'path': str(electrical_root), 'type': 'folder', 'module': 'electrical'})
            for label, relative in (
                ('Resistivity / ERT / VES', 'raw/electrical/resistivity'),
                ('Induced Polarization', 'raw/electrical/ip'),
                ('Self-Potential', 'raw/electrical/sp'),
                ('MALM / Equipotential', 'raw/electrical/potential_mapping'),
                ('Telluric', 'raw/electrical/telluric'),
                ('Processed Data', 'derived/electrical/processed'),
                ('QC Products', 'derived/electrical/qc'),
                ('Grids / Maps', 'derived/electrical/grids'),
                ('Exports', 'exports/electrical'),
                ('Reports', 'reports/electrical'),
            ):
                child_path = Path(project_path) / relative
                child = QTreeWidgetItem(electrical, [label])
                child.setIcon(0, get_icon('folder', color=icon_color('folder'), size=14))
                child.setData(0, Qt.UserRole, {'path': str(child_path), 'type': 'folder', 'module': 'electrical'})
            electrical.setExpanded(True)
        gravity_root = Path(project_path) / 'raw' / 'gravity'
        if gravity_root.exists():
            gravity = QTreeWidgetItem(root, ['Gravity'])
            gravity.setIcon(0, get_icon('view-statistics', color=icon_color('view-statistics'), size=15))
            gravity.setData(0, Qt.UserRole, {'path': str(gravity_root), 'type': 'folder', 'module': 'gravity'})
            for label, relative in (
                ('Raw Observations', 'raw/gravity/observations'),
                ('Base Station Data', 'raw/gravity/base'),
                ('Terrain / DEM Inputs', 'raw/gravity/terrain'),
                ('Regional Reference', 'raw/gravity/reference'),
                ('Corrected Data', 'derived/gravity/corrections'),
                ('Bouguer Products', 'derived/gravity/bouguer'),
                ('Grids', 'derived/gravity/grids'),
                ('Reports', 'reports/gravity'),
            ):
                child_path = Path(project_path) / relative
                child = QTreeWidgetItem(gravity, [label])
                child.setIcon(0, get_icon('folder', color=icon_color('folder'), size=14))
                child.setData(0, Qt.UserRole, {'path': str(child_path), 'type': 'folder', 'module': 'gravity'})
            gravity.setExpanded(True)
        root.setExpanded(True)

    def _populate_managed_files(self, parent: QTreeWidgetItem, project_root: Path) -> None:
        raw_root = project_root / "raw"
        if not raw_root.is_dir():
            return
        files = sorted((path for path in raw_root.rglob("*") if path.is_file()), key=lambda p: str(p).lower())
        for path in files:
            item = QTreeWidgetItem(parent, [path.name])
            info = QFileInfo(str(path))
            native_icon = self._icon_provider.icon(info)
            item.setIcon(0, native_icon if not native_icon.isNull() else icon_for_extension(info.suffix()))
            item.setToolTip(0, str(path))
            item.setData(0, Qt.UserRole, {"path": str(path), "type": "file"})
        if files:
            parent.setExpanded(True)

    def add_file(self, file_path: str) -> None:
        if self.tree.topLevelItemCount() == 0:
            self.add_project(str(Path(file_path).parent))
        root = self.tree.topLevelItem(0)
        data_folder = root.child(0)
        item = QTreeWidgetItem(data_folder, [Path(file_path).name])
        info = QFileInfo(file_path)
        native_icon = self._icon_provider.icon(info)
        item.setIcon(0, native_icon if not native_icon.isNull() else icon_for_extension(info.suffix()))
        item.setToolTip(0, file_path)
        item.setData(0, Qt.UserRole, {'path': file_path, 'type': 'file'})
        data_folder.setExpanded(True)

    def clear(self):
        self.tree.clear()
        self.title_label.setText("No Project")
        self.upload_button.setEnabled(False)

    def _on_item_clicked(self, item: QTreeWidgetItem, col: int):
        data = item.data(0, Qt.UserRole)
        if data and 'path' in data:
            self.file_selected.emit(data['path'])

    def _on_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background: white; border: 1px solid #D1D9E0; border-radius: 4px; padding: 4px 0; }
            QMenu::item { padding: 5px 20px 5px 10px; color: #102A43; }
            QMenu::item:selected { background: #E5F1FB; }
            QMenu::separator { height: 1px; background: #E2E8F0; margin: 4px 8px; }
        """)
        if item:
            data = item.data(0, Qt.UserRole) or {}
            path = Path(str(data.get("path", ""))) if data.get("path") else None
            is_file = bool(path and path.is_file())
            open_act = menu.addAction("Open")
            open_act.setEnabled(is_file)
            import_act = menu.addAction("Import…")
            run_qc = menu.addAction("Run QC")
            run_qc.setEnabled(is_file)
            view_res = menu.addAction("View QC History")
            gen_report = menu.addAction("Generate Report")
            gen_report.setEnabled(is_file)
            export_act = menu.addAction("Export / Copy…")
            export_act.setEnabled(is_file)
            menu.addSeparator()
            details_act = menu.addAction("Details…")
            delete_act = menu.addAction("Remove from Tree")
            chosen = menu.exec(self.tree.viewport().mapToGlobal(pos))
            if chosen is open_act and is_file:
                window = self.window(); handler = getattr(window, "open_imported_file", None)
                if callable(handler): handler(str(path))
                else: self.file_selected.emit(str(path))
            elif chosen is import_act:
                self._import_item(item)
            elif chosen is run_qc:
                self._run_qc(item)
            elif chosen is view_res:
                window=self.window(); handler=getattr(window,"_open_qc_history_page",None)
                if callable(handler): handler()
            elif chosen is gen_report:
                self._generate_report(item)
            elif chosen is export_act:
                self._export_item(item)
            elif chosen is details_act:
                self._show_item_details(item)
            elif chosen is delete_act:
                self._delete_item(item)
        else:
            add_proj = menu.addAction('Add Project...')
            if menu.exec(self.tree.viewport().mapToGlobal(pos)) is add_proj:
                self._add_project_dialog()

    def _show_item_details(self, item: QTreeWidgetItem) -> None:
        data = item.data(0, Qt.UserRole) or {}
        path = Path(str(data.get("path", ""))) if data.get("path") else None
        if path is None:
            return
        if path.exists():
            stat = path.stat()
            kind = "Directory" if path.is_dir() else "File"
            size = "—" if path.is_dir() else f"{stat.st_size:,} bytes"
            from datetime import datetime
            modified = datetime.fromtimestamp(stat.st_mtime).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
            message = f"Name: {path.name}\nType: {kind}\nPath: {path}\nSize: {size}\nModified: {modified}"
        else:
            message = f"Name: {item.text(0)}\nPath: {path}\nStatus: Missing from disk"
        QMessageBox.information(self, "Details", message)

    def _add_project_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, 'Select Project Folder')
        if folder:
            self.add_project(folder)

    def _import_item(self, item: QTreeWidgetItem):
        self.import_requested.emit()

    def _run_qc(self, item: QTreeWidgetItem):
        data = item.data(0, Qt.UserRole) or {}
        path = data.get('path')
        if path:
            self.run_qc_requested.emit(path)

    def _view_results(self, item: QTreeWidgetItem):
        window = self.window(); handler = getattr(window, "_open_qc_history_page", None)
        if callable(handler): handler()

    def _generate_report(self, item: QTreeWidgetItem):
        data=item.data(0,Qt.UserRole) or {}; path=Path(str(data.get("path","")))
        if not path.is_file(): return
        window=self.window(); suffix=path.suffix.lower()
        if suffix in {".sgy",".segy"}:
            opener=getattr(window,"_open_segy_file_path",None)
            # Existing SEG-Y reports are generated from a QC run, not raw data.
            history=getattr(window,"_open_qc_history_page",None)
            if callable(history): history()
        elif "grav" in str(path).lower():
            apply=getattr(window,"_apply_to_gravity",None)
            if callable(apply): apply("generate_report","pdf")
        elif suffix in {".csv",".tsv",".txt",".dat",".xyz",".xlsx",".xlsm"}:
            handler=getattr(window,"open_imported_file",None)
            if callable(handler): handler(str(path))
            QMessageBox.information(self,"Generate Report","Run the appropriate module QC first; the report action becomes enabled when a QC result exists.")

    def _export_item(self, item: QTreeWidgetItem):
        data = item.data(0, Qt.UserRole) or {}
        source = Path(str(data.get("path", "")))
        if not source.is_file():
            return
        destination, _ = QFileDialog.getSaveFileName(
            self, "Export Copy", str(Path.home() / source.name),
            f"{source.suffix.upper().lstrip('.')} (*{source.suffix});;All Files (*.*)",
        )
        if not destination:
            return
        target = Path(destination).expanduser()
        window = self.window()
        begin = getattr(window, "begin_busy_task", None)
        update = getattr(window, "update_busy_task", None)
        end_busy = getattr(window, "end_busy_task", None)
        task_id = f"file-export:{source.name}"
        if callable(begin):
            begin(task_id, "Exporting File", f"Copying {source.name}", 0)
        try:
            total = max(1, source.stat().st_size)
            copied = 0
            temporary = target.with_name(target.name + ".part")
            temporary.parent.mkdir(parents=True, exist_ok=True)
            temporary.unlink(missing_ok=True)
            with source.open("rb") as src, temporary.open("wb") as dst:
                while True:
                    block = src.read(4 * 1024 * 1024)
                    if not block:
                        break
                    dst.write(block)
                    copied += len(block)
                    if callable(update):
                        update(task_id, int(copied * 100 / total), f"Copied {copied / (1024**2):.1f} / {total / (1024**2):.1f} MB")
                    from PySide6.QtWidgets import QApplication
                    QApplication.processEvents()
            import shutil
            shutil.copystat(source, temporary)
            temporary.replace(target)
        except Exception as exc:
            try:
                temporary.unlink(missing_ok=True)
            except Exception:
                pass
            QMessageBox.critical(self, "Export File", str(exc))
        finally:
            if callable(end_busy):
                end_busy(task_id)

    def _delete_item(self, item: QTreeWidgetItem):
        reply = QMessageBox.question(
            self, "Remove from Tree",
            "Remove this item from the current tree view? The file on disk will not be deleted.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            parent = item.parent()
            if parent:
                parent.removeChild(item)
            else:
                self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(item))

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        window = self.window()
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.suffix.lower() == ".tgp-project" and path.is_file():
                opener = getattr(window, "open_project_path", None)
                if callable(opener):
                    opener(path)
            elif path.is_file():
                importer = getattr(window, "import_external_path", None)
                if callable(importer):
                    importer(path)
        event.acceptProposedAction()

    def _on_search(self, text: str):
        query = text.strip().lower()

        def apply(item: QTreeWidgetItem) -> bool:
            child_match = any(apply(item.child(i)) for i in range(item.childCount()))
            own_match = not query or query in item.text(0).lower()
            visible = own_match or child_match
            item.setHidden(not visible)
            if query and child_match:
                item.setExpanded(True)
            return visible

        for index in range(self.tree.topLevelItemCount()):
            apply(self.tree.topLevelItem(index))


class ProjectExplorerModel(QStandardItemModel):
    def __init__(self) -> None:
        super().__init__()
        self.setHorizontalHeaderLabels(["Name", "Type", "Size", "Status"])

    def set_files(self, files: list[ProjectFile]) -> None:
        self.clear()
        self.setHorizontalHeaderLabels(["Name", "Type", "Size", "Status"])
        
        modules: dict[str, list[ProjectFile]] = {}
        for file in files:
            if file.module not in modules:
                modules[file.module] = []
            modules[file.module].append(file)
        
        for module_name, module_files in modules.items():
            module_item = QStandardItem(module_name.capitalize())
            module_item.setEditable(False)
            module_item.setIcon(QIcon.fromTheme("folder"))
            
            size_item = QStandardItem("")
            size_item.setEditable(False)
            type_item = QStandardItem("")
            type_item.setEditable(False)
            status_item = QStandardItem("")
            status_item.setEditable(False)
            
            self.appendRow([module_item, type_item, status_item, size_item])
            
            for file in sorted(module_files, key=lambda f: f.original_name):
                file_item = QStandardItem(file.display_name)
                file_item.setEditable(False)
                file_item.setData(file.file_uuid, Qt.UserRole)
                file_item.setData(file.relative_path, Qt.UserRole + 1)
                file_item.setIcon(QIcon.fromTheme("file"))
                
                type_str = file.extension if file.extension else "Unknown"
                type_item_child = QStandardItem(type_str)
                type_item_child.setEditable(False)
                
                size_str = self._format_size(file.size_bytes)
                size_item_child = QStandardItem(size_str)
                size_item_child.setEditable(False)
                
                status_str = file.status.capitalize()
                status_item_child = QStandardItem(status_str)
                status_item_child.setEditable(False)
                
                module_item.appendRow([file_item, type_item_child, size_item_child, status_item_child])

    def _format_size(self, size_bytes: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"


class ProjectExplorerDock(QDockWidget):
    file_double_clicked = Signal(str)

    def __init__(self, project_manager: ProjectManager) -> None:
        super().__init__("Project Explorer")
        self._project_manager = project_manager
        self._project_manager.file_imported.connect(self._on_file_imported)
        self._project_manager.file_removed.connect(self._on_file_removed)
        self._project_manager.project_opened.connect(self._on_project_opened)
        self._project_manager.project_created.connect(self._on_project_opened)
        
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self._tree_view = QTreeView()
        self._tree_view.setHeaderHidden(False)
        self._tree_view.setAlternatingRowColors(True)
        self._tree_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self._tree_view.customContextMenuRequested.connect(self._on_context_menu)
        self._tree_view.doubleClicked.connect(self._on_double_click)
        
        header = self._tree_view.header()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        
        self._model = ProjectExplorerModel()
        self._tree_view.setModel(self._model)
        
        layout.addWidget(self._tree_view)
        self.setWidget(content)
        self.setObjectName("project_explorer_dock")
        
        self._refresh_files()

    def _on_project_opened(self, project) -> None:
        self._refresh_files()

    def _on_file_imported(self, file: ProjectFile) -> None:
        self._refresh_files()

    def _on_file_removed(self, file_uuid: str) -> None:
        self._refresh_files()

    def _refresh_files(self) -> None:
        files = self._project_manager.get_files()
        self._model.set_files(files)

    def _on_double_click(self, index: QModelIndex) -> None:
        item = self._model.itemFromIndex(index)
        if item is None:
            return
        
        file_uuid = item.data(Qt.UserRole)
        if file_uuid:
            self.file_double_clicked.emit(file_uuid)

    def _on_context_menu(self, position) -> None:
        index = self._tree_view.indexAt(position)
        if not index.isValid():
            return
        
        item = self._model.itemFromIndex(index)
        if item is None:
            return
        
        file_uuid = item.data(Qt.UserRole)
        if not file_uuid:
            return
        
        menu = QMenu()
        open_action = menu.addAction("Open")
        reveal_action = menu.addAction("Reveal in Explorer")
        menu.addSeparator()
        properties_action = menu.addAction("Properties")
        menu.addSeparator()
        remove_action = menu.addAction("Remove from Project")
        remove_action.setIcon(QIcon.fromTheme("edit-delete"))
        
        action = menu.exec(self._tree_view.viewport().mapToGlobal(position))
        
        if action == open_action:
            self.file_double_clicked.emit(file_uuid)
        elif action == reveal_action:
            file_obj = self._project_manager.get_file(file_uuid)
            if file_obj:
                project = self._project_manager.get_current_project()
                path = (project.root_folder_path / file_obj.relative_path) if project else Path(file_obj.relative_path)
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))
        elif action == properties_action:
            self._show_properties(file_uuid)
        elif action == remove_action:
            self._remove_file(file_uuid)

    def _show_properties(self, file_uuid: str) -> None:
        file_obj = self._project_manager.get_file(file_uuid)
        if not file_obj:
            return
        
        QMessageBox.information(
            self,
            "File Properties",
            f"Name: {file_obj.original_name}\n"
            f"Display: {file_obj.display_name}\n"
            f"Module: {file_obj.module}\n"
            f"Type: {file_obj.extension}\n"
            f"MIME: {file_obj.mime_type}\n"
            f"Size: {self._model._format_size(file_obj.size_bytes)}\n"
            f"SHA-256: {file_obj.sha256[:16] if file_obj.sha256 else 'N/A'}...\n"
            f"Status: {file_obj.status}\n"
            f"Imported: {file_obj.imported_at}"
        )

    def _remove_file(self, file_uuid: str) -> None:
        reply = QMessageBox.question(
            self,
            "Remove File",
            "Are you sure you want to remove this file from the project?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._project_manager.remove_file(file_uuid)