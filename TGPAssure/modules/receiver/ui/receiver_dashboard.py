from __future__ import annotations

import csv
from pathlib import Path
from statistics import mean
from typing import Iterable

import numpy as np
import pyqtgraph as pg

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QDoubleSpinBox,
)

from modules.receiver import ReceiverQcEngine, ReceiverQcLimits, ReceiverQcResult, SmtReader, SmtRecord

_STATUS_STYLE = {
    "PASS": ("#166534", "#DCFCE7"),
    "WARN": ("#92400E", "#FEF3C7"),
    "FAIL": ("#991B1B", "#FEE2E2"),
    "LOADED": ("#075985", "#E0F2FE"),
}

_QSS = """
QWidget#receiverQcDashboard { background:#F4F7FA; color:#102A3D; font-size:8.1pt; }
QFrame#rxHeader { background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #123554, stop:0.55 #0B74A7, stop:1 #0A96C7); border-radius:9px; }
QFrame#rxHeader QLabel { background:transparent; }
QFrame#rxHeaderTextPanel { background:#07304A; border:1px solid rgba(255,255,255,0.28); border-radius:7px; }
QLabel#rxTitle { background:transparent; color:#FFFFFF; font-size:12.5px; font-weight:900; }
QLabel#rxSub { background:transparent; color:#BFEAFF; font-size:7.7pt; font-weight:700; }
QLabel#rxFileBadge { color:#0B3147; background:#E7F5FE; border:1px solid rgba(255,255,255,0.35); border-radius:8px; padding:4px 8px; font-weight:900; }
QFrame#rxSidebar { background:#FFFFFF; border:1px solid #D6E2EB; border-radius:8px; }
QLabel#rxSideTitle { color:#536F83; font-size:7.5pt; font-weight:900; letter-spacing:.6px; padding:5px 7px 2px 7px; }
QPushButton#navButton { background:transparent; color:#1E3C52; border:0; border-radius:6px; min-height:28px; padding:4px 9px; text-align:left; font-size:8.0pt; font-weight:800; }
QPushButton#navButton:hover { background:#EFF6FA; color:#075C84; }
QPushButton#navButton:checked { background:#0A86C7; color:#FFFFFF; }
QFrame#contentPanel { background:#FFFFFF; border:1px solid #D5E1EA; border-radius:8px; }
QFrame#metricCard { background:#FFFFFF; border:1px solid #D6E2EB; border-left:4px solid #0A86C7; border-radius:8px; }
QFrame#metricCard[accent="green"] { border-left-color:#15945C; }
QFrame#metricCard[accent="orange"] { border-left-color:#D97706; }
QFrame#metricCard[accent="red"] { border-left-color:#C2414A; }
QFrame#metricCard[accent="purple"] { border-left-color:#7C5AC7; }
QLabel#metricTitle { color:#607889; font-size:7.6pt; font-weight:800; }
QLabel#metricValue { color:#15384F; font-size:11.5pt; font-weight:900; }
QGroupBox { background:#FFFFFF; border:1px solid #D4DEE8; border-radius:7px; margin-top:8px; padding-top:10px; font-weight:900; color:#15384F; }
QGroupBox::title { subcontrol-origin: margin; left:8px; padding:0 4px; background:#FFFFFF; }
QLabel#sectionHint { color:#657B8D; font-size:7.8pt; }
QPushButton { min-height:24px; padding:2px 10px; border:1px solid #B8C7D3; border-radius:6px; background:#F7FAFC; font-weight:800; }
QPushButton:hover { background:#EEF6FB; }
QPushButton#primary { background:#0A86C7; border-color:#0873AB; color:#FFFFFF; }
QPushButton#green { background:#15945C; border-color:#117849; color:#FFFFFF; }
QPushButton#orange { background:#D97706; border-color:#B45309; color:#FFFFFF; }
QTableWidget { background:#FFFFFF; alternate-background-color:#F7FAFC; border:1px solid #DCE5EC; gridline-color:#E7EDF2; font-size:7.8pt; selection-background-color:#DDF0FA; selection-color:#102A3D; }
QTableWidget::item { padding:2px 4px; }
QHeaderView::section { background:#E7F0F6; color:#29495E; border:0; border-right:1px solid #D3DFE8; border-bottom:1px solid #D3DFE8; padding:3px 4px; font-weight:900; }
QDoubleSpinBox { min-height:22px; border:1px solid #C3D0DB; border-radius:5px; padding:1px 5px; background:#FFFFFF; }
QProgressBar { min-height:12px; max-height:12px; border:1px solid #D7E3EC; border-radius:6px; background:#F1F5F9; text-align:center; color:transparent; }
QProgressBar::chunk { border-radius:5px; }
QTabWidget#miniTabs::pane { border:1px solid #D5E1EA; border-radius:6px; background:#FFFFFF; }
QTabWidget#miniTabs QTabBar::tab { background:#EAF0F4; color:#3D5668; border:1px solid #D4DFE7; border-bottom:0; min-height:21px; padding:3px 8px; font-size:7.8pt; font-weight:800; }
QTabWidget#miniTabs QTabBar::tab:selected { background:#FFFFFF; color:#0B658F; }
QFrame#rxChartCard { background:#FFFFFF; border:1px solid #D6E2EB; border-radius:8px; }
"""


class _BarLine(QWidget):
    def __init__(self, title: str, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title = QLabel(title)
        self.title.setMinimumWidth(92)
        self.value = QLabel("0")
        self.value.setMinimumWidth(48)
        self.value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        self.bar.setStyleSheet(f"QProgressBar::chunk{{background:{color};}}")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(6)
        layout.addWidget(self.title)
        layout.addWidget(self.bar, 1)
        layout.addWidget(self.value)

    def set_value(self, count: int, total: int) -> None:
        total = max(1, int(total))
        pct = int(round(max(0.0, min(1.0, count / total)) * 1000))
        self.bar.setValue(pct)
        self.value.setText(f"{count:,}")


class ReceiverQcDashboard(QWidget):
    """SMT-200/SMT-300 geophone/string tester analyzer replacement."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("receiverQcDashboard")
        self.setProperty("module_id", "receiver_qc")
        self.setStyleSheet(_QSS)
        self.records: list[SmtRecord] = []
        self.results: list[ReceiverQcResult] = []
        self._path: Path | None = None
        self._category_bars: list[_BarLine] = []
        self._build_ui()
        self._update_dashboard_state()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(7)
        root.addWidget(self._build_header())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_sidebar())

        content = QFrame()
        content.setObjectName("contentPanel")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(8, 8, 8, 8)
        content_layout.setSpacing(6)
        self.pages = QStackedWidget()
        self._build_overview_page()
        self._build_records_page()
        self._build_graphs_page()
        self._build_limits_page()
        self._build_failures_page()
        self._build_statistics_page()
        content_layout.addWidget(self.pages, 1)
        splitter.addWidget(content)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([150, 1250])
        root.addWidget(splitter, 1)

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("rxHeader")
        h = QHBoxLayout(header)
        h.setContentsMargins(13, 8, 13, 8)
        h.setSpacing(8)
        text_panel = QFrame()
        text_panel.setObjectName("rxHeaderTextPanel")
        text = QVBoxLayout(text_panel)
        text.setContentsMargins(12, 6, 12, 6)
        text.setSpacing(2)
        title = QLabel("Receiver / Geophone SMT QC")
        title.setObjectName("rxTitle")
        title.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        sub = QLabel("SMT import • resistance/noise/frequency/damping/distortion limits • serial history • failure categories")
        sub.setObjectName("rxSub")
        sub.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        sub.setWordWrap(False)
        text.addWidget(title)
        text.addWidget(sub)
        h.addWidget(text_panel, 1)
        self.file_badge = QLabel("No file loaded")
        self.file_badge.setObjectName("rxFileBadge")
        h.addWidget(self.file_badge)
        open_btn = QPushButton("Open SMT")
        open_btn.setObjectName("primary")
        open_btn.clicked.connect(self.open_file)
        h.addWidget(open_btn)
        run_btn = QPushButton("Run QC")
        run_btn.setObjectName("green")
        run_btn.clicked.connect(self.run_qc)
        h.addWidget(run_btn)
        export_btn = QPushButton("Export CSV")
        export_btn.setObjectName("orange")
        export_btn.clicked.connect(self.export_results)
        h.addWidget(export_btn)
        return header

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("rxSidebar")
        sidebar.setMinimumWidth(138)
        sidebar.setMaximumWidth(168)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(7, 8, 7, 8)
        layout.setSpacing(5)
        title = QLabel("RECEIVER QC")
        title.setObjectName("rxSideTitle")
        layout.addWidget(title)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: list[QPushButton] = []
        for index, label in enumerate(("Overview", "Records", "QC Graphs", "Limits", "Failures", "Statistics")):
            btn = QPushButton(label)
            btn.setObjectName("navButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, i=index: self.pages.setCurrentIndex(i))
            self.nav_group.addButton(btn, index)
            self.nav_buttons.append(btn)
            layout.addWidget(btn)
        self.nav_buttons[0].setChecked(True)
        layout.addStretch(1)
        return sidebar

    def _make_metric_card(self, key: str, title: str, accent: str = "blue") -> QFrame:
        card = QFrame()
        card.setObjectName("metricCard")
        card.setProperty("accent", accent)
        box = QVBoxLayout(card)
        box.setContentsMargins(10, 7, 10, 7)
        box.setSpacing(0)
        t = QLabel(title)
        t.setObjectName("metricTitle")
        v = QLabel("—")
        v.setObjectName("metricValue")
        v.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        box.addWidget(t)
        box.addWidget(v)
        self.metric_labels[key] = v
        return card

    def _build_overview_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        self.metric_labels: dict[str, QLabel] = {}
        cards = QWidget()
        grid = QGridLayout(cards)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(7)
        grid.setVerticalSpacing(7)
        specs = [
            ("total", "Records", "blue"),
            ("score", "QC Score", "green"),
            ("pass", "Pass", "green"),
            ("warn", "Warnings", "orange"),
            ("fail", "Failures", "red"),
            ("dup", "Duplicates", "purple"),
        ]
        for i, (key, title, accent) in enumerate(specs):
            grid.addWidget(self._make_metric_card(key, title, accent), i // 3, i % 3)
        for col in range(3):
            grid.setColumnStretch(col, 1)
        layout.addWidget(cards)

        mid = QWidget()
        mid_layout = QHBoxLayout(mid)
        mid_layout.setContentsMargins(0, 0, 0, 0)
        mid_layout.setSpacing(7)
        self.status_group = QGroupBox("Status Distribution")
        status_box = QVBoxLayout(self.status_group)
        status_box.setContentsMargins(10, 12, 10, 8)
        self.pass_bar = _BarLine("PASS", "#15945C")
        self.warn_bar = _BarLine("WARN", "#D97706")
        self.fail_bar = _BarLine("FAIL", "#C2414A")
        for b in (self.pass_bar, self.warn_bar, self.fail_bar):
            status_box.addWidget(b)
        status_box.addStretch(1)
        mid_layout.addWidget(self.status_group, 1)

        self.quick_group = QGroupBox("Data Completeness")
        qbox = QVBoxLayout(self.quick_group)
        qbox.setContentsMargins(10, 12, 10, 8)
        self.completeness_lines: dict[str, _BarLine] = {}
        for key, title, color in (
            ("resistance", "Resistance", "#0A86C7"),
            ("noise", "Noise", "#7857B6"),
            ("frequency", "Frequency", "#15945C"),
            ("damping", "Damping", "#D97706"),
            ("distortion", "Distortion", "#C2414A"),
        ):
            line = _BarLine(title, color)
            self.completeness_lines[key] = line
            qbox.addWidget(line)
        qbox.addStretch(1)
        mid_layout.addWidget(self.quick_group, 1)
        layout.addWidget(mid, 1)

        hint = QLabel("Open an SMT/geophone tester file, review completeness, adjust limits if required, then run QC and inspect failures/statistics.")
        hint.setObjectName("sectionHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.pages.addWidget(page)

    @staticmethod
    def _prep_table(table: QTableWidget) -> None:
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(21)
        table.horizontalHeader().setStretchLastSection(True)
        table.setShowGrid(True)

    def _build_records_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.records_table = QTableWidget(0, 13)
        self.records_table.setHorizontalHeaderLabels(["Status", "Serial", "String", "Resistance", "Noise", "Distortion", "Freq", "Damping", "Sensitivity", "Impedance", "Polarity", "Tester", "Note"])
        self._prep_table(self.records_table)
        layout.addWidget(self.records_table, 1)
        self.pages.addWidget(page)

    def _build_graphs_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        tabs = QTabWidget()
        tabs.setObjectName("miniTabs")

        status_page = QWidget()
        status_layout = QVBoxLayout(status_page)
        status_layout.setContentsMargins(8, 8, 8, 8)
        self.status_plot = pg.PlotWidget(background="w")
        self.status_plot.showGrid(x=False, y=True, alpha=0.18)
        self.status_plot.setLabel("left", "Receiver count")
        self.status_plot.setTitle("Run QC to display PASS / WARN / FAIL distribution")
        status_layout.addWidget(self.status_plot, 1)
        tabs.addTab(status_page, "Vertical Status Graph")

        cat_page = QWidget()
        cat_layout = QVBoxLayout(cat_page)
        cat_layout.setContentsMargins(10, 10, 10, 10)
        self.category_group = QGroupBox("Finding Categories")
        self.category_layout = QVBoxLayout(self.category_group)
        self.category_layout.setContentsMargins(10, 12, 10, 8)
        self.category_empty = QLabel("Run QC to see categorized receiver/geophone failures.")
        self.category_empty.setObjectName("sectionHint")
        self.category_empty.setWordWrap(True)
        self.category_layout.addWidget(self.category_empty)
        self.category_plot = pg.PlotWidget(background="w")
        self.category_plot.showGrid(x=False, y=True, alpha=0.18)
        self.category_plot.setLabel("left", "Finding count")
        cat_layout.addWidget(self.category_group)
        cat_layout.addWidget(self.category_plot, 1)
        tabs.addTab(cat_page, "Finding Categories")

        stats_page = QWidget()
        stats_layout = QVBoxLayout(stats_page)
        stats_layout.setContentsMargins(10, 10, 10, 10)
        self.numeric_plot = pg.PlotWidget(background="w")
        self.numeric_plot.showGrid(x=False, y=True, alpha=0.18)
        self.numeric_plot.setLabel("left", "Mean value")
        self.numeric_table = QTableWidget(0, 5)
        self.numeric_table.setHorizontalHeaderLabels(["Measurement", "Valid", "Min", "Mean", "Max"])
        self._prep_table(self.numeric_table)
        stats_layout.addWidget(self.numeric_plot, 1)
        stats_layout.addWidget(self.numeric_table, 1)
        tabs.addTab(stats_page, "Measurement Ranges")
        layout.addWidget(tabs, 1)
        self.pages.addWidget(page)

    def _build_limits_page(self) -> None:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        box = QGroupBox("QC Limits")
        form = QFormLayout(box)
        form.setContentsMargins(12, 12, 12, 10)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(5)

        def spin(value: float, hi: float = 999999.0) -> QDoubleSpinBox:
            s = QDoubleSpinBox()
            s.setRange(-999999.0, hi)
            s.setDecimals(4)
            s.setValue(value)
            return s

        self.res_min = spin(250)
        self.res_max = spin(650)
        self.noise_max = spin(20)
        self.dist_max = spin(0.2)
        self.freq_min = spin(8)
        self.freq_max = spin(14)
        self.damp_min = spin(0.35)
        self.damp_max = spin(0.85)
        self.sens_min = spin(0)
        self.imp_min = spin(0)
        for label, widget in (("Resistance min", self.res_min), ("Resistance max", self.res_max), ("Noise max", self.noise_max), ("Distortion max", self.dist_max), ("Frequency min", self.freq_min), ("Frequency max", self.freq_max), ("Damping min", self.damp_min), ("Damping max", self.damp_max), ("Sensitivity min", self.sens_min), ("Impedance min", self.imp_min)):
            form.addRow(label + ":", widget)
        apply = QPushButton("Apply Limits & Re-run QC")
        apply.setObjectName("primary")
        apply.clicked.connect(self.run_qc)
        form.addRow(apply)
        layout.addWidget(box, 0)
        layout.addStretch(1)
        self.pages.addWidget(page)

    def _build_failures_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self.failure_table = QTableWidget(0, 7)
        self.failure_table.setHorizontalHeaderLabels(["Status", "Serial/String", "Category", "Finding", "Recommended Action", "Tester", "Source"])
        self._prep_table(self.failure_table)
        layout.addWidget(self.failure_table)
        self.pages.addWidget(page)

    def _build_statistics_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self.stats_table = QTableWidget(0, 2)
        self.stats_table.setHorizontalHeaderLabels(["Metric", "Value"])
        self._prep_table(self.stats_table)
        self.stats_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        layout.addWidget(self.stats_table)
        self.pages.addWidget(page)

    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open SMT / geophone tester file", str(Path.home()), "SMT/CSV/TXT (*.csv *.txt *.tsv *.dat *.log);;All files (*.*)")
        if not path:
            return
        main_window = self.window()
        task_id = f"receiver:file:{Path(path).name}"
        if hasattr(main_window, "begin_busy_task"):
            main_window.begin_busy_task(task_id, "Opening Receiver QC File", f"Reading {Path(path).name}", 10)
        try:
            self.records = SmtReader().read(path)
            if hasattr(main_window, "update_busy_task"):
                main_window.update_busy_task(task_id, 55, "Populating receiver tables and statistics")
            self._path = Path(path)
            self.results = []
            self.file_badge.setText(self._path.name)
            self._populate_records()
            self._populate_statistics()
            self._update_dashboard_state()
            if hasattr(main_window, "update_busy_task"):
                main_window.update_busy_task(task_id, 82, "Running Receiver QC")
            self.run_qc()
            if hasattr(main_window, "update_busy_task"):
                main_window.update_busy_task(task_id, 100, "Receiver QC file is ready")
        except Exception as exc:
            QMessageBox.critical(self, "Receiver SMT Import", str(exc))
        finally:
            if hasattr(main_window, "end_busy_task"):
                main_window.end_busy_task(task_id)

    def _limits(self) -> ReceiverQcLimits:
        return ReceiverQcLimits(
            resistance_min=self.res_min.value(), resistance_max=self.res_max.value(), noise_max=self.noise_max.value(), distortion_max=self.dist_max.value(),
            frequency_min=self.freq_min.value(), frequency_max=self.freq_max.value(), damping_min=self.damp_min.value(), damping_max=self.damp_max.value(),
            sensitivity_min=self.sens_min.value(), impedance_min=self.imp_min.value(),
        )

    def run_qc(self) -> None:
        if not self.records:
            QMessageBox.information(self, "Receiver QC", "Open an SMT/geophone tester file first.")
            return
        self.results = ReceiverQcEngine(self._limits()).evaluate(self.records)
        self._populate_records()
        self._populate_failures()
        self._populate_statistics()
        self._update_dashboard_state()
        if len(self.results) > 0:
            self.pages.setCurrentIndex(2)
            self.nav_buttons[2].setChecked(True)

    def _status_item(self, status: str) -> QTableWidgetItem:
        item = QTableWidgetItem(status)
        fg, bg = _STATUS_STYLE.get(status.upper(), ("#334155", "#E2E8F0"))
        item.setForeground(QColor(fg))
        item.setBackground(QColor(bg))
        item.setTextAlignment(Qt.AlignCenter)
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        return item

    def _populate_records(self) -> None:
        rows = self.results or [ReceiverQcResult(record=r, status="LOADED") for r in self.records]
        self.records_table.setRowCount(0)
        for result in rows:
            r = result.record
            row = self.records_table.rowCount()
            self.records_table.insertRow(row)
            values = [result.status, r.serial, r.string_id, r.resistance, r.noise, r.distortion, r.frequency, r.damping, r.sensitivity, r.impedance, r.polarity, r.tester, r.note]
            for col, value in enumerate(values):
                item = self._status_item(str(value)) if col == 0 else QTableWidgetItem("" if value is None else str(value))
                self.records_table.setItem(row, col, item)
        self.records_table.resizeColumnsToContents()

    @staticmethod
    def _finding_category(text: str) -> str:
        parts = text.split()
        if len(parts) >= 2:
            return parts[1].strip().title()
        return "General"

    @staticmethod
    def _recommended_action(category: str) -> str:
        cat = category.lower()
        if cat == "resistance":
            return "Check coil/string continuity, connectors and cable resistance."
        if cat == "noise":
            return "Retest in quiet conditions; inspect leakage, cable motion and grounding."
        if cat == "distortion":
            return "Repeat tester calibration and check damaged geophone elements."
        if cat == "frequency":
            return "Verify geophone natural frequency and replace out-of-band units."
        if cat == "damping":
            return "Check damping resistance and mechanical damage."
        if cat == "polarity":
            return "Reverse wiring or mark unit for repair before deployment."
        return "Inspect source record and retest the receiver/string."

    def _populate_failures(self) -> None:
        self.failure_table.setRowCount(0)
        for result in self.results:
            if result.status == "PASS" and not result.findings:
                continue
            r = result.record
            for finding in result.findings or ["WARN review record"]:
                category = self._finding_category(finding)
                row = self.failure_table.rowCount()
                self.failure_table.insertRow(row)
                values = [result.status, r.serial or r.string_id, category, finding, self._recommended_action(category), r.tester, f"{r.source_file}:{r.source_line}"]
                for col, value in enumerate(values):
                    item = self._status_item(str(value)) if col == 0 else QTableWidgetItem(str(value))
                    self.failure_table.setItem(row, col, item)
        self.failure_table.resizeColumnsToContents()

    def _numeric_summary_rows(self) -> list[tuple[str, int, str, str, str]]:
        fields = [
            ("Resistance", "resistance"),
            ("Noise", "noise"),
            ("Distortion", "distortion"),
            ("Frequency", "frequency"),
            ("Damping", "damping"),
            ("Sensitivity", "sensitivity"),
            ("Impedance", "impedance"),
        ]
        rows: list[tuple[str, int, str, str, str]] = []
        for title, attr in fields:
            values = [float(getattr(record, attr)) for record in self.records if getattr(record, attr) is not None]
            if values:
                rows.append((title, len(values), f"{min(values):.6g}", f"{mean(values):.6g}", f"{max(values):.6g}"))
            else:
                rows.append((title, 0, "—", "—", "—"))
        return rows

    def _refresh_graphs(self) -> None:
        if not hasattr(self, "status_plot"):
            return
        for plot in (self.status_plot, self.category_plot, self.numeric_plot):
            plot.clear()
        summary = ReceiverQcEngine.summarize(self.results) if self.results else {
            "total": len(self.records), "pass": 0, "warn": 0, "fail": 0, "score": 0.0,
            "duplicates": self._duplicate_count(), "categories": {},
        }
        status_names = ["PASS", "WARN", "FAIL"]
        status_values = np.asarray([summary.get("pass", 0), summary.get("warn", 0), summary.get("fail", 0)], dtype=float)
        status_colors = [pg.mkBrush("#15945C"), pg.mkBrush("#D97706"), pg.mkBrush("#C2414A")]
        self.status_plot.addItem(pg.BarGraphItem(x=np.arange(3), height=status_values, width=0.62, brushes=status_colors, pen=pg.mkPen("#FFFFFF")))
        self.status_plot.getAxis("bottom").setTicks([[(float(i), label) for i, label in enumerate(status_names)]])
        self.status_plot.setYRange(0, max(1.0, float(np.max(status_values)) * 1.18), padding=0)
        self.status_plot.setTitle(f"Receiver QC vertical status graph — score {float(summary.get('score', 0.0)):.1f}%")

        categories = dict(summary.get("categories", {}) or {})
        if categories:
            labels = [str(k).title() for k, _ in sorted(categories.items(), key=lambda kv: int(kv[1]), reverse=True)]
            values = np.asarray([int(categories[k]) for k, _ in sorted(categories.items(), key=lambda kv: int(kv[1]), reverse=True)], dtype=float)
            self.category_plot.addItem(pg.BarGraphItem(x=np.arange(len(values)), height=values, width=0.62, brush=pg.mkBrush("#0A86C7"), pen=pg.mkPen("#FFFFFF")))
            self.category_plot.getAxis("bottom").setTicks([[(float(i), label[:12]) for i, label in enumerate(labels)]])
            self.category_plot.setYRange(0, max(1.0, float(np.max(values)) * 1.18), padding=0)
            self.category_plot.setTitle("Failure category counts")
        else:
            self.category_plot.setTitle("No categorized findings yet")

        numeric = self._numeric_summary_rows()
        labels, means = [], []
        for title, valid, _min_v, mean_v, _max_v in numeric:
            try:
                value = float(mean_v)
            except Exception:
                continue
            if int(valid) > 0 and np.isfinite(value):
                labels.append(title)
                means.append(value)
        if means:
            means_array = np.asarray(means, dtype=float)
            display = np.log10(np.maximum(np.abs(means_array), 1e-12))
            self.numeric_plot.addItem(pg.BarGraphItem(x=np.arange(len(display)), height=display, width=0.62, brush=pg.mkBrush("#7857B6"), pen=pg.mkPen("#FFFFFF")))
            self.numeric_plot.getAxis("bottom").setTicks([[(float(i), label[:10]) for i, label in enumerate(labels)]])
            self.numeric_plot.setLabel("left", "log10(|mean|)")
            self.numeric_plot.setTitle("Measurement mean levels by receiver-test channel")
        else:
            self.numeric_plot.setTitle("No numeric receiver measurements available")

    def _populate_statistics(self) -> None:
        summary = ReceiverQcEngine.summarize(self.results) if self.results else {
            "total": len(self.records), "pass": 0, "warn": 0, "fail": 0, "score": 0.0, "duplicates": self._duplicate_count(), "categories": {}
        }
        rows = [
            ("QC score", f"{summary['score']}%" if self.results else "Not run"),
            ("Total records", summary["total"]),
            ("Pass", summary["pass"]),
            ("Warn", summary["warn"]),
            ("Fail", summary["fail"]),
            ("Duplicate serial/string IDs", summary["duplicates"]),
        ]
        for cat, count in sorted(summary.get("categories", {}).items()):
            rows.append((f"Finding category: {cat}", count))
        for title, valid, min_v, mean_v, max_v in self._numeric_summary_rows():
            rows.append((f"{title} valid/min/mean/max", f"{valid} / {min_v} / {mean_v} / {max_v}"))
        self.stats_table.setRowCount(0)
        for key, value in rows:
            row = self.stats_table.rowCount()
            self.stats_table.insertRow(row)
            self.stats_table.setItem(row, 0, QTableWidgetItem(str(key)))
            self.stats_table.setItem(row, 1, QTableWidgetItem(str(value)))
        self.stats_table.resizeColumnsToContents()
        self._populate_numeric_table()
        self._populate_category_bars(summary)
        self._refresh_graphs()

    def _populate_numeric_table(self) -> None:
        rows = self._numeric_summary_rows()
        self.numeric_table.setRowCount(0)
        for row_values in rows:
            row = self.numeric_table.rowCount()
            self.numeric_table.insertRow(row)
            for col, value in enumerate(row_values):
                self.numeric_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.numeric_table.resizeColumnsToContents()

    def _clear_category_bars(self) -> None:
        while self.category_layout.count() > 1:
            item = self.category_layout.takeAt(1)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._category_bars.clear()

    def _populate_category_bars(self, summary: dict[str, object]) -> None:
        self._clear_category_bars()
        categories = dict(summary.get("categories", {}) or {})
        self.category_empty.setVisible(not bool(categories))
        total = sum(int(v) for v in categories.values()) or 1
        colors = ["#C2414A", "#D97706", "#7857B6", "#0A86C7", "#15945C", "#475569"]
        for i, (cat, count) in enumerate(sorted(categories.items(), key=lambda item: int(item[1]), reverse=True)):
            line = _BarLine(str(cat).title(), colors[i % len(colors)])
            line.set_value(int(count), total)
            self._category_bars.append(line)
            self.category_layout.addWidget(line)
        self.category_layout.addStretch(1)

    def _duplicate_count(self) -> int:
        serials = [r.serial or r.string_id for r in self.records if r.serial or r.string_id]
        return len(serials) - len(set(serials))

    def _update_dashboard_state(self) -> None:
        if self.results:
            summary = ReceiverQcEngine.summarize(self.results)
        else:
            summary = {"total": len(self.records), "pass": 0, "warn": 0, "fail": 0, "score": 0.0, "duplicates": self._duplicate_count(), "categories": {}}
        self.metric_labels["total"].setText(f"{int(summary['total']):,}")
        self.metric_labels["score"].setText(f"{float(summary['score']):.1f}%" if self.results else "—")
        self.metric_labels["pass"].setText(f"{int(summary['pass']):,}")
        self.metric_labels["warn"].setText(f"{int(summary['warn']):,}")
        self.metric_labels["fail"].setText(f"{int(summary['fail']):,}")
        self.metric_labels["dup"].setText(f"{int(summary['duplicates']):,}")
        total = int(summary["total"])
        self.pass_bar.set_value(int(summary["pass"]), total)
        self.warn_bar.set_value(int(summary["warn"]), total)
        self.fail_bar.set_value(int(summary["fail"]), total)
        for attr, line in self.completeness_lines.items():
            valid = sum(1 for r in self.records if getattr(r, attr) is not None)
            line.set_value(valid, len(self.records))
        if self._path is not None:
            self.file_badge.setText(self._path.name)
        else:
            self.file_badge.setText("No file loaded")

    def export_results(self) -> None:
        if not self.results:
            QMessageBox.information(self, "Receiver QC", "Run QC before export.")
            return
        suggested = (self._path.with_name(self._path.stem + "_receiver_smt_qc.csv") if self._path else Path.home() / "receiver_smt_qc.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Export Receiver QC", str(suggested), "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["status", "serial", "string_id", "resistance", "noise", "distortion", "frequency", "damping", "sensitivity", "impedance", "polarity", "tester", "operator", "findings", "source_file", "source_line"])
            for result in self.results:
                r = result.record
                writer.writerow([result.status, r.serial, r.string_id, r.resistance, r.noise, r.distortion, r.frequency, r.damping, r.sensitivity, r.impedance, r.polarity, r.tester, r.operator, "; ".join(result.findings), r.source_file, r.source_line])
        QMessageBox.information(self, "Receiver QC", f"Exported:\n{path}")

    def _show_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        if 0 <= index < len(self.nav_buttons):
            self.nav_buttons[index].setChecked(True)

    def show_records(self) -> None: self._show_page(1)
    def show_limits(self) -> None: self._show_page(3)
    def show_failures(self) -> None: self._show_page(4)
    def show_statistics(self) -> None: self._show_page(5)

    def can_execute(self, action_id: str) -> bool:
        if action_id in {"receiver_open", "receiver_limits"}:
            return True
        if action_id in {"receiver_run_qc", "receiver_failures", "receiver_export"}:
            return bool(self.records)
        return True
