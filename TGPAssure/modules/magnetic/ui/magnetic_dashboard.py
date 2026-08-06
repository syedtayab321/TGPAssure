from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QMouseEvent, QPainter, QPen, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QTabWidget,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from modules.magnetic.constants import (
    BASE_TOTAL_FIELD,
    DESPIKED_TOTAL_FIELD,
    DIURNAL_CORRECTED_FIELD,
    LEVELED_FIELD,
    MICROLEVELED_FIELD,
    RAW_TOTAL_FIELD,
)
from modules.magnetic.models import MagneticDataRole, MagneticDataset, MagneticSurveyType
from modules.magnetic.reader import MagneticReader


_ENMAG_QSS = """
QWidget#enmagDashboard {
    background:#EEF4F7;
    color:#102233;
    font-family: Arial, Helvetica, sans-serif;
    font-size: 7.4pt;
}
QWidget#enmagDashboard QLabel { background:transparent; color:#13293A; }
QFrame#magTopBar {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #06293A, stop:.55 #0C7891, stop:1 #20A5B8);
    border:0;
    border-radius:5px;
}
QLabel#magTopTitle { color:#FFFFFF; font-size:8.4pt; font-weight:800; }
QLabel#magTopHint { color:#D8F5FA; font-size:6.9pt; }
QLineEdit#pathEdit {
    background:#FFFFFF;
    border:1px solid rgba(255,255,255,.55);
    border-radius:5px;
    min-height:20px;
    padding:1px 6px;
    color:#102233;
}
QGroupBox {
    border:1px solid #CAD7DE;
    border-radius:5px;
    margin-top:8px;
    padding-top:8px;
    background:#FFFFFF;
    font-weight:700;
}
QGroupBox::title { subcontrol-origin: margin; left:9px; padding:0 4px; color:#174057; }
QTabWidget#settingsTabs::pane {
    border:1px solid #CAD7DE;
    border-radius:6px;
    background:#FFFFFF;
    top:-1px;
}
QTabWidget#settingsTabs QTabBar::tab {
    background:#DDEAF0;
    color:#2B4E62;
    border:1px solid #B9CBD5;
    border-bottom:0;
    border-top-left-radius:5px;
    border-top-right-radius:5px;
    padding:3px 7px;
    min-height:17px;
    font-size:7.0pt;
    font-weight:800;
}
QTabWidget#settingsTabs QTabBar::tab:selected {
    background:#FFFFFF;
    color:#08708C;
    border-top:3px solid #0C8EA8;
}
QLineEdit, QComboBox, QSpinBox, QTextEdit {
    background:#FFFFFF;
    border:1px solid #B7C7D0;
    border-radius:4px;
    min-height:19px;
    padding:1px 5px;
    color:#102233;
}
QCheckBox { color:#102233; background:transparent; font-size:7.1pt; }
QPushButton {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #FFFFFF, stop:1 #DDE9F0);
    border:1px solid #A9BBC6;
    border-radius:5px;
    padding:1px 6px;
    min-height:20px;
    color:#102233;
    font-weight:650;
}
QPushButton:hover { background:#E9F6FB; border-color:#5EA9C2; }
QPushButton:pressed { background:#CFE3ED; }
QPushButton#primaryButton {
    background:#0B7F9C;
    color:#FFFFFF;
    border-color:#066A82;
    font-weight:900;
}
QPushButton#primaryButton:hover { background:#0E99B9; }
QPushButton#zoomButton {
    background:#263440;
    color:white;
    font-weight:900;
    border-radius:4px;
    min-width:24px;
    max-width:24px;
    min-height:24px;
    max-height:24px;
    font-size:9pt;
}
QFrame#previewFrame {
    background:#F7FAFC;
    border:1px solid #CAD7DE;
    border-radius:5px;
}
QFrame#canvasFrame { background:#ECEEEB; border:1px solid #D5DDD9; border-radius:4px; }
QLabel#muted { color:#667A87; }
QLabel#statusLabel { color:#123247; font-weight:700; }
QTextEdit#summaryBox { background:#F9FBFC; font-size:7.0pt; }
QTableWidget { background:white; gridline-color:#D0D0D0; }
QHeaderView::section { background:#E6E6E6; border:1px solid #C0C0C0; padding:2px; font-size:7.0pt; }
"""


@dataclass(slots=True)
class _MagData:
    x: np.ndarray
    y: np.ndarray
    value: np.ndarray
    line: np.ndarray
    station: np.ndarray
    source: np.ndarray

    @property
    def size(self) -> int:
        return int(self.value.size)


class _EnmagPreviewCanvas(QWidget):
    cursor_changed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(620, 420)
        self.setMouseTracking(True)
        self._data: Optional[_MagData] = None
        self._grid: Optional[np.ndarray] = None
        self._grid_bounds: Optional[tuple[float, float, float, float]] = None
        self._color_min: Optional[float] = None
        self._color_max: Optional[float] = None
        self._opacity = 1.0
        self._point_radius = 2.2
        self._mode = "grid"
        self._filter_mask: Optional[np.ndarray] = None
        self._zoom = 1.0
        self._pan = QPointF(0.0, 0.0)
        self._drag_start: Optional[QPointF] = None
        self._pan_start: Optional[QPointF] = None
        self._cursor: Optional[QPointF] = None

    def set_data(self, data: Optional[_MagData]) -> None:
        self._data = data
        self._grid = None
        self._grid_bounds = None
        self._filter_mask = None
        self.fit()

    def set_grid(self, grid: Optional[np.ndarray], bounds: Optional[tuple[float, float, float, float]]) -> None:
        self._grid = grid
        self._grid_bounds = bounds
        self.update()

    def set_display_options(
        self,
        *,
        mode: str,
        color_min: Optional[float],
        color_max: Optional[float],
        opacity: float,
        point_radius: float,
        filter_mask: Optional[np.ndarray],
    ) -> None:
        self._mode = mode.lower()
        self._color_min = color_min
        self._color_max = color_max
        self._opacity = float(np.clip(opacity, 0.05, 1.0))
        self._point_radius = max(0.5, float(point_radius))
        self._filter_mask = filter_mask
        self.update()

    def fit(self) -> None:
        self._zoom = 1.0
        self._pan = QPointF(0.0, 0.0)
        self.update()

    def zoom_by(self, factor: float) -> None:
        self._zoom = float(np.clip(self._zoom * factor, 0.25, 32.0))
        self.update()

    def plot_rect(self) -> QRectF:
        return QRectF(12.0, 14.0, max(1.0, self.width() - 24.0), max(1.0, self.height() - 28.0))

    def _effective_mask(self) -> np.ndarray:
        if self._data is None:
            return np.zeros(0, dtype=bool)
        base = np.isfinite(self._data.x) & np.isfinite(self._data.y) & np.isfinite(self._data.value)
        if self._filter_mask is not None and self._filter_mask.size == base.size:
            base &= self._filter_mask
        return base

    def _bounds(self) -> tuple[float, float, float, float]:
        if self._data is None or self._data.size == 0:
            return 0.0, 1.0, 0.0, 1.0
        mask = self._effective_mask()
        if not np.any(mask):
            return 0.0, 1.0, 0.0, 1.0
        xmin = float(np.nanmin(self._data.x[mask])); xmax = float(np.nanmax(self._data.x[mask]))
        ymin = float(np.nanmin(self._data.y[mask])); ymax = float(np.nanmax(self._data.y[mask]))
        if abs(xmax - xmin) < 1e-9: xmax = xmin + 1.0
        if abs(ymax - ymin) < 1e-9: ymax = ymin + 1.0
        pad_x = (xmax - xmin) * 0.03
        pad_y = (ymax - ymin) * 0.03
        return xmin - pad_x, xmax + pad_x, ymin - pad_y, ymax + pad_y

    def _world_to_screen(self, x: np.ndarray | float, y: np.ndarray | float) -> tuple[np.ndarray | float, np.ndarray | float]:
        rect = self.plot_rect()
        xmin, xmax, ymin, ymax = self._bounds()
        cx = (xmin + xmax) / 2.0
        cy = (ymin + ymax) / 2.0
        span_x = (xmax - xmin) / self._zoom
        span_y = (ymax - ymin) / self._zoom
        xmin = cx - span_x / 2.0 - self._pan.x() * span_x
        xmax = cx + span_x / 2.0 - self._pan.x() * span_x
        ymin = cy - span_y / 2.0 + self._pan.y() * span_y
        ymax = cy + span_y / 2.0 + self._pan.y() * span_y
        sx = rect.left() + (np.asarray(x) - xmin) / max(1e-12, xmax - xmin) * rect.width()
        sy = rect.bottom() - (np.asarray(y) - ymin) / max(1e-12, ymax - ymin) * rect.height()
        if np.isscalar(x) and np.isscalar(y):
            return float(sx), float(sy)
        return sx, sy

    def _screen_to_world(self, p: QPointF) -> tuple[float, float]:
        rect = self.plot_rect()
        xmin, xmax, ymin, ymax = self._bounds()
        cx = (xmin + xmax) / 2.0
        cy = (ymin + ymax) / 2.0
        span_x = (xmax - xmin) / self._zoom
        span_y = (ymax - ymin) / self._zoom
        xmin = cx - span_x / 2.0 - self._pan.x() * span_x
        xmax = cx + span_x / 2.0 - self._pan.x() * span_x
        ymin = cy - span_y / 2.0 + self._pan.y() * span_y
        ymax = cy + span_y / 2.0 + self._pan.y() * span_y
        x = xmin + (p.x() - rect.left()) / max(1.0, rect.width()) * (xmax - xmin)
        y = ymax - (p.y() - rect.top()) / max(1.0, rect.height()) * (ymax - ymin)
        return float(x), float(y)

    @staticmethod
    def _palette(frac: float) -> QColor:
        f = float(np.clip(frac, 0.0, 1.0))
        stops = [
            (0.00, QColor(0, 45, 230)),
            (0.20, QColor(0, 188, 255)),
            (0.40, QColor(42, 210, 105)),
            (0.60, QColor(245, 238, 70)),
            (0.78, QColor(255, 140, 30)),
            (1.00, QColor(232, 0, 58)),
        ]
        for (f0, c0), (f1, c1) in zip(stops[:-1], stops[1:]):
            if f <= f1:
                t = 0.0 if f1 == f0 else (f - f0) / (f1 - f0)
                return QColor(
                    int(c0.red() + (c1.red() - c0.red()) * t),
                    int(c0.green() + (c1.green() - c0.green()) * t),
                    int(c0.blue() + (c1.blue() - c0.blue()) * t),
                    int(255 * self_alpha_safe()),
                )
        return QColor(232, 0, 58)

    def _color_for_value(self, value: float) -> QColor:
        vmin, vmax = self._color_range()
        f = (float(value) - vmin) / max(1e-12, vmax - vmin)
        c = self._palette(f)
        c.setAlpha(int(255 * self._opacity))
        return c

    def _color_range(self) -> tuple[float, float]:
        if self._data is None or self._data.size == 0:
            return 0.0, 1.0
        mask = self._effective_mask()
        finite = self._data.value[mask]
        finite = finite[np.isfinite(finite)]
        if finite.size == 0:
            return 0.0, 1.0
        if self._color_min is not None and self._color_max is not None and self._color_max > self._color_min:
            return float(self._color_min), float(self._color_max)
        lo = float(np.nanpercentile(finite, 2.0))
        hi = float(np.nanpercentile(finite, 98.0))
        if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
            lo = float(np.nanmin(finite)); hi = float(np.nanmax(finite))
        if hi <= lo:
            hi = lo + 1.0
        return lo, hi

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(236, 236, 233))
        plot = self.plot_rect()
        painter.fillRect(plot, QColor(238, 238, 235))
        painter.setPen(QPen(QColor(218, 218, 214), 1))
        painter.drawRect(plot)
        if self._data is None or self._data.size == 0:
            painter.setPen(QPen(QColor(50, 50, 50), 1))
            painter.drawText(plot, Qt.AlignmentFlag.AlignCenter, "Select a magnetic log folder or file, then click Draw.")
            painter.end()
            return
        if self._mode in {"grid", "mag"} and self._grid is not None and self._grid.size:
            self._draw_grid(painter, plot)
        self._draw_points(painter, plot)
        if self._cursor is not None and plot.contains(self._cursor):
            painter.setPen(QPen(QColor(50, 50, 50), 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(plot.left(), self._cursor.y()), QPointF(plot.right(), self._cursor.y()))
            painter.drawLine(QPointF(self._cursor.x(), plot.top()), QPointF(self._cursor.x(), plot.bottom()))
        painter.end()

    def _draw_grid(self, painter: QPainter, plot: QRectF) -> None:
        if self._grid is None or self._grid_bounds is None:
            return
        grid = self._grid
        rows, cols = grid.shape
        if rows == 0 or cols == 0:
            return
        image = QImage(cols, rows, QImage.Format.Format_ARGB32)
        image.fill(QColor(0, 0, 0, 0))
        for r in range(rows):
            for c in range(cols):
                value = float(grid[r, c])
                if np.isfinite(value):
                    image.setPixelColor(c, r, self._color_for_value(value))
        painter.drawImage(plot, image)

    def _draw_points(self, painter: QPainter, _plot: QRectF) -> None:
        if self._data is None:
            return
        mask = self._effective_mask()
        if not np.any(mask):
            return
        x = self._data.x[mask]
        y = self._data.y[mask]
        v = self._data.value[mask]
        sx, sy = self._world_to_screen(x, y)
        point_count = len(v)
        step = max(1, int(math.ceil(point_count / 50000)))
        radius = self._point_radius
        for px, py, val in zip(np.asarray(sx)[::step], np.asarray(sy)[::step], v[::step]):
            if not np.isfinite(px) or not np.isfinite(py) or not np.isfinite(val):
                continue
            painter.setPen(QPen(QColor(20, 20, 20, 150), 0.5))
            painter.setBrush(self._color_for_value(float(val)))
            painter.drawEllipse(QPointF(float(px), float(py)), radius, radius)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position()
            self._pan_start = QPointF(self._pan)
            event.accept(); return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        point = event.position()
        self._cursor = point if self.plot_rect().contains(point) else None
        if self._drag_start is not None and event.buttons() & Qt.MouseButton.LeftButton:
            delta = point - self._drag_start
            plot = self.plot_rect()
            self._pan = self._pan_start + QPointF(delta.x() / max(1.0, plot.width()), -delta.y() / max(1.0, plot.height()))
            self.update(); event.accept(); return
        if self._cursor is not None and self._data is not None and self._data.size:
            wx, wy = self._screen_to_world(point)
            mask = self._effective_mask()
            if np.any(mask):
                dx = self._data.x[mask] - wx
                dy = self._data.y[mask] - wy
                idx_local = int(np.nanargmin(dx * dx + dy * dy))
                global_idx = np.flatnonzero(mask)[idx_local]
                self.cursor_changed.emit(
                    f"X {self._data.x[global_idx]:.3f} | Y {self._data.y[global_idx]:.3f} | Mag {self._data.value[global_idx]:.6g} | Line {self._data.line[global_idx]} | Source {self._data.source[global_idx]}"
                )
        self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = None
            self._pan_start = None
            event.accept(); return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        self.zoom_by(1.2 if event.angleDelta().y() > 0 else 1 / 1.2)
        event.accept()


def self_alpha_safe() -> float:
    # Kept as a function to avoid repeating magic constants in the static colour interpolator.
    return 1.0


class _EnmagColorBar(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(24)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(238, 238, 235))
        painter.setPen(QPen(QColor(20, 20, 20), 1))
        painter.drawText(QRectF(0, 0, 58, 22), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "Low")
        painter.drawText(QRectF(self.width() - 58, 0, 58, 22), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "High")
        rect = QRectF(92, 5, max(10, self.width() - 184), 14)
        for x in range(int(rect.left()), int(rect.right())):
            f = (x - rect.left()) / max(1.0, rect.width())
            c = _EnmagPreviewCanvas._palette(f)
            c.setAlpha(255)
            painter.setPen(QPen(c, 1))
            painter.drawLine(x, int(rect.top()), x, int(rect.bottom()))
        painter.setPen(QPen(QColor(160, 160, 160), 1))
        painter.drawRect(rect)
        painter.end()


class MagneticDashboard(QWidget):
    """EnMag-style magnetic log QC workspace.

    This replaces the prior large magnetic dashboard with a direct EnMag-inspired
    screen: folder selector, grid settings, colour controls, map preview, panning,
    zooming, filtering, drawing and export. The class keeps the method names used
    by the main TGPAssure ribbon so the rest of the software can call the same
    actions.
    """

    dataset_changed = Signal(object)
    activity_started = Signal(str, str)
    activity_progress = Signal(int, str)
    activity_finished = Signal()

    TAB_OVERVIEW = 0
    TAB_QC = 0
    TAB_PROCESSING = 0
    TAB_SPATIAL = 0
    TAB_REPORTS = 0

    def __init__(self, controller=None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setObjectName("enmagDashboard")
        self.setProperty("module_id", "magnetic")
        self.setStyleSheet(_ENMAG_QSS)
        self.reader = MagneticReader()
        self.rover: Optional[MagneticDataset] = None
        self.base: Optional[MagneticDataset] = None
        self.boundary = None
        self._mag_data: Optional[_MagData] = None
        self._current_channel = RAW_TOTAL_FIELD
        self._last_grid: Optional[np.ndarray] = None
        self._last_grid_bounds: Optional[tuple[float, float, float, float]] = None
        self._filter_mask: Optional[np.ndarray] = None
        self._build_ui()
        self._refresh_controls()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(5, 5, 5, 5)
        root.setSpacing(4)

        top_frame = QFrame()
        top_frame.setObjectName("magTopBar")
        top = QHBoxLayout(top_frame)
        top.setContentsMargins(8, 5, 8, 5)
        top.setSpacing(6)
        log_label = QLabel("Log File")
        log_label.setStyleSheet("color:#FFFFFF;font-weight:700;font-size:7.3pt;")
        top.addWidget(log_label)
        self.path_edit = QLineEdit()
        self.path_edit.setObjectName("pathEdit")
        self.path_edit.returnPressed.connect(lambda: self.open_rover_path(self.path_edit.text()))
        top.addWidget(self.path_edit, 1)
        self.select_folder_btn = QPushButton("Select Folder")
        self.select_folder_btn.setObjectName("primaryButton")
        self.select_folder_btn.clicked.connect(self.select_folder)
        top.addWidget(self.select_folder_btn)
        root.addWidget(top_frame)

        main = QHBoxLayout()
        main.setSpacing(5)
        root.addLayout(main, 1)

        settings_group = QGroupBox("Settings")
        settings_group.setFixedWidth(214)
        settings_outer = QVBoxLayout(settings_group)
        settings_outer.setContentsMargins(6, 8, 6, 6)
        settings_outer.setSpacing(4)
        self.settings_tabs = QTabWidget()
        self.settings_tabs.setObjectName("settingsTabs")
        self.settings_tabs.setDocumentMode(True)
        self.settings_tabs.tabBar().setExpanding(False)
        settings_outer.addWidget(self.settings_tabs, 1)

        general_tab = QWidget()
        general = QGridLayout(general_tab)
        general.setContentsMargins(5, 5, 5, 5)
        general.setHorizontalSpacing(4)
        general.setVerticalSpacing(5)
        row = 0
        self.preview_mode = QComboBox(); self.preview_mode.addItems(["Grid", "Points", "Grid + Points"])
        self.preview_mode.currentIndexChanged.connect(self._refresh_draw_only)
        row = self._add_row(general, row, "Preview", self.preview_mode)
        self.grid_cols = QSpinBox(); self.grid_cols.setRange(8, 512); self.grid_cols.setValue(64)
        row = self._add_row(general, row, "Cols", self.grid_cols)
        self.grid_rows = QSpinBox(); self.grid_rows.setRange(8, 512); self.grid_rows.setValue(64)
        row = self._add_row(general, row, "Rows", self.grid_rows)
        self.point_radius = QLineEdit("2.2")
        row = self._add_row(general, row, "Point", self.point_radius)
        self.idw_power = QLineEdit("0.7")
        row = self._add_row(general, row, "IDW", self.idw_power)
        self.opacity = QSlider(Qt.Orientation.Horizontal); self.opacity.setRange(5, 100); self.opacity.setValue(100)
        self.opacity_label = QLabel("100%")
        opbox = QHBoxLayout(); opbox.setContentsMargins(0,0,0,0); opbox.setSpacing(4); opbox.addWidget(self.opacity, 1); opbox.addWidget(self.opacity_label)
        opw = QWidget(); opw.setLayout(opbox)
        self.opacity.valueChanged.connect(lambda v: (self.opacity_label.setText(f"{v}%"), self._refresh_draw_only()))
        row = self._add_row(general, row, "Opacity", opw)
        general.setRowStretch(row, 1)
        self.settings_tabs.addTab(general_tab, "Grid")

        colour_tab = QWidget()
        colour = QGridLayout(colour_tab)
        colour.setContentsMargins(5, 5, 5, 5)
        colour.setHorizontalSpacing(4)
        colour.setVerticalSpacing(5)
        row = 0
        self.color_scale = QComboBox(); self.color_scale.addItems(["Robust Auto", "Full Range", "Manual"])
        self.color_scale.currentIndexChanged.connect(self._refresh_draw_only)
        row = self._add_row(colour, row, "Scale", self.color_scale)
        self.color_min = QLineEdit()
        row = self._add_row(colour, row, "Min", self.color_min)
        self.color_max = QLineEdit()
        row = self._add_row(colour, row, "Max", self.color_max)
        self.reset_color_btn = QPushButton("Reset Colour")
        self.reset_color_btn.clicked.connect(self.reset_color)
        colour.addWidget(self.reset_color_btn, row, 0, 1, 2); row += 1
        colour.setRowStretch(row, 1)
        self.settings_tabs.addTab(colour_tab, "Colour")

        data_tab = QWidget()
        data = QGridLayout(data_tab)
        data.setContentsMargins(5, 5, 5, 5)
        data.setHorizontalSpacing(4)
        data.setVerticalSpacing(5)
        row = 0
        self.grid_type = QComboBox(); self.grid_type.addItems(["Mag", "TMI", "Despiked", "Diurnal Corrected", "Leveled", "Microleveled"])
        self.grid_type.currentIndexChanged.connect(lambda *_: (self._select_channel_from_combo(), self._refresh_draw_only()))
        row = self._add_row(data, row, "Channel", self.grid_type)
        self.interp = QComboBox(); self.interp.addItems(["Fast Grid", "IDW", "Nearest", "Points Only"])
        row = self._add_row(data, row, "Interp.", self.interp)
        self.include_invalid = QCheckBox("Include invalid samples")
        data.addWidget(self.include_invalid, row, 0, 1, 2); row += 1
        self.heading_export = QCheckBox("Heading info export")
        data.addWidget(self.heading_export, row, 0, 1, 2); row += 1
        data.addWidget(QLabel("Summary"), row, 0, 1, 2); row += 1
        self.summary = QTextEdit(); self.summary.setObjectName("summaryBox"); self.summary.setMinimumHeight(100); self.summary.setReadOnly(True)
        data.addWidget(self.summary, row, 0, 1, 2); row += 1
        data.setRowStretch(row, 1)
        self.settings_tabs.addTab(data_tab, "Data")
        main.addWidget(settings_group)

        preview_frame = QFrame()
        preview_frame.setObjectName("previewFrame")
        p = QVBoxLayout(preview_frame)
        p.setContentsMargins(8, 8, 8, 6)
        p.setSpacing(5)
        note = QLabel("North up | drag to pan | wheel/buttons to zoom")
        note.setStyleSheet("font-size:7.4pt;font-weight:700;color:#123247;")
        p.addWidget(note)
        controls = QHBoxLayout()
        controls.setSpacing(6)
        self.preview_help = QLabel("Move over the map to inspect grid and nearest point values.")
        self.preview_help.setObjectName("muted")
        controls.addWidget(self.preview_help, 1)
        self.pan_btn = QPushButton("Pan")
        self.filter_btn = QPushButton("Filter"); self.filter_btn.clicked.connect(self.apply_filter)
        self.reset_filter_btn = QPushButton("Reset Filter"); self.reset_filter_btn.clicked.connect(self.reset_filter)
        self.filter_combo = QComboBox(); self.filter_combo.addItems(["None", "Valid Mag", "Inside Robust Range", "High Only", "Low Only", "Invalid Only"])
        self.filter_combo.setMaximumWidth(118)
        controls.addWidget(self.pan_btn); controls.addWidget(self.filter_btn); controls.addWidget(self.reset_filter_btn); controls.addWidget(self.filter_combo)
        p.addLayout(controls)
        p.addWidget(self._color_bar())
        canvas_frame = QFrame(); canvas_frame.setObjectName("canvasFrame")
        canvas_layout = QGridLayout(canvas_frame); canvas_layout.setContentsMargins(0,0,0,0)
        self.canvas = _EnmagPreviewCanvas(self)
        self.canvas.cursor_changed.connect(self._set_cursor_text)
        canvas_layout.addWidget(self.canvas, 0, 0, 3, 3)
        self.zoom_in_btn = QPushButton("+"); self.zoom_in_btn.setObjectName("zoomButton"); self.zoom_in_btn.clicked.connect(lambda: self.canvas.zoom_by(1.25))
        self.zoom_out_btn = QPushButton("-"); self.zoom_out_btn.setObjectName("zoomButton"); self.zoom_out_btn.clicked.connect(lambda: self.canvas.zoom_by(0.8))
        canvas_layout.addWidget(self.zoom_in_btn, 0, 0, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        canvas_layout.addWidget(self.zoom_out_btn, 1, 0, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        p.addWidget(canvas_frame, 1)
        main.addWidget(preview_frame, 1)

        bottom = QHBoxLayout()
        bottom.setSpacing(5)
        self.status = QLabel("No .txt files found")
        self.status.setObjectName("statusLabel")
        bottom.addWidget(self.status, 1)
        self.draw_btn = QPushButton("Draw"); self.draw_btn.setObjectName("primaryButton"); self.draw_btn.clicked.connect(self.draw)
        self.export_btn = QPushButton("Export"); self.export_btn.clicked.connect(self.export_csv)
        bottom.addWidget(self.draw_btn); bottom.addWidget(self.export_btn)
        root.addLayout(bottom)

    def _add_row(self, layout: QGridLayout, row: int, label: str, widget: QWidget) -> int:
        layout.addWidget(QLabel(label), row, 0)
        layout.addWidget(widget, row, 1)
        return row + 1

    def _color_bar(self) -> QWidget:
        return _EnmagColorBar(self)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------
    def select_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select EnMag / magnetic log folder", str(Path.home()))
        if folder:
            self.open_folder(folder)

    def open_folder(self, folder: str | Path) -> None:
        path = Path(folder)
        self.path_edit.setText(str(path))
        files = [p for p in sorted(path.iterdir()) if p.suffix.lower() in {".txt", ".csv", ".dat", ".log", ".mag"}]
        if not files:
            self.status.setText(f"No .txt files found in {path}")
            self.summary.setPlainText(f"No supported magnetic log files were found in:\n{path}")
            return
        self.activity_started.emit("Loading Magnetic Folder", f"Reading {len(files)} magnetic log file(s)")
        datasets: list[MagneticDataset] = []
        errors: list[str] = []
        for i, f in enumerate(files, start=1):
            try:
                datasets.append(self._read_any_magnetic_file(f))
            except Exception as exc:
                errors.append(f"{f.name}: {exc}")
            self.activity_progress.emit(int(i / max(1, len(files)) * 100), f"Read {f.name}")
            QApplication.processEvents()
        if not datasets:
            self.activity_finished.emit()
            QMessageBox.warning(self, "Magnetic Load", "No readable magnetic files were found.\n\n" + "\n".join(errors[:8]))
            return
        self.rover = self._merge_datasets(datasets, path)
        self._current_channel = self._default_channel(self.rover)
        self._rebuild_mag_data()
        self.canvas.set_data(self._mag_data)
        self.status.setText(f"Loaded {len(datasets)} file(s), {self.rover.record_count:,} samples from {path}")
        self._update_summary(errors)
        self.dataset_changed.emit(self.rover)
        self.activity_finished.emit()
        self.draw()

    def open_rover(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open magnetic rover/log file", str(Path.home()), "Magnetic logs (*.txt *.csv *.dat *.log *.mag);;All Files (*.*)")
        if path:
            self.open_rover_path(path)

    def open_rover_path(self, path: str | Path, *, show_import_dialog: bool = False) -> None:
        p = Path(path)
        if p.is_dir():
            self.open_folder(p); return
        self.path_edit.setText(str(p))
        try:
            self.activity_started.emit("Loading Magnetic Log", f"Reading {p.name}")
            self.rover = self._read_any_magnetic_file(p)
            self._current_channel = self._default_channel(self.rover)
            self._rebuild_mag_data()
            self.canvas.set_data(self._mag_data)
            self.status.setText(f"Loaded {p.name} — {self.rover.record_count:,} samples")
            self._update_summary([])
            self.dataset_changed.emit(self.rover)
            self.draw()
        except Exception as exc:
            QMessageBox.critical(self, "Magnetic Import Error", str(exc))
        finally:
            self.activity_finished.emit()

    def open_base(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open magnetic base station file", str(Path.home()), "Magnetic base (*.txt *.csv *.dat *.log *.mag);;All Files (*.*)")
        if not path:
            return
        try:
            self.base = self.reader.read_base(path)
        except Exception:
            self.base = self._read_any_magnetic_file(path, role=MagneticDataRole.BASE, survey_type=MagneticSurveyType.BASE_STATION)
        self.status.setText(f"Base station loaded: {Path(path).name}")
        self._update_summary([])
        self.dataset_changed.emit(self.rover)

    def open_boundary(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open magnetic boundary", str(Path.home()), "Boundary (*.kml *.kmz *.geojson *.json);;All Files (*.*)")
        if not path:
            return
        self.boundary = Path(path)
        self.status.setText(f"Boundary file selected: {self.boundary.name}")
        self._update_summary([])

    def _read_any_magnetic_file(self, path: Path, *, role: MagneticDataRole = MagneticDataRole.ROVER, survey_type: MagneticSurveyType = MagneticSurveyType.GROUND) -> MagneticDataset:
        try:
            if role == MagneticDataRole.BASE:
                return self.reader.read_base(path)
            return self.reader.read_rover(path)
        except Exception:
            return self._read_generic_text(path, role=role, survey_type=survey_type)

    @staticmethod
    def _decode_text(path: Path) -> str:
        raw = path.read_bytes()
        for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("latin-1", errors="replace")

    @staticmethod
    def _norm(name: str) -> str:
        return "".join(ch.lower() if ch.isalnum() else "_" for ch in str(name)).strip("_")

    def _read_generic_text(self, path: Path, *, role: MagneticDataRole, survey_type: MagneticSurveyType) -> MagneticDataset:
        text = self._decode_text(path)
        lines = [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith(("#", "//"))]
        if not lines:
            raise ValueError("File contains no readable rows")
        try:
            dialect = csv.Sniffer().sniff("\n".join(lines[:20]), delimiters=",;\t| ")
            rows = list(csv.reader(lines, dialect))
        except Exception:
            rows = [ln.replace(",", " ").split() for ln in lines]
        header_idx = 0
        header = [self._norm(c) for c in rows[0]]
        numeric_first = sum(self._to_float(c) is not None for c in rows[0]) >= max(2, len(rows[0]) // 2)
        if numeric_first:
            max_cols = max(len(r) for r in rows)
            header = [f"col_{i+1}" for i in range(max_cols)]
            data_rows = rows
        else:
            data_rows = rows[1:]
        columns: dict[str, list[str]] = {h: [] for h in header}
        for r in data_rows:
            for i, h in enumerate(header):
                columns[h].append(r[i] if i < len(r) else "")
        n = len(data_rows)
        if n == 0:
            raise ValueError("File contains a header but no data rows")
        def find(names: Iterable[str], contains: Iterable[str] = ()) -> Optional[str]:
            name_set = {self._norm(x) for x in names}
            for h in header:
                if h in name_set:
                    return h
            for h in header:
                if any(token in h for token in contains):
                    return h
            return None
        mag_col = find(["mag", "tmi", "total_field", "total_field_raw", "field", "nt", "value", "magnetic"], ["mag", "tmi", "field"])
        x_col = find(["x", "e", "east", "easting", "lon", "long", "longitude"], ["east", "lon"])
        y_col = find(["y", "n", "north", "northing", "lat", "latitude"], ["north", "lat"])
        line_col = find(["line", "line_id", "lineno", "profile"], ["line"])
        station_col = find(["station", "station_id", "stn", "fid", "record"], ["station", "stn"])
        if mag_col is None:
            # fallback: first numeric column with a magnetic-looking dynamic range
            best = None; best_score = -1.0
            for h in header:
                arr = np.asarray([self._to_float(v) if self._to_float(v) is not None else np.nan for v in columns[h]], dtype=float)
                finite = arr[np.isfinite(arr)]
                if finite.size >= max(3, n // 5):
                    score = float(np.nanstd(finite)) + (5.0 if np.nanmedian(np.abs(finite)) > 100 else 0.0)
                    if score > best_score:
                        best = h; best_score = score
            mag_col = best
        if mag_col is None:
            raise ValueError("Could not identify a magnetic value column")
        value = self._float_array(columns[mag_col])
        if x_col is None or y_col is None:
            x = np.arange(n, dtype=float)
            y = np.zeros(n, dtype=float)
        else:
            x = self._float_array(columns[x_col]); y = self._float_array(columns[y_col])
        line = np.asarray(columns[line_col] if line_col else [path.stem] * n, dtype=object)
        station = np.asarray(columns[station_col] if station_col else [str(i + 1) for i in range(n)], dtype=object)
        ts = np.datetime64("2026-01-01T00:00:00.000") + np.arange(n).astype("timedelta64[ms]")
        return MagneticDataset(
            source_path=path,
            role=role,
            survey_type=survey_type,
            timestamps=ts,
            channels={RAW_TOTAL_FIELD: value, "mag": value, "tmi": value},
            x=x,
            y=y,
            elevation=np.full(n, np.nan),
            line_id=line,
            station_id=station,
            metadata={"reader": "EnMag generic text", "mag_column": mag_col, "x_column": x_col, "y_column": y_col},
            crs=None,
        )

    @staticmethod
    def _to_float(value: object) -> Optional[float]:
        try:
            text = str(value).strip().replace(",", "")
            if text == "":
                return None
            return float(text)
        except Exception:
            return None

    def _float_array(self, values: Iterable[object]) -> np.ndarray:
        return np.asarray([self._to_float(v) if self._to_float(v) is not None else np.nan for v in values], dtype=float)

    def _merge_datasets(self, datasets: list[MagneticDataset], source_path: Path) -> MagneticDataset:
        channel_names: set[str] = set()
        for ds in datasets:
            channel_names.update(ds.channels)
        channels: dict[str, np.ndarray] = {}
        for name in channel_names:
            parts = []
            for ds in datasets:
                if name in ds.channels:
                    parts.append(ds.channels[name])
                else:
                    parts.append(np.full(ds.record_count, np.nan))
            channels[name] = np.concatenate(parts)
        ts = np.concatenate([ds.timestamps for ds in datasets])
        x = np.concatenate([ds.x for ds in datasets])
        y = np.concatenate([ds.y for ds in datasets])
        elevation = np.concatenate([ds.elevation for ds in datasets])
        line = np.concatenate([ds.line_id if ds.line_id is not None else np.full(ds.record_count, ds.source_path.stem, dtype=object) for ds in datasets])
        station = np.concatenate([ds.station_id if ds.station_id is not None else np.arange(ds.record_count).astype(str) for ds in datasets])
        return MagneticDataset(
            source_path=source_path,
            role=MagneticDataRole.ROVER,
            survey_type=MagneticSurveyType.GROUND,
            timestamps=ts,
            channels=channels,
            x=x,
            y=y,
            elevation=elevation,
            line_id=line,
            station_id=station,
            metadata={"merged_files": [str(ds.source_path) for ds in datasets]},
            crs=datasets[0].crs,
        )

    def _default_channel(self, dataset: MagneticDataset) -> str:
        for name in (RAW_TOTAL_FIELD, "mag", "tmi", "total_field", BASE_TOTAL_FIELD):
            if name in dataset.channels:
                return name
        return dataset.channel_names[0]

    # ------------------------------------------------------------------
    # Drawing / processing
    # ------------------------------------------------------------------
    def _select_channel_from_combo(self) -> None:
        text = self.grid_type.currentText().lower()
        mapping = {
            "mag": RAW_TOTAL_FIELD,
            "tmi": "tmi",
            "despiked": DESPIKED_TOTAL_FIELD,
            "diurnal corrected": DIURNAL_CORRECTED_FIELD,
            "leveled": LEVELED_FIELD,
            "microleveled": MICROLEVELED_FIELD,
        }
        selected = mapping.get(text, self._current_channel)
        if self.rover and selected not in self.rover.channels:
            if text == "tmi" and "mag" in self.rover.channels:
                selected = "mag"
            else:
                selected = self._default_channel(self.rover)
        self._current_channel = selected
        self._rebuild_mag_data()

    def _rebuild_mag_data(self) -> None:
        if self.rover is None:
            self._mag_data = None; return
        if self._current_channel not in self.rover.channels:
            self._current_channel = self._default_channel(self.rover)
        value = np.asarray(self.rover.channels[self._current_channel], dtype=float)
        source = np.full(self.rover.record_count, self.rover.source_path.name, dtype=object)
        if "merged_files" in self.rover.metadata:
            source = np.asarray([self.rover.source_path.name] * self.rover.record_count, dtype=object)
        self._mag_data = _MagData(
            x=np.asarray(self.rover.x, dtype=float),
            y=np.asarray(self.rover.y, dtype=float),
            value=value,
            line=np.asarray(self.rover.line_id, dtype=object),
            station=np.asarray(self.rover.station_id, dtype=object),
            source=source,
        )
        self.canvas.set_data(self._mag_data)

    def draw(self) -> None:
        if self._mag_data is None or self._mag_data.size == 0:
            QMessageBox.information(self, "EnMag Draw", "Load a magnetic folder or log file first.")
            return
        self._select_channel_from_combo()
        self.activity_started.emit("Drawing Magnetic Preview", "Generating EnMag-style magnetic preview")
        try:
            grid = None; bounds = None
            mode = self.preview_mode.currentText().lower()
            if "grid" in mode and self.interp.currentText() != "Points Only":
                grid, bounds = self._make_grid()
            self._last_grid = grid; self._last_grid_bounds = bounds
            self.canvas.set_grid(grid, bounds)
            self._refresh_canvas_options()
            self.status.setText(f"Drawn {self._current_channel} preview — {self._visible_count():,} visible sample(s)")
        except Exception as exc:
            QMessageBox.critical(self, "Magnetic Draw Error", str(exc))
        finally:
            self.activity_finished.emit()

    def _make_grid(self) -> tuple[np.ndarray, tuple[float, float, float, float]]:
        if self._mag_data is None:
            raise ValueError("No magnetic data loaded")
        mask = self._mask_for_grid()
        if not np.any(mask):
            raise ValueError("No valid samples are available for gridding")
        x = self._mag_data.x[mask]; y = self._mag_data.y[mask]; z = self._mag_data.value[mask]
        xmin, xmax = float(np.nanmin(x)), float(np.nanmax(x))
        ymin, ymax = float(np.nanmin(y)), float(np.nanmax(y))
        if xmax <= xmin: xmax = xmin + 1.0
        if ymax <= ymin: ymax = ymin + 1.0
        cols = int(self.grid_cols.value()); rows = int(self.grid_rows.value())
        gx = np.linspace(xmin, xmax, cols)
        gy = np.linspace(ymax, ymin, rows)  # image row order: north at top
        grid = np.full((rows, cols), np.nan, dtype=float)
        method = self.interp.currentText().lower()
        power = self._float_from_line(self.idw_power, 0.7)
        for r, yy in enumerate(gy):
            self.activity_progress.emit(int(r / max(1, rows - 1) * 100), "Interpolating magnetic grid")
            for c, xx in enumerate(gx):
                d2 = (x - xx) ** 2 + (y - yy) ** 2
                if d2.size == 0:
                    continue
                nearest = int(np.argmin(d2))
                if method in {"fast grid", "nearest"} or x.size > 12000:
                    grid[r, c] = z[nearest]
                else:
                    d = np.sqrt(np.maximum(d2, 1e-12))
                    order = np.argsort(d)[: min(24, d.size)]
                    w = 1.0 / np.power(d[order], max(0.1, power))
                    grid[r, c] = float(np.sum(w * z[order]) / np.sum(w))
        return grid, (xmin, xmax, ymin, ymax)

    def _mask_for_grid(self) -> np.ndarray:
        if self._mag_data is None:
            return np.zeros(0, dtype=bool)
        mask = np.isfinite(self._mag_data.x) & np.isfinite(self._mag_data.y)
        if not self.include_invalid.isChecked():
            mask &= np.isfinite(self._mag_data.value)
        if self._filter_mask is not None and self._filter_mask.size == mask.size:
            mask &= self._filter_mask
        return mask

    def _refresh_canvas_options(self) -> None:
        cmin = cmax = None
        if self.color_scale.currentText() == "Manual":
            cmin = self._optional_float(self.color_min.text())
            cmax = self._optional_float(self.color_max.text())
        elif self.color_scale.currentText() == "Full Range" and self._mag_data is not None:
            finite = self._mag_data.value[np.isfinite(self._mag_data.value)]
            if finite.size:
                cmin = float(np.nanmin(finite)); cmax = float(np.nanmax(finite))
        point_radius = self._float_from_line(self.point_radius, 2.2)
        self.canvas.set_display_options(
            mode=self.preview_mode.currentText(),
            color_min=cmin,
            color_max=cmax,
            opacity=self.opacity.value() / 100.0,
            point_radius=point_radius,
            filter_mask=self._filter_mask,
        )

    def _refresh_draw_only(self) -> None:
        self._refresh_canvas_options()

    def apply_filter(self) -> None:
        if self._mag_data is None:
            return
        mode = self.filter_combo.currentText()
        v = self._mag_data.value
        finite = np.isfinite(v)
        mask = np.ones(v.size, dtype=bool)
        if mode == "None":
            self._filter_mask = None
        elif mode == "Valid Mag":
            mask = finite; self._filter_mask = mask
        elif mode == "Invalid Only":
            mask = ~finite; self._filter_mask = mask
        else:
            valid = v[finite]
            if valid.size:
                lo, hi = np.nanpercentile(valid, [2.0, 98.0])
                if mode == "Inside Robust Range":
                    mask = finite & (v >= lo) & (v <= hi)
                elif mode == "High Only":
                    mask = finite & (v > hi)
                elif mode == "Low Only":
                    mask = finite & (v < lo)
                self._filter_mask = mask
        self.draw()

    def reset_filter(self) -> None:
        self._filter_mask = None
        self.filter_combo.setCurrentText("None")
        self.draw()

    def reset_color(self) -> None:
        self.color_min.clear(); self.color_max.clear(); self.color_scale.setCurrentText("Robust Auto")
        self._refresh_canvas_options()

    # Processing actions
    def process_despike(self) -> None:
        if not self._require_rover(): return
        ch = self._current_channel
        values = self.rover.channels[ch]
        finite = values[np.isfinite(values)]
        if finite.size == 0: return
        med = float(np.nanmedian(finite)); mad = float(np.nanmedian(np.abs(finite - med))) or float(np.nanstd(finite)) or 1.0
        out = values.copy()
        spikes = np.abs(out - med) > 6.0 * mad
        out[spikes] = med
        self.rover.add_derived_channel(DESPIKED_TOTAL_FIELD, out, parent_channel=ch, operation="EnMag despike", overwrite=True)
        self.grid_type.setCurrentText("Despiked"); self._current_channel = DESPIKED_TOTAL_FIELD; self._rebuild_mag_data(); self.draw()

    def process_diurnal(self) -> None:
        if not self._require_rover(): return
        ch = self._current_channel
        values = self.rover.channels[ch]
        if self.base is not None:
            base_ch = self._default_channel(self.base)
            base_values = self.base.channels[base_ch]
            x_src = np.linspace(0, 1, base_values.size)
            correction = np.interp(np.linspace(0, 1, values.size), x_src, np.nan_to_num(base_values - np.nanmedian(base_values)))
            out = values - correction
        else:
            # field-expedient fallback: subtract long-record median drift trend
            idx = np.arange(values.size, dtype=float)
            finite = np.isfinite(values)
            if np.count_nonzero(finite) > 3:
                coeff = np.polyfit(idx[finite], values[finite], 1)
                trend = np.polyval(coeff, idx)
                out = values - (trend - np.nanmedian(trend))
            else:
                out = values.copy()
        self.rover.add_derived_channel(DIURNAL_CORRECTED_FIELD, out, parent_channel=ch, operation="EnMag diurnal correction", overwrite=True)
        self.grid_type.setCurrentText("Diurnal Corrected"); self._current_channel = DIURNAL_CORRECTED_FIELD; self._rebuild_mag_data(); self.draw()

    def process_leveling(self) -> None:
        if not self._require_rover(): return
        ch = self._current_channel
        values = self.rover.channels[ch].copy()
        line = self.rover.line_id.astype(str)
        global_med = np.nanmedian(values)
        out = values.copy()
        for ln in np.unique(line):
            m = line == ln
            if np.any(m):
                out[m] = values[m] - (np.nanmedian(values[m]) - global_med)
        self.rover.add_derived_channel(LEVELED_FIELD, out, parent_channel=ch, operation="EnMag line median levelling", overwrite=True)
        self.grid_type.setCurrentText("Leveled"); self._current_channel = LEVELED_FIELD; self._rebuild_mag_data(); self.draw()

    def process_microlevel(self) -> None:
        if not self._require_rover(): return
        ch = self._current_channel
        values = self.rover.channels[ch].copy()
        out = values.copy()
        line = self.rover.line_id.astype(str)
        for ln in np.unique(line):
            idx = np.flatnonzero(line == ln)
            if idx.size >= 9:
                row = values[idx]
                kernel = max(5, min(51, int(idx.size // 9) * 2 + 1))
                smooth = np.convolve(np.nan_to_num(row, nan=np.nanmedian(row)), np.ones(kernel) / kernel, mode="same")
                corr = np.clip(smooth - np.nanmedian(smooth), -10.0, 10.0)
                out[idx] = row - corr
        self.rover.add_derived_channel(MICROLEVELED_FIELD, out, parent_channel=ch, operation="EnMag gentle microlevel", overwrite=True)
        self.grid_type.setCurrentText("Microleveled"); self._current_channel = MICROLEVELED_FIELD; self._rebuild_mag_data(); self.draw()

    def generate_grid(self) -> None:
        self.draw()

    def run_full_qc(self) -> None:
        if not self._require_rover(): return
        self.process_despike(); self.process_diurnal(); self.process_leveling(); self.process_microlevel()
        self.status.setText("Full magnetic QC chain complete: despike, diurnal, levelling, microlevelling and grid preview")

    def run_raw_qc(self) -> None:
        if not self._require_rover(): return
        self.status.setText(f"Raw QC: {self.rover.record_count:,} samples | channel {self._current_channel} | finite {self._visible_count():,}")
        self.draw()

    def run_processed_qc(self) -> None:
        self.run_full_qc()

    def cancel_qc(self) -> None:
        self.status.setText("No active magnetic background job to cancel.")

    # Ribbon/view compatibility
    def show_map(self) -> None: self.draw()
    def show_profile(self) -> None: self._show_profile_summary()
    def show_native_view(self, mode: str = "2d") -> None: self.draw()
    def show_geospatial_view(self, mode: str = "2d") -> None: self.draw()

    def _show_profile_summary(self) -> None:
        if not self._require_rover(): return
        lines = self.rover.line_id.astype(str)
        values = self.rover.channels[self._current_channel]
        rows = []
        for ln in np.unique(lines):
            m = lines == ln
            finite = values[m][np.isfinite(values[m])]
            if finite.size:
                rows.append(f"Line {ln}: n={finite.size}, min={np.nanmin(finite):.3f}, max={np.nanmax(finite):.3f}, mean={np.nanmean(finite):.3f}")
        QMessageBox.information(self, "Magnetic Profile Summary", "\n".join(rows[:80]) or "No profile values available.")

    # ------------------------------------------------------------------
    # Export and reports
    # ------------------------------------------------------------------
    def export_csv(self) -> None:
        if not self._require_rover(): return
        suggested = self.rover.source_path.with_name(f"{self.rover.source_path.stem}_enmag_export.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Export EnMag magnetic CSV", str(suggested), "CSV (*.csv)")
        if not path: return
        md = self._mag_data
        if md is None: return
        mask = self._mask_for_grid()
        with Path(path).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["x", "y", "magnetic_value", "channel", "line", "station", "source"])
            for i in np.flatnonzero(mask):
                writer.writerow([md.x[i], md.y[i], md.value[i], self._current_channel, md.line[i], md.station[i], md.source[i]])
        self.status.setText(f"Exported magnetic CSV: {path}")

    def generate_report(self, fmt: str = "pdf") -> None:
        if not self._require_rover(): return
        default_ext = "csv" if fmt == "xlsx" else "txt"
        path, _ = QFileDialog.getSaveFileName(self, "Export magnetic QC report", str(self.rover.source_path.with_name(f"{self.rover.source_path.stem}_magnetic_report.{default_ext}")), "Report (*.txt *.csv)")
        if not path: return
        text = self._summary_text([])
        Path(path).write_text(text, encoding="utf-8")
        self.status.setText(f"Report exported: {path}")

    def export_current_image(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export EnMag preview image", "enmag_preview.png", "PNG (*.png);;BMP (*.bmp)")
        if not path: return
        self.canvas.grab().save(path)
        self.status.setText(f"Preview image exported: {path}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _visible_count(self) -> int:
        if self._mag_data is None: return 0
        return int(np.count_nonzero(self._mask_for_grid()))

    def _refresh_controls(self) -> None:
        self.draw_btn.setEnabled(True)
        self.export_btn.setEnabled(True)

    def _require_rover(self) -> bool:
        if self.rover is None:
            QMessageBox.information(self, "Magnetic QC", "Load magnetic data first.")
            return False
        return True

    def _update_summary(self, errors: list[str]) -> None:
        self.summary.setPlainText(self._summary_text(errors))

    def _summary_text(self, errors: list[str]) -> str:
        if self.rover is None:
            return "No magnetic data loaded."
        value = self.rover.channels.get(self._current_channel, next(iter(self.rover.channels.values())))
        finite = value[np.isfinite(value)]
        bounds = self.rover.bounds()
        lines = [
            "EnMag-style magnetic QC summary",
            f"Source: {self.rover.source_path}",
            f"Samples: {self.rover.record_count:,}",
            f"Channels: {', '.join(self.rover.channel_names)}",
            f"Active channel: {self._current_channel}",
            f"Finite values: {finite.size:,}",
        ]
        if finite.size:
            lines.extend([
                f"Min / Max: {np.nanmin(finite):.6g} / {np.nanmax(finite):.6g}",
                f"Mean / Std: {np.nanmean(finite):.6g} / {np.nanstd(finite):.6g}",
            ])
        lines.append(f"Bounds: X {bounds.get('min_x')} – {bounds.get('max_x')} | Y {bounds.get('min_y')} – {bounds.get('max_y')}")
        if self.base is not None:
            lines.append(f"Base: {self.base.source_path.name}")
        if self.boundary is not None:
            lines.append(f"Boundary: {self.boundary}")
        if errors:
            lines.append("\nSkipped files:")
            lines.extend(errors[:12])
        return "\n".join(lines)

    def _set_cursor_text(self, text: str) -> None:
        self.preview_help.setText(text)

    @staticmethod
    def _optional_float(text: str) -> Optional[float]:
        try:
            value = float(str(text).strip())
            return value if np.isfinite(value) else None
        except Exception:
            return None

    def _float_from_line(self, line: QLineEdit, default: float) -> float:
        value = self._optional_float(line.text())
        return default if value is None else value
