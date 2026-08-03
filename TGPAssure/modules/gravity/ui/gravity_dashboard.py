from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSplitter,
    QStackedWidget, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QInputDialog,
)

from modules.gravity.constants import COMPLETE_BOUGUER_ANOMALY, RAW_GRAVITY
from modules.gravity.gravity_controller import GravityQcController
from modules.gravity.gravity_engine import FIELD_STAGE_KEYS, FINAL_STAGE_KEYS
from modules.gravity.gravity_processing_engine import GravityProcessingEngine
from modules.gravity.gravity_profiles import profile_names
from modules.gravity.models import GravityDataset
from modules.gravity.reader import GravityReader
from core.domain.geospatial import CoordinateTransformError, to_wgs84
from ui.widgets.geospatial_view import GeoTrack, GoogleGeospatialView
from ui.widgets.scientific_spatial_view import ScientificSpatialView

try:
    import pyqtgraph as pg
except Exception:  # optional at source-analysis/test time
    pg = None

_QSS = """
QWidget#gravityDashboard {
    background:#F3F6FA;
    color:#102D42;
    font-size:8.3pt;
}
QWidget#gravityDashboard QLabel { background: transparent; }
QFrame#gravHeader {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #09273D,stop:.56 #0E5F83,stop:1 #13A9C4);
    border:0;
    border-radius:8px;
}
QLabel#gravTitle { color:#FFFFFF; font-size:14px; font-weight:900; }
QLabel#gravSubtitle { color:#D5EDF6; font-size:8px; font-weight:600; }
QLabel#gravHeaderLabel { color:#D8ECF6; font-size:8px; font-weight:900; }
QLabel#gravBadge {
    background:#E8F7EF; color:#0F6C43; border:1px solid #B8DEC9; border-radius:8px;
    padding:4px 10px; font-size:8px; font-weight:900;
}
QFrame#gravControlStrip, QFrame#gravMetricBox, QFrame#gravPanel, QFrame#gravReportPanel {
    background:#FFFFFF; border:1px solid #D4DEE8; border-radius:7px;
}
QFrame#gravMetricBox {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #FFFFFF,stop:1 #F5F8FB);
    border-left:3px solid #0A86C7;
}
QLabel#gravStripLabel { color:#4A6174; font-size:7.8pt; font-weight:800; }
QLabel#gravMetricTitle { color:#617789; font-size:7.5pt; font-weight:900; }
QLabel#gravMetricValue { color:#0F2E44; font-size:13px; font-weight:900; }
QLabel#gravSectionTitle { color:#123047; font-size:10px; font-weight:900; }
QLabel#gravHelp { color:#5D7080; font-size:8px; }
QLabel#gravStatus {
    background:#FFFFFF; color:#254C66; border:1px solid #D4E1EC; border-radius:7px;
    padding:3px 8px; font-size:8pt; font-weight:700;
}
QFrame#gravSideNav { background:#FFFFFF; border:1px solid #D3DFE8; border-radius:7px; }
QLabel#gravNavTitle {
    color:#587287; font-size:7.8px; font-weight:900; letter-spacing:.5px; padding:3px 4px 4px 5px;
}
QPushButton#gravNavButton {
    text-align:left; min-height:25px; max-height:27px; padding:2px 7px;
    border:1px solid transparent; border-radius:5px; background:transparent;
    color:#24465D; font-size:7.5pt; font-weight:700;
}
QPushButton#gravNavButton:hover { background:#EDF5FB; border-color:#D2E6F1; color:#0A6EA8; }
QPushButton#gravNavButton:checked { background:#0A6EA8; border-color:#075C8C; color:#FFFFFF; }
QPushButton {
    min-height:23px; max-height:28px; padding:2px 9px; border:1px solid #B8C7D3; border-radius:5px;
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #FFFFFF,stop:1 #EDF3F8);
    color:#102A3D; font-size:8pt; font-weight:700;
}
QPushButton:hover { background:#E7F2FA; border-color:#75AFCF; }
QPushButton#gravPrimaryButton { background:#0A82BE; color:#FFFFFF; border:1px solid #086A9B; font-weight:900; }
QPushButton#gravPrimaryButton:hover { background:#0792D8; }
QPushButton#gravHeaderButton {
    background:rgba(255,255,255,.16); color:#FFFFFF; border:1px solid rgba(255,255,255,.30);
    border-radius:6px; font-weight:900;
}
QPushButton#gravHeaderButton:hover { background:rgba(255,255,255,.25); }
QComboBox, QDoubleSpinBox {
    min-height:23px; max-height:27px; padding:1px 6px; border:1px solid #BCCBD6; border-radius:5px;
    background:#FFFFFF; color:#102D42; font-size:8pt;
}
QTabWidget::pane { border:1px solid #D4DEE8; border-radius:6px; background:#FFFFFF; top:-1px; }
QTabBar::tab {
    background:#EAF1F6; color:#335064; border:1px solid #D4DEE8; padding:4px 9px;
    min-height:18px; font-size:7.8pt; font-weight:800;
}
QTabBar::tab:selected { background:#FFFFFF; color:#0A6EA8; border-bottom-color:#FFFFFF; font-weight:900; }
QTableWidget {
    background:#FFFFFF; alternate-background-color:#F7FAFC; border:1px solid #DCE5EC;
    gridline-color:#E7EDF2; selection-background-color:#D6EBF7; selection-color:#0E2E44; font-size:8pt;
}
QHeaderView::section {
    background:#E8F0F6; color:#29495E; border:0; border-bottom:1px solid #D3DFE8;
    border-right:1px solid #E1E8EF; padding:3px 4px; font-weight:900; font-size:8pt;
}
QSplitter::handle { background:#CCD7E0; }
QSplitter::handle:horizontal { width:4px; }
QSplitter::handle:vertical { height:4px; }
"""

class _Signals(QObject):
    result = Signal(object)
    error = Signal(str)
    progress = Signal(int, str)


class _Worker(QRunnable):
    def __init__(self, fn: Callable[[Callable[[int, str], None]], Any]) -> None:
        super().__init__()
        self.fn = fn
        self.signals = _Signals()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.result.emit(self.fn(self.signals.progress.emit))
        except Exception:
            self.signals.error.emit(traceback.format_exc())


class _NoOpTabBar:
    def setExpanding(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def setElideMode(self, *_args: Any, **_kwargs: Any) -> None:
        return None


class _GravityNavigationStack(QWidget):
    """Electrical-style left navigation with a QTabWidget-compatible subset."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._buttons: list[QPushButton] = []
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(5)

        self.nav_panel = QFrame(self)
        self.nav_panel.setObjectName("gravSideNav")
        self.nav_panel.setFixedWidth(144)
        nav = QVBoxLayout(self.nav_panel)
        nav.setContentsMargins(5, 6, 5, 6)
        nav.setSpacing(4)
        title = QLabel("GRAVITY")
        title.setObjectName("gravNavTitle")
        nav.addWidget(title)
        self._nav_layout = nav

        self.stack = QStackedWidget(self)
        self.stack.currentChanged.connect(self._sync_buttons)
        root.addWidget(self.nav_panel)
        root.addWidget(self.stack, 1)

    def addTab(self, widget: QWidget, title: str) -> int:
        index = self.stack.addWidget(widget)
        button = QPushButton(title)
        button.setObjectName("gravNavButton")
        button.setCheckable(True)
        button.setToolTip(title)
        button.setMinimumWidth(0)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.clicked.connect(lambda _checked=False, target=index: self.setCurrentIndex(target))
        self._buttons.append(button)
        self._nav_layout.addWidget(button)
        if index == 0:
            button.setChecked(True)
        return index

    def finalize(self) -> None:
        self._nav_layout.addStretch(1)

    def setCurrentIndex(self, index: int) -> None:
        if 0 <= index < self.stack.count():
            self.stack.setCurrentIndex(index)
            self._sync_buttons(index)

    def currentIndex(self) -> int:
        return self.stack.currentIndex()

    def setCurrentWidget(self, widget: QWidget) -> None:
        self.stack.setCurrentWidget(widget)
        self._sync_buttons(self.stack.currentIndex())

    def currentWidget(self) -> QWidget | None:
        return self.stack.currentWidget()

    def setDocumentMode(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def setUsesScrollButtons(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def setElideMode(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def tabBar(self) -> _NoOpTabBar:
        return _NoOpTabBar()

    def _sync_buttons(self, index: int) -> None:
        for button_index, button in enumerate(self._buttons):
            button.blockSignals(True)
            button.setChecked(button_index == index)
            button.blockSignals(False)


class GravityDashboard(QWidget):
    activity_started = Signal(str, str)
    activity_progress = Signal(int, str)
    activity_finished = Signal()
    state_changed = Signal()

    TAB_OVERVIEW = 0
    TAB_OBSERVATIONS = 1
    TAB_QC = 2
    TAB_PROCESSING = 3
    TAB_MAP = 4
    TAB_PROFILES = 5
    TAB_SPATIAL = 6
    TAB_GEOSPATIAL = 7
    TAB_REPORTS = 8

    def __init__(self, controller: GravityQcController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("gravityDashboard")
        self.setProperty("module_id", "gravity")
        self.setStyleSheet(_QSS)
        self.controller = controller
        self.reader = GravityReader()
        self.processing = GravityProcessingEngine()
        self.observations: GravityDataset | None = None
        self.base: GravityDataset | None = None
        self.latest_result: dict[str, Any] | None = None
        self.processing_products: dict[str, Any] = {}
        self._thread_pool = QThreadPool(self)
        self._thread_pool.setMaxThreadCount(1)
        self._workers: set[_Worker] = set()
        self._build_ui()
        self._connect_controller()
        self._refresh_all()

    # ---------------- public ribbon API ----------------
    def open_observations(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Gravity Observations", str(Path.home()),
                                              "Gravity data (*.csv *.txt *.dat *.xyz *.xlsx *.xlsm);;All files (*)")
        if path:
            self.open_observations_path(path)

    def open_observations_path(self, path: str | Path) -> None:
        source = str(Path(path).expanduser().resolve())
        def work(progress):
            progress(10, "Inspecting gravity columns and coordinate fields")
            inspection = self.reader.inspect(source)
            if not inspection["is_gravity_candidate"]:
                raise ValueError("The selected file does not contain a recognizable observed-gravity field.")
            progress(40, "Reading and normalizing gravity observations")
            dataset = self.reader.read_observations(source)
            progress(100, f"Loaded {dataset.record_count:,} gravity observations")
            return dataset
        self._run_background("Opening Gravity Observations", f"Reading {Path(source).name}", work, self._accept_observations)

    def open_base(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Gravity Base Station", str(Path.home()),
                                              "Gravity data (*.csv *.txt *.dat *.xyz *.xlsx *.xlsm);;All files (*)")
        if path:
            self.open_base_path(path)

    def open_base_path(self, path: str | Path) -> None:
        source = str(Path(path).expanduser().resolve())
        def work(progress):
            progress(15, "Reading base-station observations")
            data = self.reader.read_base(source)
            progress(100, f"Loaded {data.record_count:,} base readings")
            return data
        self._run_background("Opening Gravity Base Station", f"Reading {Path(source).name}", work, self._accept_base)

    def run_full_qc(self) -> None:
        self._run_qc(None)

    def run_field_qc(self) -> None:
        self._run_qc(FIELD_STAGE_KEYS)

    def run_final_qc(self) -> None:
        self._run_qc(FINAL_STAGE_KEYS)

    def cancel_qc(self) -> None:
        self.controller.cancel()

    def process_standard(self) -> None:
        if not self._require_observations():
            return
        density, ok = QInputDialog.getDouble(self, "Standard Gravity Reduction", "Bouguer reduction density (g/cm³):",
                                             self.density_spin.value(), 1.0, 5.0, 3)
        if not ok:
            return
        self.density_spin.setValue(density)
        def work(progress):
            progress(10, "Applying tidal and base-drift corrections")
            result = self.processing.run_standard_reduction(self.observations, base=self.base, density_g_cm3=density)
            progress(70, "Calculating normal gravity, free-air and Bouguer anomalies")
            progress(100, "Standard gravity reduction complete")
            return result
        self._run_background("Reducing Gravity Data", "Executing auditable standard land-gravity reduction", work, self._accept_reduction)

    def generate_grid(self) -> None:
        if not self._require_observations():
            return
        if COMPLETE_BOUGUER_ANOMALY not in self.observations.channels:
            QMessageBox.information(self, "Gravity Grid", "Run Standard Reduction before generating a Bouguer-anomaly grid.")
            return
        size, ok = QInputDialog.getDouble(self, "Gravity Grid", "Grid cell size (metres):", 50.0, 0.1, 100000.0, 2)
        if not ok:
            return
        def work(progress):
            progress(15, "Preparing reduced gravity coordinates")
            grid = self.processing.grid(self.observations, cell_size=size)
            progress(90, "Finalizing Bouguer-anomaly grid")
            progress(100, "Gravity grid ready")
            return grid
        self._run_background("Generating Gravity Grid", f"Interpolating {size:g} m grid", work, self._accept_grid)

    def show_map(self) -> None:
        if not self._require_observations():
            return
        self.tabs.setCurrentIndex(self.TAB_MAP)
        self.activity_started.emit("Rendering Gravity Anomaly Map", "Preparing Bouguer-anomaly map display")
        try:
            self.activity_progress.emit(50, "Updating map and color scale")
            self._refresh_map()
            self.activity_progress.emit(100, "Anomaly map ready")
        finally:
            self.activity_finished.emit()

    def show_profile(self) -> None:
        if not self._require_observations():
            return
        self.tabs.setCurrentIndex(self.TAB_PROFILES)
        self.activity_started.emit("Rendering Gravity Profile", "Preparing line/station anomaly profile")
        try:
            self.activity_progress.emit(60, "Updating profile plot")
            self._refresh_profile()
            self.activity_progress.emit(100, "Gravity profile ready")
        finally:
            self.activity_finished.emit()

    def show_native_view(self, mode: str = "2d") -> None:
        if not self._require_observations():
            return
        self.tabs.setCurrentIndex(self.TAB_SPATIAL)
        self._refresh_native_spatial()
        self.native_view.set_mode("3d" if str(mode).lower().startswith("3") else "2d")

    def show_geospatial_view(self, mode: str = "2d") -> None:
        if not self._require_observations():
            return
        self.tabs.setCurrentIndex(self.TAB_GEOSPATIAL)
        self._refresh_geospatial()
        self.geospatial_view.set_mode("3d" if str(mode).lower().startswith("3") else "2d")

    def export_csv(self) -> None:
        if not self._require_observations():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Gravity Data", str(Path.home() / "gravity_processed.csv"), "CSV (*.csv)")
        if not path:
            return
        data = self.observations
        self._run_background("Exporting Gravity Data", f"Writing {Path(path).name}",
                             lambda progress: self._export_worker(progress, data, path),
                             lambda output: QMessageBox.information(self, "Gravity Export", f"Saved:\n{output}"))

    def generate_report(self, fmt: str) -> None:
        if self.latest_result is None:
            QMessageBox.information(self, "Gravity Report", "Run Gravity QC before generating a report.")
            return
        suffix = ".pdf" if fmt.lower() == "pdf" else ".xlsx"
        suggested = Path.home() / f"gravity_qc_report{suffix}"
        from ui.dialogs.report_dialog import ReportDialog
        dialog = ReportDialog(
            self, default_format=fmt, default_title="Land Gravity Quality-Control Report",
            suggested_path=suggested, allow_format_change=False,
        )
        if not dialog.exec():
            return
        config = dialog.get_report_config()
        path = config.output_path
        payload = dict(self.latest_result)
        def work(progress):
            progress(15, "Building gravity QC report tables and figures")
            from report.report_builders.gravity_qc_report_builder import GravityQcReportBuilder
            output = GravityQcReportBuilder().build(payload, path, fmt)
            progress(100, "Gravity QC report complete")
            return output
        def completed(output):
            if hasattr(self, "report_status"):
                self.report_status.setText(f"Saved {fmt.upper()} report: {output}")
                self.tabs.setCurrentIndex(self.TAB_REPORTS)
            QMessageBox.information(self, "Gravity Report", f"Saved:\n{output}")
        self._run_background("Generating Gravity QC Report", f"Creating {fmt.upper()} report", work, completed)

    def can_execute(self, action_id: str) -> bool:
        has_data = self.observations is not None
        has_result = self.latest_result is not None
        running = self.controller.active_job_id is not None
        if action_id in {"gravity_open", "gravity_open_observations", "gravity_open_base"}:
            return True
        if action_id == "gravity_cancel":
            return running
        if action_id in {"gravity_run_full", "gravity_run_field", "gravity_reduce"}:
            return has_data and not running
        if action_id == "gravity_run_final":
            return has_data and COMPLETE_BOUGUER_ANOMALY in (self.observations.channels if self.observations else {}) and not running
        if action_id == "gravity_grid":
            return has_data and COMPLETE_BOUGUER_ANOMALY in self.observations.channels
        if action_id in {"gravity_map", "gravity_profile", "gravity_view_2d", "gravity_view_3d", "gravity_satellite", "gravity_export_csv"}:
            return has_data
        if action_id in {"gravity_report_pdf", "gravity_report_xlsx"}:
            return has_result
        return True

    # ---------------- internals ----------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(5, 5, 5, 5)
        root.setSpacing(5)

        header = QFrame()
        header.setObjectName("gravHeader")
        header.setMinimumHeight(68)
        header.setMaximumHeight(78)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(11, 7, 11, 7)
        hl.setSpacing(10)

        title_layout = QVBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(1)
        title = QLabel("Gravity QC & Reduction")
        title.setObjectName("gravTitle")
        subtitle = QLabel("Land gravity • base drift • repeatability • Bouguer reduction • anomaly mapping • profile QA")
        subtitle.setObjectName("gravSubtitle")
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        hl.addLayout(title_layout, 1)

        actions = QWidget()
        actions.setStyleSheet("background: transparent;")
        action_grid = QGridLayout(actions)
        action_grid.setContentsMargins(0, 0, 0, 0)
        action_grid.setHorizontalSpacing(6)
        action_grid.setVerticalSpacing(4)
        for idx, (text, slot) in enumerate((
            ("Observations", self.open_observations),
            ("Base", self.open_base),
            ("Run QC", self.run_full_qc),
            ("Reduce", self.process_standard),
            ("Grid", self.generate_grid),
            ("Export", self.export_csv),
        )):
            button = QPushButton(text)
            button.setObjectName("gravHeaderButton")
            button.setFixedHeight(27)
            button.setMinimumWidth(82)
            button.clicked.connect(slot)
            action_grid.addWidget(button, idx // 3, idx % 3)
        hl.addWidget(actions, 0)

        self.dataset_badge = QLabel("NO DATASET")
        self.dataset_badge.setObjectName("gravBadge")
        self.dataset_badge.setFixedHeight(27)
        self.dataset_badge.setMinimumWidth(96)
        self.dataset_badge.setAlignment(Qt.AlignCenter)
        hl.addWidget(self.dataset_badge)
        root.addWidget(header)

        controls = QFrame()
        controls.setObjectName("gravControlStrip")
        controls.setMaximumHeight(40)
        cl = QHBoxLayout(controls)
        cl.setContentsMargins(9, 5, 9, 5)
        cl.setSpacing(7)
        profile_label = QLabel("QC Profile")
        profile_label.setObjectName("gravStripLabel")
        cl.addWidget(profile_label)
        self.profile_combo = QComboBox()
        self.profile_combo.setFixedWidth(130)
        for name in profile_names():
            self.profile_combo.addItem(name.title(), name)
        self.profile_combo.setCurrentText("Standard")
        cl.addWidget(self.profile_combo)
        density_label = QLabel("Density")
        density_label.setObjectName("gravStripLabel")
        cl.addWidget(density_label)
        self.density_spin = QDoubleSpinBox()
        self.density_spin.setRange(1, 5)
        self.density_spin.setDecimals(3)
        self.density_spin.setValue(2.67)
        self.density_spin.setSuffix(" g/cm³")
        self.density_spin.setFixedWidth(122)
        cl.addWidget(self.density_spin)
        cl.addStretch(1)
        self.status_label = QLabel("Ready — open gravity observations to begin")
        self.status_label.setObjectName("gravStatus")
        self.status_label.setMinimumWidth(0)
        self.status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        cl.addWidget(self.status_label, 2)
        root.addWidget(controls)

        self.metric_labels = {}
        self.tabs = _GravityNavigationStack()
        self.tabs.stack.currentChanged.connect(self._page_changed)
        self.tabs.addTab(self._overview_tab(), "Overview")
        self.tabs.addTab(self._observations_tab(), "Observations")
        self.tabs.addTab(self._qc_tab(), "QC Results")
        self.tabs.addTab(self._processing_tab(), "Reduction")
        self.tabs.addTab(self._map_tab(), "Anomaly Map")
        self.tabs.addTab(self._profile_tab(), "Profiles")
        self.tabs.addTab(self._spatial_tab(), "2D / 3D Data")
        self.tabs.addTab(self._geospatial_tab(), "Satellite / Terrain")
        self.tabs.addTab(self._reports_tab(), "Reports / Export")
        self.tabs.finalize()
        root.addWidget(self.tabs, 1)

    def _metrics_row_widget(self) -> QWidget:
        metrics = QWidget()
        ml = QGridLayout(metrics)
        ml.setContentsMargins(0, 0, 0, 2)
        ml.setHorizontalSpacing(6)
        ml.setVerticalSpacing(0)
        for col, (key, label) in enumerate((
            ("records", "Records"),
            ("stations", "Stations"),
            ("lines", "Lines"),
            ("status", "QC Status"),
            ("score", "QC Score"),
        )):
            box = QFrame()
            box.setObjectName("gravMetricBox")
            box.setMinimumHeight(44)
            box.setMaximumHeight(48)
            bl = QVBoxLayout(box)
            bl.setContentsMargins(9, 4, 9, 4)
            bl.setSpacing(0)
            t = QLabel(label)
            t.setObjectName("gravMetricTitle")
            v = QLabel("—")
            v.setObjectName("gravMetricValue")
            bl.addWidget(t)
            bl.addWidget(v)
            ml.addWidget(box, 0, col)
            ml.setColumnStretch(col, 1)
            self.metric_labels[key] = v
        return metrics

    def _configure_table(self, table: QTableWidget, min_height: int = 180) -> QTableWidget:
        table.setAlternatingRowColors(True)
        table.setWordWrap(False)
        table.setShowGrid(True)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(22)
        table.horizontalHeader().setStretchLastSection(True)
        table.setMinimumHeight(min_height)
        return table

    def _overview_tab(self):
        host = QWidget()
        l = QVBoxLayout(host)
        l.setContentsMargins(7, 7, 7, 7)
        l.setSpacing(6)
        l.addWidget(self._metrics_row_widget())
        self.overview_table = self._configure_table(QTableWidget(0, 2), 190)
        self.overview_table.setHorizontalHeaderLabels(["Property", "Value"])
        self.overview_table.setColumnWidth(0, 190)
        l.addWidget(self.overview_table, 1)
        return host

    def _observations_tab(self):
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(7, 7, 7, 7)
        layout.setSpacing(6)
        intro = QLabel("Observation and base-station records are separated so wide tables can use the full workspace.")
        intro.setObjectName("gravHelp")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        self.observation_table = self._configure_table(QTableWidget(0, 8), 230)
        self.observation_table.setHorizontalHeaderLabels(["#", "Time", "Station", "Line", "X / Lon", "Y / Lat", "Elevation", "Gravity"])
        self.observation_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.observation_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.observation_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.observation_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.observation_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.Stretch)
        tabs.addTab(self.observation_table, "Observation Preview")
        self.base_preview_table = self._configure_table(QTableWidget(0, 8), 230)
        self.base_preview_table.setHorizontalHeaderLabels(["#", "Time", "Station", "Line", "X / Lon", "Y / Lat", "Elevation", "Gravity"])
        self.base_preview_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.base_preview_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.base_preview_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.Stretch)
        tabs.addTab(self.base_preview_table, "Base Preview")
        layout.addWidget(tabs, 1)
        return host

    def _qc_tab(self):
        host = QWidget()
        l = QVBoxLayout(host)
        l.setContentsMargins(8, 8, 8, 8)
        tabs = QTabWidget(host)
        tabs.setDocumentMode(True)
        table_page = QWidget()
        table_layout = QVBoxLayout(table_page)
        table_layout.setContentsMargins(4, 4, 4, 4)
        self.qc_table = self._configure_table(QTableWidget(0, 5), 190)
        self.qc_table.setHorizontalHeaderLabels(["Stage", "Status", "Message", "Duration ms", "Metrics"])
        self.qc_table.setColumnWidth(0, 170)
        self.qc_table.setColumnWidth(1, 90)
        self.qc_table.setColumnWidth(3, 90)
        table_layout.addWidget(self.qc_table, 1)
        tabs.addTab(table_page, "Stage Results")

        chart_page = QWidget()
        chart_layout = QVBoxLayout(chart_page)
        chart_layout.setContentsMargins(4, 4, 4, 4)
        chart_layout.setSpacing(5)
        if pg is not None:
            self.gravity_qc_status_plot = pg.PlotWidget(background="w")
            self.gravity_qc_status_plot.showGrid(x=False, y=True, alpha=0.18)
            self.gravity_qc_status_plot.setLabel("left", "Stage count")
            self.gravity_qc_status_plot.setTitle("Run Gravity QC to show status graph")
            self.gravity_qc_duration_plot = pg.PlotWidget(background="w")
            self.gravity_qc_duration_plot.showGrid(x=False, y=True, alpha=0.18)
            self.gravity_qc_duration_plot.setLabel("left", "Duration (ms)")
            chart_layout.addWidget(self.gravity_qc_status_plot, 1)
            chart_layout.addWidget(self.gravity_qc_duration_plot, 1)
        else:
            chart_layout.addWidget(QLabel("pyqtgraph is unavailable; QC tables remain active."), 1)
        tabs.addTab(chart_page, "QC Graphs")
        l.addWidget(tabs, 1)
        return host

    def _processing_tab(self):
        host = QWidget()
        l = QVBoxLayout(host)
        l.setContentsMargins(8, 8, 8, 8)
        self.channel_table = self._configure_table(QTableWidget(0, 4), 190)
        self.channel_table.setHorizontalHeaderLabels(["Channel", "Min", "Max", "Mean"])
        self.channel_table.setColumnWidth(0, 220)
        self.channel_table.setColumnWidth(1, 120)
        self.channel_table.setColumnWidth(2, 120)
        l.addWidget(self.channel_table, 1)
        return host

    def _map_tab(self):
        host = QWidget()
        l = QVBoxLayout(host)
        l.setContentsMargins(8, 8, 8, 8)
        if pg is not None:
            self.map_plot = pg.PlotWidget()
            self.map_plot.setBackground("w")
            self.map_plot.showGrid(x=True, y=True, alpha=0.25)
            self.map_plot.setLabel("bottom", "X / Longitude")
            self.map_plot.setLabel("left", "Y / Latitude")
            l.addWidget(self.map_plot, 1)
        else:
            self.map_plot = None
            l.addWidget(QLabel("Map rendering requires pyqtgraph. Grid statistics remain available in the Reduction tab."))
        return host

    def _profile_tab(self):
        host = QWidget()
        l = QVBoxLayout(host)
        l.setContentsMargins(8, 8, 8, 8)
        if pg is not None:
            self.profile_plot = pg.PlotWidget()
            self.profile_plot.setBackground("w")
            self.profile_plot.showGrid(x=True, y=True, alpha=0.25)
            self.profile_plot.setLabel("bottom", "Observation index")
            self.profile_plot.setLabel("left", "Gravity (mGal)")
            l.addWidget(self.profile_plot, 1)
        else:
            self.profile_plot = None
            self.profile_table = self._configure_table(QTableWidget(0, 3), 220)
            self.profile_table.setHorizontalHeaderLabels(["Index", "Station", "Gravity"])
            l.addWidget(self.profile_table, 1)
        return host

    def _spatial_tab(self):
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(7, 7, 7, 7)
        self.native_view = ScientificSpatialView(host, title="Gravity Native 2D / 3D Anomaly View")
        layout.addWidget(self.native_view, 1)
        return host

    def _reports_tab(self):
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        panel = QFrame()
        panel.setObjectName("gravReportPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(12, 10, 12, 10)
        title = QLabel("Gravity deliverables")
        title.setObjectName("gravSectionTitle")
        panel_layout.addWidget(title)
        help_label = QLabel("Export processed channels or create client-ready PDF and Excel QC reports from the latest completed run.")
        help_label.setObjectName("gravHelp")
        help_label.setWordWrap(True)
        panel_layout.addWidget(help_label)
        buttons = QHBoxLayout()
        for text, callback in (
            ("Export CSV", self.export_csv),
            ("PDF QC Report", lambda: self.generate_report("pdf")),
            ("Excel QC Report", lambda: self.generate_report("xlsx")),
        ):
            button = QPushButton(text)
            if text.startswith("PDF"):
                button.setObjectName("gravPrimaryButton")
            button.clicked.connect(callback)
            buttons.addWidget(button)
        buttons.addStretch(1)
        panel_layout.addLayout(buttons)
        self.report_status = QLabel("Load observations and run QC to enable report generation.")
        self.report_status.setObjectName("gravHelp")
        self.report_status.setWordWrap(True)
        panel_layout.addWidget(self.report_status)
        layout.addWidget(panel)
        layout.addStretch(1)
        return host

    def _geospatial_tab(self):
        host = QWidget()
        l = QVBoxLayout(host)
        l.setContentsMargins(8, 8, 8, 8)
        self.geospatial_view = GoogleGeospatialView(host, title="Gravity Survey — Satellite & 3D Terrain")
        l.addWidget(self.geospatial_view, 1)
        return host

    def _connect_controller(self):
        self.controller.run_started.connect(self._on_run_started)
        self.controller.progress_changed.connect(self._on_progress)
        self.controller.run_completed.connect(self._on_run_completed)
        self.controller.run_failed.connect(self._on_run_failed)
        self.controller.run_cancelled.connect(self._on_run_cancelled)

    def _run_qc(self, stages):
        if not self._require_observations(): return
        try:
            self.controller.run_qc(self.observations, base=self.base, profile_name=str(self.profile_combo.currentData()),
                                   selected_stage_keys=stages, density_g_cm3=self.density_spin.value(),
                                   processing_products=self.processing_products)
        except Exception as exc:
            QMessageBox.critical(self,"Gravity QC Error",str(exc))

    def _on_run_started(self, job_id):
        self.status_label.setText("Gravity QC running…"); self.activity_started.emit("Running Gravity QC","Executing gravity QC stages and reduction checks"); self.state_changed.emit()
    def _on_progress(self,current,total,message):
        value=round(100*current/max(total,1)); self.status_label.setText(message); self.activity_progress.emit(value,message)
    def _on_run_completed(self,result):
        self.latest_result=result; self.status_label.setText(f"QC {str(result.get('status','')).upper()} — score {float(result.get('score',0)):.1f}/100"); self._refresh_all(); self.activity_finished.emit(); self.state_changed.emit()
    def _on_run_failed(self,error):
        self.activity_finished.emit(); self.state_changed.emit(); QMessageBox.critical(self,"Gravity QC",error)
    def _on_run_cancelled(self):
        self.activity_finished.emit(); self.status_label.setText("Gravity QC cancelled"); self.state_changed.emit()

    def _accept_observations(self,data):
        self.observations=data; self.latest_result=None; self.processing_products.clear(); self.status_label.setText(f"Loaded {data.record_count:,} observations from {data.source_path.name}"); self._refresh_all(); self.state_changed.emit()
    def _accept_base(self,data):
        self.base=data; self.latest_result=None; self.status_label.setText(f"Loaded {data.record_count:,} base-station readings"); self._refresh_all(); self.state_changed.emit()
    def _accept_reduction(self,data):
        self.observations=data; self.latest_result=None; self.status_label.setText("Standard gravity reduction completed; rerun Final/Full QC for acceptance"); self._refresh_all(); self.state_changed.emit()
    def _accept_grid(self,grid):
        self.processing_products["grid"]=grid; self.status_label.setText(f"Generated {grid['values'].shape[1]} × {grid['values'].shape[0]} gravity grid"); self._refresh_map(); self.state_changed.emit()

    def _export_worker(self,progress,data,path):
        progress(20,"Writing gravity channels and coordinates"); output=self.processing.export_csv(data,path); progress(100,"Gravity CSV export complete"); return output

    def _run_background(self,title,message,work,on_result):
        self.activity_started.emit(title,message)
        worker=_Worker(work); self._workers.add(worker)
        worker.signals.progress.connect(self.activity_progress.emit)
        def done(result):
            self._workers.discard(worker)
            try: on_result(result)
            finally: self.activity_finished.emit()
        def failed(tb):
            self._workers.discard(worker); self.activity_finished.emit(); msg=tb.strip().splitlines()[-1] if tb.strip() else "Unknown error"; QMessageBox.critical(self,title,msg)
        worker.signals.result.connect(done); worker.signals.error.connect(failed); self._thread_pool.start(worker)

    def _require_observations(self):
        if self.observations is None:
            QMessageBox.information(self,"Gravity QC","Open gravity observations first."); return False
        return True

    def _page_changed(self, index: int) -> None:
        """Refresh expensive views only when their sidebar page becomes visible."""
        if index == self.TAB_MAP:
            self._refresh_map()
        elif index == self.TAB_PROFILES:
            self._refresh_profile()
        elif index == self.TAB_SPATIAL:
            self._refresh_native_spatial()
        elif index == self.TAB_GEOSPATIAL:
            self._refresh_geospatial()

    def _refresh_all(self):
        d=self.observations
        self.dataset_badge.setText("NO DATASET" if d is None else d.source_path.name[:32])
        self.metric_labels["records"].setText("—" if d is None else f"{d.record_count:,}")
        self.metric_labels["stations"].setText("—" if d is None else f"{d.station_count:,}")
        self.metric_labels["lines"].setText("—" if d is None else f"{d.line_count:,}")
        self.metric_labels["status"].setText("—" if not self.latest_result else str(self.latest_result.get("status","—")).upper())
        self.metric_labels["score"].setText("—" if not self.latest_result else f"{float(self.latest_result.get('score',0)):.1f}")
        self._refresh_overview(); self._refresh_observation_previews(); self._refresh_qc(); self._refresh_channels(); self._refresh_map(); self._refresh_profile()
        if self.tabs.currentIndex() == self.TAB_SPATIAL:
            self._refresh_native_spatial()
        if self.tabs.currentIndex() == self.TAB_GEOSPATIAL:
            self._refresh_geospatial()
        if hasattr(self, "report_status"):
            self.report_status.setText(
                "QC report is ready for export." if self.latest_result else
                "Load observations and run QC to enable report generation."
            )

    def _refresh_overview(self):
        if self.observations:
            s = self.observations.summary()
            rows = [
                ("Source file", s["source_path"]),
                ("Survey type", s["survey_type"]),
                ("Records", f"{self.observations.record_count:,}"),
                ("Stations", f"{self.observations.station_count:,}"),
                ("Lines", f"{self.observations.line_count:,}"),
                ("CRS", s.get("crs") or "Not defined"),
                ("Gravity units", s["gravity_units"]),
                ("Elevation units", s["elevation_units"]),
                ("Channels", ", ".join(s["channels"])),
                ("Base station", self.base.source_path.name if self.base else "Not loaded"),
                ("Bouguer density", f"{self.density_spin.value():.3f} g/cm³"),
            ]
        else:
            rows = [
                ("Status", "No gravity observation file loaded"),
                ("Next step", "Click Observations to load CSV/TXT/DAT/XYZ/XLSX gravity data"),
                ("Expected fields", "station/line, observed gravity, elevation, coordinate or longitude/latitude"),
                ("Base correction", "Optional: load a base-station file before running full QC"),
                ("Outputs", "QC stages, standard reduction channels, Bouguer anomaly map, profiles, CSV/PDF/XLSX reports"),
            ]
        self.overview_table.setRowCount(len(rows))
        for r, (k, v) in enumerate(rows):
            self.overview_table.setItem(r, 0, QTableWidgetItem(str(k)))
            item = QTableWidgetItem(str(v))
            item.setToolTip(str(v))
            self.overview_table.setItem(r, 1, item)
        self.overview_table.resizeRowsToContents()

    def _refresh_observation_previews(self) -> None:
        if hasattr(self, "observation_table"):
            self._fill_preview_table(self.observation_table, self.observations)
        if hasattr(self, "base_preview_table"):
            self._fill_preview_table(self.base_preview_table, self.base)

    def _fill_preview_table(self, table: QTableWidget, dataset: GravityDataset | None) -> None:
        if dataset is None:
            table.setRowCount(1)
            table.setItem(0, 0, QTableWidgetItem("—"))
            table.setItem(0, 1, QTableWidgetItem("No dataset loaded"))
            for column in range(2, table.columnCount()):
                table.setItem(0, column, QTableWidgetItem(""))
            return
        limit = min(dataset.record_count, 2000)
        channel_name = RAW_GRAVITY if RAW_GRAVITY in dataset.channels else next(iter(dataset.channels), None)
        values = dataset.channels.get(channel_name, np.full(dataset.record_count, np.nan))
        use_projected = np.count_nonzero(np.isfinite(dataset.x) & np.isfinite(dataset.y)) >= 1
        table.setRowCount(limit)
        for row in range(limit):
            timestamp = dataset.timestamps[row]
            time_text = "" if np.isnat(timestamp) else np.datetime_as_string(timestamp, unit="ms")
            x_value = dataset.x[row] if use_projected else dataset.longitude[row]
            y_value = dataset.y[row] if use_projected else dataset.latitude[row]
            record = (
                row + 1, time_text, str(dataset.station_id[row]), str(dataset.line_id[row]),
                self._number_text(x_value, 4), self._number_text(y_value, 4),
                self._number_text(dataset.elevation[row], 3), self._number_text(values[row], 5),
            )
            for column, value in enumerate(record):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                table.setItem(row, column, item)
        table.resizeRowsToContents()

    @staticmethod
    def _number_text(value: Any, decimals: int) -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return ""
        return "" if not np.isfinite(number) else f"{number:.{decimals}f}"

    def _refresh_qc_graphs(self, stages: list[dict[str, Any]]) -> None:
        if pg is None or not hasattr(self, "gravity_qc_status_plot"):
            return
        self.gravity_qc_status_plot.clear()
        self.gravity_qc_duration_plot.clear()
        if not stages:
            self.gravity_qc_status_plot.setTitle("Run Gravity QC to show status graph")
            self.gravity_qc_duration_plot.setTitle("Run Gravity QC to show stage durations")
            return
        counts: dict[str, int] = {}
        durations: list[float] = []
        labels: list[str] = []
        for stage in stages:
            status = str(stage.get("status", "unknown")).upper()
            counts[status] = counts.get(status, 0) + 1
            durations.append(float(stage.get("duration_ms", 0) or 0))
            labels.append(str(stage.get("display_name", stage.get("stage_key", "Stage")))[:12])
        keys = sorted(counts)
        values = np.asarray([counts[key] for key in keys], dtype=float)
        brushes = []
        for key in keys:
            low = key.lower()
            brushes.append(pg.mkBrush("#C2414A") if low in {"fail", "failed", "error"} else (pg.mkBrush("#D97706") if "warn" in low else pg.mkBrush("#15945C")))
        self.gravity_qc_status_plot.addItem(pg.BarGraphItem(x=np.arange(len(values)), height=values, width=0.62, brushes=brushes, pen=pg.mkPen("#FFFFFF")))
        self.gravity_qc_status_plot.getAxis("bottom").setTicks([[(float(i), key.title()) for i, key in enumerate(keys)]])
        self.gravity_qc_status_plot.setYRange(0, max(1.0, float(np.max(values)) * 1.18), padding=0)
        self.gravity_qc_status_plot.setTitle("Gravity QC status summary")

        duration_values = np.asarray(durations, dtype=float)
        self.gravity_qc_duration_plot.addItem(pg.BarGraphItem(x=np.arange(len(duration_values)), height=duration_values, width=0.62, brush=pg.mkBrush("#0A86C7"), pen=pg.mkPen("#FFFFFF")))
        self.gravity_qc_duration_plot.getAxis("bottom").setTicks([[(float(i), label) for i, label in enumerate(labels)]])
        self.gravity_qc_duration_plot.setYRange(0, max(1.0, float(np.max(duration_values)) * 1.18), padding=0)
        self.gravity_qc_duration_plot.setTitle("Gravity QC duration by stage")

    def _refresh_qc(self):
        stages = list(self.latest_result.get("stage_outcomes", [])) if self.latest_result else []
        if not stages:
            rows = [["Not run", "—", "Load observations and run Gravity QC to populate stage results", "—", "—"]]
        else:
            rows = [[
                s.get("display_name", s.get("stage_key", "")),
                str(s.get("status", "")).upper(),
                s.get("message", ""),
                s.get("duration_ms", 0),
                self._metric_preview(s.get("metrics", {})),
            ] for s in stages]
        self.qc_table.setRowCount(len(rows))
        for r, vals in enumerate(rows):
            for c, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                item.setToolTip(str(v))
                self.qc_table.setItem(r, c, item)
        self.qc_table.resizeRowsToContents()
        self._refresh_qc_graphs(stages)

    @staticmethod
    def _metric_preview(metrics):
        if not isinstance(metrics,dict): return str(metrics)
        return "; ".join(f"{k}={v}" for k,v in list(metrics.items())[:5] if not isinstance(v,(dict,list)))

    def _refresh_channels(self):
        channels = [] if self.observations is None else list(self.observations.channels.items())
        if not channels:
            rows = [["No reduced/observed channels", "—", "—", "Open data or run Standard Reduction"]]
        else:
            rows = []
            for name, values in channels:
                finite = np.asarray(values, float)
                finite = finite[np.isfinite(finite)]
                rows.append([name, "—", "—", "—"] if not finite.size else [
                    name,
                    f"{np.min(finite):.5f}",
                    f"{np.max(finite):.5f}",
                    f"{np.mean(finite):.5f}",
                ])
        self.channel_table.setRowCount(len(rows))
        for r, stats in enumerate(rows):
            for c, v in enumerate(stats):
                item = QTableWidgetItem(str(v))
                item.setToolTip(str(v))
                self.channel_table.setItem(r, c, item)
        self.channel_table.resizeRowsToContents()

    def _xy_for_plot(self):
        d=self.observations
        if d is None: return np.array([]),np.array([])
        if np.count_nonzero(np.isfinite(d.x)&np.isfinite(d.y))>=3: return d.x,d.y
        return d.longitude,d.latitude

    def _refresh_map(self):
        if self.map_plot is None: return
        self.map_plot.clear()
        if self.observations is None: return
        x,y=self._xy_for_plot(); channel=COMPLETE_BOUGUER_ANOMALY if COMPLETE_BOUGUER_ANOMALY in self.observations.channels else RAW_GRAVITY; z=self.observations.channel(channel); valid=np.isfinite(x)&np.isfinite(y)&np.isfinite(z)
        if not np.any(valid): return
        brush=[pg.intColor(i, hues=64) for i in np.clip(((z[valid]-np.nanmin(z[valid]))/max(np.ptp(z[valid]),1e-9)*63).astype(int),0,63)]
        self.map_plot.plot(x[valid],y[valid],pen=None,symbol="o",symbolSize=7,symbolBrush=brush)

    def _refresh_profile(self):
        if self.observations is None: return
        channel=COMPLETE_BOUGUER_ANOMALY if COMPLETE_BOUGUER_ANOMALY in self.observations.channels else RAW_GRAVITY; values=self.observations.channel(channel)
        if self.profile_plot is not None:
            self.profile_plot.clear(); self.profile_plot.plot(np.arange(values.size), values, pen=pg.mkPen("#0B83BA", width=2))
        elif hasattr(self,"profile_table"):
            n=min(values.size,1000); self.profile_table.setRowCount(n)
            for i in range(n):
                for c,v in enumerate((i,str(self.observations.station_id[i]),f"{values[i]:.6f}")): self.profile_table.setItem(i,c,QTableWidgetItem(str(v)))

    def _refresh_native_spatial(self) -> None:
        if not hasattr(self, "native_view"):
            return
        if self.observations is None:
            self.native_view.clear("No gravity observations loaded")
            return
        x, y = self._xy_for_plot()
        channel = COMPLETE_BOUGUER_ANOMALY if COMPLETE_BOUGUER_ANOMALY in self.observations.channels else RAW_GRAVITY
        values = self.observations.channel(channel)
        self.native_view.set_data(
            x, y, values, z=self.observations.elevation,
            title="Gravity Anomaly", value_label=channel.replace("_", " ").title(),
            value_units=self.observations.gravity_units, coordinate_label="Survey coordinates", allow_surface=True,
        )

    def _refresh_geospatial(self):
        if not hasattr(self, "geospatial_view"):
            return
        d=self.observations
        if d is None:
            self.geospatial_view.clear_tracks(); return
        direct=np.isfinite(d.longitude)&np.isfinite(d.latitude)&(np.abs(d.longitude)<=180)&(np.abs(d.latitude)<=90)
        try:
            if np.count_nonzero(direct):
                coords=to_wgs84(d.longitude,d.latitude,crs="EPSG:4326",altitude_m=d.elevation,allow_lonlat_inference=True)
            else:
                coords=to_wgs84(d.x,d.y,crs=d.crs,altitude_m=d.elevation,allow_lonlat_inference=True)
        except CoordinateTransformError as exc:
            self.geospatial_view.clear_tracks(); self.geospatial_view.set_status_message(str(exc)); return
        valid=coords.valid_mask
        if not np.any(valid):
            self.geospatial_view.clear_tracks(); self.geospatial_view.set_status_message("No valid geographic coordinates are available for satellite/3D display."); return
        tracks=[]
        line_values=np.asarray(d.line_id,dtype=object)
        names=[str(v).strip() for v in line_values if str(v).strip()]
        for name in dict.fromkeys(names):
            idx=np.flatnonzero((line_values.astype(str)==name)&valid)
            if idx.size: tracks.append(GeoTrack(name,coords.longitude[idx],coords.latitude[idx],coords.altitude_m[idx]))
        if not tracks:
            idx=np.flatnonzero(valid); tracks=[GeoTrack("Gravity Survey",coords.longitude[idx],coords.latitude[idx],coords.altitude_m[idx])]
        self.geospatial_view.set_tracks(tracks,render=self.tabs.currentIndex()==self.TAB_GEOSPATIAL)
