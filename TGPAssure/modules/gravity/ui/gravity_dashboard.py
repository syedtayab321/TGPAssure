
from __future__ import annotations

import csv
import math
import traceback
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QApplication,
)

from modules.gravity.constants import (
    COMPLETE_BOUGUER_ANOMALY,
    DEFAULT_DENSITY_G_CM3,
    FREE_AIR_ANOMALY,
    RAW_GRAVITY,
    SIMPLE_BOUGUER_ANOMALY,
)
from modules.gravity.gravity_controller import GravityQcController
from modules.gravity.gravity_processing_engine import GravityProcessingEngine
from modules.gravity.models import GravityDataset
from modules.gravity.reader import GravityReader

try:
    import pyqtgraph as pg
except Exception:  # pragma: no cover
    pg = None


_QSS = """
QWidget#gravityDashboard {
    background:#ECEFF3;
    color:#1E2935;
    font-family:"Segoe UI", Arial, sans-serif;
    font-size:7pt;
}
QFrame#gxMenu, QFrame#gxToolStrip, QFrame#gxPanel, QFrame#gxLeft, QFrame#gxRight {
    background:#FFFFFF;
    border:1px solid #CCD4DE;
    border-radius:5px;
}
QFrame#gxMenu {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #F6F9FC, stop:1 #EAF3FA);
}
QFrame#gxToolStrip {
    background:#FAFBFC;
}
QLabel#gxTitle {
    color:#203243;
    font-size:8pt;
    font-weight:900;
}
QLabel#gxStatus {
    background:#FFFFFF;
    color:#24485F;
    border:1px solid #C9D9E8;
    border-radius:4px;
    padding:2px 6px;
    font-weight:700;
}
QLabel#gxMetric {
    background:#F8FAFC;
    border:1px solid #D3DAE3;
    border-left:3px solid #247BA0;
    border-radius:5px;
    padding:4px 7px;
    font-weight:800;
    color:#263746;
}
QLabel#gxSection {
    color:#344150;
    font-weight:900;
    background:#EEF2F6;
    padding:2px 5px;
    border-radius:3px;
}
QToolButton, QPushButton {
    min-height:22px;
    padding:3px 9px;
    border:1px solid #B8C3D0;
    border-radius:5px;
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #FFFFFF, stop:1 #EDF3F8);
    color:#1E2935;
    font-weight:800;
}
QToolButton:disabled, QPushButton:disabled {
    background:#E5EAF0;
    color:#8492A0;
    border-color:#CBD3DC;
}
QToolButton:hover, QPushButton:hover { background:#EEF6FC; border-color:#6FA4C7; }
QToolButton#primaryTool, QPushButton#primaryTool {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #E5F5FF, stop:1 #CFE9FA);
    border-color:#63A8D4;
    color:#0B4F7B;
}
QToolButton#greenTool, QPushButton#greenTool {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ECFBF1, stop:1 #D2F1DD);
    border-color:#75C791;
    color:#176333;
}
QToolButton#purpleTool, QPushButton#purpleTool {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #F6EEFF, stop:1 #E6D7FB);
    border-color:#B79DE3;
    color:#4F2F88;
}
QToolButton#orangeTool, QPushButton#orangeTool {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #FFF8E8, stop:1 #FFE9B7);
    border-color:#D7B66B;
    color:#745305;
}
QComboBox, QDoubleSpinBox {
    background:#FFFFFF;
    border:1px solid #C3CCD7;
    border-radius:4px;
    min-height:19px;
    padding:1px 4px;
}
QTabWidget::pane {
    border:1px solid #CCD4DE;
    border-radius:5px;
    background:#FFFFFF;
}
QTabBar::tab {
    background:#E9EEF4;
    border:1px solid #CCD4DE;
    padding:3px 9px;
    margin-right:1px;
    border-top-left-radius:4px;
    border-top-right-radius:4px;
    font-weight:700;
}
QTabBar::tab:selected {
    background:#FFFFFF;
    color:#0B4F7B;
    border-top:3px solid #247BA0;
    border-bottom-color:#FFFFFF;
}
QListWidget {
    background:#FFFFFF;
    border:1px solid #D3DAE3;
    border-radius:4px;
    alternate-background-color:#F8FAFC;
}
QListWidget::item { padding:3px 4px; }
QListWidget::item:selected { background:#D9EAF7; color:#083B66; }
QTableWidget {
    background:#FFFFFF;
    alternate-background-color:#F8FAFC;
    border:1px solid #D3DAE3;
    gridline-color:#E5EAF0;
    selection-background-color:#D9EAF7;
    selection-color:#1E2935;
}
QHeaderView::section {
    background:#E8EEF5;
    color:#263746;
    border:0;
    border-right:1px solid #CCD4DE;
    border-bottom:1px solid #CCD4DE;
    padding:3px;
    font-weight:800;
}
QTextEdit {
    background:#FFFFFF;
    border:1px solid #D3DAE3;
    border-radius:4px;
    padding:5px;
}
"""


class _Signals(QObject):
    completed = Signal(object)
    failed = Signal(str)


class _Worker(QRunnable):
    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self.fn = fn
        self.signals = _Signals()
        self.cancelled = False
        # Keep the runnable alive until signals are delivered. Losing the Python
        # wrapper too early can leave the global loader visible even though the
        # worker finished.
        self.setAutoDelete(False)

    def cancel(self) -> None:
        self.cancelled = True

    @Slot()
    def run(self) -> None:
        if self.cancelled:
            return
        try:
            value = self.fn()
            self.signals.completed.emit(value)
        except Exception:
            self.signals.failed.emit(traceback.format_exc())


class GravityDashboard(QWidget):
    """Oasis-montaj-style gravity mapping/profiling submodule.

    This is a TGPAssure-native workspace. It replaces the old Gravity QC pages
    with a database/map/profile workflow similar to a gravity-geology mapping
    package: project/data explorer, map windows, profile view, reduction tools,
    grid generation and export.
    """

    state_changed = Signal()
    activity_started = Signal(str, str)
    activity_started_cancellable = Signal(str, str, object)
    activity_progress = Signal(int, str)
    activity_finished = Signal()

    TAB_DATABASE = 0
    TAB_MAP = 1
    TAB_PROFILE = 2
    TAB_REDUCTION = 3
    TAB_REPORT = 4

    def __init__(self, controller: GravityQcController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("gravityDashboard")
        self.setStyleSheet(_QSS)
        self.controller = controller
        self.reader = GravityReader()
        self.engine = GravityProcessingEngine()
        self.thread_pool = QThreadPool.globalInstance()

        self.observations: GravityDataset | None = None
        self.base: GravityDataset | None = None
        self.reduced: GravityDataset | None = None
        self.grid: dict[str, Any] | None = None
        self.last_qc: dict[str, Any] | None = None
        self._tool_buttons: list[QToolButton] = []
        self._busy_count = 0
        self._active_workers: list[_Worker] = []
        self._active_worker: _Worker | None = None
        self._active_task_title = ""

        self._build_ui()
        self._refresh_everything()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(5, 5, 5, 5)
        root.setSpacing(4)

        root.addWidget(self._menu_bar())
        root.addWidget(self._tool_strip())

        body = QSplitter(Qt.Horizontal)
        body.setChildrenCollapsible(False)
        body.addWidget(self._left_explorer())
        body.addWidget(self._center_workspace())
        body.addWidget(self._right_inspector())
        body.setSizes([220, 1050, 230])
        root.addWidget(body, 1)

        bottom = QHBoxLayout()
        self.status = QLabel("No gravity dataset loaded")
        self.status.setObjectName("gxStatus")
        self.metric_records = QLabel("Records: 0")
        self.metric_records.setObjectName("gxMetric")
        self.metric_channels = QLabel("Channels: 0")
        self.metric_channels.setObjectName("gxMetric")
        self.metric_grid = QLabel("Grid: none")
        self.metric_grid.setObjectName("gxMetric")
        bottom.addWidget(self.status, 1)
        bottom.addWidget(self.metric_records)
        bottom.addWidget(self.metric_channels)
        bottom.addWidget(self.metric_grid)
        root.addLayout(bottom)

    def _menu_bar(self) -> QFrame:
        frame = QFrame(objectName="gxMenu")
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(5, 3, 5, 3)
        lay.setSpacing(7)
        for text in ["File", "Edit", "View", "Database", "Map", "Grid", "Profile", "Gravity", "Export", "Help"]:
            btn = QToolButton(text=text)
            btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
            lay.addWidget(btn)
        lay.addStretch(1)
        label = QLabel("Oasis-style Gravity Mapping Workspace")
        label.setObjectName("gxTitle")
        lay.addWidget(label)
        return frame

    def _tool_strip(self) -> QFrame:
        frame = QFrame(objectName="gxToolStrip")
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(5, 4, 5, 4)
        lay.setSpacing(5)

        tools = [
            ("Open Workspace", self.open_workspace_folder, "primaryTool"),
            ("Open Observations", self.open_observations, "orangeTool"),
            ("Open Base", self.open_base, "orangeTool"),
            ("Standard Reduction", self.process_standard, "greenTool"),
            ("Create Grid", self.generate_grid, "primaryTool"),
            ("Map", self.show_map, "primaryTool"),
            ("Profile", self.show_profile, "primaryTool"),
            ("Export CSV", self.export_csv, "purpleTool"),
            ("Report", lambda: self.generate_report("pdf"), "purpleTool"),
        ]
        for text, slot, obj in tools:
            b = QToolButton(text=text)
            b.setObjectName(obj)
            b.setToolButtonStyle(Qt.ToolButtonTextOnly)
            b.clicked.connect(slot)
            self._tool_buttons.append(b)
            lay.addWidget(b)

        lay.addSpacing(10)
        lay.addWidget(QLabel("Channel:"))
        self.channel_combo = QComboBox()
        self.channel_combo.setMinimumWidth(190)
        self.channel_combo.currentIndexChanged.connect(lambda *_: self._refresh_views())
        lay.addWidget(self.channel_combo)
        lay.addWidget(QLabel("Line:"))
        self.line_combo = QComboBox()
        self.line_combo.setMinimumWidth(120)
        self.line_combo.currentIndexChanged.connect(lambda *_: self._refresh_profile())
        lay.addWidget(self.line_combo)
        lay.addWidget(QLabel("Density:"))
        self.density_spin = QDoubleSpinBox()
        self.density_spin.setRange(1.0, 5.0)
        self.density_spin.setDecimals(3)
        self.density_spin.setValue(DEFAULT_DENSITY_G_CM3)
        self.density_spin.setSuffix(" g/cc")
        lay.addWidget(self.density_spin)
        lay.addStretch(1)
        return frame

    def _left_explorer(self) -> QFrame:
        frame = QFrame(objectName="gxLeft")
        frame.setMinimumWidth(190)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(5, 5, 5, 5)
        lay.setSpacing(4)
        self.left_tabs = QTabWidget()
        self.project_list = QListWidget()
        self.data_list = QListWidget()
        self.window_list = QListWidget()
        self.left_tabs.addTab(self.project_list, "Project")
        self.left_tabs.addTab(self.data_list, "Data")
        self.left_tabs.addTab(self.window_list, "Windows")
        lay.addWidget(self.left_tabs, 1)
        return frame

    def _center_workspace(self) -> QFrame:
        frame = QFrame(objectName="gxPanel")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(5, 5, 5, 5)
        lay.setSpacing(4)
        self.tabs = QTabWidget()
        self.table = self._make_table()
        self.tabs.addTab(self.table, "Database")

        if pg:
            self.map_plot = pg.PlotWidget(background="#FFFFFF")
            self.map_plot.showGrid(x=True, y=True, alpha=0.22)
            self.map_plot.setLabel("bottom", "Easting / Longitude")
            self.map_plot.setLabel("left", "Northing / Latitude")
            self.profile_plot = pg.PlotWidget(background="#FFFFFF")
            self.profile_plot.showGrid(x=True, y=True, alpha=0.22)
            self.profile_plot.setLabel("bottom", "Station / Distance")
            self.profile_plot.setLabel("left", "Gravity / Anomaly (mGal)")
        else:
            self.map_plot = QTextEdit("pyqtgraph is not installed. Install pyqtgraph for map display.")
            self.map_plot.setReadOnly(True)
            self.profile_plot = QTextEdit("pyqtgraph is not installed. Install pyqtgraph for profile display.")
            self.profile_plot.setReadOnly(True)

        self.tabs.addTab(self.map_plot, "Map")
        self.tabs.addTab(self.profile_plot, "Profile")
        self.reduction_table = self._make_table(["Product", "Available", "Min", "Max", "Mean"])
        self.tabs.addTab(self.reduction_table, "Reduction")
        self.report_text = QTextEdit()
        self.report_text.setReadOnly(True)
        self.tabs.addTab(self.report_text, "Report")
        lay.addWidget(self.tabs, 1)
        return frame

    def _right_inspector(self) -> QFrame:
        frame = QFrame(objectName="gxRight")
        frame.setMinimumWidth(200)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(5, 5, 5, 5)
        lay.setSpacing(4)
        self.right_tabs = QTabWidget()
        self.layer_list = QListWidget()
        self.channel_list = QListWidget()
        self.properties = QTextEdit()
        self.properties.setReadOnly(True)
        self.right_tabs.addTab(self.layer_list, "Layers")
        self.right_tabs.addTab(self.channel_list, "Channels")
        self.right_tabs.addTab(self.properties, "Properties")
        lay.addWidget(self.right_tabs, 1)
        return frame

    @staticmethod
    def _make_table(headers: list[str] | None = None) -> QTableWidget:
        headers = headers or []
        table = QTableWidget(0, len(headers))
        if headers:
            table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(20)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    # ------------------------------------------------------------------ ribbon compatibility
    def can_execute(self, action_id: str) -> bool:
        if action_id in {"gravity_open", "gravity_open_observations", "gravity_open_base"}:
            return True
        return self.observations is not None or action_id in {"gravity_wall", "gravity_oasis"}

    def handle_ribbon_action(self, action_id: str) -> None:
        mapping = {
            "gravity_open": self.open_workspace_folder,
            "gravity_wall": self.open_observations,
            "gravity_oasis": self.open_workspace_folder,
            "gravity_open_observations": self.open_observations,
            "gravity_open_base": self.open_base,
            "gravity_reduce": self.process_standard,
            "gravity_grid": self.generate_grid,
            "gravity_map": self.show_map,
            "gravity_profile": self.show_profile,
            "gravity_view_2d": self.show_map,
            "gravity_view_3d": lambda: self._info("3D viewer", "3D visualization is reserved for the next Gravity submodule. Current Oasis workspace is 2D map/profile."),
            "gravity_satellite": lambda: self._info("Satellite", "Satellite view removed from this Gravity Mapping submodule."),
            "gravity_export_csv": self.export_csv,
            "gravity_report_pdf": lambda: self.generate_report("pdf"),
            "gravity_report_xlsx": lambda: self.generate_report("xlsx"),
            "gravity_run_full": self.run_full_qc,
            "gravity_run_field": self.run_field_qc,
            "gravity_run_final": self.run_final_qc,
            "gravity_cancel": self.cancel_qc,
        }
        func = mapping.get(action_id)
        if func:
            func()
        else:
            self._status(f"Gravity action not used in this Oasis workspace: {action_id}")

    # ------------------------------------------------------------------ actions
    def open_workspace_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Open gravity workspace folder", "")
        if folder:
            self.open_workspace_folder_path(folder)

    def open_workspace_folder_path(self, folder: str | Path) -> None:
        root = Path(folder)
        if not root.exists() or not root.is_dir():
            self._info("Gravity Workspace", f"Folder not found: {root}")
            return

        def load_workspace() -> tuple[GravityDataset | None, GravityDataset | None, list[str]]:
            supported = {".csv", ".txt", ".dat", ".xyz", ".xlsx", ".xlsm"}
            files = [p for p in sorted(root.iterdir()) if p.is_file() and p.suffix.lower() in supported]
            if not files:
                raise ValueError("No gravity CSV/TXT/DAT/XYZ/XLSX files were found in the selected folder.")
            observations: GravityDataset | None = None
            base: GravityDataset | None = None
            notes: list[str] = []
            for candidate in files:
                name = candidate.name.lower()
                try:
                    info = self.reader.inspect(candidate)
                    if not info.get("is_gravity_candidate"):
                        notes.append(f"Skipped {candidate.name}: no gravity column detected")
                        continue
                    if any(token in name for token in ("base", "drift", "repeat")) and base is None:
                        base = self.reader.read_base(candidate)
                        notes.append(f"Base loaded: {candidate.name}")
                    elif observations is None:
                        observations = self.reader.read_observations(candidate)
                        notes.append(f"Observations loaded: {candidate.name}")
                    elif base is None and any(token in name for token in ("base", "drift", "repeat")):
                        base = self.reader.read_base(candidate)
                        notes.append(f"Base loaded: {candidate.name}")
                    else:
                        notes.append(f"Skipped {candidate.name}: already loaded workspace data")
                except Exception as exc:
                    notes.append(f"Skipped {candidate.name}: {exc}")
            if observations is None and base is not None:
                observations, base = base, None
                notes.append("Only a base-style file was found; opened it as observations for display.")
            if observations is None:
                raise ValueError("No usable gravity observation file was found in the selected folder.\n" + "\n".join(notes))
            return observations, base, notes

        self._run_background(
            "Open Gravity Workspace",
            f"Scanning {root.name}",
            load_workspace,
            self._accept_workspace,
        )

    def open_observations(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open gravity observations",
            "",
            "Gravity data (*.csv *.txt *.dat *.xyz *.xlsx *.xlsm);;All files (*.*)",
        )
        if path:
            self.open_observations_path(path)

    def open_observations_path(self, path: str | Path) -> None:
        source = Path(path)
        self._run_background(
            "Open Gravity Observations",
            f"Reading {source.name}",
            lambda: (self.reader.inspect(source), self.reader.read_observations(source)),
            self._accept_observations,
        )

    def open_base(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open base station gravity",
            "",
            "Gravity base data (*.csv *.txt *.dat *.xyz *.xlsx *.xlsm);;All files (*.*)",
        )
        if path:
            self.open_base_path(path)

    def open_base_path(self, path: str | Path) -> None:
        source = Path(path)
        self._run_background("Open Gravity Base", f"Reading {source.name}", lambda: (self.reader.inspect(source), self.reader.read_base(source)), self._accept_base)

    def process_standard(self) -> None:
        if not self._require_data():
            return
        self._run_background(
            "Standard Gravity Reduction",
            "Applying drift/tide/free-air/Bouguer corrections",
            lambda: self.engine.run_standard_reduction(self.observations.copy(), base=self.base, density_g_cm3=float(self.density_spin.value())),
            self._accept_reduction,
        )

    def generate_grid(self) -> None:
        ds = self.reduced or self.observations
        if ds is None:
            self._info("Gravity Grid", "Open gravity observations first.")
            return
        channel = self._current_channel()
        if channel not in ds.channels:
            self._info("Gravity Grid", f"Channel not available: {channel}")
            return
        self._run_background(
            "Gravity Grid",
            f"Creating grid for {self._label(channel)}",
            lambda: self.engine.grid(ds, source_channel=channel, cell_size=None, method="linear"),
            self._accept_grid,
        )

    def show_map(self) -> None:
        self.tabs.setCurrentIndex(self.TAB_MAP)
        self._refresh_map()

    def show_profile(self) -> None:
        self.tabs.setCurrentIndex(self.TAB_PROFILE)
        self._refresh_profile()

    def show_native_view(self, mode: str = "2d") -> None:
        self.show_map()

    def show_geospatial_view(self, mode: str = "2d") -> None:
        self.show_map()

    def run_full_qc(self) -> None:
        if not self._require_data():
            return
        ds = self.reduced or self.observations
        issues = []
        for name, arr in ds.channels.items():
            vals = np.asarray(arr, dtype=float)
            if np.count_nonzero(np.isfinite(vals)) == 0:
                issues.append(f"{name}: no finite values")
            elif np.nanstd(vals) == 0:
                issues.append(f"{name}: constant values")
        coord_ok = int(np.count_nonzero(ds.valid_coordinate_mask()))
        if coord_ok < ds.record_count:
            issues.append(f"Coordinates missing for {ds.record_count - coord_ok} records")
        self.last_qc = {"issues": issues, "status": "PASS" if not issues else "REVIEW"}
        self._refresh_report()
        self.tabs.setCurrentIndex(self.TAB_REPORT)
        self._status(f"QC completed: {self.last_qc['status']}")

    def run_field_qc(self) -> None:
        self.run_full_qc()

    def run_final_qc(self) -> None:
        self.run_full_qc()

    def cancel_qc(self) -> None:
        worker = self._active_worker
        if worker is not None and not worker.cancelled:
            worker.cancel()
            self._status(f"{self._active_task_title or 'Gravity task'} cancelled")
            self._set_busy(False)
            self.activity_finished.emit()
            return
        self._status("No running gravity task to cancel")

    def export_csv(self) -> None:
        ds = self.reduced or self.observations
        if ds is None:
            self._info("Export CSV", "Open gravity observations first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export gravity database", "gravity_oasis_export.csv", "CSV (*.csv)")
        if not path:
            return
        self._export_dataset_csv(ds, path)
        self._status(f"Exported {ds.record_count:,} records to {Path(path).name}")

    def generate_report(self, fmt: str = "pdf") -> None:
        self.tabs.setCurrentIndex(self.TAB_REPORT)
        self._refresh_report()

    # ------------------------------------------------------------------ data/state
    def _accept_workspace(self, result: tuple[GravityDataset | None, GravityDataset | None, list[str]]) -> None:
        observations, base, notes = result
        if observations is None:
            raise ValueError("Workspace did not return observation data")
        self.observations = observations
        self.base = base
        self.reduced = None
        self.grid = None
        self.last_qc = None
        details = " | ".join(notes[:3]) if notes else observations.source_path.name
        self._status(f"Gravity workspace loaded: {observations.record_count:,} observations" + (f" + {base.record_count:,} base" if base else "") + f" | {details}")
        self._refresh_everything()
        self.state_changed.emit()

    def _accept_observations(self, dataset: GravityDataset | tuple[dict[str, Any], GravityDataset]) -> None:
        inspect_info: dict[str, Any] | None = None
        if isinstance(dataset, tuple):
            inspect_info, dataset = dataset
        self.observations = dataset
        self.reduced = None
        self.grid = None
        self.last_qc = None
        mapped = inspect_info.get("mapped_fields", {}) if inspect_info else dataset.metadata.get("column_mapping", {})
        self._status(f"Loaded observations: {dataset.source_path.name} | {dataset.record_count:,} records | mapped {len(mapped)} fields")
        self._refresh_everything()
        self.state_changed.emit()

    def _accept_base(self, dataset: GravityDataset | tuple[dict[str, Any], GravityDataset]) -> None:
        if isinstance(dataset, tuple):
            _inspect_info, dataset = dataset
        self.base = dataset
        self._status(f"Loaded base station: {dataset.source_path.name} | {dataset.record_count:,} records")
        self._refresh_everything()
        self.state_changed.emit()

    def _accept_reduction(self, dataset: GravityDataset) -> None:
        self.reduced = dataset
        self._status(f"Reduction complete: {dataset.record_count:,} records | {len(dataset.channels)} channels")
        self._refresh_everything()
        self.tabs.setCurrentIndex(self.TAB_REDUCTION)
        self.state_changed.emit()

    def _accept_grid(self, grid: dict[str, Any]) -> None:
        self.grid = grid
        self._status(f"Grid created: {self._label(str(grid.get('source_channel', 'channel')))}")
        self._refresh_everything()
        self.tabs.setCurrentIndex(self.TAB_MAP)
        self.state_changed.emit()

    def _require_data(self) -> bool:
        if self.observations is None:
            self._info("Gravity", "Open gravity observations first.")
            return False
        return True

    def _run_background(self, title: str, message: str, fn: Callable[[], Any], callback: Callable[[Any], None]) -> None:
        worker = _Worker(fn)
        self._active_worker = worker
        self._active_workers.append(worker)
        self._active_task_title = title

        def cancel_current() -> None:
            if worker.cancelled:
                return
            worker.cancel()
            self._status(f"{title} cancelled")
            self._set_busy(False)
            self.activity_finished.emit()

        self.activity_started_cancellable.emit(title, message, cancel_current)
        self._set_busy(True)
        self._status(message)
        QApplication.processEvents()

        def cleanup() -> None:
            if worker in self._active_workers:
                self._active_workers.remove(worker)
            if self._active_worker is worker:
                self._active_worker = None
                self._active_task_title = ""

        def done(value):
            try:
                if worker.cancelled:
                    return
                callback(value)
            except Exception:
                tb = traceback.format_exc()
                self._status(f"{title} failed")
                QMessageBox.critical(self, title, tb)
            finally:
                if not worker.cancelled:
                    self._set_busy(False)
                    self.activity_finished.emit()
                cleanup()

        def failed(tb: str):
            try:
                if worker.cancelled:
                    return
                self._set_busy(False)
                self.activity_finished.emit()
                self._status(f"{title} failed")
                QMessageBox.critical(self, title, tb)
            finally:
                cleanup()

        worker.signals.completed.connect(done)
        worker.signals.failed.connect(failed)
        self.thread_pool.start(worker)

        # Safety net: if a worker signal is swallowed by the Qt runtime, avoid an
        # endless full-screen loader. The worker remains in the background, but
        # the user can continue and retry/cancel instead of being locked out.
        def still_running_notice() -> None:
            if worker in self._active_workers and not worker.cancelled:
                self._status(f"{title} is still running. Use Cancel Task if the selected file/folder is wrong.")
        QTimer.singleShot(12000, still_running_notice)

    def _set_busy(self, busy: bool) -> None:
        self._busy_count = max(0, self._busy_count + (1 if busy else -1))
        enabled = self._busy_count == 0
        for button in getattr(self, "_tool_buttons", []):
            button.setEnabled(enabled)
        self.setCursor(Qt.CursorShape.WaitCursor if busy else Qt.CursorShape.ArrowCursor)

    # ------------------------------------------------------------------ refresh
    def _refresh_everything(self) -> None:
        self._refresh_combo_boxes()
        self._refresh_left_lists()
        self._refresh_right_lists()
        self._refresh_database()
        self._refresh_reduction()
        self._refresh_views()
        self._refresh_report()
        self._refresh_metrics()

    def _refresh_combo_boxes(self) -> None:
        ds = self.reduced or self.observations
        current = self.channel_combo.currentData()
        self.channel_combo.blockSignals(True)
        self.channel_combo.clear()
        if ds is not None:
            preferred = [COMPLETE_BOUGUER_ANOMALY, SIMPLE_BOUGUER_ANOMALY, FREE_AIR_ANOMALY, RAW_GRAVITY]
            names = [n for n in preferred if n in ds.channels] + [n for n in ds.channel_names if n not in preferred]
            for name in names:
                self.channel_combo.addItem(self._label(name), name)
            idx = self.channel_combo.findData(current)
            if idx >= 0:
                self.channel_combo.setCurrentIndex(idx)
        self.channel_combo.blockSignals(False)

        line_current = self.line_combo.currentText()
        self.line_combo.blockSignals(True)
        self.line_combo.clear()
        self.line_combo.addItem("All")
        if ds is not None and ds.line_id is not None:
            values = sorted({str(v).strip() for v in ds.line_id if str(v).strip()})
            self.line_combo.addItems(values)
            idx = self.line_combo.findText(line_current)
            if idx >= 0:
                self.line_combo.setCurrentIndex(idx)
        self.line_combo.blockSignals(False)

    def _refresh_left_lists(self) -> None:
        self.project_list.clear()
        self.data_list.clear()
        self.window_list.clear()
        if self.observations is None:
            for text in ["No project loaded", "Open Observations from ribbon/toolstrip"]:
                self.project_list.addItem(text)
            return
        ds = self.reduced or self.observations
        self.project_list.addItems([
            f"Project: {self.observations.source_path.stem}",
            f"Observations: {self.observations.record_count:,}",
            f"Base: {'loaded' if self.base else 'not loaded'}",
            f"Reduction: {'complete' if self.reduced else 'not run'}",
            f"Grid: {'created' if self.grid else 'not created'}",
        ])
        self.data_list.addItem(f"Database: {self.observations.source_path.name}")
        for ch in ds.channel_names:
            self.data_list.addItem(f"Channel: {self._label(ch)}")
        self.window_list.addItems(["Database", "Map", "Profile", "Reduction", "Report"])

    def _refresh_right_lists(self) -> None:
        self.layer_list.clear()
        self.channel_list.clear()
        ds = self.reduced or self.observations
        if ds is None:
            self.properties.setText("No gravity database loaded.")
            return
        self.layer_list.addItems(["Station points", "Gravity color symbols"])
        if self.grid:
            self.layer_list.addItem("Interpolated grid")
        for ch in ds.channel_names:
            self.channel_list.addItem(self._label(ch))
        summary = ds.summary()
        self.properties.setText("\n".join([
            f"Source: {Path(summary.get('source_path', '')).name}",
            f"Records: {summary.get('record_count', 0):,}",
            f"Stations: {summary.get('station_count', 0):,}",
            f"Lines: {summary.get('line_count', 0):,}",
            f"CRS: {summary.get('crs')}",
            f"Units: {summary.get('gravity_units')}",
            f"Start: {summary.get('start_time')}",
            f"End: {summary.get('end_time')}",
        ]))

    def _refresh_database(self) -> None:
        ds = self.reduced or self.observations
        if ds is None:
            self.table.setColumnCount(0)
            self.table.setRowCount(0)
            return
        channel = self._current_channel(ds)
        channel_names = list(ds.channel_names)
        headers = ["Station", "Line", "Lat", "Lon", "X", "Y", "Elev"] + [self._label(name) for name in channel_names]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        n = min(ds.record_count, 5000)
        self.table.setRowCount(n)
        active_channel_index = 7 + channel_names.index(channel) if channel in channel_names else -1
        for r in range(n):
            vals = [
                ds.station_id[r],
                ds.line_id[r],
                self._fmt(ds.latitude[r], 6),
                self._fmt(ds.longitude[r], 6),
                self._fmt(ds.x[r], 2),
                self._fmt(ds.y[r], 2),
                self._fmt(ds.elevation[r], 2),
            ] + [self._fmt(ds.channels[name][r], 4) for name in channel_names]
            for c, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                if c == active_channel_index:
                    item.setBackground(QColor("#E8F5FF"))
                self.table.setItem(r, c, item)
        self.table.resizeColumnsToContents()
        if ds.record_count > n:
            self.table.setToolTip(f"Showing first {n:,} of {ds.record_count:,} records. Export CSV writes the full database.")

    def _refresh_reduction(self) -> None:
        ds = self.reduced or self.observations
        rows: list[tuple[str, str, str, str, str]] = []
        if ds:
            for channel in [RAW_GRAVITY, FREE_AIR_ANOMALY, SIMPLE_BOUGUER_ANOMALY, COMPLETE_BOUGUER_ANOMALY]:
                arr = ds.channels.get(channel)
                if arr is None:
                    rows.append((self._label(channel), "No", "", "", ""))
                else:
                    vals = arr[np.isfinite(arr)]
                    rows.append((self._label(channel), "Yes", self._fmt(np.nanmin(vals), 4), self._fmt(np.nanmax(vals), 4), self._fmt(np.nanmean(vals), 4)))
        self.reduction_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                self.reduction_table.setItem(r, c, QTableWidgetItem(str(val)))
        self.reduction_table.resizeColumnsToContents()

    def _refresh_views(self) -> None:
        self._refresh_map()
        self._refresh_profile()

    def _refresh_map(self) -> None:
        if not pg:
            return
        self.map_plot.clear()
        ds = self.reduced or self.observations
        if ds is None:
            self.map_plot.setTitle("Open gravity observations to display map")
            return
        channel = self._current_channel(ds)
        x, y = self._xy(ds)
        values = ds.channels.get(channel, np.full(ds.record_count, np.nan))
        valid = np.isfinite(x) & np.isfinite(y) & np.isfinite(values)
        if not np.any(valid):
            self.map_plot.setTitle("No valid coordinates for map")
            return
        colors = self._colors(values[valid])
        spots = [{"pos": (float(px), float(py)), "brush": color, "pen": pg.mkPen("#1F2933", width=0.3), "size": 7} for px, py, color in zip(x[valid], y[valid], colors)]
        self.map_plot.addItem(pg.ScatterPlotItem(spots=spots))
        self.map_plot.setTitle(f"{self._label(channel)} map | {np.count_nonzero(valid):,} stations")

    def _refresh_profile(self) -> None:
        if not pg:
            return
        self.profile_plot.clear()
        ds = self.reduced or self.observations
        if ds is None:
            self.profile_plot.setTitle("Open gravity observations to display profile")
            return
        channel = self._current_channel(ds)
        values = ds.channels.get(channel, np.full(ds.record_count, np.nan))
        x, _ = self._xy(ds)
        line = self.line_combo.currentText() if hasattr(self, "line_combo") else "All"
        mask = np.isfinite(values)
        if line and line != "All":
            mask &= np.asarray([str(v).strip() == line for v in ds.line_id])
        distance = x if np.any(np.isfinite(x)) else np.arange(ds.record_count, dtype=float)
        mask &= np.isfinite(distance)
        if not np.any(mask):
            self.profile_plot.setTitle("No valid values for profile")
            return
        order = np.argsort(distance[mask])
        self.profile_plot.plot(distance[mask][order], values[mask][order], pen=pg.mkPen("#1F78B4", width=1.5), symbol="o", symbolSize=4, symbolBrush="#E9C449", symbolPen=pg.mkPen("#1F2933", width=0.4))
        self.profile_plot.setTitle(f"{self._label(channel)} profile | {line}")

    def _refresh_report(self) -> None:
        ds = self.reduced or self.observations
        if ds is None:
            self.report_text.setText("No gravity data loaded.\n\nUse Open Observations to load gravity data.")
            return
        summary = ds.summary()
        issues = (self.last_qc or {}).get("issues", [])
        lines = [
            "TGPAssure Oasis-Style Gravity Mapping Report",
            "",
            f"Source: {summary.get('source_path')}",
            f"Records: {summary.get('record_count'):,}",
            f"Stations: {summary.get('station_count'):,}",
            f"Lines: {summary.get('line_count'):,}",
            f"Channels: {', '.join(summary.get('channels', []))}",
            f"Base loaded: {'Yes' if self.base else 'No'}",
            f"Reduction applied: {'Yes' if self.reduced else 'No'}",
            f"Grid created: {'Yes' if self.grid else 'No'}",
            "",
            "QC:",
        ]
        lines.extend([f"- {issue}" for issue in issues] if issues else ["- No issues listed"])
        self.report_text.setText("\n".join(lines))

    def _refresh_metrics(self) -> None:
        ds = self.reduced or self.observations
        if ds and ds.metadata.get("missing_elevation"):
            self.status.setToolTip("Elevation column was not present. Data is loaded for display/export, but reduction/QC will flag missing elevations.")
        self.metric_records.setText(f"Records: {ds.record_count:,}" if ds else "Records: 0")
        self.metric_channels.setText(f"Channels: {len(ds.channels)}" if ds else "Channels: 0")
        self.metric_grid.setText("Grid: created" if self.grid else "Grid: none")

    # ------------------------------------------------------------------ helpers
    def _current_channel(self, ds: GravityDataset | None = None) -> str:
        ds = ds or self.reduced or self.observations
        selected = self.channel_combo.currentData() if hasattr(self, "channel_combo") else None
        if selected:
            return str(selected)
        if ds and COMPLETE_BOUGUER_ANOMALY in ds.channels:
            return COMPLETE_BOUGUER_ANOMALY
        if ds and RAW_GRAVITY in ds.channels:
            return RAW_GRAVITY
        return next(iter(ds.channels), RAW_GRAVITY) if ds else RAW_GRAVITY

    def _xy(self, ds: GravityDataset) -> tuple[np.ndarray, np.ndarray]:
        x = np.asarray(ds.x, dtype=float)
        y = np.asarray(ds.y, dtype=float)
        if np.count_nonzero(np.isfinite(x) & np.isfinite(y)) >= 3:
            return x, y
        return np.asarray(ds.longitude, dtype=float), np.asarray(ds.latitude, dtype=float)

    def _status(self, text: str) -> None:
        self.status.setText(text)

    def _info(self, title: str, message: str) -> None:
        QMessageBox.information(self, title, message)
        self._status(message)

    @staticmethod
    def _fmt(value: Any, decimals: int = 2) -> str:
        try:
            number = float(value)
        except Exception:
            return "" if value is None else str(value)
        if not math.isfinite(number):
            return ""
        return f"{number:.{decimals}f}"

    @staticmethod
    def _label(channel: str) -> str:
        return str(channel).replace("_", " ").replace("mgal", "mGal").title()

    @staticmethod
    def _colors(values: np.ndarray) -> list[QColor]:
        vals = np.asarray(values, dtype=float)
        finite = vals[np.isfinite(vals)]
        if finite.size == 0:
            return [QColor("#1F78B4") for _ in vals]
        lo, hi = np.nanpercentile(finite, [2, 98])
        span = max(hi - lo, 1e-15)
        out: list[QColor] = []
        for value in vals:
            f = float(np.clip((value - lo) / span, 0.0, 1.0))
            if f < 0.20:
                out.append(QColor("#243B8F"))
            elif f < 0.40:
                out.append(QColor("#1F9BCF"))
            elif f < 0.60:
                out.append(QColor("#32B36C"))
            elif f < 0.80:
                out.append(QColor("#F3D64E"))
            else:
                out.append(QColor("#D74242"))
        return out

    @staticmethod
    def _export_dataset_csv(ds: GravityDataset, path: str | Path) -> None:
        path = Path(path)
        headers = ["timestamp", "station_id", "line_id", "latitude", "longitude", "x", "y", "elevation"] + list(ds.channel_names)
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(headers)
            for i in range(ds.record_count):
                writer.writerow([
                    str(ds.timestamps[i]),
                    ds.station_id[i],
                    ds.line_id[i],
                    ds.latitude[i],
                    ds.longitude[i],
                    ds.x[i],
                    ds.y[i],
                    ds.elevation[i],
                    *[ds.channels[name][i] for name in ds.channel_names],
                ])
