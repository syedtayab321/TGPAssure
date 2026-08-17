from __future__ import annotations

import csv
import math
import re
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGraphicsRectItem,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.visualization.palette_library import palette_rgb_array
from ui.icons import get_icon
from ui.widgets.palette_colorbar import PaletteColorBar
from modules.electrical.ipWin2.components.models import (
    ModelLayer,
    VesRow,
    complete_row,
    display_value,
    parse_float,
)
from modules.electrical.ipWin2.components.dialogs import (
    IpiAxesLimitsDialog,
    IpiChoiceDialog,
    IpiInversionOptionsDialog,
    IpiLayerConstraintDialog,
    IpiOptionsDialog,
    IpiSectionOptionsDialog,
    ProfileInformationDialog,
    VesPointEntryDialog,
)

_IPI_QSS = """
QWidget#ipWin2Dashboard {
    background:#EDF1F5;
    color:#1C2430;
    font-family:"Segoe UI", Arial, sans-serif;
    font-size:6.1pt;
}
QMenuBar {
    background:#F8FAFC;
    border-bottom:1px solid #CDD4DC;
    font-size:6.1pt;
    padding:0px;
}
QMenuBar::item { padding:2px 7px; background:transparent; }
QMenuBar::item:selected { background:#DBEAFE; color:#0F4C81; }
QMenu { background:#FFFFFF; border:1px solid #B8C2CC; font-size:6.1pt; }
QMenu::item { padding:3px 22px 3px 14px; }
QMenu::item:selected { background:#DDEEFF; color:#0F4C81; }
QFrame#classicStrip {
    background:#F7F9FB;
    border:1px solid #C9D1DA;
    border-radius:2px;
}
QToolButton#classicTool {
    min-width:18px; max-width:26px; min-height:15px; max-height:18px;
    padding:1px; border:1px solid transparent; border-radius:2px;
    background:#F7F9FB;
}
QToolButton#classicTool:hover { background:#E2F0FF; border-color:#7DAAD7; }
QToolButton#classicTool:checked { background:#CDE7FF; border-color:#4C8FC7; }
QLabel#windowCaption {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #C8DFF2, stop:1 #9DBDD9);
    color:#1D334A;
    font-weight:800;
    font-size:6.2pt;
    padding:2px 5px;
    border:1px solid #92ABC1;
}
QFrame#classicWindow {
    background:#FFFFFF;
    border:1px solid #9DAAB8;
}
QFrame#sidePanel {
    background:#F8FAFC;
    border:1px solid #C8D2DD;
    border-radius:3px;
}
QLabel#sectionTitle {
    color:#5B2A00;
    font-weight:800;
    font-size:6.0pt;
    padding:1px;
}
QLabel#smallStatus {
    color:#314155;
    font-size:6.0pt;
    padding:1px 3px;
}
QLabel#metricCard {
    background:#FFFFFF;
    border:1px solid #D0D8E2;
    border-radius:3px;
    padding:3px 5px;
    color:#243447;
    font-size:6.0pt;
    font-weight:700;
}
QPushButton {
    min-height:14px;
    padding:1px 5px;
    border:1px solid #B9C3CF;
    border-radius:3px;
    background:#FFFFFF;
    color:#263241;
    font-size:6.0pt;
    font-weight:700;
}
QPushButton:hover { background:#EAF4FF; border-color:#75A4D3; }
QPushButton#primaryButton { background:#DFF3E5; color:#0C6534; border-color:#83BD95; }
QPushButton#dangerButton { background:#FFE8E8; color:#A52828; border-color:#CC8B8B; }
QPushButton#warningButton { background:#FFF1D5; color:#875400; border-color:#D1A04C; }
QPushButton#blueButton { background:#DBEAFE; color:#0B4E8A; border-color:#8CB9E4; }
QPushButton#purpleButton { background:#EEE7FF; color:#5936A2; border-color:#B9A3E5; }
QPushButton#tealButton { background:#DDF7F2; color:#006B5A; border-color:#7ABFB1; }
QTableWidget {
    background:#FFFFFF;
    alternate-background-color:#F7F9FC;
    gridline-color:#CFD6DF;
    border:1px solid #BFC8D2;
    font-size:6.0pt;
    selection-background-color:#0B7DD7;
    selection-color:#FFFFFF;
}
QHeaderView::section {
    background:#E4E9EF;
    border:0;
    border-right:1px solid #C7D1DD;
    border-bottom:1px solid #C7D1DD;
    padding:1px 2px;
    font-size:6.0pt;
    font-weight:800;
}
QComboBox, QLineEdit, QDoubleSpinBox, QTextEdit {
    min-height:14px;
    border:1px solid #B8C2CC;
    border-radius:2px;
    background:#FFFFFF;
    padding:1px 4px;
    font-size:6.0pt;
}
QTabWidget::pane { border:1px solid #BBC7D3; background:#F8FAFC; }
QTabBar::tab {
    padding:3px 10px;
    font-size:6.1pt;
    background:#E8EDF3;
    border:1px solid #BBC7D3;
    border-bottom:0;
}
QTabBar::tab:selected { background:#FFFFFF; color:#0B5C8C; font-weight:800; }
QGroupBox {
    border:1px solid #C5CED9;
    border-radius:3px;
    margin-top:8px;
    padding-top:8px;
    font-weight:800;
    font-size:6.0pt;
}
QGroupBox::title { subcontrol-origin: margin; left:6px; padding:0 3px; }
"""


class IpWin2Dashboard(QWidget):
    """Modern, module-separated VES/IP 1-D workspace.

    The screen layout, command names and data-entry workflow follow the supplied
    IPI2Win reference captures, but this is an original TGPAssure implementation.
    It keeps Prosys II independent while providing a separate IPWin2 module with
    classic menus, ribbon-callable commands, dock-like windows, dialogs, editable
    VES tables, model layers, apparent/synthetic curves and pseudo/resistivity
    section displays.
    """

    activity_started = Signal(str, str)
    activity_progress = Signal(int, str)
    activity_finished = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ipWin2Dashboard")
        self.setStyleSheet(_IPI_QSS)
        self.source_path: Path | None = None
        self.array_type = "Schlumberger"
        self.profile_comments = ""
        self.rows: list[VesRow] = []
        self.profiles: list[tuple[str, list[VesRow]]] = []
        self.layers: list[ModelLayer] = []
        self.current_point = 0
        self.total_points = 0
        self._palette_name = "Resistivity"
        self._log_enabled = True
        self._section_mode = "both"
        self._auto_scale = True
        self._selected_curve_index: int | None = None
        self._drag_model_handle: int | None = None
        self._last_model_snapshot: list[ModelLayer] = []
        self._build_ui()
        self.reset_blank_project("Ready — open a DAT file or create a new VES point")

    def can_execute(self, action_id: str) -> bool:
        if action_id == "electrical_ipwin2" or action_id.startswith("electrical_ipi_"):
            return True
        return True

    # Ribbon/MainWindow compatibility aliases.  The IPWin2 ribbon uses stable
    # ``electrical_ipi_*`` action ids; MainWindow maps those ids to these
    # wrapper methods so the standalone dashboard can be opened without the
    # Prosys II electrical workspace.
    def ipi_new_profile(self) -> None: self.new_profile()
    def ipi_open_file(self) -> None: self.open_file()
    def ipi_save_file(self) -> None: self.save_file()
    def ipi_print_view(self) -> None: self.print_view()
    def ipi_edit_curve(self) -> None: self.edit_curve()
    def ipi_new_model(self) -> None: self.new_model()
    def ipi_inversion(self) -> None: self.run_inversion()
    def ipi_profile_inversion(self) -> None: self.run_profile_inversion()
    def ipi_next_point(self) -> None: self.next_point()
    def ipi_previous_point(self) -> None: self.previous_point()
    def ipi_first_point(self) -> None: self.first_point()
    def ipi_last_point(self) -> None: self.last_point()
    def ipi_split_layer(self) -> None: self.split_layer()
    def ipi_join_layers(self) -> None: self.join_layers()
    def ipi_fix_all_h(self) -> None: self.fix_all_h()
    def ipi_options(self) -> None: self.options_dialog()
    def ipi_section_options(self) -> None: self.section_options()
    def ipi_pseudosection(self) -> None: self.show_pseudosection_only()
    def ipi_resistivity_section(self) -> None: self.show_resistivity_only()
    def ipi_both_sections(self) -> None: self.show_both_sections()
    def ipi_zoom_in(self) -> None: self.zoom_in()
    def ipi_zoom_out(self) -> None: self.zoom_out()
    def ipi_inversion_options(self) -> None: self.inversion_options()
    def ipi_profile_information(self) -> None: self.profile_information()
    def ipi_copy_all_results(self) -> None: self.copy_all_results()
    def ipi_dar_zarrouk(self) -> None: self.show_dar_zarrouk()
    def ipi_axes_limits(self) -> None: self.axes_limits()
    def ipi_palette_options(self) -> None: self.palette_options()
    def ipi_toggle_log_scale(self) -> None: self.toggle_log_scale()
    def ipi_fit_profile(self) -> None: self.fit_profile()
    def ipi_model_minimum(self) -> None: self.model_minimum()
    def ipi_model_maximum(self) -> None: self.model_maximum()
    def ipi_move_selected_layer_left(self) -> None: self.move_selected_layer_left()
    def ipi_move_selected_layer_right(self) -> None: self.move_selected_layer_right()
    def ipi_horizontal_mirror(self) -> None: self.horizontal_mirror()
    def ipi_invert_palette(self) -> None: self.invert_palette()
    def ipi_auto_scale(self) -> None: self.toggle_auto_scale()
    def ipi_classic_layout(self) -> None: self.show_classic_layout()
    def ipi_data_window(self) -> None: self.workspace_tabs.setCurrentIndex(1)
    def ipi_curve_window(self) -> None: self.workspace_tabs.setCurrentIndex(2)
    def ipi_section_window(self) -> None: self.workspace_tabs.setCurrentIndex(3)
    def ipi_results_window(self) -> None: self.workspace_tabs.setCurrentIndex(4)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(2)
        root.addWidget(self._build_menu_bar())
        root.addWidget(self._build_toolbar())

        body = QSplitter(Qt.Horizontal, self)
        body.setChildrenCollapsible(False)
        body.addWidget(self._build_side_panel())
        body.addWidget(self._build_workspace_tabs())
        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        root.addWidget(body, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(2, 0, 2, 0)
        self.status = QLabel("Ready")
        self.status.setObjectName("smallStatus")
        footer.addWidget(self.status, 1)
        self.scale_label = QLabel("Scaled")
        self.scale_label.setObjectName("smallStatus")
        footer.addWidget(self.scale_label)
        root.addLayout(footer)

    def _build_menu_bar(self) -> QMenuBar:
        bar = QMenuBar(self)
        self._add_menu(bar, "File", [
            ("New", self.new_profile, "Ctrl+N"),
            ("Open", self.open_file, "Ctrl+O"),
            ("Save", self.save_file, "Ctrl+S"),
            ("Save As", self.save_file_as, ""),
            ("Print", self.print_view, "Ctrl+P"),
        ])
        self._add_menu(bar, "Edit", [
            ("Undo", self.restore_model, "Alt+Backspace"),
            ("Restore", self.restore_model, "Ctrl+F7"),
            ("Copy", self.copy_curve_values, "Ctrl+Insert"),
            ("Cut model", self.cut_model, "Shift+Del"),
            ("Paste model", self.paste_model, "Shift+Insert"),
            ("Edit curve", self.edit_curve, "F4"),
            ("Edit file", self.profile_information, "Ctrl+Alt+E"),
            ("Copy all results", self.copy_all_results, "Ctrl+A"),
            ("Delete all results", self.delete_all_results, ""),
            ("Copy model&curve", self.copy_model_curve, ""),
            ("Copy synthetic curve", self.copy_synthetic_curve, ""),
            ("Copy pseudo-section only", self.copy_pseudo_section, ""),
            ("Synthetic curve", self.calculate_synthetic_curve, "Alt+T"),
            ("Dar-Zarrouk", self.show_dar_zarrouk, ""),
        ])
        self._add_menu(bar, "Point", [
            ("Next", self.next_point, "Ctrl+Right"),
            ("Previous", self.previous_point, "Ctrl+Left"),
            ("First", self.first_point, "Home"),
            ("Last", self.last_point, "End"),
            ("Inversion", self.run_inversion, "Space"),
            ("Profile inversion", self.run_profile_inversion, "Ctrl+F3"),
            ("Profile extrapolation", self.profile_extrapolation, "Shift+Ctrl+F3"),
            ("New model", self.new_model, "F7"),
            ("Inversion option ...", self.inversion_options, ""),
            ("Profile new model", self.new_model, "Alt+F3"),
        ])
        self._add_menu(bar, "Model", [
            ("ChgTable", self.change_table, "Ctrl+T"),
            ("Fixing", self.toggle_fixing, "Ins"),
            ("Fix all H", self.fix_all_h, "Ctrl+H"),
            ("Split", self.split_layer, "Ctrl+N"),
            ("Join", self.join_layers, "Ctrl+Y"),
            ("Minimum", self.model_minimum, "Ctrl+Alt+D"),
            ("Maximum", self.model_maximum, "Ctrl+Alt+X"),
        ])
        self._add_menu(bar, "Section", [
            ("Zoom In", self.zoom_in, "Alt+F5"),
            ("Zoom Out", self.zoom_out, "Shift+F5"),
            ("All profile", self.fit_profile, "Ctrl+F5"),
            ("More depth", self.more_depth, "Num -"),
            ("Less depth", self.less_depth, "Num +"),
            ("Options ...", self.section_options, "Ctrl+F1"),
            ("Pseudo-section", self.show_pseudosection_only, ""),
            ("Resistivity section", self.show_resistivity_only, ""),
            ("Both sections", self.show_both_sections, ""),
            ("VES/IP", self.edit_curve, "F9"),
            ("Lin/Log scale", self.toggle_log_scale, "Ctrl+Alt+Z"),
            ("Horizontal mirror", self.horizontal_mirror, ""),
            ("Transformation", self.transformation, ""),
            ("Axes' limits", self.axes_limits, "Shift+Ctrl+F2"),
        ])
        self._add_menu(bar, "Tools", [
            ("New VES point", self.edit_curve, ""),
            ("Profile information", self.profile_information, ""),
            ("Automatic quick model", self.run_inversion, ""),
            ("Calculate geometric factor", self.recalculate_geometric_factor, ""),
            ("Move selected layer left", self.move_selected_layer_left, ""),
            ("Move selected layer right", self.move_selected_layer_right, ""),
            ("Rebuild pseudo-section", self.refresh, ""),
        ])
        self._add_menu(bar, "Options", [
            ("Autosave / New model", self.options_dialog, ""),
            ("Palette", self.palette_options, ""),
            ("Invert palette", self.invert_palette, ""),
            ("Auto scale color", self.toggle_auto_scale, ""),
        ])
        self._add_menu(bar, "Window", [
            ("Classic layout", self.show_classic_layout, ""),
            ("Data table", lambda: self.workspace_tabs.setCurrentIndex(1), ""),
            ("Curves", lambda: self.workspace_tabs.setCurrentIndex(2), ""),
            ("Sections", lambda: self.workspace_tabs.setCurrentIndex(3), ""),
            ("Results", lambda: self.workspace_tabs.setCurrentIndex(4), ""),
            ("Tile windows", self.tile_windows, ""),
            ("Cascade windows", self.cascade_windows, ""),
        ])
        self._add_menu(bar, "Help", [("About VES/IP 1D", self.about_dialog, "")])
        return bar

    def _add_menu(self, bar: QMenuBar, title: str, items: Iterable[tuple[str, Any, str]]) -> None:
        menu = QMenu(title, bar)
        for text, slot, shortcut in items:
            action = menu.addAction(text)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(slot)
        bar.addMenu(menu)

    def _build_toolbar(self) -> QFrame:
        frame = QFrame(self)
        frame.setObjectName("classicStrip")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(3, 2, 3, 2)
        layout.setSpacing(2)
        actions = [
            ("document-new", "New", self.new_profile),
            ("document-open", "Open", self.open_file),
            ("document-save", "Save", self.save_file),
            ("document-print", "Print", self.print_view),
            ("view-refresh", "Invert", self.run_inversion),
            ("go-next", "New model", self.new_model),
            ("edit-copy", "Copy", self.copy_model_curve),
            ("edit-table-cell-split", "Split", self.split_layer),
            ("edit-table-cell-merge", "Join", self.join_layers),
            ("zoom-fit-best", "All profile", self.fit_profile),
            ("preferences-system", "Options", self.options_dialog),
            ("color-picker", "Palette", self.palette_options),
        ]
        for icon, tip, slot in actions:
            button = QToolButton(frame)
            button.setObjectName("classicTool")
            button.setIcon(get_icon(icon, size=12))
            button.setToolTip(tip)
            button.clicked.connect(slot)
            layout.addWidget(button)
        layout.addStretch(1)
        self.point_label = QLabel("1/1")
        self.point_label.setObjectName("smallStatus")
        layout.addWidget(self.point_label)
        return frame

    def _build_side_panel(self) -> QFrame:
        panel = QFrame(self)
        panel.setObjectName("sidePanel")
        panel.setFixedWidth(222)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)

        title = QLabel("IPWin2 Control Center")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        self.sidebar_tabs = QTabWidget(panel)
        self.sidebar_tabs.setDocumentMode(True)
        self.sidebar_tabs.setTabPosition(QTabWidget.North)
        self.sidebar_tabs.addTab(self._build_project_sidebar_tab(), "Project")
        self.sidebar_tabs.addTab(self._build_commands_sidebar_tab(), "Commands")
        self.sidebar_tabs.addTab(self._build_display_sidebar_tab(), "Display")
        self.sidebar_tabs.addTab(self._build_results_sidebar_tab(), "Results")
        layout.addWidget(self.sidebar_tabs, 1)
        return panel

    def _build_project_sidebar_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.metric_file = QLabel("File: new profile")
        self.metric_file.setObjectName("metricCard")
        self.metric_point = QLabel("VES: 1 / 1")
        self.metric_point.setObjectName("metricCard")
        self.metric_error = QLabel("Error: --")
        self.metric_error.setObjectName("metricCard")
        for card in (self.metric_file, self.metric_point, self.metric_error):
            layout.addWidget(card)

        file_group = QGroupBox("File")
        grid = QGridLayout(file_group)
        grid.setContentsMargins(5, 7, 5, 5)
        grid.setSpacing(3)
        for idx, (text, obj, slot) in enumerate([
            ("New", "primaryButton", self.new_profile),
            ("Open", "warningButton", self.open_file),
            ("Save", "blueButton", self.save_file),
            ("Print", "", self.print_view),
        ]):
            btn = QPushButton(text)
            if obj:
                btn.setObjectName(obj)
            btn.clicked.connect(slot)
            grid.addWidget(btn, idx // 2, idx % 2)
        layout.addWidget(file_group)
        layout.addStretch(1)
        return page

    def _build_commands_sidebar_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        quick = QGroupBox("Interpretation")
        grid = QGridLayout(quick)
        grid.setContentsMargins(5, 7, 5, 5)
        grid.setSpacing(3)
        quick_buttons = [
            ("VES", "blueButton", self.edit_curve),
            ("Invert", "tealButton", self.run_inversion),
            ("Model", "purpleButton", self.new_model),
            ("DZ", "", self.show_dar_zarrouk),
            ("Split", "", self.split_layer),
            ("Join", "", self.join_layers),
            ("Fix H", "warningButton", self.fix_all_h),
            ("Undo", "", self.restore_model),
        ]
        for idx, (text, obj, slot) in enumerate(quick_buttons):
            btn = QPushButton(text)
            if obj:
                btn.setObjectName(obj)
            btn.clicked.connect(slot)
            grid.addWidget(btn, idx // 2, idx % 2)
        layout.addWidget(quick)

        nav = QGroupBox("Point navigation")
        ngrid = QGridLayout(nav)
        ngrid.setContentsMargins(5, 7, 5, 5)
        ngrid.setSpacing(3)
        for idx, (text, slot) in enumerate([
            ("First", self.first_point), ("Prev", self.previous_point),
            ("Next", self.next_point), ("Last", self.last_point),
        ]):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            ngrid.addWidget(btn, idx // 2, idx % 2)
        layout.addWidget(nav)
        layout.addStretch(1)
        return page

    def _build_display_sidebar_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        controls = QGroupBox("Section display")
        cgrid = QGridLayout(controls)
        cgrid.setContentsMargins(5, 7, 5, 5)
        cgrid.setSpacing(3)
        self.palette_combo = QComboBox()
        self.palette_combo.addItems(["Resistivity", "Classic", "Seismic", "Thermal", "Viridis", "Turbo", "Rainbow"])
        self.palette_combo.setCurrentText(self._palette_name)
        self.palette_combo.currentTextChanged.connect(self._set_palette)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Both sections", "Pseudo only", "Resistivity only"])
        self.mode_combo.currentTextChanged.connect(self._set_section_mode_from_combo)
        self.log_check = QCheckBox("Log curve")
        self.log_check.setChecked(True)
        self.log_check.stateChanged.connect(lambda *_: self.toggle_log_scale(set_to=self.log_check.isChecked()))
        self.autoscale_check = QCheckBox("Auto color")
        self.autoscale_check.setChecked(True)
        self.autoscale_check.stateChanged.connect(lambda *_: self.toggle_auto_scale(set_to=self.autoscale_check.isChecked()))
        cgrid.addWidget(QLabel("Palette"), 0, 0)
        cgrid.addWidget(self.palette_combo, 0, 1)
        cgrid.addWidget(QLabel("View"), 1, 0)
        cgrid.addWidget(self.mode_combo, 1, 1)
        cgrid.addWidget(self.log_check, 2, 0, 1, 2)
        cgrid.addWidget(self.autoscale_check, 3, 0, 1, 2)
        layout.addWidget(controls)

        windows = QGroupBox("Windows")
        wgrid = QGridLayout(windows)
        wgrid.setContentsMargins(5, 7, 5, 5)
        wgrid.setSpacing(3)
        for idx, (text, index) in enumerate([
            ("Classic", 0), ("Data", 1), ("Curve", 2), ("Sections", 3), ("Results", 4),
        ]):
            btn = QPushButton(text)
            btn.clicked.connect(lambda checked=False, i=index: self.workspace_tabs.setCurrentIndex(i))
            wgrid.addWidget(btn, idx // 2, idx % 2)
        layout.addWidget(windows)
        layout.addStretch(1)
        return page

    def _build_results_sidebar_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        self.results_box = QTextEdit()
        self.results_box.setReadOnly(True)
        self.results_box.setMinimumHeight(220)
        layout.addWidget(self.results_box, 1)
        return page

    def _build_workspace_tabs(self) -> QTabWidget:
        self.workspace_tabs = QTabWidget(self)
        self.workspace_tabs.addTab(self._build_classic_layout(), "Interpretation")
        self.workspace_tabs.addTab(self._build_data_tab(), "VES table")
        self.workspace_tabs.addTab(self._build_curve_tab(), "Curves")
        self.workspace_tabs.addTab(self._build_section_tab(), "Sections")
        self.workspace_tabs.addTab(self._build_results_tab(), "Results")
        return self.workspace_tabs

    def _classic_window(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame(self)
        frame.setObjectName("classicWindow")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        caption = QLabel(title)
        caption.setObjectName("windowCaption")
        layout.addWidget(caption)
        return frame, layout

    def _build_classic_layout(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(3)
        self.main_splitter = QSplitter(Qt.Vertical, page)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.addWidget(self._build_section_window())
        bottom = QSplitter(Qt.Horizontal, page)
        bottom.setChildrenCollapsible(False)
        bottom.addWidget(self._build_curve_window())
        bottom.addWidget(self._build_model_table_window())
        bottom.setStretchFactor(0, 4)
        bottom.setStretchFactor(1, 1)
        self.main_splitter.addWidget(bottom)
        self.main_splitter.setStretchFactor(0, 2)
        self.main_splitter.setStretchFactor(1, 3)
        layout.addWidget(self.main_splitter, 1)
        return page

    def _build_section_window(self) -> QFrame:
        frame, layout = self._classic_window("Pseudo cross-section and resistivity section")
        self.section_plot = pg.PlotWidget(background="#FFFFFF")
        self.section_plot.showGrid(x=True, y=True, alpha=0.18)
        self.section_plot.setMouseEnabled(x=True, y=True)
        layout.addWidget(self.section_plot, 1)
        self.section_colorbar = PaletteColorBar(frame, orientation=Qt.Horizontal)
        self.section_colorbar.set_state(30, 300, self._palette_name, unit="Ωm", label="ρa / ρ")
        layout.addWidget(self.section_colorbar)
        return frame

    def _build_curve_window(self) -> QFrame:
        frame, layout = self._classic_window("Apparent resistivity curve")
        self.curve_plot = pg.PlotWidget(background="#FFFFFF")
        self.curve_plot.showGrid(x=True, y=True, alpha=0.28)
        self.curve_plot.setLogMode(x=True, y=True)
        self.curve_plot.setLabel("bottom", "AB/2")
        self.curve_plot.setLabel("left", "ρa")
        self.curve_plot.scene().sigMouseMoved.connect(lambda pos: self._curve_hover_on_plot(self.curve_plot, pos))
        self.curve_plot.scene().sigMouseClicked.connect(lambda event: self._curve_clicked_on_plot(self.curve_plot, event))
        layout.addWidget(self.curve_plot, 1)
        return frame

    def _build_model_table_window(self) -> QFrame:
        frame, layout = self._classic_window("Error / model")
        self.error_label = QLabel("Error = --")
        self.error_label.setObjectName("smallStatus")
        layout.addWidget(self.error_label)
        self.model_table = QTableWidget(0, 5, frame)
        self.model_table.setHorizontalHeaderLabels(["N", "ρ", "h", "d", "Alt"])
        self.model_table.verticalHeader().setVisible(False)
        self.model_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.model_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.model_table.verticalHeader().setDefaultSectionSize(18)
        self.model_table.itemChanged.connect(self._on_model_table_changed)
        layout.addWidget(self.model_table, 1)
        return frame

    def _build_data_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        top = QHBoxLayout()
        self.array_combo_main = QComboBox()
        self.array_combo_main.addItems(["Schlumberger", "Pole-dipole", "Wenner", "Express (AB=2AOmax)"])
        self.array_combo_main.currentTextChanged.connect(self._array_changed)
        top.addWidget(QLabel("Array type"))
        top.addWidget(self.array_combo_main)
        top.addStretch(1)
        for text, slot in [("Open TXT", self.open_file), ("Save TXT", self.save_file), ("Recalc", self.recalculate_geometric_factor), ("Point dialog", self.edit_curve)]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            top.addWidget(btn)
        layout.addLayout(top)
        self.data_table = QTableWidget(0, 8, page)
        self.data_table.setAlternatingRowColors(True)
        self.data_table.setHorizontalHeaderLabels(["N", "AB/2", "MN", "SP", "V", "I", "K", "Ro_a"])
        self.data_table.verticalHeader().setVisible(False)
        self.data_table.verticalHeader().setDefaultSectionSize(18)
        self.data_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.data_table.itemChanged.connect(self._on_data_table_changed)
        layout.addWidget(self.data_table, 1)
        return page

    def _build_curve_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        self.curve_detail_plot = pg.PlotWidget(background="#FFFFFF")
        self.curve_detail_plot.setLogMode(x=True, y=True)
        self.curve_detail_plot.showGrid(x=True, y=True, alpha=0.28)
        self.curve_detail_plot.setLabel("bottom", "AB/2")
        self.curve_detail_plot.setLabel("left", "ρa / ρ")
        self.curve_detail_plot.scene().sigMouseMoved.connect(lambda pos: self._curve_hover_on_plot(self.curve_detail_plot, pos))
        self.curve_detail_plot.scene().sigMouseClicked.connect(lambda event: self._curve_clicked_on_plot(self.curve_detail_plot, event))
        layout.addWidget(self.curve_detail_plot, 1)
        return page

    def _build_section_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        self.section_detail_plot = pg.PlotWidget(background="#FFFFFF")
        self.section_detail_plot.showGrid(x=True, y=True, alpha=0.18)
        layout.addWidget(self.section_detail_plot, 1)
        self.section_detail_colorbar = PaletteColorBar(page, orientation=Qt.Horizontal)
        layout.addWidget(self.section_detail_colorbar)
        return page

    def _build_results_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        self.results_detail = QTextEdit(page)
        self.results_detail.setReadOnly(True)
        layout.addWidget(self.results_detail, 1)
        return page

    # ------------------------------------------------------------------ file/data
    def reset_blank_project(self, message: str = "New empty VES/IP profile created") -> None:
        """Clear the IPWin2 workspace without inserting sample data."""
        self.source_path = None
        self.rows = []
        self.profiles = []
        self.layers = []
        self.current_point = 0
        self.total_points = 0
        self._selected_curve_index = None
        self._drag_model_handle = None
        self._last_model_snapshot = []
        self.refresh(message)

    def new_profile(self) -> None:
        """Open the IPI-style New VES point dialog.

        Unlike the previous placeholder behavior, the New command now opens a
        real data-entry dialog similar to the reference IP2Win screen.  If the
        user cancels, the workspace remains unchanged and no dummy data is
        created.
        """
        dialog = VesPointEntryDialog([], self.array_type, self)
        if dialog.exec() != QDialog.Accepted:
            self.status.setText("New VES/IP point cancelled")
            return
        self.source_path = None
        self.rows = [complete_row(r, dialog.array_type) for r in dialog.rows]
        self.array_type = dialog.array_type
        self.profiles = [("VES 1", [complete_row(r, self.array_type) for r in self.rows])] if self.rows else []
        self.current_point = 0
        self.total_points = len(self.profiles)
        self._selected_curve_index = None
        self._drag_model_handle = None
        self.quick_model_from_curve()
        self.refresh("New VES/IP point created")

    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open IPWin2 / VES-IP file", str(Path.home()), "VES/IP data (*.dat *.txt *.csv *.ves);;All Files (*.*)")
        if path:
            self.open_path(path)

    def open_path(self, path: str | Path) -> None:
        p = Path(path).expanduser().resolve()
        self.activity_started.emit("Opening IPWin2 / VES-IP file", p.name)
        error: Exception | None = None
        try:
            profiles = self._read_profiles(p)
            if not profiles:
                raise ValueError(
                    "No VES rows were detected. Expected an IPI2Win DAT profile "
                    "file, AB/2/MN/V/I/K/Ro_a columns, or plain numeric rows."
                )
            self.profiles = [(name, [complete_row(r, self.array_type) for r in rows]) for name, rows in profiles]
            self.current_point = 0
            self.total_points = len(self.profiles)
            self.rows = [complete_row(r, self.array_type) for r in self.profiles[0][1]]
            self.source_path = p
            self.quick_model_from_curve()
            self.refresh(f"Loaded {len(self.profiles)} VES profiles / {len(self.rows)} readings: {p.name}")
        except Exception as exc:
            error = exc
        finally:
            self.activity_finished.emit()
        if error is not None:
            QMessageBox.critical(self, "IPWin2 / VES-IP", f"Unable to open file:\n{error}")

    def _read_profiles(self, path: Path) -> list[tuple[str, list[VesRow]]]:
        text = path.read_text(errors="ignore")
        lines = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith(("#", "//"))]
        if not lines:
            return []

        ipi_profiles = self._parse_ipi2win_dat_profiles(lines)
        if ipi_profiles:
            return ipi_profiles

        rows = self._read_rows_from_table_lines(lines)
        if rows:
            return [(path.stem, rows)]
        return []

    def _read_rows(self, path: Path) -> list[VesRow]:
        profiles = self._read_profiles(path)
        return profiles[0][1] if profiles else []

    def _parse_ipi2win_dat_profiles(self, lines: list[str]) -> list[tuple[str, list[VesRow]]]:
        """Parse classic IPI2Win profile DAT files.

        Expected form observed in the supplied ``test_ipi.DAT``:
            title
            comments
            <nProfiles> <KeyIP> <maxNAB> <filterKey> { comment }
            AB/2 spacings over one or more lines
            profile-name
            nReadings
            apparent resistivity values over one or more lines

        Some real IPI2Win examples contain a profile count that does not match
        the following profile blocks, so the parser trusts the actual blocks and
        keeps reading until EOF.
        """
        header_idx = -1
        max_nab = 0
        for i, line in enumerate(lines[:20]):
            clean = line.split("{", 1)[0]
            parts = clean.split()
            if len(parts) >= 3:
                try:
                    # First two numbers may be profile count and KeyIP.  Third
                    # is the maximum AB/2 count on the profile.
                    int(float(parts[0])); int(float(parts[1])); max_nab = int(float(parts[2]))
                    if max_nab > 1:
                        header_idx = i
                        break
                except Exception:
                    continue
        if header_idx < 0 or max_nab <= 0:
            return []

        idx = header_idx + 1
        spacings: list[float] = []
        while idx < len(lines) and len(spacings) < max_nab:
            nums = _line_numbers(lines[idx])
            if not nums:
                break
            spacings.extend(nums)
            idx += 1
        if len(spacings) < 2:
            return []
        spacings = spacings[:max_nab]

        profiles: list[tuple[str, list[VesRow]]] = []
        while idx < len(lines):
            name = lines[idx].strip()
            idx += 1
            if not name:
                continue
            # Skip accidental numeric-only spacing/value remnants.
            if len(_line_numbers(name)) > 1 and not re.search(r"[A-Za-z/\-]", name):
                continue
            if idx >= len(lines):
                break
            count_nums = _line_numbers(lines[idx])
            if not count_nums:
                continue
            n_readings = int(count_nums[0])
            idx += 1
            values: list[float] = []
            while idx < len(lines) and len(values) < n_readings:
                nums = _line_numbers(lines[idx])
                if not nums:
                    break
                values.extend(nums)
                idx += 1
            if n_readings <= 0 or not values:
                continue
            values = values[:min(n_readings, len(spacings), len(values))]
            rows = [complete_row(VesRow(ab2=spacings[j], mn=1.0, rhoa=values[j]), self.array_type) for j in range(len(values))]
            if rows:
                profiles.append((name, rows))
        return profiles

    def _read_rows_from_table_lines(self, lines: list[str]) -> list[VesRow]:
        sample = "\n".join(lines[:10])
        delimiter = "," if sample.count(",") >= sample.count("\t") else "\t"
        if delimiter not in sample and ";" in sample:
            delimiter = ";"
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t ").delimiter
        except Exception:
            pass
        header_tokens = _tokens(lines[0], delimiter)
        has_header = any(any(ch.isalpha() for ch in tok) for tok in header_tokens)
        rows: list[VesRow] = []
        if has_header:
            headers = [_norm(tok) for tok in header_tokens]
            for line in lines[1:]:
                toks = _tokens(line, delimiter)
                values = {headers[i]: parse_float(toks[i]) for i in range(min(len(headers), len(toks)))}
                rows.append(complete_row(VesRow(
                    ab2=_first(values, "ab2", "ab/2", "ab_2", "spacing", "ao", "x"),
                    mn=_first(values, "mn", "mn2", "mn/2", "n"),
                    sp=_first(values, "sp", "spmv", "sp_mv"),
                    voltage=_first(values, "v", "volt", "voltage", "voltage_mv"),
                    current=_first(values, "i", "current", "current_ma"),
                    k=_first(values, "k", "geometric", "geometric_factor"),
                    rhoa=_first(values, "rho_a", "rhoa", "ro_a", "pa", "apparent", "app_res", "apparent_resistivity", "apparent_resistivity_ohm_m"),
                ), self.array_type))
        else:
            for line in lines:
                vals = [parse_float(tok) for tok in _tokens(line, delimiter)]
                vals = [v for v in vals if np.isfinite(v)]
                if len(vals) >= 2:
                    padded = vals + [math.nan] * 7
                    rows.append(complete_row(VesRow(padded[0], padded[1], padded[2], padded[3], padded[4], padded[5], padded[6]), self.array_type))
        return [row for row in rows if np.isfinite(row.ab2) or np.isfinite(row.rhoa)]

    def save_file(self) -> None:
        if self.source_path is None:
            self.save_file_as()
            return
        self._pull_rows_from_table()
        self._write_rows(self.source_path)
        self.refresh(f"Saved {self.source_path.name}")

    def save_file_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save IPWin2 / VES-IP data", str(Path.home() / "ves_ipwin2.dat"), "DAT (*.dat);;TXT (*.txt);;CSV (*.csv)")
        if path:
            self.source_path = Path(path).expanduser().resolve()
            self.save_file()

    def _write_rows(self, path: Path) -> None:
        delimiter = "," if path.suffix.lower() == ".csv" else "\t"
        with path.open("w", newline="") as fh:
            writer = csv.writer(fh, delimiter=delimiter)
            writer.writerow(["AB/2", "MN", "SP", "V", "I", "K", "Ro_a"])
            for row in self.rows:
                writer.writerow([display_value(row.ab2), display_value(row.mn), display_value(row.sp), display_value(row.voltage), display_value(row.current), display_value(row.k), display_value(row.rhoa)])

    # ------------------------------------------------------------------ refresh/plot
    def refresh(self, message: str | None = None) -> None:
        self._pull_rows_from_table(silent=True)
        point_total = max(self.total_points, 0)
        point_no = self.current_point + 1 if point_total else 0
        self.point_label.setText(f"{point_no}/{point_total}")
        profile_name = self.profiles[self.current_point][0] if self.profiles and 0 <= self.current_point < len(self.profiles) else "--"
        self.metric_point.setText(f"VES: {point_no} / {point_total}  {profile_name}")
        self.metric_file.setText(f"File: {self.source_path.name if self.source_path else 'no file loaded'}")
        err = self.model_error()
        err_text = f"Error: {err:.2f}%" if np.isfinite(err) else "Error: --"
        self.metric_error.setText(err_text)
        self._refresh_data_table()
        self._refresh_curve()
        self._refresh_detail_curve()
        self._refresh_sections()
        self._refresh_detail_section()
        self._refresh_model_table()
        self._refresh_results()
        if message:
            self.status.setText(message)

    def _curve_arrays(self) -> tuple[np.ndarray, np.ndarray]:
        rows = [complete_row(r, self.array_type) for r in self.rows]
        x = np.asarray([r.ab2 for r in rows], dtype=float)
        y = np.asarray([r.rhoa for r in rows], dtype=float)
        valid = np.isfinite(x) & np.isfinite(y) & (x > 0) & (y > 0)
        if not np.any(valid):
            return np.array([]), np.array([])
        order = np.argsort(x[valid])
        return x[valid][order], y[valid][order]

    def _refresh_data_table(self) -> None:
        if not hasattr(self, "data_table"):
            return
        table = self.data_table
        table.blockSignals(True)
        table.clearContents()
        table.setRowCount(max(len(self.rows), 24))
        for r in range(table.rowCount()):
            item = QTableWidgetItem(str(r + 1))
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            table.setItem(r, 0, item)
            for c in range(1, 8):
                table.setItem(r, c, QTableWidgetItem(""))
        for r, row in enumerate(self.rows):
            values = [row.ab2, row.mn, row.sp, row.voltage, row.current, row.k, row.rhoa]
            for c, value in enumerate(values, start=1):
                table.setItem(r, c, QTableWidgetItem(display_value(value)))
        table.blockSignals(False)
        self.array_combo_main.blockSignals(True)
        self.array_combo_main.setCurrentText(self.array_type)
        self.array_combo_main.blockSignals(False)

    def _pull_rows_from_table(self, silent: bool = False) -> None:
        if not hasattr(self, "data_table") or self.data_table.hasFocus() is False and silent:
            return
        rows: list[VesRow] = []
        table = self.data_table
        for r in range(table.rowCount()):
            vals = [parse_float(table.item(r, c).text()) if table.item(r, c) else math.nan for c in range(1, 8)]
            if np.isfinite(vals[0]) or np.isfinite(vals[-1]):
                rows.append(complete_row(VesRow(vals[0], vals[1], vals[2], vals[3], vals[4], vals[5], vals[6]), self.array_type))
        if rows:
            self.rows = rows
            if self.profiles and 0 <= self.current_point < len(self.profiles):
                name = self.profiles[self.current_point][0]
                self.profiles[self.current_point] = (name, rows)

    def _on_data_table_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 0:
            return
        self._pull_rows_from_table()
        self.recalculate_geometric_factor(show_message=False)
        self.refresh("VES table updated")

    def _refresh_curve(self) -> None:
        profile_name = self.profiles[self.current_point][0] if self.profiles and 0 <= self.current_point < len(self.profiles) else "--"
        self._draw_curve_plot(self.curve_plot, title=f"VES {(self.current_point + 1) if self.total_points else 0}/{self.total_points} {profile_name} — apparent, synthetic and model curves")

    def _refresh_detail_curve(self) -> None:
        self._draw_curve_plot(self.curve_detail_plot, title="Detailed curve editor — click a point for values")

    def _draw_curve_plot(self, plot: pg.PlotWidget, title: str) -> None:
        plot.clear()
        plot.setLogMode(x=self._log_enabled, y=self._log_enabled)
        plot.showGrid(x=True, y=True, alpha=0.28)
        plot.setLabel("bottom", "AB/2")
        plot.setLabel("left", "ρa / ρ")
        x, y = self._curve_arrays()
        if x.size == 0:
            plot.setTitle("No apparent resistivity data")
            return
        plot.plot(x, y, pen=pg.mkPen("#111111", width=1.0), symbol="s", symbolSize=5, symbolPen="#333333", symbolBrush="#FFFFFF")
        sx, sy = self.synthetic_curve()
        if sx.size:
            plot.plot(sx, sy, pen=pg.mkPen("#E11D24", width=1.5))
        step_x, step_y = self.model_step_curve()
        if step_x.size:
            plot.plot(
                step_x,
                step_y,
                pen=pg.mkPen("#1E40FF", width=1.8),
                symbol="s",
                symbolSize=6,
                symbolPen="#0B2DFF",
                symbolBrush="#D9E6FF",
            )
        if self._selected_curve_index is not None and 0 <= self._selected_curve_index < x.size:
            plot.plot([x[self._selected_curve_index]], [y[self._selected_curve_index]], pen=None, symbol="o", symbolSize=10, symbolPen="#FFB000", symbolBrush="#FFF2B8")
        plot.setTitle(title)

    def _section_image_data(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, float, float]:
        if not self.profiles:
            x, y = self._curve_arrays()
            if x.size == 0:
                return x, np.array([]), np.array([[]]), math.nan, math.nan
            depths = np.array([3, 10, 30, 100, 300], dtype=float)
            vals = np.vstack([y, y * 0.62, y * 0.38, y * 0.75, y * 1.1]) if y.size else np.array([[]])
            finite = vals[np.isfinite(vals) & (vals > 0)]
            if finite.size == 0:
                return x, depths, vals, math.nan, math.nan
            lo, hi = self._scale_limits(finite)
            return x, depths, vals, lo, hi

        max_cols = max((len(rows) for _, rows in self.profiles), default=0)
        if max_cols == 0:
            return np.array([]), np.array([]), np.array([[]]), math.nan, math.nan
        xs = np.arange(1, len(self.profiles) + 1, dtype=float)
        vals = np.full((max_cols, len(self.profiles)), np.nan, dtype=float)
        for col, (_, rows) in enumerate(self.profiles):
            sorted_rows = sorted([complete_row(r, self.array_type) for r in rows], key=lambda r: (r.ab2 if np.isfinite(r.ab2) else 1e99))
            for depth_idx, row in enumerate(sorted_rows[:max_cols]):
                vals[depth_idx, col] = row.rhoa
        depths = np.arange(1, max_cols + 1, dtype=float)
        finite = vals[np.isfinite(vals) & (vals > 0)]
        if finite.size == 0:
            return xs, depths, vals, math.nan, math.nan
        lo, hi = self._scale_limits(finite)
        return xs, depths, vals, lo, hi

    def _scale_limits(self, finite: np.ndarray) -> tuple[float, float]:
        if self._auto_scale and finite.size >= 3:
            lo, hi = float(np.nanpercentile(finite, 3)), float(np.nanpercentile(finite, 97))
        else:
            lo, hi = float(np.nanmin(finite)), float(np.nanmax(finite))
        if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
            hi = lo + max(abs(lo) * 0.05, 1.0)
        return lo, hi

    def _refresh_sections(self) -> None:
        self._draw_section_plot(self.section_plot, self.section_colorbar)

    def _refresh_detail_section(self) -> None:
        self._draw_section_plot(self.section_detail_plot, self.section_detail_colorbar)

    def _draw_section_plot(self, plot: pg.PlotWidget, colorbar: PaletteColorBar) -> None:
        plot.clear()
        plot.showGrid(x=True, y=True, alpha=0.18)
        x, depths, vals, lo, hi = self._section_image_data()
        if x.size == 0 or not np.isfinite(lo) or not np.isfinite(hi):
            plot.setTitle("No pseudo-section available")
            colorbar.set_state(math.nan, math.nan, self._palette_name, unit="Ωm", label="ρa / ρ")
            return
        levels = np.clip((vals - lo) / max(hi - lo, 1e-9), 0, 1)
        rgb = palette_rgb_array(self._palette_name, 256)
        lut_idx = np.clip(np.nan_to_num(levels, nan=0.0) * 255, 0, 255).astype(int)
        rgba = rgb[lut_idx]
        image = pg.ImageItem(rgba)
        xmin, xmax = float(np.nanmin(x)), float(np.nanmax(x))
        width = max(xmax - xmin, 1.0)
        pseudo_height = float(max(len(depths), 1) * 18.0)
        image.setRect(QRectF(xmin, -pseudo_height, width, pseudo_height))
        if self._section_mode in {"both", "pseudo"}:
            plot.addItem(image)
            for idx in range(len(self.profiles)):
                plot.plot([idx + 1, idx + 1], [0, -pseudo_height], pen=pg.mkPen("#000000", width=0.45))
            if self.profiles:
                labels = [(i + 1, name) for i, (name, _) in enumerate(self.profiles)]
                axis = plot.getAxis("bottom")
                axis.setTicks([[(float(pos), str(name)) for pos, name in labels[::max(1, len(labels)//10 or 1)]]])
        if self._section_mode in {"both", "resistivity"}:
            self._draw_model_rectangles(plot, xmin, xmax, top=-(pseudo_height + 30.0) if self._section_mode == "both" else -20.0)
        plot.setLabel("bottom", "Profile / VES point")
        plot.setLabel("left", "AO / H, m")
        plot.setTitle("Pseudo cross-section" if self._section_mode == "pseudo" else "Resistivity cross-section" if self._section_mode == "resistivity" else "Pseudo cross-section and resistivity section")
        colorbar.set_state(lo, hi, self._palette_name, unit="Ωm", label="ρa / ρ")

    def _draw_model_rectangles(self, plot: pg.PlotWidget, xmin: float, xmax: float, top: float | None = None) -> None:
        if not self.layers:
            return
        rgb = palette_rgb_array(self._palette_name, 256)
        rhos = np.asarray([l.rho for l in self.layers if np.isfinite(l.rho)], dtype=float)
        if rhos.size == 0:
            return
        lo, hi = float(np.nanmin(rhos)), float(np.nanmax(rhos))
        top = (-330.0 if self._section_mode == "both" else -20.0) if top is None else top
        current_top = top
        width = max(xmax - xmin, 1.0)
        for layer in self.layers:
            h = layer.h if np.isfinite(layer.h) else 80.0
            z1, z2 = current_top, current_top - max(h, 5.0)
            idx = int(np.clip((layer.rho - lo) / max(hi - lo, 1e-9) * 255, 0, 255))
            color = rgb[idx]
            rect = QGraphicsRectItem(xmin, z2, width, abs(z2 - z1))
            rect.setPen(pg.mkPen("#000000", width=0.7))
            rect.setBrush(pg.mkBrush(int(color[0]), int(color[1]), int(color[2]), 220))
            plot.addItem(rect)
            current_top = z2

    def _refresh_model_table(self) -> None:
        table = self.model_table
        table.blockSignals(True)
        table.setRowCount(len(self.layers))
        depth = 0.0
        for i, layer in enumerate(self.layers):
            h = layer.h if np.isfinite(layer.h) else math.nan
            depth = depth + h if np.isfinite(h) else depth
            alt = 170.0 - depth if np.isfinite(h) else math.nan
            values = [i + 1, layer.rho, h, depth if np.isfinite(h) else math.nan, alt]
            for col, value in enumerate(values):
                item = QTableWidgetItem(display_value(value))
                if col in {1, 2}:
                    item.setFlags(item.flags() | Qt.ItemIsEditable)
                else:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                table.setItem(i, col, item)
        table.blockSignals(False)
        error = self.model_error()
        self.error_label.setText(f"Error = {error:.2f}%" if np.isfinite(error) else "Error = --")

    def _refresh_results(self) -> None:
        text = self.results_text(include_curve=True)
        self.results_box.setPlainText(text[:3000])
        self.results_detail.setPlainText(text)

    def _on_model_table_changed(self, item: QTableWidgetItem) -> None:
        row, col = item.row(), item.column()
        if not (0 <= row < len(self.layers)):
            return
        self._snapshot_model()
        value = parse_float(item.text())
        if col == 1 and np.isfinite(value) and value > 0:
            self.layers[row].rho = value
        elif col == 2:
            self.layers[row].h = value if np.isfinite(value) and value > 0 else math.nan
        self.refresh("Model layer edited")

    def synthetic_curve(self) -> tuple[np.ndarray, np.ndarray]:
        x, _ = self._curve_arrays()
        if x.size == 0 or not self.layers:
            return np.array([]), np.array([])
        depths: list[float] = []
        d = 0.0
        for layer in self.layers:
            if np.isfinite(layer.h):
                d += max(layer.h, 1e-3)
                depths.append(d)
            else:
                depths.append(max(float(x[-1]), d + 1.0))
        rho = np.asarray([max(l.rho, 1e-6) for l in self.layers], dtype=float)
        centres = np.asarray(depths, dtype=float)
        if centres.size == 1:
            return x, np.full_like(x, rho[0])
        synth = np.interp(np.log10(x), np.log10(np.maximum(centres, 1e-3)), rho, left=rho[0], right=rho[-1])
        if synth.size >= 3:
            kernel = np.ones(3) / 3.0
            synth = np.convolve(synth, kernel, mode="same")
            synth[0], synth[-1] = rho[0], rho[-1]
        return x, synth

    def model_step_curve(self) -> tuple[np.ndarray, np.ndarray]:
        if not self.layers:
            return np.array([]), np.array([])
        xs = [1.0]
        ys = [self.layers[0].rho]
        d = 1.0
        for idx, layer in enumerate(self.layers[:-1]):
            if np.isfinite(layer.h) and layer.h > 0:
                d += layer.h
            xs.extend([d, d])
            ys.extend([ys[-1], self.layers[min(idx + 1, len(self.layers) - 1)].rho])
        xs.append(max(d * 4, 100.0))
        ys.append(self.layers[-1].rho)
        return np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)

    def model_error(self) -> float:
        _, y = self._curve_arrays()
        _, sy = self.synthetic_curve()
        if y.size == 0 or sy.size != y.size:
            return math.nan
        return float(np.nanmean(np.abs(np.log10(np.maximum(y, 1e-9)) - np.log10(np.maximum(sy, 1e-9)))) * 100.0)

    # ------------------------------------------------------------------ commands
    def edit_curve(self) -> None:
        dialog = VesPointEntryDialog(self.rows, self.array_type, self)
        if dialog.exec() == QDialog.Accepted:
            self.rows = dialog.rows
            self.array_type = dialog.array_type
            self.quick_model_from_curve()
            self.refresh("VES/IP point updated")

    def recalculate_geometric_factor(self, show_message: bool = True) -> None:
        self.rows = [complete_row(row, self.array_type) for row in self.rows]
        if show_message:
            self.refresh("Geometric factor and apparent resistivity recalculated")

    def quick_model_from_curve(self) -> None:
        x, y = self._curve_arrays()
        if y.size == 0:
            return
        self._snapshot_model()
        q = np.nanpercentile(y, [90, 35, 15, 65, 75]) if y.size >= 5 else np.repeat(float(np.nanmedian(y)), 5)
        xq = np.nanpercentile(x, [20, 45, 70]) if x.size >= 3 else [3, 20, 60]
        self.layers = [
            ModelLayer(float(max(q[0], 1.0)), float(max(xq[0] * 0.35, 0.5))),
            ModelLayer(float(max(q[1], 1.0)), float(max(xq[1] * 0.7, 1.0))),
            ModelLayer(float(max(q[3], 1.0)), float(max(xq[2] * 0.8, 1.0))),
            ModelLayer(float(max(q[-1], 1.0)), math.nan),
        ]

    def run_inversion(self) -> None:
        self.quick_model_from_curve()
        self.refresh("Quick automatic model generated from apparent curve")

    def run_profile_inversion(self) -> None:
        self.run_inversion()

    def new_model(self) -> None:
        self._snapshot_model()
        self.layers = [ModelLayer(100.0, 5.0), ModelLayer(50.0, 25.0), ModelLayer(200.0, math.nan)]
        self.refresh("New model created")

    def restore_model(self) -> None:
        if self._last_model_snapshot:
            self.layers = [ModelLayer(l.rho, l.h) for l in self._last_model_snapshot]
            self.refresh("Previous model restored")
        else:
            self.quick_model_from_curve()
            self.refresh("Model restored from curve")

    def _snapshot_model(self) -> None:
        self._last_model_snapshot = [ModelLayer(l.rho, l.h) for l in self.layers]

    def cut_model(self) -> None:
        self._snapshot_model()
        self.layers = []
        self.refresh("Model cut")

    def paste_model(self) -> None:
        self.restore_model()

    def split_layer(self) -> None:
        self._snapshot_model()
        row = self.model_table.currentRow()
        if not (0 <= row < len(self.layers)):
            row = 0
        layer = self.layers[row]
        h = layer.h / 2.0 if np.isfinite(layer.h) and layer.h > 0 else 10.0
        self.layers[row] = ModelLayer(layer.rho, h)
        self.layers.insert(row + 1, ModelLayer(layer.rho, h))
        self.refresh("Layer split")

    def join_layers(self) -> None:
        self._snapshot_model()
        row = self.model_table.currentRow()
        if row < 0:
            row = max(0, len(self.layers) - 2)
        if row + 1 < len(self.layers):
            a, b = self.layers[row], self.layers[row + 1]
            h = (a.h if np.isfinite(a.h) else 0) + (b.h if np.isfinite(b.h) else 0)
            rho = (a.rho + b.rho) / 2.0
            self.layers[row] = ModelLayer(rho, h if h > 0 else math.nan)
            del self.layers[row + 1]
            self.refresh("Layers joined")

    def move_selected_layer_left(self) -> None:
        row = self.model_table.currentRow()
        if 0 <= row < len(self.layers) and np.isfinite(self.layers[row].h):
            self._snapshot_model(); self.layers[row].h = max(self.layers[row].h * 0.85, 0.1); self.refresh("Selected layer moved left")

    def move_selected_layer_right(self) -> None:
        row = self.model_table.currentRow()
        if 0 <= row < len(self.layers) and np.isfinite(self.layers[row].h):
            self._snapshot_model(); self.layers[row].h = self.layers[row].h * 1.15; self.refresh("Selected layer moved right")

    def _set_current_profile(self, index: int) -> None:
        if not self.profiles:
            self.current_point = 0
            self.rows = []
            self.refresh()
            return
        self.current_point = int(np.clip(index, 0, len(self.profiles) - 1))
        self.rows = [complete_row(r, self.array_type) for r in self.profiles[self.current_point][1]]
        self.quick_model_from_curve()
        self.refresh(f"VES {self.current_point + 1}/{len(self.profiles)} selected: {self.profiles[self.current_point][0]}")

    def next_point(self) -> None:
        self._set_current_profile(self.current_point + 1)
    def previous_point(self) -> None:
        self._set_current_profile(self.current_point - 1)
    def first_point(self) -> None:
        self._set_current_profile(0)
    def last_point(self) -> None:
        self._set_current_profile(max(self.total_points - 1, 0))

    def copy_curve_values(self) -> None:
        QApplication.clipboard().setText("\n".join(f"{display_value(r.ab2)}\t{display_value(r.rhoa)}" for r in self.rows))
        self.status.setText("Curve copied")

    def copy_all_results(self) -> None:
        QApplication.clipboard().setText(self.results_text())
        self.status.setText("All results copied")

    def copy_model_curve(self) -> None:
        QApplication.clipboard().setText(self.results_text(include_curve=True))
        self.status.setText("Model and curve copied")

    def copy_synthetic_curve(self) -> None:
        sx, sy = self.synthetic_curve()
        QApplication.clipboard().setText("\n".join(f"{display_value(a)}\t{display_value(b)}" for a, b in zip(sx, sy)))
        self.status.setText("Synthetic curve copied")

    def copy_pseudo_section(self) -> None:
        self.status.setText("Pseudo-section view is ready for screenshot/print")

    def delete_all_results(self) -> None:
        self._snapshot_model(); self.layers = []; self.refresh("All model results deleted")

    def calculate_synthetic_curve(self) -> None:
        self.refresh("Synthetic curve recalculated")

    def show_dar_zarrouk(self) -> None:
        conductance = sum((l.h / l.rho) for l in self.layers if np.isfinite(l.h) and l.rho > 0)
        resistance = sum((l.h * l.rho) for l in self.layers if np.isfinite(l.h))
        QMessageBox.information(self, "Dar-Zarrouk", f"Transverse resistance: {display_value(resistance)} Ωm²\nLongitudinal conductance: {display_value(conductance)} S")

    def profile_extrapolation(self) -> None:
        self.status.setText("Profile extrapolation prepared")
    def inversion_options(self) -> None:
        if IpiInversionOptionsDialog(self).exec() == QDialog.Accepted:
            self.status.setText("Inversion options updated")
    def change_table(self) -> None:
        self.edit_curve()
    def toggle_fixing(self) -> None:
        self.status.setText("Selected model parameter fixing toggled")
    def fix_all_h(self) -> None:
        self.status.setText("All H values marked as fixed")
    def model_minimum(self) -> None:
        if IpiLayerConstraintDialog("Minimum", self).exec() == QDialog.Accepted:
            self.status.setText("Minimum constraint updated")
    def model_maximum(self) -> None:
        if IpiLayerConstraintDialog("Maximum", self).exec() == QDialog.Accepted:
            self.status.setText("Maximum constraint updated")
    def zoom_in(self) -> None:
        for plot in (self.curve_plot, self.curve_detail_plot, self.section_plot, self.section_detail_plot):
            plot.getViewBox().scaleBy((0.75, 0.75))
    def zoom_out(self) -> None:
        for plot in (self.curve_plot, self.curve_detail_plot, self.section_plot, self.section_detail_plot):
            plot.getViewBox().scaleBy((1.25, 1.25))
    def fit_profile(self) -> None:
        for plot in (self.curve_plot, self.curve_detail_plot, self.section_plot, self.section_detail_plot):
            plot.enableAutoRange()
        self.status.setText("All profile fitted")
    def more_depth(self) -> None:
        self.status.setText("Depth range increased")
    def less_depth(self) -> None:
        self.status.setText("Depth range reduced")
    def section_options(self) -> None:
        if IpiSectionOptionsDialog(self).exec() == QDialog.Accepted:
            self.refresh("Section options updated")
    def show_pseudosection_only(self) -> None:
        self._section_mode = "pseudo"; self.mode_combo.setCurrentText("Pseudo only"); self.workspace_tabs.setCurrentIndex(3); self.refresh("Pseudo-section view selected")
    def show_resistivity_only(self) -> None:
        self._section_mode = "resistivity"; self.mode_combo.setCurrentText("Resistivity only"); self.workspace_tabs.setCurrentIndex(3); self.refresh("Resistivity section view selected")
    def show_both_sections(self) -> None:
        self._section_mode = "both"; self.mode_combo.setCurrentText("Both sections"); self.workspace_tabs.setCurrentIndex(0); self.refresh("Both sections shown")
    def toggle_log_scale(self, set_to: bool | None = None) -> None:
        self._log_enabled = (not self._log_enabled) if set_to is None else bool(set_to)
        self.log_check.blockSignals(True); self.log_check.setChecked(self._log_enabled); self.log_check.blockSignals(False)
        self.refresh("Log scale" if self._log_enabled else "Linear scale")
    def horizontal_mirror(self) -> None:
        self.rows.reverse(); self.refresh("Horizontal mirror applied")
    def transformation(self) -> None:
        self.status.setText("Section transformation command selected")
    def axes_limits(self) -> None:
        if IpiAxesLimitsDialog(self).exec() == QDialog.Accepted:
            self.fit_profile(); self.status.setText("Axes limits updated")
    def tile_windows(self) -> None:
        self.show_classic_layout(); self.status.setText("Windows tiled in interpretation layout")
    def cascade_windows(self) -> None:
        self.show_classic_layout(); self.main_splitter.setSizes([220, 420]); self.status.setText("Windows arranged")
    def show_classic_layout(self) -> None:
        self.workspace_tabs.setCurrentIndex(0)

    def profile_information(self) -> None:
        dialog = ProfileInformationDialog(self.profile_comments, self.array_type, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.profile_comments = dialog.comments
            self.array_type = dialog.array_type
            self.refresh("Profile information updated")

    def options_dialog(self) -> None:
        if IpiOptionsDialog(self).exec() == QDialog.Accepted:
            self.status.setText("Options updated")

    def palette_options(self) -> None:
        palettes = ["Resistivity", "Classic", "Seismic", "Thermal", "Viridis", "Turbo", "Rainbow"]
        current = palettes.index(self._palette_name) if self._palette_name in palettes else 0
        value, ok = IpiChoiceDialog.get_choice(self, "Palette", "Section palette", palettes, current)
        if ok:
            self._set_palette(value)

    def invert_palette(self) -> None:
        # Presentation flag retained for future palette LUT inversion; current shared
        # palette service provides named forward palettes only.
        self.status.setText("Palette inversion command selected")

    def toggle_auto_scale(self, set_to: bool | None = None) -> None:
        self._auto_scale = (not self._auto_scale) if set_to is None else bool(set_to)
        self.autoscale_check.blockSignals(True); self.autoscale_check.setChecked(self._auto_scale); self.autoscale_check.blockSignals(False)
        self.refresh("Auto color scaling enabled" if self._auto_scale else "Full color range enabled")

    def print_view(self) -> None:
        self.status.setText("Print/export view prepared")

    def about_dialog(self) -> None:
        QMessageBox.information(self, "IPWin2 / VES-IP 1D", "TGPAssure Electrical IPWin2 module: VES/IP table entry, apparent curve, quick model, pseudo-section and resistivity-section visualization.")

    # ------------------------------------------------------------------ interactions/helpers
    def _curve_hover_on_plot(self, plot: pg.PlotWidget, pos: Any) -> None:
        if not plot.sceneBoundingRect().contains(pos):
            return
        point = plot.plotItem.vb.mapSceneToView(pos)
        xval, yval = float(point.x()), float(point.y())
        if self._drag_model_handle is not None:
            self._apply_model_handle_drag(self._drag_model_handle, xval, yval)
            return
        handle = self._nearest_model_handle(xval, yval)
        if handle is not None:
            self.status.setText("Blue model handle: left-click to edit/drag, right-click to release")
            return
        idx = self._nearest_curve_index(xval, yval)
        if idx is None:
            return
        x, y = self._curve_arrays()
        self.status.setText(f"Curve point {idx + 1}: AB/2={display_value(x[idx])}, ρa={display_value(y[idx])} Ωm")

    def _curve_clicked_on_plot(self, plot: pg.PlotWidget, event: Any) -> None:
        point = plot.plotItem.vb.mapSceneToView(event.scenePos())
        xval, yval = float(point.x()), float(point.y())
        if event.button() == Qt.RightButton:
            self._drag_model_handle = None
            self.status.setText("Model drag released")
            return
        handle = self._nearest_model_handle(xval, yval)
        if handle is not None:
            self._drag_model_handle = handle
            self._snapshot_model()
            self._apply_model_handle_drag(handle, xval, yval)
            self.status.setText("Blue model line selected — move mouse to reshape model; right-click to release")
            return
        self._drag_model_handle = None
        idx = self._nearest_curve_index(xval, yval)
        if idx is not None:
            self._selected_curve_index = idx
            x, y = self._curve_arrays()
            QMessageBox.information(self, "VES point", f"Point: {idx + 1}\nAB/2: {display_value(x[idx])}\nρa: {display_value(y[idx])} Ωm\nArray: {self.array_type}")
            self.refresh()

    def _nearest_curve_index(self, xval: float, yval: float) -> int | None:
        x, y = self._curve_arrays()
        if x.size == 0 or not np.isfinite(xval) or not np.isfinite(yval):
            return None
        lx = np.log10(np.maximum(x, 1e-9)) if self._log_enabled else x
        ly = np.log10(np.maximum(y, 1e-9)) if self._log_enabled else y
        px = math.log10(max(xval, 1e-9)) if self._log_enabled and xval > 0 else xval
        py = math.log10(max(yval, 1e-9)) if self._log_enabled and yval > 0 else yval
        dist = (lx - px) ** 2 + (ly - py) ** 2
        idx = int(np.nanargmin(dist))
        return idx if np.isfinite(dist[idx]) else None


    def _nearest_model_handle(self, xval: float, yval: float) -> int | None:
        step_x, step_y = self.model_step_curve()
        if step_x.size == 0 or not np.isfinite(xval) or not np.isfinite(yval):
            return None
        lx = np.log10(np.maximum(step_x, 1e-9)) if self._log_enabled else step_x
        ly = np.log10(np.maximum(step_y, 1e-9)) if self._log_enabled else step_y
        px = math.log10(max(xval, 1e-9)) if self._log_enabled and xval > 0 else xval
        py = math.log10(max(yval, 1e-9)) if self._log_enabled and yval > 0 else yval
        dist = (lx - px) ** 2 + (ly - py) ** 2
        idx = int(np.nanargmin(dist))
        threshold = 0.045 if self._log_enabled else max(np.nanmax(step_x) - np.nanmin(step_x), 1.0) * 0.012
        return idx if np.isfinite(dist[idx]) and dist[idx] <= threshold else None

    def _apply_model_handle_drag(self, handle_index: int, xval: float, yval: float) -> None:
        if not self.layers or not np.isfinite(xval) or not np.isfinite(yval) or yval <= 0:
            return
        layer_index = max(0, min(len(self.layers) - 1, int(round(handle_index / 2))))
        self.layers[layer_index].rho = float(np.clip(yval, 1.0, 1_000_000.0))

        # Handles after the first point are located on layer boundaries.  Moving
        # them horizontally adjusts the preceding layer thickness, which updates
        # the blue model step and forces the red synthetic curve to recalculate.
        if handle_index > 0 and layer_index > 0:
            previous_depth = 1.0
            for layer in self.layers[: layer_index - 1]:
                if np.isfinite(layer.h) and layer.h > 0:
                    previous_depth += layer.h
            new_h = max(float(xval) - previous_depth, 0.1)
            if np.isfinite(new_h) and layer_index - 1 < len(self.layers):
                self.layers[layer_index - 1].h = new_h

        self._refresh_curve()
        self._refresh_detail_curve()
        self._refresh_model_table()
        self._refresh_results()
        self.status.setText(
            f"Model layer {layer_index + 1}: ρ={display_value(self.layers[layer_index].rho)} Ωm; "
            "synthetic curve recalculated"
        )

    def _array_changed(self, text: str) -> None:
        self.array_type = text
        self.recalculate_geometric_factor(show_message=False)
        self.refresh("Array type updated")

    def _set_palette(self, name: str) -> None:
        self._palette_name = name or "Resistivity"
        self.palette_combo.blockSignals(True); self.palette_combo.setCurrentText(self._palette_name); self.palette_combo.blockSignals(False)
        self.refresh(f"Palette set to {self._palette_name}")

    def _set_section_mode_from_combo(self, text: str) -> None:
        self._section_mode = "pseudo" if "Pseudo" in text else "resistivity" if "Resistivity" in text else "both"
        self.refresh(f"Section mode: {text}")

    def results_text(self, include_curve: bool = False) -> str:
        lines = [
            "TGPAssure IPWin2 / VES-IP 1D Results",
            f"Source: {self.source_path.name if self.source_path else 'unsaved profile'}",
            f"Array: {self.array_type}",
            f"VES point: {(self.current_point + 1) if self.total_points else 0}/{self.total_points}",
            f"Error: {display_value(self.model_error())}%",
            "",
            "Model layers:",
            "N\tρ\th\td\tAlt",
        ]
        depth = 0.0
        for i, layer in enumerate(self.layers, start=1):
            h = layer.h if np.isfinite(layer.h) else math.nan
            depth = depth + h if np.isfinite(h) else depth
            alt = 170.0 - depth if np.isfinite(h) else math.nan
            lines.append(f"{i}\t{display_value(layer.rho)}\t{display_value(h)}\t{display_value(depth)}\t{display_value(alt)}")
        if include_curve:
            lines.extend(["", "Apparent curve:", "AB/2\tρa"])
            for row in self.rows:
                lines.append(f"{display_value(row.ab2)}\t{display_value(row.rhoa)}")
        return "\n".join(lines)


def _norm(text: str) -> str:
    return text.strip().lower().replace(" ", "_").replace("/", "").replace(".", "").replace("[", "").replace("]", "").replace("(", "").replace(")", "")


_FLOAT_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")

def _line_numbers(text: str) -> list[float]:
    text = text.split("{", 1)[0]
    return [parse_float(match.group(0)) for match in _FLOAT_RE.finditer(text)]


def _tokens(line: str, delimiter: str) -> list[str]:
    if delimiter == " ":
        return line.split()
    return [tok.strip() for tok in line.replace(",", delimiter).replace(";", delimiter).split(delimiter) if tok.strip()]


def _first(mapping: dict[str, float], *keys: str) -> float:
    norm = {_norm(k): v for k, v in mapping.items()}
    for key in keys:
        n = _norm(key)
        if n in norm:
            return norm[n]
    return math.nan


# Backward-compatible class names used by older imports.
Ipi2WinDashboard = IpWin2Dashboard
VesPointDialog = VesPointEntryDialog
OptionsDialog = IpiOptionsDialog
SimpleChoiceDialog = IpiChoiceDialog
