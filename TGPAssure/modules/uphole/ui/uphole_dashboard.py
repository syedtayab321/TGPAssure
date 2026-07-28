from __future__ import annotations

import csv
from pathlib import Path

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from modules.uphole import UpholeInterpreter, UpholeReader, UpholeShot

_QSS = """
QWidget#upholeDashboard { background:#F4F7FA; color:#102A3D; font-size:8pt; }
QLabel#uhTitle { color:#FFFFFF; font-size:13px; font-weight:900; }
QLabel#uhSub { color:#D7EDF8; font-size:8px; }
QLabel#uhMetric { background:#FFFFFF; border:1px solid #D5E1EA; border-radius:8px; padding:7px 10px; font-size:8pt; font-weight:900; }
QPushButton { min-height:24px; padding:2px 9px; border:1px solid #B8C7D3; border-radius:5px; background:#F7FAFC; font-weight:800; }
QPushButton#primary { background:#0A86C7; border-color:#0873AB; color:#FFFFFF; }
QPushButton#green { background:#15945C; border-color:#117849; color:#FFFFFF; }
QTableWidget { background:#FFFFFF; alternate-background-color:#F7FAFC; border:1px solid #DCE5EC; gridline-color:#E7EDF2; font-size:7.8pt; }
QHeaderView::section { background:#E7F0F6; color:#29495E; border:0; border-bottom:1px solid #D3DFE8; padding:3px 4px; font-weight:900; }
"""

class UpholeDashboard(QWidget):
    """Uphole first-break/time-depth interpretation workspace."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("upholeDashboard")
        self.setProperty("module_id", "uphole")
        self.setStyleSheet(_QSS)
        self.records: list[UpholeShot] = []
        self.layers = []
        self.interpreter = UpholeInterpreter()
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self); root.setContentsMargins(8, 8, 8, 8); root.setSpacing(8)
        header = QWidget(); header.setStyleSheet("background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #3E315C, stop:1 #0A86C7); border-radius:8px;")
        h = QHBoxLayout(header); h.setContentsMargins(12, 8, 12, 8)
        text = QVBoxLayout(); text.setSpacing(1)
        title = QLabel("Uphole QC & Interpretation"); title.setObjectName("uhTitle")
        sub = QLabel("SEG-2/OYO/table import • file-depth assignment • first-break picks • corrected time-depth curve • weathering velocity") ; sub.setObjectName("uhSub")
        text.addWidget(title); text.addWidget(sub); h.addLayout(text, 1)
        open_file = QPushButton("Open File"); open_file.setObjectName("primary"); open_file.clicked.connect(self.open_file); h.addWidget(open_file)
        open_folder = QPushButton("Open Folder"); open_folder.clicked.connect(self.open_folder); h.addWidget(open_folder)
        interpret = QPushButton("Interpret"); interpret.setObjectName("green"); interpret.clicked.connect(self.interpret); h.addWidget(interpret)
        export = QPushButton("Export CSV"); export.clicked.connect(self.export_csv); h.addWidget(export)
        root.addWidget(header)
        metrics = QHBoxLayout(); self.metric_labels = {}
        for key, label in (("records", "Records: 0"), ("points", "Time-depth points: 0"), ("layers", "Layers: 0"), ("velocity", "Velocity: —")):
            w = QLabel(label); w.setObjectName("uhMetric"); w.setAlignment(Qt.AlignCenter); self.metric_labels[key] = w; metrics.addWidget(w)
        root.addLayout(metrics)
        self.tabs = QTabWidget(); root.addWidget(self.tabs, 1)
        self._build_assignment_tab(); self._build_plot_tab(); self._build_layers_tab(); self._build_notes_tab()

    @staticmethod
    def _prep_table(table: QTableWidget) -> None:
        table.setAlternatingRowColors(True); table.setSelectionBehavior(QTableWidget.SelectRows); table.verticalHeader().setVisible(False); table.verticalHeader().setDefaultSectionSize(22); table.horizontalHeader().setStretchLastSection(True)

    def _build_assignment_tab(self) -> None:
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(6, 6, 6, 6)
        self.assignment_table = QTableWidget(0, 9)
        self.assignment_table.setHorizontalHeaderLabels(["File", "Shot", "Depth m", "Offset m", "Pick ms", "Corrected ms", "Channel", "dt ms", "Note"])
        self._prep_table(self.assignment_table); self.assignment_table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed | QTableWidget.AnyKeyPressed)
        layout.addWidget(self.assignment_table); self.tabs.addTab(page, "File / Depth / Picks")

    def _build_plot_tab(self) -> None:
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(6, 6, 6, 6)
        self.td_plot = pg.PlotWidget(); self.td_plot.setBackground("w"); self.td_plot.showGrid(x=True, y=True, alpha=0.2); self.td_plot.setLabel("bottom", "Time", units="ms"); self.td_plot.setLabel("left", "Depth", units="m"); self.td_plot.setTitle("Uphole Time-Depth Curve")
        layout.addWidget(self.td_plot); self.tabs.addTab(page, "Time-Depth")

    def _build_layers_tab(self) -> None:
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(6, 6, 6, 6)
        self.layers_table = QTableWidget(0, 5); self.layers_table.setHorizontalHeaderLabels(["Top m", "Base m", "Top ms", "Base ms", "Velocity m/s"])
        self._prep_table(self.layers_table); self.layers_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); layout.addWidget(self.layers_table); self.tabs.addTab(page, "Layers / Velocity")

    def _build_notes_tab(self) -> None:
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(10, 10, 10, 10)
        note = QLabel("Workflow: load SEG-2/OYO or CSV table, fill missing depth/pick/corrected time cells, then select Interpret. CSV table aliases accepted: depth, pick_ms, corrected_ms, offset, channel, sample_interval, trace_count.")
        note.setWordWrap(True); layout.addWidget(note); layout.addStretch(1); self.tabs.addTab(page, "Guide")

    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open uphole file", str(Path.home()), "Uphole (*.sg2 *.seg2 *.dat *.oyo *.csv *.txt *.fda *.hol *.cho);;All files (*.*)")
        if path:
            self._load(path)

    def open_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open uphole folder", str(Path.home()))
        if path:
            self._load(path)

    def _load(self, path: str) -> None:
        try:
            self.records = UpholeReader().read(path)
            self.layers = []
            self._populate_assignment(); self.interpret()
        except Exception as exc:
            QMessageBox.critical(self, "Uphole Import", str(exc))

    def _sync_from_table(self) -> None:
        records: list[UpholeShot] = []
        for row in range(self.assignment_table.rowCount()):
            def txt(col: int) -> str:
                item = self.assignment_table.item(row, col); return item.text().strip() if item else ""
            def fl(col: int):
                try: return float(txt(col)) if txt(col) else None
                except ValueError: return None
            def integer(col: int):
                try: return int(float(txt(col))) if txt(col) else None
                except ValueError: return None
            records.append(UpholeShot(file_name=txt(0), shot_id=txt(1), depth_m=fl(2), offset_m=fl(3), pick_ms=fl(4), corrected_ms=fl(5), channel=integer(6), sample_interval_ms=fl(7), note=txt(8)))
        self.records = records

    def interpret(self) -> None:
        if not self.records:
            QMessageBox.information(self, "Uphole", "Load uphole files or a pick table first.")
            return
        self._sync_from_table()
        self.layers = self.interpreter.layers(self.records)
        self._populate_plot(); self._populate_layers(); self._update_metrics()

    def _populate_assignment(self) -> None:
        self.assignment_table.setRowCount(0)
        for r in self.records:
            row = self.assignment_table.rowCount(); self.assignment_table.insertRow(row)
            values = [r.file_name, r.shot_id, r.depth_m, r.offset_m, r.pick_ms, r.corrected_ms, r.channel, r.sample_interval_ms, r.note]
            for col, value in enumerate(values):
                self.assignment_table.setItem(row, col, QTableWidgetItem("" if value is None else str(value)))
        self.assignment_table.resizeRowsToContents(); self._update_metrics()

    def _populate_plot(self) -> None:
        self.td_plot.clear()
        td = self.interpreter.build_time_depth(self.records)
        if not td:
            return
        x = [self.interpreter.interpreted_time(r) for r in td]
        y = [r.depth_m for r in td]
        self.td_plot.plot(x, y, pen=pg.mkPen(width=2), symbol="o", symbolSize=6)
        self.td_plot.invertY(False)

    def _populate_layers(self) -> None:
        self.layers_table.setRowCount(0)
        for layer in self.layers:
            row = self.layers_table.rowCount(); self.layers_table.insertRow(row)
            vals = [layer.top_depth_m, layer.base_depth_m, layer.top_time_ms, layer.base_time_ms, round(layer.interval_velocity_m_s, 2)]
            for col, value in enumerate(vals):
                self.layers_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.layers_table.resizeRowsToContents()

    def _update_metrics(self) -> None:
        summary = self.interpreter.summary(self.records)
        self.metric_labels["records"].setText(f"Records: {summary['records']:,}")
        self.metric_labels["points"].setText(f"Time-depth points: {summary['usable_time_depth_points']:,}")
        self.metric_labels["layers"].setText(f"Layers: {summary['layers']:,}")
        avg = summary.get("average_velocity_m_s")
        self.metric_labels["velocity"].setText(f"Avg velocity: {avg:,.1f} m/s" if avg is not None else "Velocity: —")

    def export_csv(self) -> None:
        if not self.records:
            QMessageBox.information(self, "Uphole", "Nothing to export.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export uphole interpretation", "uphole_interpretation.csv", "CSV (*.csv)")
        if not path: return
        self._sync_from_table()
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["file", "shot", "depth_m", "offset_m", "pick_ms", "corrected_ms", "channel", "sample_interval_ms", "note"])
            for r in self.records:
                writer.writerow([r.file_name, r.shot_id, r.depth_m, r.offset_m, r.pick_ms, r.corrected_ms, r.channel, r.sample_interval_ms, r.note])
            writer.writerow([]); writer.writerow(["top_depth_m", "base_depth_m", "top_time_ms", "base_time_ms", "interval_velocity_m_s"])
            for l in self.layers:
                writer.writerow([l.top_depth_m, l.base_depth_m, l.top_time_ms, l.base_time_ms, l.interval_velocity_m_s])
        QMessageBox.information(self, "Uphole", f"Exported:\n{path}")

    def show_assignment(self) -> None: self.tabs.setCurrentIndex(0)
    def show_time_depth(self) -> None: self.tabs.setCurrentIndex(1)
    def show_layers(self) -> None: self.tabs.setCurrentIndex(2)
    def show_guide(self) -> None: self.tabs.setCurrentIndex(3)

    def can_execute(self, action_id: str) -> bool:
        if action_id in {"uphole_open", "uphole_open_folder"}:
            return True
        if action_id in {"uphole_interpret", "uphole_export", "uphole_time_depth", "uphole_layers"}:
            return bool(self.records)
        return True
