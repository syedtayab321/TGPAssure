from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable
import traceback

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, QRectF, Signal, Slot
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules.magnetic.constants import (
    BASE_TOTAL_FIELD,
    DESPIKED_TOTAL_FIELD,
    DIURNAL_CORRECTED_FIELD,
    LEVELED_FIELD,
    MICROLEVELED_FIELD,
    RAW_TOTAL_FIELD,
)
from modules.magnetic.magnetic_controller import MagneticQcController
from modules.magnetic.magnetic_engine import PROCESSED_STAGE_KEYS, RAW_STAGE_KEYS
from modules.magnetic.magnetic_processing_engine import MagneticProcessingEngine
from modules.magnetic.models import MagneticBoundary, MagneticDataset
from modules.magnetic.reader import MagneticReader
from modules.magnetic.acquisition_tools import MagneticAcquisitionTools
from modules.magnetic.readers.boundary_reader import MagneticBoundaryReader
from modules.magnetic.ui.import_dialog import MagneticImportDialog
from core.domain.geospatial import CoordinateTransformError, to_wgs84
from core.domain.spatial_visualization import geographic_to_local_xy
from ui.widgets.geospatial_view import GeoTrack, GoogleGeospatialView
from ui.widgets.scientific_spatial_view import ScientificSpatialView


_DASHBOARD_QSS = """
QWidget#magneticDashboard {
    background: #F3F6FA;
    color: #0F2638;
    font-size: 8.5pt;
}
QWidget#magneticDashboard QLabel { background: transparent; }
QFrame#magHeader {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #082B3D, stop:.58 #0B586F, stop:1 #0E8DA8);
    border: 0;
    border-radius: 7px;
}
QFrame#magHeader QLabel { background: transparent; }
QFrame#magStatusBar,
QFrame#magMetricCard,
QFrame#magPanel,
QFrame#magActionCard,
QFrame#magControlBand {
    background: #FFFFFF;
    border: 1px solid #D7E0E7;
    border-radius: 7px;
}
QLabel#magTitle {
    color: #FFFFFF;
    font-size: 13px;
    font-weight: 900;
}
QLabel#magSubtitle {
    color: #D1EBF4;
    font-size: 8px;
}
QLabel#magHeaderLabel {
    color: #D6EDF5;
    font-size: 8px;
    font-weight: 900;
}
QLabel#magDatasetBadge {
    background: #E8F7EF;
    color: #0C6A43;
    border: 1px solid #B8DEC9;
    border-radius: 8px;
    padding: 4px 10px;
    font-size: 8px;
    font-weight: 900;
}
QLabel#magMetricTitle {
    color: #607587;
    font-size: 7.8px;
    font-weight: 900;
    letter-spacing: .4px;
}
QLabel#magMetricValue {
    color: #0F3149;
    font-size: 15px;
    font-weight: 900;
}
QLabel#magMetricHint {
    color: #778897;
    font-size: 7.8px;
}
QLabel#magSectionTitle {
    color: #123047;
    font-size: 10px;
    font-weight: 900;
}
QLabel#magSectionHelp {
    color: #5D7080;
    font-size: 8px;
}
QLabel#magStatusBadge {
    border-radius: 8px;
    padding: 2px 8px;
    font-size: 8px;
    font-weight: 900;
}
QFrame#magSideNav {
    background: #FFFFFF;
    border: 1px solid #D3DFE8;
    border-radius: 7px;
}
QLabel#magNavTitle {
    color: #587287;
    font-size: 8px;
    font-weight: 900;
    letter-spacing: .5px;
    padding: 3px 4px 4px 5px;
}
QPushButton#magNavButton {
    text-align: left;
    min-height: 25px;
    max-height: 27px;
    padding: 2px 7px;
    border: 1px solid transparent;
    border-radius: 5px;
    background: transparent;
    color: #24465D;
    font-size: 7.4pt;
    font-weight: 700;
}
QPushButton#magNavButton:hover {
    background: #FFF3EA;
    border-color: #F3D1BE;
    color: #B75518;
}
QPushButton#magNavButton:checked {
    background: #D95F23;
    border-color: #B94D18;
    color: #FFFFFF;
}
QPushButton {
    min-height: 23px;
    max-height: 28px;
    padding: 2px 9px;
    border: 1px solid #B8C7D3;
    border-radius: 5px;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #FFFFFF, stop:1 #EDF3F8);
    color: #102A3D;
}
QPushButton:hover { background:#E7F2FA; border-color:#75AFCF; }
QPushButton#magPrimaryButton {
    background: #D95F23;
    color: #FFFFFF;
    border: 1px solid #B94D18;
    font-weight: 900;
}
QPushButton#magPrimaryButton:hover { background:#F07228; }
QPushButton#magHeaderButton {
    background: rgba(255,255,255,0.16);
    color: #FFFFFF;
    border: 1px solid rgba(255,255,255,0.28);
    border-radius: 6px;
    font-weight: 900;
    min-width: 78px;
}
QPushButton#magHeaderButton:hover { background: rgba(255,255,255,0.25); }
QComboBox {
    min-height: 24px;
    border: 1px solid #BCCBD6;
    border-radius: 5px;
    background: #FFFFFF;
    color: #102A3D;
    padding: 1px 7px;
}
QTabWidget::pane {
    border: 1px solid #C8D4DE;
    border-radius: 6px;
    background: #FFFFFF;
    top: -1px;
}
QTabBar::tab {
    background: #DDE6ED;
    color: #30495C;
    border: 1px solid #C4D0D9;
    border-bottom: 2px solid #B6C5D0;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    margin-right: 3px;
    padding: 3px 7px;
    font-weight: 700;
    font-size: 8.2pt;
}
QTabBar::tab:selected {
    background: #FFFFFF;
    color: #B75518;
    border: 1px solid #D6AD8E;
    border-top: 3px solid #D95F23;
    border-bottom-color: #FFFFFF;
}
QTableWidget {
    background: #FFFFFF;
    alternate-background-color: #F7FAFC;
    border: 1px solid #DCE5EC;
    gridline-color: #E7EDF2;
    selection-background-color: #F9E5D7;
    selection-color: #0E2E44;
    font-size: 8.2pt;
}
QHeaderView::section {
    background: #E8F0F6;
    color: #29495E;
    border: 0;
    border-bottom: 1px solid #D3DFE8;
    border-right: 1px solid #E1E8EF;
    padding: 3px 4px;
    font-weight: 900;
    font-size: 8.1pt;
}
QProgressBar {
    border: 1px solid #CBD8E2;
    border-radius: 6px;
    background: #EEF3F7;
    text-align: center;
    min-height: 10px;
    max-height: 10px;
    font-size: 7.5px;
}
QProgressBar::chunk { border-radius: 5px; background: #D95F23; }
QPlainTextEdit {
    background: #FFFFFF;
    border: 1px solid #D8E1E8;
    border-radius: 4px;
    font-size: 8.2pt;
}
QSplitter::handle { background: #CCD7E0; }
QSplitter::handle:horizontal { width: 4px; }
QSplitter::handle:vertical { height: 4px; }
"""


class _MetricCard(QFrame):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("magMetricCard")
        self.setMinimumHeight(50)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(7, 4, 7, 4)
        layout.setSpacing(1)
        self.title = QLabel(title.upper())
        self.title.setObjectName("magMetricTitle")
        self.value = QLabel("—")
        self.value.setObjectName("magMetricValue")
        self.value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.value.setWordWrap(False)
        self.value.setMinimumWidth(0)
        self.value.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.hint = QLabel("")
        self.hint.setObjectName("magMetricHint")
        self.hint.setWordWrap(True)
        self.hint.setMinimumWidth(0)
        layout.addWidget(self.title)
        layout.addWidget(self.value)
        layout.addWidget(self.hint)

    def set_value(self, value: Any, hint: str = "") -> None:
        self.value.setText("—" if value in (None, "") else str(value))
        self.hint.setText(hint)




class _MagneticWorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    progress = Signal(int, str)


class _MagneticRunnable(QRunnable):
    def __init__(self, function: Callable[[Callable[[int, str], None]], Any]) -> None:
        super().__init__()
        self.function = function
        self.signals = _MagneticWorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.function(self.signals.progress.emit)
            self.signals.result.emit(result)
        except Exception:
            self.signals.error.emit(traceback.format_exc())



class _NoOpTabBar:
    def setExpanding(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def setElideMode(self, *_args: Any, **_kwargs: Any) -> None:
        return None


class _MagneticNavigationStack(QWidget):
    """Electrical-style left navigation wrapper with a QTabWidget-compatible subset."""

    _SHORT_TITLES = {
        "Data": "Overview",
        "Acq Quick View": "Acquisition",
        "Stats": "Stats",
        "QC": "QC Results",
        "Findings": "Findings",
        "Process": "Processing",
        "Map": "Map",
        "Profiles": "Profiles",
        "2D/3D": "2D / 3D",
        "Satellite": "Satellite",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._buttons: list[QPushButton] = []
        self._widgets: list[QWidget] = []
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(5)

        self.nav_panel = QFrame(self)
        self.nav_panel.setObjectName("magSideNav")
        self.nav_panel.setFixedWidth(140)
        nav = QVBoxLayout(self.nav_panel)
        nav.setContentsMargins(5, 6, 5, 6)
        nav.setSpacing(4)
        nav_title = QLabel("MAGNETIC")
        nav_title.setObjectName("magNavTitle")
        nav.addWidget(nav_title)
        self._nav_layout = nav

        self.stack = QStackedWidget(self)
        root.addWidget(self.nav_panel)
        root.addWidget(self.stack, 1)
        self.stack.currentChanged.connect(self._sync_buttons)

    def addTab(self, widget: QWidget, title: str) -> int:
        index = self.stack.addWidget(widget)
        self._widgets.append(widget)
        button = QPushButton(self._SHORT_TITLES.get(title, title))
        button.setObjectName("magNavButton")
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
        for i, button in enumerate(self._buttons):
            button.blockSignals(True)
            button.setChecked(i == index)
            button.blockSignals(False)

class MagneticDashboard(QWidget):
    dataset_changed = Signal(object)
    activity_started = Signal(str, str)
    activity_progress = Signal(int, str)
    activity_finished = Signal()

    TAB_OVERVIEW = 0
    TAB_ACQUISITION = 1
    TAB_STATS = 2
    TAB_QC = 3
    TAB_FINDINGS = 4
    TAB_PROCESSING = 5
    TAB_MAP = 6
    TAB_PROFILES = 7
    TAB_SPATIAL = 8
    TAB_GEOSPATIAL = 9

    def __init__(self, controller: MagneticQcController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("magneticDashboard")
        self.setProperty("module_id", "magnetic")
        self.setStyleSheet(_DASHBOARD_QSS)

        self.controller = controller
        self.reader = MagneticReader()
        self.boundary_reader = MagneticBoundaryReader()
        self.processing = MagneticProcessingEngine()

        self.rover: MagneticDataset | None = None
        self.base: MagneticDataset | None = None
        self.boundary: MagneticBoundary | None = None
        self.processing_products: dict[str, Any] = {}
        self.latest_result: dict[str, Any] | None = None
        self._all_findings: list[tuple[str, dict[str, Any]]] = []
        self._thread_pool = QThreadPool(self)
        self._thread_pool.setMaxThreadCount(1)
        self._active_workers: set[_MagneticRunnable] = set()
        self._background_busy_count = 0
        self._acq_polygon_points: list[tuple[float, float]] = []
        self._acq_polygon_mode: str = "keep"
        self._acq_drawing_polygon = False
        self._acq_grid_item: Any = None
        self._acq_scatter_item: Any = None
        self._acq_track_items: list[Any] = []
        self._acq_polygon_item: Any = None

        self._build_ui()
        self._connect_controller()
        self._refresh_dataset_views()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(3)

        root.addWidget(self._build_header())
        root.addWidget(self._build_status_bar())

        self.tabs = _MagneticNavigationStack()
        self.tabs.addTab(self._build_overview_tab(), "Data")
        self.tabs.addTab(self._build_acquisition_tab(), "Acq Quick View")
        self.tabs.addTab(self._build_stats_tab(), "Stats")
        self.tabs.addTab(self._build_qc_tab(), "QC")
        self.tabs.addTab(self._build_findings_tab(), "Findings")
        self.tabs.addTab(self._build_processing_tab(), "Process")
        self.tabs.addTab(self._build_map_tab(), "Map")
        self.tabs.addTab(self._build_profile_tab(), "Profiles")
        self.tabs.addTab(self._build_native_spatial_tab(), "2D/3D")
        self.tabs.addTab(self._build_geospatial_tab(), "Satellite")
        self.tabs.finalize()
        root.addWidget(self.tabs, 1)

    def _build_header(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("magHeader")
        outer = QHBoxLayout(frame)
        outer.setContentsMargins(10, 7, 10, 7)
        outer.setSpacing(10)

        # Add the title layout directly to the gradient frame.  A child QWidget
        # can receive an opaque palette on some Windows/Qt styles, which caused
        # the white title to be drawn over a white rectangle.
        title_layout = QVBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(1)
        title = QLabel("Magnetic Geophysics QC")
        title.setObjectName("magTitle")
        title.setStyleSheet("background: transparent; color: #FFFFFF;")
        subtitle = QLabel("Import • base correction • boundary filter • acquisition quick view • map • 2D/3D • reports")
        subtitle.setObjectName("magSubtitle")
        subtitle.setStyleSheet("background: transparent; color: #D1EBF4;")
        subtitle.setToolTip(
            "Professional magnetic QC workflow with reader detection, EnMag quick view, processing, maps and exports."
        )
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        outer.addLayout(title_layout, 1)

        self.open_rover_button = QPushButton("Open Data")
        self.open_rover_button.setObjectName("magHeaderButton")
        self.open_rover_button.setToolTip("Open rover, static, or general magnetic acquisition data")
        self.open_rover_button.clicked.connect(self.open_rover)
        self.open_base_button = QPushButton("Base")
        self.open_base_button.setObjectName("magHeaderButton")
        self.open_base_button.setToolTip("Load a separate base-station magnetic file")
        self.open_base_button.clicked.connect(self.open_base)
        self.open_boundary_button = QPushButton("Boundary")
        self.open_boundary_button.setObjectName("magHeaderButton")
        self.open_boundary_button.setToolTip("Load KML/KMZ/GeoJSON survey boundary")
        self.open_boundary_button.clicked.connect(self.open_boundary)

        self.profile_combo = QComboBox()
        self.profile_combo.addItem("Field QC", "field")
        self.profile_combo.addItem("Standard QC", "standard")
        self.profile_combo.addItem("Processing QC", "processing")
        self.profile_combo.addItem("Strict Final QC", "strict")
        self.profile_combo.setMinimumWidth(118)
        self.profile_combo.setMaximumWidth(160)

        self.run_button = QPushButton("Run QC")
        self.run_button.setObjectName("magPrimaryButton")
        self.run_button.clicked.connect(self.run_full_qc)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_qc)

        action_grid = QGridLayout()
        action_grid.setContentsMargins(0, 0, 0, 0)
        action_grid.setHorizontalSpacing(6)
        action_grid.setVerticalSpacing(5)
        action_grid.addWidget(self.open_rover_button, 0, 0)
        action_grid.addWidget(self.open_base_button, 0, 1)
        action_grid.addWidget(self.open_boundary_button, 0, 2)
        profile_label = QLabel("PROFILE")
        profile_label.setObjectName("magHeaderLabel")
        action_grid.addWidget(profile_label, 1, 0)
        action_grid.addWidget(self.profile_combo, 1, 1)
        action_grid.addWidget(self.run_button, 1, 2)
        action_grid.addWidget(self.cancel_button, 1, 3)
        outer.addLayout(action_grid)

        self.dataset_badge = QLabel("NO DATASET")
        self.dataset_badge.setObjectName("magDatasetBadge")
        self.dataset_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dataset_badge.setFixedHeight(24)
        self.dataset_badge.setMinimumWidth(100)
        outer.addWidget(self.dataset_badge)
        return frame

    def _build_metrics(self) -> QWidget:
        host = QWidget()
        layout = QGridLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(5)
        layout.setVerticalSpacing(5)

        self.metric_records = _MetricCard("Records")
        self.metric_field = _MetricCard("Magnetic Field")
        self.metric_spatial = _MetricCard("Spatial")
        self.metric_support = _MetricCard("Support Data")
        self.metric_qc = _MetricCard("QC Status")

        cards = (
            self.metric_records,
            self.metric_field,
            self.metric_spatial,
            self.metric_support,
            self.metric_qc,
        )
        for index, card in enumerate(cards):
            card.setMinimumWidth(0)
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            layout.addWidget(card, 0, index)
            layout.setColumnStretch(index, 1)
        return host

    def _build_status_bar(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("magStatusBar")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(7, 2, 7, 2)
        layout.setSpacing(5)

        self.status_badge = QLabel("READY")
        self.status_badge.setObjectName("magStatusBadge")
        self._set_status_badge("ready")
        self.status_label = QLabel("Load a magnetic dataset to begin.")
        self.status_label.setMinimumWidth(0)
        self.status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.status_label.setToolTip(
            "Native format, magnetic channel and CRS are detected automatically when possible."
        )
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setMinimumWidth(95)
        self.progress.setMaximumWidth(150)

        layout.addWidget(self.status_badge)
        layout.addWidget(self.status_label, 1)
        layout.addWidget(self.progress)
        return frame

    def _build_overview_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        self.overview_summary = QLabel("No magnetic dataset loaded")
        self.overview_summary.setObjectName("magSectionHelp")
        self.overview_summary.setWordWrap(True)
        self.overview_summary.setContentsMargins(4, 2, 4, 2)
        layout.addWidget(self.overview_summary)
        self.dataset_tabs = QTabWidget()
        self.dataset_tabs.setDocumentMode(True)
        self.dataset_tabs.setUsesScrollButtons(False)
        self.dataset_tabs.tabBar().setExpanding(True)

        self.primary_table = self._make_key_value_table()
        self.dataset_tabs.addTab(self._table_page(self.primary_table), "Dataset")

        self.base_table = self._make_key_value_table()
        self.dataset_tabs.addTab(self._table_page(self.base_table), "Base & Boundary")

        self.metadata_table = self._make_key_value_table()
        self.dataset_tabs.addTab(self._table_page(self.metadata_table), "Metadata")

        self.channels_table = QTableWidget(0, 7)
        self._configure_table(
            self.channels_table,
            ["Channel", "Unit", "Valid", "Minimum", "Maximum", "Mean", "Std. Dev."],
            stretch_last=False,
        )
        self.channels_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 7):
            self.channels_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.dataset_tabs.addTab(self._table_page(self.channels_table), "Channels")

        self.records_table = QTableWidget(0, 8)
        self._configure_table(
            self.records_table,
            ["#", "Timestamp", "X / Longitude", "Y / Latitude", "Elevation", "Total Field", "Line", "Station"],
            stretch_last=False,
        )
        self.records_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.records_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        for col in (2, 3, 4, 5):
            self.records_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.records_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.records_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.dataset_tabs.addTab(self._table_page(self.records_table), "Data Preview")

        layout.addWidget(self.dataset_tabs, 1)
        return page

    def _build_acquisition_tab(self) -> QWidget:
        """Build a non-overflowing acquisition workspace.

        The map/sample display remains visible on the left while dense controls are
        separated into compact tabs on the right.  This prevents spin boxes, action
        buttons and diagnostic tables from being compressed into one narrow column.
        """
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        toolbar = QFrame()
        toolbar.setObjectName("magPanel")
        row = QHBoxLayout(toolbar)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(5)
        title = QLabel("EnMag Acquisition Quick View")
        title.setObjectName("magSectionTitle")
        self.acq_status_label = QLabel("Open an EnMag/Bulucu event log or magnetic dataset to preview acquisition quality.")
        self.acq_status_label.setObjectName("magSectionHelp")
        self.acq_status_label.setMinimumWidth(0)
        self.acq_status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.acq_metric_combo = QComboBox()
        self.acq_metric_combo.addItem("Magnetic field", "mag_nt")
        self.acq_metric_combo.addItem("Elevation", "alt_m")
        self.acq_metric_combo.addItem("BNO / Heading", "bno_heading_deg")
        self.acq_metric_combo.addItem("GPS HDOP", "gps_hdop")
        self.acq_metric_combo.setMinimumWidth(132)
        self.acq_metric_combo.currentIndexChanged.connect(self._refresh_acquisition_quick_view)
        self.acq_view_combo = QComboBox()
        self.acq_view_combo.addItem("Heatmap + points", "heat_points")
        self.acq_view_combo.addItem("Sample points only", "points")
        self.acq_view_combo.addItem("Gap-aware track", "track")
        self.acq_view_combo.addItem("Grid only", "grid")
        self.acq_view_combo.setMinimumWidth(150)
        self.acq_view_combo.currentIndexChanged.connect(self._refresh_acquisition_quick_view)
        self.acq_include_invalid = QCheckBox("Include invalid (*)")
        self.acq_include_invalid.stateChanged.connect(self._refresh_acquisition_quick_view)
        row.addWidget(title)
        row.addWidget(self.acq_status_label, 1)
        row.addWidget(QLabel("Metric:"))
        row.addWidget(self.acq_metric_combo)
        row.addWidget(QLabel("View:"))
        row.addWidget(self.acq_view_combo)
        row.addWidget(self.acq_include_invalid)
        layout.addWidget(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Main display: map and records have their own full-size tabs rather than
        # sharing half of the available vertical space.
        self.acq_display_tabs = QTabWidget()
        self.acq_display_tabs.setDocumentMode(True)
        map_page = QWidget()
        map_layout = QVBoxLayout(map_page)
        map_layout.setContentsMargins(2, 2, 2, 2)
        self.acq_plot = pg.PlotWidget()
        self.acq_plot.setBackground("w")
        self.acq_plot.showGrid(x=True, y=True, alpha=0.2)
        self.acq_plot.setLabel("bottom", "Longitude / X")
        self.acq_plot.setLabel("left", "Latitude / Y")
        try:
            self.acq_plot.scene().sigMouseClicked.connect(self._on_acq_plot_clicked)
        except Exception:
            pass
        map_layout.addWidget(self.acq_plot, 1)
        self.acq_display_tabs.addTab(map_page, "Quick Map")

        samples_page = QWidget()
        samples_layout = QVBoxLayout(samples_page)
        samples_layout.setContentsMargins(2, 2, 2, 2)
        self.acq_sample_table = QTableWidget(0, 8)
        self._configure_table(self.acq_sample_table, ["#", "Time", "X/Lon", "Y/Lat", "Elev", "Metric", "Invalid", "Segment"])
        for column in (0, 1, 2, 3, 7):
            self.acq_sample_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.acq_sample_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        samples_layout.addWidget(self.acq_sample_table, 1)
        self.acq_display_tabs.addTab(samples_page, "Sample Records")
        splitter.addWidget(self.acq_display_tabs)

        # Compact right-side control notebook.  Every control gets a stable width
        # and no action row is allowed to overlap another row.
        self.acq_control_tabs = QTabWidget()
        self.acq_control_tabs.setDocumentMode(True)
        self.acq_control_tabs.setMinimumWidth(300)
        self.acq_control_tabs.setMaximumWidth(420)

        grid_scroll = QScrollArea()
        grid_scroll.setWidgetResizable(True)
        grid_scroll.setFrameShape(QFrame.Shape.NoFrame)
        grid_page = QWidget()
        grid_layout = QVBoxLayout(grid_page)
        grid_layout.setContentsMargins(7, 7, 7, 7)
        grid_layout.setSpacing(6)
        grid_intro = QLabel("Grid, interpolation and colour-scale controls")
        grid_intro.setObjectName("magSectionTitle")
        grid_layout.addWidget(grid_intro)
        settings = QFrame()
        settings.setObjectName("magPanel")
        sgrid = QGridLayout(settings)
        sgrid.setContentsMargins(8, 8, 8, 8)
        sgrid.setHorizontalSpacing(8)
        sgrid.setVerticalSpacing(6)
        self.acq_grid_cols = QSpinBox()
        self.acq_grid_cols.setRange(20, 600)
        self.acq_grid_cols.setValue(120)
        self.acq_grid_cols.valueChanged.connect(self._refresh_acquisition_quick_view)
        self.acq_grid_rows = QSpinBox()
        self.acq_grid_rows.setRange(20, 600)
        self.acq_grid_rows.setValue(90)
        self.acq_grid_rows.valueChanged.connect(self._refresh_acquisition_quick_view)
        self.acq_idw_power = QDoubleSpinBox()
        self.acq_idw_power.setRange(0.5, 6.0)
        self.acq_idw_power.setDecimals(1)
        self.acq_idw_power.setSingleStep(0.5)
        self.acq_idw_power.setValue(2.0)
        self.acq_idw_power.valueChanged.connect(self._refresh_acquisition_quick_view)
        self.acq_heat_spread = QDoubleSpinBox()
        self.acq_heat_spread.setRange(0.5, 10.0)
        self.acq_heat_spread.setDecimals(1)
        self.acq_heat_spread.setSingleStep(0.5)
        self.acq_heat_spread.setValue(1.5)
        self.acq_heat_spread.valueChanged.connect(self._refresh_acquisition_quick_view)
        self.acq_gap_factor = QDoubleSpinBox()
        self.acq_gap_factor.setRange(2.0, 30.0)
        self.acq_gap_factor.setDecimals(1)
        self.acq_gap_factor.setValue(6.0)
        self.acq_gap_factor.valueChanged.connect(self._refresh_acquisition_quick_view)
        self.acq_color_mode = QComboBox()
        self.acq_color_mode.addItem("Robust 2–98%", "robust")
        self.acq_color_mode.addItem("Full range", "full")
        self.acq_color_mode.addItem("Manual", "manual")
        self.acq_color_mode.currentIndexChanged.connect(self._refresh_acquisition_quick_view)
        self.acq_color_min = QLineEdit()
        self.acq_color_min.setPlaceholderText("Minimum value")
        self.acq_color_min.editingFinished.connect(self._refresh_acquisition_quick_view)
        self.acq_color_max = QLineEdit()
        self.acq_color_max.setPlaceholderText("Maximum value")
        self.acq_color_max.editingFinished.connect(self._refresh_acquisition_quick_view)
        fields = [
            ("Grid columns", self.acq_grid_cols),
            ("Grid rows", self.acq_grid_rows),
            ("IDW power", self.acq_idw_power),
            ("Heat spread", self.acq_heat_spread),
            ("Gap factor", self.acq_gap_factor),
            ("Colour scale", self.acq_color_mode),
            ("Manual minimum", self.acq_color_min),
            ("Manual maximum", self.acq_color_max),
        ]
        for row_index, (label_text, widget) in enumerate(fields):
            label_widget = QLabel(label_text + ":")
            label_widget.setMinimumWidth(96)
            widget.setMinimumWidth(135)
            sgrid.addWidget(label_widget, row_index, 0)
            sgrid.addWidget(widget, row_index, 1)
        sgrid.setColumnStretch(1, 1)
        grid_layout.addWidget(settings)
        grid_note = QLabel("Changes update the Quick Map automatically. Manual limits are used only when Colour scale is set to Manual.")
        grid_note.setObjectName("magSectionHelp")
        grid_note.setWordWrap(True)
        grid_layout.addWidget(grid_note)
        grid_layout.addStretch(1)
        grid_scroll.setWidget(grid_page)
        self.acq_control_tabs.addTab(grid_scroll, "Grid & Scale")

        filter_page = QWidget()
        filter_layout = QVBoxLayout(filter_page)
        filter_layout.setContentsMargins(7, 7, 7, 7)
        filter_layout.setSpacing(6)
        filter_title = QLabel("Polygon filtering and export")
        filter_title.setObjectName("magSectionTitle")
        filter_layout.addWidget(filter_title)
        filters = QFrame()
        filters.setObjectName("magPanel")
        fgrid = QGridLayout(filters)
        fgrid.setContentsMargins(8, 8, 8, 8)
        fgrid.setHorizontalSpacing(6)
        fgrid.setVerticalSpacing(6)
        actions = (
            ("Draw Polygon", self._toggle_acq_polygon_drawing),
            ("Undo Point", self._undo_acq_polygon_point),
            ("Reset Polygon", self._reset_acq_polygon),
            ("Apply Keep", lambda: self._set_acq_polygon_mode("keep")),
            ("Apply Reject", lambda: self._set_acq_polygon_mode("reject")),
            ("Export Filtered CSV", self.export_acq_filtered_csv),
            ("Export HTML Map", self.export_acq_html_map),
        )
        for action_index, (text, callback) in enumerate(actions):
            button = QPushButton(text)
            button.setMinimumWidth(0)
            button.clicked.connect(callback)
            fgrid.addWidget(button, action_index // 2, action_index % 2)
        fgrid.setColumnStretch(0, 1)
        fgrid.setColumnStretch(1, 1)
        filter_layout.addWidget(filters)
        self.acq_filter_label = QLabel("No polygon filter")
        self.acq_filter_label.setObjectName("magSectionHelp")
        self.acq_filter_label.setWordWrap(True)
        filter_layout.addWidget(self.acq_filter_label)
        filter_help = QLabel("Select Draw Polygon, then click the Quick Map. Keep or reject mode is applied to all export and preview records.")
        filter_help.setObjectName("magSectionHelp")
        filter_help.setWordWrap(True)
        filter_layout.addWidget(filter_help)
        filter_layout.addStretch(1)
        self.acq_control_tabs.addTab(filter_page, "Polygon & Export")

        diagnostics_page = QWidget()
        diagnostics_layout = QVBoxLayout(diagnostics_page)
        diagnostics_layout.setContentsMargins(5, 5, 5, 5)
        diagnostics_layout.setSpacing(4)
        diagnostics_tabs = QTabWidget()
        diagnostics_tabs.setDocumentMode(True)
        self.acq_parse_table = self._make_key_value_table()
        diagnostics_tabs.addTab(self._table_page(self.acq_parse_table), "Parser")
        self.acq_heading_table = self._make_key_value_table()
        diagnostics_tabs.addTab(self._table_page(self.acq_heading_table), "Heading QC")
        diagnostics_layout.addWidget(diagnostics_tabs, 1)
        self.acq_control_tabs.addTab(diagnostics_page, "Diagnostics")

        splitter.addWidget(self.acq_control_tabs)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([1050, 360])
        layout.addWidget(splitter, 1)
        return page


    def _build_stats_tab(self) -> QWidget:
        """Dedicated statistics workspace so summary cards never compress data tables."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        intro = QFrame()
        intro.setObjectName("magPanel")
        intro_layout = QVBoxLayout(intro)
        intro_layout.setContentsMargins(12, 9, 12, 9)
        intro_layout.setSpacing(2)
        title = QLabel("Dataset Statistics")
        title.setObjectName("magSectionTitle")
        help_label = QLabel(
            "High-level acquisition, magnetic-field, spatial, support-data and QC statistics. "
            "Detailed channel statistics remain available in Data > Channels."
        )
        help_label.setObjectName("magSectionHelp")
        help_label.setWordWrap(True)
        intro_layout.addWidget(title)
        intro_layout.addWidget(help_label)
        layout.addWidget(intro)
        layout.addWidget(self._build_metrics())

        self.stats_details = QTableWidget(0, 3)
        self._configure_table(self.stats_details, ["Statistic", "Value", "Interpretation"])
        self.stats_details.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.stats_details.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.stats_details.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.stats_details, 1)
        return page

    def _build_qc_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        toolbar = QFrame()
        toolbar.setObjectName("magPanel")
        row = QHBoxLayout(toolbar)
        row.setContentsMargins(9, 5, 9, 5)
        row.setSpacing(6)
        title = QLabel("QC stage results")
        title.setObjectName("magSectionTitle")
        self.qc_summary_label = QLabel("No QC run completed")
        self.qc_summary_label.setObjectName("magSectionHelp")
        self.qc_summary_label.setMinimumWidth(0)
        raw_btn = QPushButton("Raw QC")
        raw_btn.clicked.connect(self.run_raw_qc)
        processed_btn = QPushButton("Processed QC")
        processed_btn.clicked.connect(self.run_processed_qc)
        row.addWidget(title)
        row.addWidget(self.qc_summary_label, 1)
        row.addWidget(raw_btn)
        row.addWidget(processed_btn)
        layout.addWidget(toolbar)

        self.stage_table = QTableWidget(0, 6)
        self._configure_table(
            self.stage_table,
            ["Stage", "Status", "Key Metric", "Duration", "Findings", "Message"],
        )
        self.stage_table.setWordWrap(True)
        self.stage_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.stage_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.stage_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.stage_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.stage_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.stage_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.stage_table, 1)
        return page

    def _build_findings_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        toolbar = QFrame()
        toolbar.setObjectName("magPanel")
        row = QHBoxLayout(toolbar)
        row.setContentsMargins(9, 5, 9, 5)
        row.setSpacing(6)
        title = QLabel("QC findings")
        title.setObjectName("magSectionTitle")
        self.finding_count_label = QLabel("0 findings")
        self.finding_count_label.setObjectName("magSectionHelp")
        self.findings_filter = QComboBox()
        self.findings_filter.addItem("All", "all")
        self.findings_filter.addItem("Critical", "critical")
        self.findings_filter.addItem("Error", "error")
        self.findings_filter.addItem("Warning", "warning")
        self.findings_filter.addItem("Info", "info")
        self.findings_filter.currentIndexChanged.connect(self._apply_findings_filter)
        row.addWidget(title)
        row.addWidget(self.finding_count_label, 1)
        row.addWidget(QLabel("Severity:"))
        row.addWidget(self.findings_filter)
        layout.addWidget(toolbar)

        self.findings_table = QTableWidget(0, 5)
        self._configure_table(
            self.findings_table,
            ["Severity", "Stage", "Rule", "Finding", "Recommended Action"],
        )
        self.findings_table.setWordWrap(True)
        self.findings_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.findings_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.findings_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.findings_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.findings_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.findings_table, 1)
        return page

    def _build_processing_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        self.processing_tabs = QTabWidget()
        self.processing_tabs.setDocumentMode(True)
        self.processing_tabs.setUsesScrollButtons(False)
        self.processing_tabs.tabBar().setExpanding(True)
        self.processing_tabs.addTab(
            self._build_processing_action_page(
                "Clean / Despike",
                "Detect robust magnetic spikes and create a new despiked channel. Raw measurements are preserved.",
                [("Run Despike", self.process_despike)],
                "Works with a primary magnetic dataset. Review the output channel before further correction.",
            ),
            "1  Clean",
        )
        self.processing_tabs.addTab(
            self._build_processing_action_page(
                "Diurnal Correction",
                "Interpolate a separate base-station series and create a diurnally corrected magnetic channel.",
                [("Run Diurnal Correction", self.process_diurnal)],
                "Requires a separate base-station dataset overlapping the rover acquisition time.",
            ),
            "2  Correct",
        )
        self.processing_tabs.addTab(
            self._build_processing_action_page(
                "Line Leveling",
                "Apply line-level corrections and optional microleveling to reduce line-to-line mismatch without overwriting raw data.",
                [("Run Line Leveling", self.process_leveling), ("Run Microleveling", self.process_microlevel)],
                "Best used for traverse/tie-line surveys. Static acquisitions may not support these operations.",
            ),
            "3  Level",
        )
        self.processing_tabs.addTab(
            self._build_processing_action_page(
                "Products / Export",
                "Generate spatial products only when the dataset has sufficient geographic coverage, or export the current channels to CSV.",
                [("Generate Grid", self.generate_grid), ("Export CSV", self.export_csv)],
                "Grid generation is intentionally blocked for stationary or insufficiently distributed datasets.",
            ),
            "4  Products",
        )

        history_page = QWidget()
        history_layout = QVBoxLayout(history_page)
        history_layout.setContentsMargins(6, 6, 6, 6)
        history_layout.setSpacing(5)
        self.provenance_table = QTableWidget(0, 5)
        self._configure_table(
            self.provenance_table,
            ["Output Channel", "Parent", "Operation", "Created", "Parameters"],
        )
        self.provenance_table.setWordWrap(True)
        self.provenance_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.provenance_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.provenance_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.provenance_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.provenance_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        self.processing_log = QPlainTextEdit()
        self.processing_log.setReadOnly(True)
        self.processing_log.setPlaceholderText("Processing messages will appear here.")
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.provenance_table)
        splitter.addWidget(self.processing_log)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 90])
        history_layout.addWidget(splitter, 1)
        self.processing_tabs.addTab(history_page, "History & Log")

        layout.addWidget(self.processing_tabs, 1)
        return page

    def _build_processing_action_page(
        self,
        title: str,
        description: str,
        actions: list[tuple[str, Any]],
        requirement: str,
    ) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        panel = QFrame()
        panel.setObjectName("magPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(14, 12, 14, 12)
        panel_layout.setSpacing(8)

        heading = QLabel(title)
        heading.setObjectName("magSectionTitle")
        description_label = QLabel(description)
        description_label.setObjectName("magSectionHelp")
        description_label.setWordWrap(True)
        requirement_label = QLabel("Requirement: " + requirement)
        requirement_label.setWordWrap(True)
        requirement_label.setStyleSheet(
            "background:#F6F8FA;border:1px solid #E0E6EB;border-radius:5px;"
            "padding:7px;color:#556B7B;"
        )

        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        for label, handler in actions:
            button = QPushButton(label)
            button.clicked.connect(handler)
            button_row.addWidget(button)
        button_row.addStretch(1)

        panel_layout.addWidget(heading)
        panel_layout.addWidget(description_label)
        panel_layout.addWidget(requirement_label)
        panel_layout.addLayout(button_row)
        outer.addWidget(panel)
        outer.addStretch(1)
        return page

    def _build_map_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        toolbar = QFrame()
        toolbar.setObjectName("magPanel")
        row = QHBoxLayout(toolbar)
        row.setContentsMargins(9, 5, 9, 5)
        row.setSpacing(6)
        title = QLabel("Spatial review")
        title.setObjectName("magSectionTitle")
        self.map_info_label = QLabel("No dataset")
        self.map_info_label.setObjectName("magSectionHelp")
        self.map_info_label.setMinimumWidth(0)
        self.map_channel_combo = QComboBox()
        self.map_channel_combo.setMinimumWidth(150)
        self.map_channel_combo.currentIndexChanged.connect(self._refresh_map)
        row.addWidget(title)
        row.addWidget(self.map_info_label, 1)
        row.addWidget(QLabel("Channel:"))
        row.addWidget(self.map_channel_combo)
        layout.addWidget(toolbar)

        self.map_plot = pg.PlotWidget()
        self.map_plot.setBackground("w")
        self.map_plot.showGrid(x=True, y=True, alpha=0.2)
        layout.addWidget(self.map_plot, 1)
        return page

    def _build_profile_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        toolbar = QFrame()
        toolbar.setObjectName("magPanel")
        row = QHBoxLayout(toolbar)
        row.setContentsMargins(9, 5, 9, 5)
        row.setSpacing(6)
        title = QLabel("Profile review")
        title.setObjectName("magSectionTitle")
        self.profile_info_label = QLabel("No dataset")
        self.profile_info_label.setObjectName("magSectionHelp")
        self.profile_info_label.setMinimumWidth(0)
        self.line_combo = QComboBox()
        self.line_combo.setMinimumWidth(105)
        self.line_combo.currentIndexChanged.connect(self._refresh_profile)
        self.profile_channel_combo = QComboBox()
        self.profile_channel_combo.setMinimumWidth(145)
        self.profile_channel_combo.currentIndexChanged.connect(self._refresh_profile)
        row.addWidget(title)
        row.addWidget(self.profile_info_label, 1)
        row.addWidget(QLabel("Group:"))
        row.addWidget(self.line_combo)
        row.addWidget(QLabel("Channel:"))
        row.addWidget(self.profile_channel_combo)
        layout.addWidget(toolbar)

        self.profile_plot = pg.PlotWidget()
        self.profile_plot.setBackground("w")
        self.profile_plot.setLabel("left", "Magnetic field", units="nT")
        self.profile_plot.showGrid(x=True, y=True, alpha=0.2)
        layout.addWidget(self.profile_plot, 1)
        return page

    def _build_native_spatial_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        toolbar = QFrame()
        toolbar.setObjectName("magPanel")
        row = QHBoxLayout(toolbar)
        row.setContentsMargins(9, 5, 9, 5)
        row.addWidget(QLabel("Scientific channel:"))
        self.spatial_channel_combo = QComboBox()
        self.spatial_channel_combo.setMinimumWidth(170)
        self.spatial_channel_combo.currentIndexChanged.connect(self._refresh_native_spatial)
        row.addWidget(self.spatial_channel_combo)
        row.addStretch(1)
        layout.addWidget(toolbar)
        self.native_spatial_view = ScientificSpatialView(page, title="Magnetic Native 2D / 3D")
        layout.addWidget(self.native_spatial_view, 1)
        return page

    def _build_geospatial_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self.geospatial_view = GoogleGeospatialView(page, title="Magnetic Survey — Satellite & 3D Terrain")
        layout.addWidget(self.geospatial_view, 1)
        return page

    def _acq_current_polygon(self) -> np.ndarray | None:
        if len(self._acq_polygon_points) < 3:
            return None
        return np.asarray(self._acq_polygon_points, dtype=float)

    def _acq_current_metric(self) -> str:
        if hasattr(self, "acq_metric_combo"):
            return str(self.acq_metric_combo.currentData() or "mag_nt")
        return "mag_nt"

    def _acq_current_view(self):
        dataset = self._display_dataset()
        if dataset is None:
            return None
        return MagneticAcquisitionTools.sample_view(
            dataset,
            metric=self._acq_current_metric(),
            include_invalid=bool(getattr(self, "acq_include_invalid", None) and self.acq_include_invalid.isChecked()),
            polygon=self._acq_current_polygon(),
            polygon_mode=self._acq_polygon_mode,  # type: ignore[arg-type]
        )

    def _refresh_acquisition_quick_view(self) -> None:
        if not hasattr(self, "acq_plot"):
            return
        dataset = self._display_dataset()
        self.acq_plot.clear()
        self.acq_sample_table.setRowCount(0)
        if dataset is None:
            self.acq_status_label.setText("No magnetic dataset loaded")
            self._set_key_value_rows(self.acq_parse_table, [("Status", "Load EnMag/Bulucu event log or magnetic data")])
            self._set_key_value_rows(self.acq_heading_table, [("Heading QC", "No dataset")])
            return

        metric = self._acq_current_metric()
        view = self._acq_current_view()
        if view is None or view.values.size == 0:
            self.acq_status_label.setText("No finite samples after current invalid/polygon filter")
            self._refresh_acq_filter_label()
            return

        report = MagneticAcquisitionTools.parse_report(dataset)
        heading = MagneticAcquisitionTools.heading_qc(dataset)
        parse_rows = [
            ("Reader", dataset.metadata.get("reader", "—")),
            ("Format", dataset.metadata.get("format_id", "magnetic_dataset")),
            ("Total records", report.get("total_records")),
            ("Sensor records", report.get("sensor_records")),
            ("GPS records", report.get("gps_records")),
            ("Exportable samples", report.get("exportable_sample_count")),
            ("Invalid sensor", f"{report.get('invalid_sensor_count', 0)} ({float(report.get('invalid_sensor_ratio_pct', 0.0)):.2f}%)"),
            ("Inline events", report.get("inline_event_count")),
            ("Bad-data events", report.get("inline_bad_data_event_count")),
            ("Median step", self._format_number(report.get("median_step_m"), " m")),
            ("P95 step", self._format_number(report.get("p95_step_m"), " m")),
            ("Track length", self._format_number(report.get("track_length_m"), " m")),
        ]
        self._set_key_value_rows(self.acq_parse_table, parse_rows)
        heading_rows = [(self._humanize(k), v) for k, v in heading.items()]
        self._set_key_value_rows(self.acq_heading_table, heading_rows or [("Heading QC", "No heading channels available")])
        self.acq_status_label.setText(
            f"{view.indices.size:,} displayed samples • {view.metric_name} {view.metric_units} • filter: {self._acq_polygon_mode if self._acq_current_polygon() is not None else 'none'}"
        )
        self._refresh_acq_filter_label()
        self._draw_acq_plot(view)
        self._populate_acq_sample_table(view)

    def _draw_acq_plot(self, view) -> None:
        mode = str(self.acq_view_combo.currentData() or "heat_points") if hasattr(self, "acq_view_combo") else "heat_points"
        finite = np.isfinite(view.x) & np.isfinite(view.y) & np.isfinite(view.values)
        x = view.x[finite]
        y = view.y[finite]
        z = view.values[finite]
        invalid = view.invalid_sensor[finite]
        if not z.size:
            self.acq_plot.setTitle("No finite samples")
            return
        self.acq_plot.setLabel("bottom", "Longitude / X")
        self.acq_plot.setLabel("left", "Latitude / Y")
        self.acq_plot.setTitle(view.metric_name)
        vmin, vmax = self._acq_color_limits(z)
        normalized = np.clip((z - vmin) / (vmax - vmin if vmax > vmin else 1.0), 0.0, 1.0)

        if mode in {"heat_points", "grid"}:
            try:
                grid = MagneticAcquisitionTools.idw_grid(
                    view,
                    columns=int(self.acq_grid_cols.value()),
                    rows=int(self.acq_grid_rows.value()),
                    power=float(self.acq_idw_power.value()),
                    spread=float(self.acq_heat_spread.value()),
                )
                if grid.grid.size and np.any(np.isfinite(grid.grid)):
                    image = pg.ImageItem(grid.grid.T)
                    image.setOpacity(0.58 if mode == "heat_points" else 0.86)
                    if grid.x_edges.size >= 2 and grid.y_edges.size >= 2:
                        image.setRect(QRectF(float(grid.x_edges[0]), float(grid.y_edges[0]), float(grid.x_edges[-1] - grid.x_edges[0]), float(grid.y_edges[-1] - grid.y_edges[0])))
                    self.acq_plot.addItem(image)
            except Exception:
                pass

        if mode in {"heat_points", "points"}:
            max_points = 18000
            if z.size > max_points:
                take = np.linspace(0, z.size - 1, max_points).astype(int)
                px, py, nv, inv = x[take], y[take], normalized[take], invalid[take]
            else:
                px, py, nv, inv = x, y, normalized, invalid
            try:
                cmap = pg.colormap.get("turbo")
                colors = cmap.map(nv, mode="qcolor")
                spots = []
                for sx, sy, color, is_bad in zip(px, py, colors, inv):
                    color.setAlpha(95 if is_bad else 210)
                    spots.append({"pos": (float(sx), float(sy)), "brush": color, "pen": pg.mkPen("#111111", width=0.3) if is_bad else None, "size": 4 if not is_bad else 3})
                self.acq_plot.addItem(pg.ScatterPlotItem(spots=spots))
            except Exception:
                self.acq_plot.addItem(pg.ScatterPlotItem(px, py, size=4, pen=None, brush=pg.mkBrush(20, 120, 170, 150)))

        if mode in {"heat_points", "track"}:
            segments = MagneticAcquisitionTools.segmented_track(view, gap_factor=float(self.acq_gap_factor.value()))
            for segment in segments[:200]:
                if segment.size >= 2:
                    self.acq_plot.plot(view.x[segment], view.y[segment], pen=pg.mkPen("#0B5D84", width=1.0))

        polygon = self._acq_current_polygon()
        if polygon is not None:
            closed = np.vstack([polygon, polygon[0]])
            self.acq_plot.plot(closed[:, 0], closed[:, 1], pen=pg.mkPen("#E67E22", width=2.2))
        elif self._acq_polygon_points:
            pts = np.asarray(self._acq_polygon_points, dtype=float)
            self.acq_plot.plot(pts[:, 0], pts[:, 1], pen=pg.mkPen("#E67E22", width=1.5), symbol="o", symbolSize=6, symbolBrush="#E67E22")

        self.acq_plot.enableAutoRange()

    def _acq_color_limits(self, values: np.ndarray) -> tuple[float, float]:
        values = values[np.isfinite(values)]
        if values.size == 0:
            return 0.0, 1.0
        mode = str(self.acq_color_mode.currentData() or "robust") if hasattr(self, "acq_color_mode") else "robust"
        if mode == "manual":
            try:
                low = float(self.acq_color_min.text())
                high = float(self.acq_color_max.text())
                if np.isfinite(low) and np.isfinite(high) and high > low:
                    return low, high
            except Exception:
                pass
        if mode == "full":
            low, high = float(np.nanmin(values)), float(np.nanmax(values))
        else:
            low, high = float(np.nanpercentile(values, 2.0)), float(np.nanpercentile(values, 98.0))
        if not np.isfinite(low) or not np.isfinite(high) or high <= low:
            mean = float(np.nanmean(values))
            return mean - 1.0, mean + 1.0
        return low, high

    def _populate_acq_sample_table(self, view) -> None:
        max_rows = min(500, int(view.indices.size))
        self.acq_sample_table.setRowCount(max_rows)
        segments = MagneticAcquisitionTools.segmented_track(view, gap_factor=float(self.acq_gap_factor.value())) if view.indices.size else []
        segment_lookup: dict[int, int] = {}
        for seg_id, segment in enumerate(segments, start=1):
            for local_index in segment:
                segment_lookup[int(local_index)] = seg_id
        for row in range(max_rows):
            global_index = int(view.indices[row])
            values = [
                global_index,
                str(view.timestamps[row]),
                self._format_number(view.x[row]),
                self._format_number(view.y[row]),
                self._format_number(view.z[row]),
                self._format_number(view.values[row]),
                "YES" if view.invalid_sensor[row] else "NO",
                segment_lookup.get(row, "—"),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 6 and str(value) == "YES":
                    item.setForeground(QColor("#B42318"))
                self.acq_sample_table.setItem(row, col, item)
        self.acq_sample_table.resizeRowsToContents()

    def _toggle_acq_polygon_drawing(self) -> None:
        self._acq_drawing_polygon = not self._acq_drawing_polygon
        mode = "ON" if self._acq_drawing_polygon else "OFF"
        self._set_status(f"Acquisition polygon drawing {mode}. Click the quick-view map to add vertices.", "ready")
        self._refresh_acq_filter_label()

    def _on_acq_plot_clicked(self, event: Any) -> None:
        if not self._acq_drawing_polygon:
            return
        try:
            if event.button() != Qt.MouseButton.LeftButton:
                return
            point = self.acq_plot.plotItem.vb.mapSceneToView(event.scenePos())
            self._acq_polygon_points.append((float(point.x()), float(point.y())))
            self._refresh_acquisition_quick_view()
        except Exception:
            return

    def _undo_acq_polygon_point(self) -> None:
        if self._acq_polygon_points:
            self._acq_polygon_points.pop()
        self._refresh_acquisition_quick_view()

    def _reset_acq_polygon(self) -> None:
        self._acq_polygon_points.clear()
        self._acq_drawing_polygon = False
        self._refresh_acquisition_quick_view()

    def _set_acq_polygon_mode(self, mode: str) -> None:
        self._acq_polygon_mode = "reject" if mode == "reject" else "keep"
        self._refresh_acquisition_quick_view()

    def _refresh_acq_filter_label(self) -> None:
        if not hasattr(self, "acq_filter_label"):
            return
        vertices = len(self._acq_polygon_points)
        if vertices < 3:
            drawing = "drawing on" if self._acq_drawing_polygon else "drawing off"
            self.acq_filter_label.setText(f"No active polygon • {vertices} vertices • {drawing}")
        else:
            self.acq_filter_label.setText(f"Polygon filter active • {vertices} vertices • mode: {self._acq_polygon_mode.upper()}")

    def export_acq_filtered_csv(self) -> None:
        dataset = self._display_dataset()
        if dataset is None:
            QMessageBox.information(self, "Export Filtered CSV", "Load magnetic data first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export filtered magnetic samples",
            str(Path(dataset.source_path).with_suffix(".filtered_samples.csv")),
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        try:
            output = MagneticAcquisitionTools.export_filtered_csv(
                dataset,
                path,
                metric=self._acq_current_metric(),
                include_invalid=self.acq_include_invalid.isChecked(),
                polygon=self._acq_current_polygon(),
                polygon_mode=self._acq_polygon_mode,  # type: ignore[arg-type]
            )
            self._set_status(f"Filtered samples exported: {output}", "ready")
        except Exception as exc:
            QMessageBox.critical(self, "Export Filtered CSV", str(exc))

    def export_acq_html_map(self) -> None:
        dataset = self._display_dataset()
        if dataset is None:
            QMessageBox.information(self, "Export HTML Map", "Load magnetic data first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export interactive magnetic HTML map",
            str(Path(dataset.source_path).with_suffix(".magnetic_map.html")),
            "HTML files (*.html);;All files (*)",
        )
        if not path:
            return
        try:
            output = MagneticAcquisitionTools.export_leaflet_html(
                dataset,
                path,
                metric=self._acq_current_metric(),
                include_invalid=self.acq_include_invalid.isChecked(),
                polygon=self._acq_current_polygon(),
                polygon_mode=self._acq_polygon_mode,  # type: ignore[arg-type]
            )
            self._set_status(f"Interactive HTML map exported: {output}", "ready")
        except Exception as exc:
            QMessageBox.critical(self, "Export HTML Map", str(exc))

    @staticmethod
    def _format_number(value: Any, suffix: str = "") -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "—"
        if not np.isfinite(number):
            return "—"
        return f"{number:,.6g}{suffix}"


    def _display_dataset(self) -> MagneticDataset | None:
        """Dataset currently available for visual review.

        Rover data remains the QC primary dataset, but a base-only file must still
        open visibly instead of appearing to do nothing.
        """
        return self.rover if self.rover is not None else self.base

    def _action_card(
        self,
        title: str,
        description: str,
        actions: list[tuple[str, Any]],
    ) -> QWidget:
        card = QFrame()
        card.setObjectName("magActionCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)
        heading = QLabel(title)
        heading.setObjectName("magSectionTitle")
        text = QLabel(description)
        text.setObjectName("magSectionHelp")
        text.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(text)
        layout.addStretch(1)
        for label, handler in actions:
            button = QPushButton(label)
            button.clicked.connect(handler)
            layout.addWidget(button)
        return card

    # ------------------------------------------------------------------
    # Long-running activity helpers
    # ------------------------------------------------------------------

    def _begin_activity(self, title: str, message: str) -> None:
        self.activity_started.emit(str(title), str(message))
        QApplication.processEvents()

    def _update_activity(self, progress: int, message: str) -> None:
        self.activity_progress.emit(max(0, min(100, int(progress))), str(message))
        QApplication.processEvents()

    def _finish_activity(self) -> None:
        self.activity_finished.emit()
        QApplication.processEvents()

    def _run_background(
        self,
        function: Callable[[Callable[[int, str], None]], Any],
        on_result: Callable[[Any], None],
        title: str,
        detail: str,
        *,
        finish_before_result: bool = False,
    ) -> None:
        worker = _MagneticRunnable(function)
        self._active_workers.add(worker)
        self._background_busy_count += 1
        self._begin_activity(title, detail)
        worker.signals.progress.connect(self._update_activity)
        worker.signals.result.connect(
            lambda result, active_worker=worker: self._background_success(
                active_worker, on_result, result, finish_before_result
            )
        )
        worker.signals.error.connect(
            lambda text, active_worker=worker: self._background_error(active_worker, title, text)
        )
        self._thread_pool.start(worker)

    def _background_success(
        self,
        worker: _MagneticRunnable,
        on_result: Callable[[Any], None],
        result: Any,
        finish_before_result: bool,
    ) -> None:
        if finish_before_result:
            self._release_worker(worker)
        try:
            on_result(result)
        except Exception as exc:
            if not finish_before_result:
                self._release_worker(worker)
            QMessageBox.critical(self, "Magnetic Processing Error", str(exc))
            return
        if not finish_before_result:
            self._release_worker(worker)

    def _background_error(self, worker: _MagneticRunnable, title: str, traceback_text: str) -> None:
        self._release_worker(worker)
        message = traceback_text.strip().splitlines()[-1] if traceback_text.strip() else "Unknown error"
        QMessageBox.critical(self, title, message)

    def _release_worker(self, worker: _MagneticRunnable) -> None:
        self._active_workers.discard(worker)
        self._background_busy_count = max(0, self._background_busy_count - 1)
        if self._background_busy_count == 0:
            self._finish_activity()

    # ------------------------------------------------------------------
    # Public actions used by the ribbon/main window
    # ------------------------------------------------------------------

    def open_rover(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Magnetic Data",
            str(Path.home()),
            "Magnetic data (*.csv *.txt *.dat *.log *.xyz);;All files (*)",
        )
        if not path:
            return
        self._inspect_rover_path(path)

    def open_rover_path(self, path: str | Path, *, show_import_dialog: bool = False) -> None:
        """Open a rover file supplied by Project Explorer/import workflows.

        Direct project imports use automatic schema detection; the ribbon's Open
        Data action still presents the detailed import dialog after inspection.
        """
        resolved = str(Path(path).expanduser().resolve())
        if show_import_dialog:
            self._inspect_rover_path(resolved)
            return
        self._load_rover_background(resolved, survey_type=None, crs=None)

    def _inspect_rover_path(self, path: str) -> None:
        self._run_background(
            lambda report: self._inspect_magnetic_file(path, report, role="rover"),
            lambda inspection: self._show_rover_import_dialog(path, inspection),
            "Inspecting Magnetic File",
            f"Detecting format and acquisition metadata for {Path(path).name}",
            finish_before_result=True,
        )

    @staticmethod
    def _inspect_magnetic_file(
        path: str,
        report: Callable[[int, str], None],
        *,
        role: str,
    ) -> dict[str, Any]:
        report(10, "Detecting magnetic file format")
        reader = MagneticReader()
        if role == "base":
            result = reader.inspect(path, role="base", survey_type="base_station")
        else:
            result = reader.inspect(path)
        report(100, "Magnetic file inspection complete")
        return result

    def _show_rover_import_dialog(self, path: str, inspection: dict[str, Any]) -> None:
        dialog = MagneticImportDialog(inspection, importing_base=False, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._load_rover_background(
            path,
            survey_type=dialog.selected_survey_type,
            crs=dialog.selected_crs,
        )

    def _load_rover_background(
        self,
        path: str,
        *,
        survey_type: Any = None,
        crs: Any = None,
    ) -> None:
        def load(report: Callable[[int, str], None]) -> MagneticDataset:
            report(5, "Opening magnetic dataset")
            options: dict[str, Any] = {}
            if survey_type is not None:
                options["survey_type"] = survey_type
            if crs not in (None, ""):
                options["crs"] = crs
            dataset = MagneticReader().read_rover(path, **options)
            report(62, f"Parsed {dataset.record_count:,} magnetic records")
            return dataset

        self._run_background(
            load,
            lambda dataset: self._accept_rover_dataset(path, dataset),
            "Loading Magnetic Data",
            f"Reading and preparing {Path(path).name}",
        )

    def _accept_rover_dataset(self, path: str, dataset: MagneticDataset) -> None:
        self.rover = dataset
        self.processing_products.clear()
        self.latest_result = None
        self._all_findings.clear()
        self._clear_results()
        self._refresh_dataset_views_with_progress(62)

        classification = str(self.rover.metadata.get("acquisition_classification", "moving"))
        if classification == "stationary":
            message = (
                f"Loaded {self.rover.record_count:,} records from {Path(path).name}. "
                "Stationary/static acquisition detected; non-applicable line, tie and grid QC will skip."
            )
        else:
            message = f"Loaded {self.rover.record_count:,} magnetic records from {Path(path).name}."
        self._set_status(message, "ready")
        self.dataset_changed.emit(self.rover)
        self.tabs.setCurrentIndex(self.TAB_OVERVIEW)

    def open_base(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Magnetic Base-Station Data",
            str(Path.home()),
            "Magnetic data (*.csv *.txt *.dat *.log *.xyz);;All files (*)",
        )
        if not path:
            return
        self._run_background(
            lambda report: self._inspect_magnetic_file(path, report, role="base"),
            lambda inspection: self._show_base_import_dialog(path, inspection),
            "Inspecting Base-Station File",
            f"Detecting format and metadata for {Path(path).name}",
            finish_before_result=True,
        )

    def _show_base_import_dialog(self, path: str, inspection: dict[str, Any]) -> None:
        dialog = MagneticImportDialog(inspection, importing_base=True, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected_crs = dialog.selected_crs

        def load(report: Callable[[int, str], None]) -> MagneticDataset:
            report(10, "Reading base-station records")
            dataset = MagneticReader().read_base(path, crs=selected_crs)
            report(70, f"Parsed {dataset.record_count:,} base-station records")
            return dataset

        self._run_background(
            load,
            lambda dataset: self._accept_base_dataset(path, dataset),
            "Loading Base-Station Data",
            f"Reading and preparing {Path(path).name}",
        )

    def _accept_base_dataset(self, path: str, dataset: MagneticDataset) -> None:
        self.base = dataset
        self._refresh_dataset_views_with_progress(70)
        self._set_status(
            f"Loaded {self.base.record_count:,} base-station records from {Path(path).name}.",
            "ready",
        )
        # A base-only survey is still a valid viewable magnetic dataset. Emitting
        # this signal refreshes ribbon prerequisites and switching to Overview
        # makes the load visibly successful instead of appearing to do nothing.
        self.dataset_changed.emit(self.base)
        self.tabs.setCurrentIndex(self.TAB_OVERVIEW)

    def open_boundary(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Survey Boundary",
            str(Path.home()),
            "Boundaries (*.kml *.kmz *.geojson *.json *.csv *.txt *.xyz);;All files (*)",
        )
        if not path:
            return

        def load(report: Callable[[int, str], None]) -> MagneticBoundary:
            report(20, "Reading survey boundary")
            boundary = MagneticBoundaryReader().read(path)
            report(75, "Preparing boundary geometry")
            return boundary

        self._run_background(
            load,
            lambda boundary: self._accept_boundary(path, boundary),
            "Loading Survey Boundary",
            f"Reading {Path(path).name}",
        )

    def _accept_boundary(self, path: str, boundary: MagneticBoundary) -> None:
        self.boundary = boundary
        self._update_activity(82, "Updating magnetic dashboard")
        self._refresh_dataset_views()
        self._update_activity(100, "Survey boundary is ready")
        self._set_status(f"Loaded boundary {self.boundary.name}.", "ready")

    def run_full_qc(self) -> None:
        self._run_qc(None)

    def run_raw_qc(self) -> None:
        self._run_qc(RAW_STAGE_KEYS)

    def run_processed_qc(self) -> None:
        self._run_qc(PROCESSED_STAGE_KEYS)

    def cancel_qc(self) -> None:
        self.controller.cancel()

    def process_despike(self) -> None:
        if not self._require_rover():
            return
        factor, accepted = QInputDialog.getDouble(
            self,
            "Despike",
            "Robust outlier factor:",
            6.0,
            2.0,
            20.0,
            1,
        )
        if not accepted:
            return

        def process(report: Callable[[int, str], None]):
            report(10, "Detecting magnetic spikes and outliers")
            mask = self.processing.despike(self.rover, outlier_factor=factor)
            report(65, "Despike processing complete")
            return mask

        self._run_background(
            process,
            lambda mask: self._accept_despike(mask),
            "Despiking Magnetic Data",
            "Applying robust magnetic outlier detection",
        )

    def _accept_despike(self, mask: Any) -> None:
        self._append_processing(
            f"Despike created {DESPIKED_TOTAL_FIELD}; replaced {np.count_nonzero(mask):,} records."
        )
        self._refresh_dataset_views_with_progress(65)

    def process_diurnal(self) -> None:
        if not self._require_rover():
            return
        if self.base is None:
            QMessageBox.information(
                self,
                "Diurnal Correction",
                "Load a separate base-station dataset first. A single rover/static file is not treated as a simultaneous base survey.",
            )
            return
        maximum_gap, accepted = QInputDialog.getDouble(
            self,
            "Diurnal Correction",
            "Maximum supported base gap (seconds):",
            30.0,
            1.0,
            3600.0,
            1,
        )
        if not accepted:
            return

        def process(report: Callable[[int, str], None]):
            report(10, "Interpolating base-station magnetic field")
            self.processing.apply_diurnal_correction(
                self.rover,
                self.base,
                maximum_gap_s=maximum_gap,
            )
            report(65, "Diurnal correction complete")
            return maximum_gap

        self._run_background(
            process,
            self._accept_diurnal,
            "Applying Diurnal Correction",
            "Correcting rover data from the base-station record",
        )

    def _accept_diurnal(self, maximum_gap: float) -> None:
        self._append_processing(
            f"Created {DIURNAL_CORRECTED_FIELD} using base interpolation with {maximum_gap:.1f} s maximum gap."
        )
        self._refresh_dataset_views_with_progress(65)

    def process_leveling(self) -> None:
        if not self._require_rover():
            return

        classification = str(self.rover.metadata.get("acquisition_classification", "moving")).strip().lower()
        if classification in {"stationary", "static", "base", "base_station"}:
            QMessageBox.information(
                self,
                "Line Leveling Not Applicable",
                "This dataset is classified as stationary/static acquisition. Line leveling requires "
                "multiple survey lines (normally traverse and tie/control lines), so no leveling correction "
                "is scientifically valid for this file. Use despiking/diurnal correction as applicable, or "
                "load a moving line-survey dataset with line identifiers.",
            )
            return
        groups = self.rover.line_groups()
        if len(groups) < 2:
            QMessageBox.information(
                self,
                "Line Identifiers Required",
                "Line leveling needs at least two valid survey-line identifiers. No correction was applied.\n\n"
                "Re-import the dataset and map the line/flight-line column, or load a dataset that contains "
                "traverse/tie-line identifiers. TGPAssure will not invent line IDs because doing so can remove "
                "real geological gradients.",
            )
            return

        def process(report: Callable[[int, str], None]):
            report(10, "Calculating line and tie corrections")
            corrections = self.processing.level_lines(self.rover)
            report(65, "Line leveling complete")
            return corrections

        self._run_background(
            process,
            self._accept_leveling,
            "Leveling Magnetic Lines",
            "Calculating and applying line/tie corrections",
        )

    def _accept_leveling(self, corrections: dict[Any, Any]) -> None:
        maximum = max((abs(value) for value in corrections.values()), default=0.0)
        self._append_processing(
            f"Created {LEVELED_FIELD}; applied corrections to {len(corrections)} lines. "
            f"Maximum correction: {maximum:.2f} nT."
        )
        self._refresh_dataset_views_with_progress(65)

    def process_microlevel(self) -> None:
        if not self._require_rover():
            return
        if LEVELED_FIELD not in self.rover.channels:
            QMessageBox.information(self, "Microlevel", "Run line leveling first.")
            return

        def process(report: Callable[[int, str], None]):
            report(10, "Calculating residual line-level corrections")
            corrections = self.processing.microlevel(self.rover)
            report(65, "Microlevel correction complete")
            return corrections

        self._run_background(
            process,
            self._accept_microlevel,
            "Microleveling Magnetic Data",
            "Removing residual line-to-line artifacts",
        )

    def _accept_microlevel(self, corrections: dict[Any, Any]) -> None:
        self._append_processing(
            f"Created {MICROLEVELED_FIELD}; bounded microlevel corrections calculated for {len(corrections)} lines."
        )
        self._refresh_dataset_views_with_progress(65)

    def generate_grid(self) -> None:
        if not self._require_rover():
            return
        cell_size, accepted = QInputDialog.getDouble(
            self,
            "Magnetic Grid",
            "Grid cell size (metres):",
            25.0,
            0.01,
            100000.0,
            2,
        )
        if not accepted:
            return

        def process(report: Callable[[int, str], None]):
            report(10, "Interpolating magnetic grid")
            grid = self.processing.grid(self.rover, cell_size=cell_size)
            report(90, "Finalizing grid product")
            return grid

        self._run_background(
            process,
            self._accept_grid,
            "Generating Magnetic Grid",
            f"Interpolating a {cell_size:g} m grid",
        )

    def _accept_grid(self, grid: dict[str, Any]) -> None:
        self.processing_products["grid"] = grid
        self._append_processing(
            f"Generated {grid['values'].shape[1]} × {grid['values'].shape[0]} magnetic grid from {grid['source_channel']}."
        )
        self._update_activity(100, "Magnetic grid is ready")

    def export_csv(self) -> None:
        if not self._require_rover():
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Magnetic Data",
            str(Path.home() / "magnetic_processed.csv"),
            "CSV files (*.csv)",
        )
        if not path:
            return

        def process(report: Callable[[int, str], None]):
            report(10, "Writing magnetic records to CSV")
            output = self.processing.export_csv(self.rover, path)
            report(100, "CSV export complete")
            return output

        self._run_background(
            process,
            lambda output: self._set_status(f"Exported magnetic dataset to {output}", "pass"),
            "Exporting Magnetic Data",
            f"Writing {Path(path).name}",
        )

    def generate_report(self, fmt: str) -> None:
        if self.latest_result is None:
            QMessageBox.information(self, "Magnetic Report", "Run magnetic QC before generating a report.")
            return
        extension = ".pdf" if fmt == "pdf" else ".xlsx"
        from ui.dialogs.report_dialog import ReportDialog
        dialog = ReportDialog(
            self, default_format=fmt, default_title="Magnetic Quality-Control Report",
            suggested_path=Path.home() / f"magnetic_qc_report{extension}", allow_format_change=False,
        )
        if not dialog.exec():
            return
        config = dialog.get_report_config()
        path = str(config.output_path)
        result_payload = dict(self.latest_result)

        def process(report: Callable[[int, str], None]):
            report(10, "Building report tables and graphs")
            from report.report_builders.magnetic_qc_report_builder import MagneticQcReportBuilder

            output = MagneticQcReportBuilder().build(result_payload, path, fmt)
            report(100, "Magnetic QC report complete")
            return output

        self._run_background(
            process,
            lambda output: self._set_status(f"Magnetic QC report saved to {output}", "pass"),
            "Generating Magnetic QC Report",
            f"Creating {fmt.upper()} report with graphs",
        )

    def can_execute(self, action_id: str) -> bool:
        has_data = self.rover is not None
        has_result = self.latest_result is not None
        running = getattr(self.controller, "active_job_id", None) is not None
        if action_id in {"magnetic_open", "magnetic_open_rover", "magnetic_open_base", "magnetic_open_boundary"}:
            return True
        if action_id == "magnetic_cancel":
            return running
        if action_id in {"magnetic_run_full", "magnetic_run_raw", "magnetic_run_processed"}:
            return has_data and not running
        if action_id == "magnetic_diurnal":
            return has_data and self.base is not None
        if action_id in {"magnetic_report_pdf", "magnetic_report_xlsx"}:
            return has_result
        if action_id in {"magnetic_view_2d", "magnetic_view_3d", "magnetic_satellite", "magnetic_terrain"}:
            return self._display_dataset() is not None
        if action_id in {"magnetic_despike", "magnetic_level", "magnetic_microlevel", "magnetic_grid", "magnetic_map", "magnetic_profile", "magnetic_export_csv"}:
            return has_data
        return True

    def show_map(self) -> None:
        dataset = self._display_dataset()
        if dataset is not None and not bool(np.any(dataset.valid_coordinate_mask())):
            # Base-station exports commonly contain only time + field.  Treat that
            # as a valid 2D dataset and show the physically meaningful time
            # profile instead of opening an empty XY map.
            self.tabs.setCurrentIndex(self.TAB_PROFILES)
            self._begin_activity("Rendering Magnetic Profile", "No valid XY coordinates; preparing time/record profile")
            try:
                self._update_activity(35, "Preparing base/rover profile samples")
                self._refresh_profile()
                self._set_status("No valid XY coordinates were supplied; showing the magnetic 2D time/profile view instead.", "ready")
                self._update_activity(100, "Magnetic profile is ready")
            finally:
                self._finish_activity()
            return

        self.tabs.setCurrentIndex(self.TAB_MAP)
        self._begin_activity("Rendering Magnetic Map", "Preparing map points and magnetic color scale")
        try:
            self._update_activity(35, "Preparing magnetic map points")
            self._refresh_map()
            self._update_activity(100, "Magnetic map is ready")
        finally:
            self._finish_activity()

    def show_profile(self) -> None:
        self.tabs.setCurrentIndex(self.TAB_PROFILES)
        self._begin_activity("Rendering Magnetic Profile", "Preparing line profile and channel samples")
        try:
            self._update_activity(35, "Preparing profile samples")
            self._refresh_profile()
            self._update_activity(100, "Magnetic profile is ready")
        finally:
            self._finish_activity()

    def show_native_view(self, mode: str = "2d") -> None:
        dataset = self._display_dataset()
        if dataset is None:
            QMessageBox.information(self, "Magnetic Visualization", "Load rover or base-station magnetic data first.")
            return
        if not bool(np.any(dataset.valid_coordinate_mask())):
            self.show_profile()
            self._set_status("Native 2D/3D spatial view requires valid XY coordinates; showing the time/profile view instead.", "ready")
            return
        self.tabs.setCurrentIndex(self.TAB_SPATIAL)
        self._refresh_native_spatial()
        self.native_spatial_view.set_mode("3d" if str(mode).lower().startswith("3") else "2d")

    def show_geospatial_view(self, mode: str = "2d") -> None:
        dataset = self._display_dataset()
        if dataset is None:
            QMessageBox.information(self, "Magnetic Visualization", "Load rover or base-station magnetic data first.")
            return
        self.tabs.setCurrentIndex(self.TAB_GEOSPATIAL)
        self._refresh_geospatial()
        self.geospatial_view.set_mode("3d" if str(mode).lower().startswith("3") else "2d")

    # ------------------------------------------------------------------
    # QC execution
    # ------------------------------------------------------------------

    def _run_qc(self, stages: Iterable[str] | None) -> None:
        if self.rover is None:
            QMessageBox.information(self, "Magnetic QC", "Load a primary magnetic dataset first.")
            return
        try:
            self.controller.run_qc(
                self.rover,
                base=self.base,
                boundary=self.boundary,
                profile_name=str(self.profile_combo.currentData()),
                selected_stage_keys=stages,
                processing_products=self.processing_products,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Magnetic QC Error", str(exc))

    def _connect_controller(self) -> None:
        self.controller.run_started.connect(self._on_run_started)
        self.controller.progress_changed.connect(self._on_progress)
        self.controller.run_completed.connect(self._on_run_completed)
        self.controller.run_failed.connect(self._on_run_failed)
        self.controller.run_cancelled.connect(self._on_run_cancelled)

    def _on_run_started(self, _job_id: int) -> None:
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setValue(0)
        self._set_status("Magnetic QC started.", "running")

    def _on_progress(self, current: int, total: int, message: str) -> None:
        self.progress.setValue(round(100 * current / max(total, 1)))
        self.status_label.setText(message)

    def _on_run_completed(self, result: dict) -> None:
        self.latest_result = result
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress.setValue(100)
        status = str(result.get("status", "unknown")).lower()
        score = float(result.get("score", 0.0) or 0.0)
        self._set_status(f"Magnetic QC complete: {status.upper()} — score {score:.1f}", status)
        self._populate_results(result)
        self._refresh_metrics()
        self.tabs.setCurrentIndex(self.TAB_QC)

    def _on_run_failed(self, error: str) -> None:
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self._set_status("Magnetic QC failed.", "fail")
        QMessageBox.critical(self, "Magnetic QC Error", error)

    def _on_run_cancelled(self) -> None:
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self._set_status("Magnetic QC cancelled.", "cancelled")

    # ------------------------------------------------------------------
    # Refresh / presentation
    # ------------------------------------------------------------------

    def _refresh_dataset_views(self) -> None:
        self._refresh_metrics()
        self._refresh_primary_table()
        self._refresh_base_boundary_table()
        self._refresh_metadata_table()
        self._refresh_channels_table()
        self._refresh_records_preview()
        self._refresh_channel_combos()
        self._refresh_acquisition_quick_view()
        self._refresh_provenance()
        self._refresh_map()
        self._refresh_profile()
        self._refresh_native_spatial()
        self._refresh_geospatial()

    def _refresh_dataset_views_with_progress(self, start_progress: int = 60) -> None:
        """Refresh the heavy dashboard views while keeping the global loader alive."""
        steps = (
            (self._refresh_metrics, "Calculating dataset statistics"),
            (self._refresh_primary_table, "Updating dataset summary"),
            (self._refresh_base_boundary_table, "Updating support-data summary"),
            (self._refresh_metadata_table, "Preparing metadata table"),
            (self._refresh_channels_table, "Calculating channel statistics"),
            (self._refresh_records_preview, "Preparing records preview"),
            (self._refresh_channel_combos, "Preparing channel controls"),
            (self._refresh_acquisition_quick_view, "Preparing acquisition quick view"),
            (self._refresh_provenance, "Updating provenance details"),
            (self._refresh_map, "Rendering magnetic map"),
            (self._refresh_profile, "Rendering magnetic profile"),
            (self._refresh_native_spatial, "Preparing native 2D / 3D data view"),
            (self._refresh_geospatial, "Preparing satellite / terrain geometry"),
        )
        start = max(0, min(90, int(start_progress)))
        span = max(1, 98 - start)
        for index, (callback, message) in enumerate(steps, start=1):
            progress = start + round(span * (index - 1) / max(1, len(steps)))
            self._update_activity(progress, message)
            callback()
        self._update_activity(100, "Magnetic dataset is ready")

    def _refresh_metrics(self) -> None:
        dataset = self._display_dataset()
        if dataset is None:
            self.dataset_badge.setText("NO DATASET")
            self.metric_records.set_value("—", "Load magnetic data")
            self.metric_field.set_value("—", "No magnetic channel")
            self.metric_spatial.set_value("—", "No coordinates")
            self.metric_support.set_value("—", "Base / boundary optional")
            self.metric_qc.set_value("—", "No QC run")
            if hasattr(self, "overview_summary"):
                self.overview_summary.setText("No magnetic dataset loaded. Use Open Data to begin.")
            self._refresh_stats_details()
            return

        filename = Path(dataset.source_path).name
        self.dataset_badge.setText(filename)
        self.dataset_badge.setToolTip(str(dataset.source_path))
        classification = str(dataset.metadata.get("acquisition_classification", dataset.survey_type.value))
        self.metric_records.set_value(f"{dataset.record_count:,}", self._humanize(classification))

        channel_name = (
            RAW_TOTAL_FIELD
            if RAW_TOTAL_FIELD in dataset.channels
            else BASE_TOTAL_FIELD
            if BASE_TOTAL_FIELD in dataset.channels
            else next(iter(dataset.channels), "")
        )
        if channel_name:
            values = np.asarray(dataset.channels[channel_name], dtype=float)
            finite = values[np.isfinite(values)]
            if finite.size:
                field_mean = float(np.mean(finite))
                field_range = float(np.max(finite) - np.min(finite))
                self.metric_field.set_value(
                    f"{field_mean:,.2f} {dataset.magnetic_units}",
                    f"Range Δ {field_range:,.2f} {dataset.magnetic_units}",
                )
            else:
                self.metric_field.set_value("No valid values", channel_name)
        else:
            self.metric_field.set_value("—", "No channel")

        coordinate_mask = dataset.valid_coordinate_mask()
        valid_pct = 100.0 * float(np.count_nonzero(coordinate_mask)) / max(dataset.record_count, 1)
        crs_label = dataset.crs or "CRS not set"
        self.metric_spatial.set_value(crs_label, f"{valid_pct:.1f}% valid coordinates")

        support = []
        if self.base is not None:
            support.append("Base")
        if self.boundary is not None:
            support.append("Boundary")
        self.metric_support.set_value(" + ".join(support) if support else "None", "Optional support data")

        if self.latest_result:
            status = str(self.latest_result.get("status", "unknown")).upper()
            score = float(self.latest_result.get("score", 0.0) or 0.0)
            self.metric_qc.set_value(status, f"Score {score:.1f} / 100")
        else:
            self.metric_qc.set_value("Not run", "Choose a QC profile")

        if hasattr(self, "overview_summary"):
            start, end = dataset.time_bounds()
            summary = (
                f"{filename}  •  {dataset.record_count:,} records  •  "
                f"{self._humanize(classification)}  •  {dataset.crs or 'CRS not set'}"
            )
            if start and end:
                summary += f"  •  {start} to {end}"
            self.overview_summary.setText(summary)
        self._refresh_stats_details()

    def _refresh_stats_details(self) -> None:
        if not hasattr(self, "stats_details"):
            return
        dataset = self._display_dataset()
        if dataset is None:
            self.stats_details.setRowCount(0)
            return
        rows: list[tuple[str, Any, str]] = []
        classification = str(dataset.metadata.get("acquisition_classification", dataset.survey_type.value))
        rows.append(("Acquisition class", self._humanize(classification), "Controls which QC and processing operations are applicable."))
        rows.append(("Record count", f"{dataset.record_count:,}", "Total imported magnetic observations."))
        start, end = dataset.time_bounds()
        rows.append(("Time span", f"{start or '—'}  to  {end or '—'}", "Acquisition time coverage after timestamp parsing."))
        line_count = len(dataset.line_groups())
        rows.append(("Valid line identifiers", line_count, "Line leveling requires at least two valid survey lines; tie/control lines are preferred."))
        valid_xy = int(np.count_nonzero(dataset.valid_coordinate_mask()))
        rows.append(("Valid coordinates", f"{valid_xy:,} / {dataset.record_count:,}", "Finite XY/longitude-latitude coordinate pairs available for spatial QC."))
        for name, values in dataset.channels.items():
            arr = np.asarray(values, dtype=float)
            finite = arr[np.isfinite(arr)]
            if not finite.size:
                continue
            rows.append((f"{name}: mean", f"{float(np.mean(finite)):.6g}", "Arithmetic mean of finite samples."))
            rows.append((f"{name}: standard deviation", f"{float(np.std(finite)):.6g}", "Population standard deviation of finite samples."))
            rows.append((f"{name}: robust spread", f"{float(np.nanpercentile(finite, 95)-np.nanpercentile(finite, 5)):.6g}", "95th–5th percentile range; less sensitive to extreme spikes than full range."))
        self.stats_details.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.stats_details.setItem(r, c, item)

    def _refresh_primary_table(self) -> None:
        dataset = self._display_dataset()
        if dataset is None:
            self._set_key_value_rows(self.primary_table, [("Dataset", "No magnetic dataset loaded")])
            return
        start, end = dataset.time_bounds()
        bounds = dataset.bounds()
        rows = [
            ("File", str(dataset.source_path)),
            ("Role", self._humanize(dataset.role.value)),
            ("Survey type", self._humanize(dataset.survey_type.value)),
            ("Acquisition classification", self._humanize(dataset.metadata.get("acquisition_classification", "—"))),
            ("Records", f"{dataset.record_count:,}"),
            ("Channels", ", ".join(dataset.channel_names)),
            ("Magnetic units", dataset.magnetic_units),
            ("Coordinate units", dataset.coordinate_units),
            ("Source CRS", dataset.crs or "Not defined"),
            ("Start time", start or "—"),
            ("End time", end or "—"),
            ("Minimum X / Longitude", bounds.get("min_x")),
            ("Maximum X / Longitude", bounds.get("max_x")),
            ("Minimum Y / Latitude", bounds.get("min_y")),
            ("Maximum Y / Latitude", bounds.get("max_y")),
        ]
        self._set_key_value_rows(self.primary_table, rows)

    def _refresh_base_boundary_table(self) -> None:
        rows: list[tuple[str, Any]] = []
        if self.base is None:
            rows.extend(
                [
                    ("Base station", "Not loaded"),
                    ("Base-dependent QC", "Will be skipped where a separate base survey is required"),
                ]
            )
        else:
            start, end = self.base.time_bounds()
            rows.extend(
                [
                    ("Base station file", str(self.base.source_path)),
                    ("Base records", f"{self.base.record_count:,}"),
                    ("Base CRS", self.base.crs or "Not defined"),
                    ("Base start", start or "—"),
                    ("Base end", end or "—"),
                ]
            )
        if self.boundary is None:
            rows.extend(
                [
                    ("Survey boundary", "Not loaded"),
                    ("Boundary QC", "Will be skipped"),
                ]
            )
        else:
            rows.extend(
                [
                    ("Boundary", self.boundary.name),
                    ("Boundary CRS", self.boundary.crs or "Not defined"),
                    ("Boundary vertices", int(self.boundary.vertices.shape[0])),
                ]
            )
        self._set_key_value_rows(self.base_table, rows)

    def _refresh_metadata_table(self) -> None:
        dataset = self._display_dataset()
        if dataset is None:
            self._set_key_value_rows(self.metadata_table, [("Metadata", "No dataset loaded")])
            return
        metadata = dataset.metadata or {}
        rows: list[tuple[str, Any]] = []
        preferred = (
            "format",
            "reader",
            "log_name",
            "remark",
            "sensor_serial",
            "sensor_serial_number",
            "logger_serial",
            "gps_rate_hz",
            "gps_fix_type",
            "gps_dop_hdop",
            "recommended_working_crs",
            "acquisition_classification",
        )
        seen: set[str] = set()
        for key in preferred:
            if key in metadata:
                rows.append((self._humanize(key), self._display_value(metadata[key])))
                seen.add(key)
        for key in sorted(metadata):
            if key in seen:
                continue
            value = metadata[key]
            if isinstance(value, (dict, list, tuple, set)):
                value = self._display_value(value)
            rows.append((self._humanize(key), value))
        if not rows:
            rows.append(("Metadata", "No additional metadata available"))
        self._set_key_value_rows(self.metadata_table, rows)

    def _refresh_channels_table(self) -> None:
        self.channels_table.setRowCount(0)
        dataset = self._display_dataset()
        if dataset is None:
            return
        self.channels_table.setRowCount(len(dataset.channel_names))
        for row, name in enumerate(dataset.channel_names):
            values = np.asarray(dataset.channels[name], dtype=float)
            finite = values[np.isfinite(values)]
            unit = dataset.magnetic_units if name == RAW_TOTAL_FIELD or "field" in name.lower() else "—"
            valid_text = f"{finite.size:,} / {values.size:,}"
            if finite.size:
                stats: list[Any] = [
                    name,
                    unit,
                    valid_text,
                    f"{float(np.min(finite)):.6g}",
                    f"{float(np.max(finite)):.6g}",
                    f"{float(np.mean(finite)):.6g}",
                    f"{float(np.std(finite)):.6g}",
                ]
            else:
                stats = [name, unit, valid_text, "—", "—", "—", "—"]
            for col, value in enumerate(stats):
                self.channels_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.channels_table.resizeRowsToContents()

    def _refresh_records_preview(self) -> None:
        if not hasattr(self, "records_table"):
            return
        self.records_table.setRowCount(0)
        dataset = self._display_dataset()
        if dataset is None:
            return

        count = min(dataset.record_count, 500)
        self.records_table.setRowCount(count)
        channel_name = RAW_TOTAL_FIELD if RAW_TOTAL_FIELD in dataset.channels else (BASE_TOTAL_FIELD if BASE_TOTAL_FIELD in dataset.channels else next(iter(dataset.channels), ""))
        field = np.asarray(dataset.channels[channel_name], dtype=float) if channel_name else np.full(dataset.record_count, np.nan)

        for row in range(count):
            timestamp = dataset.timestamps[row]
            timestamp_text = "—" if np.isnat(timestamp) else str(timestamp)
            values = [
                row + 1,
                timestamp_text,
                self._display_value(float(dataset.x[row])) if np.isfinite(dataset.x[row]) else "—",
                self._display_value(float(dataset.y[row])) if np.isfinite(dataset.y[row]) else "—",
                self._display_value(float(dataset.elevation[row])) if np.isfinite(dataset.elevation[row]) else "—",
                self._display_value(float(field[row])) if np.isfinite(field[row]) else "—",
                str(dataset.line_id[row] or "—"),
                str(dataset.station_id[row] or "—"),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col in (0, 2, 3, 4, 5):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.records_table.setItem(row, col, item)
        self.records_table.setToolTip(
            f"Showing the first {count:,} of {dataset.record_count:,} records. Export CSV for the complete dataset."
        )

    def _refresh_channel_combos(self) -> None:
        dataset = self._display_dataset()
        channels = list(dataset.channel_names) if dataset else []
        combos = [self.map_channel_combo, self.profile_channel_combo]
        if hasattr(self, "spatial_channel_combo"):
            combos.append(self.spatial_channel_combo)
        for combo in combos:
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(channels)
            if current in channels:
                combo.setCurrentText(current)
            elif RAW_TOTAL_FIELD in channels:
                combo.setCurrentText(RAW_TOTAL_FIELD)
            elif BASE_TOTAL_FIELD in channels:
                combo.setCurrentText(BASE_TOTAL_FIELD)
            combo.blockSignals(False)

        groups = dataset.line_groups() if dataset else {}
        self.line_combo.blockSignals(True)
        self.line_combo.clear()
        self.line_combo.addItem("All records", "__all__")
        for line in sorted(groups):
            self.line_combo.addItem(line, line)
        self.line_combo.blockSignals(False)

    def _refresh_provenance(self) -> None:
        self.provenance_table.setRowCount(0)
        dataset = self._display_dataset()
        if dataset is None:
            return
        entries = list(dataset.provenance)
        self.provenance_table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            values = [
                entry.channel,
                entry.parent_channel or "—",
                entry.operation,
                entry.created_at,
                self._display_value(dict(entry.parameters)),
            ]
            for col, value in enumerate(values):
                self.provenance_table.setItem(row, col, QTableWidgetItem(str(value)))

    def _refresh_map(self) -> None:
        if not hasattr(self, "map_plot"):
            return
        self.map_plot.clear()
        dataset = self._display_dataset()
        if dataset is None or not self.map_channel_combo.currentText():
            if hasattr(self, "map_info_label"):
                self.map_info_label.setText("No dataset")
            return
        is_geographic = str(dataset.crs or "").upper() in {"EPSG:4326", "4326", "WGS84", "WGS 84"} or dataset.coordinate_units.lower() in {"deg", "degree", "degrees"}
        self.map_plot.setLabel("bottom", "Longitude" if is_geographic else "X / Easting", units="" if is_geographic else dataset.coordinate_units)
        self.map_plot.setLabel("left", "Latitude" if is_geographic else "Y / Northing", units="" if is_geographic else dataset.coordinate_units)
        if hasattr(self, "map_info_label"):
            classification = self._humanize(dataset.metadata.get("acquisition_classification", dataset.survey_type.value))
            self.map_info_label.setText(f"{dataset.record_count:,} records • {dataset.crs or 'CRS not set'} • {classification}")
        mask = dataset.valid_coordinate_mask()
        if not np.any(mask):
            self.map_plot.setTitle("No valid coordinates available")
            return

        x = np.asarray(dataset.x[mask], dtype=float)
        y = np.asarray(dataset.y[mask], dtype=float)
        values = np.asarray(dataset.channel(self.map_channel_combo.currentText())[mask], dtype=float)
        finite = np.isfinite(x) & np.isfinite(y) & np.isfinite(values)
        x, y, values = x[finite], y[finite], values[finite]
        if not values.size:
            return

        max_points = 15000
        if values.size > max_points:
            indices = np.linspace(0, values.size - 1, max_points).astype(int)
            x, y, values = x[indices], y[indices], values[indices]

        low = float(np.nanpercentile(values, 2.0))
        high = float(np.nanpercentile(values, 98.0))
        if not np.isfinite(low) or not np.isfinite(high) or high <= low:
            normalized = np.full(values.shape, 0.5)
        else:
            normalized = np.clip((values - low) / (high - low), 0.0, 1.0)

        try:
            cmap = pg.colormap.get("viridis")
            colors = cmap.map(normalized, mode="qcolor")
            spots = [
                {"pos": (float(px), float(py)), "brush": color, "pen": None, "size": 5}
                for px, py, color in zip(x, y, colors)
            ]
            scatter = pg.ScatterPlotItem(spots=spots)
        except Exception:
            scatter = pg.ScatterPlotItem(x, y, size=5, pen=None, brush=pg.mkBrush(30, 110, 165, 180))
        self.map_plot.addItem(scatter)

        if self.boundary is not None:
            vertices = self.boundary.vertices
            closed = np.vstack((vertices, vertices[0]))
            self.map_plot.plot(closed[:, 0], closed[:, 1], pen=pg.mkPen("#C0392B", width=2))

        self.map_plot.setTitle(self.map_channel_combo.currentText())
        self.map_plot.enableAutoRange()

    def _refresh_profile(self) -> None:
        if not hasattr(self, "profile_plot"):
            return
        self.profile_plot.clear()
        dataset = self._display_dataset()
        if dataset is None or not self.profile_channel_combo.currentText():
            if hasattr(self, "profile_info_label"):
                self.profile_info_label.setText("No dataset")
            return

        if hasattr(self, "profile_info_label"):
            classification = self._humanize(dataset.metadata.get("acquisition_classification", dataset.survey_type.value))
            self.profile_info_label.setText(f"{dataset.record_count:,} records • {classification}")

        selected = self.line_combo.currentData()
        if selected in (None, "__all__"):
            indices = np.arange(dataset.record_count)
            label = "All records"
        else:
            indices = dataset.line_groups().get(str(selected), np.arange(dataset.record_count))
            label = str(selected)

        values = np.asarray(dataset.channel(self.profile_channel_combo.currentText())[indices], dtype=float)
        valid = np.isfinite(values)
        if not np.any(valid):
            return

        max_points = 30000
        timestamps = dataset.timestamps[indices]
        timestamp_valid = ~np.isnat(timestamps)
        if np.any(timestamp_valid):
            raw_ms = timestamps.astype("datetime64[ms]").astype("int64").astype(float)
            first_valid = float(raw_ms[timestamp_valid][0])
            x_values = (raw_ms - first_valid) / 1000.0
            self.profile_plot.setLabel("bottom", "Elapsed time", units="s")
        else:
            x_values = np.arange(values.size, dtype=float)
            self.profile_plot.setLabel("bottom", "Record / station sequence")
        if values.size > max_points:
            sample = np.linspace(0, values.size - 1, max_points).astype(int)
            x_values = x_values[sample]
            values = values[sample]
            valid = np.isfinite(values) & np.isfinite(x_values)
        else:
            valid = valid & np.isfinite(x_values)

        self.profile_plot.plot(
            x_values[valid],
            values[valid],
            pen=pg.mkPen("#0B6FA4", width=1.2),
        )
        self.profile_plot.setTitle(f"{label} — {self.profile_channel_combo.currentText()}")
        self.profile_plot.enableAutoRange()

    def _refresh_native_spatial(self) -> None:
        if not hasattr(self, "native_spatial_view"):
            return
        dataset = self._display_dataset()
        if dataset is None:
            self.native_spatial_view.clear("Load magnetic data to enable the native 2D/3D view.")
            return
        channel = self.spatial_channel_combo.currentText() if hasattr(self, "spatial_channel_combo") else ""
        if not channel or channel not in dataset.channel_names:
            self.native_spatial_view.clear("Select a magnetic channel for scientific visualization.")
            return
        mask = dataset.valid_coordinate_mask()
        if not np.any(mask):
            self.native_spatial_view.clear("No finite XY coordinates are available. Base-only time series remain available in Profiles.")
            return
        x = np.asarray(dataset.x, dtype=float)
        y = np.asarray(dataset.y, dtype=float)
        z = np.asarray(dataset.elevation, dtype=float) if dataset.elevation is not None else np.zeros(dataset.record_count)
        values = np.asarray(dataset.channel(channel), dtype=float)
        is_geo = str(dataset.crs or "").upper() in {"EPSG:4326", "4326", "WGS84", "WGS 84"} or str(dataset.coordinate_units).lower() in {"deg", "degree", "degrees"}
        coordinate_label = dataset.crs or dataset.coordinate_units or "Survey coordinates"
        if is_geo:
            x, y, lon0, lat0 = geographic_to_local_xy(x, y)
            coordinate_label = f"Local metric display about {lat0:.6f}°, {lon0:.6f}° (source WGS84)"
        self.native_spatial_view.set_data(
            x, y, values, z=z,
            title=Path(dataset.source_path).name,
            value_label=channel.replace("_", " "),
            value_units="nT",
            coordinate_label=coordinate_label,
            allow_surface=True,
        )

    def _refresh_geospatial(self) -> None:
        if not hasattr(self, "geospatial_view"):
            return
        dataset = self._display_dataset()
        if dataset is None:
            self.geospatial_view.clear_tracks()
            return
        try:
            coords = to_wgs84(
                dataset.x,
                dataset.y,
                crs=dataset.crs,
                altitude_m=dataset.elevation,
                allow_lonlat_inference=True,
            )
        except CoordinateTransformError as exc:
            self.geospatial_view.clear_tracks()
            self.geospatial_view.set_status_message(str(exc))
            return
        valid = coords.valid_mask
        if not np.any(valid):
            self.geospatial_view.clear_tracks()
            self.geospatial_view.set_status_message("No valid geographic coordinates are available for satellite/3D display.")
            return

        tracks: list[GeoTrack] = []
        groups = dataset.line_groups()
        if groups:
            for line_name, indices in groups.items():
                idx = np.asarray(indices, dtype=int)
                idx = idx[(idx >= 0) & (idx < dataset.record_count)]
                idx = idx[valid[idx]]
                if idx.size:
                    tracks.append(
                        GeoTrack(
                            str(line_name),
                            coords.longitude[idx],
                            coords.latitude[idx],
                            coords.altitude_m[idx],
                        )
                    )
        else:
            idx = np.flatnonzero(valid)
            role_name = "Base Station" if dataset.role.value == "base" else "Magnetic Survey"
            tracks.append(
                GeoTrack(
                    role_name,
                    coords.longitude[idx],
                    coords.latitude[idx],
                    coords.altitude_m[idx],
                )
            )
        self.geospatial_view.set_tracks(
            tracks,
            render=self.tabs.currentIndex() == self.TAB_GEOSPATIAL,
        )

    def _populate_results(self, result: dict[str, Any]) -> None:
        stages = list(result.get("stage_outcomes", []))
        self.stage_table.setRowCount(len(stages))
        self._all_findings = []

        status_counts: dict[str, int] = {}
        for row, stage in enumerate(stages):
            metrics = stage.get("metrics", {}) or {}
            status = str(stage.get("status", "")).upper()
            status_counts[status] = status_counts.get(status, 0) + 1
            prominent = self._prominent_metric(metrics)
            finding_count = len(stage.get("findings", []) or [])
            values = [
                stage.get("display_name", ""),
                status,
                prominent,
                f"{stage.get('duration_ms', 0)} ms",
                str(finding_count),
                stage.get("message", ""),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 1:
                    self._color_status_item(item, status)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if column in (2, 3, 4):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.stage_table.setItem(row, column, item)
            self._all_findings.extend(
                (stage.get("display_name", ""), finding)
                for finding in stage.get("findings", []) or []
            )

        summary = "  •  ".join(f"{key}: {value}" for key, value in sorted(status_counts.items()))
        self.qc_summary_label.setText(summary or "No stage outcomes")
        self.stage_table.resizeRowsToContents()
        self._apply_findings_filter()

    def _apply_findings_filter(self) -> None:
        selected = str(self.findings_filter.currentData() or "all").lower()
        visible = [
            pair
            for pair in self._all_findings
            if selected == "all" or str(pair[1].get("severity", "")).lower() == selected
        ]
        self.findings_table.setRowCount(len(visible))
        for row, (stage_name, item_data) in enumerate(visible):
            severity = str(item_data.get("severity", "")).upper()
            values = [
                severity,
                stage_name,
                item_data.get("rule_id", ""),
                item_data.get("message", ""),
                item_data.get("suggested_action", "") or "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    self._color_status_item(item, severity)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.findings_table.setItem(row, column, item)
        self.findings_table.resizeRowsToContents()
        self.finding_count_label.setText(f"{len(visible)} finding{'s' if len(visible) != 1 else ''}")

    def _clear_results(self) -> None:
        self.stage_table.setRowCount(0)
        self.findings_table.setRowCount(0)
        self.qc_summary_label.setText("No QC run has been completed")
        self.finding_count_label.setText("0 findings")
        self.metric_qc.set_value("Not run", "Select a profile and run QC")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _require_rover(self) -> bool:
        if self.rover is not None:
            return True
        QMessageBox.information(self, "Magnetic", "Load a primary magnetic dataset first.")
        return False

    def _append_processing(self, message: str) -> None:
        self.processing_log.appendPlainText(message)
        self._set_status(message, "ready")
        self.tabs.setCurrentIndex(self.TAB_PROCESSING)

    def _set_status(self, message: str, state: str) -> None:
        self.status_label.setText(message)
        self._set_status_badge(state)

    def _set_status_badge(self, state: str) -> None:
        normalized = state.lower().strip()
        palette = {
            "ready": ("READY", "#EAF3F8", "#0B6FA4", "#BBD5E4"),
            "running": ("RUNNING", "#E8F0FA", "#245D9B", "#B8CAE0"),
            "pass": ("PASS", "#E8F4EC", "#167044", "#B9DEC7"),
            "passed": ("PASS", "#E8F4EC", "#167044", "#B9DEC7"),
            "warn": ("WARN", "#FFF4DE", "#A96308", "#E6C787"),
            "warning": ("WARN", "#FFF4DE", "#A96308", "#E6C787"),
            "fail": ("FAIL", "#FCEBEC", "#A82E35", "#E5B8BC"),
            "failed": ("FAIL", "#FCEBEC", "#A82E35", "#E5B8BC"),
            "error": ("ERROR", "#FCEBEC", "#A82E35", "#E5B8BC"),
            "cancelled": ("CANCELLED", "#EFF1F3", "#68737D", "#D0D5D9"),
        }
        text, background, foreground, border = palette.get(normalized, palette["ready"])
        self.status_badge.setText(text)
        self.status_badge.setStyleSheet(
            "QLabel#magStatusBadge{"
            f"background:{background};color:{foreground};border:1px solid {border};"
            "border-radius:9px;padding:3px 9px;font-size:9px;font-weight:700;}"
        )

    @staticmethod
    def _make_key_value_table() -> QTableWidget:
        table = QTableWidget(0, 2)
        MagneticDashboard._configure_table(table, ["Property", "Value"])
        table.setWordWrap(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().resizeSection(0, 210)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        return table

    @staticmethod
    def _table_page(table: QTableWidget) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(table)
        return page

    @staticmethod
    def _configure_table(
        table: QTableWidget,
        headers: list[str],
        *,
        stretch_last: bool = True,
    ) -> None:
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSortingEnabled(False)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(stretch_last)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

    @staticmethod
    def _set_key_value_rows(table: QTableWidget, rows: list[tuple[str, Any]]) -> None:
        table.setRowCount(len(rows))
        for row, (key, value) in enumerate(rows):
            key_item = QTableWidgetItem(str(key))
            value_item = QTableWidgetItem(MagneticDashboard._display_value(value))
            key_item.setFont(QFont(key_item.font().family(), key_item.font().pointSize(), QFont.Weight.DemiBold))
            table.setItem(row, 0, key_item)
            table.setItem(row, 1, value_item)
        table.resizeRowsToContents()

    @staticmethod
    def _display_value(value: Any) -> str:
        if value is None or value == "":
            return "—"
        if isinstance(value, dict):
            return ";  ".join(
                f"{MagneticDashboard._humanize(key)}: {MagneticDashboard._display_value(item)}"
                for key, item in value.items()
            )
        if isinstance(value, (list, tuple, set)):
            return ", ".join(MagneticDashboard._display_value(item) for item in value)
        if isinstance(value, float):
            if np.isnan(value):
                return "—"
            return f"{value:.6g}"
        return str(value)

    @staticmethod
    def _humanize(value: Any) -> str:
        text = str(value or "—").replace("_", " ").strip()
        return text.title() if text != "—" else text

    @staticmethod
    def _prominent_metric(metrics: dict[str, Any]) -> str:
        preferred = (
            "overall_score",
            "record_count",
            "maximum_absolute_misclosure_nt",
            "rms_nt",
            "outlier_count",
            "missing_pct",
            "noise_rms_nt",
        )
        for key in preferred:
            if key in metrics:
                return f"{MagneticDashboard._humanize(key)}: {MagneticDashboard._display_value(metrics[key])}"
        for key, value in metrics.items():
            if isinstance(value, (int, float, str)):
                return f"{MagneticDashboard._humanize(key)}: {MagneticDashboard._display_value(value)}"
        return "—"

    @staticmethod
    def _color_status_item(item: QTableWidgetItem, status: str) -> None:
        normalized = status.lower().strip()
        if normalized in {"pass", "passed", "completed", "info"}:
            item.setForeground(QColor("#167044" if normalized != "info" else "#0B6FA4"))
        elif normalized in {"warn", "warning"}:
            item.setForeground(QColor("#A96308"))
        elif normalized in {"critical", "fail", "failed", "error"}:
            item.setForeground(QColor("#A82E35"))
        elif normalized in {"skipped", "cancelled"}:
            item.setForeground(QColor("#68737D"))
        else:
            item.setForeground(QColor("#42586B"))
