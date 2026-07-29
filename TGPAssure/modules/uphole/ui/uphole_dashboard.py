from __future__ import annotations

import csv
from pathlib import Path
from statistics import mean
from typing import Iterable

import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFileDialog,
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from modules.uphole import UpholeInterpreter, UpholeReader, UpholeShot

_QSS = """
QWidget#upholeDashboard {
    background:#F4F7FA;
    color:#102A3D;
    font-family:Poppins, Segoe UI, Arial;
    font-size:8pt;
}
QLabel { background:transparent; }
QFrame#heroCard {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #28345F, stop:0.55 #086D9E, stop:1 #15A4C8);
    border-radius:9px;
}
QLabel#uhTitle { color:#FFFFFF; font-size:13px; font-weight:900; background:transparent; }
QLabel#uhSub { color:#D7EDF8; font-size:7.4pt; background:transparent; }
QFrame#metricCard {
    background:#FFFFFF;
    border:1px solid #D5E1EA;
    border-left:4px solid #0A86C7;
    border-radius:8px;
}
QLabel#metricCaption { color:#5A6C7E; font-size:7pt; font-weight:800; background:transparent; }
QLabel#metricValue { color:#0A2A44; font-size:12px; font-weight:900; background:transparent; }
QFrame#sideBar {
    background:#FFFFFF;
    border:1px solid #D7E2EC;
    border-radius:9px;
}
QLabel#sideTitle { color:#456073; font-size:7.5pt; font-weight:900; background:#F3F6FA; border-radius:5px; padding:5px; }
QPushButton#navButton {
    border:0;
    border-radius:7px;
    background:transparent;
    color:#123047;
    text-align:left;
    padding:7px 10px;
    font-size:8pt;
    font-weight:800;
}
QPushButton#navButton:hover { background:#EAF5FB; color:#075F89; }
QPushButton#navButton:checked { background:#0A87C6; color:#FFFFFF; }
QPushButton {
    min-height:24px;
    padding:3px 10px;
    border:1px solid #B8C7D3;
    border-radius:7px;
    background:#F7FAFC;
    color:#102A3D;
    font-weight:800;
}
QPushButton:hover { background:#EAF5FB; border-color:#0A86C7; }
QPushButton#primary { background:#0A86C7; border-color:#0873AB; color:#FFFFFF; }
QPushButton#primary:hover { background:#0874AD; }
QPushButton#green { background:#15945C; border-color:#117849; color:#FFFFFF; }
QPushButton#green:hover { background:#117B4D; }
QPushButton#orange { background:#D97706; border-color:#B96105; color:#FFFFFF; }
QPushButton#orange:hover { background:#B96105; }
QFrame#panel {
    background:#FFFFFF;
    border:1px solid #D7E2EC;
    border-radius:9px;
}
QLabel#panelTitle { color:#0D3150; font-size:10px; font-weight:900; background:transparent; }
QLabel#hintBox { color:#4F6173; background:#EEF7FC; border:1px solid #CDE7F4; border-radius:7px; padding:7px; }
QTableWidget {
    background:#FFFFFF;
    alternate-background-color:#F7FAFC;
    border:1px solid #DCE5EC;
    gridline-color:#E7EDF2;
    font-size:7.8pt;
    selection-background-color:#D7F0FB;
    selection-color:#0A2A44;
}
QHeaderView::section {
    background:#E7F0F6;
    color:#29495E;
    border:0;
    border-right:1px solid #D3DFE8;
    border-bottom:1px solid #D3DFE8;
    padding:4px 5px;
    font-weight:900;
}
QProgressBar {
    background:#EEF3F7;
    border:1px solid #CFE0EC;
    border-radius:6px;
    text-align:center;
    color:#0A2A44;
    font-weight:800;
    min-height:14px;
    max-height:15px;
}
QProgressBar::chunk { background:#0A86C7; border-radius:5px; }
QFrame#loader {
    background:#FFF7E8;
    border:1px solid #F4C989;
    border-radius:8px;
}
QLabel#loaderTitle { color:#7A4300; font-weight:900; background:transparent; }
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
        self._interpreting = False
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(7)

        hero = QFrame()
        hero.setObjectName("heroCard")
        hero.setMaximumHeight(68)
        h = QHBoxLayout(hero)
        h.setContentsMargins(12, 7, 12, 7)
        h.setSpacing(8)
        text = QVBoxLayout()
        text.setSpacing(1)
        title = QLabel("Uphole QC & Interpretation")
        title.setObjectName("uhTitle")
        sub = QLabel("SEG-2/OYO/table import • depth assignment • first-break picks • time-depth curve • weathering velocity")
        sub.setObjectName("uhSub")
        sub.setWordWrap(True)
        text.addWidget(title)
        text.addWidget(sub)
        h.addLayout(text, 1)
        self.open_file_btn = QPushButton("Open File")
        self.open_file_btn.setObjectName("primary")
        self.open_file_btn.clicked.connect(self.open_file)
        h.addWidget(self.open_file_btn)
        self.open_folder_btn = QPushButton("Open Folder")
        self.open_folder_btn.clicked.connect(self.open_folder)
        h.addWidget(self.open_folder_btn)
        self.interpret_btn = QPushButton("Interpret")
        self.interpret_btn.setObjectName("green")
        self.interpret_btn.clicked.connect(self.interpret)
        h.addWidget(self.interpret_btn)
        self.export_btn = QPushButton("Export CSV")
        self.export_btn.setObjectName("orange")
        self.export_btn.clicked.connect(self.export_csv)
        h.addWidget(self.export_btn)
        root.addWidget(hero)

        self.loader = QFrame()
        self.loader.setObjectName("loader")
        loader_layout = QHBoxLayout(self.loader)
        loader_layout.setContentsMargins(10, 5, 10, 5)
        loader_layout.setSpacing(8)
        loader_label = QLabel("Interpreting uphole records and rebuilding velocity products…")
        loader_label.setObjectName("loaderTitle")
        loader_layout.addWidget(loader_label)
        self.loader_progress = QProgressBar()
        self.loader_progress.setRange(0, 0)
        loader_layout.addWidget(self.loader_progress, 1)
        self.loader.setVisible(False)
        root.addWidget(self.loader)

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(7)
        metrics.setVerticalSpacing(6)
        self.metric_values: dict[str, QLabel] = {}
        for i, (key, caption, value, color) in enumerate(
            (
                ("records", "RECORDS", "0", "#0A86C7"),
                ("points", "TIME-DEPTH POINTS", "0", "#15945C"),
                ("layers", "LAYERS", "0", "#7656A5"),
                ("velocity", "AVG VELOCITY", "—", "#D97706"),
            )
        ):
            card, val = self._metric_card(caption, value, color)
            self.metric_values[key] = val
            metrics.addWidget(card, 0, i)
        root.addLayout(metrics)

        content = QHBoxLayout()
        content.setSpacing(7)
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sideBar")
        self.sidebar.setFixedWidth(174)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(8, 8, 8, 8)
        side.setSpacing(5)
        side_title = QLabel("UPHOLE")
        side_title.setObjectName("sideTitle")
        side.addWidget(side_title)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: list[QPushButton] = []
        for index, label in enumerate(("Overview", "File / Depth / Picks", "Time-Depth", "Layers / Velocity", "QC Summary", "Guide")):
            button = QPushButton(label)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.clicked.connect(lambda _=False, i=index: self._set_page(i))
            self.nav_group.addButton(button, index)
            self.nav_buttons.append(button)
            side.addWidget(button)
        side.addStretch(1)
        content.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        content.addWidget(self.stack, 1)
        root.addLayout(content, 1)

        self._build_overview_page()
        self._build_assignment_page()
        self._build_plot_page()
        self._build_layers_page()
        self._build_qc_page()
        self._build_guide_page()
        self._set_page(0)

    def _metric_card(self, caption: str, value: str, color: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName("metricCard")
        card.setStyleSheet(f"QFrame#metricCard {{ border-left:4px solid {color}; }}")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(1)
        cap = QLabel(caption)
        cap.setObjectName("metricCaption")
        val = QLabel(value)
        val.setObjectName("metricValue")
        layout.addWidget(cap)
        layout.addWidget(val)
        return card, val

    @staticmethod
    def _panel(title: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)
        label = QLabel(title)
        label.setObjectName("panelTitle")
        layout.addWidget(label)
        return frame, layout

    @staticmethod
    def _prep_table(table: QTableWidget) -> None:
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(22)
        table.horizontalHeader().setStretchLastSection(True)

    def _build_overview_page(self) -> None:
        page = QWidget()
        layout = QGridLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        panel, left = self._panel("Interpretation Overview")
        self.overview_plot = pg.PlotWidget()
        self.overview_plot.setBackground("w")
        self.overview_plot.showGrid(x=True, y=True, alpha=0.2)
        self.overview_plot.setLabel("bottom", "Time", units="ms")
        self.overview_plot.setLabel("left", "Depth", units="m")
        left.addWidget(self.overview_plot, 1)
        layout.addWidget(panel, 0, 0)

        panel2, right = self._panel("Velocity / Layer Quality")
        self.velocity_overview_plot = pg.PlotWidget()
        self.velocity_overview_plot.setBackground("w")
        self.velocity_overview_plot.showGrid(x=True, y=True, alpha=0.2)
        self.velocity_overview_plot.setLabel("left", "Velocity", units="m/s")
        self.velocity_overview_plot.setLabel("bottom", "Layer")
        right.addWidget(self.velocity_overview_plot, 1)
        layout.addWidget(panel2, 0, 1)

        hint = QLabel("Load an uphole file or folder, edit picks/depths if required, then press Interpret. The dashboard will rebuild time-depth, interval velocity, QC completeness and export-ready tables.")
        hint.setObjectName("hintBox")
        hint.setWordWrap(True)
        layout.addWidget(hint, 1, 0, 1, 2)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        self.stack.addWidget(page)

    def _build_assignment_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self.assignment_table = QTableWidget(0, 9)
        self.assignment_table.setHorizontalHeaderLabels(["File", "Shot", "Depth m", "Offset m", "Pick ms", "Corrected ms", "Channel", "dt ms", "Note"])
        self._prep_table(self.assignment_table)
        self.assignment_table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed | QTableWidget.AnyKeyPressed)
        layout.addWidget(self.assignment_table)
        self.stack.addWidget(page)

    def _build_plot_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self.td_plot = pg.PlotWidget()
        self.td_plot.setBackground("w")
        self.td_plot.showGrid(x=True, y=True, alpha=0.2)
        self.td_plot.setLabel("bottom", "Time", units="ms")
        self.td_plot.setLabel("left", "Depth", units="m")
        self.td_plot.setTitle("Uphole Time-Depth Curve")
        layout.addWidget(self.td_plot)
        self.stack.addWidget(page)

    def _build_layers_page(self) -> None:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.layers_table = QTableWidget(0, 5)
        self.layers_table.setHorizontalHeaderLabels(["Top m", "Base m", "Top ms", "Base ms", "Velocity m/s"])
        self._prep_table(self.layers_table)
        self.layers_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.layers_table, 2)
        panel, p_layout = self._panel("Interval Velocity Graph")
        self.velocity_plot = pg.PlotWidget()
        self.velocity_plot.setBackground("w")
        self.velocity_plot.showGrid(x=True, y=True, alpha=0.2)
        self.velocity_plot.setLabel("left", "Velocity", units="m/s")
        self.velocity_plot.setLabel("bottom", "Layer")
        p_layout.addWidget(self.velocity_plot)
        layout.addWidget(panel, 1)
        self.stack.addWidget(page)

    def _build_qc_page(self) -> None:
        page = QWidget()
        layout = QGridLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        panel, left = self._panel("Data Completeness")
        self.completeness_table = QTableWidget(0, 3)
        self.completeness_table.setHorizontalHeaderLabels(["Field", "Present", "Completeness"])
        self._prep_table(self.completeness_table)
        self.completeness_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        left.addWidget(self.completeness_table)
        layout.addWidget(panel, 0, 0)

        panel2, right = self._panel("Interpretation Statistics")
        self.stats_table = QTableWidget(0, 2)
        self.stats_table.setHorizontalHeaderLabels(["Metric", "Value"])
        self._prep_table(self.stats_table)
        self.stats_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.stats_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        right.addWidget(self.stats_table)
        layout.addWidget(panel2, 0, 1)
        self.stack.addWidget(page)

    def _build_guide_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        panel, body = self._panel("Recommended Uphole Workflow")
        note = QLabel(
            "1) Load SEG-2/OYO records, a folder, or a CSV pick table.\n"
            "2) Check/complete depth, offset, first-break pick and corrected-time fields.\n"
            "3) Press Interpret to rebuild the time-depth curve and interval velocity model.\n"
            "4) Review QC Summary for missing values and velocity ranges.\n"
            "5) Export CSV for reporting or downstream statics/weathering analysis.\n\n"
            "Accepted CSV aliases include: depth, depth_m, pick_ms, corrected_ms, offset, offset_m, channel, sample_interval and trace_count."
        )
        note.setObjectName("hintBox")
        note.setWordWrap(True)
        body.addWidget(note)
        body.addStretch(1)
        layout.addWidget(panel, 1)
        self.stack.addWidget(page)

    def _set_page(self, index: int) -> None:
        index = max(0, min(index, self.stack.count() - 1))
        self.stack.setCurrentIndex(index)
        if index < len(self.nav_buttons):
            self.nav_buttons[index].setChecked(True)

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
            self._populate_assignment()
            self.interpret()
        except Exception as exc:
            QMessageBox.critical(self, "Uphole Import", str(exc))

    def _sync_from_table(self) -> None:
        records: list[UpholeShot] = []
        for row in range(self.assignment_table.rowCount()):
            def txt(col: int) -> str:
                item = self.assignment_table.item(row, col)
                return item.text().strip() if item else ""
            def fl(col: int):
                try:
                    return float(txt(col)) if txt(col) else None
                except ValueError:
                    return None
            def integer(col: int):
                try:
                    return int(float(txt(col))) if txt(col) else None
                except ValueError:
                    return None
            records.append(UpholeShot(file_name=txt(0), shot_id=txt(1), depth_m=fl(2), offset_m=fl(3), pick_ms=fl(4), corrected_ms=fl(5), channel=integer(6), sample_interval_ms=fl(7), note=txt(8)))
        self.records = records

    def interpret(self) -> None:
        if self._interpreting:
            return
        if not self.records:
            QMessageBox.information(self, "Uphole", "Load uphole files or a pick table first.")
            return
        self._interpreting = True
        self.loader.setVisible(True)
        self.interpret_btn.setEnabled(False)
        self.open_file_btn.setEnabled(False)
        self.open_folder_btn.setEnabled(False)
        QTimer.singleShot(60, self._finish_interpret)

    def _finish_interpret(self) -> None:
        try:
            self._sync_from_table()
            self.layers = self.interpreter.layers(self.records)
            self._populate_plot()
            self._populate_layers()
            self._populate_qc_tables()
            self._update_metrics()
            self._set_page(0)
        except Exception as exc:
            QMessageBox.critical(self, "Uphole Interpretation", str(exc))
        finally:
            self._interpreting = False
            self.loader.setVisible(False)
            self.interpret_btn.setEnabled(True)
            self.open_file_btn.setEnabled(True)
            self.open_folder_btn.setEnabled(True)

    def _populate_assignment(self) -> None:
        self.assignment_table.setRowCount(0)
        for r in self.records:
            row = self.assignment_table.rowCount()
            self.assignment_table.insertRow(row)
            values = [r.file_name, r.shot_id, r.depth_m, r.offset_m, r.pick_ms, r.corrected_ms, r.channel, r.sample_interval_ms, r.note]
            for col, value in enumerate(values):
                self.assignment_table.setItem(row, col, QTableWidgetItem("" if value is None else str(value)))
        self.assignment_table.resizeRowsToContents()
        self._populate_qc_tables()
        self._update_metrics()

    def _time_depth_xy(self) -> tuple[list[float], list[float]]:
        td = self.interpreter.build_time_depth(self.records)
        x = [float(self.interpreter.interpreted_time(r) or 0.0) for r in td]
        y = [float(r.depth_m or 0.0) for r in td]
        return x, y

    def _populate_plot(self) -> None:
        for plot in (self.td_plot, self.overview_plot):
            plot.clear()
        x, y = self._time_depth_xy()
        if not x:
            return
        for plot in (self.td_plot, self.overview_plot):
            plot.plot(x, y, pen=pg.mkPen("#0A86C7", width=2), symbol="o", symbolBrush="#15945C", symbolSize=6)
            plot.invertY(False)

    def _populate_layers(self) -> None:
        self.layers_table.setRowCount(0)
        for idx, layer in enumerate(self.layers, start=1):
            row = self.layers_table.rowCount()
            self.layers_table.insertRow(row)
            vals = [layer.top_depth_m, layer.base_depth_m, layer.top_time_ms, layer.base_time_ms, round(layer.interval_velocity_m_s, 2)]
            for col, value in enumerate(vals):
                self.layers_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.layers_table.resizeRowsToContents()
        self._populate_velocity_plot()

    def _populate_velocity_plot(self) -> None:
        for plot in (self.velocity_plot, self.velocity_overview_plot):
            plot.clear()
        if not self.layers:
            return
        x = list(range(1, len(self.layers) + 1))
        y = [float(layer.interval_velocity_m_s) for layer in self.layers]
        for plot in (self.velocity_plot, self.velocity_overview_plot):
            bg = pg.BarGraphItem(x=x, height=y, width=0.65, brush="#0A86C7")
            plot.addItem(bg)
            plot.plot(x, y, pen=pg.mkPen("#D97706", width=2), symbol="o", symbolBrush="#D97706", symbolSize=5)

    def _field_count(self, attr: str) -> int:
        return sum(1 for record in self.records if getattr(record, attr, None) is not None and getattr(record, attr, None) != "")

    def _populate_qc_tables(self) -> None:
        total = max(len(self.records), 1)
        self.completeness_table.setRowCount(0)
        fields = [
            ("Depth", "depth_m"),
            ("Offset", "offset_m"),
            ("Pick time", "pick_ms"),
            ("Corrected time", "corrected_ms"),
            ("Channel", "channel"),
            ("Sample interval", "sample_interval_ms"),
        ]
        for label, attr in fields:
            present = self._field_count(attr)
            row = self.completeness_table.rowCount()
            self.completeness_table.insertRow(row)
            self.completeness_table.setItem(row, 0, QTableWidgetItem(label))
            self.completeness_table.setItem(row, 1, QTableWidgetItem(f"{present:,} / {len(self.records):,}"))
            self.completeness_table.setItem(row, 2, QTableWidgetItem(f"{present / total * 100:.1f}%"))

        summary = self.interpreter.summary(self.records)
        velocities = [float(layer.interval_velocity_m_s) for layer in self.layers]
        stats = [
            ("Records", f"{summary['records']:,}"),
            ("Usable time-depth points", f"{summary['usable_time_depth_points']:,}"),
            ("Interpreted layers", f"{summary['layers']:,}"),
            ("Average velocity", f"{summary.get('average_velocity_m_s'):,.2f} m/s" if summary.get("average_velocity_m_s") is not None else "—"),
            ("Minimum velocity", f"{min(velocities):,.2f} m/s" if velocities else "—"),
            ("Maximum velocity", f"{max(velocities):,.2f} m/s" if velocities else "—"),
            ("Velocity spread", f"{(max(velocities) - min(velocities)):,.2f} m/s" if velocities else "—"),
        ]
        self.stats_table.setRowCount(0)
        for key, value in stats:
            row = self.stats_table.rowCount()
            self.stats_table.insertRow(row)
            self.stats_table.setItem(row, 0, QTableWidgetItem(key))
            self.stats_table.setItem(row, 1, QTableWidgetItem(str(value)))

    def _update_metrics(self) -> None:
        summary = self.interpreter.summary(self.records)
        self.metric_values["records"].setText(f"{summary['records']:,}")
        self.metric_values["points"].setText(f"{summary['usable_time_depth_points']:,}")
        self.metric_values["layers"].setText(f"{summary['layers']:,}")
        avg = summary.get("average_velocity_m_s")
        self.metric_values["velocity"].setText(f"{avg:,.1f} m/s" if avg is not None else "—")

    def export_csv(self) -> None:
        if not self.records:
            QMessageBox.information(self, "Uphole", "Nothing to export.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export uphole interpretation", "uphole_interpretation.csv", "CSV (*.csv)")
        if not path:
            return
        self._sync_from_table()
        self.layers = self.interpreter.layers(self.records)
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["file", "shot", "depth_m", "offset_m", "pick_ms", "corrected_ms", "channel", "sample_interval_ms", "note"])
            for r in self.records:
                writer.writerow([r.file_name, r.shot_id, r.depth_m, r.offset_m, r.pick_ms, r.corrected_ms, r.channel, r.sample_interval_ms, r.note])
            writer.writerow([])
            writer.writerow(["top_depth_m", "base_depth_m", "top_time_ms", "base_time_ms", "interval_velocity_m_s"])
            for layer in self.layers:
                writer.writerow([layer.top_depth_m, layer.base_depth_m, layer.top_time_ms, layer.base_time_ms, layer.interval_velocity_m_s])
        QMessageBox.information(self, "Uphole", f"Exported:\n{path}")

    def show_assignment(self) -> None:
        self._set_page(1)

    def show_time_depth(self) -> None:
        self._set_page(2)

    def show_layers(self) -> None:
        self._set_page(3)

    def show_guide(self) -> None:
        self._set_page(5)

    def can_execute(self, action_id: str) -> bool:
        if action_id in {"uphole_open", "uphole_open_folder"}:
            return True
        if action_id in {"uphole_interpret", "uphole_export", "uphole_time_depth", "uphole_layers", "uphole_assignments", "uphole_guide"}:
            return bool(self.records) or action_id == "uphole_guide"
        return True
