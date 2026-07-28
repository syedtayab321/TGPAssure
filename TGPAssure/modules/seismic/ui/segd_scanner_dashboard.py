from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from modules.seismic.segd_scanner import (
    DEFAULT_SUMMARY_FIELDS,
    FILE_HEADER_FIELDS,
    SELECTABLE_FIELDS,
    SegdHeaderScanner,
    SegdScanResult,
)


_QSS = """
QWidget#segdScannerDashboard {
    background:#F3F6F9;
    color:#143044;
    font-size:8.6pt;
}
QFrame#scannerHeader {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #1D3148, stop:0.48 #0B6E9E, stop:1 #0787C5);
    border-radius:9px;
}
QFrame#scannerTitleBlock {
    background:rgba(10, 31, 52, 0.42);
    border:1px solid rgba(255,255,255,0.16);
    border-radius:7px;
}
QLabel#scTitle {
    background:transparent;
    border:0px;
    color:#FFFFFF;
    font-size:13px;
    font-weight:900;
    padding:0px;
}
QLabel#scSub {
    background:transparent;
    border:0px;
    color:#D9F4FF;
    font-size:8.1pt;
    padding:0px;
}
QLabel#scMetric {
    background:#FFFFFF;
    border:1px solid #D5E2EB;
    border-radius:7px;
    padding:5px 9px;
    font-size:8.5pt;
    font-weight:900;
    color:#17364B;
}
QFrame#sideNav {
    background:#FFFFFF;
    border:1px solid #D6E2EB;
    border-radius:8px;
}
QLabel#sideNavTitle {
    color:#547084;
    font-size:7.6pt;
    font-weight:900;
    letter-spacing:0.5px;
    padding:4px 7px 2px 7px;
}
QPushButton#navButton {
    background:transparent;
    color:#1E3C52;
    border:0px;
    border-radius:6px;
    min-height:25px;
    padding:3px 8px;
    text-align:left;
    font-size:8.4pt;
    font-weight:800;
}
QPushButton#navButton:hover {
    background:#EFF6FA;
    color:#075C84;
}
QPushButton#navButton:checked {
    background:#0787C5;
    color:#FFFFFF;
}
QFrame#contentCard {
    background:#FFFFFF;
    border:1px solid #D5E1EA;
    border-radius:8px;
}
QLabel#sectionTitle {
    background:transparent;
    color:#17364B;
    font-size:10pt;
    font-weight:900;
    padding:0px;
}
QLabel#muted {
    background:transparent;
    color:#607889;
    font-size:8pt;
}
QLabel#selectedCount {
    background:#E8F4FA;
    border:1px solid #B9DCEB;
    border-radius:6px;
    color:#075C84;
    font-weight:800;
    padding:4px 7px;
    font-size:8pt;
}
QFrame#card {
    background:#FFFFFF;
    border:1px solid #D8E3EB;
    border-radius:8px;
}
QGroupBox {
    background:#FFFFFF;
    border:1px solid #D8E3EB;
    border-radius:7px;
    margin-top:10px;
    padding-top:8px;
    font-size:8.4pt;
    font-weight:800;
}
QGroupBox::title {
    subcontrol-origin:margin;
    left:8px;
    padding:0 4px;
    color:#17364B;
}
QCheckBox {
    min-height:19px;
    font-size:8.1pt;
    color:#1E3443;
    spacing:5px;
}
QCheckBox::indicator { width:13px; height:13px; }
QPushButton {
    min-height:25px;
    padding:2px 10px;
    border:1px solid #9FB1BE;
    border-radius:6px;
    background:#F8FAFC;
    color:#17364B;
    font-weight:800;
    font-size:8.5pt;
}
QPushButton:hover { background:#EAF2F7; border-color:#6F91A6; }
QPushButton:disabled { color:#8B9AA4; background:#EEF2F5; border-color:#D6DEE4; }
QPushButton#primary { background:#0787C5; border-color:#0473A9; color:#FFFFFF; }
QPushButton#primary:hover { background:#087AB0; }
QPushButton#green { background:#188C5A; border-color:#147449; color:#FFFFFF; }
QPushButton#green:hover { background:#167A50; }
QPushButton#danger { background:#D96728; border-color:#B95018; color:#FFFFFF; }
QLineEdit {
    min-height:25px;
    border:1px solid #B7C6D1;
    border-radius:5px;
    background:#FFFFFF;
    padding:2px 6px;
    font-size:8.4pt;
}
QStackedWidget {
    background:transparent;
    border:0px;
}
QTabWidget::pane {
    border:1px solid #D5E1EA;
    background:#FFFFFF;
    border-radius:5px;
    top:-1px;
}
QTabBar::tab {
    background:#EAF0F4;
    color:#3D5668;
    border:1px solid #D4DFE7;
    border-bottom:none;
    padding:5px 10px;
    min-width:76px;
    font-size:8.3pt;
}
QTabBar::tab:selected {
    background:#FFFFFF;
    color:#0B658F;
    font-weight:900;
}
QTabBar::tab:hover { background:#F7FAFC; }
QTableWidget {
    background:#FFFFFF;
    alternate-background-color:#F7FAFC;
    border:1px solid #D7E2EA;
    gridline-color:#E5EDF2;
    font-size:8.2pt;
    selection-background-color:#D8ECF7;
    selection-color:#102A3D;
}
QHeaderView::section {
    background:#E5EFF5;
    color:#24485F;
    border:0;
    border-right:1px solid #D4E0E8;
    border-bottom:1px solid #CBD9E2;
    padding:5px 6px;
    font-size:8.2pt;
    font-weight:900;
}
QPlainTextEdit {
    background:#FFFFFF;
    border:1px solid #D7E2EA;
    border-radius:4px;
    font-family:Consolas, monospace;
    font-size:8.2pt;
    padding:5px;
}
QScrollArea { border:0; background:transparent; }
"""


# The result grid intentionally excludes the long free-text details field.  Long
# text is displayed on the dedicated Record Details tab instead of forcing rows
# to expand and making the result table unreadable.
_RESULT_TABLE_FIELDS: tuple[tuple[str, str], ...] = tuple(
    item for item in DEFAULT_SUMMARY_FIELDS if item[0] != "details"
)

_FIELD_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Position & Geometry",
        ("serial_number", "line", "point", "northing", "easting", "elevation", "channel_type"),
    ),
    (
        "Unit & Channel",
        (
            "control_unit_type",
            "control_unit_sn",
            "assembly_sn",
            "assembly_location",
            "fdu_unit_type",
            "channel_set",
            "gain_code",
            "filter_type",
        ),
    ),
    (
        "Trace & Edit",
        (
            "edited",
            "overscale",
            "number_of_interpolation",
            "conversion_factor",
            "trace_max_value",
            "sensor_type",
            "trace_channel_type",
        ),
    ),
    (
        "Receiver QC",
        (
            "resistance",
            "capacitance",
            "leakage",
            "tilt",
            "resistance_error",
            "capacitance_error",
            "leakage_error",
            "tilt_error",
            "resistance_limits",
            "capacitance_limits",
            "leakage_limits",
            "tilt_limits",
        ),
    ),
)


class SegdScannerDashboard(QWidget):
    """Responsive 408/428 header scanner with separated workflow tabs."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("segdScannerDashboard")
        self.setProperty("module_id", "segd_scanner")
        self.setStyleSheet(_QSS)

        self.results: list[SegdScanResult] = []
        self.scanner = SegdHeaderScanner()
        self.field_checks: dict[str, QCheckBox] = {}
        self.header_checks: dict[str, QCheckBox] = {}
        self._current_result_index = -1
        self._building_tables = False

        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(7)

        root.addWidget(self._build_header())
        root.addLayout(self._build_metrics())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(8)
        root.addLayout(body, 1)

        self.pages = QStackedWidget()
        self.tabs = self.pages  # Backwards-compatible alias for ribbon hooks.
        self.scan_tab_index = self.pages.addWidget(self._wrap_content(self._build_scan_tab()))
        self.fields_tab_index = self.pages.addWidget(self._wrap_content(self._build_field_selection_tab()))
        self.results_tab_index = self.pages.addWidget(self._wrap_content(self._build_results_tab()))
        self.output_tab_index = self.pages.addWidget(self._wrap_content(self._build_output_tab()))
        self.details_tab_index = self.pages.addWidget(self._wrap_content(self._build_details_tab()))
        self.guide_tab_index = self.pages.addWidget(self._wrap_content(self._build_guide_tab()))

        body.addWidget(self._build_sidebar(), 0)
        body.addWidget(self.pages, 1)

        self._show_page(self.scan_tab_index)
        self._update_selected_count()
        self._update_action_state()

    def _wrap_content(self, widget: QWidget) -> QWidget:
        container = QFrame()
        container.setObjectName("contentCard")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(0)
        layout.addWidget(widget)
        return container

    def _build_sidebar(self) -> QWidget:
        nav = QFrame()
        nav.setObjectName("sideNav")
        nav.setMinimumWidth(135)
        nav.setMaximumWidth(158)
        layout = QVBoxLayout(nav)
        layout.setContentsMargins(7, 8, 7, 8)
        layout.setSpacing(4)

        title = QLabel("HEADER SCANNER")
        title.setObjectName("sideNavTitle")
        layout.addWidget(title)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: dict[int, QPushButton] = {}
        nav_items = (
            (self.scan_tab_index, "Scan / Export"),
            (self.fields_tab_index, "Field Selection"),
            (self.results_tab_index, "Results"),
            (self.output_tab_index, "Selected Output"),
            (self.details_tab_index, "Record Details"),
            (self.guide_tab_index, "Guide"),
        )
        for index, label in nav_items:
            button = QPushButton(label)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, page_index=index: self._show_page(page_index))
            self.nav_group.addButton(button)
            self.nav_buttons[index] = button
            layout.addWidget(button)

        layout.addStretch(1)
        return nav

    def _show_page(self, index: int) -> None:
        if hasattr(self, "pages"):
            self.pages.setCurrentIndex(index)
        if hasattr(self, "nav_buttons") and index in self.nav_buttons:
            self.nav_buttons[index].setChecked(True)

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("scannerHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        title_block = QFrame()
        title_block.setObjectName("scannerTitleBlock")
        title_layout = QVBoxLayout(title_block)
        title_layout.setContentsMargins(10, 6, 10, 6)
        title_layout.setSpacing(1)

        title = QLabel("408 / 428 Header Scanner")
        title.setObjectName("scTitle")
        title.setAutoFillBackground(False)
        title.setStyleSheet("background: transparent; color: #FFFFFF;")
        subtitle = QLabel(
            "Scan SEG-D records, select fields, inspect each record, and export a controlled header audit."
        )
        subtitle.setObjectName("scSub")
        subtitle.setAutoFillBackground(False)
        subtitle.setStyleSheet("background: transparent; color: #D9F4FF;")
        subtitle.setWordWrap(True)
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        layout.addWidget(title_block, 1)

        open_file = QPushButton("Scan File")
        open_file.setObjectName("primary")
        open_file.clicked.connect(self.scan_file)
        layout.addWidget(open_file)

        open_folder = QPushButton("Scan Folder")
        open_folder.setObjectName("green")
        open_folder.clicked.connect(self.scan_folder)
        layout.addWidget(open_folder)

        self.header_export_button = QPushButton("Export")
        self.header_export_button.clicked.connect(self.export_selected)
        layout.addWidget(self.header_export_button)
        return header

    def _build_metrics(self) -> QHBoxLayout:
        metrics = QHBoxLayout()
        metrics.setSpacing(8)
        self.metric_labels: dict[str, QLabel] = {}
        for key, label in (
            ("files", "Files: 0"),
            ("pass", "PASS: 0"),
            ("review", "REVIEW/WARN: 0"),
            ("fail", "FAIL: 0"),
        ):
            widget = QLabel(label)
            widget.setObjectName("scMetric")
            widget.setAlignment(Qt.AlignCenter)
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.metric_labels[key] = widget
            metrics.addWidget(widget)
        return metrics

    def _build_scan_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        workflow_card = QFrame()
        workflow_card.setObjectName("card")
        workflow = QVBoxLayout(workflow_card)
        workflow.setContentsMargins(11, 9, 11, 9)
        workflow.setSpacing(6)

        title = QLabel("1. Select the scan source")
        title.setObjectName("sectionTitle")
        workflow.addWidget(title)
        note = QLabel(
            "Scan one SEG-D/408/428 record or a folder. After decoding, the dashboard opens the Results tab automatically."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        workflow.addWidget(note)

        scan_buttons = QHBoxLayout()
        scan_file = QPushButton("Scan One File")
        scan_file.setObjectName("primary")
        scan_file.clicked.connect(self.scan_file)
        scan_folder = QPushButton("Scan Complete Folder")
        scan_folder.setObjectName("green")
        scan_folder.clicked.connect(self.scan_folder)
        scan_buttons.addWidget(scan_file)
        scan_buttons.addWidget(scan_folder)
        scan_buttons.addStretch(1)
        workflow.addLayout(scan_buttons)
        layout.addWidget(workflow_card)

        export_card = QFrame()
        export_card.setObjectName("card")
        export_layout = QVBoxLayout(export_card)
        export_layout.setContentsMargins(11, 9, 11, 9)
        export_layout.setSpacing(6)

        export_title = QLabel("2. Configure the export")
        export_title.setObjectName("sectionTitle")
        export_layout.addWidget(export_title)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Output file"))
        self.output_name = QLineEdit()
        self.output_name.setPlaceholderText("Example: 428_header_scan.txt or 428_header_scan.csv")
        path_row.addWidget(self.output_name, 1)
        browse = QPushButton("Browse")
        browse.clicked.connect(self.choose_output_file)
        path_row.addWidget(browse)
        export_layout.addLayout(path_row)

        options_row = QHBoxLayout()
        self.display_notepad_check = QCheckBox("Open TXT output in Notepad after export")
        options_row.addWidget(self.display_notepad_check)
        options_row.addStretch(1)
        export_layout.addLayout(options_row)

        buttons = QHBoxLayout()
        self.export_txt_button = QPushButton("Export TXT")
        self.export_txt_button.setObjectName("primary")
        self.export_txt_button.clicked.connect(lambda: self.export_selected("txt"))
        self.export_csv_button = QPushButton("Export CSV")
        self.export_csv_button.setObjectName("green")
        self.export_csv_button.clicked.connect(lambda: self.export_selected("csv"))
        buttons.addWidget(self.export_txt_button)
        buttons.addWidget(self.export_csv_button)
        buttons.addStretch(1)
        export_layout.addLayout(buttons)
        layout.addWidget(export_card)

        state_card = QFrame()
        state_card.setObjectName("card")
        state_layout = QVBoxLayout(state_card)
        state_layout.setContentsMargins(11, 9, 11, 9)
        state_layout.setSpacing(4)
        state_title = QLabel("Workflow status")
        state_title.setObjectName("sectionTitle")
        state_layout.addWidget(state_title)
        self.workflow_status = QLabel("No scan loaded. Select fields before or after scanning.")
        self.workflow_status.setObjectName("muted")
        self.workflow_status.setWordWrap(True)
        state_layout.addWidget(self.workflow_status)
        layout.addWidget(state_card)
        layout.addStretch(1)
        return page

    def _build_field_selection_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        bar = QHBoxLayout()
        intro = QLabel("Choose the fields included in Selected Output and exported TXT/CSV files.")
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        bar.addWidget(intro, 1)
        self.selected_count_label = QLabel()
        self.selected_count_label.setObjectName("selectedCount")
        bar.addWidget(self.selected_count_label)
        outer.addLayout(bar)

        self.field_tabs = QTabWidget()
        self.field_tabs.setDocumentMode(True)
        outer.addWidget(self.field_tabs, 1)

        label_map = dict(SELECTABLE_FIELDS)
        assigned: set[str] = set()
        for title, keys in _FIELD_GROUPS:
            assigned.update(keys)
            self.field_tabs.addTab(self._make_checkbox_page(keys, label_map), title)

        extra_keys = tuple(key for key, _ in SELECTABLE_FIELDS if key not in assigned)
        if extra_keys:
            self.field_tabs.addTab(self._make_checkbox_page(extra_keys, label_map), "Other Fields")

        header_label_map = dict(FILE_HEADER_FIELDS)
        header_page = self._make_checkbox_page(
            tuple(key for key, _ in FILE_HEADER_FIELDS),
            header_label_map,
            header_fields=True,
        )
        self.field_tabs.addTab(header_page, "Header Blocks")

        controls = QHBoxLayout()
        all_button = QPushButton("Select All")
        all_button.clicked.connect(self.select_all_fields)
        none_button = QPushButton("Clear All")
        none_button.clicked.connect(self.select_no_fields)
        defaults_button = QPushButton("Recommended Fields")
        defaults_button.clicked.connect(self.select_recommended_fields)
        controls.addWidget(all_button)
        controls.addWidget(none_button)
        controls.addWidget(defaults_button)
        controls.addStretch(1)
        outer.addLayout(controls)
        return page

    def _make_checkbox_page(
        self,
        keys: tuple[str, ...],
        label_map: dict[str, str],
        *,
        header_fields: bool = False,
    ) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(6, 6, 6, 6)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        panel = QWidget()
        grid = QGridLayout(panel)
        grid.setContentsMargins(10, 10, 10, 10)
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(8)
        column_count = 3 if len(keys) > 10 else 2
        for column in range(column_count):
            grid.setColumnStretch(column, 1)

        target = self.header_checks if header_fields else self.field_checks
        for index, key in enumerate(keys):
            check = QCheckBox(label_map.get(key, key.replace("_", " ").title()))
            check.setChecked(False)
            check.toggled.connect(self._on_field_selection_changed)
            target[key] = check
            grid.addWidget(check, index // column_count, index % column_count)
        grid.setRowStretch((len(keys) + column_count - 1) // column_count, 1)
        scroll.setWidget(panel)
        return page

    def _build_results_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        top = QHBoxLayout()
        label = QLabel("Scan results")
        label.setObjectName("sectionTitle")
        top.addWidget(label)
        self.result_hint = QLabel("Select a row to inspect all decoded fields and header blocks.")
        self.result_hint.setObjectName("muted")
        top.addWidget(self.result_hint)
        top.addStretch(1)
        details_button = QPushButton("Open Record Details")
        details_button.clicked.connect(self._open_current_details)
        top.addWidget(details_button)
        layout.addLayout(top)

        self.results_table = QTableWidget(0, len(_RESULT_TABLE_FIELDS))
        self.results_table.setHorizontalHeaderLabels([label for _, label in _RESULT_TABLE_FIELDS])
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.results_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.results_table.setWordWrap(False)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.verticalHeader().setDefaultSectionSize(28)
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.results_table.horizontalHeader().setMinimumSectionSize(68)
        self.results_table.horizontalHeader().setDefaultSectionSize(115)
        self.results_table.horizontalHeader().setStretchLastSection(False)
        self.results_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.results_table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.results_table.itemSelectionChanged.connect(self._result_selection_changed)
        self.results_table.itemDoubleClicked.connect(lambda *_: self._open_current_details())
        layout.addWidget(self.results_table, 1)

        self._configure_result_column_widths()
        return page

    def _build_output_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        top = QHBoxLayout()
        label = QLabel("Selected output fields")
        label.setObjectName("sectionTitle")
        top.addWidget(label)
        hint = QLabel("Summary columns are always retained; selected 408/428 fields are appended.")
        hint.setObjectName("muted")
        top.addWidget(hint)
        top.addStretch(1)
        fields_button = QPushButton("Edit Field Selection")
        fields_button.clicked.connect(lambda: self._show_page(self.fields_tab_index))
        top.addWidget(fields_button)
        layout.addLayout(top)

        self.output_views = QTabWidget()
        self.output_views.setDocumentMode(True)
        layout.addWidget(self.output_views, 1)

        table_page = QWidget()
        table_layout = QVBoxLayout(table_page)
        table_layout.setContentsMargins(4, 4, 4, 4)
        self.table = QTableWidget(0, 1)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setMinimumSectionSize(72)
        self.table.horizontalHeader().setDefaultSectionSize(130)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.itemSelectionChanged.connect(self._output_selection_changed)
        table_layout.addWidget(self.table)
        self.output_views.addTab(table_page, "Table")

        preview_page = QWidget()
        preview_layout = QVBoxLayout(preview_page)
        preview_layout.setContentsMargins(4, 4, 4, 4)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        preview_layout.addWidget(self.preview)
        self.output_views.addTab(preview_page, "Text Preview")
        return page

    def _build_details_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        top = QHBoxLayout()
        self.detail_title = QLabel("No record selected")
        self.detail_title.setObjectName("sectionTitle")
        top.addWidget(self.detail_title)
        top.addStretch(1)
        previous_button = QPushButton("Previous")
        previous_button.clicked.connect(lambda: self._move_record(-1))
        next_button = QPushButton("Next")
        next_button.clicked.connect(lambda: self._move_record(1))
        top.addWidget(previous_button)
        top.addWidget(next_button)
        layout.addLayout(top)

        self.detail_views = QTabWidget()
        self.detail_views.setDocumentMode(True)
        layout.addWidget(self.detail_views, 1)

        properties_page = QWidget()
        properties_layout = QVBoxLayout(properties_page)
        properties_layout.setContentsMargins(4, 4, 4, 4)
        self.details_table = QTableWidget(0, 2)
        self.details_table.setHorizontalHeaderLabels(["Property", "Value"])
        self.details_table.setAlternatingRowColors(True)
        self.details_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.details_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.details_table.setWordWrap(True)
        self.details_table.verticalHeader().setVisible(False)
        self.details_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.details_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        properties_layout.addWidget(self.details_table)
        self.detail_views.addTab(properties_page, "Decoded Properties")

        self.header_text_views: dict[str, QPlainTextEdit] = {}
        for key, label in FILE_HEADER_FIELDS:
            editor = QPlainTextEdit()
            editor.setReadOnly(True)
            editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
            self.header_text_views[key] = editor
            self.detail_views.addTab(editor, label)

        details_editor = QPlainTextEdit()
        details_editor.setReadOnly(True)
        details_editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.record_notes = details_editor
        self.detail_views.addTab(details_editor, "Scanner Notes")
        return page

    def _build_guide_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("Header scanner workflow")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        guide = QLabel(
            "1. Use Scan File or Scan Folder.\n\n"
            "2. Open Field Selection and choose geometry, unit/channel, trace/edit, receiver-QC, and header-block fields.\n\n"
            "3. Use Results for a compact file-level QC summary. Long details are deliberately moved out of the table.\n\n"
            "4. Use Selected Output to inspect the exact columns that will be exported.\n\n"
            "5. Use Record Details to inspect decoded properties and each header block without crowding the results grid.\n\n"
            "Native SEG-D records are decoded with the internal reader. Unsupported vendor variations remain visible as fallback scan records rather than being silently omitted."
        )
        guide.setWordWrap(True)
        guide.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        layout.addWidget(guide)
        layout.addStretch(1)
        return page

    # ---------------------------------------------------------- field state
    def selected_fields(self) -> list[str]:
        header_keys = [key for key, check in self.header_checks.items() if check.isChecked()]
        field_keys = [key for key, check in self.field_checks.items() if check.isChecked()]
        return SegdHeaderScanner.selected_field_keys(True, header_keys, field_keys)

    def select_all_fields(self) -> None:
        for check in list(self.field_checks.values()) + list(self.header_checks.values()):
            check.blockSignals(True)
            check.setChecked(True)
            check.blockSignals(False)
        self._on_field_selection_changed()

    def select_no_fields(self) -> None:
        for check in list(self.field_checks.values()) + list(self.header_checks.values()):
            check.blockSignals(True)
            check.setChecked(False)
            check.blockSignals(False)
        self._on_field_selection_changed()

    def select_recommended_fields(self) -> None:
        recommended = {
            "serial_number",
            "line",
            "point",
            "northing",
            "easting",
            "elevation",
            "channel_type",
            "channel_set",
            "sensor_type",
            "resistance",
            "capacitance",
            "leakage",
            "tilt",
            "general_headers",
            "channel_set_header",
        }
        for key, check in {**self.field_checks, **self.header_checks}.items():
            check.blockSignals(True)
            check.setChecked(key in recommended)
            check.blockSignals(False)
        self._on_field_selection_changed()

    def _on_field_selection_changed(self, *_args) -> None:
        self._update_selected_count()
        self._populate_selected_output()
        self._refresh_preview()
        self._populate_detail_record(self._current_result_index)

    def _update_selected_count(self) -> None:
        count = sum(check.isChecked() for check in self.field_checks.values())
        headers = sum(check.isChecked() for check in self.header_checks.values())
        if hasattr(self, "selected_count_label"):
            self.selected_count_label.setText(f"Selected: {count} fields + {headers} header blocks")

    # -------------------------------------------------------------- scanning
    def choose_output_file(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Output file name",
            "428_header_scan.txt",
            "Text (*.txt);;CSV (*.csv)",
        )
        if path:
            self.output_name.setText(path)

    def scan_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Scan SEG-D/408/428 file",
            str(Path.home()),
            "SEG-D/Field Records (*.segd *.sgd *.d *.dat *.bin *.raw *.000);;All files (*.*)",
        )
        if path:
            self._scan(path)

    def scan_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Scan SEG-D/408/428 folder",
            str(Path.home()),
        )
        if path:
            self._scan(path)

    def _scan(self, path: str) -> None:
        try:
            self.workflow_status.setText(f"Scanning: {path}")
            self.results = self.scanner.scan_path(path)
            if not self.output_name.text().strip():
                source = Path(path)
                stem = source.stem if source.is_file() else source.name
                self.output_name.setText(str(Path.home() / f"{stem}_428_header_scan.txt"))

            self._populate()
            self._refresh_preview()
            self._update_action_state()

            source_label = "file" if Path(path).is_file() else "folder"
            self.workflow_status.setText(
                f"Loaded {len(self.results):,} record(s) from the selected {source_label}. "
                "Review Results, then inspect Record Details or export Selected Output."
            )
            self._show_page(self.results_tab_index)
        except Exception as exc:
            self.workflow_status.setText("Scan failed. Review the error and select another source.")
            QMessageBox.critical(self, "408/428 Header Scanner", str(exc))

    # --------------------------------------------------------------- tables
    def _populate(self) -> None:
        self._building_tables = True
        try:
            self._populate_results_table()
            self._populate_selected_output()
            self._update_metrics()
        finally:
            self._building_tables = False

        if self.results:
            self._select_result_index(0)
        else:
            self._current_result_index = -1
            self._populate_detail_record(-1)

    def _populate_results_table(self) -> None:
        self.results_table.setRowCount(len(self.results))
        for row, result in enumerate(self.results):
            values = result.to_dict()
            for column, (key, _label) in enumerate(_RESULT_TABLE_FIELDS):
                item = QTableWidgetItem(self._display_value(values.get(key, "")))
                if key in {"size_bytes", "sample_count", "trace_count", "channel_sets", "warning_count"}:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                elif key == "status":
                    item.setTextAlignment(Qt.AlignCenter)
                self.results_table.setItem(row, column, item)
        self._configure_result_column_widths()

    def _configure_result_column_widths(self) -> None:
        if not hasattr(self, "results_table"):
            return
        widths = {
            "status": 82,
            "file_name": 220,
            "size_bytes": 105,
            "format_code": 90,
            "manufacturer": 165,
            "sample_interval_ms": 90,
            "sample_count": 100,
            "trace_count": 100,
            "channel_sets": 85,
            "warning_count": 90,
        }
        for column, (key, _label) in enumerate(_RESULT_TABLE_FIELDS):
            self.results_table.setColumnWidth(column, widths.get(key, 115))

    def _populate_selected_output(self) -> None:
        if not hasattr(self, "table"):
            return
        keys = self.selected_fields()
        labels = SegdHeaderScanner.field_labels(keys)
        self.table.setColumnCount(len(keys))
        self.table.setHorizontalHeaderLabels(labels)
        self.table.setRowCount(len(self.results))

        for row, result in enumerate(self.results):
            values = result.to_dict()
            for column, key in enumerate(keys):
                item = QTableWidgetItem(self._display_value(values.get(key, "")))
                self.table.setItem(row, column, item)

        for column, key in enumerate(keys):
            if key == "file_name":
                self.table.setColumnWidth(column, 210)
            elif key in {"details", "general_headers", "channel_set_header", "extended_header", "external_header"}:
                self.table.setColumnWidth(column, 300)
            elif key in {"status", "format_code", "sample_interval_ms", "warning_count"}:
                self.table.setColumnWidth(column, 95)
            else:
                self.table.setColumnWidth(column, 130)

        if self.results and 0 <= self._current_result_index < len(self.results):
            self.table.selectRow(self._current_result_index)

    def _update_metrics(self) -> None:
        total = len(self.results)
        passed = sum(1 for result in self.results if result.status == "PASS")
        failed = sum(1 for result in self.results if result.status == "FAIL")
        review = total - passed - failed
        self.metric_labels["files"].setText(f"Files: {total:,}")
        self.metric_labels["pass"].setText(f"PASS: {passed:,}")
        self.metric_labels["review"].setText(f"REVIEW/WARN: {review:,}")
        self.metric_labels["fail"].setText(f"FAIL: {failed:,}")

    def _result_selection_changed(self) -> None:
        if self._building_tables:
            return
        row = self.results_table.currentRow()
        if row >= 0:
            self._select_result_index(row, source="results")

    def _output_selection_changed(self) -> None:
        if self._building_tables:
            return
        row = self.table.currentRow()
        if row >= 0:
            self._select_result_index(row, source="output")

    def _select_result_index(self, index: int, source: str | None = None) -> None:
        if not (0 <= index < len(self.results)):
            return
        self._current_result_index = index

        if source != "results":
            self.results_table.blockSignals(True)
            self.results_table.selectRow(index)
            self.results_table.blockSignals(False)
        if source != "output" and self.table.rowCount() > index:
            self.table.blockSignals(True)
            self.table.selectRow(index)
            self.table.blockSignals(False)

        self._populate_detail_record(index)
        self._refresh_preview()

    def _populate_detail_record(self, index: int) -> None:
        if not hasattr(self, "details_table"):
            return
        if not (0 <= index < len(self.results)):
            self.detail_title.setText("No record selected")
            self.details_table.setRowCount(0)
            for editor in self.header_text_views.values():
                editor.clear()
            self.record_notes.clear()
            return

        result = self.results[index]
        values = result.to_dict()
        selected = self.selected_fields()

        # Show the complete summary plus selected output fields, without repeating
        # long header text in the property grid.
        detail_keys: list[str] = [key for key, _ in DEFAULT_SUMMARY_FIELDS if key != "details"]
        for key in selected:
            if key not in detail_keys and key not in self.header_text_views:
                detail_keys.append(key)

        labels = dict(DEFAULT_SUMMARY_FIELDS + SELECTABLE_FIELDS + FILE_HEADER_FIELDS)
        self.details_table.setRowCount(len(detail_keys))
        for row, key in enumerate(detail_keys):
            property_item = QTableWidgetItem(labels.get(key, key.replace("_", " ").title()))
            value_item = QTableWidgetItem(self._display_value(values.get(key, "")))
            property_item.setFlags(property_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            value_item.setFlags(value_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.details_table.setItem(row, 0, property_item)
            self.details_table.setItem(row, 1, value_item)
        self.details_table.resizeRowsToContents()

        self.detail_title.setText(
            f"Record {index + 1:,} of {len(self.results):,}: {result.file_name} [{result.status}]"
        )
        for key, editor in self.header_text_views.items():
            text = self._display_value(values.get(key, ""))
            editor.setPlainText(text or "No decoded content is available for this header block.")
        self.record_notes.setPlainText(result.details or "No scanner notes are available.")

    def _refresh_preview(self) -> None:
        if not hasattr(self, "preview"):
            return
        keys = self.selected_fields()
        labels = SegdHeaderScanner.field_labels(keys)
        rows: list[str] = []

        preview_results = self.results
        if 0 <= self._current_result_index < len(self.results):
            preview_results = [self.results[self._current_result_index]]
        else:
            preview_results = self.results[:3]

        for result in preview_results:
            data = result.to_dict()
            rows.append("=" * 92)
            rows.append(f"{result.file_name} [{result.status}]")
            rows.append("-" * 92)
            for key, label in zip(keys, labels):
                rows.append(f"{label:28s}: {self._display_value(data.get(key, ''))}")
            rows.append("")

        if not rows:
            rows = [
                "No scan loaded.",
                "Use Scan File or Scan Folder, then choose fields on the Field Selection tab.",
            ]
        self.preview.setPlainText("\n".join(rows))

    @staticmethod
    def _display_value(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, float):
            return f"{value:g}"
        return str(value)

    # --------------------------------------------------------------- details
    def _open_current_details(self) -> None:
        if not self.results:
            QMessageBox.information(self, "408/428 Header Scanner", "Run a scan before opening record details.")
            return
        if self._current_result_index < 0:
            self._select_result_index(0)
        self._show_page(self.details_tab_index)

    def _move_record(self, step: int) -> None:
        if not self.results:
            return
        current = self._current_result_index if self._current_result_index >= 0 else 0
        target = max(0, min(len(self.results) - 1, current + step))
        self._select_result_index(target)

    # --------------------------------------------------------------- export
    def export_selected(self, mode: str | None = None) -> None:
        if not self.results:
            QMessageBox.information(self, "408/428 Header Scanner", "Run a scan before export.")
            return

        keys = self.selected_fields()
        path_text = self.output_name.text().strip()
        if not path_text:
            suffix = "csv" if mode == "csv" else "txt"
            path_text, _ = QFileDialog.getSaveFileName(
                self,
                "Export 408/428 scan",
                f"428_header_scan.{suffix}",
                "Text (*.txt);;CSV (*.csv)",
            )
            if not path_text:
                return

        path = Path(path_text)
        if mode is None:
            mode = "csv" if path.suffix.lower() == ".csv" else "txt"
        if not path.suffix:
            path = path.with_suffix(".csv" if mode == "csv" else ".txt")

        try:
            if mode == "csv":
                self.scanner.export_csv(self.results, path, keys)
            else:
                self.scanner.export_txt(self.results, path, keys)
            self.output_name.setText(str(path))
            if self.display_notepad_check.isChecked() and mode != "csv":
                self._open_in_notepad(path)
            QMessageBox.information(self, "408/428 Header Scanner", f"Exported:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "408/428 Header Scanner", f"Export failed:\n{exc}")

    def _open_in_notepad(self, path: Path) -> None:
        try:
            if os.name == "nt":
                subprocess.Popen(["notepad.exe", str(path)], close_fds=True)
        except Exception:
            # Export remains successful even if the optional Notepad launch fails.
            pass

    def export_csv(self) -> None:
        self.export_selected("csv")

    # ---------------------------------------------------------- ribbon hooks
    def show_results(self) -> None:
        self._show_page(self.results_tab_index)

    def show_guide(self) -> None:
        self._show_page(self.guide_tab_index)

    def can_execute(self, action_id: str) -> bool:
        if action_id in {"segd_scanner_open", "segd_scanner_folder"}:
            return True
        if action_id == "segd_scanner_export":
            return bool(self.results)
        return True

    def _update_action_state(self) -> None:
        enabled = bool(self.results)
        if hasattr(self, "header_export_button"):
            self.header_export_button.setEnabled(enabled)
        if hasattr(self, "export_txt_button"):
            self.export_txt_button.setEnabled(enabled)
        if hasattr(self, "export_csv_button"):
            self.export_csv_button.setEnabled(enabled)
