from __future__ import annotations

from pathlib import Path
from typing import Optional
import csv

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QDoubleSpinBox,
    QHeaderView,
    QAbstractItemView,
)

from modules.vibroseis import SweepParameters, VibroseisEngine
from modules.vibroseis.vaps_reader import VapsReader, VapsQcEngine, VapsRecord
from modules.vibroseis.ui.classic_vaps_analyser import ClassicVapsAnalyser, DISPLAY_ATTRS
from modules.vibroseis.ui.vibroseis_results_dialog import VapsQcResultsDialog


_VIB_QSS = """
QWidget#vibroseisDashboard {
    background:#F3F3F3;
    color:#111111;
    font-family: Arial, Helvetica, sans-serif;
    font-size:7.7pt;
}
QTabWidget#vibTabs::pane {
    border:1px solid #B8B8B8;
    background:#F3F3F3;
    top:-1px;
}
QTabWidget#vibTabs QTabBar::tab {
    background:#E7E7E7;
    color:#111111;
    border:1px solid #B9B9B9;
    padding:3px 12px;
    min-height:18px;
    font-size:7.7pt;
    font-weight:600;
}
QTabWidget#vibTabs QTabBar::tab:selected {
    background:#FFFFFF;
    border-bottom-color:#FFFFFF;
    color:#006B8F;
    font-weight:800;
}
QGroupBox {
    border:1px solid #A9A9A9;
    margin-top:6px;
    padding-top:8px;
    background:#F3F3F3;
    font-size:7.6pt;
    font-weight:700;
}
QGroupBox::title { subcontrol-origin: margin; left:7px; padding:0 3px; }
QLabel { background:transparent; font-size:7.6pt; }
QLabel#statusLine {
    color:#202020;
    border-top:1px solid #D2D2D2;
    padding:2px 4px;
}
QPushButton {
    background:#ECECEC;
    border:1px outset #D0D0D0;
    min-height:22px;
    max-height:26px;
    padding:1px 7px;
    font-size:7.5pt;
}
QPushButton:pressed { border:1px inset #D0D0D0; background:#DCDCDC; }
QComboBox, QDoubleSpinBox, QLineEdit {
    min-height:20px;
    max-height:24px;
    font-size:7.5pt;
    background:#FFFFFF;
    border:1px solid #B6B6B6;
    padding:1px 4px;
}
QTableWidget {
    background:#FFFFFF;
    alternate-background-color:#F7F7F7;
    gridline-color:#E0E0E0;
    font-size:7.4pt;
}
QHeaderView::section {
    background:#E4E4E4;
    color:#111111;
    border:0;
    border-right:1px solid #D0D0D0;
    border-bottom:1px solid #D0D0D0;
    padding:2px 3px;
    font-size:7.4pt;
    font-weight:700;
}
"""


class VibroseisDashboard(QWidget):
    """Compact Vibroseis workspace with only Sweep, Manual QC and VAPS Analyser.

    All VAPS Analyser command buttons and display choices are controlled from
    the main top ribbon.  The workspace itself stays clean and close to the
    supplied classic analyser layout.
    """

    page_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("vibroseisDashboard")
        self.setProperty("module_id", "vibroseis")
        self.setStyleSheet(_VIB_QSS)
        self.engine = VibroseisEngine()
        self._telemetry_path: Optional[Path] = None
        self._telemetry_names: list[str] = []
        self._telemetry_data: Optional[np.ndarray] = None
        self._vaps_path: Optional[Path] = None
        self._vaps_records: list[VapsRecord] = []
        self._manual_qc_rows: list[list[str]] = []
        self._last_sweep = None
        self._build_ui()
        self.show_classic_vaps()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(3, 3, 3, 3)
        root.setSpacing(3)

        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("vibTabs")
        self.tabs.setDocumentMode(True)
        self.tabs.currentChanged.connect(self._emit_page_change)
        root.addWidget(self.tabs, 1)

        self._build_sweep_tab()
        self._build_manual_qc_tab()
        self._build_classic_vaps_tab()

        self.status_badge = QLabel("VAPS Analyser ready")
        self.status_badge.setObjectName("statusLine")
        root.addWidget(self.status_badge)
        self._plot_placeholder(self.sweep_plot, "Pilot Sweep", "Use the top ribbon: Sweep → Generate Sweep.")
        self._plot_placeholder(self.spectrum_plot, "Normalized Sweep Spectrum", "No sweep generated.")
        self._plot_placeholder(self.klauder_plot, "Klauder Wavelet", "No sweep generated.")
        self._plot_placeholder(self.manual_vib_plot, "Manual Vibroseis QC Preview", "Use the top ribbon: Manual QC → Add / Export / Clear.")

    def active_ribbon_context(self) -> str:
        index = self.tabs.currentIndex()
        if index == 0:
            return "sweep"
        if index == 1:
            return "manual"
        return "vaps"

    def _emit_page_change(self, _index: int = -1) -> None:
        self.page_changed.emit(self.active_ribbon_context())

    def _spin(self, lo: float, hi: float, value: float, decimals: int = 2, suffix: str = "") -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(lo, hi)
        spin.setDecimals(decimals)
        spin.setValue(value)
        spin.setSuffix(suffix)
        spin.setKeyboardTracking(False)
        return spin

    @staticmethod
    def _style_plot(plot: pg.PlotWidget, title: str) -> None:
        plot.setBackground("w")
        plot.showGrid(x=True, y=True, alpha=0.18)
        plot.setTitle(title, color="#202020", size="8pt")
        try:
            plot.getAxis("left").setStyle(tickFont=QFont("Arial", 7))
            plot.getAxis("bottom").setStyle(tickFont=QFont("Arial", 7))
        except Exception:
            pass

    @staticmethod
    def _plot_placeholder(plot: pg.PlotWidget, title: str, message: str) -> None:
        plot.clear()
        plot.setTitle(title, color="#202020", size="8pt")
        try:
            text = pg.TextItem(message, color="#555555", anchor=(0.5, 0.5))
            text.setFont(QFont("Arial", 8))
            plot.addItem(text)
            text.setPos(0.5, 0.5)
            plot.setXRange(0, 1, padding=0)
            plot.setYRange(0, 1, padding=0)
        except Exception:
            pass

    @staticmethod
    def _prepare_table(table: QTableWidget) -> None:
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(19)
        table.horizontalHeader().setStretchLastSection(True)

    def _build_sweep_tab(self) -> None:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        controls = QGroupBox("Sweep Parameters")
        controls.setMaximumWidth(245)
        form = QFormLayout(controls)
        form.setContentsMargins(6, 8, 6, 6)
        form.setSpacing(3)
        self.f0 = self._spin(0.1, 1000, 5, 2, " Hz")
        self.f1 = self._spin(0.1, 1000, 100, 2, " Hz")
        self.duration = self._spin(0.1, 300, 12, 3, " s")
        self.fs = self._spin(10, 100000, 1000, 1, " Hz")
        self.sweep_type = QComboBox()
        self.sweep_type.addItems(["Linear", "Logarithmic"])
        self.taper_in = self._spin(0, 30, 0.25, 3, " s")
        self.taper_out = self._spin(0, 30, 0.25, 3, " s")
        self.amplitude = self._spin(0, 1e9, 1, 4)
        self.phase = self._spin(-360, 360, 0, 1, "°")
        for label, widget in [
            ("Start frequency", self.f0),
            ("End frequency", self.f1),
            ("Sweep length", self.duration),
            ("Sample rate", self.fs),
            ("Sweep type", self.sweep_type),
            ("Start taper", self.taper_in),
            ("End taper", self.taper_out),
            ("Amplitude", self.amplitude),
            ("Initial phase", self.phase),
        ]:
            form.addRow(label + ":", widget)
        gen = QPushButton("Generate Sweep")
        gen.clicked.connect(self.design_sweep)
        form.addRow(gen)
        export = QPushButton("Export Pilot CSV")
        export.clicked.connect(self.export_pilot)
        form.addRow(export)
        layout.addWidget(controls, 0)

        plots = QSplitter(Qt.Orientation.Vertical)
        self.sweep_plot = pg.PlotWidget()
        self.sweep_plot.setLabel("bottom", "Time", units="s")
        self.sweep_plot.setLabel("left", "Amplitude")
        self._style_plot(self.sweep_plot, "Pilot Sweep")
        self.spectrum_plot = pg.PlotWidget()
        self.spectrum_plot.setLabel("bottom", "Frequency", units="Hz")
        self.spectrum_plot.setLabel("left", "Amplitude")
        self._style_plot(self.spectrum_plot, "Normalized Sweep Spectrum")
        self.klauder_plot = pg.PlotWidget()
        self.klauder_plot.setLabel("bottom", "Lag", units="s")
        self.klauder_plot.setLabel("left", "Correlation")
        self._style_plot(self.klauder_plot, "Klauder Wavelet")
        plots.addWidget(self.sweep_plot)
        plots.addWidget(self.spectrum_plot)
        plots.addWidget(self.klauder_plot)
        plots.setSizes([190, 155, 155])
        layout.addWidget(plots, 1)
        self.tabs.addTab(page, "Sweep")

    def _build_manual_qc_tab(self) -> None:
        page = QWidget()
        root = QHBoxLayout(page)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        controls = QGroupBox("Manual QC Mark")
        controls.setMaximumWidth(250)
        form = QFormLayout(controls)
        form.setContentsMargins(6, 8, 6, 6)
        form.setSpacing(3)
        self.manual_vib_source = QComboBox()
        self.manual_vib_source.addItems(["Current VAPS attribute", "Telemetry summary", "General observation"])
        self.manual_vib_status = QComboBox()
        self.manual_vib_status.addItems(["Review", "Pass", "Suspect", "Reject", "Timing", "Phase", "Force", "Sweep distortion", "GPS/position"])
        self.manual_vib_comment = QLineEdit()
        self.manual_vib_comment.setPlaceholderText("Manual note / observation")
        add_btn = QPushButton("Add Mark")
        add_btn.clicked.connect(self._add_manual_vib_qc)
        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self._export_manual_vib_qc)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_manual_vib_qc)
        form.addRow("QC source:", self.manual_vib_source)
        form.addRow("Status:", self.manual_vib_status)
        form.addRow("Comment:", self.manual_vib_comment)
        form.addRow(add_btn)
        form.addRow(export_btn)
        form.addRow(clear_btn)
        root.addWidget(controls, 0)

        right = QWidget()
        layout = QVBoxLayout(right)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.manual_vib_table = QTableWidget(0, 8)
        self.manual_vib_table.setHorizontalHeaderLabels(["Source", "Record/Trace", "Vib", "Attribute", "Value", "Status", "Comment", "File"])
        self._prepare_table(self.manual_vib_table)
        self.manual_vib_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.manual_vib_table.horizontalHeader().setStretchLastSection(True)
        self.manual_vib_plot = pg.PlotWidget()
        self.manual_vib_plot.setLabel("bottom", "Record / sample")
        self.manual_vib_plot.setLabel("left", "QC value")
        self._style_plot(self.manual_vib_plot, "Manual Vibroseis QC Preview")
        layout.addWidget(self.manual_vib_table, 1)
        layout.addWidget(self.manual_vib_plot, 1)
        root.addWidget(right, 1)
        self.tabs.addTab(page, "Manual QC")

    def _build_classic_vaps_tab(self) -> None:
        self.classic_vaps_analyser = ClassicVapsAnalyser(self)
        self.classic_vaps_analyser.records_loaded.connect(self._sync_classic_vaps_records)
        self.tabs.addTab(self.classic_vaps_analyser, "VAPS Analyser")

    # ---------- page switching / ribbon integration ----------
    def show_sweep(self) -> None:
        self.tabs.setCurrentIndex(0)
        self._emit_page_change()

    def show_manual_qc(self) -> None:
        self.tabs.setCurrentIndex(1)
        self._emit_page_change()

    def show_classic_vaps(self) -> None:
        self.tabs.setCurrentIndex(2)
        self._emit_page_change()

    def show_vaps_qc(self) -> None:
        self.show_classic_vaps()

    def show_signal_qc(self) -> None:
        self.show_manual_qc()

    def show_ground_force(self) -> None:
        self.show_manual_qc()

    def show_productivity(self) -> None:
        self.show_sweep()

    def show_geospatial_view(self, mode: str = "2d") -> None:
        del mode
        self.show_classic_vaps()

    def handle_ribbon_action(self, action_id: str) -> None:
        if action_id in {"vibroseis_open", "vibroseis_vaps_view", "vibroseis_page_vaps"}:
            self.show_classic_vaps()
        elif action_id in {"vibroseis_sweep", "vibroseis_page_sweep"}:
            self.show_sweep()
        elif action_id in {"vibroseis_manual_qc", "vibroseis_page_manual"}:
            self.show_manual_qc()
        elif action_id == "vibroseis_generate":
            self.show_sweep(); self.design_sweep()
        elif action_id == "vibroseis_export_pilot":
            self.show_sweep(); self.export_pilot()
        elif action_id in {"vibroseis_load", "vibroseis_open_telemetry"}:
            self.show_manual_qc(); self.open_telemetry()
        elif action_id in {"vibroseis_load_vaps", "vibroseis_vaps_open"}:
            self.show_classic_vaps(); self.open_vaps(run_after_load=False)
        elif action_id == "vibroseis_vaps_qc":
            self.show_classic_vaps(); self.run_vaps_qc()
        elif action_id == "vibroseis_auto_qc":
            self.run_automated_vibroseis_qc()
        elif action_id == "vibroseis_vaps_print":
            self.show_classic_vaps(); self.classic_vaps_analyser.print_view()
        elif action_id == "vibroseis_vaps_bmp":
            self.show_classic_vaps(); self.classic_vaps_analyser.export_bmp()
        elif action_id == "vibroseis_vaps_end":
            self.show_classic_vaps(); self.classic_vaps_analyser.clear_records(); self._vaps_records = []; self._vaps_path = None
        elif action_id == "vibroseis_vaps_all":
            self.show_classic_vaps(); self.classic_vaps_analyser.select_all_vibs()
        elif action_id == "vibroseis_vaps_none":
            self.show_classic_vaps(); self.classic_vaps_analyser.select_no_vibs()
        elif action_id == "vibroseis_vaps_reset":
            self.show_classic_vaps(); self.classic_vaps_analyser.reset_to_loaded()
        elif action_id == "vibroseis_vaps_mode_raw":
            self.show_classic_vaps(); self.classic_vaps_analyser.set_raw_mode()
        elif action_id == "vibroseis_vaps_mode_filtered":
            self.show_classic_vaps(); self.classic_vaps_analyser.set_filtered_mode()
        elif action_id.startswith("vibroseis_vaps_attr_"):
            self.show_classic_vaps(); self.classic_vaps_analyser.set_attribute(action_id.replace("vibroseis_vaps_attr_", "", 1))
        elif action_id == "vibroseis_manual_add":
            self.show_manual_qc(); self._add_manual_vib_qc()
        elif action_id == "vibroseis_manual_export":
            self.show_manual_qc(); self._export_manual_vib_qc()
        elif action_id == "vibroseis_manual_clear":
            self.show_manual_qc(); self._clear_manual_vib_qc()
        elif action_id in {"vibroseis_signal_qc", "vibroseis_correlation", "vibroseis_ground_force"}:
            self.show_manual_qc()
            QMessageBox.information(self, "Vibroseis QC", "This simplified screen keeps Manual QC, Sweep and VAPS Analyser only. Use Manual QC for notes or VAPS Analyser for field vibrator QC.")
        elif action_id == "vibroseis_productivity":
            self.show_sweep()

    def can_execute(self, action_id: str) -> bool:
        if action_id.startswith("vibroseis_"):
            return True
        return True

    # ---------- Sweep ----------
    def design_sweep(self) -> None:
        try:
            params = SweepParameters(
                start_frequency_hz=self.f0.value(),
                end_frequency_hz=self.f1.value(),
                duration_s=self.duration.value(),
                sample_rate_hz=self.fs.value(),
                sweep_type=self.sweep_type.currentText().lower(),
                taper_in_s=self.taper_in.value(),
                taper_out_s=self.taper_out.value(),
                amplitude=self.amplitude.value(),
                phase_deg=self.phase.value(),
            )
            result = self.engine.design_sweep(params)
            self._last_sweep = result
            self.sweep_plot.clear()
            self.sweep_plot.plot(result.time_s, result.samples, pen=pg.mkPen("#005A82", width=1.0))
            self.sweep_plot.setTitle("Pilot Sweep", color="#202020", size="8pt")
            self.spectrum_plot.clear()
            self.spectrum_plot.plot(result.frequency_hz, result.amplitude_spectrum, pen=pg.mkPen("#1A7F37", width=1.0))
            self.spectrum_plot.setTitle("Normalized Sweep Spectrum", color="#202020", size="8pt")
            self.klauder_plot.clear()
            self.klauder_plot.plot(result.autocorrelation_lag_s, result.klauder_wavelet, pen=pg.mkPen("#9A5B00", width=1.0))
            self.klauder_plot.setTitle("Klauder Wavelet", color="#202020", size="8pt")
            self.status_badge.setText("Sweep generated")
        except Exception as exc:
            QMessageBox.critical(self, "Sweep Design Error", str(exc))

    def export_pilot(self) -> None:
        if self._last_sweep is None:
            QMessageBox.information(self, "Export Pilot", "Generate a sweep first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Vibroseis Pilot", "vibroseis_pilot.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            np.savetxt(
                path,
                np.column_stack([self._last_sweep.time_s, self._last_sweep.samples, self._last_sweep.instantaneous_frequency_hz]),
                delimiter=",",
                header="time_s,pilot_amplitude,instantaneous_frequency_hz",
                comments="",
            )
            self.status_badge.setText(f"Pilot CSV exported: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Pilot", str(exc))

    # ---------- VAPS ----------
    def open_vaps(self, run_after_load: bool = False) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open VAPS / H26 vibrator attributes",
            str(Path.home()),
            "VAPS/H26/Text (*.vaps *.h26 *.csv *.txt *.dat *.log);;All Files (*.*)",
        )
        if not path:
            return
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            records = VapsReader().read(path)
            self._sync_classic_vaps_records(records, Path(path))
            self.classic_vaps_analyser.load_records(records, Path(path))
            self.status_badge.setText(f"Loaded {len(records):,} VAPS/H26 records: {Path(path).name}")
            if run_after_load:
                self.run_vaps_qc()
        except Exception as exc:
            QMessageBox.critical(self, "VAPS/H26 Import Error", str(exc))
        finally:
            QApplication.restoreOverrideCursor()

    def _sync_classic_vaps_records(self, records: list[VapsRecord], path: object = None) -> None:
        self._vaps_records = list(records or [])
        self._vaps_path = Path(path) if path else None
        self.status_badge.setText(f"Loaded {len(self._vaps_records):,} VAPS/H26 records" if self._vaps_records else "No VAPS/H26 file loaded")

    @staticmethod
    def _normalize_vib_id(value: object) -> str:
        text = str(value or "").strip()
        digits = "".join(ch for ch in text if ch.isdigit())
        return str(int(digits)) if digits else text

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

    def _selected_vaps_records(self) -> list[VapsRecord]:
        selected = self.classic_vaps_analyser.selected_vibs() if hasattr(self, "classic_vaps_analyser") else set()
        records = list(self._vaps_records)
        if selected:
            records = [record for record in records if self._normalize_vib_id(record.vib) in selected]
        if hasattr(self, "classic_vaps_analyser") and self.classic_vaps_analyser.filtered_radio.isChecked():
            attr, _label = self.classic_vaps_analyser.selected_attr()
            records = [record for record in records if self._vaps_metric_value(record, attr) is not None]
        return records

    def run_vaps_qc(self) -> None:
        if not self._vaps_records:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setWindowTitle("VAPS / H26 Field QC")
            msg.setText("Load a VAPS/H26 file first.")
            open_btn = msg.addButton("Open VAPS/H26", QMessageBox.ButtonRole.AcceptRole)
            msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            msg.exec()
            if msg.clickedButton() is open_btn:
                self.open_vaps(run_after_load=False)
            return
        try:
            engine = VapsQcEngine()
            summary = engine.summarize(self._vaps_records)
            attr, label = self.classic_vaps_analyser.selected_attr()
            records = self._selected_vaps_records() or list(self._vaps_records)
            self.status_badge.setText(
                f"VAPS QC complete: {summary.get('pass', 0):,} pass / {summary.get('fail', 0):,} fail / {summary.get('records', 0):,} records"
            )
            VapsQcResultsDialog(summary, records, attr, label, self._vaps_metric_value, self).exec()
        except Exception as exc:
            QMessageBox.critical(self, "VAPS Field QC Error", str(exc))

    # ---------- Manual QC and telemetry ----------
    def open_telemetry(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Vibroseis telemetry", str(Path.home()), "Data (*.csv *.txt *.dat *.log);;All Files (*.*)")
        if not path:
            return
        try:
            names, data = self.engine.load_numeric_table(path)
            self._telemetry_path = Path(path)
            self._telemetry_names = list(names)
            self._telemetry_data = np.asarray(data, dtype=float)
            self.status_badge.setText(f"Telemetry loaded: {self._telemetry_path.name} — {data.shape[0]:,} rows × {data.shape[1]} columns")
        except Exception as exc:
            QMessageBox.critical(self, "Vibroseis Telemetry", str(exc))

    def _add_manual_vib_qc(self) -> None:
        source_mode = self.manual_vib_source.currentText()
        status = self.manual_vib_status.currentText()
        comment = self.manual_vib_comment.text().strip()
        file_name = str(self._vaps_path or self._telemetry_path or "No file loaded")
        if source_mode.startswith("Current VAPS") and self._vaps_records:
            records = self._selected_vaps_records() or list(self._vaps_records)
            record = records[0]
            attr, label = self.classic_vaps_analyser.selected_attr()
            value = self._vaps_metric_value(record, attr)
            values = ["VAPS/H26", str(record.source_line), str(record.vib), label, "" if value is None else f"{value:.6g}", status, comment or "Manual VAPS attribute observation", file_name]
            self._plot_manual_vib_preview_from_vaps(attr, label)
        elif source_mode.startswith("Telemetry") and self._telemetry_data is not None:
            col = 0
            values_array = np.asarray(self._telemetry_data[:, col], dtype=float)
            finite = values_array[np.isfinite(values_array)]
            metric = float(np.sqrt(np.mean(np.square(finite)))) if finite.size else float("nan")
            name = self._telemetry_names[col] if self._telemetry_names else "Column 1"
            values = ["Telemetry", "all", "—", f"RMS {name}", f"{metric:.6g}", status, comment or "Manual telemetry observation", file_name]
            self._plot_manual_vib_preview_from_telemetry(col, name)
        else:
            values = ["Manual", "—", "—", "General", "—", status, comment or "Manual vibroseis QC observation", file_name]
        self._append_manual_vib_row(values)

    def _append_manual_vib_row(self, values: list[str]) -> None:
        self._manual_qc_rows.append(list(values))
        row = self.manual_vib_table.rowCount()
        self.manual_vib_table.insertRow(row)
        for col, value in enumerate(values):
            self.manual_vib_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.status_badge.setText(f"Manual QC marks: {len(self._manual_qc_rows)}")

    def _plot_manual_vib_preview_from_vaps(self, attr: str, label: str) -> None:
        self.manual_vib_plot.clear()
        records = self._selected_vaps_records() or list(self._vaps_records)
        x, y = [], []
        for idx, record in enumerate(records):
            value = self._vaps_metric_value(record, attr)
            if value is not None:
                x.append(idx + 1)
                y.append(value)
        if x:
            self.manual_vib_plot.plot(np.asarray(x), np.asarray(y), pen=pg.mkPen("#005A82", width=1.0), symbol="o", symbolSize=3)
        self.manual_vib_plot.setTitle(f"Manual QC Preview — {label}", color="#202020", size="8pt")
        self.manual_vib_plot.setLabel("left", label)

    def _plot_manual_vib_preview_from_telemetry(self, col: int, name: str) -> None:
        if self._telemetry_data is None:
            return
        self.manual_vib_plot.clear()
        values = np.asarray(self._telemetry_data[:, col], dtype=float)
        max_points = min(values.size, 5000)
        self.manual_vib_plot.plot(np.arange(max_points), values[:max_points], pen=pg.mkPen("#1A7F37", width=1.0))
        self.manual_vib_plot.setTitle(f"Manual QC Preview — {name}", color="#202020", size="8pt")
        self.manual_vib_plot.setLabel("left", name)

    def _clear_manual_vib_qc(self) -> None:
        self._manual_qc_rows.clear()
        self.manual_vib_table.setRowCount(0)
        self._plot_placeholder(self.manual_vib_plot, "Manual Vibroseis QC Preview", "Manual QC table cleared.")
        self.status_badge.setText("Manual QC cleared")

    def _export_manual_vib_qc(self) -> None:
        if not self._manual_qc_rows:
            QMessageBox.information(self, "Manual Vibroseis QC", "There are no manual QC rows to export.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Manual Vibroseis QC", "vibroseis_manual_qc.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            headers = [self.manual_vib_table.horizontalHeaderItem(c).text() for c in range(self.manual_vib_table.columnCount())]
            with Path(path).open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(headers)
                writer.writerows(self._manual_qc_rows)
            self.status_badge.setText("Manual QC CSV exported")
        except Exception as exc:
            QMessageBox.warning(self, "Manual Vibroseis QC", str(exc))

    def run_automated_vibroseis_qc(self) -> None:
        if self._vaps_records:
            self.show_classic_vaps()
            self.run_vaps_qc()
            return
        QMessageBox.information(self, "Automated QC", "Load VAPS/H26 data first. The simplified Vibroseis workspace now focuses on VAPS Analyser, Manual QC and Sweep only.")

    # Legacy action compatibility. These remain safe no-ops/messages so old
    # shortcut/action ids cannot crash the simplified screen.
    def run_signal_qc(self) -> None:
        self.show_manual_qc()
        QMessageBox.information(self, "Source Signal QC", "Use Manual QC in this simplified Vibroseis screen.")

    def correlate_trace(self) -> None:
        self.show_manual_qc()
        QMessageBox.information(self, "Correlation", "Use Manual QC in this simplified Vibroseis screen.")

    def calculate_ground_force(self) -> None:
        self.show_manual_qc()
        QMessageBox.information(self, "Ground Force", "Use Manual QC in this simplified Vibroseis screen.")

    def calculate_productivity(self) -> None:
        self.show_sweep()
        QMessageBox.information(self, "Productivity", "Use the Sweep tab in this simplified Vibroseis screen.")


__all__ = ["VibroseisDashboard", "DISPLAY_ATTRS"]
