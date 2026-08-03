from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pyqtgraph as pg
import pyqtgraph.exporters
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QPushButton,
    QFileDialog,
    QTabWidget,
    QGroupBox,
    QDoubleSpinBox,
    QSpinBox,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QSplitter,
    QLineEdit,
    QFrame,
    QGridLayout,
    QSizePolicy,
    QCheckBox,
    QRadioButton,
    QButtonGroup,
    QScrollArea,
    QProgressDialog,
)

from modules.vibroseis import SweepParameters, VibroseisEngine
from modules.vibroseis.vaps_reader import VapsReader, VapsQcEngine, VapsRecord
from core.domain.geospatial import CoordinateTransformError, to_wgs84
from ui.widgets.geospatial_view import GeoTrack, GoogleGeospatialView
from modules.vibroseis.ui.vibroseis_results_dialog import (
    CorrelationResultsDialog,
    GroundForceResultsDialog,
    ProductivityResultsDialog,
    SignalQcResultsDialog,
    SweepResultsDialog,
    VapsQcResultsDialog,
)


_VIB_QSS = """
QWidget#vibroseisDashboard {
    background: #F3F6FA;
    color: #102A3D;
    font-size: 8pt;
}
QWidget#vibroseisDashboard QLabel { background: transparent; }
QFrame#vibHeader {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #07263A, stop:.55 #0C516B, stop:1 #1183A3);
    border: 0;
    border-radius: 7px;
}
QLabel#vibTitle {
    color: #FFFFFF;
    font-size: 12px;
    font-weight: 900;
}
QLabel#vibSubtitle {
    color: #D5EDF6;
    font-size: 7.8px;
}
QLabel#vibBadge {
    background: #E8F7EF;
    color: #0C6A43;
    border: 1px solid #B8DEC9;
    border-radius: 8px;
    padding: 4px 10px;
    font-size: 7.6px;
    font-weight: 900;
}
QLabel#vibStatus {
    background: rgba(255,255,255,0.14);
    color: #FFFFFF;
    border: 1px solid rgba(255,255,255,0.24);
    border-radius: 8px;
    padding: 4px 10px;
    font-size: 7.6px;
    font-weight: 800;
}
QLabel#vibInfo {
    color:#516B7D;
    background:transparent;
    font-size:7.8pt;
    font-weight:700;
}
QTabWidget#vibTabs::pane {
    border: 1px solid #D2DFE9;
    background: #FFFFFF;
    top: -1px;
}
QTabWidget#vibTabs QTabBar::tab {
    background:#E9F1F6;
    color:#2E5368;
    border:1px solid #D2DFE9;
    padding:4px 10px;
    min-height:18px;
    font-size:7.8pt;
    font-weight:700;
}
QTabWidget#vibTabs QTabBar::tab:selected {
    background:#FFFFFF;
    color:#0879A8;
    border-top:2px solid #0A92C4;
    border-bottom-color:#FFFFFF;
    font-weight:900;
}
QGroupBox {
    background:#FFFFFF;
    color:#15384F;
    border:1px solid #D4DEE8;
    border-radius:7px;
    margin-top:8px;
    padding-top:9px;
    font-size:7.8pt;
    font-weight:900;
}
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
QTableWidget {
    background:#FFFFFF;
    alternate-background-color:#F7FAFC;
    border:1px solid #DCE5EC;
    gridline-color:#E7EDF2;
    selection-background-color:#D6EBF7;
    selection-color:#0E2E44;
    font-size:7.7pt;
}
QHeaderView::section {
    background:#E7F0F6;
    color:#29495E;
    border:0;
    border-bottom:1px solid #D3DFE8;
    border-right:1px solid #E1E8EF;
    padding:3px 4px;
    font-size:7.8pt;
    font-weight:900;
}
QPushButton {
    min-height:23px;
    max-height:28px;
    padding:2px 9px;
    border:1px solid #B8C7D3;
    border-radius:5px;
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #FFFFFF, stop:1 #EDF3F8);
    color:#102A3D;
    font-size:7.8pt;
    font-weight:800;
}
QPushButton:hover { border-color:#0A86C7; background:#F2F9FD; }
QPushButton#vibPrimary {
    background:#0A86C7;
    border-color:#0873AB;
    color:#FFFFFF;
    font-weight:900;
}
QPushButton#vibGreen {
    background:#15945C;
    border-color:#117849;
    color:#FFFFFF;
    font-weight:900;
}
QPushButton#vibOrange {
    background:#D98919;
    border-color:#B97314;
    color:#FFFFFF;
    font-weight:900;
}
QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit {
    min-height:22px;
    max-height:26px;
    border:1px solid #C3D0DB;
    border-radius:5px;
    background:#FFFFFF;
    padding:1px 5px;
    color:#102A3D;
    font-size:7.8pt;
}

QFrame#vibLegacySidebar {
    background:#F8FBFD;
    border:1px solid #D4DEE8;
    border-radius:8px;
}
QLabel#vibSideTitle {
    color:#0A4868;
    font-size:8pt;
    font-weight:900;
    padding:3px 4px;
}
QPushButton#vibNavButton {
    text-align:left;
    padding-left:10px;
    background:#FFFFFF;
    border:1px solid #CFDAE3;
    color:#14384D;
}
QPushButton#vibNavButton:hover {
    background:#EAF6FC;
    border-color:#0A86C7;
}
QFrame#vibMetricCard {
    background:#FFFFFF;
    border:1px solid #D5E0EA;
    border-radius:8px;
}
QLabel#vibMetricTitle {
    color:#49687A;
    font-size:7.2pt;
    font-weight:900;
    text-transform:uppercase;
}
QLabel#vibMetricValue {
    color:#06243A;
    font-size:11pt;
    font-weight:900;
}
QScrollArea {
    border:0;
    background:transparent;
}

QSplitter::handle { background:#CAD5DE; }
"""


class VibroseisDashboard(QWidget):
    """Vibroseis sweep design, correlation, source-QC and productivity workspace."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("vibroseisDashboard")
        self.setProperty("module_id", "vibroseis")
        self.setStyleSheet(_VIB_QSS)
        self.engine = VibroseisEngine()
        self._telemetry_path: Optional[Path] = None
        self._telemetry_names: list[str] = []
        self._telemetry_data: Optional[np.ndarray] = None
        self._last_sweep = None
        self._vaps_path: Optional[Path] = None
        self._vaps_records: list[VapsRecord] = []
        self._build_ui()
        self._show_initial_state()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        header = QFrame(self)
        header.setObjectName("vibHeader")
        header.setMaximumHeight(56)
        h = QHBoxLayout(header)
        h.setContentsMargins(10, 4, 10, 4)
        h.setSpacing(8)

        text = QVBoxLayout()
        text.setSpacing(1)
        title = QLabel("Vibroseis Source Design & QC")
        title.setObjectName("vibTitle")
        subtitle = QLabel("Sweep design • pilot export • signal correlation • ground-force QC • productivity • satellite/terrain context")
        subtitle.setObjectName("vibSubtitle")
        text.addWidget(title)
        text.addWidget(subtitle)
        h.addLayout(text, 1)

        self.telemetry_badge = QLabel("No telemetry loaded")
        self.telemetry_badge.setObjectName("vibBadge")
        self.telemetry_badge.setMinimumWidth(230)
        self.telemetry_badge.setAlignment(Qt.AlignCenter)
        h.addWidget(self.telemetry_badge)

        self.status_badge = QLabel("Sweep designer ready")
        self.status_badge.setObjectName("vibStatus")
        self.status_badge.setMinimumWidth(180)
        self.status_badge.setAlignment(Qt.AlignCenter)
        h.addWidget(self.status_badge)
        root.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("vibTabs")
        self.tabs.setDocumentMode(True)
        self.tabs.setElideMode(Qt.ElideRight)
        root.addWidget(self.tabs, 1)

        self._build_sweep_tab()
        self._build_signal_qc_tab()
        self._build_vaps_qc_tab()
        self._build_ground_force_tab()
        self._build_productivity_tab()
        self._build_geospatial_tab()

    def _spin(self, lo, hi, value, decimals=2, suffix=""):
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(decimals)
        s.setValue(value)
        s.setSuffix(suffix)
        s.setKeyboardTracking(False)
        return s

    @staticmethod
    def _style_plot(plot: pg.PlotWidget, title: str) -> None:
        plot.setBackground("w")
        plot.showGrid(x=True, y=True, alpha=0.20)
        plot.setTitle(title, color="#15384F", size="9pt")
        try:
            plot.getAxis("left").setWidth(48)
            plot.getAxis("left").setStyle(tickFont=QFont("Arial", 8))
            plot.getAxis("bottom").setStyle(tickFont=QFont("Arial", 8))
        except Exception:
            pass

    @staticmethod
    def _prepare_table(table: QTableWidget) -> None:
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(22)
        table.horizontalHeader().setStretchLastSection(True)

    def _show_initial_state(self) -> None:
        """Keep the Vibroseis workspace clean until the user loads or generates data."""
        self.telemetry_badge.setText("No telemetry loaded")
        self.status_badge.setText("No data loaded")
        self._plot_placeholder(self.sweep_plot, "Pilot Sweep", "Click Generate Sweep to create a pilot sweep.")
        self._plot_placeholder(self.spectrum_plot, "Normalized Sweep Spectrum", "No generated sweep yet.")
        self._plot_placeholder(self.klauder_plot, "Klauder Wavelet / Autocorrelation", "No generated sweep yet.")
        self._plot_placeholder(self.signal_plot, "Signal / Correlation View", "Load telemetry, map columns, then run Source Signal QC or Correlate Trace.")
        self._plot_placeholder(self.force_plot, "Estimated Ground Force", "Load a telemetry / ground-force file, map acceleration channels, then calculate.")
        if hasattr(self, "vaps_plot"):
            self._plot_placeholder(self.vaps_plot, "VAPS Attribute Display", "Load VAPS / H26 field attributes, then run Field QC.")

    @staticmethod
    def _plot_placeholder(plot: pg.PlotWidget, title: str, message: str) -> None:
        plot.clear()
        plot.setTitle(title, color="#15384F", size="9pt")
        try:
            text = pg.TextItem(message, color="#5D7588", anchor=(0.5, 0.5))
            text.setFont(QFont("Arial", 9))
            plot.addItem(text)
            text.setPos(0.5, 0.5)
            plot.setXRange(0, 1, padding=0)
            plot.setYRange(0, 1, padding=0)
        except Exception:
            pass

    def _busy(self, title: str, message: str) -> QProgressDialog:
        dlg = QProgressDialog(message, None, 0, 0, self)
        dlg.setWindowTitle(title)
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.setCancelButton(None)
        dlg.resize(420, 92)
        dlg.show()
        QApplication.processEvents()
        return dlg

    @staticmethod
    def _finish_busy(dlg: QProgressDialog | None) -> None:
        if dlg is not None:
            dlg.close()
            dlg.deleteLater()
        QApplication.processEvents()

    def _require_telemetry(self, process_name: str) -> bool:
        if self._telemetry_data is not None:
            return True
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle(process_name)
        msg.setText(f"{process_name} needs a telemetry CSV/TXT file first.")
        msg.setInformativeText("Open the file now, then map the required columns and run the process again.")
        open_btn = msg.addButton("Open File", QMessageBox.AcceptRole)
        msg.addButton("Cancel", QMessageBox.RejectRole)
        msg.exec()
        if msg.clickedButton() is open_btn:
            self.open_telemetry()
        return self._telemetry_data is not None

    def _require_vaps(self, process_name: str) -> bool:
        if self._vaps_records:
            return True
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle(process_name)
        msg.setText(f"{process_name} needs a VAPS/H26 field attribute file first.")
        msg.setInformativeText("Open the VAPS/H26 file now, then run Field QC again.")
        open_btn = msg.addButton("Open VAPS/H26", QMessageBox.AcceptRole)
        msg.addButton("Cancel", QMessageBox.RejectRole)
        msg.exec()
        if msg.clickedButton() is open_btn:
            self.open_vaps(run_after_load=False)
        return bool(self._vaps_records)

    def open_ground_force_file(self) -> None:
        self.show_ground_force()
        self.open_telemetry()
        if self._telemetry_data is not None:
            self.status_badge.setText("Ground-force telemetry loaded")

    def _build_sweep_tab(self) -> None:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        controls = QGroupBox("Sweep Parameters")
        controls.setMaximumWidth(300)
        form = QFormLayout(controls)
        form.setContentsMargins(8, 8, 8, 8)
        form.setSpacing(5)
        self.f0 = self._spin(0.1, 1000, 5, 2, " Hz")
        self.f1 = self._spin(0.1, 1000, 100, 2, " Hz")
        self.duration = self._spin(0.1, 300, 12, 3, " s")
        self.fs = self._spin(10, 100000, 1000, 1, " Hz")
        self.sweep_type = QComboBox(); self.sweep_type.addItems(["Linear", "Logarithmic"])
        self.taper_in = self._spin(0, 30, 0.25, 3, " s")
        self.taper_out = self._spin(0, 30, 0.25, 3, " s")
        self.amplitude = self._spin(0, 1e9, 1, 4)
        self.phase = self._spin(-360, 360, 0, 1, "°")
        for label, widget in [
            ("Start frequency", self.f0), ("End frequency", self.f1), ("Sweep length", self.duration),
            ("Sample rate", self.fs), ("Sweep type", self.sweep_type), ("Start taper", self.taper_in),
            ("End taper", self.taper_out), ("Amplitude", self.amplitude), ("Initial phase", self.phase),
        ]:
            form.addRow(label + ":", widget)
        b = QPushButton("Generate / Recalculate"); b.setObjectName("vibPrimary"); b.clicked.connect(self.design_sweep); form.addRow(b)
        export = QPushButton("Export Pilot CSV"); export.setObjectName("vibGreen"); export.clicked.connect(self.export_pilot); form.addRow(export)
        layout.addWidget(controls, 0)

        plots = QSplitter(Qt.Vertical)
        self.sweep_plot = pg.PlotWidget()
        self.sweep_plot.setLabel("bottom", "Time", units="s"); self.sweep_plot.setLabel("left", "Amplitude")
        self._style_plot(self.sweep_plot, "Pilot Sweep")
        self.spectrum_plot = pg.PlotWidget()
        self.spectrum_plot.setLabel("bottom", "Frequency", units="Hz"); self.spectrum_plot.setLabel("left", "Amplitude")
        self._style_plot(self.spectrum_plot, "Normalized Sweep Spectrum")
        self.klauder_plot = pg.PlotWidget()
        self.klauder_plot.setLabel("bottom", "Lag", units="s"); self.klauder_plot.setLabel("left", "Normalized correlation")
        self._style_plot(self.klauder_plot, "Klauder Wavelet / Autocorrelation")
        plots.addWidget(self.sweep_plot); plots.addWidget(self.spectrum_plot); plots.addWidget(self.klauder_plot)
        plots.setSizes([220, 180, 180])
        layout.addWidget(plots, 1)
        self.tabs.addTab(page, "Sweep Designer")

    def _build_signal_qc_tab(self) -> None:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(6)
        open_btn = QPushButton("Open Telemetry CSV/TXT")
        open_btn.setObjectName("vibPrimary")
        open_btn.clicked.connect(self.open_telemetry)
        top.addWidget(open_btn)
        self.telemetry_label = QLabel("No telemetry loaded")
        self.telemetry_label.setObjectName("vibInfo")
        top.addWidget(self.telemetry_label, 1)
        root.addLayout(top)

        splitter = QSplitter(Qt.Horizontal)
        mapping = QGroupBox("Signal Mapping & QC")
        mapping.setMaximumWidth(315)
        form = QFormLayout(mapping)
        form.setContentsMargins(8, 8, 8, 8)
        form.setSpacing(5)
        self.reference_col = QComboBox(); self.measured_col = QComboBox(); self.trace_col = QComboBox()
        self.telemetry_fs = self._spin(1, 100000, 1000, 2, " Hz")
        self.band_lo = self._spin(0, 10000, 5, 2, " Hz"); self.band_hi = self._spin(0, 10000, 100, 2, " Hz")
        form.addRow("Reference / pilot:", self.reference_col); form.addRow("Measured / force:", self.measured_col)
        form.addRow("Trace to correlate:", self.trace_col); form.addRow("Sample rate:", self.telemetry_fs)
        form.addRow("QC band low:", self.band_lo); form.addRow("QC band high:", self.band_hi)
        qc_btn = QPushButton("Run Source Signal QC"); qc_btn.setObjectName("vibPrimary"); qc_btn.clicked.connect(self.run_signal_qc); form.addRow(qc_btn)
        corr_btn = QPushButton("Correlate Trace"); corr_btn.setObjectName("vibOrange"); corr_btn.clicked.connect(self.correlate_trace); form.addRow(corr_btn)
        splitter.addWidget(mapping)

        right = QWidget(); rlay = QVBoxLayout(right); rlay.setContentsMargins(0, 0, 0, 0); rlay.setSpacing(6)
        self.qc_table = QTableWidget(0, 2); self.qc_table.setHorizontalHeaderLabels(["Metric", "Value"])
        self._prepare_table(self.qc_table)
        self.qc_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.qc_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.qc_table.setMaximumHeight(155)
        self.signal_plot = pg.PlotWidget()
        self.signal_plot.setLabel("bottom", "Time / Lag", units="s")
        self._style_plot(self.signal_plot, "Signal / Correlation View")
        rlay.addWidget(self.qc_table, 0); rlay.addWidget(self.signal_plot, 1)
        splitter.addWidget(right); splitter.setSizes([300, 980]); root.addWidget(splitter, 1)
        self.tabs.addTab(page, "Signal QC")

    def _build_vaps_qc_tab(self) -> None:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # Compact action strip stays visible, while detailed controls live in tabs below.
        top = QHBoxLayout()
        top.setSpacing(6)
        open_btn = QPushButton("Open VAPS / H26 Attributes")
        open_btn.setObjectName("vibPrimary")
        open_btn.clicked.connect(self.open_vaps)
        run_btn = QPushButton("Run Field QC")
        run_btn.setObjectName("vibGreen")
        run_btn.clicked.connect(self.run_vaps_qc)
        bmp_btn = QPushButton("Export Image")
        bmp_btn.clicked.connect(self.export_vaps_plot)
        self.vaps_label = QLabel("No VAPS/H26 field attributes loaded")
        self.vaps_label.setObjectName("vibInfo")
        top.addWidget(open_btn)
        top.addWidget(run_btn)
        top.addWidget(bmp_btn)
        top.addWidget(self.vaps_label, 1)
        root.addLayout(top)

        main = QSplitter(Qt.Horizontal)

        # Left sidebar: navigation + frequent actions. This avoids the old crowded one-page layout.
        sidebar = QFrame()
        sidebar.setObjectName("vibLegacySidebar")
        sidebar.setMaximumWidth(245)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(8, 8, 8, 8)
        side.setSpacing(6)
        side_title = QLabel("VAPS / H26 WORKSPACE")
        side_title.setObjectName("vibSideTitle")
        side.addWidget(side_title)

        self.vaps_inner_tabs = QTabWidget()
        self.vaps_inner_tabs.setObjectName("vibTabs")
        self.vaps_inner_tabs.setDocumentMode(True)
        self.vaps_inner_tabs.setElideMode(Qt.ElideRight)

        nav_defs = [
            ("Summary / Load", 0),
            ("Vibrator Fleet", 1),
            ("Attributes", 2),
            ("Display / Plot", 3),
            ("Records Table", 4),
            ("Warnings", 5),
        ]
        for label, idx in nav_defs:
            btn = QPushButton(label)
            btn.setObjectName("vibNavButton")
            btn.clicked.connect(lambda _checked=False, tab=idx: self.vaps_inner_tabs.setCurrentIndex(tab))
            side.addWidget(btn)
        side.addSpacing(5)
        side.addWidget(open_btn)
        side.addWidget(run_btn)
        side.addWidget(bmp_btn)
        side.addStretch(1)
        main.addWidget(sidebar)

        # 1) Summary / load tab.
        summary_page = QWidget()
        sroot = QVBoxLayout(summary_page)
        sroot.setContentsMargins(8, 8, 8, 8)
        sroot.setSpacing(7)
        cards = QGridLayout()
        cards.setSpacing(7)
        self.vaps_metrics: dict[str, QLabel] = {}
        metric_cards = [
            ("records", "RECORDS", "0"),
            ("vibs", "VIBRATORS", "0"),
            ("pass", "PASS", "0"),
            ("fail", "FAIL", "0"),
        ]
        for idx, (key, title_text, value_text) in enumerate(metric_cards):
            card = QFrame()
            card.setObjectName("vibMetricCard")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(10, 7, 10, 7)
            cl.setSpacing(1)
            t = QLabel(title_text)
            t.setObjectName("vibMetricTitle")
            v = QLabel(value_text)
            v.setObjectName("vibMetricValue")
            self.vaps_metrics[key] = v
            cl.addWidget(t)
            cl.addWidget(v)
            cards.addWidget(card, 0, idx)
        sroot.addLayout(cards)

        load_box = QGroupBox("Loaded File / Workflow")
        load_layout = QVBoxLayout(load_box)
        load_layout.setContentsMargins(8, 8, 8, 8)
        load_layout.setSpacing(5)
        load_layout.addWidget(QLabel("Use Open VAPS / H26 Attributes to load VAPS, H26, CSV, TXT, DAT or LOG field vibrator attribute files."))
        load_layout.addWidget(QLabel("After loading, run Field QC, select Vib 1–20, choose an attribute, then review plot, record table and warnings in separate tabs."))
        sroot.addWidget(load_box)

        self.vaps_summary_table = QTableWidget(5, 2)
        self.vaps_summary_table.setHorizontalHeaderLabels(["Item", "Value"])
        self._prepare_table(self.vaps_summary_table)
        self.vaps_summary_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.vaps_summary_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for r, (k, v) in enumerate([
            ("Status", "No VAPS/H26 field attribute file loaded"),
            ("Supported", "VAPS, H26, CSV, TXT, DAT, LOG"),
            ("Vib selection", "Vib 1–20, All, None, Reset to loaded"),
            ("Display", "Raw / Filtered attribute plot"),
            ("Outputs", "QC table, warning count, PNG/BMP plot export"),
        ]):
            self.vaps_summary_table.setItem(r, 0, QTableWidgetItem(k))
            self.vaps_summary_table.setItem(r, 1, QTableWidgetItem(v))
        sroot.addWidget(self.vaps_summary_table, 1)
        self.vaps_inner_tabs.addTab(summary_page, "Summary")

        # 2) Vibrator fleet tab.
        fleet_page = QWidget()
        froot = QVBoxLayout(fleet_page)
        froot.setContentsMargins(8, 8, 8, 8)
        froot.setSpacing(7)
        fleet_help = QLabel("Select the vibrator units to display and include in QC tables. Reset selects only vibrators found in the loaded file.")
        fleet_help.setObjectName("vibInfo")
        froot.addWidget(fleet_help)

        select_box = QGroupBox("Select Vibs 1–20")
        select_grid = QGridLayout(select_box)
        select_grid.setContentsMargins(8, 8, 8, 8)
        select_grid.setHorizontalSpacing(12)
        select_grid.setVerticalSpacing(5)
        self.vaps_vib_checks: dict[str, QCheckBox] = {}
        for i in range(1, 21):
            cell = QWidget()
            row = QHBoxLayout(cell)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(5)
            cb = QCheckBox(f"Vib {i}")
            cb.setChecked(False)
            cb.toggled.connect(self._refresh_vaps_display)
            self.vaps_vib_checks[str(i)] = cb
            tag = QLabel(f"V{i}")
            tag.setAlignment(Qt.AlignCenter)
            tag.setFixedWidth(32)
            tag.setStyleSheet("background:#EAF2F8;border:1px solid #CAD3DA;border-radius:3px;font-size:7pt;font-weight:900;color:#0A4868;")
            row.addWidget(cb, 1)
            row.addWidget(tag, 0)
            select_grid.addWidget(cell, (i - 1) // 4, (i - 1) % 4)
        froot.addWidget(select_box)
        vib_btns = QHBoxLayout()
        all_btn = QPushButton("All Vibs")
        all_btn.clicked.connect(lambda: self._set_vaps_vibs(True))
        none_btn = QPushButton("None")
        none_btn.clicked.connect(lambda: self._set_vaps_vibs(False))
        rst_btn = QPushButton("Reset to Loaded")
        rst_btn.clicked.connect(self._reset_vaps_vibs_to_loaded)
        vib_btns.addWidget(all_btn)
        vib_btns.addWidget(none_btn)
        vib_btns.addWidget(rst_btn)
        vib_btns.addStretch(1)
        froot.addLayout(vib_btns)
        froot.addStretch(1)
        self.vaps_inner_tabs.addTab(fleet_page, "Vibs")

        # 3) Attribute selector tab.
        attr_page = QWidget()
        aroot = QVBoxLayout(attr_page)
        aroot.setContentsMargins(8, 8, 8, 8)
        aroot.setSpacing(6)
        self.vaps_metric_group = QButtonGroup(self)
        self.vaps_metric_group.setExclusive(True)
        self.vaps_metric_buttons: dict[str, QRadioButton] = {}

        groups = [
            ("Drive / Phase", [
                ("drive_level_pct", "Drive Level"),
                ("avg_phase_deg", "Average Phase"),
                ("peak_phase_deg", "Peak Phase"),
                ("avg_distortion_pct", "Average Distortion"),
                ("peak_distortion_pct", "Peak Distortion"),
            ]),
            ("Force / Mechanics", [
                ("avg_force", "Average Force"),
                ("peak_force", "Peak Force"),
                ("avg_viscosity", "Average Viscosity"),
                ("avg_stiffness", "Average Stiffness"),
                ("hdop", "Horizontal Accuracy"),
            ]),
            ("Warnings / Status", [
                ("status_code", "Status Code"),
                ("mass_warning", "Mass Warning"),
                ("plate_warning", "Plate Warning"),
                ("force_overload", "Force Overload"),
                ("pressure_overload", "Pressure Overload"),
                ("mass_overload", "Mass Overload"),
                ("valve_overload", "Valve Overload"),
                ("excitation_overload", "Excitation Overload"),
                ("spare_1", "Spare"),
                ("spare_2", "Spare"),
            ]),
        ]
        for title_text, items in groups:
            box = QGroupBox(title_text)
            grid = QGridLayout(box)
            grid.setContentsMargins(8, 8, 8, 8)
            grid.setHorizontalSpacing(12)
            grid.setVerticalSpacing(4)
            for idx, (attr, label) in enumerate(items):
                rb = QRadioButton(label)
                rb.toggled.connect(self._refresh_vaps_display)
                self.vaps_metric_group.addButton(rb)
                self.vaps_metric_buttons[attr] = rb
                grid.addWidget(rb, idx // 3, idx % 3)
            aroot.addWidget(box)
        self.vaps_metric_buttons["drive_level_pct"].setChecked(True)
        aroot.addStretch(1)
        self.vaps_inner_tabs.addTab(attr_page, "Attributes")

        # 4) Plot tab with raw/filtered mode.
        plot_page = QWidget()
        proot = QVBoxLayout(plot_page)
        proot.setContentsMargins(8, 8, 8, 8)
        proot.setSpacing(6)
        plot_controls = QHBoxLayout()
        mode_box = QGroupBox("Display Mode")
        mode_layout = QHBoxLayout(mode_box)
        mode_layout.setContentsMargins(8, 6, 8, 6)
        self.vaps_filtered_radio = QRadioButton("Filtered")
        self.vaps_raw_radio = QRadioButton("Raw")
        self.vaps_raw_radio.setChecked(True)
        self.vaps_raw_radio.toggled.connect(self._refresh_vaps_display)
        self.vaps_filtered_radio.toggled.connect(self._refresh_vaps_display)
        mode_layout.addWidget(self.vaps_raw_radio)
        mode_layout.addWidget(self.vaps_filtered_radio)
        plot_controls.addWidget(mode_box, 0)
        plot_controls.addStretch(1)
        proot.addLayout(plot_controls)
        self.vaps_plot = pg.PlotWidget()
        self.vaps_plot.setLabel("bottom", "VAPS record / source line")
        self.vaps_plot.setLabel("left", "Selected attribute")
        self._style_plot(self.vaps_plot, "VAPS Attribute Display")
        proot.addWidget(self.vaps_plot, 1)
        self.vaps_inner_tabs.addTab(plot_page, "Display")

        # 5) Record table tab.
        records_page = QWidget()
        rr = QVBoxLayout(records_page)
        rr.setContentsMargins(8, 8, 8, 8)
        rr.setSpacing(6)
        self.vaps_table = QTableWidget(0, 16)
        self.vaps_table.setHorizontalHeaderLabels([
            "Status", "Vib", "VP", "Drive %", "Avg Phase", "Peak Phase", "Avg Dist", "Peak Dist",
            "Avg Force", "Peak Force", "Viscosity", "Stiffness", "HDOP", "Status Code", "Warnings", "Line"
        ])
        self._prepare_table(self.vaps_table)
        self.vaps_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.vaps_table.horizontalHeader().setStretchLastSection(True)
        rr.addWidget(self.vaps_table, 1)
        self.vaps_inner_tabs.addTab(records_page, "Records")

        # 6) Warning summary tab.
        warn_page = QWidget()
        wr = QVBoxLayout(warn_page)
        wr.setContentsMargins(8, 8, 8, 8)
        wr.setSpacing(6)
        self.vaps_warning_table = QTableWidget(0, 2)
        self.vaps_warning_table.setHorizontalHeaderLabels(["Warning / QC category", "Count"])
        self._prepare_table(self.vaps_warning_table)
        self.vaps_warning_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.vaps_warning_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        wr.addWidget(self.vaps_warning_table, 1)
        self.vaps_inner_tabs.addTab(warn_page, "Warnings")

        main.addWidget(self.vaps_inner_tabs)
        main.setSizes([230, 1100])
        root.addWidget(main, 1)
        self.tabs.addTab(page, "VAPS / H26 Field QC")

    def _build_ground_force_tab(self) -> None:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        box = QGroupBox("Ground Force Estimation")
        box.setMaximumWidth(315)
        form = QFormLayout(box)
        form.setContentsMargins(8, 8, 8, 8)
        form.setSpacing(5)
        self.rm_col = QComboBox(); self.bp_col = QComboBox()
        self.rm_mass = self._spin(1, 100000, 3000, 1, " kg"); self.bp_mass = self._spin(1, 100000, 1500, 1, " kg")
        self.rm_sign = QComboBox(); self.rm_sign.addItems(["+1", "-1"])
        self.bp_sign = QComboBox(); self.bp_sign.addItems(["+1", "-1"])
        load_force = QPushButton("Open Ground-Force / Telemetry File")
        load_force.setObjectName("vibGreen")
        load_force.clicked.connect(self.open_ground_force_file)
        form.addRow(load_force)
        self.ground_force_file_label = QLabel("No ground-force telemetry loaded")
        self.ground_force_file_label.setObjectName("vibInfo")
        self.ground_force_file_label.setWordWrap(True)
        form.addRow(self.ground_force_file_label)
        form.addRow("Reaction accel:", self.rm_col); form.addRow("Baseplate accel:", self.bp_col)
        form.addRow("Reaction mass:", self.rm_mass); form.addRow("Baseplate mass:", self.bp_mass)
        form.addRow("Reaction polarity:", self.rm_sign); form.addRow("Baseplate polarity:", self.bp_sign)
        note = QLabel("Acceleration must be in m/s². Sensor signs must match vibrator/controller convention.")
        note.setWordWrap(True); note.setStyleSheet("color:#8A4B00;font-size:7.6pt;"); form.addRow(note)
        calc = QPushButton("Calculate Ground Force"); calc.setObjectName("vibPrimary"); calc.clicked.connect(self.calculate_ground_force); form.addRow(calc)
        layout.addWidget(box, 0)
        right = QWidget(); r = QVBoxLayout(right); r.setContentsMargins(0, 0, 0, 0); r.setSpacing(6)
        self.force_table = QTableWidget(0, 2); self.force_table.setHorizontalHeaderLabels(["Metric", "Value"])
        self._prepare_table(self.force_table)
        self.force_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.force_table.setMaximumHeight(118)
        self.force_plot = pg.PlotWidget()
        self.force_plot.setLabel("bottom", "Time", units="s"); self.force_plot.setLabel("left", "Force", units="N")
        self._style_plot(self.force_plot, "Estimated Ground Force")
        r.addWidget(self.force_table, 0); r.addWidget(self.force_plot, 1); layout.addWidget(right, 1)
        self.tabs.addTab(page, "Ground Force")

    def _build_productivity_tab(self) -> None:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        box = QGroupBox("Nominal Vibroseis Cycle")
        box.setMaximumWidth(315)
        form = QFormLayout(box)
        form.setContentsMargins(8, 8, 8, 8)
        form.setSpacing(5)
        self.prod_sweep = self._spin(0.1, 300, 12, 2, " s")
        self.prod_n = QSpinBox(); self.prod_n.setRange(1, 100); self.prod_n.setValue(2)
        self.prod_listen = self._spin(0, 300, 4, 2, " s")
        self.prod_pad = self._spin(0, 600, 8, 2, " s")
        self.prod_move = self._spin(0, 3600, 25, 2, " s")
        for label, widget in [("Sweep length", self.prod_sweep), ("Sweeps per VP", self.prod_n), ("Listen / sweep", self.prod_listen), ("Pad up/down / VP", self.prod_pad), ("Move time / VP", self.prod_move)]:
            form.addRow(label + ":", widget)
        b = QPushButton("Calculate Productivity"); b.setObjectName("vibPrimary"); b.clicked.connect(self.calculate_productivity); form.addRow(b)
        layout.addWidget(box, 0)
        self.prod_table = QTableWidget(0, 2); self.prod_table.setHorizontalHeaderLabels(["Metric", "Value"])
        self._prepare_table(self.prod_table)
        self.prod_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.prod_table, 1)
        self.tabs.addTab(page, "Productivity")
        self._set_table(self.prod_table, {"Status": "Click Calculate Productivity to generate cycle results."})

    def _build_geospatial_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        toolbar.addWidget(QLabel("Coordinate CRS:"))
        self.telemetry_crs = QLineEdit()
        self.telemetry_crs.setPlaceholderText("EPSG:4326 for lon/lat, or projected CRS e.g. EPSG:32642")
        self.telemetry_crs.setMaximumWidth(330)
        toolbar.addWidget(self.telemetry_crs)
        refresh = QPushButton("Refresh Geometry"); refresh.setObjectName("vibPrimary"); refresh.clicked.connect(self._refresh_geospatial); toolbar.addWidget(refresh)
        toolbar.addStretch(1); layout.addLayout(toolbar)
        self.geospatial_view = GoogleGeospatialView(page, title="Vibroseis Source/Telemetry — Satellite & 3D Terrain")
        layout.addWidget(self.geospatial_view, 1)
        self.tabs.addTab(page, "2D / 3D & Satellite")

    def _set_table(self, table: QTableWidget, values: dict[str, object]) -> None:
        table.setRowCount(0)
        for k, v in values.items():
            row = table.rowCount(); table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(k)); table.setItem(row, 1, QTableWidgetItem(str(v)))
        table.resizeRowsToContents()

    def design_sweep(self) -> None:
        dlg = None
        try:
            dlg = self._busy("Generating Sweep", "Generating pilot sweep, spectrum and Klauder wavelet...")
            p = SweepParameters(
                start_frequency_hz=self.f0.value(), end_frequency_hz=self.f1.value(), duration_s=self.duration.value(),
                sample_rate_hz=self.fs.value(), sweep_type=self.sweep_type.currentText().lower(),
                taper_in_s=self.taper_in.value(), taper_out_s=self.taper_out.value(), amplitude=self.amplitude.value(), phase_deg=self.phase.value(),
            )
            result = self.engine.design_sweep(p); self._last_sweep = result
            self.sweep_plot.clear(); self.sweep_plot.plot(result.time_s, result.samples, pen=pg.mkPen("#0A6EA8", width=1.2))
            self.sweep_plot.setTitle("Pilot Sweep", color="#15384F", size="9pt")
            self.spectrum_plot.clear(); self.spectrum_plot.plot(result.frequency_hz, result.amplitude_spectrum, pen=pg.mkPen("#15945C", width=1.4))
            self.spectrum_plot.setTitle("Normalized Sweep Spectrum", color="#15384F", size="9pt")
            self.spectrum_plot.setXRange(0, min(self.fs.value()/2, max(self.f0.value(), self.f1.value())*1.35), padding=0.02)
            self.klauder_plot.clear(); self.klauder_plot.plot(result.autocorrelation_lag_s, result.klauder_wavelet, pen=pg.mkPen("#D98919", width=1.1))
            self.klauder_plot.setTitle("Klauder Wavelet / Autocorrelation", color="#15384F", size="9pt")
            half = min(2.0, self.duration.value()); self.klauder_plot.setXRange(-half, half, padding=0.01)
            self.status_badge.setText("Sweep design ready")
            self._finish_busy(dlg); dlg = None
            SweepResultsDialog(result, self.fs.value(), self).exec()
        except Exception as exc:
            self._finish_busy(dlg)
            QMessageBox.critical(self, "Vibroseis Sweep Error", str(exc))


    def export_pilot(self) -> None:
        if self._last_sweep is None: self.design_sweep()
        if self._last_sweep is None: return
        path, _ = QFileDialog.getSaveFileName(self, "Export Vibroseis Pilot", "vibroseis_pilot.csv", "CSV (*.csv)")
        if not path: return
        np.savetxt(path, np.column_stack([self._last_sweep.time_s, self._last_sweep.samples, self._last_sweep.instantaneous_frequency_hz]), delimiter=",", header="time_s,pilot_amplitude,instantaneous_frequency_hz", comments="")
        self.status_badge.setText("Pilot CSV exported")

    def open_telemetry(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Vibroseis telemetry", str(Path.home()), "Data (*.csv *.txt *.dat *.log);;All Files (*.*)")
        if not path:
            return
        dlg = None
        try:
            dlg = self._busy("Loading Telemetry", "Reading telemetry / source QC file and detecting numeric columns...")
            names, data = self.engine.load_numeric_table(path)
            self._telemetry_path = Path(path); self._telemetry_names = names; self._telemetry_data = data
            label = f"{self._telemetry_path.name} — {data.shape[0]:,} rows × {data.shape[1]} columns"
            self.telemetry_label.setText(label)
            self.telemetry_badge.setText(label)
            if hasattr(self, "ground_force_file_label"):
                self.ground_force_file_label.setText(label)
            self.status_badge.setText("Telemetry loaded")
            for combo in (self.reference_col, self.measured_col, self.trace_col, self.rm_col, self.bp_col):
                combo.clear(); combo.addItems(names)
            self._auto_map_columns(names)
            self._refresh_geospatial()
            self._finish_busy(dlg); dlg = None
            QMessageBox.information(
                self,
                "Telemetry Loaded",
                f"Loaded {data.shape[0]:,} rows and {data.shape[1]} columns.\n\nNext: check column mapping, then run Signal QC, Correlation or Ground Force.",
            )
        except Exception as exc:
            self._finish_busy(dlg)
            QMessageBox.critical(self, "Vibroseis Import Error", str(exc))


    def _auto_map_columns(self, names: list[str]) -> None:
        lowered = [n.lower() for n in names]
        def choose(combo, words, fallback):
            for i, name in enumerate(lowered):
                if any(w in name for w in words): combo.setCurrentIndex(i); return
            if combo.count(): combo.setCurrentIndex(min(fallback, combo.count()-1))
        choose(self.reference_col, ["pilot", "reference", "ref"], 0)
        choose(self.measured_col, ["ground_force", "ground force", "force", "measured"], 1)
        choose(self.trace_col, ["trace", "seismic"], 1)
        choose(self.rm_col, ["reaction", "mass_acc", "mass acc"], 0)
        choose(self.bp_col, ["baseplate", "base_acc", "plate acc"], 1)

    def _column(self, combo: QComboBox) -> np.ndarray:
        if self._telemetry_data is None: raise ValueError("Load a telemetry CSV/TXT file first.")
        return self._telemetry_data[:, combo.currentIndex()]

    def run_signal_qc(self) -> None:
        if not self._require_telemetry("Source Signal QC"):
            return
        dlg = None
        try:
            dlg = self._busy("Running Source Signal QC", "Calculating lag, RMS, amplitude ratio, coherence, phase error and band energy...")
            ref = self._column(self.reference_col); mea = self._column(self.measured_col)
            result = self.engine.signal_qc(ref, mea, self.telemetry_fs.value(), (self.band_lo.value(), self.band_hi.value()))
            self._set_table(self.qc_table, {
                "Normalized correlation": f"{result.normalized_correlation:.5f}", "Estimated lag": f"{result.lag_samples} samples ({result.lag_ms:.3f} ms)",
                "Reference RMS": f"{result.rms_reference:.6g}", "Measured RMS": f"{result.rms_measured:.6g}", "Amplitude ratio": f"{result.amplitude_ratio_db:.3f} dB",
                "RMS spectral phase error": f"{result.phase_error_rms_deg:.3f}°", "Mean magnitude-squared coherence": f"{result.spectral_coherence_mean:.5f}",
                "Energy inside QC band": f"{100*result.in_band_energy_fraction:.2f}%", "Dominant frequency": f"{result.dominant_frequency_hz:.3f} Hz", "Crest factor": f"{result.crest_factor:.4f}",
            })
            n = min(ref.size, mea.size)
            t = np.arange(n)/self.telemetry_fs.value()
            self.signal_plot.clear()
            self.signal_plot.setTitle("Source Signal QC — Reference vs Measured", color="#15384F", size="9pt")
            self.signal_plot.plot(t, ref[:n], pen=pg.mkPen("#0A6EA8", width=1.05))
            self.signal_plot.plot(t, mea[:n], pen=pg.mkPen("#D98919", width=1.05))
            self.status_badge.setText("Signal QC complete")
            self._finish_busy(dlg); dlg = None
            SignalQcResultsDialog(result, np.asarray(ref, dtype=float), np.asarray(mea, dtype=float), self.telemetry_fs.value(), self).exec()
        except Exception as exc:
            self._finish_busy(dlg)
            QMessageBox.critical(self, "Vibroseis Signal QC Error", str(exc))


    def correlate_trace(self) -> None:
        if not self._require_telemetry("Trace Correlation"):
            return
        dlg = None
        try:
            dlg = self._busy("Running Trace Correlation", "Calculating normalized trace × pilot cross-correlation...")
            trace = self._column(self.trace_col); ref = self._column(self.reference_col)
            lag, corr = self.engine.correlate_trace(trace, ref, self.telemetry_fs.value())
            self.signal_plot.clear()
            self.signal_plot.plot(lag, corr, pen=pg.mkPen("#15945C", width=1.25))
            self.signal_plot.setTitle("Normalized Trace × Pilot Cross-Correlation", color="#15384F", size="9pt")
            self.status_badge.setText("Trace correlation complete")
            self._finish_busy(dlg); dlg = None
            CorrelationResultsDialog(lag, corr, self).exec()
        except Exception as exc:
            self._finish_busy(dlg)
            QMessageBox.critical(self, "Vibroseis Correlation Error", str(exc))


    def calculate_ground_force(self) -> None:
        if not self._require_telemetry("Ground Force Calculation"):
            return
        dlg = None
        try:
            dlg = self._busy("Calculating Ground Force", "Calculating inertial force from reaction-mass and baseplate acceleration channels...")
            r = self.engine.calculate_ground_force(
                self._column(self.rm_col), self._column(self.bp_col), self.rm_mass.value(), self.bp_mass.value(),
                self.telemetry_fs.value(), 1 if self.rm_sign.currentIndex()==0 else -1, 1 if self.bp_sign.currentIndex()==0 else -1,
            )
            self._set_table(self.force_table, {
                "Peak |ground force|": f"{r.peak_force_n:,.2f} N",
                "RMS ground force": f"{r.rms_force_n:,.2f} N",
                "Signed force impulse": f"{r.impulse_ns:,.3f} N·s",
            })
            self.force_plot.clear()
            self.force_plot.setTitle("Estimated Ground Force", color="#15384F", size="9pt")
            self.force_plot.plot(r.time_s, r.ground_force_n, pen=pg.mkPen("#0A6EA8", width=1.15))
            self.force_plot.addLine(y=0, pen=pg.mkPen("#687B88", width=1.0, style=Qt.DashLine))
            self.status_badge.setText("Ground force calculated")
            self._finish_busy(dlg); dlg = None
            GroundForceResultsDialog(r, self).exec()
        except Exception as exc:
            self._finish_busy(dlg)
            QMessageBox.critical(self, "Ground Force Error", str(exc))


    def calculate_productivity(self) -> None:
        dlg = None
        try:
            dlg = self._busy("Calculating Productivity", "Calculating nominal VP/hour and active sweep fraction...")
            r = self.engine.productivity(self.prod_sweep.value(), self.prod_n.value(), self.prod_listen.value(), self.prod_pad.value(), self.prod_move.value())
            self._set_table(self.prod_table, {
                "Nominal cycle time / VP": f"{r.cycle_time_per_vp_s:.2f} s",
                "Theoretical VP / hour": f"{r.theoretical_vp_per_hour:.2f}",
                "Theoretical sweeps / hour": f"{r.theoretical_sweeps_per_hour:.2f}",
                "Active sweep fraction": f"{100*r.active_sweep_fraction:.2f}%",
            })
            self.status_badge.setText("Productivity calculated")
            self._finish_busy(dlg); dlg = None
            ProductivityResultsDialog(r, self).exec()
        except Exception as exc:
            self._finish_busy(dlg)
            QMessageBox.critical(self, "Productivity Error", str(exc))


    def _set_vaps_vibs(self, checked: bool) -> None:
        for cb in getattr(self, "vaps_vib_checks", {}).values():
            cb.setChecked(checked)
        self._refresh_vaps_display()

    def _reset_vaps_vibs_to_loaded(self) -> None:
        loaded = {self._normalize_vib_id(r.vib) for r in self._vaps_records if r.vib}
        for vib, cb in getattr(self, "vaps_vib_checks", {}).items():
            cb.setChecked(vib in loaded)
        self._refresh_vaps_display()

    @staticmethod
    def _normalize_vib_id(value: object) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        m = __import__("re").search(r"\d+", text)
        return str(int(m.group(0))) if m else text

    def _selected_vaps_metric(self) -> tuple[str, str]:
        for attr, rb in getattr(self, "vaps_metric_buttons", {}).items():
            if rb.isChecked():
                return attr, rb.text()
        return "drive_level_pct", "Drive Level"

    def _selected_vaps_records(self) -> list[VapsRecord]:
        records = list(self._vaps_records)
        selected = {v for v, cb in getattr(self, "vaps_vib_checks", {}).items() if cb.isChecked()}
        if selected:
            records = [r for r in records if self._normalize_vib_id(r.vib) in selected]
        if getattr(self, "vaps_filtered_radio", None) is not None and self.vaps_filtered_radio.isChecked():
            attr, _label = self._selected_vaps_metric()
            records = [r for r in records if self._vaps_metric_value(r, attr) is not None]
        return records

    @staticmethod
    def _vaps_metric_value(record: VapsRecord, attr: str) -> float | None:
        if attr.startswith("spare"):
            return None
        value = getattr(record, attr, None)
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        if attr == "status_code":
            try:
                return float(str(value).strip()) if str(value).strip() else None
            except Exception:
                return None
        if value is None or value == "":
            return None
        try:
            return float(value)
        except Exception:
            return None

    def _refresh_vaps_display(self) -> None:
        if hasattr(self, "vaps_plot") and self._vaps_records:
            self._plot_vaps_metric()

    def _plot_vaps_metric(self) -> None:
        if not hasattr(self, "vaps_plot"):
            return
        attr, label = self._selected_vaps_metric()
        self.vaps_plot.clear()
        if not self._vaps_records:
            self.vaps_plot.setTitle("VAPS Attribute Display — no data", color="#15384F", size="9pt")
            return
        records = self._selected_vaps_records()
        by_vib: dict[str, list[tuple[float, float]]] = {}
        for i, record in enumerate(records):
            value = self._vaps_metric_value(record, attr)
            if value is None:
                continue
            vib = self._normalize_vib_id(record.vib) or "?"
            x = float(record.source_line or i + 1)
            by_vib.setdefault(vib, []).append((x, value))
        pens = ["#111111", "#0A6EA8", "#D7191C", "#15945C", "#E6C200", "#7B61FF", "#AA3377", "#EE7733", "#009988", "#33BBEE"]
        for idx, (vib, pairs) in enumerate(sorted(by_vib.items(), key=lambda kv: (int(kv[0]) if kv[0].isdigit() else 999, kv[0]))):
            if not pairs:
                continue
            pairs.sort(key=lambda p: p[0])
            x = np.asarray([p[0] for p in pairs], dtype=float)
            y = np.asarray([p[1] for p in pairs], dtype=float)
            pen = pg.mkPen(pens[idx % len(pens)], width=1.4)
            self.vaps_plot.plot(x, y, pen=pen, symbol="o", symbolSize=4, name=f"Vib {vib}")
        mode = "Filtered" if getattr(self, "vaps_filtered_radio", None) is not None and self.vaps_filtered_radio.isChecked() else "Raw"
        self.vaps_plot.setTitle(f"{label} Day / Record Display — {mode}", color="#15384F", size="9pt")
        self.vaps_plot.setLabel("left", label)

    def export_vaps_plot(self) -> None:
        if not hasattr(self, "vaps_plot"):
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export VAPS display", "vaps_display.png", "PNG (*.png);;BMP (*.bmp)")
        if not path:
            return
        try:
            exporter = pg.exporters.ImageExporter(self.vaps_plot.plotItem)
            exporter.export(path)
            QMessageBox.information(self, "VAPS Analyser", f"Display exported:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "VAPS Export Error", str(exc))

    def open_vaps(self, run_after_load: bool = True) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open VAPS / H26 vibrator attributes", str(Path.home()), "VAPS/H26/Text (*.vaps *.h26 *.csv *.txt *.dat *.log);;All Files (*.*)")
        if not path:
            return
        dlg = None
        try:
            dlg = self._busy("Loading VAPS/H26", "Reading field vibrator attributes and mapping QC columns...")
            self._vaps_records = VapsReader().read(path)
            self._vaps_path = Path(path)
            self.vaps_label.setText(f"{self._vaps_path.name} — {len(self._vaps_records):,} VAPS records")
            if hasattr(self, "vaps_summary_table"):
                self.vaps_summary_table.setItem(0, 1, QTableWidgetItem(f"Loaded: {self._vaps_path.name}"))
                self.vaps_summary_table.setItem(1, 1, QTableWidgetItem(str(self._vaps_path)))
            self.status_badge.setText("VAPS/H26 attributes loaded")
            self._reset_vaps_vibs_to_loaded()
            self._finish_busy(dlg); dlg = None
            if run_after_load:
                self.run_vaps_qc()
            else:
                QMessageBox.information(
                    self,
                    "VAPS/H26 Loaded",
                    f"Loaded {len(self._vaps_records):,} VAPS/H26 records.\n\nNext: select vibrators/attribute and run Field QC.",
                )
        except Exception as exc:
            self._finish_busy(dlg)
            QMessageBox.critical(self, "VAPS/H26 Import Error", str(exc))


    def run_vaps_qc(self) -> None:
        if not self._require_vaps("VAPS / H26 Field QC"):
            return
        dlg = None
        try:
            dlg = self._busy("Running VAPS Field QC", "Evaluating vibrator attributes, status flags, warning categories and selected attribute graph...")
            engine = VapsQcEngine()
            summary = engine.summarize(self._vaps_records)
            self.vaps_metrics["records"].setText(f"{summary['records']:,}")
            self.vaps_metrics["vibs"].setText(f"{summary['vibs']:,}")
            self.vaps_metrics["pass"].setText(f"{summary['pass']:,}")
            self.vaps_metrics["fail"].setText(f"{summary['fail']:,}")

            display_records = self._selected_vaps_records() or list(self._vaps_records)
            self.vaps_table.setRowCount(0)
            for record in display_records:
                status, findings = engine.evaluate_record(record)
                row = self.vaps_table.rowCount(); self.vaps_table.insertRow(row)
                values = [
                    status, record.vib, record.vp, record.drive_level_pct, record.avg_phase_deg, record.peak_phase_deg,
                    record.avg_distortion_pct, record.peak_distortion_pct, record.avg_force, record.peak_force,
                    record.avg_viscosity, record.avg_stiffness, record.hdop, record.status_code, "; ".join(findings), record.source_line,
                ]
                for col, value in enumerate(values):
                    item = QTableWidgetItem("" if value is None else str(value))
                    if status == "FAIL":
                        item.setBackground(Qt.GlobalColor.red)
                        item.setForeground(Qt.GlobalColor.white)
                    elif status == "PASS" and col == 0:
                        item.setBackground(Qt.GlobalColor.green)
                    self.vaps_table.setItem(row, col, item)
            self.vaps_table.resizeRowsToContents()
            self.vaps_warning_table.setRowCount(0)
            for key, count in sorted(summary.get("warnings", {}).items()):
                row = self.vaps_warning_table.rowCount(); self.vaps_warning_table.insertRow(row)
                self.vaps_warning_table.setItem(row, 0, QTableWidgetItem(str(key)))
                self.vaps_warning_table.setItem(row, 1, QTableWidgetItem(str(count)))
            self.vaps_warning_table.resizeRowsToContents()
            self._plot_vaps_metric()
            self.status_badge.setText("VAPS analyser display/QC complete")
            attr, label = self._selected_vaps_metric()
            self._finish_busy(dlg); dlg = None
            VapsQcResultsDialog(summary, display_records, attr, label, self._vaps_metric_value, self).exec()
        except Exception as exc:
            self._finish_busy(dlg)
            QMessageBox.critical(self, "VAPS Field QC Error", str(exc))


    def _find_telemetry_column(self, aliases: tuple[str, ...]) -> np.ndarray | None:
        if self._telemetry_data is None:
            return None
        normalized = [name.lower().replace(" ", "_").replace("-", "_") for name in self._telemetry_names]
        for alias in aliases:
            key = alias.lower().replace(" ", "_").replace("-", "_")
            for i, name in enumerate(normalized):
                if len(key) <= 2:
                    matched = name == key or name.endswith("_" + key)
                else:
                    matched = name == key or name.endswith("_" + key) or key in name
                if matched:
                    return np.asarray(self._telemetry_data[:, i], dtype=float)
        return None

    def _refresh_geospatial(self) -> None:
        if not hasattr(self, "geospatial_view"):
            return
        if self._telemetry_data is None:
            self.geospatial_view.clear_tracks()
            self.geospatial_view.set_status_message("Load vibroseis telemetry with lon/lat or easting/northing columns for 2D/3D context.")
            return
        lon = self._find_telemetry_column(("longitude", "lon", "lng"))
        lat = self._find_telemetry_column(("latitude", "lat"))
        east = self._find_telemetry_column(("easting", "utm_e", "x_coord", "x"))
        north = self._find_telemetry_column(("northing", "utm_n", "y_coord", "y"))
        alt = self._find_telemetry_column(("elevation", "altitude", "height", "z"))
        try:
            if lon is not None and lat is not None:
                coords = to_wgs84(lon, lat, crs="EPSG:4326", altitude_m=alt, allow_lonlat_inference=True)
            elif east is not None and north is not None:
                crs = self.telemetry_crs.text().strip() or None
                coords = to_wgs84(east, north, crs=crs, altitude_m=alt, allow_lonlat_inference=True)
            else:
                self.geospatial_view.clear_tracks()
                self.geospatial_view.set_status_message("Telemetry needs longitude/latitude or easting/northing columns for satellite/3D context.")
                return
        except CoordinateTransformError as exc:
            self.geospatial_view.clear_tracks(); self.geospatial_view.set_status_message(str(exc)); return
        idx = np.flatnonzero(coords.valid_mask)
        if not idx.size:
            self.geospatial_view.clear_tracks(); self.geospatial_view.set_status_message("No valid georeferenced telemetry points were found."); return
        name = self._telemetry_path.name if self._telemetry_path else "Vibroseis Telemetry"
        self.geospatial_view.set_tracks([GeoTrack(name, coords.longitude[idx], coords.latitude[idx], coords.altitude_m[idx])], render=self.tabs.currentIndex() == 5)

    # Ribbon-facing helpers
    def show_sweep(self): self.tabs.setCurrentIndex(0)
    def show_signal_qc(self): self.tabs.setCurrentIndex(1)
    def show_vaps_qc(self): self.tabs.setCurrentIndex(2)
    def show_ground_force(self): self.tabs.setCurrentIndex(3)
    def show_productivity(self): self.tabs.setCurrentIndex(4)
    def show_geospatial_view(self, mode: str = "2d"):
        self.tabs.setCurrentIndex(5); self._refresh_geospatial(); self.geospatial_view.set_mode("3d" if str(mode).lower().startswith("3") else "2d")

    def can_execute(self, action_id: str) -> bool:
        # Navigation/load/action buttons must stay enabled so the dashboard can guide the user to the required file.
        if action_id in {
            "vibroseis_open", "vibroseis_load", "vibroseis_sweep", "vibroseis_generate", "vibroseis_productivity",
            "vibroseis_load_vaps", "vibroseis_vaps_qc", "vibroseis_signal_qc", "vibroseis_ground_force",
        }:
            return True
        if action_id in {"vibroseis_correlation", "vibroseis_view_2d", "vibroseis_view_3d", "vibroseis_satellite"}:
            return self._telemetry_data is not None
        return True
