from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

import numpy as np
from PySide6.QtCore import Qt, Signal, QRectF, QSize
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush, QPixmap, QLinearGradient
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QDoubleSpinBox,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QTabWidget,
    QHeaderView,
    QVBoxLayout,
    QWidget,
)

from modules.geodetic.dc_reader import DcFileReader
from modules.geodetic.models import FIELD_LABELS, GeodeticDataset, RECORD_SCHEMAS
from core.visualization.palette_library import COLOR_PALETTES, palette_hex
from ui.widgets.color_palette_dialog import PaletteSelectorButton


QSS = """
QWidget#dcExaminerRoot {
    background:#F4F7FB;
    color:#17212B;
    font-family:"Segoe UI", Arial, sans-serif;
    font-size:8pt;
}
QFrame#geoSidebar {
    background:#FFFFFF;
    border:1px solid #D5DCE5;
    border-radius:8px;
}
QFrame#geoMainPanel {
    background:#FFFFFF;
    border:1px solid #D5DCE5;
    border-radius:8px;
}
QLabel#status {
    color:#083B66;
    font-weight:700;
    padding:6px 9px;
    background:#EAF3FC;
    border:1px solid #B9D1EA;
    border-radius:6px;
}
QLabel#sectionTitle {
    color:#344150;
    font-size:9pt;
    font-weight:700;
    padding:2px 0;
}
QGroupBox {
    border:1px solid #D1DAE5;
    border-radius:7px;
    margin-top:10px;
    padding:8px 8px 7px 8px;
    font-weight:700;
    background:#FBFCFE;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left:10px;
    padding:0 5px;
    color:#17212B;
    background:#FBFCFE;
}
QGroupBox[accent='green'] {
    border-color:#B7DDC4;
    background:#F7FCF8;
}
QGroupBox[accent='green']::title {
    color:#0A7A35;
    background:#F7FCF8;
}
QGroupBox[accent='blue'] {
    border-color:#B9D1EA;
    background:#F7FBFF;
}
QGroupBox[accent='blue']::title {
    color:#174EA6;
    background:#F7FBFF;
}
QPushButton {
    min-height:26px;
    padding:4px 10px;
    border:1px solid #B7C2CF;
    border-radius:6px;
    background:#EEF3F8;
    color:#17212B;
    font-weight:600;
}
QPushButton:hover {
    background:#E2ECF7;
    border-color:#7BA9D8;
}
QPushButton:pressed {
    background:#D5E4F4;
}
QPushButton#sideButton {
    min-height:30px;
    border:1px solid #B7C2CF;
    border-radius:7px;
    background:#EEF3F8;
    color:#0B2239;
    font-weight:700;
}
QPushButton#openButton {
    background:#F5C453;
    color:#101820;
    border:1px solid #C69421;
    border-radius:7px;
    font-weight:800;
}
QPushButton#graphButton {
    background:#2F6FA7;
    color:#FFFFFF;
    border:1px solid #24587F;
    border-radius:7px;
    font-weight:800;
}
QPushButton#allButton {
    min-width:42px;
    min-height:22px;
    border:1px solid #8BC09B;
    border-radius:5px;
    background:#E3F6E9;
    color:#087B2F;
    font-weight:800;
}
QPushButton#noneButton {
    min-width:42px;
    min-height:22px;
    border:1px solid #D19A9A;
    border-radius:5px;
    background:#FFF0F0;
    color:#B52828;
    font-weight:800;
}
QCheckBox {
    spacing:6px;
    color:#1F2933;
    background:transparent;
    min-height:20px;
    padding:1px 2px;
}
QCheckBox::indicator {
    width:15px;
    height:15px;
    border-radius:4px;
    border:1px solid #9AA7B4;
    background:#FFFFFF;
}
QCheckBox::indicator:hover {
    border:1px solid #4086C5;
    background:#F0F7FF;
}
QCheckBox::indicator:checked {
    background:#2F7DC1;
    border:1px solid #1E5F95;
    image:none;
}
QCheckBox::indicator:checked:disabled {
    background:#AAB7C4;
}
QCheckBox:checked {
    color:#0B335A;
    font-weight:600;
}
QScrollArea {
    border:none;
    background:transparent;
}
QTabWidget::pane {
    border:1px solid #D5DCE5;
    border-radius:6px;
    background:#FFFFFF;
}
QTabBar::tab {
    background:#EEF3F8;
    border:1px solid #C7D1DD;
    padding:5px 12px;
    margin-right:2px;
    border-top-left-radius:6px;
    border-top-right-radius:6px;
}
QTabBar::tab:selected {
    background:#FFFFFF;
    color:#174EA6;
    font-weight:700;
}
QTableWidget {
    background:#FFFFFF;
    gridline-color:#E1E6EC;
    color:#17212B;
    selection-background-color:#D8ECFF;
    selection-color:#17212B;
    alternate-background-color:#F8FAFC;
    font-size:8pt;
}
QHeaderView::section {
    background:#E8EEF5;
    color:#17212B;
    font-weight:800;
    padding:5px;
    border:1px solid #C7D1DD;
}
QTextEdit {
    background:#FFFFFF;
    color:#17212B;
    border:1px solid #D1DAE5;
    border-radius:6px;
    font-size:8pt;
    padding:6px;
}
QDoubleSpinBox {
    background:#FFFFFF;
    color:#17212B;
    border:1px solid #AEB9C5;
    border-radius:5px;
    min-height:22px;
}
"""




class ModernCheckBox(QCheckBox):
    """Compact checkbox with an explicit painted tick for bright dashboards."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(22)

    def sizeHint(self):  # noqa: N802
        base = super().sizeHint()
        return QSize(max(base.width() + 8, 92), max(base.height(), 23))

    def paintEvent(self, event):  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        box_size = 15
        x = 2
        y = (self.height() - box_size) // 2
        if self.isChecked():
            fill = QColor("#2F7DC1") if self.isEnabled() else QColor("#AAB7C4")
            border = QColor("#1E5F95") if self.isEnabled() else QColor("#8E9AA6")
        else:
            fill = QColor("#FFFFFF")
            border = QColor("#9AA7B4") if self.isEnabled() else QColor("#C1CAD3")
        painter.setPen(QPen(border, 1.2))
        painter.setBrush(fill)
        painter.drawRoundedRect(x, y, box_size, box_size, 4, 4)
        if self.isChecked():
            painter.setPen(QPen(QColor("#FFFFFF"), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawLine(x + 4, y + 8, x + 7, y + 11)
            painter.drawLine(x + 7, y + 11, x + 12, y + 4)
        text_color = QColor("#0B335A") if self.isChecked() else QColor("#1F2933")
        if not self.isEnabled():
            text_color = QColor("#8A97A5")
        font = painter.font()
        font.setPointSize(8)
        font.setBold(self.isChecked())
        painter.setFont(font)
        painter.setPen(text_color)
        painter.drawText(QRectF(x + box_size + 7, 0, self.width() - box_size - 9, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self.text())

class MiniPlot(QWidget):
    def __init__(self, title: str, values: np.ndarray | list[float] | None = None, limit: float | None = None, parent=None):
        super().__init__(parent)
        self.title = title
        self.values = np.asarray(values if values is not None else [], dtype=float)
        self.limit = limit
        self.ymin: float | None = None
        self.ymax: float | None = None
        self.palette_name = "Seismic"
        self.setMinimumHeight(132)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAutoFillBackground(False)

    def set_data(self, values: np.ndarray | list[float], limit: float | None = None, ymin: float | None = None, ymax: float | None = None) -> None:
        self.values = np.asarray(values, dtype=float)
        self.limit = limit
        self.ymin = ymin
        self.ymax = ymax
        self.update()

    def set_palette(self, palette_name: str) -> None:
        if palette_name in COLOR_PALETTES:
            self.palette_name = palette_name
            self.update()

    def paintEvent(self, event):  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect().adjusted(5, 4, -5, -4)
        painter.fillRect(rect, QColor("#F7FBFF"))
        painter.setPen(QPen(QColor("#D4DFEA"), 1))
        painter.drawRoundedRect(rect, 6, 6)
        plot = rect.adjusted(38, 22, -60, -25)
        painter.fillRect(plot, QColor("#F1F5F9"))
        painter.setPen(QPen(QColor("#FFFFFF"), 1))
        for i in range(1, 10):
            y = plot.top() + i * plot.height() / 10
            painter.drawLine(plot.left(), int(y), plot.right(), int(y))
        painter.setPen(QPen(QColor("#47525D"), 1))
        painter.drawRect(plot)
        font = painter.font(); font.setPointSize(8); font.setBold(True); painter.setFont(font)
        painter.setPen(QColor("#0B2239"))
        painter.drawText(rect.adjusted(0, 0, 0, -rect.height()+17), Qt.AlignCenter, self.title)
        values = self.values[np.isfinite(self.values)] if self.values.size else np.array([], dtype=float)
        if values.size == 0:
            painter.setPen(QColor("#666666"))
            painter.drawText(plot, Qt.AlignCenter, "No data")
            painter.setPen(QColor("#003366"))
            painter.drawText(rect.left(), rect.bottom()-3, "File :")
            return
        ymin = self.ymin if self.ymin is not None else float(np.nanmin(values))
        ymax = self.ymax if self.ymax is not None else float(np.nanmax(values))
        if math.isclose(ymin, ymax):
            ymin -= 1.0; ymax += 1.0
        pad = (ymax - ymin) * 0.05
        ymin -= pad; ymax += pad
        def ymap(v: float) -> int:
            return int(plot.bottom() - ((v - ymin) / (ymax - ymin)) * plot.height())
        if self.limit is not None and ymin <= self.limit <= ymax:
            painter.setPen(QPen(QColor("#D04A02"), 1, Qt.DashLine))
            yy = ymap(float(self.limit))
            painter.drawLine(plot.left(), yy, plot.right(), yy)
        # Display-only decimation keeps large GNSS logs responsive while preserving
        # the full arrays for QC calculations and statistics.
        if values.size > 5000:
            idx = np.linspace(0, values.size - 1, 5000, dtype=int)
            draw_values = values[idx]
        else:
            draw_values = values
        xs = np.linspace(plot.left()+3, plot.right()-3, max(draw_values.size, 2))[:draw_values.size]
        last = None
        span = max(ymax - ymin, 1e-12)
        for x, v in zip(xs, draw_values):
            pt = (int(x), ymap(float(v)))
            if last is not None:
                norm = min(1.0, max(0.0, (float(v) - ymin) / span))
                painter.setPen(QPen(QColor(palette_hex(self.palette_name, norm)), 1.7))
                painter.drawLine(last[0], last[1], pt[0], pt[1])
            last = pt
        # Numeric per-graph color bar.
        bar = QRectF(plot.right() + 12, plot.top() + 7, 10, max(24, plot.height() - 14))
        grad = QLinearGradient(bar.left(), bar.bottom(), bar.left(), bar.top())
        stops = COLOR_PALETTES.get(self.palette_name, COLOR_PALETTES["Seismic"])
        for i, color in enumerate(stops):
            grad.setColorAt(i / max(1, len(stops) - 1), QColor(color))
        painter.setBrush(grad); painter.setPen(QPen(QColor("#94A3B8"), 0.7)); painter.drawRect(bar)
        tiny = painter.font(); tiny.setPointSize(6); tiny.setBold(False); painter.setFont(tiny)
        painter.setPen(QColor("#475569"))
        painter.drawText(QRectF(bar.right()+3, bar.top()-5, 35, 14), Qt.AlignLeft | Qt.AlignVCenter, f"{ymax:.2g}")
        painter.drawText(QRectF(bar.right()+3, bar.bottom()-7, 35, 14), Qt.AlignLeft | Qt.AlignVCenter, f"{ymin:.2g}")
        painter.setPen(QColor("#003366"))
        small = painter.font(); small.setPointSize(7); small.setBold(False); painter.setFont(small)
        for k in range(5):
            val = ymin + (ymax-ymin)*k/4
            painter.drawText(2, ymap(val)+3, f"{val:.2f}")
        painter.drawText(rect.left()+4, rect.bottom()-5, "File:")
        painter.drawText(plot, Qt.AlignHCenter | Qt.AlignBottom, "Observation Number")
        stats = f"n={values.size}  min={float(np.nanmin(values)):.3g}  max={float(np.nanmax(values)):.3g}  mean={float(np.nanmean(values)):.3g}"
        painter.setPen(QColor("#395366"))
        painter.drawText(plot.adjusted(4, 2, -4, 0), Qt.AlignLeft | Qt.AlignTop, stats)


class GraphControl(QWidget):
    def __init__(self, plot: MiniPlot, default_max: float, default_limit: float, default_min: float, parent=None):
        super().__init__(parent)
        self.plot = plot
        self.setFixedWidth(96)
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 4, 6, 4)
        layout.setHorizontalSpacing(2)
        layout.setVerticalSpacing(2)
        self.max_box = self._number_box(default_max)
        self.limit_box = self._number_box(default_limit)
        self.min_box = self._number_box(default_min)
        layout.addWidget(self._label("Max"), 0, 0); layout.addWidget(self.max_box, 0, 1)
        set_btn = self._small_button("Set", "#305D8D", "#FFFFFF"); set_btn.clicked.connect(self.apply_range)
        layout.addWidget(set_btn, 1, 1)
        layout.addWidget(self._label("Limit"), 2, 0); layout.addWidget(self.limit_box, 2, 1)
        bmp = self._small_button("BMP", "#E8F2FF", "#0B2239"); bmp.clicked.connect(self.save_bmp); layout.addWidget(bmp, 3, 1)
        prn = self._small_button("Print", "#F4F7FA", "#0B2239"); prn.clicked.connect(self.print_plot); layout.addWidget(prn, 4, 1)
        layout.addWidget(self._label("Min"), 5, 0); layout.addWidget(self.min_box, 5, 1)
        layout.setRowStretch(6, 1)

    @staticmethod
    def _label(text: str) -> QLabel:
        lab = QLabel(text)
        lab.setStyleSheet("color:#0B2239;font-size:8pt;font-weight:600;")
        lab.setFixedWidth(34)
        return lab

    @staticmethod
    def _number_box(value: float) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(-999999.0, 999999.0)
        box.setDecimals(2)
        box.setValue(float(value))
        box.setFixedSize(56, 23)
        box.setButtonSymbols(QDoubleSpinBox.NoButtons)
        box.setStyleSheet("QDoubleSpinBox{background:#FFFFFF;color:#111;border:1px solid #9FB0C0;border-radius:2px;font-size:7pt;padding:1px;}")
        return box

    @staticmethod
    def _small_button(text: str, bg: str, fg: str) -> QPushButton:
        b = QPushButton(text)
        b.setFixedSize(48, 20)
        b.setStyleSheet(f"QPushButton{{background:{bg};color:{fg};border:1px solid #8BA4B8;border-radius:3px;font-weight:700;font-size:7pt;}} QPushButton:hover{{border-color:#2B7BBB;}}")
        return b

    def apply_range(self):
        self.plot.set_data(self.plot.values, float(self.limit_box.value()), float(self.min_box.value()), float(self.max_box.value()))

    def save_bmp(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save BMP", f"{self.plot.title.replace(' ', '_')}.bmp", "Bitmap (*.bmp);;PNG (*.png)")
        if not path:
            return
        pixmap = QPixmap(self.plot.size())
        self.plot.render(pixmap)
        pixmap.save(path)

    def print_plot(self):
        QMessageBox.information(self, "Print", "Graph print command received. Use BMP export when a printer is not configured.")


class DcfGraphsDialog(QDialog):
    PAGES = [
        [("Minimum Number of Satellites", "min_satellites", 5, 3, 10), ("Relative DOPS", "relative_dops", 2.5, 1, 4), ("PDOP", "pdop", 5, 1, 5), ("HDOP", "hdop", 1.5, 0, 3)],
        [("VDOP", "vdop", 2, 0, 5), ("RMS", "rms_m", 0.05, 0, 1), ("Horizontal SD", "horizontal_sd_m", 0.05, 0, 1), ("Vertical SD", "vertical_sd_m", 0.08, 0, 1)],
        [("Number of Positions Used", "positions_used", 5, 0, 20), ("Delta Time", "delta_time_s", 60, 0, 300), ("Horizontal Precision", "horizontal_precision_m", 0.05, 0, 1), ("Vertical Precision", "vertical_precision_m", 0.08, 0, 1)],
    ]

    def __init__(self, dataset: GeodeticDataset | None, parent=None):
        super().__init__(parent)
        self.dataset = dataset
        self.page_index = 0
        self._palette_name = "Seismic"
        self._plots: list[MiniPlot] = []
        self.setWindowTitle("DCFX Graphs1")
        self.resize(1220, 760)
        self.setMinimumSize(980, 620)
        self.setStyleSheet("""
            QDialog { background:#F4F7FB; color:#17212B; font-family:"Segoe UI", Arial, sans-serif; font-size:8pt; }
            QWidget#graphNavPanel { background:#FFFFFF; border:1px solid #D5DCE5; border-radius:8px; }
            QWidget#graphRowsPanel { background:#FFFFFF; border:1px solid #D5DCE5; border-radius:8px; }
            QLabel#graphHeader { color:#174EA6; font-size:10pt; font-weight:800; padding:4px 6px; }
            QPushButton#navButton { background:#EEF3F8; color:#0B2239; border:1px solid #B7C2CF; border-radius:7px; min-height:30px; font-weight:800; }
            QPushButton#navButton:hover { background:#E2ECF7; border-color:#2B7BBB; }
            QPushButton#closeNavButton { background:#FFEFEF; color:#A22A2A; border:1px solid #D19A9A; border-radius:7px; min-height:30px; font-weight:800; }
            QPushButton#nextNavButton { background:#E7F1FF; color:#174EA6; border:1px solid #8BB1DE; border-radius:7px; min-height:30px; font-weight:800; }
            QPushButton#prevNavButton { background:#F5EBDD; color:#7A4E12; border:1px solid #D4B57E; border-radius:7px; min-height:30px; font-weight:800; }
        """)
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        nav_panel = QWidget()
        nav_panel.setObjectName("graphNavPanel")
        nav_panel.setFixedWidth(105)
        nav = QVBoxLayout(nav_panel)
        nav.setContentsMargins(10, 10, 10, 10)
        nav.setSpacing(8)
        for text, slot, obj in (("Close", self.close, "closeNavButton"), ("Next Page", self.next_page, "nextNavButton"), ("Last Page", self.last_page, "prevNavButton")):
            b = QPushButton(text)
            b.setObjectName(obj)
            b.setFixedSize(84, 34)
            b.clicked.connect(slot)
            nav.addWidget(b)
        nav.addStretch(1)
        root.addWidget(nav_panel)

        rows_panel = QWidget()
        rows_panel.setObjectName("graphRowsPanel")
        rows_layout = QVBoxLayout(rows_panel)
        rows_layout.setContentsMargins(10, 10, 10, 10)
        rows_layout.setSpacing(8)
        header_row = QHBoxLayout()
        self.graph_header = QLabel("Geodetic QC Graphs")
        self.graph_header.setObjectName("graphHeader")
        header_row.addWidget(self.graph_header, 1)
        header_row.addWidget(QLabel("Global palette:"))
        self.palette_selector = PaletteSelectorButton(self._palette_name, rows_panel)
        self.palette_selector.setMinimumWidth(150)
        self.palette_selector.currentTextChanged.connect(self._set_palette)
        header_row.addWidget(self.palette_selector)
        rows_layout.addLayout(header_row)
        self.rows_box = QVBoxLayout()
        self.rows_box.setContentsMargins(0, 0, 0, 0)
        self.rows_box.setSpacing(8)
        rows_layout.addLayout(self.rows_box, 1)
        root.addWidget(rows_panel, 1)
        self.graph_header.setText(f"Geodetic QC Graphs — Page {self.page_index + 1}")
        self._draw_page()

    def _series(self, key: str) -> np.ndarray:
        if not self.dataset:
            return np.array([], dtype=float)
        arr = self.dataset.numeric_series("C6", key)
        return arr[np.isfinite(arr)]

    def _clear(self):
        self._plots.clear()
        while self.rows_box.count():
            item = self.rows_box.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _draw_page(self):
        self._clear()
        for title, key, limit, ymin, ymax in self.PAGES[self.page_index]:
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            plot = MiniPlot(title, self._series(key), limit)
            plot.set_data(plot.values, limit, ymin, ymax)
            plot.set_palette(self._palette_name)
            self._plots.append(plot)
            control = GraphControl(plot, ymax, limit, ymin)
            row_layout.addWidget(control)
            row_layout.addWidget(plot, 1)
            self.rows_box.addWidget(row_widget, 1)

    def _set_palette(self, palette_name: str) -> None:
        self._palette_name = palette_name
        for plot in self._plots:
            plot.set_palette(palette_name)

    def next_page(self):
        self.page_index = (self.page_index + 1) % len(self.PAGES)
        self.setWindowTitle(f"DCFX Graphs{self.page_index + 1}")
        self.graph_header.setText(f"Geodetic QC Graphs — Page {self.page_index + 1}")
        self._draw_page()

    def last_page(self):
        self.page_index = (self.page_index - 1) % len(self.PAGES)
        self.setWindowTitle(f"DCFX Graphs{self.page_index + 1}")
        self.graph_header.setText(f"Geodetic QC Graphs — Page {self.page_index + 1}")
        self._draw_page()


class GeodeticDashboard(QWidget):
    state_changed = Signal()
    activity_started = Signal(str, str)
    activity_progress = Signal(int, str)
    activity_finished = Signal()

    TAB_OVERVIEW = 0
    TAB_EXAMINER = 0
    TAB_QC = 0
    TAB_COORDINATES = 0
    TAB_SPATIAL = 0
    TAB_REPORT = 0

    def __init__(self, database_engine=None, parent=None):
        super().__init__(parent)
        self.database_engine = database_engine
        self.reader = DcFileReader()
        self.dataset: GeodeticDataset | None = None
        self.current_path: Path | None = None
        self.field_checks: dict[tuple[str, str], QCheckBox] = {}
        self.graph_dialog: DcfGraphsDialog | None = None
        self.setObjectName("dcExaminerRoot")
        self.setStyleSheet(QSS)
        self._build_ui()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        side_frame = QFrame()
        side_frame.setObjectName("geoSidebar")
        side_frame.setFixedWidth(140)
        side = QVBoxLayout(side_frame)
        side.setContentsMargins(10, 10, 10, 10)
        side.setSpacing(8)
        title = QLabel("Geodetic")
        title.setObjectName("sectionTitle")
        side.addWidget(title)
        open_btn = self._side_button("Open", self.open_file)
        exit_btn = self._side_button("Exit", self.close)
        side.addWidget(open_btn)
        side.addWidget(exit_btn)

        output = QGroupBox("Output")
        output_layout = QVBoxLayout(output)
        output_layout.setContentsMargins(8, 8, 8, 8)
        output_layout.setSpacing(5)
        self.text_check = ModernCheckBox("Text")
        self.text_check.setChecked(True)
        self.xls_check = ModernCheckBox("XLS")
        self.xls_check.setChecked(True)
        output_layout.addWidget(self.text_check)
        output_layout.addWidget(self.xls_check)
        side.addWidget(output)

        self.show_results_check = ModernCheckBox("Show Text Results")
        self.show_results_check.setChecked(True)
        self.show_results_check.stateChanged.connect(lambda *_: self._refresh_results())
        side.addWidget(self.show_results_check)
        graphs_btn = self._side_button("Graphs", self.show_graphs)
        side.addWidget(graphs_btn)
        side.addStretch(1)
        root.addWidget(side_frame)

        center_frame = QFrame()
        center_frame.setObjectName("geoMainPanel")
        center = QVBoxLayout(center_frame)
        center.setContentsMargins(10, 10, 10, 10)
        center.setSpacing(8)
        self.status = QLabel("No DC/geodetic file loaded")
        self.status.setObjectName("status")
        center.addWidget(self.status)

        self.tabs = QTabWidget()
        examiner_tab = QWidget()
        examiner_layout = QVBoxLayout(examiner_tab)
        examiner_layout.setContentsMargins(6, 6, 6, 6)
        examiner_layout.setSpacing(6)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(2, 2, 4, 4)
        self.body_layout.setSpacing(4)
        self._build_record_groups()
        scroll.setWidget(body)
        examiner_layout.addWidget(scroll, 1)
        self.tabs.addTab(examiner_tab, "Record Selection")

        results_tab = QWidget()
        results_layout = QVBoxLayout(results_tab)
        results_layout.setContentsMargins(6, 6, 6, 6)
        self.results = QTextEdit(self)
        self.results.setReadOnly(True)
        results_layout.addWidget(self.results, 1)
        self.tabs.addTab(results_tab, "Text Results")
        center.addWidget(self.tabs, 1)
        root.addWidget(center_frame, 1)

    def _side_button(self, text: str, slot) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("openButton" if text == "Open" else "graphButton" if text == "Graphs" else "sideButton")
        btn.clicked.connect(slot)
        btn.setMinimumWidth(108)
        return btn

    def _build_record_groups(self):
        for schema in RECORD_SCHEMAS:
            title = f"Record ID {' and '.join(schema.record_ids)} - {schema.title}"
            group = QGroupBox(title)
            if any(r in {"66", "67", "68"} for r in schema.record_ids):
                group.setProperty("accent", "green")
            if "C6" in schema.record_ids:
                group.setProperty("accent", "blue")
            row = QHBoxLayout(group); row.setContentsMargins(8, 8, 8, 8); row.setSpacing(10)
            buttons = QVBoxLayout(); buttons.setSpacing(4)
            all_btn = QPushButton("All"); all_btn.setObjectName("allButton")
            none_btn = QPushButton("None"); none_btn.setObjectName("noneButton")
            buttons.addWidget(all_btn); buttons.addWidget(none_btn)
            row.addLayout(buttons)
            field_box = QGridLayout(); field_box.setHorizontalSpacing(12); field_box.setVerticalSpacing(4)
            checks: list[QCheckBox] = []
            for i, (key, label) in enumerate(schema.fields):
                cb = ModernCheckBox(label); cb.setChecked(True)
                checks.append(cb)
                for record_id in schema.record_ids:
                    self.field_checks[(record_id.upper(), key)] = cb
                field_box.addWidget(cb, i // 6, i % 6)
            all_btn.clicked.connect(lambda _=False, items=checks: self._set_checks(items, True))
            none_btn.clicked.connect(lambda _=False, items=checks: self._set_checks(items, False))
            row.addLayout(field_box, 1)
            self.body_layout.addWidget(group)
        self.body_layout.addStretch(1)

    @staticmethod
    def _set_checks(checks: list[QCheckBox], state: bool):
        for cb in checks:
            cb.setChecked(state)

    def _selected_fields(self) -> dict[str, list[str]]:
        selected: dict[str, list[str]] = {}
        for (record_id, key), cb in self.field_checks.items():
            if cb.isChecked():
                selected.setdefault(record_id, []).append(key)
        return selected

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open DC/geodetic file", "", "Geodetic files (*.dc *.dcf *.txt *.csv *.tsv *.dat);;All files (*.*)")
        if not path:
            return
        try:
            self.dataset = self.reader.read(path)
            self.current_path = Path(path)
        except Exception as exc:
            QMessageBox.critical(self, "Open DC", str(exc))
            return
        ids = ", ".join(sorted(self.dataset.available_record_ids())) or "none"
        self.status.setText(f"File: {self.current_path.name} | Records: {self.dataset.record_count} | Record IDs: {ids}")
        self._refresh_results()
        self.state_changed.emit()

    def _refresh_results(self):
        if not self.show_results_check.isChecked():
            self.results.setText("Text results are hidden by the Show Text Results option.")
            return
        if not self.dataset:
            self.results.setText("Open a .dc/.txt/.csv geodetic file, select required fields, then export or view graphs.")
            return
        lines = [f"File: {self.dataset.source_path}", f"Format: {self.dataset.source_format}", f"Records: {self.dataset.record_count}", ""]
        selected = self._selected_fields()
        for record in self.dataset.records[:300]:
            keys = selected.get(record.record_id.upper(), [])
            if not keys:
                continue
            parts = [f"{FIELD_LABELS.get(k, k)}={record.values.get(k, '')}" for k in keys if k in record.values]
            if parts:
                lines.append(f"{record.record_id} | " + " | ".join(parts))
        if len(self.dataset.records) > 300:
            lines.append("... results truncated in preview; export for full results.")
        self.results.setText("\n".join(lines))

    def show_examiner(self):
        self.raise_(); self.setFocus(Qt.OtherFocusReason)

    def show_text_results(self):
        self.show_results_check.setChecked(True)
        self._refresh_results()
        dlg = QDialog(self)
        dlg.setWindowTitle("DC File Examiner - Text Results")
        dlg.resize(980, 520)
        dlg.setStyleSheet("QDialog{background:#F4F7FB;color:#17212B;font-family:\"Segoe UI\";font-size:8pt;} QTextEdit{background:#FFFFFF;color:#17212B;border:1px solid #D1DAE5;border-radius:6px;padding:6px;} QPushButton{background:#2F6FA7;color:white;border-radius:6px;padding:6px 14px;font-weight:700;} QPushButton:hover{background:#245D8D;}")
        layout = QVBoxLayout(dlg)
        text = QTextEdit(dlg); text.setReadOnly(True); text.setText(self.results.toPlainText())
        layout.addWidget(text, 1)
        close_btn = QPushButton("Close"); close_btn.clicked.connect(dlg.close)
        row = QHBoxLayout(); row.addStretch(1); row.addWidget(close_btn); layout.addLayout(row)
        dlg.exec()

    def _rows_for_export(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if not self.dataset:
            return rows
        selected = self._selected_fields()
        for record in self.dataset.records:
            keys = selected.get(record.record_id.upper(), [])
            row = {"record_id": record.record_id, "line_number": record.line_number}
            for key in keys:
                row[FIELD_LABELS.get(key, key)] = record.values.get(key, "")
            rows.append(row)
        return rows

    def export_text(self):
        if not self.dataset:
            QMessageBox.warning(self, "Export Text", "Open a DC/geodetic file first."); return
        path, _ = QFileDialog.getSaveFileName(self, "Export Text", "dc_file_examiner_selected.txt", "Text (*.txt);;CSV (*.csv)")
        if not path: return
        rows = self._rows_for_export()
        columns = sorted({k for row in rows for k in row.keys()}, key=lambda x: (x not in {"record_id", "line_number"}, x))
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns, delimiter="\t")
            writer.writeheader(); writer.writerows(rows)
        QMessageBox.information(self, "Export Text", f"Exported {len(rows)} rows.")

    def export_xlsx(self):
        if not self.dataset:
            QMessageBox.warning(self, "Export XLS", "Open a DC/geodetic file first."); return
        path, _ = QFileDialog.getSaveFileName(self, "Export XLS", "dc_file_examiner_selected.xlsx", "Excel (*.xlsx);;CSV (*.csv)")
        if not path: return
        rows = self._rows_for_export()
        columns = sorted({k for row in rows for k in row.keys()}, key=lambda x: (x not in {"record_id", "line_number"}, x))
        try:
            from openpyxl import Workbook
            wb = Workbook(); ws = wb.active; ws.title = "DC Results"; ws.append(columns)
            for row in rows: ws.append([row.get(c, "") for c in columns])
            wb.save(path)
        except Exception:
            with open(path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=columns); writer.writeheader(); writer.writerows(rows)
        QMessageBox.information(self, "Export XLS", f"Exported {len(rows)} rows.")

    def show_graphs(self):
        if self.graph_dialog is None or not self.graph_dialog.isVisible():
            self.graph_dialog = DcfGraphsDialog(self.dataset, self)
        else:
            self.graph_dialog.dataset = self.dataset
            self.graph_dialog._draw_page()
        self.graph_dialog.show(); self.graph_dialog.raise_(); self.graph_dialog.activateWindow()

    def previous_graph_page(self):
        self.show_graphs(); self.graph_dialog.last_page()

    def next_graph_page(self):
        self.show_graphs(); self.graph_dialog.next_page()

    def export_graphs(self):
        self.show_graphs()
        path, _ = QFileDialog.getSaveFileName(self, "Export Graph Window", "dcfx_graphs.bmp", "Bitmap (*.bmp);;PNG (*.png)")
        if not path: return
        pixmap = QPixmap(self.graph_dialog.size())
        self.graph_dialog.render(pixmap); pixmap.save(path)

    def run_qc(self):
        self.show_graphs()

    def show_qc(self):
        self.show_graphs()

    def show_positions(self):
        self._show_record_table("GPS Positions", ("66", "68"))

    def show_vectors(self):
        self._show_record_table("GPS Vectors", ("67",))

    def show_datum_crs(self):
        self._show_record_table("Datum / Coordinate System", ("49", "C8", "D5", "65"))

    def show_equipment(self):
        self._show_record_table("Equipment", ("56", "57", "E2"))

    def show_native_view(self, mode="2d"):
        self.show_positions()

    def show_geospatial_view(self, mode="2d"):
        self.show_positions()

    def generate_report(self):
        self.export_text()

    def _show_record_table(self, title: str, record_ids: tuple[str, ...]):
        if not self.dataset:
            QMessageBox.warning(self, title, "Open a DC/geodetic file first."); return
        records = self.dataset.records_for(*record_ids)
        if not records:
            QMessageBox.information(self, title, "No matching records found in selected file."); return
        dlg = QDialog(self); dlg.setWindowTitle(title); dlg.resize(980, 480)
        dlg.setStyleSheet(QSS)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(10, 10, 10, 10)
        table = QTableWidget(dlg); table.setAlternatingRowColors(True); layout.addWidget(table)
        keys = sorted({k for r in records for k in r.values.keys()})
        headers = ["Record ID", "Line"] + [FIELD_LABELS.get(k, k) for k in keys]
        table.setColumnCount(len(headers)); table.setHorizontalHeaderLabels(headers); table.setRowCount(len(records))
        for row_i, record in enumerate(records):
            table.setItem(row_i, 0, QTableWidgetItem(record.record_id)); table.setItem(row_i, 1, QTableWidgetItem(str(record.line_number)))
            for col_i, key in enumerate(keys, start=2): table.setItem(row_i, col_i, QTableWidgetItem(str(record.values.get(key, ""))))
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        dlg.exec()

    def _show_page(self, index: int):
        self.show_examiner()

    def handle_ribbon_action(self, action_id: str) -> None:
        mapping = {
            "geodetic_open": self.open_file,
            "geodetic_examiner": self.show_examiner,
            "geodetic_text_results": self.show_text_results,
            "geodetic_export_text": self.export_text,
            "geodetic_export_xlsx": self.export_xlsx,
            "geodetic_run_qc": self.run_qc,
            "geodetic_qc_results": self.show_qc,
            "geodetic_graph_prev": self.previous_graph_page,
            "geodetic_graph_next": self.next_graph_page,
            "geodetic_export_graphs": self.export_graphs,
            "geodetic_positions": self.show_positions,
            "geodetic_vectors": self.show_vectors,
            "geodetic_datum_crs": self.show_datum_crs,
            "geodetic_equipment": self.show_equipment,
            "geodetic_report_pdf": self.generate_report,
        }
        func = mapping.get(action_id)
        if func: func()
