from __future__ import annotations

import csv
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QDoubleSpinBox,
    QHeaderView,
)

from modules.receiver import ReceiverQcEngine, ReceiverQcLimits, ReceiverQcResult, SmtReader, SmtRecord

_QSS = """
QWidget#receiverQcDashboard { background:#F4F7FA; color:#102A3D; font-size:8pt; }
QGroupBox { background:#FFFFFF; border:1px solid #D4DEE8; border-radius:7px; margin-top:8px; padding-top:10px; font-weight:900; color:#15384F; }
QGroupBox::title { subcontrol-origin: margin; left:8px; padding:0 4px; }
QLabel#rxTitle { color:#FFFFFF; font-size:13px; font-weight:900; }
QLabel#rxSub { color:#D7EDF8; font-size:8px; }
QLabel#rxMetric { background:#FFFFFF; border:1px solid #D5E1EA; border-radius:8px; padding:7px 10px; font-size:8pt; font-weight:900; }
QPushButton { min-height:24px; padding:2px 9px; border:1px solid #B8C7D3; border-radius:5px; background:#F7FAFC; font-weight:800; }
QPushButton#primary { background:#0A86C7; border-color:#0873AB; color:#FFFFFF; }
QPushButton#green { background:#15945C; border-color:#117849; color:#FFFFFF; }
QTableWidget { background:#FFFFFF; alternate-background-color:#F7FAFC; border:1px solid #DCE5EC; gridline-color:#E7EDF2; font-size:7.8pt; }
QHeaderView::section { background:#E7F0F6; color:#29495E; border:0; border-bottom:1px solid #D3DFE8; padding:3px 4px; font-weight:900; }
QDoubleSpinBox { min-height:22px; border:1px solid #C3D0DB; border-radius:5px; padding:1px 5px; background:#FFFFFF; }
"""

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
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        header = QWidget()
        header.setStyleSheet("background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #263B5E, stop:1 #0A86C7); border-radius:8px;")
        h = QHBoxLayout(header); h.setContentsMargins(12, 8, 12, 8)
        text = QVBoxLayout(); text.setSpacing(1)
        title = QLabel("Receiver / Geophone SMT QC") ; title.setObjectName("rxTitle")
        sub = QLabel("SMT-200/300 import • resistance/noise/frequency/damping/distortion limits • serial history • failure categories") ; sub.setObjectName("rxSub")
        text.addWidget(title); text.addWidget(sub); h.addLayout(text, 1)
        open_btn = QPushButton("Open SMT File"); open_btn.setObjectName("primary"); open_btn.clicked.connect(self.open_file); h.addWidget(open_btn)
        run_btn = QPushButton("Run QC"); run_btn.setObjectName("green"); run_btn.clicked.connect(self.run_qc); h.addWidget(run_btn)
        export_btn = QPushButton("Export Results CSV"); export_btn.clicked.connect(self.export_results); h.addWidget(export_btn)
        root.addWidget(header)

        self.metrics = QHBoxLayout(); self.metrics.setSpacing(8)
        self.metric_labels: dict[str, QLabel] = {}
        for key, label in (("file", "No file loaded"), ("total", "Records: 0"), ("pass", "PASS: 0"), ("warn", "WARN: 0"), ("fail", "FAIL: 0"), ("dup", "Duplicates: 0")):
            w = QLabel(label); w.setObjectName("rxMetric"); w.setAlignment(Qt.AlignCenter); self.metric_labels[key] = w; self.metrics.addWidget(w)
        root.addLayout(self.metrics)

        self.tabs = QTabWidget(); root.addWidget(self.tabs, 1)
        self._build_records_tab(); self._build_limits_tab(); self._build_failures_tab(); self._build_statistics_tab()

    @staticmethod
    def _prep_table(table: QTableWidget) -> None:
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(22)
        table.horizontalHeader().setStretchLastSection(True)

    def _build_records_tab(self) -> None:
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(6, 6, 6, 6)
        self.records_table = QTableWidget(0, 13)
        self.records_table.setHorizontalHeaderLabels(["Status", "Serial", "String", "Resistance", "Noise", "Distortion", "Freq", "Damping", "Sensitivity", "Impedance", "Polarity", "Tester", "Note"])
        self._prep_table(self.records_table); layout.addWidget(self.records_table)
        self.tabs.addTab(page, "Records")

    def _build_limits_tab(self) -> None:
        page = QWidget(); layout = QHBoxLayout(page); layout.setContentsMargins(6, 6, 6, 6)
        box = QGroupBox("QC Limits")
        form = QFormLayout(box); form.setContentsMargins(10, 8, 10, 8)
        def spin(value: float, hi: float = 999999.0) -> QDoubleSpinBox:
            s = QDoubleSpinBox(); s.setRange(-999999.0, hi); s.setDecimals(4); s.setValue(value); return s
        self.res_min = spin(250); self.res_max = spin(650)
        self.noise_max = spin(20); self.dist_max = spin(0.2)
        self.freq_min = spin(8); self.freq_max = spin(14)
        self.damp_min = spin(0.35); self.damp_max = spin(0.85)
        self.sens_min = spin(0); self.imp_min = spin(0)
        for label, widget in (("Resistance min", self.res_min), ("Resistance max", self.res_max), ("Noise max", self.noise_max), ("Distortion max", self.dist_max), ("Frequency min", self.freq_min), ("Frequency max", self.freq_max), ("Damping min", self.damp_min), ("Damping max", self.damp_max), ("Sensitivity min", self.sens_min), ("Impedance min", self.imp_min)):
            form.addRow(label + ":", widget)
        apply = QPushButton("Apply Limits & Re-run QC"); apply.setObjectName("primary"); apply.clicked.connect(self.run_qc); form.addRow(apply)
        layout.addWidget(box, 0); layout.addStretch(1)
        self.tabs.addTab(page, "Limits")

    def _build_failures_tab(self) -> None:
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(6, 6, 6, 6)
        self.failure_table = QTableWidget(0, 4)
        self.failure_table.setHorizontalHeaderLabels(["Serial/String", "Status", "Findings", "Source"])
        self._prep_table(self.failure_table); layout.addWidget(self.failure_table)
        self.tabs.addTab(page, "Failures")

    def _build_statistics_tab(self) -> None:
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(6, 6, 6, 6)
        self.stats_table = QTableWidget(0, 2); self.stats_table.setHorizontalHeaderLabels(["Metric", "Value"])
        self._prep_table(self.stats_table); self.stats_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        layout.addWidget(self.stats_table)
        self.tabs.addTab(page, "Statistics")

    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open SMT / geophone tester file", str(Path.home()), "SMT/CSV/TXT (*.csv *.txt *.tsv *.dat *.log);;All files (*.*)")
        if not path:
            return
        try:
            self.records = SmtReader().read(path)
            self._path = Path(path)
            self.results = []
            self.metric_labels["file"].setText(self._path.name)
            self.metric_labels["total"].setText(f"Records: {len(self.records):,}")
            self._populate_records()
            self.run_qc()
        except Exception as exc:
            QMessageBox.critical(self, "Receiver SMT Import", str(exc))

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
        self._populate_records(); self._populate_failures(); self._populate_statistics()

    def _populate_records(self) -> None:
        rows = self.results or [ReceiverQcResult(record=r, status="LOADED") for r in self.records]
        self.records_table.setRowCount(0)
        for result in rows:
            r = result.record; row = self.records_table.rowCount(); self.records_table.insertRow(row)
            values = [result.status, r.serial, r.string_id, r.resistance, r.noise, r.distortion, r.frequency, r.damping, r.sensitivity, r.impedance, r.polarity, r.tester, r.note]
            for col, value in enumerate(values):
                item = QTableWidgetItem("" if value is None else str(value)); self.records_table.setItem(row, col, item)
        self.records_table.resizeRowsToContents()

    def _populate_failures(self) -> None:
        self.failure_table.setRowCount(0)
        for result in self.results:
            if result.status == "PASS":
                continue
            r = result.record; row = self.failure_table.rowCount(); self.failure_table.insertRow(row)
            for col, value in enumerate([r.serial or r.string_id, result.status, "; ".join(result.findings), f"{r.source_file}:{r.source_line}"]):
                self.failure_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.failure_table.resizeRowsToContents()

    def _populate_statistics(self) -> None:
        summary = ReceiverQcEngine.summarize(self.results)
        self.metric_labels["pass"].setText(f"PASS: {summary['pass']:,}")
        self.metric_labels["warn"].setText(f"WARN: {summary['warn']:,}")
        self.metric_labels["fail"].setText(f"FAIL: {summary['fail']:,}")
        self.metric_labels["dup"].setText(f"Duplicates: {summary['duplicates']:,}")
        rows = [("QC score", f"{summary['score']}%"), ("Total records", summary["total"]), ("Pass", summary["pass"]), ("Warn", summary["warn"]), ("Fail", summary["fail"]), ("Duplicate serial/string IDs", summary["duplicates"])]
        for cat, count in sorted(summary.get("categories", {}).items()):
            rows.append((f"Finding category: {cat}", count))
        self.stats_table.setRowCount(0)
        for key, value in rows:
            row = self.stats_table.rowCount(); self.stats_table.insertRow(row); self.stats_table.setItem(row, 0, QTableWidgetItem(str(key))); self.stats_table.setItem(row, 1, QTableWidgetItem(str(value)))
        self.stats_table.resizeRowsToContents()

    def export_results(self) -> None:
        if not self.results:
            QMessageBox.information(self, "Receiver QC", "Run QC before export.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Receiver QC", "receiver_smt_qc.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["status", "serial", "string_id", "resistance", "noise", "distortion", "frequency", "damping", "sensitivity", "impedance", "polarity", "tester", "operator", "findings", "source_file", "source_line"])
            for result in self.results:
                r = result.record
                writer.writerow([result.status, r.serial, r.string_id, r.resistance, r.noise, r.distortion, r.frequency, r.damping, r.sensitivity, r.impedance, r.polarity, r.tester, r.operator, "; ".join(result.findings), r.source_file, r.source_line])
        QMessageBox.information(self, "Receiver QC", f"Exported:\n{path}")

    def show_records(self) -> None: self.tabs.setCurrentIndex(0)
    def show_limits(self) -> None: self.tabs.setCurrentIndex(1)
    def show_failures(self) -> None: self.tabs.setCurrentIndex(2)
    def show_statistics(self) -> None: self.tabs.setCurrentIndex(3)

    def can_execute(self, action_id: str) -> bool:
        if action_id in {"receiver_open", "receiver_limits"}:
            return True
        if action_id in {"receiver_run_qc", "receiver_failures", "receiver_export"}:
            return bool(self.records)
        return True
