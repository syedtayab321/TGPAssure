from __future__ import annotations

import csv
import tempfile
import traceback
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PySide6.QtCore import (
    QObject,
    QRunnable,
    QSignalBlocker,
    QThreadPool,
    QTimer,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.data_access.db_engine import DatabaseEngine
from core.domain.geospatial import CoordinateTransformError, to_wgs84
from ui.widgets.geospatial_view import GeoTrack, GoogleGeospatialView
from core.infrastructure.service_container import ServiceContainer
from modules.seismic.visualization.data_source import UnifiedSeismicDataSource
from modules.seismic.visualization.exporters import (
    export_geotiff,
    export_horizons_shapefile,
    export_html_report,
    export_kml,
    export_kmz,
    export_pdf_report,
    export_time_slice_animation,
    register_visualization_report,
)
from modules.seismic.visualization.models import (
    GainSettings,
    InterpretationObject,
    InterpretationPoint,
    QcTraceFlag,
    SectionData,
    SectionRequest,
    VisualizationSession,
    VolumeData,
    WellPath,
)
from modules.seismic.visualization.processing import calculate_noise_metrics, detect_bad_traces
from modules.seismic.visualization.seismic_attributes import (
    ATTRIBUTE_NAMES,
    AttributeParameters,
    compute_attribute,
    compute_volume_attribute,
)
from modules.seismic.visualization.qc_panel import SeismicQcPanel
from modules.seismic.visualization.session_store import VisualizationSessionStore
from modules.seismic.visualization.view_2d import Seismic2DView
from modules.seismic.visualization.view_3d import Seismic3DView
from modules.seismic.visualization.geometry_map import SeismicGeometryMap
from ui.theme.petrel_theme import FONT_SIZE_CAPTION, FONT_SIZE_LARGE, FONT_SIZE_NORMAL, FONT_SIZE_SMALL


ProgressReporter = Callable[[int, str], None]
TaskFunction = Callable[[ProgressReporter], Any]


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    progress = Signal(int, str)
    finished = Signal()


class FunctionRunnable(QRunnable):
    def __init__(self, function: TaskFunction) -> None:
        super().__init__()
        self.function = function
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.function(self.signals.progress.emit)
            self.signals.result.emit(result)
        except Exception:
            self.signals.error.emit(traceback.format_exc())
        finally:
            self.signals.finished.emit()


class LoadingOverlay(QFrame):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("seismicLoadingOverlay")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            "QFrame#seismicLoadingOverlay{background-color:rgba(4,12,20,205);}"
            "QFrame#seismicLoadingCard{background:#FFFFFF;border:1px solid #8EA6B8;border-radius:10px;}"
            f"QLabel#seismicLoadingTitle{{font-size:{FONT_SIZE_LARGE}pt;font-weight:600;color:#123047;}}"
            f"QLabel#seismicLoadingDetail{{font-size:{FONT_SIZE_NORMAL}pt;color:#51697B;}}"
            "QProgressBar{border:1px solid #B8C7D2;border-radius:5px;background:#EAF0F4;height:12px;}"
            "QProgressBar::chunk{background:#1273DE;border-radius:4px;}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.addStretch(1)

        card = QFrame(self)
        card.setObjectName("seismicLoadingCard")
        card.setFixedWidth(430)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(30, 25, 30, 25)
        card_layout.setSpacing(12)

        self.title_label = QLabel("Loading seismic data")
        self.title_label.setObjectName("seismicLoadingTitle")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.detail_label = QLabel("Preparing reader")
        self.detail_label.setObjectName("seismicLoadingDetail")
        self.detail_label.setAlignment(Qt.AlignCenter)
        self.detail_label.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("%p%")

        card_layout.addWidget(self.title_label)
        card_layout.addWidget(self.detail_label)
        card_layout.addWidget(self.progress)
        root.addWidget(card, 0, Qt.AlignCenter)
        root.addStretch(1)
        self.hide()

    def show_activity(self, title: str, detail: str | None = None, value: int = 0) -> None:
        self.title_label.setText(title)
        self.detail_label.setText(detail or title)
        self.progress.setValue(max(0, min(100, int(value))))
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        self.show()
        self.raise_()

    def update_activity(self, value: int, detail: str) -> None:
        self.progress.setValue(max(0, min(100, int(value))))
        if detail:
            self.detail_label.setText(detail)

    def hide_activity(self) -> None:
        self.hide()


class SeismicVisualizationDashboard(QWidget):
    status_message = Signal(str)
    activity_started = Signal(str, str)
    activity_progress = Signal(int, str)
    activity_finished = Signal()

    TAB_2D = 0
    TAB_3D = 1
    TAB_MAP = 2
    TAB_GEOSPATIAL = 3
    TAB_QC = 4
    TAB_OUTPUTS = 5

    def __init__(
        self,
        container: ServiceContainer,
        file_path: str | Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.container = container
        self.database_engine = container.resolve(DatabaseEngine) if container.has(DatabaseEngine) else None
        self.session_store = VisualizationSessionStore(self.database_engine)
        self.data_source: UnifiedSeismicDataSource | None = None
        self.volume: VolumeData | None = None
        self.raw_volume: VolumeData | None = None
        self.qc_flags: list[QcTraceFlag] = []
        self.interpretations: list[InterpretationObject] = []
        self.wells: list[WellPath] = []
        self._current_path: Path | None = None
        self._thread_pool = QThreadPool(self)
        self._thread_pool.setMaxThreadCount(1)
        self._active_workers: set[FunctionRunnable] = set()
        self._busy_count = 0
        self._pending_open_path: Path | None = None
        self._geometry_cache: dict[str, np.ndarray] | None = None
        self._pick_color = "#00E5FF"
        self._closing = False
        self._volume_reload_timer = QTimer(self)
        self._volume_reload_timer.setSingleShot(True)
        self._volume_reload_timer.setInterval(550)
        self._volume_reload_timer.timeout.connect(self._reload_volume_from_controls)
        self.setObjectName("seismicVisualizationDashboard")
        self.setProperty("module_id", "visualization")

        self._build_ui()
        self._apply_local_style()
        self._connect_signals()
        if file_path is not None:
            path = Path(file_path).expanduser().resolve()
            QTimer.singleShot(80, lambda: self.open_path(path))

    @property
    def current_path(self) -> Path | None:
        return self._current_path

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        header = QFrame()
        header.setProperty("card", True)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 12, 8)
        header_layout.setSpacing(12)

        self.open_button = self._button("Open SEG-Y / SEG-D", "primary")
        self.open_button.setMinimumWidth(180)
        self.file_label = QLabel("No seismic file open")
        self.file_label.setObjectName("seismicFileLabel")
        self.file_label.setMinimumWidth(220)
        self.file_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.metadata_label = QLabel("Select a file to begin")
        self.metadata_label.setObjectName("seismicMetadataLabel")
        self.metadata_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.metadata_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.metadata_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        header_layout.addWidget(self.open_button)
        header_layout.addWidget(self.file_label, 1)
        header_layout.addWidget(self.metadata_label)
        root.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("seismicMainTabs")
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setElideMode(Qt.ElideNone)
        self.tabs.addTab(self._build_2d_tab(), "2D Viewer")
        self.tabs.addTab(self._build_3d_tab(), "3D Viewer")
        self.tabs.addTab(self._build_map_tab(), "Map & Geometry")
        self.tabs.addTab(self._build_geospatial_tab(), "Satellite / 3D Terrain")
        self.tabs.addTab(self._build_qc_tab(), "QC and Geometry")
        self.tabs.addTab(self._build_outputs_tab(), "Sessions and Outputs")
        root.addWidget(self.tabs, 1)

        status_frame = QFrame()
        status_frame.setProperty("statusBar", True)
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(10, 5, 10, 5)
        self.status_label = QLabel("Ready")
        self.cursor_label = QLabel("Trace: —   Sample: —   Time: —   Amplitude: —")
        self.cursor_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        status_layout.addWidget(self.status_label, 1)
        status_layout.addWidget(self.cursor_label)
        root.addWidget(status_frame)

        self.loading_overlay = LoadingOverlay(self)
        self.loading_overlay.setGeometry(self.rect())

    def _build_2d_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        controls_card = QFrame()
        controls_card.setProperty("card", True)
        controls_card.setMinimumWidth(330)
        controls_card.setMaximumWidth(440)
        controls_layout = QVBoxLayout(controls_card)
        controls_layout.setContentsMargins(8, 8, 8, 8)
        controls_layout.setSpacing(6)

        self.tools_2d_tabs = QTabWidget()
        self.tools_2d_tabs.setObjectName("seismicToolTabs")
        self.tools_2d_tabs.setUsesScrollButtons(True)
        self.tools_2d_tabs.setElideMode(Qt.ElideNone)
        self.tools_2d_tabs.addTab(self._scroll_page(self._build_section_controls()), "Section")
        self.tools_2d_tabs.addTab(self._scroll_page(self._build_display_controls()), "Display")
        self.tools_2d_tabs.addTab(self._scroll_page(self._build_picking_controls()), "Picking")
        controls_layout.addWidget(self.tools_2d_tabs)

        view_card = QFrame()
        view_card.setProperty("plotCard", True)
        view_layout = QVBoxLayout(view_card)
        view_layout.setContentsMargins(4, 4, 4, 4)
        self.view_2d = Seismic2DView()
        view_layout.addWidget(self.view_2d)

        splitter.addWidget(controls_card)
        splitter.addWidget(view_card)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([365, 1265])
        layout.addWidget(splitter)
        return tab

    def _build_section_controls(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(10)

        group = QGroupBox("Section Range")
        form = QFormLayout(group)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.trace_start_spin = QSpinBox()
        self.trace_start_spin.setRange(0, 0)
        self.trace_count_spin = QSpinBox()
        self.trace_count_spin.setRange(1, 1_000_000)
        self.trace_count_spin.setValue(240)
        self.sample_start_spin = QSpinBox()
        self.sample_start_spin.setRange(0, 0)
        self.sample_count_spin = QSpinBox()
        self.sample_count_spin.setRange(1, 1_000_000)
        self.sample_count_spin.setValue(1600)
        self.trace_decimation_spin = QSpinBox()
        self.trace_decimation_spin.setRange(1, 1000)
        self.trace_decimation_spin.setValue(1)
        self.sample_decimation_spin = QSpinBox()
        self.sample_decimation_spin.setRange(1, 1000)
        self.sample_decimation_spin.setValue(1)
        form.addRow("Start trace", self.trace_start_spin)
        form.addRow("Trace count", self.trace_count_spin)
        form.addRow("Start sample", self.sample_start_spin)
        form.addRow("Sample count", self.sample_count_spin)
        form.addRow("Trace decimation", self.trace_decimation_spin)
        form.addRow("Sample decimation", self.sample_decimation_spin)
        layout.addWidget(group)

        self.apply_button = self._button("Load Selected Section", "primary")
        layout.addWidget(self.apply_button)

        note = QLabel(
            "Use decimation for very large sections. The original file remains unchanged."
        )
        note.setProperty("muted", True)
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        return page

    def _build_display_controls(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(10)

        mode_group = QGroupBox("Display")
        mode_form = QFormLayout(mode_group)
        self.display_combo = QComboBox()
        self.display_combo.addItem("Wiggle + Variable Density", "wiggle_density")
        self.display_combo.addItem("Wiggle", "wiggle")
        self.display_combo.addItem("Variable Density", "variable_density")
        self.label_combo = QComboBox()
        self.label_combo.addItem("Automatic", "auto")
        self.label_combo.addItem("Trace Number", "trace")
        self.label_combo.addItem("CDP", "cdp")
        self.label_combo.addItem("Shot Point", "shot")
        self.label_combo.addItem("Inline/Crossline or RL/RP", "line_point")
        self.label_combo.addItem("Hide Labels", "none")
        self.attribute_combo = QComboBox()
        for key, label in ATTRIBUTE_NAMES.items():
            self.attribute_combo.addItem(label, key)
        mode_form.addRow("Plot mode", self.display_combo)
        mode_form.addRow("Seismic attribute", self.attribute_combo)
        mode_form.addRow("Section labels", self.label_combo)
        layout.addWidget(mode_group)

        attribute_group = QGroupBox("Attribute Parameters")
        attribute_form = QFormLayout(attribute_group)
        self.rms_window_spin = QDoubleSpinBox()
        self.rms_window_spin.setRange(2.0, 2000.0)
        self.rms_window_spin.setDecimals(1)
        self.rms_window_spin.setValue(40.0)
        self.rms_window_spin.setSuffix(" ms")
        self.coherence_window_spin = QDoubleSpinBox()
        self.coherence_window_spin.setRange(2.0, 2000.0)
        self.coherence_window_spin.setDecimals(1)
        self.coherence_window_spin.setValue(32.0)
        self.coherence_window_spin.setSuffix(" ms")
        self.coherence_radius_spin = QSpinBox()
        self.coherence_radius_spin.setRange(1, 20)
        self.coherence_radius_spin.setValue(2)
        self.minimum_frequency_spin = QDoubleSpinBox()
        self.minimum_frequency_spin.setRange(0.1, 500.0)
        self.minimum_frequency_spin.setDecimals(1)
        self.minimum_frequency_spin.setValue(1.0)
        self.minimum_frequency_spin.setSuffix(" Hz")
        attribute_form.addRow("RMS window", self.rms_window_spin)
        attribute_form.addRow("Coherence window", self.coherence_window_spin)
        attribute_form.addRow("Trace aperture radius", self.coherence_radius_spin)
        attribute_form.addRow("Sweetness frequency floor", self.minimum_frequency_spin)
        layout.addWidget(attribute_group)

        gain_group = QGroupBox("Gain and Clipping")
        gain_form = QFormLayout(gain_group)
        self.gain_spin = QDoubleSpinBox()
        self.gain_spin.setRange(0.001, 100000.0)
        self.gain_spin.setDecimals(3)
        self.gain_spin.setValue(1.0)
        self.clip_spin = QDoubleSpinBox()
        self.clip_spin.setRange(50.0, 100.0)
        self.clip_spin.setDecimals(1)
        self.clip_spin.setValue(98.5)
        self.clip_spin.setSuffix(" %")
        self.agc_check = QCheckBox("Enable AGC")
        self.agc_window_spin = QDoubleSpinBox()
        self.agc_window_spin.setRange(10.0, 10000.0)
        self.agc_window_spin.setValue(500.0)
        self.agc_window_spin.setSuffix(" ms")
        self.normalize_check = QCheckBox("Balance each trace")
        gain_form.addRow("Scalar gain", self.gain_spin)
        gain_form.addRow("Clip percentile", self.clip_spin)
        gain_form.addRow(self.agc_check)
        gain_form.addRow("AGC window", self.agc_window_spin)
        gain_form.addRow(self.normalize_check)
        layout.addWidget(gain_group)

        overlay_group = QGroupBox("Overlays")
        overlay_layout = QVBoxLayout(overlay_group)
        self.noise_overlay_check = QCheckBox("Show noise analysis overlay")
        self.noise_overlay_check.setChecked(True)
        overlay_layout.addWidget(self.noise_overlay_check)
        layout.addWidget(overlay_group)

        self.fit_button = self._button("Fit Section to Window", "secondary")
        layout.addWidget(self.fit_button)
        layout.addStretch(1)
        return page

    def _build_picking_controls(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(10)

        object_group = QGroupBox("Interpretation Object")
        object_layout = QVBoxLayout(object_group)
        name_row = QHBoxLayout()
        self.pick_name_edit = QLineEdit("Horizon 1")
        self.pick_color_button = QToolButton()
        self.pick_color_button.setText("Color")
        self.pick_color_button.setMinimumHeight(28)
        self.pick_color_button.setMinimumWidth(70)
        name_row.addWidget(self.pick_name_edit, 1)
        name_row.addWidget(self.pick_color_button)
        object_layout.addLayout(name_row)
        layout.addWidget(object_group)

        pick_group = QGroupBox("Picking Tools")
        pick_grid = QGridLayout(pick_group)
        self.horizon_button = self._button("Pick Horizon", "success")
        self.fault_button = self._button("Pick Fault", "warning")
        self.measure_button = self._button("Measure", "secondary")
        self.undo_pick_button = self._button("Undo Last Pick", "secondary")
        self.stop_pick_button = self._button("Stop Picking", "danger")
        pick_grid.addWidget(self.horizon_button, 0, 0)
        pick_grid.addWidget(self.fault_button, 0, 1)
        pick_grid.addWidget(self.measure_button, 1, 0)
        pick_grid.addWidget(self.undo_pick_button, 1, 1)
        pick_grid.addWidget(self.stop_pick_button, 2, 0, 1, 2)
        layout.addWidget(pick_group)

        note = QLabel(
            "Horizon and fault picks snap to the strongest local amplitude near the cursor."
        )
        note.setProperty("muted", True)
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        return page

    def _build_3d_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        controls_card = QFrame()
        controls_card.setProperty("card", True)
        controls_card.setMinimumWidth(350)
        controls_card.setMaximumWidth(470)
        controls_layout = QVBoxLayout(controls_card)
        controls_layout.setContentsMargins(8, 8, 8, 8)

        self.tools_3d_tabs = QTabWidget()
        self.tools_3d_tabs.setObjectName("seismicToolTabs")
        self.tools_3d_tabs.setUsesScrollButtons(True)
        self.tools_3d_tabs.setElideMode(Qt.ElideNone)
        self.tools_3d_tabs.addTab(self._scroll_page(self._build_volume_controls()), "Volume")
        self.tools_3d_tabs.addTab(self._scroll_page(self._build_slice_controls()), "Slices")
        self.tools_3d_tabs.addTab(self._scroll_page(self._build_well_controls()), "Wells")
        controls_layout.addWidget(self.tools_3d_tabs)

        view_card = QFrame()
        view_card.setProperty("plotCard", True)
        view_layout = QVBoxLayout(view_card)
        view_layout.setContentsMargins(4, 4, 4, 4)
        self.view_3d = Seismic3DView()
        view_layout.addWidget(self.view_3d)

        splitter.addWidget(controls_card)
        splitter.addWidget(view_card)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([405, 1225])
        layout.addWidget(splitter)
        return tab

    def _build_volume_controls(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        tabs = QTabWidget(page)
        tabs.setObjectName("seismicToolTabs")
        tabs.setDocumentMode(True)

        dataset_page = QWidget()
        dataset_layout = QVBoxLayout(dataset_page)
        dataset_layout.setContentsMargins(8, 8, 8, 8)
        status_group = QGroupBox("Dataset")
        status_layout = QVBoxLayout(status_group)
        self.volume_kind_label = QLabel("No seismic file open")
        self.volume_kind_label.setWordWrap(True)
        self.volume_status_label = QLabel("No volume loaded")
        self.volume_status_label.setWordWrap(True)
        self.volume_status_label.setProperty("muted", True)
        status_layout.addWidget(self.volume_kind_label)
        status_layout.addWidget(self.volume_status_label)
        dataset_layout.addWidget(status_group)
        dataset_help = QLabel("3D volume/cutain is prepared automatically when limits are changed or when a 3D/slice view is requested.")
        dataset_help.setProperty("muted", True)
        dataset_help.setWordWrap(True)
        dataset_layout.addWidget(dataset_help)
        dataset_layout.addStretch(1)
        tabs.addTab(dataset_page, "Dataset")

        limits_page = QWidget()
        limits_layout = QVBoxLayout(limits_page)
        limits_layout.setContentsMargins(8, 8, 8, 8)
        limits_group = QGroupBox("Performance Limits")
        limits_form = QFormLayout(limits_group)
        self.max_inline_spin = QSpinBox()
        self.max_inline_spin.setRange(2, 256)
        self.max_inline_spin.setValue(72)
        self.max_crossline_spin = QSpinBox()
        self.max_crossline_spin.setRange(8, 512)
        self.max_crossline_spin.setValue(120)
        self.max_volume_samples_spin = QSpinBox()
        self.max_volume_samples_spin.setRange(64, 2048)
        self.max_volume_samples_spin.setValue(420)
        limits_form.addRow("Maximum inlines", self.max_inline_spin)
        limits_form.addRow("Maximum crosslines", self.max_crossline_spin)
        limits_form.addRow("Maximum samples", self.max_volume_samples_spin)
        limits_layout.addWidget(limits_group)
        limits_note = QLabel("Changing these values now refreshes the 3D dataset automatically after a short debounce. No manual Load button is required.")
        limits_note.setProperty("muted", True)
        limits_note.setWordWrap(True)
        limits_layout.addWidget(limits_note)
        limits_layout.addStretch(1)
        tabs.addTab(limits_page, "Performance Limits")

        render_page = QWidget()
        render_layout = QVBoxLayout(render_page)
        render_layout.setContentsMargins(8, 8, 8, 8)
        render_group = QGroupBox("Rendering")
        render_form = QFormLayout(render_group)
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(5, 100)
        self.opacity_slider.setValue(48)
        self.opacity_value_label = QLabel("48%")
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(self.opacity_slider, 1)
        opacity_row.addWidget(self.opacity_value_label)
        opacity_widget = QWidget()
        opacity_widget.setLayout(opacity_row)
        self.volume_attribute_combo = QComboBox()
        for key, label in ATTRIBUTE_NAMES.items():
            self.volume_attribute_combo.addItem(label, key)
        self.apply_volume_attribute_button = self._button("Apply 3D Attribute", "secondary")
        self.volume_clip_spin = QDoubleSpinBox()
        self.volume_clip_spin.setRange(90.0, 100.0)
        self.volume_clip_spin.setDecimals(1)
        self.volume_clip_spin.setValue(98.5)
        self.volume_clip_spin.setSuffix(" %")
        self.volume_threshold_spin = QDoubleSpinBox()
        self.volume_threshold_spin.setRange(0.0, 95.0)
        self.volume_threshold_spin.setDecimals(1)
        self.volume_threshold_spin.setValue(4.0)
        self.volume_threshold_spin.setSuffix(" % scale")
        self.show_volume_button = self._button("Show Volume / Curtain", "primary")
        render_form.addRow("Opacity", opacity_widget)
        render_form.addRow("3D attribute", self.volume_attribute_combo)
        render_form.addRow(self.apply_volume_attribute_button)
        render_form.addRow("Robust amplitude clip", self.volume_clip_spin)
        render_form.addRow("Transparency threshold", self.volume_threshold_spin)
        render_form.addRow(self.show_volume_button)
        render_layout.addWidget(render_group)
        render_layout.addStretch(1)
        tabs.addTab(render_page, "Rendering")

        self.load_volume_button = self._button("Load 3D Volume", "success")
        self.load_volume_button.setVisible(False)
        layout.addWidget(tabs, 1)
        return page

    def _build_slice_controls(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        tabs = QTabWidget(page)
        tabs.setObjectName("seismicToolTabs")
        tabs.setDocumentMode(True)

        extraction_page = QWidget()
        extraction_layout = QVBoxLayout(extraction_page)
        extraction_layout.setContentsMargins(8, 8, 8, 8)
        group = QGroupBox("Slice Extraction")
        form = QFormLayout(group)
        self.volume_mode_combo = QComboBox()
        self.volume_mode_combo.addItem("Volume / Curtain", "volume")
        self.volume_mode_combo.addItem("Inline Slice", "inline")
        self.volume_mode_combo.addItem("Crossline Slice", "crossline")
        self.volume_mode_combo.addItem("Time Slice", "time")
        self.volume_mode_combo.addItem("Orthogonal Probe (IL/XL/Time)", "orthogonal")
        self.slice_slider = QSlider(Qt.Horizontal)
        self.slice_slider.setRange(0, 0)
        self.slice_slider.setEnabled(False)
        self.slice_value_label = QLabel("Volume")
        self.slice_value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.slice_value_label.setProperty("valueBadge", True)
        form.addRow("Slice type", self.volume_mode_combo)
        form.addRow("Position", self.slice_slider)
        form.addRow("Current", self.slice_value_label)
        extraction_layout.addWidget(group)
        extraction_layout.addStretch(1)
        tabs.addTab(extraction_page, "Slice Extraction")

        quick_page = QWidget()
        quick_layout = QVBoxLayout(quick_page)
        quick_layout.setContentsMargins(8, 8, 8, 8)
        buttons_group = QGroupBox("Quick Views")
        buttons_layout = QVBoxLayout(buttons_group)
        self.inline_button = self._button("Show Inline Slice", "primary")
        self.crossline_button = self._button("Show Crossline Slice", "primary")
        self.time_slice_button = self._button("Show Time Slice", "primary")
        self.orthogonal_button = self._button("Show Orthogonal Probe", "success")
        buttons_layout.addWidget(self.inline_button)
        buttons_layout.addWidget(self.crossline_button)
        buttons_layout.addWidget(self.time_slice_button)
        buttons_layout.addWidget(self.orthogonal_button)
        quick_layout.addWidget(buttons_group)
        quick_layout.addStretch(1)
        tabs.addTab(quick_page, "Quick View")

        layout.addWidget(tabs, 1)
        return page

    def _build_well_controls(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(10)

        well_group = QGroupBox("Well Paths")
        well_layout = QVBoxLayout(well_group)
        self.add_well_button = self._button("Import Well Path CSV", "primary")
        well_layout.addWidget(self.add_well_button)
        well_note = QLabel("Accepted columns: X/Y/Z, Easting/Northing/Depth, or Longitude/Latitude/Elevation.")
        well_note.setProperty("muted", True)
        well_note.setWordWrap(True)
        well_layout.addWidget(well_note)
        layout.addWidget(well_group)

        camera_group = QGroupBox("Camera")
        camera_layout = QVBoxLayout(camera_group)
        self.camera_button = self._button("Reset Camera", "secondary")
        camera_layout.addWidget(self.camera_button)
        layout.addWidget(camera_group)
        layout.addStretch(1)
        return page

    def _build_map_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        splitter = QSplitter(Qt.Horizontal, tab)
        splitter.setChildrenCollapsible(False)

        sidebar = QFrame(tab)
        sidebar.setProperty("card", True)
        sidebar.setMinimumWidth(265)
        sidebar.setMaximumWidth(360)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(7, 7, 7, 7)

        self.map_side_tabs = QTabWidget(sidebar)
        self.map_side_tabs.setObjectName("seismicToolTabs")
        self.map_side_tabs.setUsesScrollButtons(True)

        summary_page = QWidget()
        summary_layout = QVBoxLayout(summary_page)
        summary_layout.setContentsMargins(8, 8, 8, 8)
        summary_group = QGroupBox("Geometry Summary")
        summary_group_layout = QVBoxLayout(summary_group)
        self.map_summary_label = QLabel("Load seismic data to populate source, receiver and midpoint geometry statistics.")
        self.map_summary_label.setWordWrap(True)
        self.map_summary_label.setProperty("muted", True)
        summary_group_layout.addWidget(self.map_summary_label)
        summary_layout.addWidget(summary_group)
        summary_layout.addStretch(1)
        self.map_side_tabs.addTab(summary_page, "Summary")

        guide_page = QWidget()
        guide_layout = QVBoxLayout(guide_page)
        guide_layout.setContentsMargins(8, 8, 8, 8)
        guide_group = QGroupBox("Map Review")
        guide_group_layout = QVBoxLayout(guide_group)
        guide_text = QLabel(
            "Use the map controls above the plot to toggle sources, receivers and midpoint/CDP geometry. "
            "Fit Map restores the full XY extent while keeping a true 1:1 spatial aspect ratio."
        )
        guide_text.setWordWrap(True)
        guide_text.setProperty("muted", True)
        guide_group_layout.addWidget(guide_text)
        guide_layout.addWidget(guide_group)
        guide_layout.addStretch(1)
        self.map_side_tabs.addTab(guide_page, "Guide")
        side_layout.addWidget(self.map_side_tabs, 1)

        map_card = QFrame(tab)
        map_card.setProperty("plotCard", True)
        map_layout = QVBoxLayout(map_card)
        map_layout.setContentsMargins(4, 4, 4, 4)
        self.geometry_map = SeismicGeometryMap(map_card)
        map_layout.addWidget(self.geometry_map, 1)

        splitter.addWidget(sidebar)
        splitter.addWidget(map_card)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 1330])
        layout.addWidget(splitter, 1)
        return tab

    def _build_geospatial_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        splitter = QSplitter(Qt.Horizontal, tab)
        splitter.setChildrenCollapsible(False)

        sidebar = QFrame(tab)
        sidebar.setProperty("card", True)
        sidebar.setMinimumWidth(280)
        sidebar.setMaximumWidth(390)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(7, 7, 7, 7)
        self.geospatial_side_tabs = QTabWidget(sidebar)
        self.geospatial_side_tabs.setObjectName("seismicToolTabs")

        crs_page = QWidget()
        crs_layout = QVBoxLayout(crs_page)
        crs_layout.setContentsMargins(8, 8, 8, 8)
        crs_group = QGroupBox("Coordinate Reference System")
        crs_group_layout = QVBoxLayout(crs_group)
        self.seismic_crs_edit = QLineEdit()
        self.seismic_crs_edit.setPlaceholderText("e.g. EPSG:32642")
        self.seismic_crs_edit.setToolTip("Required only when SEG-Y coordinates are projected and the CRS is not embedded in project metadata.")
        crs_group_layout.addWidget(QLabel("Projected coordinate CRS"))
        crs_group_layout.addWidget(self.seismic_crs_edit)
        refresh = self._button("Refresh Satellite Geometry", "secondary")
        refresh.clicked.connect(self._refresh_geospatial)
        crs_group_layout.addWidget(refresh)
        crs_layout.addWidget(crs_group)
        crs_layout.addStretch(1)
        self.geospatial_side_tabs.addTab(crs_page, "CRS")

        info_page = QWidget()
        info_layout = QVBoxLayout(info_page)
        info_layout.setContentsMargins(8, 8, 8, 8)
        info_group = QGroupBox("Coordinate Notes")
        info_group_layout = QVBoxLayout(info_group)
        note = QLabel(
            "SEG-Y normally stores coordinate values and unit codes but not a complete EPSG definition. "
            "Decimal-degree and arc-second coordinates are handled automatically. For projected XY data, "
            "enter the verified CRS before using satellite/terrain overlays or geospatial exports."
        )
        note.setWordWrap(True)
        note.setProperty("muted", True)
        info_group_layout.addWidget(note)
        info_layout.addWidget(info_group)
        info_layout.addStretch(1)
        self.geospatial_side_tabs.addTab(info_page, "Info")
        side_layout.addWidget(self.geospatial_side_tabs, 1)

        map_card = QFrame(tab)
        map_card.setProperty("plotCard", True)
        map_layout = QVBoxLayout(map_card)
        map_layout.setContentsMargins(4, 4, 4, 4)
        self.geospatial_view = GoogleGeospatialView(map_card, title="Seismic Geometry — Satellite & 3D Terrain")
        map_layout.addWidget(self.geospatial_view, 1)

        splitter.addWidget(sidebar)
        splitter.addWidget(map_card)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([315, 1315])
        layout.addWidget(splitter, 1)
        return tab

    def _build_qc_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        controls = QFrame()
        controls.setProperty("card", True)
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(10, 8, 10, 8)
        self.detect_qc_button = self._button("Detect Bad Traces", "danger")
        self.qc_summary_label = QLabel("No QC analysis has been run")
        self.qc_summary_label.setWordWrap(True)
        controls_layout.addWidget(self.detect_qc_button)
        controls_layout.addWidget(self.qc_summary_label, 1)
        layout.addWidget(controls)

        qc_card = QFrame()
        qc_card.setProperty("plotCard", True)
        qc_layout = QVBoxLayout(qc_card)
        qc_layout.setContentsMargins(4, 4, 4, 4)
        self.qc_panel = SeismicQcPanel()
        qc_layout.addWidget(self.qc_panel)
        layout.addWidget(qc_card, 1)
        return tab

    def _build_outputs_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)

        output_tabs = QTabWidget()
        output_tabs.setObjectName("seismicToolTabs")
        output_tabs.addTab(self._build_session_page(), "Sessions")
        output_tabs.addTab(self._build_export_page(), "Data Exports")
        output_tabs.addTab(self._build_report_page(), "Reports")
        layout.addWidget(output_tabs)
        return tab

    def _build_session_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        group = QGroupBox("Interpretation Session")
        group_layout = QVBoxLayout(group)
        self.save_session_button = self._button("Save Current Session", "success")
        self.load_session_button = self._button("Load Existing Session", "primary")
        group_layout.addWidget(self.save_session_button)
        group_layout.addWidget(self.load_session_button)
        note = QLabel("Sessions preserve section settings, gain, picks, wells, QC flags, and 3D view state.")
        note.setProperty("muted", True)
        note.setWordWrap(True)
        group_layout.addWidget(note)
        layout.addWidget(group)
        layout.addStretch(1)
        return page

    def _build_export_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        group = QGroupBox("Data and Image Exports")
        grid = QGridLayout(group)
        self.export_png_button = self._button("Export 2D PNG", "primary")
        self.export_geotiff_button = self._button("Export GeoTIFF", "primary")
        self.export_kml_button = self._button("Export KML / KMZ", "success")
        self.export_shapefile_button = self._button("Export Horizon Shapefile", "success")
        self.export_animation_button = self._button("Export Time-Slice GIF", "warning")
        grid.addWidget(self.export_png_button, 0, 0)
        grid.addWidget(self.export_geotiff_button, 0, 1)
        grid.addWidget(self.export_kml_button, 1, 0)
        grid.addWidget(self.export_shapefile_button, 1, 1)
        grid.addWidget(self.export_animation_button, 2, 0, 1, 2)
        layout.addWidget(group)
        layout.addStretch(1)
        return page

    def _build_report_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        group = QGroupBox("Integrated QC Reports")
        group_layout = QVBoxLayout(group)
        self.export_html_button = self._button("Interactive HTML Report", "primary")
        self.export_pdf_button = self._button("PDF Sections Report", "danger")
        group_layout.addWidget(self.export_html_button)
        group_layout.addWidget(self.export_pdf_button)
        note = QLabel("Reports use the same report registration and output tracking as the existing QC system.")
        note.setProperty("muted", True)
        note.setWordWrap(True)
        group_layout.addWidget(note)
        layout.addWidget(group)
        layout.addStretch(1)
        return page

    def _scroll_page(self, widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        widget.setMinimumWidth(305)
        scroll.setWidget(widget)
        return scroll

    def _button(self, text: str, role: str) -> QPushButton:
        button = QPushButton(text)
        button.setProperty("role", role)
        button.setMinimumHeight(28)
        button.setCursor(Qt.PointingHandCursor)
        return button

    def _apply_local_style(self) -> None:
        self.setStyleSheet(
            f"QWidget#seismicVisualizationDashboard{{background:#EEF2F6;color:#172B3A;font-size:{FONT_SIZE_NORMAL}pt;}}"
            "QWidget#seismicVisualizationDashboard QFrame[card='true']{background:#FFFFFF;border:1px solid #C6D1DA;border-radius:6px;}"
            "QWidget#seismicVisualizationDashboard QFrame[plotCard='true']{background:#07131F;border:1px solid #9AAEBE;border-radius:5px;}"
            "QWidget#seismicVisualizationDashboard QFrame[statusBar='true']{background:#FFFFFF;border:1px solid #C6D1DA;border-radius:4px;}"
            f"QWidget#seismicVisualizationDashboard QLabel#seismicFileLabel{{font-weight:600;color:#17384F;font-size:{FONT_SIZE_NORMAL}pt;}}"
            f"QWidget#seismicVisualizationDashboard QLabel#seismicMetadataLabel{{color:#425E72;font-size:{FONT_SIZE_SMALL}pt;}}"
            f"QWidget#seismicVisualizationDashboard QLabel[muted='true']{{color:#627889;font-size:{FONT_SIZE_SMALL}pt;}}"
            f"QWidget#seismicVisualizationDashboard QLabel[valueBadge='true']{{background:#E8F2FD;border:1px solid #9BC3EA;border-radius:4px;padding:4px;color:#0B5FAC;font-weight:600;font-size:{FONT_SIZE_SMALL}pt;}}"
            f"QWidget#seismicVisualizationDashboard QGroupBox{{background:#FFFFFF;border:1px solid #B9C7D2;border-radius:5px;margin-top:12px;padding:8px 7px 6px 7px;font-weight:600;color:#18384F;font-size:{FONT_SIZE_NORMAL}pt;}}"
            f"QWidget#seismicVisualizationDashboard QGroupBox::title{{subcontrol-origin:margin;left:9px;padding:0 4px;background:#FFFFFF;font-size:{FONT_SIZE_NORMAL}pt;}}"
            "QWidget#seismicVisualizationDashboard QTabWidget::pane{border:1px solid #AFC2D0;background:#F8FAFC;border-radius:5px;} QTabBar::tab{padding:7px 14px;margin-right:2px;background:#E6EEF4;border:1px solid #B8C8D4;border-bottom:0;} QTabBar::tab:selected{background:#FFFFFF;color:#0B5D8A;font-weight:700;border-top:3px solid #1D87C9;} QTabBar::tab:hover:!selected{background:#D7EAF6;}"
            f"QWidget#seismicVisualizationDashboard QTabBar::tab{{background:#E4EBF1;border:1px solid #B9C7D2;border-bottom:none;padding:6px 12px;margin-right:2px;min-width:78px;color:#29475B;font-size:{FONT_SIZE_SMALL}pt;}}"
            f"QWidget#seismicVisualizationDashboard QTabBar::tab:selected{{background:#FFFFFF;color:#0B5FAC;font-weight:600;border-top:3px solid #1273DE;padding-top:4px;}}"
            "QWidget#seismicVisualizationDashboard QLineEdit,"
            "QWidget#seismicVisualizationDashboard QComboBox,"
            "QWidget#seismicVisualizationDashboard QSpinBox,"
            f"QWidget#seismicVisualizationDashboard QDoubleSpinBox{{background:#FFFFFF;border:1px solid #AABBC8;border-radius:4px;padding:3px 6px;min-height:22px;font-size:{FONT_SIZE_NORMAL}pt;}}"
            "QWidget#seismicVisualizationDashboard QLineEdit:focus,"
            "QWidget#seismicVisualizationDashboard QComboBox:focus,"
            "QWidget#seismicVisualizationDashboard QSpinBox:focus,"
            "QWidget#seismicVisualizationDashboard QDoubleSpinBox:focus{border:1px solid #1273DE;}"
            f"QWidget#seismicVisualizationDashboard QPushButton{{border:1px solid transparent;border-radius:4px;padding:5px 11px;font-weight:600;font-size:{FONT_SIZE_NORMAL}pt;}}"
            "QWidget#seismicVisualizationDashboard QPushButton[role='primary']{background:#126FD1;color:#FFFFFF;border-color:#0B5FAC;}"
            "QWidget#seismicVisualizationDashboard QPushButton[role='primary']:hover{background:#0D5FB7;}"
            "QWidget#seismicVisualizationDashboard QPushButton[role='success']{background:#168A57;color:#FFFFFF;border-color:#0F7045;}"
            "QWidget#seismicVisualizationDashboard QPushButton[role='success']:hover{background:#117548;}"
            "QWidget#seismicVisualizationDashboard QPushButton[role='warning']{background:#D97706;color:#FFFFFF;border-color:#B45F05;}"
            "QWidget#seismicVisualizationDashboard QPushButton[role='warning']:hover{background:#B96105;}"
            "QWidget#seismicVisualizationDashboard QPushButton[role='danger']{background:#C43D3D;color:#FFFFFF;border-color:#A62F2F;}"
            "QWidget#seismicVisualizationDashboard QPushButton[role='danger']:hover{background:#A93232;}"
            "QWidget#seismicVisualizationDashboard QPushButton[role='secondary']{background:#E7EDF2;color:#203B4E;border-color:#AFC0CC;}"
            "QWidget#seismicVisualizationDashboard QPushButton[role='secondary']:hover{background:#D7E1E8;}"
            "QWidget#seismicVisualizationDashboard QPushButton:disabled{background:#C9D2D9;color:#7D8C97;border-color:#B6C0C7;}"
            f"QWidget#seismicVisualizationDashboard QToolButton{{background:#126FD1;color:#FFFFFF;border:1px solid #0B5FAC;border-radius:4px;padding:4px 8px;font-weight:600;font-size:{FONT_SIZE_NORMAL}pt;}}"
            "QWidget#seismicVisualizationDashboard QCheckBox{spacing:6px;}"
            f"QWidget#seismicVisualizationDashboard QCheckBox{{font-size:{FONT_SIZE_NORMAL}pt;}}"
            "QWidget#seismicVisualizationDashboard QSlider::groove:horizontal{height:5px;background:#D2DCE4;border-radius:2px;}"
            "QWidget#seismicVisualizationDashboard QSlider::sub-page:horizontal{background:#1273DE;border-radius:2px;}"
            "QWidget#seismicVisualizationDashboard QSlider::handle:horizontal{background:#FFFFFF;border:2px solid #1273DE;width:14px;margin:-5px 0;border-radius:7px;}"
            "QWidget#seismicVisualizationDashboard QSplitter::handle{background:#D8E1E8;width:5px;}"
        )

    def _connect_signals(self) -> None:
        self.open_button.clicked.connect(self.open_file)
        self.apply_button.clicked.connect(self.reload_section)
        self.display_combo.currentIndexChanged.connect(
            lambda: self.view_2d.set_display_mode(str(self.display_combo.currentData()))
        )
        self.label_combo.currentIndexChanged.connect(
            lambda: self.view_2d.set_label_mode(str(self.label_combo.currentData()))
        )
        self.attribute_combo.currentIndexChanged.connect(self._apply_attribute_settings)
        for widget in (
            self.rms_window_spin,
            self.coherence_window_spin,
            self.coherence_radius_spin,
            self.minimum_frequency_spin,
        ):
            widget.valueChanged.connect(self._apply_attribute_settings)
        for widget in (self.gain_spin, self.clip_spin, self.agc_window_spin):
            widget.valueChanged.connect(self._apply_gain_settings)
        self.agc_check.toggled.connect(self._apply_gain_settings)
        self.normalize_check.toggled.connect(self._apply_gain_settings)
        self.noise_overlay_check.toggled.connect(self.view_2d.set_noise_overlay_visible)
        self.pick_color_button.clicked.connect(self._choose_pick_color)
        self.horizon_button.clicked.connect(lambda: self._begin_pick("horizon"))
        self.fault_button.clicked.connect(lambda: self._begin_pick("fault"))
        self.measure_button.clicked.connect(lambda: self._begin_pick("measurement"))
        self.stop_pick_button.clicked.connect(self.view_2d.stop_picking)
        self.undo_pick_button.clicked.connect(self.view_2d.undo_last_pick)
        self.fit_button.clicked.connect(self.view_2d.fit_view)
        self.detect_qc_button.clicked.connect(self.detect_bad_traces)
        self.load_volume_button.clicked.connect(self.load_3d_volume)
        for control in (self.max_inline_spin, self.max_crossline_spin, self.max_volume_samples_spin):
            control.valueChanged.connect(self._schedule_volume_reload)
        self.apply_volume_attribute_button.clicked.connect(self.apply_3d_attribute)
        self.show_volume_button.clicked.connect(self.show_volume)
        self.volume_mode_combo.currentIndexChanged.connect(self._update_3d_mode)
        self.slice_slider.valueChanged.connect(self._update_3d_slice)
        self.opacity_slider.valueChanged.connect(self._update_3d_opacity)
        self.volume_clip_spin.valueChanged.connect(self._update_3d_transfer_function)
        self.volume_threshold_spin.valueChanged.connect(self._update_3d_transfer_function)
        self.inline_button.clicked.connect(self.show_inline_slice)
        self.crossline_button.clicked.connect(self.show_crossline_slice)
        self.time_slice_button.clicked.connect(self.show_time_slice)
        self.orthogonal_button.clicked.connect(self.show_orthogonal_slices)
        self.camera_button.clicked.connect(self.reset_3d_camera)
        self.add_well_button.clicked.connect(self.add_well_path)
        self.save_session_button.clicked.connect(self.save_session)
        self.load_session_button.clicked.connect(self.load_session)
        self.export_png_button.clicked.connect(self.export_png)
        self.export_geotiff_button.clicked.connect(self.export_geotiff)
        self.export_kml_button.clicked.connect(self.export_kml)
        self.export_shapefile_button.clicked.connect(self.export_shapefile)
        self.export_animation_button.clicked.connect(self.export_animation)
        self.export_html_button.clicked.connect(self.export_html_report)
        self.export_pdf_button.clicked.connect(self.export_pdf_report)
        self.view_2d.cursor_changed.connect(self._on_cursor_changed)
        self.view_2d.interpretations_changed.connect(self._sync_interpretations)
        self.view_2d.measurement_completed.connect(self._show_status)
        self.qc_panel.trace_selected.connect(self._center_on_trace)
        self.view_3d.gpu_status_changed.connect(self._show_status)
        self.tabs.currentChanged.connect(self._on_main_tab_changed)

    def open_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open SEG-Y or SEG-D",
            str(self._current_path.parent if self._current_path else Path.home()),
            "Seismic Files (*.sgy *.segy *.segd *.sgd *.d *.dat);;SEG-Y (*.sgy *.segy);;SEG-D (*.segd *.sgd *.d *.dat);;All Files (*.*)",
        )
        if file_path:
            self.open_path(file_path)

    def open_path(self, file_path: str | Path) -> None:
        path = Path(file_path).expanduser().resolve()
        if self._closing:
            return
        if self._busy_count > 0:
            self._pending_open_path = path
            self._show_status(f"Queued seismic file: {path.name}")
            return
        if self.data_source is not None and self._current_path == path:
            self._show_status(f"Already open: {path.name}")
            return
        self._start_open_path(path)

    def _start_open_path(self, path: Path) -> None:
        self._pending_open_path = None
        self._run_async(
            lambda report: self._prepare_source(path, report),
            self._accept_source,
            "Opening seismic file",
            f"Preparing {path.name}",
        )

    def _prepare_source(
        self,
        path: Path,
        report: ProgressReporter,
    ) -> tuple[
        UnifiedSeismicDataSource,
        dict[str, Any],
        SectionData,
        dict[str, np.ndarray],
        list[QcTraceFlag],
        np.ndarray,
        np.ndarray,
    ]:
        source: UnifiedSeismicDataSource | None = None
        try:
            report(5, "Validating file and initializing the seismic reader")
            source = UnifiedSeismicDataSource(path, self.database_engine)
            report(25, "Reading and indexing seismic headers")
            metadata = source.metadata()
            preview_traces = min(240, source.total_traces)
            preview_samples = min(1600, source.total_samples)
            request = SectionRequest(
                trace_start=0,
                trace_count=max(1, preview_traces),
                sample_start=0,
                sample_count=max(1, preview_samples),
            )
            report(48, "Reading the initial 2D section")
            section = source.read_section(request)
            report(68, "Calculating noise overlay and display statistics")
            noise_indices, noise_scores = self._calculate_noise_overlay(section)
            report(82, "Preparing geometry QC data")
            geometry = source.geometry(maximum_points=60_000)
            report(92, "Loading existing QC trace flags")
            existing_flags = source.load_existing_qc_flags()
            report(100, "File is ready")
            return (
                source,
                metadata,
                section,
                geometry,
                existing_flags,
                noise_indices,
                noise_scores,
            )
        except Exception:
            if source is not None:
                source.close()
            raise

    def _accept_source(self, payload: object) -> None:
        (
            source,
            metadata,
            section,
            geometry,
            flags,
            noise_indices,
            noise_scores,
        ) = payload
        if self.data_source is not None:
            self.data_source.close()
        self.data_source = source
        self._current_path = source.file_path
        self._geometry_cache = geometry
        if hasattr(self, "geometry_map"):
            self.geometry_map.set_geometry(geometry)
        self._refresh_map_summary(metadata, geometry)
        self._refresh_geospatial()
        self.volume = None
        self.raw_volume = None
        self.qc_flags = list(flags)
        self.interpretations = []
        self.wells = []
        self.setProperty("seismic_visualization_file_path", str(self._current_path))

        self.file_label.setText(f"{source.format_name}: {self._current_path.name}")
        self.file_label.setToolTip(str(self._current_path))
        geometry_text = "3D geometry" if bool(metadata.get("has_3d_geometry")) else "2D/curtain geometry"
        self.metadata_label.setText(
            f"{metadata.get('trace_count', source.total_traces):,} traces  |  "
            f"{metadata.get('sample_count', source.total_samples):,} samples  |  "
            f"{source.sample_interval_ms:g} ms  |  {geometry_text}"
        )

        widgets = [
            self.trace_start_spin,
            self.trace_count_spin,
            self.sample_start_spin,
            self.sample_count_spin,
            self.trace_decimation_spin,
            self.sample_decimation_spin,
            self.normalize_check,
            self.clip_spin,
        ]
        blockers = [QSignalBlocker(widget) for widget in widgets]
        self.trace_start_spin.setRange(0, max(0, source.total_traces - 1))
        self.trace_count_spin.setMaximum(max(1, source.total_traces))
        self.trace_count_spin.setValue(min(240, max(1, source.total_traces)))
        self.sample_start_spin.setRange(0, max(0, source.total_samples - 1))
        self.sample_count_spin.setMaximum(max(1, source.total_samples))
        self.sample_count_spin.setValue(min(1600, max(1, source.total_samples)))
        self.trace_decimation_spin.setMaximum(max(1, source.total_traces))
        self.trace_decimation_spin.setValue(1)
        self.sample_decimation_spin.setMaximum(max(1, source.total_samples))
        self.sample_decimation_spin.setValue(1)
        self.normalize_check.setChecked(source.is_segd)
        self.clip_spin.setValue(98.5)
        del blockers

        gain_settings = self.current_gain_settings()
        display_mode = str(self.display_combo.currentData())
        try:
            self.view_2d.set_scene(
                section=section,
                gain_settings=gain_settings,
                display_mode=display_mode,
                label_mode=str(self.label_combo.currentData()),
                qc_flags=self.qc_flags,
                interpretations=self.interpretations,
                noise_trace_indices=noise_indices,
                noise_scores=noise_scores,
                noise_overlay_visible=self.noise_overlay_check.isChecked(),
            )
        except Exception:
            fallback_index = self.display_combo.findData("variable_density")
            if fallback_index >= 0:
                with QSignalBlocker(self.display_combo):
                    self.display_combo.setCurrentIndex(fallback_index)
            self.view_2d.set_scene(
                section=section,
                gain_settings=gain_settings,
                display_mode="variable_density",
                label_mode=str(self.label_combo.currentData()),
                qc_flags=self.qc_flags,
                interpretations=self.interpretations,
                noise_trace_indices=noise_indices,
                noise_scores=noise_scores,
                noise_overlay_visible=self.noise_overlay_check.isChecked(),
            )
        self._apply_attribute_settings()
        self.qc_panel.set_section(section)
        self.qc_panel.set_geometry(geometry)
        self.qc_panel.set_flags(self.qc_flags)
        self.qc_summary_label.setText(
            f"{len(self.qc_flags)} existing flagged traces" if self.qc_flags else "No flagged traces"
        )

        self.view_3d.clear()
        self.view_3d.set_interpretations(self.interpretations)
        self.view_3d.set_wells(self.wells)
        self.volume_status_label.setText("No volume loaded")
        if source.has_3d_geometry:
            self.volume_kind_label.setText("SEG-Y 3D geometry detected. True inline/crossline volume rendering is available.")
            self.load_volume_button.setText("Load 3D Volume")
        else:
            self.volume_kind_label.setText(
                f"{source.format_name} does not contain a complete 3D inline/crossline grid. A spatial seismic curtain will be generated."
            )
            self.load_volume_button.setText("Build 3D Seismic Curtain")
        self.slice_slider.setRange(0, 0)
        self.slice_slider.setEnabled(False)
        self.slice_value_label.setText("Volume")
        self.tabs.setCurrentIndex(self.TAB_2D)
        self.tools_2d_tabs.setCurrentIndex(0)
        self._show_status(
            f"Opened successfully: {self._current_path.name} — "
            f"{source.total_traces:,} traces, {source.total_samples:,} samples"
        )

    def _refresh_map_summary(self, metadata: dict[str, Any], geometry: dict[str, np.ndarray]) -> None:
        if not hasattr(self, "map_summary_label"):
            return
        def finite_count(x_key: str, y_key: str) -> int:
            x = np.asarray(geometry.get(x_key, []), dtype=float)
            y = np.asarray(geometry.get(y_key, []), dtype=float)
            n = min(x.size, y.size)
            if n == 0:
                return 0
            valid = np.isfinite(x[:n]) & np.isfinite(y[:n]) & ~((x[:n] == 0) & (y[:n] == 0))
            return int(np.count_nonzero(valid))

        source_count = finite_count("source_x", "source_y")
        receiver_count = finite_count("receiver_x", "receiver_y")
        midpoint_count = finite_count("midpoint_x", "midpoint_y")
        geometry_type = "3D inline/crossline" if bool(metadata.get("has_3d_geometry")) else "2D / curtain"
        coordinate_units = metadata.get("coordinate_units") or metadata.get("coordinate_unit") or "from source headers"
        self.map_summary_label.setText(
            f"Geometry type: {geometry_type}\n\n"
            f"Valid source positions: {source_count:,}\n"
            f"Valid receiver positions: {receiver_count:,}\n"
            f"Valid midpoint/CDP positions: {midpoint_count:,}\n\n"
            f"Coordinate units: {coordinate_units}\n\n"
            "The map remains in source XY coordinates until a verified CRS is supplied for geospatial conversion."
        )

    def reload_section(self) -> None:
        self.tabs.setCurrentIndex(self.TAB_2D)
        if self.data_source is None:
            self.open_file()
            return
        request = self.current_section_request()
        self._run_async(
            lambda report: self._prepare_section(request, report),
            self._accept_section,
            "Loading seismic section",
            "Reading selected traces and samples",
        )

    def _prepare_section(
        self,
        request: SectionRequest,
        report: ProgressReporter,
    ) -> tuple[SectionData, np.ndarray, np.ndarray]:
        if self.data_source is None:
            raise RuntimeError("No seismic file is open")
        report(10, "Reading selected trace window")
        section = self.data_source.read_section(request)
        report(72, "Calculating noise overlay")
        noise_indices, noise_scores = self._calculate_noise_overlay(section)
        report(100, "Section is ready")
        return section, noise_indices, noise_scores

    def _accept_section(self, payload: object) -> None:
        section, noise_indices, noise_scores = payload
        self.view_2d.set_scene(
            section=section,
            gain_settings=self.current_gain_settings(),
            display_mode=str(self.display_combo.currentData()),
            label_mode=str(self.label_combo.currentData()),
            qc_flags=self.qc_flags,
            interpretations=self.interpretations,
            noise_trace_indices=noise_indices,
            noise_scores=noise_scores,
            noise_overlay_visible=self.noise_overlay_check.isChecked(),
        )
        self._apply_attribute_settings()
        self.qc_panel.set_section(section)
        if section.trace_indices.size and section.sample_indices.size:
            self._show_status(
                f"Section loaded: traces {int(section.trace_indices[0]) + 1:,}–{int(section.trace_indices[-1]) + 1:,}; "
                f"samples {int(section.sample_indices[0]) + 1:,}–{int(section.sample_indices[-1]) + 1:,}"
            )
        else:
            self._show_status("The selected section contains no readable traces or samples")

    @staticmethod
    def _calculate_noise_overlay(section: SectionData) -> tuple[np.ndarray, np.ndarray]:
        result = calculate_noise_metrics(
            section.amplitudes,
            section.trace_indices,
            section.sample_interval_ms,
        )
        if result.trace_indices.size == 0:
            return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.float32)
        positive_rms = result.rms[result.rms > 0]
        rms_reference = float(np.median(positive_rms)) if positive_rms.size else 1.0
        rms_score = np.clip(result.rms / max(rms_reference * 3.0, 1e-12), 0.0, 1.0)
        composite = np.clip(
            0.45 * rms_score
            + 0.30 * result.high_frequency_ratio
            + 0.25 * result.incoherence,
            0.0,
            1.0,
        ).astype(np.float32)
        return result.trace_indices.astype(np.int64), composite

    def current_section_request(self) -> SectionRequest:
        return SectionRequest(
            trace_start=self.trace_start_spin.value(),
            trace_count=self.trace_count_spin.value(),
            sample_start=self.sample_start_spin.value(),
            sample_count=self.sample_count_spin.value(),
            trace_decimation=self.trace_decimation_spin.value(),
            sample_decimation=self.sample_decimation_spin.value(),
        )

    def current_gain_settings(self) -> GainSettings:
        return GainSettings(
            scalar=self.gain_spin.value(),
            clip_percentile=self.clip_spin.value(),
            agc_enabled=self.agc_check.isChecked(),
            agc_window_ms=self.agc_window_spin.value(),
            normalize_traces=self.normalize_check.isChecked(),
        )

    def _apply_gain_settings(self, *_args) -> None:
        self.view_2d.set_gain_settings(self.current_gain_settings())

    def current_attribute_parameters(self) -> AttributeParameters:
        return AttributeParameters(
            rms_window_ms=self.rms_window_spin.value(),
            coherence_window_ms=self.coherence_window_spin.value(),
            coherence_trace_radius=self.coherence_radius_spin.value(),
            minimum_frequency_hz=self.minimum_frequency_spin.value(),
        )

    def _apply_attribute_settings(self, *_args) -> None:
        if not hasattr(self, "attribute_combo"):
            return
        attribute = str(self.attribute_combo.currentData() or "amplitude")
        setter = getattr(self.view_2d, "set_attribute_mode", None)
        if not callable(setter):
            # Do not make opening a seismic file fail if a user has accidentally
            # mixed an older Seismic2DView with the newer dashboard.  The
            # synchronized visualization patch restores the full attribute API;
            # this guard keeps amplitude viewing usable until all files match.
            if attribute != "amplitude":
                amplitude_index = self.attribute_combo.findData("amplitude")
                if amplitude_index >= 0 and self.attribute_combo.currentIndex() != amplitude_index:
                    blocker = QSignalBlocker(self.attribute_combo)
                    self.attribute_combo.setCurrentIndex(amplitude_index)
                    del blocker
            self._show_status(
                "2D attribute engine unavailable: visualization files are from different versions."
            )
            return
        setter(attribute, self.current_attribute_parameters())
        attribute_label = self.attribute_combo.currentText()
        if self.view_2d.section is not None:
            self._show_status(f"2D display attribute: {attribute_label}")

    def show_geospatial_view(self, mode: str = "2d") -> None:
        if self.data_source is None:
            QMessageBox.information(self, "Seismic Satellite / 3D", "Open a SEG-Y or georeferenced seismic file first.")
            return
        self.tabs.setCurrentIndex(self.TAB_GEOSPATIAL)
        self._refresh_geospatial()
        self.geospatial_view.set_mode("3d" if str(mode).lower().startswith("3") else "2d")

    def _refresh_geospatial(self) -> None:
        if not hasattr(self, "geospatial_view"):
            return
        geometry = self._geometry_cache
        if self.data_source is None or not geometry:
            self.geospatial_view.clear_tracks()
            return
        x = np.asarray(geometry.get("midpoint_x", []), dtype=float)
        y = np.asarray(geometry.get("midpoint_y", []), dtype=float)
        if not x.size or x.size != y.size:
            self.geospatial_view.clear_tracks()
            return
        units = np.asarray(geometry.get("coordinate_units", np.zeros(x.size)), dtype=int)
        crs_text = self.seismic_crs_edit.text().strip() if hasattr(self, "seismic_crs_edit") else ""
        try:
            nonzero_units = units[units != 0]
            common_unit = int(np.bincount(nonzero_units).argmax()) if nonzero_units.size else 0
            if common_unit == 3:
                coords = to_wgs84(x, y, crs="EPSG:4326", allow_lonlat_inference=True)
            elif common_unit == 2:
                coords = to_wgs84(x / 3600.0, y / 3600.0, crs="EPSG:4326", allow_lonlat_inference=True)
            else:
                coords = to_wgs84(x, y, crs=crs_text or None, allow_lonlat_inference=True)
        except CoordinateTransformError as exc:
            self.geospatial_view.clear_tracks()
            self.geospatial_view.set_status_message(str(exc))
            return
        valid = coords.valid_mask
        if not np.any(valid):
            self.geospatial_view.clear_tracks()
            self.geospatial_view.set_status_message("No valid geographic seismic geometry is available for satellite/3D display.")
            return
        tracks: list[GeoTrack] = []
        inline = np.asarray(geometry.get("inline", np.zeros(x.size)), dtype=int)
        unique_inline = np.unique(inline[(inline != 0) & valid])
        # Keep the browser payload bounded on large 3D surveys while preserving representative survey lines.
        if unique_inline.size:
            step = max(1, int(np.ceil(unique_inline.size / 80)))
            for il in unique_inline[::step]:
                idx = np.flatnonzero((inline == il) & valid)
                if idx.size:
                    order = np.argsort(np.asarray(geometry.get("crossline", np.arange(x.size)))[idx])
                    idx = idx[order]
                    tracks.append(GeoTrack(f"Inline {int(il)}", coords.longitude[idx], coords.latitude[idx], coords.altitude_m[idx]))
        if not tracks:
            idx = np.flatnonzero(valid)
            tracks.append(GeoTrack(self._current_path.name if self._current_path else "Seismic Geometry", coords.longitude[idx], coords.latitude[idx], coords.altitude_m[idx]))
        self.geospatial_view.set_tracks(tracks, render=self.tabs.currentIndex() == self.TAB_GEOSPATIAL)

    def set_display_mode(self, mode: str) -> None:
        self.tabs.setCurrentIndex(self.TAB_2D)
        self.tools_2d_tabs.setCurrentIndex(1)
        index = self.display_combo.findData(mode)
        if index >= 0:
            self.display_combo.setCurrentIndex(index)
        self.view_2d.set_display_mode(mode)

    def set_gain_mode(self, mode: str) -> None:
        self.tabs.setCurrentIndex(self.TAB_2D)
        self.tools_2d_tabs.setCurrentIndex(1)
        normalized = mode.lower()
        if normalized == "agc":
            self.agc_check.setChecked(True)
            self.normalize_check.setChecked(False)
        elif normalized in {"trace_balance", "balance"}:
            self.agc_check.setChecked(False)
            self.normalize_check.setChecked(True)
        else:
            self.agc_check.setChecked(False)
            self.normalize_check.setChecked(False)
        self._apply_gain_settings()

    def detect_bad_traces(self) -> None:
        section = self.view_2d.section
        if section is None:
            QMessageBox.information(self, "QC", "Load a seismic section first.")
            return
        detected = detect_bad_traces(section.amplitudes, section.trace_indices)
        merged: dict[int, QcTraceFlag] = {flag.trace_index: flag for flag in self.qc_flags}
        for flag in detected:
            existing = merged.get(flag.trace_index)
            if existing is None or existing.source != "SEG-Y QC":
                merged[flag.trace_index] = flag
        self.qc_flags = sorted(merged.values(), key=lambda item: item.trace_index)
        self.view_2d.set_qc_flags(self.qc_flags)
        self.qc_panel.set_flags(self.qc_flags)
        self.qc_summary_label.setText(
            f"Detected {len(detected)} bad traces in this section; {len(self.qc_flags)} total flags"
        )
        self.tabs.setCurrentIndex(self.TAB_QC)
        self._show_status(self.qc_summary_label.text())

    def _schedule_volume_reload(self, *_args) -> None:
        if self.data_source is None:
            return
        self.raw_volume = None
        self.volume = None
        self.volume_status_label.setText("Volume limits changed — refreshing automatically…")
        self._volume_reload_timer.start()

    def _reload_volume_from_controls(self) -> None:
        if self.data_source is None:
            return
        if self.tabs.currentIndex() != self.TAB_3D:
            return
        self.load_3d_volume()

    def reset_3d_camera(self) -> None:
        self.tabs.setCurrentIndex(self.TAB_3D)
        self.tools_3d_tabs.setCurrentIndex(2)
        self.view_3d.reset_camera()
        self._show_status("3D camera reset to default inline/crossline/time view")

    def load_3d_volume(self) -> None:
        self.tabs.setCurrentIndex(self.TAB_3D)
        self.tools_3d_tabs.setCurrentIndex(0)
        if self.data_source is None:
            self.open_file()
            return
        max_inlines = self.max_inline_spin.value()
        max_crosslines = self.max_crossline_spin.value()
        max_samples = self.max_volume_samples_spin.value()
        self._run_async(
            lambda report: self._prepare_volume(
                max_inlines,
                max_crosslines,
                max_samples,
                report,
            ),
            self._accept_volume,
            "Preparing 3D seismic view",
            "Lazy loading and decimating seismic data",
        )

    def _prepare_volume(
        self,
        max_inlines: int,
        max_crosslines: int,
        max_samples: int,
        report: ProgressReporter,
    ) -> VolumeData:
        if self.data_source is None:
            raise RuntimeError("No seismic file is open")
        report(10, "Scanning inline and crossline geometry")
        report(28, "Reading decimated seismic traces")
        volume = self.data_source.load_volume(
            max_inlines=max_inlines,
            max_crosslines=max_crosslines,
            max_samples=max_samples,
        )
        report(82, "Preparing GPU-ready amplitude volume")
        # Missing bins/samples remain NaN and are rendered transparent. Replacing
        # them with zero would manufacture false zero-amplitude seismic events.
        report(100, "3D view is ready")
        return volume

    def _accept_volume(self, volume: object) -> None:
        self.raw_volume = volume
        self.volume = volume
        amplitude_index = self.volume_attribute_combo.findData("amplitude")
        if amplitude_index >= 0:
            blocker = QSignalBlocker(self.volume_attribute_combo)
            self.volume_attribute_combo.setCurrentIndex(amplitude_index)
            del blocker
        self.view_3d.set_volume(volume, self.opacity_slider.value() / 100.0)
        self.view_3d.set_interpretations(self.interpretations)
        self.view_3d.set_wells(self.wells)
        self._configure_slice_slider()
        shape_text = f"{volume.amplitudes.shape[0]} × {volume.amplitudes.shape[1]} × {volume.amplitudes.shape[2]}"
        self.volume_status_label.setText(
            f"{'Seismic curtain' if volume.is_pseudo_volume else '3D volume'} loaded: {shape_text}"
        )
        self.tabs.setCurrentIndex(self.TAB_3D)
        self._show_status(self.volume_status_label.text())

    def apply_3d_attribute(self) -> None:
        if self.raw_volume is None:
            self.load_3d_volume()
            return
        attribute = str(self.volume_attribute_combo.currentData() or "amplitude")
        parameters = self.current_attribute_parameters()
        self._run_async(
            lambda report: self._prepare_3d_attribute(self.raw_volume, attribute, parameters, report),
            self._accept_3d_attribute,
            "Calculating 3D seismic attribute",
            ATTRIBUTE_NAMES.get(attribute, attribute),
        )

    @staticmethod
    def _prepare_3d_attribute(
        raw_volume: VolumeData,
        attribute: str,
        parameters: AttributeParameters,
        report: ProgressReporter,
    ) -> VolumeData:
        report(10, f"Preparing {ATTRIBUTE_NAMES.get(attribute, attribute)}")
        if attribute == "amplitude":
            derived = raw_volume.amplitudes
        elif raw_volume.is_pseudo_volume and attribute == "semblance":
            # A pseudo-volume is an extruded 2D curtain. Compute 2D coherence only
            # along real neighboring traces; the artificial extrusion thickness
            # must not increase apparent coherence.
            middle = raw_volume.amplitudes.shape[0] // 2
            section = raw_volume.amplitudes[middle, :, :].T
            derived_section = compute_attribute(
                section, raw_volume.sample_interval_ms, attribute, parameters
            ).T
            derived = np.repeat(derived_section[None, :, :], raw_volume.amplitudes.shape[0], axis=0)
        else:
            derived = compute_volume_attribute(
                raw_volume.amplitudes,
                raw_volume.sample_interval_ms,
                attribute,
                parameters,
            )
        report(90, "Updating 3D display volume")
        result = replace(raw_volume, amplitudes=np.asarray(derived, dtype=np.float32))
        report(100, "3D attribute ready")
        return result

    def _accept_3d_attribute(self, volume: object) -> None:
        self.volume = volume
        self.view_3d.set_volume(volume, self.opacity_slider.value() / 100.0)
        self.view_3d.set_interpretations(self.interpretations)
        self.view_3d.set_wells(self.wells)
        self._configure_slice_slider()
        attribute = str(self.volume_attribute_combo.currentData() or "amplitude")
        label = ATTRIBUTE_NAMES.get(attribute, attribute)
        self.volume_status_label.setText(
            f"{label} — {'seismic curtain' if volume.is_pseudo_volume else '3D volume'} "
            f"{volume.amplitudes.shape[0]} × {volume.amplitudes.shape[1]} × {volume.amplitudes.shape[2]}"
        )
        self.view_3d.show_volume()
        self._show_status(self.volume_status_label.text())

    def show_volume(self) -> None:
        self.tabs.setCurrentIndex(self.TAB_3D)
        self.tools_3d_tabs.setCurrentIndex(0)
        if self.volume is None:
            self.load_3d_volume()
            return
        self.volume_mode_combo.setCurrentIndex(self.volume_mode_combo.findData("volume"))
        self.view_3d.show_volume()

    def show_inline_slice(self) -> None:
        self.tabs.setCurrentIndex(self.TAB_3D)
        self.tools_3d_tabs.setCurrentIndex(1)
        if self.volume is None:
            self.load_3d_volume()
            return
        self.volume_mode_combo.setCurrentIndex(self.volume_mode_combo.findData("inline"))
        self._update_3d_slice()

    def show_crossline_slice(self) -> None:
        self.tabs.setCurrentIndex(self.TAB_3D)
        self.tools_3d_tabs.setCurrentIndex(1)
        if self.volume is None:
            self.load_3d_volume()
            return
        self.volume_mode_combo.setCurrentIndex(self.volume_mode_combo.findData("crossline"))
        self._update_3d_slice()

    def show_time_slice(self) -> None:
        self.tabs.setCurrentIndex(self.TAB_3D)
        self.tools_3d_tabs.setCurrentIndex(1)
        if self.volume is None:
            self.load_3d_volume()
            return
        self.volume_mode_combo.setCurrentIndex(self.volume_mode_combo.findData("time"))
        self._update_3d_slice()

    def show_orthogonal_slices(self) -> None:
        self.tabs.setCurrentIndex(self.TAB_3D)
        self.tools_3d_tabs.setCurrentIndex(1)
        if self.volume is None:
            self.load_3d_volume()
            return
        index = self.volume_mode_combo.findData("orthogonal")
        if index >= 0:
            self.volume_mode_combo.setCurrentIndex(index)
        self._update_3d_mode()

    def _configure_slice_slider(self) -> None:
        if self.volume is None:
            self.slice_slider.setRange(0, 0)
            self.slice_slider.setEnabled(False)
            return
        mode = str(self.volume_mode_combo.currentData())
        if mode == "inline":
            maximum = self.volume.amplitudes.shape[0] - 1
        elif mode == "crossline":
            maximum = self.volume.amplitudes.shape[1] - 1
        elif mode == "time":
            maximum = self.volume.amplitudes.shape[2] - 1
        else:
            maximum = 0
        blocker = QSignalBlocker(self.slice_slider)
        self.slice_slider.setRange(0, max(0, maximum))
        self.slice_slider.setValue(min(self.slice_slider.value(), max(0, maximum)))
        self.slice_slider.setEnabled(mode not in {"volume", "orthogonal"})
        del blocker

    def _update_3d_mode(self, *_args) -> None:
        self._configure_slice_slider()
        if self.volume is None:
            return
        mode = str(self.volume_mode_combo.currentData())
        if mode == "volume":
            self.view_3d.show_volume()
            self.slice_value_label.setText("Volume")
        elif mode == "orthogonal":
            self.view_3d.show_orthogonal_slices()
            self.slice_value_label.setText("IL / XL / Time")
        else:
            self._update_3d_slice()

    def _update_3d_slice(self, *_args) -> None:
        if self.volume is None:
            return
        value = self.slice_slider.value()
        mode = str(self.volume_mode_combo.currentData())
        if mode == "inline":
            self.view_3d.show_inline_slice(value)
            label = str(int(self.volume.inline_values[value])) if self.volume.inline_values.size else str(value)
        elif mode == "crossline":
            self.view_3d.show_crossline_slice(value)
            label = str(int(self.volume.crossline_values[value])) if self.volume.crossline_values.size else str(value)
        elif mode == "time":
            self.view_3d.show_time_slice(value)
            label = f"{float(self.volume.time_ms[value]):.1f} ms" if self.volume.time_ms.size else str(value)
        else:
            self.view_3d.show_volume()
            label = "Volume"
        self.slice_value_label.setText(label)

    def _update_3d_opacity(self, value: int) -> None:
        self.opacity_value_label.setText(f"{value}%")
        self.view_3d.set_opacity(value / 100.0)

    def _update_3d_transfer_function(self, *_args) -> None:
        self.view_3d.set_render_transfer_function(
            self.volume_clip_spin.value(),
            self.volume_threshold_spin.value() / 100.0,
        )

    def _choose_pick_color(self) -> None:
        color = QColorDialog.getColor(parent=self)
        if color.isValid():
            self._pick_color = color.name()
            self.pick_color_button.setStyleSheet(
                f"background:{self._pick_color};color:#FFFFFF;border:1px solid #20455E;border-radius:4px;padding:5px 9px;font-weight:700;"
            )

    def _begin_pick(self, kind: str) -> None:
        self.tabs.setCurrentIndex(self.TAB_2D)
        self.tools_2d_tabs.setCurrentIndex(2)
        name = self.pick_name_edit.text().strip()
        if kind == "measurement":
            name = "Measurement"
        self.view_2d.begin_picking(kind, name, self._pick_color)
        self._show_status(
            f"{kind.title()} picking active; click the 2D section. Picks snap to the local amplitude peak."
        )

    def _sync_interpretations(self) -> None:
        self.interpretations = self.view_2d.interpretations
        self.view_3d.set_interpretations(self.interpretations)

    def add_well_path(self) -> None:
        self.tabs.setCurrentIndex(self.TAB_3D)
        self.tools_3d_tabs.setCurrentIndex(2)
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Well Path CSV",
            str(self._current_path.parent if self._current_path else Path.home()),
            "CSV Files (*.csv);;All Files (*.*)",
        )
        if not file_path:
            return
        try:
            with Path(file_path).open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames is None:
                    raise ValueError("CSV has no header row")
                mapping = {name.strip().lower(): name for name in reader.fieldnames}
                x_key = mapping.get("x") or mapping.get("easting") or mapping.get("longitude")
                y_key = mapping.get("y") or mapping.get("northing") or mapping.get("latitude")
                z_key = mapping.get("z") or mapping.get("tvd") or mapping.get("depth") or mapping.get("elevation")
                if not x_key or not y_key or not z_key:
                    raise ValueError(
                        "CSV must contain X/Y/Z, Easting/Northing/Depth, or Longitude/Latitude/Elevation columns"
                    )
                rows = list(reader)
            well = WellPath(
                name=Path(file_path).stem,
                x=np.asarray([float(row[x_key]) for row in rows], dtype=np.float32),
                y=np.asarray([float(row[y_key]) for row in rows], dtype=np.float32),
                z=np.asarray([float(row[z_key]) for row in rows], dtype=np.float32),
            )
            self.wells.append(well)
            self.view_3d.set_wells(self.wells)
            self._show_status(f"Imported well path: {well.name}")
        except Exception as exc:
            QMessageBox.critical(self, "Well Path Import", str(exc))

    def save_session(self) -> None:
        if self.data_source is None or self._current_path is None:
            QMessageBox.information(self, "Session", "Open a seismic file first.")
            return
        default = self._current_path.with_name(f"{self._current_path.stem}_interpretation.tgpvis")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Interpretation Session",
            str(default),
            "TGP Visualization Session (*.tgpvis);;JSON (*.json)",
        )
        if not file_path:
            return
        stat = self._current_path.stat()
        session = VisualizationSession(
            session_version=1,
            source_path=str(self._current_path),
            source_size=stat.st_size,
            source_mtime_ns=stat.st_mtime_ns,
            display_mode=str(self.display_combo.currentData()),
            section_request=self.current_section_request(),
            gain_settings=self.current_gain_settings(),
            active_time_index=self.slice_slider.value(),
            opacity=self.opacity_slider.value() / 100.0,
            interpretations=self.interpretations,
            wells=self.wells,
            qc_flags=self.qc_flags,
            ui_state={
                "volume_mode": str(self.volume_mode_combo.currentData()),
                "volume_attribute": str(self.volume_attribute_combo.currentData()),
                "noise_overlay": self.noise_overlay_check.isChecked(),
                "label_mode": str(self.label_combo.currentData()),
                "attribute_mode": str(self.attribute_combo.currentData()),
                "rms_window_ms": self.rms_window_spin.value(),
                "coherence_window_ms": self.coherence_window_spin.value(),
                "coherence_trace_radius": self.coherence_radius_spin.value(),
                "minimum_frequency_hz": self.minimum_frequency_spin.value(),
                "active_tab": self.tabs.currentIndex(),
            },
        )
        try:
            output = self.session_store.save(session, file_path)
            self._show_status(f"Session saved: {output}")
        except Exception as exc:
            QMessageBox.critical(self, "Session Save Failed", str(exc))

    def load_session(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Interpretation Session",
            str(self._current_path.parent if self._current_path else Path.home()),
            "TGP Visualization Session (*.tgpvis *.json);;All Files (*.*)",
        )
        if not file_path:
            return
        try:
            session = self.session_store.load(file_path)
        except Exception as exc:
            QMessageBox.critical(self, "Session Load Failed", str(exc))
            return
        source_path = Path(session.source_path).expanduser().resolve()
        if self._current_path != source_path:
            self._run_async(
                lambda report: self._prepare_source(source_path, report),
                lambda payload: self._accept_source_and_session(payload, session),
                "Opening session source",
                f"Preparing {source_path.name}",
            )
        else:
            self._apply_session(session)

    def _accept_source_and_session(self, payload: object, session: VisualizationSession) -> None:
        self._accept_source(payload)
        self._apply_session(session)

    def _apply_session(self, session: VisualizationSession) -> None:
        request = session.section_request
        self.trace_start_spin.setValue(request.trace_start)
        self.trace_count_spin.setValue(request.trace_count)
        self.sample_start_spin.setValue(request.sample_start)
        self.sample_count_spin.setValue(request.sample_count)
        self.trace_decimation_spin.setValue(request.trace_decimation)
        self.sample_decimation_spin.setValue(request.sample_decimation)
        settings = session.gain_settings
        self.gain_spin.setValue(settings.scalar)
        self.clip_spin.setValue(settings.clip_percentile)
        self.agc_check.setChecked(settings.agc_enabled)
        self.agc_window_spin.setValue(settings.agc_window_ms)
        self.normalize_check.setChecked(settings.normalize_traces)
        index = self.display_combo.findData(session.display_mode)
        if index >= 0:
            self.display_combo.setCurrentIndex(index)
        label_mode = session.ui_state.get("label_mode", "auto")
        label_index = self.label_combo.findData(label_mode)
        if label_index >= 0:
            self.label_combo.setCurrentIndex(label_index)
        attribute_mode = session.ui_state.get("attribute_mode", "amplitude")
        attribute_index = self.attribute_combo.findData(attribute_mode)
        if attribute_index >= 0:
            self.attribute_combo.setCurrentIndex(attribute_index)
        self.rms_window_spin.setValue(float(session.ui_state.get("rms_window_ms", 40.0)))
        self.coherence_window_spin.setValue(float(session.ui_state.get("coherence_window_ms", 32.0)))
        self.coherence_radius_spin.setValue(int(session.ui_state.get("coherence_trace_radius", 2)))
        self.minimum_frequency_spin.setValue(float(session.ui_state.get("minimum_frequency_hz", 1.0)))
        self.opacity_slider.setValue(int(round(session.opacity * 100.0)))
        self.interpretations = session.interpretations
        self.wells = session.wells
        self.qc_flags = session.qc_flags
        self.view_2d.set_interpretations(self.interpretations)
        self.view_2d.set_qc_flags(self.qc_flags)
        self.qc_panel.set_flags(self.qc_flags)
        self.view_3d.set_interpretations(self.interpretations)
        self.view_3d.set_wells(self.wells)
        self.noise_overlay_check.setChecked(bool(session.ui_state.get("noise_overlay", True)))
        active_tab = session.ui_state.get("active_tab", self.TAB_2D)
        if isinstance(active_tab, int) and 0 <= active_tab < self.tabs.count():
            self.tabs.setCurrentIndex(active_tab)
        volume_attribute = session.ui_state.get("volume_attribute")
        if volume_attribute:
            attribute_index = self.volume_attribute_combo.findData(volume_attribute)
            if attribute_index >= 0:
                self.volume_attribute_combo.setCurrentIndex(attribute_index)
        volume_mode = session.ui_state.get("volume_mode")
        if volume_mode:
            mode_index = self.volume_mode_combo.findData(volume_mode)
            if mode_index >= 0:
                self.volume_mode_combo.setCurrentIndex(mode_index)
        self.reload_section()
        self._show_status("Interpretation session loaded")

    def export_png(self) -> None:
        if self.view_2d.section is None:
            QMessageBox.information(self, "Export", "Load a seismic section first.")
            return
        default = self._default_output_path("2D_section", ".png")
        file_path, _ = QFileDialog.getSaveFileName(self, "Export PNG", str(default), "PNG (*.png)")
        if not file_path:
            return
        output = Path(file_path).with_suffix(".png")
        if not self.view_2d.grab().save(str(output), "PNG"):
            QMessageBox.critical(self, "Export", "Unable to save the PNG image")
            return
        self._show_status(f"PNG exported: {output}")

    def export_geotiff(self) -> None:
        section = self.view_2d.section
        if section is None:
            QMessageBox.information(self, "Export", "Load a seismic section first.")
            return
        epsg, accepted = QInputDialog.getInt(self, "GeoTIFF CRS", "EPSG code", 4326, 1, 999999)
        if not accepted:
            return
        time_slice_mode = self.volume is not None and str(self.volume_mode_combo.currentData()) == "time"
        default = self._default_output_path("time_slice" if time_slice_mode else "2D_section", ".tif")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export GeoTIFF",
            str(default),
            "GeoTIFF (*.tif *.tiff)",
        )
        if not file_path:
            return
        try:
            if time_slice_mode:
                sample_position = self.slice_slider.value()
                amplitudes = self.volume.amplitudes[:, :, sample_position]
                x_coordinates = self.volume.x_coordinates
                y_coordinates = self.volume.y_coordinates
            else:
                amplitudes = self.view_2d.processed_amplitudes
                x_coordinates = section.x_coordinates
                y_coordinates = section.time_ms
            output = export_geotiff(
                amplitudes,
                file_path,
                x_coordinates,
                y_coordinates,
                epsg,
            )
            self._show_status(f"GeoTIFF exported: {output}")
        except Exception as exc:
            QMessageBox.critical(self, "GeoTIFF Export", str(exc))

    def _section_footprint_interpretation(self) -> InterpretationObject | None:
        section = self.view_2d.section
        if section is None:
            return None
        x = np.asarray(section.x_coordinates, dtype=float).ravel()
        y = np.asarray(section.y_coordinates, dtype=float).ravel()
        if x.size == 0 or y.size == 0:
            return None
        n = min(x.size, y.size)
        x = x[:n]
        y = y[:n]
        valid = np.isfinite(x) & np.isfinite(y) & (np.abs(x) <= 180.0) & (np.abs(y) <= 90.0)
        if np.count_nonzero(valid) < 2:
            return None
        indices = np.flatnonzero(valid)
        if indices.size > 120:
            indices = np.unique(np.linspace(indices[0], indices[-1], 120).astype(int))
            indices = indices[valid[indices]]
        points = [
            InterpretationPoint(
                trace_index=int(section.trace_indices[min(int(index), section.trace_indices.size - 1)]) if section.trace_indices.size else int(index),
                sample_index=0,
                time_ms=0.0,
                x=float(x[index]),
                y=float(y[index]),
            )
            for index in indices
        ]
        return InterpretationObject(
            object_id="section-footprint",
            name="Seismic section footprint",
            kind="horizon",
            points=points,
            visible=True,
            color="#00A7C8",
            metadata={"source": "fallback_section_coordinates"},
        )

    def export_kml(self) -> None:
        export_items = list(self.interpretations)
        if not export_items:
            fallback = self._section_footprint_interpretation()
            if fallback is not None:
                export_items = [fallback]
            else:
                QMessageBox.information(
                    self,
                    "KML / KMZ Export",
                    "Create a horizon/fault interpretation first, or load a section with valid longitude/latitude coordinates so TGPAssure can export a section footprint.",
                )
                return
        default = self._default_output_path("interpretations", ".kmz")
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export KML/KMZ",
            str(default),
            "KMZ (*.kmz);;KML (*.kml)",
        )
        if not file_path:
            return
        try:
            if "KML" in selected_filter and "KMZ" not in selected_filter:
                output = export_kml(
                    export_items,
                    file_path,
                    self._current_path.stem if self._current_path else "TGPAssure",
                )
            else:
                output = export_kmz(
                    export_items,
                    file_path,
                    self._current_path.stem if self._current_path else "TGPAssure",
                )
            self._show_status(f"Interpretations exported: {output}")
        except Exception as exc:
            QMessageBox.critical(self, "KML Export", str(exc))

    def export_shapefile(self) -> None:
        default = self._default_output_path("interpreted_horizons", ".shp")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Horizon Shapefile",
            str(default),
            "Shapefile (*.shp)",
        )
        if not file_path:
            return
        try:
            files = export_horizons_shapefile(self.interpretations, file_path)
            self._show_status(f"Shapefile exported: {files[0]}")
        except Exception as exc:
            QMessageBox.critical(self, "Shapefile Export", str(exc))

    def export_animation(self) -> None:
        if self.volume is None:
            QMessageBox.information(self, "Animation", "Load the 3D volume first.")
            return
        default = self._default_output_path("time_slices", ".gif")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Animated Time Slices",
            str(default),
            "Animated GIF (*.gif)",
        )
        if not file_path:
            return
        self._run_async(
            lambda report: self._prepare_animation(file_path, report),
            lambda output: self._show_status(f"Animation exported: {output}"),
            "Rendering time-slice animation",
            "Generating GIF frames",
        )

    def _prepare_animation(self, file_path: str, report: ProgressReporter):
        if self.volume is None:
            raise RuntimeError("No 3D volume is loaded")
        report(10, "Preparing time-slice frames")
        output = export_time_slice_animation(self.volume, file_path)
        report(100, "Animation is ready")
        return output

    def export_html_report(self) -> None:
        default = self._default_output_path("visualization_report", ".html")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Interactive HTML Report",
            str(default),
            "HTML (*.html)",
        )
        if file_path:
            self._export_report(file_path, "html")

    def export_pdf_report(self) -> None:
        default = self._default_output_path("visualization_report", ".pdf")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export PDF Sections",
            str(default),
            "PDF (*.pdf)",
        )
        if file_path:
            self._export_report(file_path, "pdf")

    def _export_report(self, file_path: str | Path, format_name: str) -> None:
        if self.data_source is None:
            QMessageBox.information(self, "Report", "Open a seismic file first.")
            return
        title = f"Generating {format_name.upper()} Seismic Report"
        self.activity_started.emit(title, "Capturing seismic views and preparing report content")
        QApplication.processEvents()
        try:
            self.activity_progress.emit(15, "Capturing seismic section and QC views")
            QApplication.processEvents()
            with tempfile.TemporaryDirectory(prefix="tgpassure_vis_") as temp_dir:
                images = self._capture_report_images(Path(temp_dir))
                self.activity_progress.emit(48, "Reading seismic metadata and interpretation results")
                QApplication.processEvents()
                metadata = self.data_source.metadata()
                if format_name == "html":
                    output = export_html_report(
                        file_path,
                        metadata,
                        images,
                        self.interpretations,
                        self.qc_flags,
                    )
                else:
                    output = export_pdf_report(
                        file_path,
                        metadata,
                        images,
                        self.interpretations,
                        self.qc_flags,
                    )
            self.activity_progress.emit(90, "Registering report in the project database")
            QApplication.processEvents()
            register_visualization_report(
                self.database_engine,
                output,
                "seismic_visualization",
                f"Seismic Visualization — {self._current_path.name if self._current_path else ''}",
                {
                    "source_file": str(self._current_path) if self._current_path else "",
                    "interpretation_count": len(self.interpretations),
                    "flagged_trace_count": len(self.qc_flags),
                },
            )
            self.activity_progress.emit(100, "Seismic report is ready")
            self._show_status(f"{format_name.upper()} report exported and registered: {output}")
        except Exception as exc:
            QMessageBox.critical(self, "Report Export", str(exc))
        finally:
            self.activity_finished.emit()

    def _capture_report_images(self, directory: Path) -> dict[str, Path]:
        images: dict[str, Path] = {}
        active_tab = self.tabs.currentIndex()
        try:
            self.tabs.setCurrentIndex(self.TAB_2D)
            QApplication.processEvents()
            section_path = directory / "section.png"
            self.view_2d.grab().save(str(section_path), "PNG")
            images["2D Seismic Section"] = section_path

            self.tabs.setCurrentIndex(self.TAB_QC)
            QApplication.processEvents()
            qc_path = directory / "qc.png"
            self.qc_panel.grab().save(str(qc_path), "PNG")
            images["QC Analysis"] = qc_path

            self.tabs.setCurrentIndex(self.TAB_3D)
            QApplication.processEvents()
            framebuffer = self.view_3d.framebuffer()
            if framebuffer is not None:
                volume_path = directory / "volume.png"
                framebuffer.save(str(volume_path), "PNG")
                images["3D Volume and Interpretation"] = volume_path
        finally:
            self.tabs.setCurrentIndex(active_tab)
            QApplication.processEvents()
        return images

    def _center_on_trace(self, trace_index: int) -> None:
        if self.data_source is None:
            return
        half = max(1, self.trace_count_spin.value() // 2)
        self.trace_start_spin.setValue(max(0, int(trace_index) - half)
        )
        self.tabs.setCurrentIndex(self.TAB_2D)
        self.tools_2d_tabs.setCurrentIndex(0)
        self.reload_section()

    def _on_cursor_changed(
        self,
        trace_index: int,
        sample_index: int,
        time_ms: float,
        amplitude: float,
    ) -> None:
        self.cursor_label.setText(
            f"Trace {trace_index + 1:,}   Sample {sample_index + 1:,}   "
            f"Time {time_ms:.2f} ms   Amplitude {amplitude:.5g}"
        )

    def _default_output_path(self, label: str, suffix: str) -> Path:
        source = self._current_path or (Path.home() / "seismic")
        return source.with_name(f"{source.stem}_{label}{suffix}")

    def _run_async(
        self,
        function: TaskFunction,
        on_result: Callable[[object], None],
        activity: str,
        detail: str,
    ) -> None:
        if self._closing:
            return
        worker = FunctionRunnable(function)
        self._active_workers.add(worker)
        worker.signals.result.connect(
            lambda result: self._deliver_worker_result(on_result, activity, result)
        )
        worker.signals.error.connect(
            lambda message: self._show_worker_error(activity, message)
        )
        worker.signals.progress.connect(self._update_worker_progress)
        worker.signals.finished.connect(lambda: self._worker_finished(worker))
        self._busy_count += 1
        self.open_button.setEnabled(False)
        self.tabs.setEnabled(False)
        self.loading_overlay.show_activity(activity, detail, 0)
        self.status_label.setText(activity)
        if self._busy_count == 1:
            self.activity_started.emit(activity, detail)
            QApplication.setOverrideCursor(Qt.WaitCursor)
        QTimer.singleShot(0, lambda: self._start_worker(worker))

    def _start_worker(self, worker: FunctionRunnable) -> None:
        if self._closing:
            self._worker_finished(worker)
            return
        self._thread_pool.start(worker)

    def _deliver_worker_result(
        self,
        on_result: Callable[[object], None],
        activity: str,
        result: object,
    ) -> None:
        if self._closing:
            source = result[0] if isinstance(result, tuple) and result else None
            close = getattr(source, "close", None)
            if callable(close):
                close()
            return
        try:
            on_result(result)
        except Exception:
            self._show_worker_error(activity, traceback.format_exc())

    def _update_worker_progress(self, value: int, detail: str) -> None:
        self.loading_overlay.update_activity(value, detail)
        self.activity_progress.emit(max(0, min(100, int(value))), detail)
        self.status_label.setText(detail)

    def _worker_finished(self, worker: FunctionRunnable) -> None:
        self._active_workers.discard(worker)
        self._busy_count = max(0, self._busy_count - 1)
        if self._busy_count == 0:
            self.loading_overlay.hide_activity()
            self.activity_finished.emit()
            self.tabs.setEnabled(True)
            self.open_button.setEnabled(True)
            if QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()
            pending = self._pending_open_path
            self._pending_open_path = None
            if pending is not None and not self._closing:
                QTimer.singleShot(0, lambda path=pending: self._start_open_path(path))

    def _show_worker_error(self, activity: str, traceback_text: str) -> None:
        message = traceback_text.strip().splitlines()[-1] if traceback_text.strip() else "Unknown error"
        QMessageBox.critical(self, activity, message)
        self._show_status(f"Failed: {message}")

    def _show_status(self, message: str) -> None:
        self.status_label.setText(message)
        self.status_message.emit(message)

    def _on_main_tab_changed(self, index: int) -> None:
        if index == self.TAB_3D and self.volume is not None:
            QTimer.singleShot(0, self._update_3d_mode)
        elif index == self.TAB_GEOSPATIAL:
            QTimer.singleShot(0, self._refresh_geospatial)

    def begin_horizon_pick(self) -> None:
        self._begin_pick("horizon")

    def begin_fault_pick(self) -> None:
        self._begin_pick("fault")

    def begin_measurement(self) -> None:
        self._begin_pick("measurement")

    def undo_pick(self) -> None:
        self.tabs.setCurrentIndex(self.TAB_2D)
        self.tools_2d_tabs.setCurrentIndex(2)
        self.view_2d.undo_last_pick()

    def stop_picking(self) -> None:
        self.tabs.setCurrentIndex(self.TAB_2D)
        self.tools_2d_tabs.setCurrentIndex(2)
        self.view_2d.stop_picking()

    def zoom_to_fit(self) -> None:
        self.tabs.setCurrentIndex(self.TAB_2D)
        self.view_2d.fit_view()

    def toggle_noise_overlay(self) -> None:
        self.tabs.setCurrentIndex(self.TAB_2D)
        self.tools_2d_tabs.setCurrentIndex(1)
        self.noise_overlay_check.setChecked(not self.noise_overlay_check.isChecked())

    def run_qc(self, _mode: str = "full") -> None:
        self.detect_bad_traces()

    def export_image(self) -> None:
        self.export_png()

    def close_file(self) -> None:
        if self.data_source is not None:
            self.data_source.close()
            self.data_source = None
        self.volume = None
        self.view_3d.clear()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "loading_overlay"):
            self.loading_overlay.setGeometry(self.rect())
            if self.loading_overlay.isVisible():
                self.loading_overlay.raise_()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._closing = True
        self.close_file()
        super().closeEvent(event)