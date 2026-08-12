from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

import numpy as np
from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QTextEdit,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from modules.magnetic.constants import (
    DESPIKED_TOTAL_FIELD,
    DIURNAL_CORRECTED_FIELD,
    LEVELED_FIELD,
    MICROLEVELED_FIELD,
    RAW_TOTAL_FIELD,
)
from modules.magnetic.enmag_qc import EnMagQcData, SpatialFilterDefinition, grid_surface, make_color_range, robust_range
from modules.magnetic.models import MagneticDataRole, MagneticDataset, MagneticSurveyType
from modules.magnetic.reader import MagneticReader
from modules.magnetic.readers.boundary_reader import MagneticBoundaryReader
from modules.magnetic.ui.enmag_qc_canvas import EnMagCanvasContainer, EnMagColorBar, EnMagPreviewCanvas
from modules.magnetic.ui.spatial_filter_dialog import SpatialFilterDialog


_ENMAG_STYLE = """
QWidget#enmagDataQcScreen {
    background:#F3F4F6;
    color:#1E242B;
    font-family:"Segoe UI", Arial, sans-serif;
    font-size:8pt;
}
QFrame#sidebarShell, QFrame#previewShell {
    background:#F8F9FB;
    border:1px solid #D3D7DD;
    border-radius:6px;
}
QLabel#panelTitle {
    color:#4A525B;
    font-size:9pt;
    font-weight:600;
}
QLabel#statusPrimary { font-weight:600; color:#1A5E21; }
QLabel#hoverInfo { color:#2A3138; min-height:20px; }
QLabel#mutedLabel { color:#66717C; }
QGroupBox {
    border:1px solid #D2D6DA;
    margin-top:8px;
    padding-top:8px;
    background:#FBFCFD;
    border-radius:4px;
}
QGroupBox::title {
    subcontrol-origin:margin;
    left:8px;
    padding:0 4px;
    color:#46515C;
}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QTextEdit {
    background:#FFFFFF;
    border:1px solid #B8C1CB;
    border-radius:4px;
    min-height:21px;
    padding:2px 6px;
    selection-background-color:#BFD8FF;
}
QTextEdit { padding:4px 6px; }
QLineEdit:read-only { background:#EEF1F4; color:#68737E; }
QScrollArea { border:none; background:transparent; }
QTabWidget::pane { border:1px solid #D3D7DD; border-radius:4px; background:#FFFFFF; }
QTabBar::tab { background:#EEF2F6; border:1px solid #C5CDD6; padding:4px 10px; margin-right:2px; border-top-left-radius:4px; border-top-right-radius:4px; }
QTabBar::tab:selected { background:#FFFFFF; color:#174A7C; font-weight:600; }
QScrollBar:vertical {
    background:#EEF1F4; width:12px; margin:0; border-radius:5px;
}
QScrollBar::handle:vertical {
    background:#BAC4CF; min-height:24px; border-radius:5px;
}
QPushButton {
    min-height:23px;
    padding:2px 8px;
    background:#EFF2F5;
    border:1px solid #B8C1CB;
    border-radius:4px;
    color:#1F2B36;
}
QPushButton:hover { background:#E2EAF5; }
QPushButton:pressed { background:#D5E1F2; }
QPushButton:checked { background:#D6E6F7; border-color:#6E9BC6; }
QPushButton#primaryAction { background:#D7E9FB; border-color:#7FAED9; font-weight:600; }
QPushButton#primaryAction:hover { background:#C8DFF7; }
QPushButton#successAction { background:#DBF4E2; border-color:#86C59A; font-weight:600; }
QPushButton#successAction:hover { background:#D0EDD9; }
QPushButton#accentAction { background:#E3F0FF; border-color:#8FB7E4; }
QPushButton#accentAction:hover { background:#D6E7FB; }
QPushButton#warningAction { background:#F5F0E6; border-color:#D5BF8D; }
QPushButton#warningAction:hover { background:#EDE4D2; }
QToolButton#sidebarToggle {
    min-width:24px; max-width:24px; min-height:24px; max-height:24px;
    padding:0; background:#FFFFFF; border:1px solid #B8C1CB; border-radius:4px;
    font-weight:700; color:#48525B;
}
QPushButton#enmagZoomButton {
    background:#30343A;
    color:#FFFFFF;
    border:0;
    font-size:16pt;
    font-weight:700;
    padding:0;
    border-radius:4px;
}
QPushButton:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QLineEdit:disabled, QSlider:disabled {
    color:#97A0AA;
    background:#F1F3F5;
    border-color:#D4D9DF;
}
"""


class EnMagDataQcScreen(QWidget):
    """Fast EnMag-style magnetic log QC screen integrated with TGPAssure.

    The widget intentionally keeps interpolation and filtering state separate
    from rendering state: opacity/pan/zoom never rebuild a grid, while Draw,
    spatial-filter changes and grid-affecting controls do.
    """

    dataset_changed = Signal(object)
    activity_started = Signal(str, str)
    activity_progress = Signal(int, str)
    activity_finished = Signal()

    def __init__(self, controller=None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.reader = MagneticReader()
        self.boundary_reader = MagneticBoundaryReader()
        self.rover: MagneticDataset | None = None
        self.base: MagneticDataset | None = None
        self.boundary: Path | None = None
        self.boundary_data = None
        self.data: EnMagQcData | None = None
        self._folder: Path | None = None
        self._folder_files: list[Path] = []
        self._spatial_filter: SpatialFilterDefinition | None = None
        self._filter_serial = 0
        self._last_grid = None
        self._last_color_range = None
        self._last_visible_mask: np.ndarray | None = None
        self._last_grid_type_label = "Magnetic Field"
        self._last_grid_unit = "nT"
        self._last_color_mode = "Robust Auto"
        self._manual_min_text = ""
        self._manual_max_text = ""
        self._grid_type_channels: dict[str, str] = {"Mag": RAW_TOTAL_FIELD}
        self._palette_name = "Spectral"

        self.setObjectName("enmagDataQcScreen")
        self.setProperty("module_id", "magnetic")
        self.setStyleSheet(_ENMAG_STYLE)
        self._build_ui()
        self._redraw_timer = QTimer(self)
        self._redraw_timer.setSingleShot(True)
        self._redraw_timer.setInterval(180)
        self._redraw_timer.timeout.connect(self.draw)
        self._wire_grid_affecting_controls()
        self._update_control_states()
        self._update_summary()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 5)
        root.setSpacing(5)

        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(QLabel("Log File"))
        self.log_file_combo = QComboBox()
        self.log_file_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.log_file_combo.setMinimumContentsLength(45)
        self.log_file_combo.currentIndexChanged.connect(self._on_log_file_selected)
        top.addWidget(self.log_file_combo, 1)
        self.select_folder_btn = QPushButton("Select Folder")
        self.select_folder_btn.setObjectName("accentAction")
        self.select_folder_btn.clicked.connect(self.select_folder)
        top.addWidget(self.select_folder_btn)
        root.addLayout(top)

        content = QHBoxLayout()
        content.setSpacing(10)
        root.addLayout(content, 1)

        self.sidebar_shell = QFrame()
        self.sidebar_shell.setObjectName("sidebarShell")
        self.sidebar_shell.setFixedWidth(330)
        sidebar_layout = QVBoxLayout(self.sidebar_shell)
        sidebar_layout.setContentsMargins(10, 10, 10, 10)
        sidebar_layout.setSpacing(8)
        sidebar_header = QHBoxLayout()
        sidebar_header.setContentsMargins(0, 0, 0, 0)
        self.sidebar_title = QLabel("Settings")
        self.sidebar_title.setObjectName("panelTitle")
        sidebar_header.addWidget(self.sidebar_title, 1)
        self.sidebar_toggle_btn = QToolButton()
        self.sidebar_toggle_btn.setObjectName("sidebarToggle")
        self.sidebar_toggle_btn.setText("◀")
        self.sidebar_toggle_btn.clicked.connect(self._toggle_sidebar)
        sidebar_header.addWidget(self.sidebar_toggle_btn)
        sidebar_layout.addLayout(sidebar_header)

        self.sidebar_tabs = QTabWidget()
        self.sidebar_tabs.setDocumentMode(False)
        self.sidebar_tabs.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        self.settings_scroll = QScrollArea()
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        settings_content = QWidget()
        left = QGridLayout(settings_content)
        left.setContentsMargins(6, 6, 6, 6)
        left.setHorizontalSpacing(8)
        left.setVerticalSpacing(6)
        left.setColumnStretch(1, 1)
        row = 0

        self.preview_mode = QComboBox(); self.preview_mode.addItems(["Grid", "Points"])
        row = self._add_setting(left, row, "Preview Mode", self.preview_mode)

        self.grid_cols = QSpinBox(); self.grid_cols.setRange(8, 1024); self.grid_cols.setValue(64)
        row = self._add_setting(left, row, "Grid Cols", self.grid_cols)
        self.grid_rows = QSpinBox(); self.grid_rows.setRange(8, 1024); self.grid_rows.setValue(64)
        row = self._add_setting(left, row, "Grid Rows", self.grid_rows)

        self.point_radius = QDoubleSpinBox(); self.point_radius.setRange(0.0, 100.0); self.point_radius.setDecimals(2); self.point_radius.setSingleStep(0.1); self.point_radius.setValue(2.2)
        row = self._add_setting(left, row, "Point Radius", self.point_radius)
        self.idw_power = QDoubleSpinBox(); self.idw_power.setRange(0.05, 10.0); self.idw_power.setDecimals(2); self.idw_power.setSingleStep(0.1); self.idw_power.setValue(0.7)
        row = self._add_setting(left, row, "IDW Power", self.idw_power)

        opacity_box = QWidget(); opacity_layout = QHBoxLayout(opacity_box); opacity_layout.setContentsMargins(0,0,0,0); opacity_layout.setSpacing(8)
        self.grid_opacity = QSlider(Qt.Orientation.Horizontal); self.grid_opacity.setRange(0, 100); self.grid_opacity.setValue(100)
        self.opacity_value = QLabel("100%"); self.opacity_value.setFixedWidth(42)
        self.opacity_value.setObjectName("mutedLabel")
        opacity_layout.addWidget(self.grid_opacity, 1); opacity_layout.addWidget(self.opacity_value)
        row = self._add_setting(left, row, "Grid Opacity %", opacity_box)

        self.color_scale = QComboBox(); self.color_scale.addItems(["Robust Auto", "Manual", "Auto"])
        row = self._add_setting(left, row, "Color Scale", self.color_scale)
        validator = QDoubleValidator(-1e12, 1e12, 8, self)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.color_min = QLineEdit(); self.color_min.setValidator(validator)
        row = self._add_setting(left, row, "Color Min", self.color_min)
        self.color_max = QLineEdit(); self.color_max.setValidator(QDoubleValidator(-1e12, 1e12, 8, self))
        row = self._add_setting(left, row, "Color Max", self.color_max)
        self.reset_color_btn = QPushButton("Reset")
        self.reset_color_btn.setObjectName("warningAction")
        left.addWidget(self.reset_color_btn, row, 1, alignment=Qt.AlignmentFlag.AlignRight); row += 1

        self.color_palette = QComboBox(); self.color_palette.addItems(["Spectral", "Jet", "Viridis", "Gray"])
        row = self._add_setting(left, row, "Color Palette", self.color_palette)

        self.grid_type = QComboBox(); self.grid_type.addItems(["Mag", "Heading", "Elevation"])
        row = self._add_setting(left, row, "Grid Type", self.grid_type)
        self.interpolation = QComboBox(); self.interpolation.addItems(["Fast Grid", "IDW", "Nearest"])
        row = self._add_setting(left, row, "Interpolation", self.interpolation)

        self.include_invalid = QCheckBox("Include Invalid Samples")
        left.addWidget(self.include_invalid, row, 0, 1, 2); row += 1
        self.heading_info_export = QCheckBox("Heading Info Export")
        left.addWidget(self.heading_info_export, row, 0, 1, 2); row += 1
        left.setRowStretch(row, 1)
        self.settings_scroll.setWidget(settings_content)
        self.sidebar_tabs.addTab(self.settings_scroll, "Settings")

        summary_page = QWidget()
        summary_layout = QVBoxLayout(summary_page)
        summary_layout.setContentsMargins(6, 6, 6, 6)
        summary_layout.setSpacing(5)
        summary_label = QLabel("File Summary")
        summary_label.setObjectName("panelTitle")
        summary_layout.addWidget(summary_label)
        self.summary = QTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setMinimumHeight(180)
        summary_layout.addWidget(self.summary, 1)
        self.sidebar_tabs.addTab(summary_page, "Summary")
        sidebar_layout.addWidget(self.sidebar_tabs, 1)
        content.addWidget(self.sidebar_shell)

        preview_shell = QFrame()
        preview_shell.setObjectName("previewShell")
        preview_layout = QVBoxLayout(preview_shell)
        preview_layout.setContentsMargins(10, 8, 10, 8)
        preview_layout.setSpacing(7)
        preview_title = QLabel("Preview")
        preview_title.setObjectName("panelTitle")
        preview_layout.addWidget(preview_title)

        toolbar = QHBoxLayout(); toolbar.setSpacing(8)
        instructions = QVBoxLayout(); instructions.setSpacing(4)
        instructions.addWidget(QLabel("North up | Drag to pan | Mouse wheel or buttons to zoom"))
        self.hover_info = QLabel("Move over the map to inspect grid and nearest point values.")
        self.hover_info.setObjectName("hoverInfo")
        instructions.addWidget(self.hover_info)
        toolbar.addLayout(instructions, 1)
        self.pan_btn = QPushButton("Pan"); self.pan_btn.setCheckable(True); self.pan_btn.setChecked(True)
        self.pan_btn.setObjectName("accentAction")
        self.filter_btn = QPushButton("Filter")
        self.filter_btn.setObjectName("accentAction")
        self.reset_filter_btn = QPushButton("Reset Filter")
        self.reset_filter_btn.setObjectName("warningAction")
        self.filter_combo = QComboBox(); self.filter_combo.addItem("None"); self.filter_combo.setMinimumWidth(140)
        toolbar.addWidget(self.pan_btn); toolbar.addWidget(self.filter_btn); toolbar.addWidget(self.reset_filter_btn); toolbar.addWidget(self.filter_combo)
        preview_layout.addLayout(toolbar)

        self.colorbar = EnMagColorBar(self)
        preview_layout.addWidget(self.colorbar)
        self.canvas = EnMagPreviewCanvas(self)
        self.canvas_container = EnMagCanvasContainer(self.canvas, self)
        preview_layout.addWidget(self.canvas_container, 1)
        content.addWidget(preview_shell, 1)

        bottom = QHBoxLayout(); bottom.setSpacing(8)
        status_box = QVBoxLayout(); status_box.setSpacing(1)
        self.status_primary = QLabel("Draw failed"); self.status_primary.setObjectName("statusPrimary")
        self.status_filter = QLabel("Filter: none")
        self.status_filter.setObjectName("mutedLabel")
        status_box.addWidget(self.status_primary); status_box.addWidget(self.status_filter)
        bottom.addLayout(status_box, 1)
        self.draw_btn = QPushButton("Draw"); self.draw_btn.setObjectName("primaryAction"); self.draw_btn.clicked.connect(self.draw)
        self.export_btn = QPushButton("Export"); self.export_btn.setObjectName("successAction"); self.export_btn.clicked.connect(self.export_csv)
        bottom.addWidget(self.draw_btn); bottom.addWidget(self.export_btn)
        root.addLayout(bottom)

        self.grid_opacity.valueChanged.connect(self._on_opacity_changed)
        self.color_scale.currentTextChanged.connect(self._on_color_mode_changed)
        self.reset_color_btn.clicked.connect(self.reset_color)
        self.color_palette.currentTextChanged.connect(self._on_palette_changed)
        self.interpolation.currentTextChanged.connect(self._update_control_states)
        self.preview_mode.currentTextChanged.connect(self._on_preview_mode_changed)
        self.include_invalid.toggled.connect(self._on_visibility_changed)
        self.pan_btn.toggled.connect(self.canvas.set_pan_enabled)
        self.filter_btn.clicked.connect(self.open_spatial_filter)
        self.reset_filter_btn.clicked.connect(self.reset_filter)
        self.filter_combo.currentTextChanged.connect(self._on_filter_combo_changed)
        self.canvas.hover_changed.connect(self.hover_info.setText)

    def _toggle_sidebar(self) -> None:
        visible = self.sidebar_tabs.isVisible()
        self.sidebar_tabs.setVisible(not visible)
        self.sidebar_shell.setFixedWidth(330 if not visible else 34)
        self.sidebar_title.setVisible(not visible)
        self.sidebar_toggle_btn.setText("◀" if not visible else "▶")

    @staticmethod
    def _add_setting(layout: QGridLayout, row: int, label: str, widget: QWidget) -> int:
        layout.addWidget(QLabel(label), row, 0)
        layout.addWidget(widget, row, 1)
        return row + 1

    def _wire_grid_affecting_controls(self) -> None:
        self.grid_cols.valueChanged.connect(self._schedule_grid_redraw)
        self.grid_rows.valueChanged.connect(self._schedule_grid_redraw)
        self.point_radius.valueChanged.connect(self._schedule_grid_redraw)
        self.idw_power.valueChanged.connect(self._schedule_grid_redraw)
        self.grid_type.currentTextChanged.connect(self._on_grid_type_changed)
        self.interpolation.currentTextChanged.connect(self._schedule_grid_redraw)

    def _schedule_grid_redraw(self, *_args) -> None:
        if self.data is not None and self.preview_mode.currentText() == "Grid":
            self._redraw_timer.start()

    def _update_control_states(self, *_args) -> None:
        grid_mode = self.preview_mode.currentText() == "Grid"
        for widget in (self.grid_cols, self.grid_rows, self.point_radius, self.grid_opacity, self.color_scale, self.color_min, self.color_max, self.reset_color_btn, self.color_palette, self.grid_type, self.interpolation):
            widget.setEnabled(grid_mode)
        self.idw_power.setEnabled(grid_mode and self.interpolation.currentText() == "IDW")
        if grid_mode:
            manual = self.color_scale.currentText() == "Manual"
            self.color_min.setReadOnly(not manual)
            self.color_max.setReadOnly(not manual)

    def _discover_log_files(self, folder: Path) -> tuple[list[Path], list[str]]:
        suffixes = {".txt", ".csv", ".dat", ".log", ".mag", ".xyz", ".asc"}
        valid: list[Path] = []
        ignored: list[str] = []
        for candidate in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
            if not candidate.is_file() or candidate.suffix.lower() not in suffixes:
                continue
            stem = candidate.stem.lower()
            if any(token in stem for token in ("boundary", "polygon", "outline", "extent", "footprint", "aoi")):
                ignored.append(candidate.name)
                continue
            try:
                inspection = self.reader.inspect(candidate)
                missing = tuple(inspection.get("required_missing") or ())
                if missing:
                    ignored.append(candidate.name)
                    continue
            except Exception:
                ignored.append(candidate.name)
                continue
            valid.append(candidate)
        return valid, ignored

    # ------------------------------------------------------------- ingestion
    def select_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Magnetic Log Folder", str(self._folder or Path.home()))
        if folder:
            self.open_folder(folder)

    def open_folder(self, folder: str | Path) -> None:
        path = Path(folder)
        try:
            files, ignored = self._discover_log_files(path)
        except OSError as exc:
            QMessageBox.warning(self, "Magnetic Folder", str(exc))
            return
        self._folder = path
        self._folder_files = files
        self.log_file_combo.blockSignals(True)
        self.log_file_combo.clear()
        for file in files:
            self.log_file_combo.addItem(file.name, str(file))
        self.log_file_combo.blockSignals(False)
        ignored_msg = f" Ignored {len(ignored)} non-magnetic/support files." if ignored else ""
        if not files:
            self._clear_dataset()
            self.status_primary.setStyleSheet("color:#9B1C1C; font-weight:600;")
            self.status_primary.setText("Draw failed")
            self.hover_info.setText("No discoverable magnetic log files were found in the selected folder." + ignored_msg)
            return
        self.log_file_combo.setToolTip(f"{len(files)} magnetic log(s) discovered in {path}{ignored_msg}")
        self.log_file_combo.setCurrentIndex(0)
        self._load_log_file(files[0])

    def _on_log_file_selected(self, index: int) -> None:
        if index < 0:
            return
        value = self.log_file_combo.itemData(index)
        if value:
            self._load_log_file(Path(str(value)))

    def open_rover(self) -> None:

        path, _ = QFileDialog.getOpenFileName(self, "Open Magnetic Log", str(self._folder or Path.home()), "Magnetic logs (*.txt *.csv *.dat *.log *.mag *.xyz *.asc);;All files (*.*)")
        if path:
            self.open_rover_path(path)

    def open_rover_path(self, path: str | Path, *, show_import_dialog: bool = False) -> None:
        source = Path(path)
        if source.is_dir():
            self.open_folder(source); return
        self._folder = source.parent
        self._folder_files = [source]
        self.log_file_combo.blockSignals(True)
        self.log_file_combo.clear(); self.log_file_combo.addItem(source.name, str(source)); self.log_file_combo.setCurrentIndex(0)
        self.log_file_combo.blockSignals(False)
        self._load_log_file(source)

    def _load_log_file(self, path: Path) -> None:
        self.activity_started.emit("Loading Magnetic Log", f"Reading {path.name}")
        try:
            dataset = self.reader.read_rover(path)
            self.rover = dataset
            self.data = EnMagQcData.from_dataset(dataset)
            self._grid_type_channels = {"Mag": self.data.channel_name}
            self._spatial_filter = None
            self._filter_serial = 0
            self._sync_filter_combo()
            self.canvas.set_data(self.data)
            self._update_color_fields_from_auto()
            self._update_summary()
            self.dataset_changed.emit(dataset)
            self.draw()
        except Exception as exc:
            self._clear_dataset()
            self.status_primary.setStyleSheet("color:#9B1C1C; font-weight:600;")
            self.status_primary.setText("Draw failed")
            self.hover_info.setText(f"Unable to parse {path.name}: {exc}")
            QMessageBox.critical(self, "Magnetic Import Error", str(exc))
        finally:
            self.activity_finished.emit()

    def _clear_dataset(self) -> None:
        self.rover = None; self.data = None; self._last_grid = None; self._last_color_range = None; self._last_visible_mask = None
        self._spatial_filter = None
        self.canvas.set_data(None); self.colorbar.set_state(None); self._sync_filter_combo(); self._update_summary()

    def open_base(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Magnetic Base Station", str(self._folder or Path.home()), "Magnetic logs (*.txt *.csv *.dat *.log *.mag *.xyz *.asc);;All files (*.*)")
        if not path:
            return
        try:
            self.base = self.reader.read_base(path)
            self.hover_info.setText(f"Base station loaded: {Path(path).name}")
        except Exception as exc:
            QMessageBox.critical(self, "Base Station Import Error", str(exc))

    def open_boundary(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Survey Boundary",
            str(self._folder or Path.home()),
            "Boundary (*.kml *.kmz *.geojson *.json *.csv *.txt *.xyz *.shp);;All files (*.*)",
        )
        if not path:
            return
        try:
            self.boundary = Path(path)
            self.boundary_data = self.boundary_reader.read(self.boundary)
            vertex_count = int(getattr(self.boundary_data, "vertices", np.empty((0, 2))).shape[0])
            self.hover_info.setText(f"Boundary selected: {self.boundary.name} | {vertex_count} vertices")
        except Exception as exc:
            self.boundary = None
            self.boundary_data = None
            QMessageBox.critical(self, "Boundary Import Error", str(exc))

    # ------------------------------------------------------------ data state
    def _values_for_current_grid_type(self) -> tuple[np.ndarray, str, str, bool]:
        if self.data is None:
            raise ValueError("No magnetic data loaded")
        text = self.grid_type.currentText()
        if text == "Heading":
            return self.data.heading_deg, "BNO Heading", "deg", True
        if text == "Elevation":
            return self.data.altitude_m, "Elevation", "m", False
        channel = self._grid_type_channels.get(text, self.data.channel_name)
        if self.rover is not None and channel in self.rover.channels:
            unit = self.rover.magnetic_units or "nT"
            label = "Magnetic Field" if text == "Mag" else text
            return np.asarray(self.rover.channels[channel], dtype=float), label, unit, False
        return self.data.magnetic_nt, "Magnetic Field", "nT", False

    def _spatial_mask(self) -> np.ndarray | None:
        if self.data is None or self._spatial_filter is None:
            return None
        return self._spatial_filter.mask(self.data.x, self.data.y)

    def _visible_mask(self, values: np.ndarray | None = None) -> np.ndarray:
        if self.data is None:
            return np.zeros(0, dtype=bool)
        if values is None:
            values, _, _, _ = self._values_for_current_grid_type()
        return self.data.visible_mask(values=values, include_invalid=self.include_invalid.isChecked(), spatial_mask=self._spatial_mask())

    def _base_visible_without_spatial(self) -> np.ndarray:
        if self.data is None:
            return np.zeros(0, dtype=bool)
        values, _, _, _ = self._values_for_current_grid_type()
        return self.data.visible_mask(values=values, include_invalid=self.include_invalid.isChecked(), spatial_mask=None)

    def _update_summary(self) -> None:
        if self.data is None:
            self.summary.setPlainText("Input:\nNone\nRecords: 0\nVisible samples: 0\nGPS records: 0")
            return
        try:
            visible = int(np.count_nonzero(self._visible_mask()))
        except Exception:
            visible = 0
        self.summary.setPlainText(
            f"Input:\n{self.data.source_path}\n"
            f"Records: {self.data.raw_records}\n"
            f"Visible samples: {visible}\n"
            f"GPS records: {self.data.gps_records}"
        )

    def _on_visibility_changed(self, *_args) -> None:
        self._update_color_fields_from_auto()
        self._update_summary()
        if self.data is not None:
            self.draw()

    def _on_grid_type_changed(self, *_args) -> None:
        self._update_color_fields_from_auto()
        self._update_summary()
        self._schedule_grid_redraw()

    # ------------------------------------------------------------- color UI
    @staticmethod
    def _parse_optional_float(text: str) -> float | None:
        try:
            value = float(str(text).strip())
            return value if np.isfinite(value) else None
        except Exception:
            return None

    def _format_color_value(self, value: float) -> str:
        return f"{float(value):.6f}".rstrip("0").rstrip(".")

    def _update_color_fields_from_auto(self) -> None:
        if self.data is None or self.color_scale.currentText() == "Manual":
            return
        try:
            values, _, _, _ = self._values_for_current_grid_type(); mask = self._visible_mask(values); finite = values[mask]
            if finite.size == 0:
                return
            if self.color_scale.currentText() == "Auto":
                lo, hi = float(np.nanmin(finite)), float(np.nanmax(finite))
            else:
                lo, hi = robust_range(finite)
            self.color_min.setText(self._format_color_value(lo)); self.color_max.setText(self._format_color_value(hi))
        except Exception:
            pass

    def _on_color_mode_changed(self, mode: str) -> None:
        if self._last_color_mode == "Manual":
            self._manual_min_text = self.color_min.text().strip()
            self._manual_max_text = self.color_max.text().strip()
        manual = mode == "Manual"
        self.color_min.setReadOnly(not manual); self.color_max.setReadOnly(not manual)
        if manual:
            # First entry is blank like the reference application.  If the user
            # later switches away and returns, their manual limits are restored.
            self.color_min.setText(self._manual_min_text)
            self.color_max.setText(self._manual_max_text)
        else:
            self._update_color_fields_from_auto()
        self._last_color_mode = mode
        self._update_control_states()

    def reset_color(self) -> None:
        if self.data is None:
            self.color_min.clear(); self.color_max.clear(); return
        try:
            values, _, _, _ = self._values_for_current_grid_type(); mask = self._visible_mask(values)
            lo, hi = robust_range(values[mask])
            lo_text = self._format_color_value(lo); hi_text = self._format_color_value(hi)
            self.color_min.setText(lo_text); self.color_max.setText(hi_text)
            if self.color_scale.currentText() == "Manual":
                self._manual_min_text = lo_text; self._manual_max_text = hi_text
        except Exception:
            self.color_min.clear(); self.color_max.clear()

    def _on_palette_changed(self, palette: str) -> None:
        self._palette_name = palette or "Spectral"
        if self.data is not None:
            self.draw()

    def _on_opacity_changed(self, value: int) -> None:
        self.opacity_value.setText(f"{value}%")
        self.canvas.set_opacity(value / 100.0)

    def _on_preview_mode_changed(self, mode: str) -> None:
        self._update_control_states()
        self.canvas.set_mode(mode)
        if self.data is not None:
            if mode == "Points":
                values, label, unit, _ = self._values_for_current_grid_type(); mask = self._visible_mask(values)
                self.canvas.set_visible_mask(mask)
                self.canvas.set_render(None, None, mode="Points", grid_label=label, grid_values=values)
                self.status_primary.setText(f"Draw complete: {int(np.count_nonzero(mask))} samples | Points | Raw Points")
                self._update_summary()
            else:
                self.draw()

    # -------------------------------------------------------------- drawing
    def draw(self) -> None:
        if self.data is None:
            self._set_draw_failed("No magnetic data is loaded")
            return
        try:
            values, grid_label, unit, circular = self._values_for_current_grid_type()
            mask = self._visible_mask(values)
            visible_count = int(np.count_nonzero(mask))
            if visible_count == 0:
                raise ValueError("Zero visible samples after validity/filter rules")

            manual_min = self._parse_optional_float(self.color_min.text()) if self.color_scale.currentText() == "Manual" else None
            manual_max = self._parse_optional_float(self.color_max.text()) if self.color_scale.currentText() == "Manual" else None
            color_range = make_color_range(values[mask], self.color_scale.currentText(), manual_min, manual_max, unit=unit)

            mode = self.preview_mode.currentText()
            grid_result = None
            if mode == "Grid":
                source_indices = np.flatnonzero(mask)
                grid_result = grid_surface(
                    self.data.x[mask], self.data.y[mask], values[mask], source_indices,
                    cols=self.grid_cols.value(), rows=self.grid_rows.value(), point_radius=self.point_radius.value(),
                    method=self.interpolation.currentText(), idw_power=self.idw_power.value(), circular=circular,
                )
                if not np.any(np.isfinite(grid_result.values)):
                    raise ValueError("Interpolation produced no finite grid cells")

            # Commit only after every stage succeeded.  A failed draw therefore
            # leaves the last good raster on screen exactly as the reference app.
            self._last_grid = grid_result
            self._last_color_range = color_range
            self._last_visible_mask = mask.copy()
            self._last_grid_type_label = grid_label
            self._last_grid_unit = unit
            self.canvas.set_visible_mask(mask)
            self.canvas.set_opacity(self.grid_opacity.value() / 100.0)
            self._palette_name = self.color_palette.currentText() if hasattr(self, "color_palette") else self._palette_name
            self.canvas.set_render(grid_result, color_range, palette_name=self._palette_name, mode=mode, grid_label=grid_label, grid_values=values)
            self.colorbar.set_state(color_range, self._palette_name)
            if self.color_scale.currentText() != "Manual":
                self.color_min.setText(self._format_color_value(color_range.scale_min)); self.color_max.setText(self._format_color_value(color_range.scale_max))
            interp_label = self.interpolation.currentText() if mode == "Grid" else "Raw Points"
            self.status_primary.setStyleSheet("color:#1A5E21; font-weight:600;")
            self.status_primary.setText(f"Draw complete: {visible_count} samples | {grid_label} | {interp_label}")
            self.status_primary.setToolTip("")
            self._update_filter_status()
            self._update_summary()
        except Exception as exc:
            self._set_draw_failed(str(exc))

    def _set_draw_failed(self, reason: str) -> None:
        self.status_primary.setStyleSheet("color:#9B1C1C; font-weight:600;")
        self.status_primary.setText("Draw failed")
        self.status_primary.setToolTip(reason)
        self.hover_info.setText(f"Draw failed: {reason}")
        self._update_filter_status(); self._update_summary()

    # -------------------------------------------------------------- filters
    def open_spatial_filter(self) -> None:
        if self.data is None:
            self._set_draw_failed("Load a magnetic log before creating a spatial filter")
            return
        dialog = SpatialFilterDialog(
            self.data.x,
            self.data.y,
            self._base_visible_without_spatial(),
            existing_filter=self._spatial_filter,
            filter_number=max(1, self._filter_serial + (0 if self._spatial_filter is not None else 1)),
            parent=self,
        )
        dialog.filter_applied.connect(self._apply_spatial_filter_definition)
        dialog.filters_reset.connect(self.reset_filter)
        dialog.exec()

    def _apply_spatial_filter_definition(self, definition: SpatialFilterDefinition, _name: str = "") -> None:
        if self._spatial_filter is None:
            self._filter_serial += 1
        definition.name = ("Keep" if definition.mode == "keep" else "Ignore") + f" selection {max(1, self._filter_serial)}"
        self._spatial_filter = definition
        self._sync_filter_combo()
        self._update_color_fields_from_auto(); self._update_summary(); self.draw()

    def reset_filter(self) -> None:
        self._spatial_filter = None
        self._sync_filter_combo()
        self._update_color_fields_from_auto(); self._update_summary()
        if self.data is not None:
            self.draw()
        else:
            self._update_filter_status()

    def _sync_filter_combo(self) -> None:
        self.filter_combo.blockSignals(True)
        self.filter_combo.clear(); self.filter_combo.addItem("None")
        if self._spatial_filter is not None:
            self.filter_combo.addItem(self._spatial_filter.name); self.filter_combo.setCurrentIndex(1)
        else:
            self.filter_combo.setCurrentIndex(0)
        self.filter_combo.blockSignals(False)
        self._update_filter_status()

    def _on_filter_combo_changed(self, text: str) -> None:
        if text == "None" and self._spatial_filter is not None:
            self.reset_filter()

    def _update_filter_status(self) -> None:
        name = self._spatial_filter.name if self._spatial_filter is not None else "none"
        self.status_filter.setText(f"Filter: {name}")

    # --------------------------------------------------------------- export
    def export_csv(self) -> None:
        if self.data is None:
            self._set_draw_failed("No magnetic data is available to export")
            return
        suggested = self.data.source_path.with_name(f"{self.data.source_path.stem}_enmag_qc_export.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Export Magnetic QC Data", str(suggested), "CSV (*.csv)")
        if not path:
            return
        try:
            if self.preview_mode.currentText() == "Grid":
                self._export_grid(Path(path))
            else:
                self._export_points(Path(path))
            self.hover_info.setText(f"Export complete: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Magnetic Export Error", str(exc))

    def _export_grid(self, path: Path) -> None:
        result = self._last_grid
        if result is None or self._last_visible_mask is None:
            raise ValueError("Draw a valid grid before exporting")
        values, grid_label, unit, _ = self._values_for_current_grid_type()
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            header = ["row", "col", "x_or_longitude", "y_or_latitude", "grid_value", "grid_type", "unit", "nearest_source_index", "point_magnetic_nt", "altitude_m"]
            if self.heading_info_export.isChecked():
                header.append("heading_deg")
            writer.writerow(header)
            rr, cc = np.nonzero(np.isfinite(result.values))
            for r, c in zip(rr.tolist(), cc.tolist()):
                source_idx = int(result.nearest_source_index[r, c])
                point_mag = self.data.magnetic_nt[source_idx] if 0 <= source_idx < self.data.sample_count else np.nan
                altitude = self.data.altitude_m[source_idx] if 0 <= source_idx < self.data.sample_count else np.nan
                row = [r, c, result.x_coordinates[c], result.y_coordinates[r], result.values[r, c], grid_label, unit, source_idx, point_mag, altitude]
                if self.heading_info_export.isChecked():
                    row.append(self.data.heading_deg[source_idx] if 0 <= source_idx < self.data.sample_count else np.nan)
                writer.writerow(row)

    def _export_points(self, path: Path) -> None:
        values, grid_label, unit, _ = self._values_for_current_grid_type(); mask = self._visible_mask(values)
        indices = np.flatnonzero(mask)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            header = ["timestamp", "x_or_longitude", "y_or_latitude", "altitude_m", "magnetic_nt", "display_value", "grid_type", "unit", "gps_fix_quality", "sensor_invalid", "gps_invalid", "line", "station"]
            if self.heading_info_export.isChecked(): header.append("heading_deg")
            writer.writerow(header)
            for i in indices.tolist():
                row = [str(self.data.timestamps[i]), self.data.x[i], self.data.y[i], self.data.altitude_m[i], self.data.magnetic_nt[i], values[i], grid_label, unit, self.data.gps_fix_quality[i], bool(self.data.sensor_bad[i]), bool(self.data.gps_bad[i]), self.data.line_id[i], self.data.station_id[i]]
                if self.heading_info_export.isChecked(): row.append(self.data.heading_deg[i])
                writer.writerow(row)

    # ------------------------------------------- existing magnetic ribbon API
    def process_despike(self) -> None:
        if not self._require_rover(): return
        channel = self._grid_type_channels.get(self.grid_type.currentText(), self.data.channel_name if self.data else RAW_TOTAL_FIELD)
        if channel not in self.rover.channels: channel = self.data.channel_name
        src = np.asarray(self.rover.channels[channel], dtype=float)
        finite = src[np.isfinite(src)]
        if finite.size == 0: return
        med = float(np.nanmedian(finite)); mad = float(np.nanmedian(np.abs(finite-med))) or float(np.nanstd(finite)) or 1.0
        out = src.copy(); spike = np.isfinite(out) & (np.abs(out-med) > 6.0*mad); out[spike] = med
        self.rover.add_derived_channel(DESPIKED_TOTAL_FIELD, out, parent_channel=channel, operation="EnMag QC despike", overwrite=True)
        self._register_derived("Despiked", DESPIKED_TOTAL_FIELD)

    def process_diurnal(self) -> None:
        if not self._require_rover(): return
        channel = self._grid_type_channels.get(self.grid_type.currentText(), self.data.channel_name if self.data else RAW_TOTAL_FIELD)
        if channel not in self.rover.channels: channel = self.data.channel_name
        src=np.asarray(self.rover.channels[channel],dtype=float)
        if self.base is not None:
            base_name=next(iter(self.base.channels)); base=np.asarray(self.base.channels[base_name],dtype=float)
            finite=base[np.isfinite(base)]
            if finite.size:
                centered=np.nan_to_num(base-np.nanmedian(finite),nan=0.0)
                correction=np.interp(np.linspace(0,1,src.size),np.linspace(0,1,base.size),centered)
                out=src-correction
            else: out=src.copy()
        else:
            idx=np.arange(src.size,dtype=float); finite=np.isfinite(src)
            if np.count_nonzero(finite)>=3:
                coeff=np.polyfit(idx[finite],src[finite],1); trend=np.polyval(coeff,idx); out=src-(trend-np.nanmedian(trend))
            else: out=src.copy()
        self.rover.add_derived_channel(DIURNAL_CORRECTED_FIELD,out,parent_channel=channel,operation="EnMag QC diurnal correction",overwrite=True)
        self._register_derived("Diurnal Corrected",DIURNAL_CORRECTED_FIELD)

    def process_leveling(self) -> None:
        if not self._require_rover(): return
        channel=self._grid_type_channels.get(self.grid_type.currentText(),self.data.channel_name if self.data else RAW_TOTAL_FIELD)
        if channel not in self.rover.channels: channel=self.data.channel_name
        src=np.asarray(self.rover.channels[channel],dtype=float); out=src.copy(); line=self.rover.line_id.astype(str)
        global_med=float(np.nanmedian(src))
        for ln in np.unique(line):
            m=line==ln
            if np.any(m) and np.any(np.isfinite(src[m])): out[m]=src[m]-(np.nanmedian(src[m])-global_med)
        self.rover.add_derived_channel(LEVELED_FIELD,out,parent_channel=channel,operation="EnMag QC line median leveling",overwrite=True)
        self._register_derived("Leveled",LEVELED_FIELD)

    def process_microlevel(self) -> None:
        if not self._require_rover(): return
        channel=self._grid_type_channels.get(self.grid_type.currentText(),self.data.channel_name if self.data else RAW_TOTAL_FIELD)
        if channel not in self.rover.channels: channel=self.data.channel_name
        src=np.asarray(self.rover.channels[channel],dtype=float); out=src.copy(); line=self.rover.line_id.astype(str)
        for ln in np.unique(line):
            idx=np.flatnonzero(line==ln)
            if idx.size<9: continue
            row=src[idx]; fill=float(np.nanmedian(row)) if np.any(np.isfinite(row)) else 0.0
            kernel=max(5,min(51,(idx.size//9)*2+1)); smooth=np.convolve(np.nan_to_num(row,nan=fill),np.ones(kernel)/kernel,mode="same")
            out[idx]=row-np.clip(smooth-np.nanmedian(smooth),-10.0,10.0)
        self.rover.add_derived_channel(MICROLEVELED_FIELD,out,parent_channel=channel,operation="EnMag QC gentle microlevel",overwrite=True)
        self._register_derived("Microleveled",MICROLEVELED_FIELD)

    def _register_derived(self, label: str, channel: str) -> None:
        self.data=EnMagQcData.from_dataset(self.rover,channel_name=self.data.channel_name if self.data else None)
        self._grid_type_channels[label]=channel
        if self.grid_type.findText(label)<0: self.grid_type.addItem(label)
        self.grid_type.setCurrentText(label)
        self._update_summary(); self.draw(); self.dataset_changed.emit(self.rover)

    def generate_grid(self) -> None: self.draw()
    def show_map(self) -> None: self.draw()
    def show_native_view(self, mode: str = "2d") -> None: self.draw()
    def show_geospatial_view(self, mode: str = "2d") -> None: self.draw()

    def show_profile(self) -> None:
        if not self._require_rover(): return
        values, label, unit, _ = self._values_for_current_grid_type(); lines=self.rover.line_id.astype(str); text=[]
        for ln in np.unique(lines):
            vals=values[lines==ln]; vals=vals[np.isfinite(vals)]
            if vals.size: text.append(f"Line {ln}: n={vals.size}, min={np.nanmin(vals):.3f}, max={np.nanmax(vals):.3f}, mean={np.nanmean(vals):.3f} {unit}")
        QMessageBox.information(self,f"{label} Profile Summary","\n".join(text[:100]) or "No profile values available.")

    def run_full_qc(self) -> None:
        if not self._require_rover(): return
        self.process_despike(); self.process_diurnal(); self.process_leveling(); self.process_microlevel()
        self.hover_info.setText("Full magnetic QC chain completed; derived channels were preserved separately from raw data.")

    def run_raw_qc(self) -> None:
        if self._require_rover(): self.draw()
    def run_processed_qc(self) -> None: self.run_full_qc()
    def cancel_qc(self) -> None:
        if self.controller is not None and hasattr(self.controller,"cancel") and self.controller.cancel():
            self.hover_info.setText("Magnetic QC cancellation requested.")
        else:
            self.hover_info.setText("No active magnetic background QC job to cancel.")

    def generate_report(self, fmt: str = "pdf") -> None:
        if self.data is None: return
        suffix = ".txt" if fmt.lower()=="pdf" else ".csv"
        path,_=QFileDialog.getSaveFileName(self,"Export Magnetic QC Summary",str(self.data.source_path.with_name(self.data.source_path.stem+"_qc_summary"+suffix)),"Text (*.txt);;CSV (*.csv)")
        if path: Path(path).write_text(self.summary.toPlainText()+"\n"+self.status_primary.text()+"\n"+self.status_filter.text(),encoding="utf-8")

    def _require_rover(self) -> bool:
        if self.rover is None or self.data is None:
            QMessageBox.information(self,"Magnetic QC","Load a magnetic log file first."); return False
        return True
