from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from modules.electrical.models import ElectricalDataset


_PROSYS_QSS = """
QWidget#prosysPanel {
    background:#F3F6FA;
    color:#17212B;
    font-family:"Segoe UI", Arial, sans-serif;
    font-size:8pt;
}
QFrame#prosysToolbar {
    background:#FFFFFF;
    border:1px solid #D5DCE5;
    border-radius:8px;
}
QLabel#prosysStatus {
    color:#445566;
    font-size:8pt;
    font-weight:600;
    padding:3px 6px;
    background:#F4F9FE;
    border:1px solid #D5E4F2;
    border-radius:5px;
}
QLabel#prosysSmall {
    color:#53616F;
    font-size:7.8pt;
}
QFrame#prosysDivider {
    background:#E3E8EC;
    max-width:1px;
    min-width:1px;
}
QTabWidget::pane {
    border:1px solid #D5DCE5;
    background:#FFFFFF;
    border-radius:7px;
}
QTabBar::tab {
    background:#EEF3F8;
    color:#344150;
    border:1px solid #C7D1DD;
    padding:5px 10px;
    min-height:18px;
    font-weight:700;
    font-size:8pt;
    margin-right:2px;
    border-top-left-radius:6px;
    border-top-right-radius:6px;
}
QTabBar::tab:selected {
    background:#FFFFFF;
    color:#1B6FA8;
    border-bottom-color:#FFFFFF;
}
QPushButton {
    min-height:23px;
    padding:3px 9px;
    border-radius:6px;
    border:1px solid #C7D1DD;
    background:#FFFFFF;
    color:#2B3846;
    font-size:8pt;
    font-weight:700;
}
QPushButton:hover { background:#F0F6FC; border-color:#8DB4DC; }
QPushButton:pressed { background:#E2ECF7; }
QPushButton#prosysProcess {
    background:#1F78B4;
    color:#FFFFFF;
    border-color:#175E8F;
}
QPushButton#prosysProcess:hover { background:#2288CC; }
QPushButton#prosysOpen {
    background:#FFF2D7;
    color:#744C00;
    border-color:#D6AA46;
}
QPushButton#prosysFilter {
    background:#E7F5EF;
    color:#0B6235;
    border-color:#87C5A5;
}
QPushButton#prosysReject {
    background:#FFF0F0;
    color:#A22A2A;
    border-color:#D19A9A;
}
QPushButton#prosysExport {
    background:#F0E8FF;
    color:#4D278A;
    border-color:#B59BE3;
}
QPushButton#prosysNeutral { background:#FFFFFF; }
QTableWidget {
    background:#FFFFFF;
    alternate-background-color:#F8FAFC;
    border:1px solid #D5DCE5;
    border-radius:6px;
    gridline-color:#E5EAF0;
    font-size:7.9pt;
    selection-background-color:#D8ECFF;
    selection-color:#17212B;
}
QHeaderView::section {
    background:#E8EEF5;
    color:#2B3846;
    border:0;
    border-right:1px solid #D5DCE5;
    border-bottom:1px solid #D5DCE5;
    padding:4px;
    font-size:7.9pt;
    font-weight:800;
}
QComboBox, QDoubleSpinBox {
    min-height:22px;
    background:#FFFFFF;
    border:1px solid #C7D1DD;
    border-radius:5px;
    padding:1px 5px;
    font-size:8pt;
}
"""



class ProsysQcPanel(QWidget):
    """Prosys-II style electrical/IP workspace embedded inside Electrical QC.

    It does not decode proprietary SYSCAL/ELREC binary memory directly. It works
    on the tabular controller exports already loaded by the Electrical reader and
    then provides the Prosys-style QC operations: value filtering, node rejection,
    median/sliding smoothing, topography insertion, apparent sections, IP decay
    windows, GPS track review and txt/Res2DInv-style export.
    """

    def __init__(self, dashboard: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("prosysPanel")
        self.setStyleSheet(_PROSYS_QSS)
        self.dashboard = dashboard
        self.filter_table: QTableWidget | None = None
        self.numeric_table: QTableWidget | None = None
        self.topo_table: QTableWidget | None = None
        self.track_table: QTableWidget | None = None
        self._build_ui()

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------
    @property
    def dataset(self) -> ElectricalDataset | None:
        return getattr(self.dashboard, "dataset", None)

    def refresh(self) -> None:
        self._refresh_transfer()
        self._refresh_numeric()
        self._refresh_filters()
        self._refresh_section_plot()
        self._refresh_decay_plot()
        self._refresh_track()
        self._refresh_topography()
        self._refresh_export_preview()

    def _set_dashboard_dataset(self, dataset: ElectricalDataset, message: str) -> None:
        self.dashboard.dataset = dataset
        self.dashboard.qc_result = None
        self.dashboard._refresh_all()
        self.dashboard.status_label.setText(message)

    # ------------------------------------------------------------------
    # UI build
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(7)

        root.addWidget(self._build_toolbar())

        self.tabs = QTabWidget(self)
        self.tabs.setDocumentMode(False)
        self.tabs.setUsesScrollButtons(True)
        root.addWidget(self.tabs, 1)

        self.transfer_tab = QWidget()
        self.numeric_tab = QWidget()
        self.filter_tab = QWidget()
        self.section_tab = QWidget()
        self.decay_tab = QWidget()
        self.track_tab = QWidget()
        self.topo_tab = QWidget()
        self.export_tab = QWidget()
        self.tabs.addTab(self.transfer_tab, "Transfer / File")
        self.tabs.addTab(self.numeric_tab, "Numeric Results")
        self.tabs.addTab(self.filter_tab, "Processing Filters")
        self.tabs.addTab(self.section_tab, "Apparent Section")
        self.tabs.addTab(self.decay_tab, "IP Decay")
        self.tabs.addTab(self.track_tab, "GPS Track")
        self.tabs.addTab(self.topo_tab, "Topography")
        self.tabs.addTab(self.export_tab, "Export Preview")

        self._build_transfer_tab()
        self._build_numeric_tab()
        self._build_filter_tab()
        self._build_section_tab()
        self._build_decay_tab()
        self._build_track_tab()
        self._build_topo_tab()
        self._build_export_tab()

    def _build_toolbar(self) -> QFrame:
        """Single-row action bar. Replaces the old branded header block."""
        bar = QFrame(self)
        bar.setObjectName("prosysToolbar")
        outer = QVBoxLayout(bar)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(3)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(6)
        for text, slot, name in (
            ("Open Data", self.dashboard.open_data, "prosysOpen"),
            ("Run QC", self.dashboard.run_full_qc, "prosysProcess"),
            ("Filter", self.apply_range_filter, "prosysFilter"),
            ("Reject Rows", self.reject_selected_rows, "prosysReject"),
            ("Export TXT", self.export_txt, "prosysExport"),
            ("Export RES2D", self.export_res2dinv, "prosysExport"),
        ):
            button = QPushButton(text)
            button.setObjectName(name)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(slot)
            actions.addWidget(button)
        actions.addStretch(1)
        outer.addLayout(actions)

        self.status = QLabel("Open an electrical/IP dataset to start Prosys-style QC.")
        self.status.setObjectName("prosysStatus")
        self.status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        outer.addWidget(self.status)

        return bar

    def _build_transfer_tab(self) -> None:
        layout = QVBoxLayout(self.transfer_tab)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        self.transfer_table = self._table(["Item", "Value"])
        layout.addWidget(self.transfer_table, 1)

    def _build_numeric_tab(self) -> None:
        layout = QVBoxLayout(self.numeric_tab)
        layout.setContentsMargins(5, 5, 5, 5)
        self.numeric_table = self._table([])
        self.numeric_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        layout.addWidget(self.numeric_table, 1)

    def _build_filter_tab(self) -> None:
        layout = QVBoxLayout(self.filter_tab)
        layout.setContentsMargins(5, 5, 5, 5)
        top = QHBoxLayout()
        apply_button = QPushButton("Apply Range Filter")
        apply_button.setObjectName("prosysFilter")
        apply_button.clicked.connect(self.apply_range_filter)
        median_button = QPushButton("Median Average")
        median_button.setObjectName("prosysProcess")
        median_button.clicked.connect(self.apply_median_average)
        sliding_button = QPushButton("Sliding Average")
        sliding_button.setObjectName("prosysProcess")
        sliding_button.clicked.connect(self.apply_sliding_average)
        for button in (apply_button, median_button, sliding_button):
            top.addWidget(button)
        top.addStretch(1)
        layout.addLayout(top)
        self.filter_table = self._table(["Use", "Parameter", "Min value", "Max value", "Valid", "Rejected if applied"])
        layout.addWidget(self.filter_table, 1)

    def _build_section_tab(self) -> None:
        layout = QVBoxLayout(self.section_tab)
        layout.setContentsMargins(5, 5, 5, 5)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Plot:"))
        self.section_value_combo = QComboBox()
        self.section_value_combo.currentIndexChanged.connect(lambda *_: self._refresh_section_plot())
        controls.addWidget(self.section_value_combo)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.section_plot = pg.PlotWidget(background="#FFFFFF")
        self.section_plot.showGrid(x=True, y=True, alpha=0.25)
        self.section_plot.setLabel("left", "Pseudo depth / value")
        self.section_plot.setLabel("bottom", "Station / profile")
        layout.addWidget(self.section_plot, 1)

    def _build_decay_tab(self) -> None:
        layout = QVBoxLayout(self.decay_tab)
        layout.setContentsMargins(5, 5, 5, 5)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Reading:"))
        self.decay_row_combo = QComboBox()
        self.decay_row_combo.currentIndexChanged.connect(lambda *_: self._refresh_decay_plot())
        controls.addWidget(self.decay_row_combo)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.decay_plot = pg.PlotWidget(background="#FFFFFF")
        self.decay_plot.showGrid(x=True, y=True, alpha=0.25)
        self.decay_plot.setLabel("left", "IP decay")
        self.decay_plot.setLabel("bottom", "Window")
        layout.addWidget(self.decay_plot, 1)

    def _build_track_tab(self) -> None:
        layout = QVBoxLayout(self.track_tab)
        layout.setContentsMargins(5, 5, 5, 5)
        splitter = QHBoxLayout()
        self.track_plot = pg.PlotWidget(background="w")
        self.track_plot.showGrid(x=True, y=True, alpha=0.25)
        self.track_plot.setLabel("left", "Northing / Latitude")
        self.track_plot.setLabel("bottom", "Easting / Longitude")
        splitter.addWidget(self.track_plot, 2)
        self.track_table = self._table(["Metric", "Value"])
        splitter.addWidget(self.track_table, 1)
        layout.addLayout(splitter, 1)

    def _build_topo_tab(self) -> None:
        layout = QVBoxLayout(self.topo_tab)
        layout.setContentsMargins(5, 5, 5, 5)
        top = QHBoxLayout()
        import_button = QPushButton("Insert Topography CSV")
        import_button.setObjectName("prosysOpen")
        import_button.clicked.connect(self.import_topography)
        offset_button = QPushButton("Apply Elevation Offset")
        offset_button.setObjectName("prosysProcess")
        offset_button.clicked.connect(self.apply_elevation_offset)
        self.elevation_offset = QDoubleSpinBox()
        self.elevation_offset.setRange(-10000, 10000)
        self.elevation_offset.setDecimals(3)
        self.elevation_offset.setSuffix(" m")
        top.addWidget(import_button)
        top.addWidget(QLabel("Offset:"))
        top.addWidget(self.elevation_offset)
        top.addWidget(offset_button)
        top.addStretch(1)
        layout.addLayout(top)
        self.topo_table = self._table(["Row", "Station", "Easting/X", "Elevation", "Pseudo depth", "Topo corrected Z"])
        layout.addWidget(self.topo_table, 1)

    def _build_export_tab(self) -> None:
        layout = QVBoxLayout(self.export_tab)
        layout.setContentsMargins(5, 5, 5, 5)
        top = QHBoxLayout()
        for text, slot, name in (
            ("Export TXT", self.export_txt, "prosysExport"),
            ("Export RES2DINV", self.export_res2dinv, "prosysExport"),
            ("Export RES3DINV", self.export_res3dinv, "prosysExport"),
        ):
            button = QPushButton(text)
            button.setObjectName(name)
            button.clicked.connect(slot)
            top.addWidget(button)
        top.addStretch(1)
        layout.addLayout(top)
        self.export_table = self._table(["Export product", "Status", "Content"])
        layout.addWidget(self.export_table, 1)

    @staticmethod
    def _table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        if headers:
            table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(21)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    # ------------------------------------------------------------------
    # Refresh sections
    # ------------------------------------------------------------------
    def _refresh_transfer(self) -> None:
        rows = []
        ds = self.dataset
        if ds is None:
            rows = [
                ("File", "No dataset loaded"),
                ("Supported workflow", "SYSCAL / ELREC-style tabular exports, ERT, VES, IP, SP and GPS track columns"),
                ("Load rule", "Use Open Data; no file is processed until explicitly selected"),
            ]
            self.status.setText("Open an electrical/IP export to view Prosys-style numeric, section and IP/QC plots.")
        else:
            rows = [
                ("Source file", ds.source_path.name),
                ("Source path", str(ds.source_path)),
                ("Method", ds.method_label),
                ("Records", f"{ds.record_count:,}"),
                ("Columns", ", ".join(sorted(ds.columns))),
                ("Mapped fields", str(ds.metadata.get("mapped_columns", {}))),
            ]
            self.status.setText(f"Loaded {ds.record_count:,} records. Use tabs for numeric results, filters, sections, IP decay, GPS and export.")
        self._fill_key_value(self.transfer_table, rows)

    def _refresh_numeric(self) -> None:
        table = self.numeric_table
        if table is None:
            return
        table.clear()
        ds = self.dataset
        if ds is None:
            table.setColumnCount(0)
            table.setRowCount(0)
            return
        preferred = [
            "line_id", "station", "a", "b", "m", "n", "ab2_m", "mn2_m", "current_ma", "voltage_mv",
            "resistance_ohm", "apparent_resistivity_ohm_m", "chargeability_mv_v", "sp_mv", "frequency_hz",
            "phase_mrad", "contact_resistance_ohm", "stack_std_pct", "reciprocal_error_pct",
        ]
        decay = self._decay_columns(ds)
        headers = [name for name in preferred if ds.has(name)] + decay
        headers.extend(name for name in sorted(ds.columns) if name not in headers and ds.has(name))
        headers = headers[:36]
        count = min(ds.record_count, 1000)
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels([self._label(name) for name in headers])
        table.setRowCount(count)
        for row in range(count):
            for column, name in enumerate(headers):
                item = QTableWidgetItem(_display(ds.columns[name][row]))
                if name in {"apparent_resistivity_ohm_m", "chargeability_mv_v", "voltage_mv", "current_ma"}:
                    item.setBackground(QColor("#EAF3FA"))
                table.setItem(row, column, item)
        for col in range(len(headers)):
            table.setColumnWidth(col, 92)

    def _refresh_filters(self) -> None:
        table = self.filter_table
        ds = self.dataset
        if table is None:
            return
        filter_fields = self._filter_fields(ds)
        table.setRowCount(len(filter_fields))
        for row, field in enumerate(filter_fields):
            values = ds.numeric(field) if ds is not None and ds.has(field) else np.array([], dtype=float)
            finite = values[np.isfinite(values)]
            vmin = float(np.min(finite)) if finite.size else 0.0
            vmax = float(np.max(finite)) if finite.size else 0.0
            valid_count = int(finite.size)
            rejected = int((ds.record_count if ds else 0) - valid_count)
            use_item = QTableWidgetItem("Yes")
            use_item.setCheckState(Qt.Checked)
            table.setItem(row, 0, use_item)
            table.setItem(row, 1, QTableWidgetItem(self._label(field)))
            min_item = QTableWidgetItem(_display(vmin))
            max_item = QTableWidgetItem(_display(vmax))
            table.setItem(row, 2, min_item)
            table.setItem(row, 3, max_item)
            table.setItem(row, 4, QTableWidgetItem(f"{valid_count:,}"))
            table.setItem(row, 5, QTableWidgetItem(f"{rejected:,}"))
            use_item.setData(Qt.UserRole, field)
        for col, width in enumerate((52, 180, 95, 95, 80, 110)):
            table.setColumnWidth(col, width)

    def _refresh_section_plot(self) -> None:
        if not hasattr(self, "section_plot"):
            return
        plot = self.section_plot
        plot.clear()
        ds = self.dataset
        if ds is None or ds.record_count == 0:
            plot.setTitle("Open data to plot apparent resistivity / chargeability section")
            self._populate_section_combo([])
            return
        value_options = [name for name in ("apparent_resistivity_ohm_m", "chargeability_mv_v", "sp_mv", "voltage_mv") if ds.has(name)]
        value_options += [name for name in self._decay_columns(ds) if name not in value_options]
        self._populate_section_combo(value_options)
        if not value_options:
            plot.setTitle("No plottable electrical/IP value columns")
            return
        value_name = str(self.section_value_combo.currentData() or value_options[0])
        if ds.has("pseudo_x") and ds.has("pseudo_depth"):
            x = ds.numeric("pseudo_x")
            y = -ds.numeric("pseudo_depth")
            y_label = "Pseudo-depth / elevation section"
        elif ds.has("station"):
            x = ds.numeric("station")
            y = np.zeros(ds.record_count)
            y_label = "Profile line"
        elif ds.has("easting") and ds.has("elevation"):
            x = ds.numeric("easting")
            y = ds.numeric("elevation")
            y_label = "Topographic profile"
        else:
            x = np.arange(ds.record_count, dtype=float)
            y = np.zeros(ds.record_count)
            y_label = "Reading index"
        values = ds.numeric(value_name)
        valid = np.isfinite(x) & np.isfinite(y) & np.isfinite(values)
        if value_name == "apparent_resistivity_ohm_m":
            valid &= values > 0
        if np.count_nonzero(valid) == 0:
            plot.setTitle("No valid values for section plot")
            return
        display_values = np.log10(values[valid]) if value_name == "apparent_resistivity_ohm_m" else values[valid]
        colors = self._value_colors(display_values)
        spots = []
        for px, py, color, raw in zip(x[valid], y[valid], colors, values[valid]):
            spots.append({"pos": (float(px), float(py)), "brush": color, "pen": pg.mkPen("#243746", width=0.35), "size": 9, "data": float(raw)})
        scatter = pg.ScatterPlotItem(spots=spots)
        plot.addItem(scatter)
        if np.count_nonzero(valid) < 300:
            try:
                order = np.argsort(x[valid])
                plot.plot(x[valid][order], y[valid][order], pen=pg.mkPen("#6B7280", width=0.8))
            except Exception:
                pass
        plot.setLabel("bottom", "Station / X")
        plot.setLabel("left", y_label)
        plot.setTitle(f"{self._label(value_name)} apparent section — values shown by colour")

    def _refresh_decay_plot(self) -> None:
        if not hasattr(self, "decay_plot"):
            return
        plot = self.decay_plot
        plot.clear()
        ds = self.dataset
        if ds is None:
            plot.setTitle("Open TDIP/IP data to plot decay windows")
            self._populate_decay_rows(0)
            return
        decay_cols = self._decay_columns(ds)
        if not decay_cols:
            plot.setTitle("No IP decay-window columns found. Columns named M1, M2, window_01, decay_01 etc. will plot here.")
            self._populate_decay_rows(0)
            return
        self._populate_decay_rows(min(ds.record_count, 500))
        row = int(self.decay_row_combo.currentData() or 0)
        row = max(0, min(row, ds.record_count - 1))
        x = np.arange(1, len(decay_cols) + 1, dtype=float)
        y = np.asarray([ds.numeric(col)[row] for col in decay_cols], dtype=float)
        valid = np.isfinite(y)
        if not np.any(valid):
            plot.setTitle(f"Reading {row + 1}: no valid IP decay windows")
            return
        plot.plot(x[valid], y[valid], pen=pg.mkPen("#1F78B4", width=2.2), symbol="o", symbolSize=6, symbolBrush="#2E9E5B", symbolPen=pg.mkPen("#174A7C", width=0.8))
        plot.setLabel("bottom", "IP decay window")
        plot.setLabel("left", "Chargeability / window value")
        plot.setTitle(f"IP decay curve — reading {row + 1}")

    def _refresh_track(self) -> None:
        if not hasattr(self, "track_plot"):
            return
        self.track_plot.clear()
        ds = self.dataset
        rows: list[tuple[str, Any]] = []
        if ds is None:
            self.track_plot.setTitle("Open data with latitude/longitude or easting/northing to display GPS track")
            self._fill_key_value(self.track_table, rows)
            return
        if ds.has("longitude") and ds.has("latitude"):
            x = ds.numeric("longitude")
            y = ds.numeric("latitude")
            axis = ("Longitude", "Latitude")
        elif ds.has("easting") and ds.has("northing"):
            x = ds.numeric("easting")
            y = ds.numeric("northing")
            axis = ("Easting", "Northing")
        else:
            self.track_plot.setTitle("No GPS/projected coordinates available")
            self._fill_key_value(self.track_table, [("Coordinate status", "Missing latitude/longitude or easting/northing")])
            return
        valid = np.isfinite(x) & np.isfinite(y)
        if not np.any(valid):
            self.track_plot.setTitle("No valid coordinate pairs available")
            self._fill_key_value(self.track_table, [("Valid coordinate points", 0)])
            return
        self.track_plot.plot(x[valid], y[valid], pen=pg.mkPen("#C24A3A", width=2), symbol="o", symbolSize=5, symbolBrush="#1F78B4", symbolPen=pg.mkPen("#174A7C", width=0.7))
        self.track_plot.setLabel("bottom", axis[0])
        self.track_plot.setLabel("left", axis[1])
        self.track_plot.setTitle("GPS / acquisition track")
        rows = [
            ("Valid coordinate points", int(np.count_nonzero(valid))),
            ("X min", float(np.nanmin(x[valid]))),
            ("X max", float(np.nanmax(x[valid]))),
            ("Y min", float(np.nanmin(y[valid]))),
            ("Y max", float(np.nanmax(y[valid]))),
        ]
        self._fill_key_value(self.track_table, rows)

    def _refresh_topography(self) -> None:
        table = self.topo_table
        ds = self.dataset
        if table is None:
            return
        if ds is None:
            table.setRowCount(0)
            return
        count = min(ds.record_count, 600)
        table.setRowCount(count)
        station = ds.numeric("station") if ds.has("station") else np.arange(ds.record_count, dtype=float)
        x = ds.numeric("easting") if ds.has("easting") else ds.numeric("pseudo_x") if ds.has("pseudo_x") else station
        elev = ds.numeric("elevation") if ds.has("elevation") else np.full(ds.record_count, np.nan)
        depth = ds.numeric("pseudo_depth") if ds.has("pseudo_depth") else np.zeros(ds.record_count)
        for row in range(count):
            corrected = elev[row] - depth[row] if np.isfinite(elev[row]) and np.isfinite(depth[row]) else np.nan
            values = [row + 1, station[row], x[row], elev[row], depth[row], corrected]
            for col, value in enumerate(values):
                table.setItem(row, col, QTableWidgetItem(_display(value)))
        for col, width in enumerate((48, 80, 105, 95, 95, 115)):
            table.setColumnWidth(col, width)

    def _refresh_export_preview(self) -> None:
        ds = self.dataset
        rows = []
        if ds is None:
            rows = [
                ("TXT", "Waiting", "Load a dataset first"),
                ("Res2DInv", "Waiting", "Requires apparent resistivity/chargeability plus profile geometry"),
                ("Res3DInv", "Waiting", "Requires 3D-style X/Y/Z or pseudo coordinates"),
            ]
        else:
            rows = [
                ("TXT", "Ready", f"{ds.record_count:,} rows, {len(ds.columns)} recognized columns"),
                ("Res2DInv", "Ready" if self._can_export_res2d(ds) else "Review", "A/B/M/N or pseudo_x/pseudo_depth plus apparent resistivity preferred"),
                ("Res3DInv", "Ready" if (ds.has("easting") and ds.has("northing")) else "Review", "Use projected coordinates or line/pseudosection coordinates"),
            ]
        table = self.export_table
        table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 1:
                    if str(value).lower() == "ready":
                        item.setBackground(QColor("#E1F0E5"))
                    elif str(value).lower() == "review":
                        item.setBackground(QColor("#FCEFD2"))
                    else:
                        item.setBackground(QColor("#EDEDED"))
                table.setItem(row, col, item)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def apply_range_filter(self) -> None:
        ds = self.dataset
        table = self.filter_table
        if ds is None or table is None:
            QMessageBox.information(self, "Prosys Filter", "Open an electrical/IP dataset first.")
            return
        keep = np.ones(ds.record_count, dtype=bool)
        active_fields = []
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item is None or item.checkState() != Qt.Checked:
                continue
            field = str(item.data(Qt.UserRole) or "")
            if not field or not ds.has(field):
                continue
            try:
                min_value = float(table.item(row, 2).text())
                max_value = float(table.item(row, 3).text())
            except Exception:
                continue
            values = ds.numeric(field)
            keep &= np.isfinite(values) & (values >= min_value) & (values <= max_value)
            active_fields.append(field)
        if not active_fields:
            QMessageBox.information(self, "Prosys Filter", "No active valid filter rows were selected.")
            return
        if not np.any(keep):
            QMessageBox.warning(self, "Prosys Filter", "The filter would remove every row. Adjust min/max values.")
            return
        filtered = ds.copy()
        filtered.columns = {key: values[keep].copy() for key, values in ds.columns.items()}
        filtered.metadata["prosys_filter"] = ", ".join(active_fields)
        filtered.metadata["prosys_rows_removed"] = int(ds.record_count - filtered.record_count)
        self._set_dashboard_dataset(filtered, f"Prosys filter kept {filtered.record_count:,} / {ds.record_count:,} records")

    def reject_selected_rows(self) -> None:
        ds = self.dataset
        table = self.numeric_table
        if ds is None or table is None:
            QMessageBox.information(self, "Reject Rows", "Open an electrical/IP dataset first.")
            return
        rows = sorted({index.row() for index in table.selectedIndexes()})
        if not rows:
            QMessageBox.information(self, "Reject Rows", "Select one or more numeric-result rows first.")
            return
        mask = np.ones(ds.record_count, dtype=bool)
        for row in rows:
            if 0 <= row < len(mask):
                mask[row] = False
        output = ds.copy()
        output.columns = {key: values[mask].copy() for key, values in ds.columns.items()}
        output.metadata["prosys_rejected_display_rows"] = rows
        self._set_dashboard_dataset(output, f"Rejected {len(rows)} displayed row(s); {output.record_count:,} records remain")

    def apply_median_average(self) -> None:
        self._apply_window_operation("median")

    def apply_sliding_average(self) -> None:
        self._apply_window_operation("sliding")

    def _apply_window_operation(self, mode: str) -> None:
        ds = self.dataset
        if ds is None:
            QMessageBox.information(self, "Prosys Processing", "Open an electrical/IP dataset first.")
            return
        field = self._primary_process_field(ds)
        if not field:
            QMessageBox.information(self, "Prosys Processing", "No numeric measurement field is available for averaging.")
            return
        values = ds.numeric(field)
        output_values = values.copy()
        half = 2
        for i in range(len(values)):
            local = values[max(0, i - half): min(len(values), i + half + 1)]
            local = local[np.isfinite(local)]
            if local.size:
                output_values[i] = float(np.median(local) if mode == "median" else np.mean(local))
        output = ds.copy()
        suffix = "median5" if mode == "median" else "sliding5"
        output.columns[f"{field}_{suffix}"] = output_values
        output.metadata["prosys_processed_field"] = f"{field}_{suffix}"
        self._set_dashboard_dataset(output, f"Created {field}_{suffix}; original {field} preserved")

    def import_topography(self) -> None:
        ds = self.dataset
        if ds is None:
            QMessageBox.information(self, "Topography", "Open an electrical/IP dataset first.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Insert Topography CSV", "", "CSV/TXT (*.csv *.txt *.dat);;All files (*.*)")
        if not path:
            return
        rows = []
        with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
            sample = stream.read(4096)
            stream.seek(0)
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t ") if sample.strip() else csv.excel
            reader = csv.DictReader(stream, dialect=dialect)
            if not reader.fieldnames:
                QMessageBox.warning(self, "Topography", "The topography file has no headers.")
                return
            headers = {name.lower().strip(): name for name in reader.fieldnames}
            station_key = next((headers[k] for k in headers if k in {"station", "x", "chainage", "distance"}), None)
            elev_key = next((headers[k] for k in headers if k in {"elevation", "elev", "z", "height", "altitude"}), None)
            if station_key is None or elev_key is None:
                QMessageBox.warning(self, "Topography", "Topography file needs station/x and elevation/elev/z columns.")
                return
            for row in reader:
                try:
                    rows.append((float(row[station_key]), float(row[elev_key])))
                except Exception:
                    continue
        if len(rows) < 2:
            QMessageBox.warning(self, "Topography", "At least two valid topography rows are required.")
            return
        rows.sort(key=lambda item: item[0])
        topo_x = np.asarray([r[0] for r in rows], dtype=float)
        topo_z = np.asarray([r[1] for r in rows], dtype=float)
        if ds.has("station"):
            x = ds.numeric("station")
        elif ds.has("pseudo_x"):
            x = ds.numeric("pseudo_x")
        else:
            x = np.arange(ds.record_count, dtype=float)
        output = ds.copy()
        output.columns["elevation"] = np.interp(x, topo_x, topo_z)
        output.metadata["topography_source"] = str(path)
        self._set_dashboard_dataset(output, f"Inserted topography from {Path(path).name}")

    def apply_elevation_offset(self) -> None:
        ds = self.dataset
        if ds is None:
            QMessageBox.information(self, "Topography", "Open an electrical/IP dataset first.")
            return
        output = ds.copy()
        offset = float(self.elevation_offset.value())
        if output.has("elevation"):
            output.columns["elevation"] = output.numeric("elevation") + offset
        else:
            output.columns["elevation"] = np.full(output.record_count, offset, dtype=float)
        output.metadata["elevation_offset_m"] = offset
        self._set_dashboard_dataset(output, f"Applied elevation offset {offset:g} m")

    def export_txt(self) -> None:
        ds = self.dataset
        if ds is None:
            QMessageBox.information(self, "Export TXT", "Open an electrical/IP dataset first.")
            return
        suggested = ds.source_path.with_name(ds.source_path.stem + "_prosys_export.txt")
        path, _ = QFileDialog.getSaveFileName(self, "Export Prosys-style TXT", str(suggested), "Text (*.txt);;CSV (*.csv)")
        if not path:
            return
        headers, rows = self.dashboard.processing.export_rows(ds)
        delimiter = "\t" if Path(path).suffix.lower() == ".txt" else ","
        with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream, delimiter=delimiter)
            writer.writerow(headers)
            writer.writerows(rows)
        QMessageBox.information(self, "Export TXT", f"Saved:\n{path}")

    def export_res2dinv(self) -> None:
        self._export_res_inversion(dim="2d")

    def export_res3dinv(self) -> None:
        self._export_res_inversion(dim="3d")

    def _export_res_inversion(self, dim: str) -> None:
        ds = self.dataset
        if ds is None:
            QMessageBox.information(self, "Export", "Open an electrical/IP dataset first.")
            return
        suffix = "_res3dinv.dat" if dim == "3d" else "_res2dinv.dat"
        suggested = ds.source_path.with_name(ds.source_path.stem + suffix)
        title = "Export RES3DINV-style file" if dim == "3d" else "Export RES2DINV-style file"
        path, _ = QFileDialog.getSaveFileName(self, title, str(suggested), "DAT (*.dat);;Text (*.txt)")
        if not path:
            return
        content = self._res_export_text(ds, dim=dim)
        Path(path).write_text(content, encoding="utf-8")
        QMessageBox.information(self, title, f"Saved:\n{path}")

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------
    def _can_export_res2d(self, ds: ElectricalDataset) -> bool:
        return ds.has("apparent_resistivity_ohm_m") and (ds.has("pseudo_x") or ds.has("station") or {"a", "b", "m", "n"}.issubset(ds.columns))

    def _res_export_text(self, ds: ElectricalDataset, dim: str) -> str:
        value_name = "apparent_resistivity_ohm_m" if ds.has("apparent_resistivity_ohm_m") else self._primary_process_field(ds)
        x = ds.numeric("pseudo_x") if ds.has("pseudo_x") else ds.numeric("station") if ds.has("station") else np.arange(ds.record_count, dtype=float)
        z = ds.numeric("pseudo_depth") if ds.has("pseudo_depth") else np.zeros(ds.record_count, dtype=float)
        y = ds.numeric("line_id") if ds.has("line_id") and np.issubdtype(ds.columns["line_id"].dtype, np.number) else np.zeros(ds.record_count, dtype=float)
        values = ds.numeric(value_name) if value_name and ds.has(value_name) else np.full(ds.record_count, np.nan)
        valid = np.isfinite(x) & np.isfinite(z) & np.isfinite(values)
        lines = [
            f"TGPAssure Prosys-style {dim.upper()} export",
            f"Source={ds.source_path.name}",
            f"Method={ds.method_label}",
            f"Value={value_name or 'none'}",
            f"Records={int(np.count_nonzero(valid))}",
            "# Columns: x y_or_line pseudo_depth value a b m n chargeability",
        ]
        for i in np.flatnonzero(valid):
            a = ds.numeric("a")[i] if ds.has("a") else np.nan
            b = ds.numeric("b")[i] if ds.has("b") else np.nan
            m = ds.numeric("m")[i] if ds.has("m") else np.nan
            n = ds.numeric("n")[i] if ds.has("n") else np.nan
            charge = ds.numeric("chargeability_mv_v")[i] if ds.has("chargeability_mv_v") else np.nan
            yy = y[i] if np.ndim(y) else 0.0
            lines.append(" ".join(_display(v) for v in (x[i], yy, z[i], values[i], a, b, m, n, charge)))
        return "\n".join(lines) + "\n"

    def _populate_section_combo(self, fields: list[str]) -> None:
        current = self.section_value_combo.currentData() if hasattr(self, "section_value_combo") else None
        self.section_value_combo.blockSignals(True)
        self.section_value_combo.clear()
        for field in fields:
            self.section_value_combo.addItem(self._label(field), field)
        if current:
            for i in range(self.section_value_combo.count()):
                if self.section_value_combo.itemData(i) == current:
                    self.section_value_combo.setCurrentIndex(i)
                    break
        self.section_value_combo.blockSignals(False)

    def _populate_decay_rows(self, count: int) -> None:
        current = self.decay_row_combo.currentData() if hasattr(self, "decay_row_combo") else None
        self.decay_row_combo.blockSignals(True)
        self.decay_row_combo.clear()
        for i in range(min(count, 500)):
            self.decay_row_combo.addItem(f"{i + 1}", i)
        if current is not None:
            for i in range(self.decay_row_combo.count()):
                if self.decay_row_combo.itemData(i) == current:
                    self.decay_row_combo.setCurrentIndex(i)
                    break
        self.decay_row_combo.blockSignals(False)

    @staticmethod
    def _value_colors(values: np.ndarray) -> list[QColor]:
        if values.size == 0:
            return []
        low, high = np.nanpercentile(values, [2, 98]) if values.size > 3 else (np.nanmin(values), np.nanmax(values))
        if not np.isfinite(high - low) or high == low:
            high = low + 1.0
        norm = np.clip((values - low) / (high - low), 0, 1)
        try:
            cmap = pg.colormap.get("CET-R4")
        except Exception:
            cmap = pg.colormap.get("viridis")
        return list(cmap.map(norm, mode="qcolor"))

    @staticmethod
    def _filter_fields(ds: ElectricalDataset | None) -> list[str]:
        candidates = [
            "voltage_mv", "current_ma", "resistance_ohm", "apparent_resistivity_ohm_m", "chargeability_mv_v",
            "sp_mv", "contact_resistance_ohm", "stack_std_pct", "reciprocal_error_pct", "frequency_hz", "phase_mrad",
        ]
        if ds is None:
            return candidates[:6]
        return [field for field in candidates if ds.has(field)]

    @staticmethod
    def _decay_columns(ds: ElectricalDataset) -> list[str]:
        def key(name: str) -> tuple[int, str]:
            digits = "".join(ch for ch in name if ch.isdigit())
            return (int(digits) if digits else 9999, name)
        return sorted(
            [name for name in ds.columns if name.startswith(("window_", "decay_")) or name.startswith("m_window_")],
            key=key,
        )

    @staticmethod
    def _primary_process_field(ds: ElectricalDataset) -> str | None:
        for field in (
            "apparent_resistivity_ohm_m", "chargeability_mv_v", "voltage_mv", "sp_mv", "phase_mrad", "resistance_ohm"
        ):
            if ds.has(field):
                return field
        return None

    @staticmethod
    def _fill_key_value(table: QTableWidget, rows: list[tuple[str, Any]]) -> None:
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Item", "Value"])
        table.setRowCount(len(rows))
        for row, (key, value) in enumerate(rows):
            table.setItem(row, 0, QTableWidgetItem(str(key)))
            table.setItem(row, 1, QTableWidgetItem(_display(value)))
        table.setColumnWidth(0, 180)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

    @staticmethod
    def _label(name: str) -> str:
        replacements = {
            "apparent_resistivity_ohm_m": "Rho / apparent resistivity",
            "chargeability_mv_v": "M / chargeability",
            "voltage_mv": "Vp / voltage",
            "current_ma": "In / current",
            "stack_std_pct": "Dev / stacking deviation",
            "phase_mrad": "Phase",
            "frequency_hz": "Frequency",
        }
        return replacements.get(name, name.replace("_", " ").title())


def _display(value: Any) -> str:
    try:
        if value is None:
            return "—"
        if isinstance(value, (np.floating, float)):
            if not np.isfinite(float(value)):
                return "—"
            return f"{float(value):.6g}"
        if isinstance(value, (np.integer, int)):
            return str(int(value))
        text = str(value)
        return text if text.strip() else "—"
    except Exception:
        return str(value)