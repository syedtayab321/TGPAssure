from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QSignalBlocker, Signal
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath, QPen, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QRadioButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from modules.seismic.segy_reader import SegyReader
from modules.seismic.ui.interactive_trace_zoom import InteractiveTraceZoomCanvas
from modules.seismic.ui.color_palette_dialog import ColorPaletteDialog, COLOR_PALETTES, palette_icon, palette_to_rgb_array
from modules.seismic.segy_viewer.segy_display import (
    DisplayGrid,
    apply_display_gain,
    build_time_grid,
    normalize_for_display,
    trace_rms,
)


class ColorButton(QPushButton):
    """Small reusable colour selector used by the classic SEG-Y controls."""

    color_changed = Signal(QColor)

    def __init__(self, color: QColor | str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(34, 20)
        self.clicked.connect(self._choose)
        self._refresh()

    def color(self) -> QColor:
        return QColor(self._color)

    def set_color(self, color: QColor | str) -> None:
        self._color = QColor(color)
        self._refresh()
        self.color_changed.emit(self.color())

    def _refresh(self) -> None:
        self.setStyleSheet(
            "QPushButton{border:1px solid #777;background:%s;min-width:34px;max-width:34px;min-height:20px;max-height:20px;}"
            "QPushButton:hover{border:1px solid #111;}" % self._color.name()
        )

    def _choose(self) -> None:
        picked = QColorDialog.getColor(self._color, self, "Select SEG-Y display colour")
        if picked.isValid():
            self.set_color(picked)


class ProcessingDialog(QDialog):
    """Compact processing parameter dialog for viewer-only display processing."""

    def __init__(self, parent: "SegyViewerWidget") -> None:
        super().__init__(parent)
        self.viewer = parent
        self.setWindowTitle("SEG-Y Processing Parameters")
        self.setMinimumWidth(310)
        self.setStyleSheet(parent._classic_stylesheet())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        group = QGroupBox("Display Filter")
        grid = QGridLayout(group)
        grid.setContentsMargins(7, 10, 7, 7)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(5)
        self.low_cut = QDoubleSpinBox()
        self.low_cut.setRange(0.0, 1000.0)
        self.low_cut.setDecimals(1)
        self.low_cut.setSuffix(" Hz")
        self.low_cut.setValue(parent.low_cut_hz)
        self.high_cut = QDoubleSpinBox()
        self.high_cut.setRange(0.0, 1000.0)
        self.high_cut.setDecimals(1)
        self.high_cut.setSuffix(" Hz")
        self.high_cut.setValue(parent.high_cut_hz)
        self.agc_window = QDoubleSpinBox()
        self.agc_window.setRange(5.0, 5000.0)
        self.agc_window.setDecimals(0)
        self.agc_window.setSuffix(" ms")
        self.agc_window.setValue(parent.agc_window_ms)
        self.clip = QDoubleSpinBox()
        self.clip.setRange(80.0, 100.0)
        self.clip.setDecimals(1)
        self.clip.setSuffix(" %")
        self.clip.setValue(parent.clip_percent)
        grid.addWidget(QLabel("Low cut"), 0, 0)
        grid.addWidget(self.low_cut, 0, 1)
        grid.addWidget(QLabel("High cut"), 1, 0)
        grid.addWidget(self.high_cut, 1, 1)
        grid.addWidget(QLabel("AGC window"), 2, 0)
        grid.addWidget(self.agc_window, 2, 1)
        grid.addWidget(QLabel("Clip"), 3, 0)
        grid.addWidget(self.clip, 3, 1)
        layout.addWidget(group)

        note = QLabel("These operations are display-only and do not overwrite the SEG-Y file.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#555;background:#F4F4F4;border:1px solid #D4D4D4;padding:4px;")
        layout.addWidget(note)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        apply_btn = QPushButton("Apply")
        close_btn = QPushButton("Close")
        apply_btn.clicked.connect(self._apply)
        close_btn.clicked.connect(self.close)
        buttons.addWidget(apply_btn)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

    def _apply(self) -> None:
        self.viewer.low_cut_hz = float(self.low_cut.value())
        self.viewer.high_cut_hz = float(self.high_cut.value())
        self.viewer.agc_window_ms = float(self.agc_window.value())
        self.viewer.clip_percent = float(self.clip.value())
        self.viewer.render()


class SelectionZoomDialog(QDialog):
    """SEG-Y zoom dialog with a clean central trace view and live side-table values."""

    def __init__(
        self,
        title: str,
        image: QImage,
        details: list[tuple[str, str]],
        trace_rows: Optional[list[tuple[str, str, str, str, str, str, str]]] = None,
        parent: Optional[QWidget] = None,
        trace_data: Optional[np.ndarray] = None,
        trace_start: int = 0,
        sample_start: int = 0,
        sample_interval_ms: float = 1.0,
        trace_statuses: Optional[list[str]] = None,
    ) -> None:
        super().__init__(parent)
        self.open_main_requested = False
        self.setWindowTitle(title)
        self.setMinimumSize(880, 500)
        base_sheet = parent._classic_stylesheet() if hasattr(parent, "_classic_stylesheet") else ""
        self.setStyleSheet(
            base_sheet
            + "QDialog{background:#EEF2F6;}"
              "QLabel{font-size:7.6pt;color:#102033;background:transparent;}"
              "QTableWidget{font-size:7.2pt;background:white;gridline-color:#D9E3EC;alternate-background-color:#F4F9FF;}"
              "QHeaderView::section{background:#DDEEFF;color:#073B63;font-weight:700;padding:3px;border:0;border-right:1px solid #A6BDD5;}"
              "QPushButton{font-size:7.8pt;padding:4px 10px;border:1px solid #7E9AB8;background:#FFFFFF;border-radius:3px;}"
              "QPushButton:hover{background:#E8F3FF;border-color:#2D77B6;}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        header = QLabel("Selected SEG-Y area — smooth trace hover QC")
        header.setStyleSheet("font-weight:900;color:#0B4D82;background:#EEF7FF;border:1px solid #B8D8F0;padding:5px;")
        root.addWidget(header)

        content = QSplitter(Qt.Orientation.Horizontal, self)

        left = QFrame(content)
        left.setStyleSheet("QFrame{background:#F7FBFF;border:1px solid #A9C2DC;}")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(5, 5, 5, 5)
        left_layout.setSpacing(5)
        left_layout.addWidget(self._section_label("Selection"))
        self.selection_table = self._make_key_value_table(details)
        left_layout.addWidget(self.selection_table, 1)

        preview_frame = QFrame(content)
        preview_frame.setStyleSheet("QFrame{background:#FFFFFF;border:1px solid #8EAAC8;}")
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(5, 5, 5, 5)
        self.preview = InteractiveTraceZoomCanvas(self)
        self.preview.set_data(
            trace_data,
            trace_start=trace_start,
            sample_start=sample_start,
            sample_interval_ms=sample_interval_ms,
            trace_statuses=trace_statuses,
            title="SEG-Y selected-area vector trace preview",
        )
        preview_layout.addWidget(self.preview, 1)

        right = QFrame(content)
        right.setStyleSheet("QFrame{background:#F7FBFF;border:1px solid #A9C2DC;}")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(5, 5, 5, 5)
        right_layout.setSpacing(5)
        right_layout.addWidget(self._section_label("Hover sample"))
        self.hover_table = self._make_key_value_table([])
        right_layout.addWidget(self.hover_table, 1)
        self._set_hover_placeholder()

        content.addWidget(left)
        content.addWidget(preview_frame)
        content.addWidget(right)
        content.setSizes([230, 640, 250])
        root.addWidget(content, 1)

        self.preview.cursor_changed.connect(self._update_hover_table)
        self.preview.cursor_cleared.connect(self._set_hover_placeholder)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        open_btn = QPushButton("Open Area in Main View")
        close_btn = QPushButton("Close")
        open_btn.clicked.connect(self._open_main)
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(open_btn)
        buttons.addWidget(close_btn)
        root.addLayout(buttons)

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-weight:900;color:#0B4D82;background:#EAF5FF;border:1px solid #B8D8F0;padding:4px;")
        return label

    def _make_key_value_table(self, rows: list[tuple[str, str]]) -> QTableWidget:
        table = QTableWidget(max(1, len(rows)), 2)
        table.setHorizontalHeaderLabels(["Item", "Value"])
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._fill_key_value_table(table, rows)
        return table

    def _fill_key_value_table(self, table: QTableWidget, rows: list[tuple[str, str]]) -> None:
        table.setRowCount(max(1, len(rows)))
        if not rows:
            table.setItem(0, 0, QTableWidgetItem("Status"))
            table.setItem(0, 1, QTableWidgetItem("Move cursor over traces"))
            return
        for row, (key, value) in enumerate(rows):
            table.setItem(row, 0, QTableWidgetItem(str(key)))
            table.setItem(row, 1, QTableWidgetItem(str(value)))
        table.resizeRowsToContents()

    def _ensure_hover_table_rows(self) -> None:
        fields = ["Status", "Trace", "Sample", "Time", "Amplitude", "Trace Min", "Trace Max", "Trace RMS"]
        self._hover_fields = fields
        with QSignalBlocker(self.hover_table):
            self.hover_table.setRowCount(len(fields))
            for row, key in enumerate(fields):
                key_item = self.hover_table.item(row, 0)
                if key_item is None:
                    key_item = QTableWidgetItem(key)
                    self.hover_table.setItem(row, 0, key_item)
                else:
                    key_item.setText(key)
                value_item = self.hover_table.item(row, 1)
                if value_item is None:
                    value_item = QTableWidgetItem("—")
                    self.hover_table.setItem(row, 1, value_item)
            self.hover_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            self.hover_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

    def _set_hover_placeholder(self) -> None:
        if not hasattr(self, "hover_table"):
            return
        self._hover_signature = None
        self._ensure_hover_table_rows()
        with QSignalBlocker(self.hover_table):
            for row in range(self.hover_table.rowCount()):
                item = self.hover_table.item(row, 1)
                if item is not None:
                    item.setText("—")
                    item.setBackground(QColor(255, 255, 255))
                    item.setForeground(QColor(20, 32, 45))
            item = self.hover_table.item(0, 1)
            if item is not None:
                item.setText("Move cursor over traces")
                item.setBackground(QColor(240, 244, 248))
                item.setForeground(QColor(60, 70, 80))

    def _fmt(self, value: object, decimals: int = 6) -> str:
        try:
            number = float(value)
            if not np.isfinite(number):
                return "—"
            return f"{number:.{decimals}g}"
        except Exception:
            return "—" if value is None else str(value)

    def _update_hover_table(self, info: dict) -> None:
        if not hasattr(self, "hover_table"):
            return
        signature = (
            int(info.get("local_trace", -1)),
            int(info.get("local_sample", -1)),
            str(info.get("status", "Normal")),
        )
        if getattr(self, "_hover_signature", None) == signature:
            return
        self._hover_signature = signature
        self._ensure_hover_table_rows()
        values = {
            "Status": str(info.get("status", "Normal")),
            "Trace": str(int(info.get("trace", 0)) + 1),
            "Sample": str(int(info.get("sample", 0)) + 1),
            "Time": f"{float(info.get('time_ms', 0.0)):.2f} ms",
            "Amplitude": self._fmt(info.get("amplitude"), 7),
            "Trace Min": self._fmt(info.get("min"), 7),
            "Trace Max": self._fmt(info.get("max"), 7),
            "Trace RMS": self._fmt(info.get("rms"), 7),
        }
        rgb = info.get("status_color", (31, 154, 85))
        color = QColor(int(rgb[0]), int(rgb[1]), int(rgb[2])) if isinstance(rgb, tuple) and len(rgb) == 3 else QColor(31, 154, 85)
        with QSignalBlocker(self.hover_table):
            for row, key in enumerate(getattr(self, "_hover_fields", [])):
                item = self.hover_table.item(row, 1)
                if item is None:
                    continue
                item.setText(values.get(key, "—"))
                if key == "Status":
                    item.setBackground(color)
                    item.setForeground(QColor(255, 255, 255))
                else:
                    item.setBackground(QColor(255, 255, 255))
                    item.setForeground(QColor(20, 32, 45))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._center_on_available_screen()

    def _center_on_available_screen(self) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        width = min(max(880, int(available.width() * 0.80)), 1260)
        height = min(max(500, int(available.height() * 0.80)), 860)
        self.resize(width, height)
        frame = self.frameGeometry()
        frame.moveCenter(available.center())
        self.move(frame.topLeft())

    def _open_main(self) -> None:
        self.open_main_requested = True
        self.accept()


class SegyClassicCanvas(QWidget):
    """SEG-Y canvas using classic seismic viewer interaction, but safe Qt rendering."""

    window_changed = Signal(int, int, int, int)
    trace_selected = Signal(int)
    cursor_changed = Signal(int, int, float, float)
    measurement_changed = Signal(str)
    area_selected = Signal(int, int, int, int)
    manual_qc_point_added = Signal(str, int, int, float, float, str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(520, 360)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._image = QImage()
        self._t0 = 0
        self._t1 = 1
        self._s0 = 0
        self._s1 = 1
        self._total_t = 1
        self._total_s = 1
        self._grid_start_ms = 0.0
        self._sample_interval_ms = 1.0
        self._selected_trace = 0
        self._selected_color = QColor(0, 0, 255)
        self._trace_indices: list[int] = [0]
        self._display_data: Optional[np.ndarray] = None
        self._drag_start: Optional[QPointF] = None
        self._rubber_start: Optional[QPointF] = None
        self._rubber_current: Optional[QPointF] = None
        self.interaction_mode = "inspect"  # inspect, zoom, pan, pick, measure
        self.measure_start: Optional[tuple[int, int, float, float]] = None
        self.measure_end: Optional[tuple[int, int, float, float]] = None
        self.pick_points: list[tuple[int, int, float, float]] = []
        self._cursor_point: Optional[QPointF] = None
        self._area_start: Optional[QPointF] = None
        self._area_current: Optional[QPointF] = None

    def set_extent(self, trace_count: int, sample_count: int, sample_interval_ms: float, grid_start_ms: float) -> None:
        self._total_t = max(1, int(trace_count))
        self._total_s = max(1, int(sample_count))
        self._sample_interval_ms = max(1e-9, float(sample_interval_ms))
        self._grid_start_ms = float(grid_start_ms)

    def set_selected_color(self, color: QColor | str) -> None:
        self._selected_color = QColor(color)
        self.update()

    def set_display(
        self,
        image: QImage,
        trace_indices: Sequence[int],
        data: Optional[np.ndarray],
        t0: int,
        t1: int,
        s0: int,
        s1: int,
        selected_trace: int,
    ) -> None:
        self._image = image
        self._trace_indices = [int(v) for v in trace_indices] or [int(t0)]
        self._display_data = data
        self._t0, self._t1, self._s0, self._s1 = int(t0), int(t1), int(s0), int(s1)
        self._selected_trace = int(selected_trace)
        self.update()

    def plot_rect(self) -> QRectF:
        return QRectF(55, 8, max(1, self.width() - 70), max(1, self.height() - 34))

    def _trace_to_x(self, trace_index: int) -> float:
        rect = self.plot_rect()
        span = max(1, self._t1 - self._t0)
        return rect.left() + (float(trace_index) + 0.5 - self._t0) / span * rect.width()

    def _sample_to_y(self, sample_index: int) -> float:
        rect = self.plot_rect()
        span = max(1, self._s1 - self._s0)
        return rect.top() + (float(sample_index) - self._s0) / span * rect.height()

    def _position_to_trace_sample(self, pos: QPointF) -> tuple[int, int, float, float]:
        rect = self.plot_rect()
        fx = (pos.x() - rect.left()) / max(1.0, rect.width())
        fy = (pos.y() - rect.top()) / max(1.0, rect.height())
        trace = int(np.clip(math.floor(self._t0 + fx * max(1, self._t1 - self._t0)), 0, self._total_t - 1))
        sample = int(np.clip(round(self._s0 + fy * max(1, self._s1 - self._s0)), 0, self._total_s - 1))
        time_ms = self._grid_start_ms + sample * self._sample_interval_ms
        amp = float("nan")
        if self._display_data is not None and self._display_data.size and self._trace_indices:
            nearest = int(np.argmin(np.abs(np.asarray(self._trace_indices) - trace)))
            display_sample = int(np.clip(round((sample - self._s0) / max(1, self._s1 - self._s0 - 1) * (self._display_data.shape[1] - 1)), 0, self._display_data.shape[1] - 1))
            try:
                amp = float(self._display_data[nearest, display_sample])
            except Exception:
                amp = float("nan")
        return trace, sample, time_ms, amp

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(232, 232, 232))
        rect = self.plot_rect()
        painter.fillRect(rect, QColor(255, 255, 255))
        if not self._image.isNull():
            painter.drawImage(rect, self._image)

        painter.setPen(QPen(QColor(140, 140, 140), 1))
        painter.drawRect(rect)
        self._draw_axes(painter, rect)
        self._draw_selected_trace(painter)
        self._draw_picks_and_measure(painter)
        self._draw_cursor(painter)
        self._draw_rubber_band(painter)
        self._draw_area_selection(painter)
        painter.end()

    def _draw_axes(self, painter: QPainter, rect: QRectF) -> None:
        painter.setPen(QPen(QColor(25, 25, 25), 1))
        font = painter.font()
        font.setPointSizeF(7.0)
        painter.setFont(font)
        sample_span = max(1, self._s1 - self._s0)
        coarse = 200 if sample_span > 1000 else 100 if sample_span > 300 else 50 if sample_span > 100 else 10
        first_time = self._grid_start_ms + self._s0 * self._sample_interval_ms
        last_time = self._grid_start_ms + (self._s1 - 1) * self._sample_interval_ms
        start_tick = int(math.ceil(first_time / coarse) * coarse)
        tick = start_tick
        while tick <= last_time + 1e-6:
            sample = int(round((tick - self._grid_start_ms) / self._sample_interval_ms))
            y = self._sample_to_y(sample)
            if rect.top() - 1 <= y <= rect.bottom() + 1:
                painter.drawLine(int(rect.left()) - 4, int(y), int(rect.left()), int(y))
                painter.drawText(QRectF(2, y - 7, 48, 14), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(int(round(tick))))
            tick += coarse
        painter.drawText(QRectF(4, rect.top() - 2, 45, 16), Qt.AlignmentFlag.AlignRight, "ms")

        trace_span = max(1, self._t1 - self._t0)
        step = max(1, int(round(trace_span / 8.0)))
        for trace in range(self._t0, self._t1, step):
            x = self._trace_to_x(trace)
            painter.drawLine(int(x), int(rect.bottom()), int(x), int(rect.bottom()) + 4)
            painter.drawText(QRectF(x - 25, rect.bottom() + 5, 50, 14), Qt.AlignmentFlag.AlignCenter, str(trace + 1))

    def _draw_selected_trace(self, painter: QPainter) -> None:
        if not (self._t0 <= self._selected_trace < self._t1):
            return
        rect = self.plot_rect()
        x = self._trace_to_x(self._selected_trace)
        painter.setPen(QPen(self._selected_color, 1))
        painter.drawLine(int(x), int(rect.top()), int(x), int(rect.bottom()))

    def _draw_cursor(self, painter: QPainter) -> None:
        if self._cursor_point is None or not self.plot_rect().contains(self._cursor_point):
            return
        rect = self.plot_rect()
        painter.setPen(QPen(QColor(210, 0, 0), 1, Qt.PenStyle.DotLine))
        painter.drawLine(int(rect.left()), int(self._cursor_point.y()), int(rect.right()), int(self._cursor_point.y()))
        painter.drawLine(int(self._cursor_point.x()), int(rect.top()), int(self._cursor_point.x()), int(rect.bottom()))

    def _draw_picks_and_measure(self, painter: QPainter) -> None:
        rect = self.plot_rect()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(220, 0, 0), 2))
        for trace, sample, _time, _amp in self.pick_points[-50:]:
            if self._t0 <= trace < self._t1 and self._s0 <= sample < self._s1:
                x = self._trace_to_x(trace)
                y = self._sample_to_y(sample)
                painter.drawLine(int(x - 5), int(y), int(x + 5), int(y))
                painter.drawLine(int(x), int(y - 5), int(x), int(y + 5))
        if self.measure_start is not None:
            points = [self.measure_start]
            if self.measure_end is not None:
                points.append(self.measure_end)
            elif self._cursor_point is not None and rect.contains(self._cursor_point):
                points.append(self._position_to_trace_sample(self._cursor_point))
            if len(points) == 2:
                a, b = points
                ax = self._trace_to_x(a[0])
                ay = self._sample_to_y(a[1])
                bx = self._trace_to_x(b[0])
                by = self._sample_to_y(b[1])
                painter.setPen(QPen(QColor(230, 0, 0), 2))
                painter.drawLine(int(ax), int(ay), int(bx), int(by))
                painter.drawEllipse(QPointF(ax, ay), 4, 4)
                painter.drawEllipse(QPointF(bx, by), 4, 4)
                label = f"ΔTrc={b[0] - a[0]}  ΔT={b[2] - a[2]:.1f} ms  ΔSmp={b[1] - a[1]}"
                painter.fillRect(QRectF(min(ax, bx) + 8, min(ay, by) - 18, 210, 16), QColor(255, 255, 220, 230))
                painter.setPen(QPen(QColor(60, 30, 0), 1))
                painter.drawText(QRectF(min(ax, bx) + 10, min(ay, by) - 18, 210, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)

    def _draw_rubber_band(self, painter: QPainter) -> None:
        if self._rubber_start is None or self._rubber_current is None:
            return
        rect = QRectF(self._rubber_start, self._rubber_current).normalized().intersected(self.plot_rect())
        if rect.width() < 2 or rect.height() < 2:
            return
        painter.setPen(QPen(QColor(0, 80, 190), 1, Qt.PenStyle.DashLine))
        painter.fillRect(rect, QColor(70, 120, 220, 35))
        painter.drawRect(rect)

    def _draw_area_selection(self, painter: QPainter) -> None:
        if self._area_start is None or self._area_current is None:
            return
        rect = QRectF(self._area_start, self._area_current).normalized().intersected(self.plot_rect())
        if rect.width() < 2 or rect.height() < 2:
            return
        painter.setPen(QPen(QColor(255, 153, 0), 2, Qt.PenStyle.DashLine))
        painter.fillRect(rect, QColor(255, 204, 64, 45))
        painter.drawRect(rect)
        painter.fillRect(QRectF(rect.left(), max(self.plot_rect().top(), rect.top() - 18), 210, 16), QColor(255, 255, 230, 235))
        painter.setPen(QPen(QColor(90, 55, 0), 1))
        painter.drawText(QRectF(rect.left() + 5, max(self.plot_rect().top(), rect.top() - 18), 205, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "Release right mouse for QC zoom")

    def wheelEvent(self, event: QWheelEvent) -> None:
        rect = self.plot_rect()
        pos = event.position()
        if not rect.contains(pos):
            return
        trace_span = max(1, self._t1 - self._t0)
        sample_span = max(2, self._s1 - self._s0)
        factor = 0.75 if event.angleDelta().y() > 0 else 1 / 0.75
        fx = (pos.x() - rect.left()) / max(1.0, rect.width())
        fy = (pos.y() - rect.top()) / max(1.0, rect.height())
        traces_only = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        time_only = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        new_t = trace_span if time_only else int(np.clip(round(trace_span * factor), 1, self._total_t))
        new_s = sample_span if traces_only else int(np.clip(round(sample_span * factor), 8, self._total_s))
        anchor_t = self._t0 + fx * trace_span
        anchor_s = self._s0 + fy * sample_span
        t0 = int(round(anchor_t - fx * new_t))
        s0 = int(round(anchor_s - fy * new_s))
        t0 = max(0, min(t0, self._total_t - new_t))
        s0 = max(0, min(s0, self._total_s - new_s))
        self.window_changed.emit(t0, t0 + new_t, s0, s0 + new_s)
        event.accept()

    def mousePressEvent(self, event) -> None:
        rect = self.plot_rect()
        pos = event.position()
        if event.button() == Qt.MouseButton.RightButton and rect.contains(pos):
            self.setFocus()
            self._area_start = pos
            self._area_current = pos
            self.update()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and rect.contains(pos):
            self.setFocus()
            if self.interaction_mode == "pan":
                self._drag_start = pos
                return
            if self.interaction_mode == "zoom":
                self._rubber_start = pos
                self._rubber_current = pos
                self.update()
                return
            trace, sample, time_ms, amp = self._position_to_trace_sample(pos)
            self.trace_selected.emit(trace)
            if self.interaction_mode == "pick":
                self.pick_points.append((trace, sample, time_ms, amp))
                self.measurement_changed.emit(f"Pick: Trc={trace + 1} Time={time_ms:.1f} ms Smp={sample + 1} Amp={amp:.6g}")
                self.manual_qc_point_added.emit("Pick", trace, sample, time_ms, amp, "Manual pick from seismic canvas")
            elif self.interaction_mode == "measure":
                if self.measure_start is None or self.measure_end is not None:
                    self.measure_start = (trace, sample, time_ms, amp)
                    self.measure_end = None
                    self.measurement_changed.emit("Measure: click end point")
                else:
                    self.measure_end = (trace, sample, time_ms, amp)
                    start = self.measure_start
                    self.measurement_changed.emit(
                        f"Measure: ΔTrc={trace - start[0]} ΔT={time_ms - start[2]:.2f} ms ΔSmp={sample - start[1]}"
                    )
                    self.manual_qc_point_added.emit("Measure", trace, sample, time_ms, amp, f"Measured from Trc {start[0] + 1}, Smp {start[1] + 1}")
            self.update()
            return
        if event.button() == Qt.MouseButton.MiddleButton:
            self._drag_start = pos
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        rect = self.plot_rect()
        pos = event.position()
        self._cursor_point = pos if rect.contains(pos) else None
        if rect.contains(pos):
            self.cursor_changed.emit(*self._position_to_trace_sample(pos))
        if self._area_start is not None and (event.buttons() & Qt.MouseButton.RightButton):
            self._area_current = pos
            self.update()
            event.accept()
            return
        if self._drag_start is not None and (event.buttons() & Qt.MouseButton.MiddleButton or self.interaction_mode == "pan"):
            delta = pos - self._drag_start
            self._drag_start = pos
            trace_span = self._t1 - self._t0
            sample_span = self._s1 - self._s0
            dt = int(round(-delta.x() / max(1.0, rect.width()) * trace_span))
            ds = int(round(-delta.y() / max(1.0, rect.height()) * sample_span))
            t0 = max(0, min(self._t0 + dt, self._total_t - trace_span))
            s0 = max(0, min(self._s0 + ds, self._total_s - sample_span))
            self.window_changed.emit(t0, t0 + trace_span, s0, s0 + sample_span)
        if self._rubber_start is not None:
            self._rubber_current = pos
            self.update()
        else:
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton and self._area_start is not None and self._area_current is not None:
            selected = QRectF(self._area_start, self._area_current).normalized().intersected(self.plot_rect())
            plot = self.plot_rect()
            self._area_start = None
            self._area_current = None
            if selected.width() > 12 and selected.height() > 12:
                fx0 = (selected.left() - plot.left()) / max(1.0, plot.width())
                fx1 = (selected.right() - plot.left()) / max(1.0, plot.width())
                fy0 = (selected.top() - plot.top()) / max(1.0, plot.height())
                fy1 = (selected.bottom() - plot.top()) / max(1.0, plot.height())
                t_span = max(1, self._t1 - self._t0)
                s_span = max(1, self._s1 - self._s0)
                t0 = int(np.clip(math.floor(self._t0 + fx0 * t_span), 0, self._total_t - 1))
                t1 = int(np.clip(math.ceil(self._t0 + fx1 * t_span), t0 + 1, self._total_t))
                s0 = int(np.clip(math.floor(self._s0 + fy0 * s_span), 0, self._total_s - 1))
                s1 = int(np.clip(math.ceil(self._s0 + fy1 * s_span), s0 + 1, self._total_s))
                self.area_selected.emit(t0, t1, s0, s1)
            self.update()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._rubber_start is not None and self._rubber_current is not None:
            rect = QRectF(self._rubber_start, self._rubber_current).normalized().intersected(self.plot_rect())
            plot = self.plot_rect()
            self._rubber_start = None
            self._rubber_current = None
            self._area_start = None
            self._area_current = None
            if rect.width() > 12 and rect.height() > 12:
                fx0 = (rect.left() - plot.left()) / max(1.0, plot.width())
                fx1 = (rect.right() - plot.left()) / max(1.0, plot.width())
                fy0 = (rect.top() - plot.top()) / max(1.0, plot.height())
                fy1 = (rect.bottom() - plot.top()) / max(1.0, plot.height())
                t_span = max(1, self._t1 - self._t0)
                s_span = max(1, self._s1 - self._s0)
                t0 = int(np.clip(math.floor(self._t0 + fx0 * t_span), 0, self._total_t - 1))
                t1 = int(np.clip(math.ceil(self._t0 + fx1 * t_span), t0 + 1, self._total_t))
                s0 = int(np.clip(math.floor(self._s0 + fy0 * s_span), 0, self._total_s - 1))
                s1 = int(np.clip(math.ceil(self._s0 + fy1 * s_span), s0 + 1, self._total_s))
                self.window_changed.emit(t0, t1, s0, s1)
            self.update()
            return
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._drag_start = None
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.measure_start = None
            self.measure_end = None
            self._rubber_start = None
            self._rubber_current = None
            self.update()
            self.measurement_changed.emit("Measurement cleared")
            return
        super().keyPressEvent(event)

    def clear_marks(self) -> None:
        self.pick_points.clear()
        self.measure_start = None
        self.measure_end = None
        self.update()


class SegyBusyOverlay(QFrame):
    """Full-widget busy overlay shown while SEG-Y display operations are applied."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("segyBusyOverlay")
        self.setStyleSheet(
            "QFrame#segyBusyOverlay{background:rgba(12,25,38,185);border:0;}"
            "QLabel{color:white;background:transparent;font-size:9pt;font-weight:700;}"
            "QProgressBar{background:#25384A;border:1px solid #57748B;border-radius:5px;color:white;text-align:center;min-height:14px;}"
            "QProgressBar::chunk{background:#1EA7D8;border-radius:4px;}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch(1)
        card = QFrame(self)
        card.setStyleSheet("QFrame{background:rgba(16,45,66,235);border:1px solid #5A7E98;border-radius:8px;}")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(26, 18, 26, 18)
        card_layout.setSpacing(8)
        self.title = QLabel("Applying SEG-Y display")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message = QLabel("Please wait while traces are rendered")
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedWidth(320)
        card_layout.addWidget(self.title)
        card_layout.addWidget(self.message)
        card_layout.addWidget(self.progress)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(card)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)
        self.hide()

    def show_busy(self, title: str = "Applying SEG-Y display", message: str = "Rendering traces and processing display options") -> None:
        self.title.setText(title)
        self.message.setText(message)
        self.setGeometry(self.parentWidget().rect() if self.parentWidget() is not None else self.geometry())
        self.raise_()
        self.show()
        QApplication.processEvents()

    def hide_busy(self) -> None:
        self.hide()
        QApplication.processEvents()


class SegyViewerWidget(QWidget):
    color_density_changed = Signal(bool)

    """Classic compact SEG-Y viewer for manual QC and display-only processing.

    This replaces the old SEG-Y dashboard with a small-font seismic viewer layout:
    file browser, compact control panel, Seismic / Trace Headers / Hardcopy tabs,
    display processing toggles, pick/measure tools, zoom/pan and export tools.
    """

    MAX_RENDER_TRACES = 1400
    MAX_RENDER_SAMPLES = 5200

    def __init__(self, file_path: str | Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setProperty("module_id", "segy_viewer")
        self.file_path = Path(file_path)
        self.reader: Optional[SegyReader] = None
        self.index = None
        self.time_grid: Optional[DisplayGrid] = None
        self._t0 = self._s0 = 0
        self._t1 = self._s1 = 1
        self._selected_trace = 0
        self._effective_intervals_us = np.array([1000.0], dtype=np.float64)
        self._last_trace_indices: list[int] = []
        self._last_raw_window: Optional[np.ndarray] = None
        self.low_cut_hz = 0.0
        self.high_cut_hz = 0.0
        self.agc_window_ms = 100.0
        self.clip_percent = 99.0
        self.color_palette_name = "Seismic"
        self._building_ui = True
        self._rendering_busy = False
        self._build_ui()
        self._building_ui = False
        self.open_file(self.file_path)

    def resizeEvent(self, event) -> None:
        if hasattr(self, "busy_overlay"):
            self.busy_overlay.setGeometry(self.rect())
        super().resizeEvent(event)

    @staticmethod
    def _classic_stylesheet() -> str:
        return (
            "QWidget{font-size:7.8pt;color:#102033;background:#EEF2F6;}"
            "QFrame#topMenu{background:#F8FBFF;border-bottom:1px solid #8AB5E3;}"
            "QFrame#topPanel{background:#EAF4FF;border-top:1px solid #FFFFFF;border-bottom:1px solid #7CAAD8;}"
            "QFrame#fileBrowser{background:#F3F7FB;border-right:1px solid #8FB6DA;}"
            "QFrame#toolStrip{background:#DCEEFF;border-right:1px solid #7CAAD8;}"
            "QFrame#classicStatus{background:#F7FBFF;border-top:1px solid #7CAAD8;}"
            "QGroupBox{font-size:7.4pt;font-weight:700;border:1px solid #93B7D9;margin-top:5px;padding-top:7px;background:#F4F9FF;border-radius:2px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:5px;padding:0 3px;background:#F4F9FF;color:#0B4D82;}"
            "QGroupBox#displayGroup{border-color:#5AA3D6;background:#F3FAFF;}"
            "QGroupBox#fillGroup{border-color:#6DBF7C;background:#F5FFF7;}"
            "QGroupBox#colorsGroup{border-color:#876BD8;background:#F8F5FF;}"
            "QGroupBox#scaleGroup{border-color:#D59A25;background:#FFF9EE;}"
            "QGroupBox#directionGroup{border-color:#4F9CA8;background:#F2FDFF;}"
            "QGroupBox#processingGroup{border-color:#D77A61;background:#FFF5F2;}"
            "QLabel{font-size:7.6pt;background:transparent;color:#102033;}"
            "QPushButton{font-size:7.4pt;min-height:18px;padding:1px 5px;border:1px solid #7E9AB8;background:#FFFFFF;color:#102033;border-radius:2px;}"
            "QPushButton:hover{background:#E8F3FF;border-color:#2D77B6;}"
            "QPushButton:pressed{background:#D4E8FF;}"
            "QPushButton:checked{background:#1F79BD;border:1px solid #0B4D82;color:#FFFFFF;font-weight:700;}"
            "QPushButton#menuButton{border:0;background:transparent;color:#0B4D82;font-size:7.8pt;font-weight:700;padding:1px 4px;}"
            "QPushButton#menuButton:hover{background:#DCEEFF;border:1px solid #8AB5E3;}"
            "QPushButton#processingParamButton{background:#FFF2D6;border:1px solid #C88919;color:#7A4B00;font-weight:700;}"
            "QCheckBox,QRadioButton{font-size:7.4pt;background:transparent;color:#102033;}"
            "QCheckBox::indicator,QRadioButton::indicator{width:11px;height:11px;border:1px solid #6C8AA8;background:#FFFFFF;}"
            "QCheckBox::indicator:checked{background:#1F79BD;border:1px solid #0B4D82;}"
            "QRadioButton::indicator{border-radius:6px;}"
            "QRadioButton::indicator:checked{background:#1F79BD;border:2px solid #FFFFFF;outline:1px solid #0B4D82;}"
            "QComboBox,QSpinBox,QDoubleSpinBox,QLineEdit{font-size:7.4pt;min-height:18px;border:1px solid #8EAAC8;background:#FFFFFF;padding:1px 2px;color:#102033;}"
            "QSlider{min-height:16px;max-height:16px;}"
            "QSlider::groove:horizontal{height:4px;background:#B9C8D8;border:1px solid #99AFC4;}"
            "QSlider::handle:horizontal{width:12px;margin:-5px 0;background:#1F79BD;border:1px solid #0B4D82;border-radius:6px;}"
            "QTabWidget::pane{border:1px solid #8EAAC8;background:#FFFFFF;top:-1px;}"
            "QTabBar::tab{font-size:7.8pt;background:#EAF2FB;border:1px solid #8EAAC8;border-bottom:0;padding:3px 9px;margin-right:1px;color:#24445F;}"
            "QTabBar::tab:selected{background:#FFFFFF;color:#0B4D82;font-weight:700;}"
            "QTableWidget{font-size:7.2pt;background:#FFFFFF;gridline-color:#DADADA;alternate-background-color:#F1F7FD;color:#102033;}"
            "QHeaderView::section{font-size:7.2pt;background:#DDEFFF;color:#0B4D82;border:0;border-right:1px solid #9FBBD7;border-bottom:1px solid #9FBBD7;padding:2px 3px;font-weight:700;}"
            "QListWidget{font-size:7.6pt;background:#FFFFFF;border:1px solid #8EAAC8;color:#102033;}"
            "QListWidget::item:selected{background:#1F79BD;color:#FFFFFF;}"
            "QTextEdit{font-size:7.4pt;background:#FFFFFF;font-family:Consolas, Courier New, monospace;border:1px solid #8EAAC8;color:#102033;}"
        )

    def _build_ui(self) -> None:
        self.setStyleSheet(self._classic_stylesheet())
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # The SEG-Y display controls now live in the main TGPAssure ribbon.
        # Hidden control objects are still used internally so the rendering and
        # compatibility API remain stable for existing viewer code.
        self._create_ribbon_backed_state_controls()
        self._build_body(root)
        self._build_status_bar(root)
        self.busy_overlay = SegyBusyOverlay(self)
        self.busy_overlay.setGeometry(self.rect())

    def _create_ribbon_backed_state_controls(self) -> None:
        """Create non-visible controls used as the viewer state model.

        The main ribbon drives these controls through public methods below.
        Keeping them as Qt widgets avoids a risky renderer rewrite because the
        existing rendering code already reads checkbox/radio/slider state.
        """
        self.wiggle_cb = QCheckBox("Wiggle", self)
        self.gray_cb = QCheckBox("Gray", self)
        self.color_cb = QCheckBox("Color", self)
        self.timelines_cb = QCheckBox("Timelines", self)
        self.wiggle_cb.setChecked(True)
        self.gray_cb.setChecked(True)
        self.timelines_cb.setChecked(True)
        for cb in (self.wiggle_cb, self.gray_cb, self.color_cb, self.timelines_cb):
            cb.hide()
            cb.toggled.connect(self._display_mode_from_checks)

        self.fill_group = QButtonGroup(self)
        self.fill_none = QRadioButton("None", self)
        self.fill_pos = QRadioButton("Positive (+)", self)
        self.fill_neg = QRadioButton("Negative(-)", self)
        self.fill_none.setChecked(True)
        for index, rb in enumerate((self.fill_none, self.fill_pos, self.fill_neg)):
            rb.hide()
            self.fill_group.addButton(rb, index)
        self.fill_group.buttonClicked.connect(lambda *_args: self.render())

        self.use_delay_cb = QCheckBox("Use Delay Header", self)
        self.use_delay_cb.hide()
        self.use_delay_cb.toggled.connect(self.render)

        self.wiggle_color = ColorButton("#000000", self)
        self.fill_color = ColorButton("#000000", self)
        self.selected_color = ColorButton("#0000ff", self)
        for button in (self.wiggle_color, self.fill_color, self.selected_color):
            button.hide()
            button.color_changed.connect(self.render)

        self.trace_scale = self._hidden_scale_control(10, 500, 155)
        self.time_scale = self._hidden_scale_control(10, 600, 307)
        self.gain_w = self._hidden_scale_control(5, 500, 22)
        self.gain_c = self._hidden_scale_control(5, 500, 22)

        self.direction_group = QButtonGroup(self)
        self.normal_rb = QRadioButton("Normal", self)
        self.reversed_rb = QRadioButton("Reversed", self)
        self.normal_rb.setChecked(True)
        for index, rb in enumerate((self.normal_rb, self.reversed_rb)):
            rb.hide()
            self.direction_group.addButton(rb, index)
        self.direction_group.buttonClicked.connect(lambda *_args: self.render())

        self.inversion_cb = QCheckBox("Inversion", self)
        self.filter_cb = QCheckBox("Filter", self)
        self.agc_cb = QCheckBox("Agc", self)
        self.norm_cb = QCheckBox("Norm", self)
        self.weight_cb = QCheckBox("Weight", self)
        for cb in (self.inversion_cb, self.filter_cb, self.agc_cb, self.norm_cb, self.weight_cb):
            cb.hide()
            cb.toggled.connect(self.render)

        # Compatibility combo used by the main TGPAssure ribbon actions.
        self.mode = QComboBox(self)
        for name, value in (("Wiggle", "wiggle"), ("Variable Area", "va"), ("Variable Density", "vd"), ("Color Density", "color")):
            self.mode.addItem(name, value)
        self.mode.currentIndexChanged.connect(self._apply_compat_mode)
        self.mode.hide()

    def _hidden_scale_control(self, minimum: int, maximum: int, value: int) -> QSlider:
        slider = QSlider(Qt.Orientation.Horizontal, self)
        slider.setRange(minimum, maximum)
        slider.setValue(value)
        slider.hide()
        edit = QLineEdit(f"{value / 10.0:g}", self)
        edit.hide()
        slider.value_edit = edit  # type: ignore[attr-defined]

        def update_from_slider(v: int) -> None:
            edit.setText(f"{v / 10.0:g}")
            self.render()

        slider.valueChanged.connect(update_from_slider)
        return slider

    def _build_menu_bar(self, root: QVBoxLayout) -> None:
        menu = QFrame()
        menu.setObjectName("topMenu")
        row = QHBoxLayout(menu)
        row.setContentsMargins(5, 2, 5, 2)
        row.setSpacing(12)
        for title, callback in (
            ("File", self._choose_file),
            ("View", self.show_display_page),
            ("Processing", self.show_processing_dialog),
            ("Help", self._show_short_help),
        ):
            btn = QPushButton(title)
            btn.setObjectName("menuButton")
            btn.setFlat(True)
            btn.clicked.connect(callback)
            row.addWidget(btn)
        row.addStretch(1)
        root.addWidget(menu)

    def _build_top_panel(self, root: QVBoxLayout) -> None:
        panel = QFrame()
        panel.setObjectName("topPanel")
        row = QHBoxLayout(panel)
        row.setContentsMargins(4, 3, 4, 3)
        row.setSpacing(4)

        display = QGroupBox("Display Mode")
        display.setObjectName("displayGroup")
        grid = QGridLayout(display)
        grid.setContentsMargins(6, 8, 6, 4)
        grid.setHorizontalSpacing(5)
        grid.setVerticalSpacing(1)
        self.wiggle_cb = QCheckBox("Wiggle")
        self.gray_cb = QCheckBox("Gray")
        self.color_cb = QCheckBox("Color")
        self.timelines_cb = QCheckBox("Timelines")
        self.wiggle_cb.setChecked(True)
        self.gray_cb.setChecked(True)
        self.timelines_cb.setChecked(True)
        for i, cb in enumerate((self.wiggle_cb, self.gray_cb, self.color_cb, self.timelines_cb)):
            cb.toggled.connect(self._display_mode_from_checks)
            grid.addWidget(cb, i, 0)
        row.addWidget(display)

        fill = QGroupBox("Wiggle Fill")
        fill.setObjectName("fillGroup")
        fill_grid = QGridLayout(fill)
        fill_grid.setContentsMargins(6, 8, 6, 4)
        fill_grid.setHorizontalSpacing(4)
        fill_grid.setVerticalSpacing(1)
        self.fill_group = QButtonGroup(self)
        self.fill_none = QRadioButton("None")
        self.fill_pos = QRadioButton("Positive (+)")
        self.fill_neg = QRadioButton("Negative(-)")
        self.fill_none.setChecked(True)
        for index, rb in enumerate((self.fill_none, self.fill_pos, self.fill_neg)):
            self.fill_group.addButton(rb, index)
            fill_grid.addWidget(rb, index, 0)
        self.use_delay_cb = QCheckBox("Use Delay Header")
        fill_grid.addWidget(self.use_delay_cb, 3, 0)
        self.fill_group.buttonClicked.connect(self.render)
        self.use_delay_cb.toggled.connect(self.render)
        row.addWidget(fill)

        colors = QGroupBox("Colors")
        colors.setObjectName("colorsGroup")
        color_grid = QGridLayout(colors)
        color_grid.setContentsMargins(6, 8, 6, 4)
        color_grid.setHorizontalSpacing(5)
        color_grid.setVerticalSpacing(2)
        self.wiggle_color = ColorButton("#000000")
        self.fill_color = ColorButton("#000000")
        self.selected_color = ColorButton("#0000ff")
        for button in (self.wiggle_color, self.fill_color, self.selected_color):
            button.color_changed.connect(self.render)
        color_grid.addWidget(QLabel("Wiggle"), 0, 0)
        color_grid.addWidget(self.wiggle_color, 0, 1)
        color_grid.addWidget(QLabel("Fill"), 1, 0)
        color_grid.addWidget(self.fill_color, 1, 1)
        color_grid.addWidget(QLabel("Selected"), 2, 0)
        color_grid.addWidget(self.selected_color, 2, 1)
        row.addWidget(colors)

        scales = QGroupBox("Scale")
        scales.setObjectName("scaleGroup")
        scale_grid = QGridLayout(scales)
        scale_grid.setContentsMargins(6, 8, 6, 4)
        scale_grid.setHorizontalSpacing(4)
        scale_grid.setVerticalSpacing(2)
        self.trace_scale = self._scale_row(scale_grid, 0, "Traces", 10, 500, 155, "trc/cm")
        self.time_scale = self._scale_row(scale_grid, 1, "Time", 10, 600, 307, "cm/sec")
        self.gain_w = self._scale_row(scale_grid, 2, "Gain-w", 5, 500, 22, "=")
        self.gain_c = self._scale_row(scale_grid, 3, "Gain-c", 5, 500, 22, "")
        row.addWidget(scales)

        direction = QGroupBox("Direction")
        direction.setObjectName("directionGroup")
        dir_layout = QVBoxLayout(direction)
        dir_layout.setContentsMargins(6, 8, 6, 4)
        dir_layout.setSpacing(1)
        self.normal_rb = QRadioButton("Normal")
        self.reversed_rb = QRadioButton("Reversed")
        self.normal_rb.setChecked(True)
        self.direction_group = QButtonGroup(self)
        self.direction_group.addButton(self.normal_rb, 0)
        self.direction_group.addButton(self.reversed_rb, 1)
        self.direction_group.buttonClicked.connect(self.render)
        dir_layout.addWidget(self.normal_rb)
        dir_layout.addWidget(self.reversed_rb)
        row.addWidget(direction)

        processing = QGroupBox("Processing")
        processing.setObjectName("processingGroup")
        process_grid = QGridLayout(processing)
        process_grid.setContentsMargins(6, 8, 6, 4)
        process_grid.setHorizontalSpacing(4)
        process_grid.setVerticalSpacing(1)
        self.inversion_cb = QCheckBox("Inversion")
        self.filter_cb = QCheckBox("Filter")
        self.agc_cb = QCheckBox("Agc")
        self.norm_cb = QCheckBox("Norm")
        self.weight_cb = QCheckBox("Weight")
        p_button = QPushButton("P")
        p_button.setObjectName("processingParamButton")
        p_button.setFixedSize(22, 20)
        p_button.clicked.connect(self.show_processing_dialog)
        for cb in (self.inversion_cb, self.filter_cb, self.agc_cb, self.norm_cb, self.weight_cb):
            cb.toggled.connect(self.render)
        process_grid.addWidget(self.inversion_cb, 0, 0, 1, 2)
        process_grid.addWidget(self.filter_cb, 1, 0)
        process_grid.addWidget(p_button, 1, 1)
        process_grid.addWidget(self.agc_cb, 2, 0)
        process_grid.addWidget(self.norm_cb, 2, 1)
        process_grid.addWidget(self.weight_cb, 3, 0)
        row.addWidget(processing)

        row.addStretch(1)
        root.addWidget(panel)

        # Compatibility combo used by the main TGPAssure ribbon actions.
        self.mode = QComboBox()
        for name, value in (("Wiggle", "wiggle"), ("Variable Area", "va"), ("Variable Density", "vd"), ("Color Density", "color")):
            self.mode.addItem(name, value)
        self.mode.currentIndexChanged.connect(self._apply_compat_mode)
        self.mode.hide()

    def _scale_row(self, layout: QGridLayout, row: int, label: str, minimum: int, maximum: int, value: int, suffix: str) -> QSlider:
        layout.addWidget(QLabel(label), row, 0)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setValue(value)
        slider.setFixedWidth(80)
        edit = QLineEdit(f"{value / 10.0:g}" if label != "Traces" else f"{value / 10.0:g}")
        edit.setFixedWidth(48)
        edit.setAlignment(Qt.AlignmentFlag.AlignRight)
        unit = QLabel(suffix)
        layout.addWidget(slider, row, 1)
        layout.addWidget(edit, row, 2)
        layout.addWidget(unit, row, 3)

        def update_from_slider(v: int) -> None:
            edit.setText(f"{v / 10.0:g}")
            self.render()

        def update_from_text() -> None:
            try:
                slider.setValue(int(float(edit.text()) * 10.0))
            except Exception:
                edit.setText(f"{slider.value() / 10.0:g}")

        slider.valueChanged.connect(update_from_slider)
        edit.editingFinished.connect(update_from_text)
        slider.value_edit = edit  # type: ignore[attr-defined]
        return slider

    def _build_body(self, root: QVBoxLayout) -> None:
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        root.addLayout(body, 1)

        tools = QFrame()
        tools.setObjectName("toolStrip")
        tools.setFixedWidth(34)
        tools.setStyleSheet("QFrame#toolStrip{background:#DCEEFF;border-right:1px solid #7CAAD8;}QPushButton{font-size:8pt;min-height:24px;max-height:24px;min-width:24px;max-width:24px;padding:0;background:#FFFFFF;border:1px solid #7E9AB8;color:#0B4D82;border-radius:2px;}QPushButton:hover{background:#E8F3FF;border-color:#2D77B6;}QPushButton:checked{background:#1F79BD;color:#FFFFFF;border-color:#0B4D82;} ")
        tools_layout = QVBoxLayout(tools)
        tools_layout.setContentsMargins(4, 4, 4, 4)
        tools_layout.setSpacing(4)
        for text, tooltip, mode, callback in (
            ("↙", "Fit full seismic", "inspect", self.fit),
            ("🔍", "Zoom box", "zoom", None),
            ("↔", "Pan", "pan", None),
            ("✚", "Pick point", "pick", None),
            ("━", "Measure", "measure", None),
            ("☰", "Trace headers", "inspect", self.show_headers_page),
            ("▥", "Hardcopy/export", "inspect", self.show_hardcopy_page),
            ("⌫", "Clear picks/measure", "inspect", self._clear_marks),
        ):
            btn = QPushButton(text)
            btn.setToolTip(tooltip)
            btn.setCheckable(callback is None)
            if callback is None:
                btn.clicked.connect(lambda _checked=False, m=mode: self._set_tool_mode(m))
            else:
                btn.clicked.connect(callback)
            tools_layout.addWidget(btn)
            if callback is None:
                if not hasattr(self, "tool_buttons"):
                    self.tool_buttons = []
                self.tool_buttons.append(btn)
        tools_layout.addStretch(1)
        body.addWidget(tools)

        browser = QFrame()
        browser.setObjectName("fileBrowser")
        browser.setFixedWidth(240)
        bl = QVBoxLayout(browser)
        bl.setContentsMargins(4, 4, 4, 4)
        bl.setSpacing(3)
        brow = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setMinimumHeight(20)
        up_btn = QPushButton("↩")
        up_btn.setFixedWidth(25)
        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedWidth(25)
        open_btn = QPushButton("📁")
        open_btn.setFixedWidth(25)
        up_btn.clicked.connect(self._go_parent_dir)
        refresh_btn.clicked.connect(self._refresh_file_list)
        open_btn.clicked.connect(self._choose_file)
        self.path_edit.returnPressed.connect(lambda: self._load_directory(Path(self.path_edit.text())))
        brow.addWidget(up_btn)
        brow.addWidget(refresh_btn)
        brow.addWidget(open_btn)
        bl.addLayout(brow)
        bl.addWidget(self.path_edit)
        self.file_list = QListWidget()
        self.file_list.itemDoubleClicked.connect(self._open_list_item)
        bl.addWidget(self.file_list, 1)
        body.addWidget(browser)

        self.tabs = QTabWidget()
        self.canvas = SegyClassicCanvas()
        self.canvas.window_changed.connect(self.set_window)
        self.canvas.trace_selected.connect(self.select_trace)
        self.canvas.cursor_changed.connect(self._update_cursor)
        self.canvas.measurement_changed.connect(self._set_measure_status)
        self.canvas.area_selected.connect(self._show_area_zoom_dialog)
        self.canvas.manual_qc_point_added.connect(self._append_manual_qc_from_canvas)
        self.tabs.addTab(self.canvas, "Seismic")
        self.tabs.addTab(self._manual_qc_page(), "Manual QC")
        self.tabs.addTab(self._trace_headers_page(), "Trace Headers")
        self.tabs.addTab(self._hardcopy_page(), "Hardcopy")
        body.addWidget(self.tabs, 1)

    def _manual_qc_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)
        top = QHBoxLayout()
        self.manual_status_combo = QComboBox()
        self.manual_status_combo.addItems(["Review", "Pass", "Suspect", "Reject", "Noise", "Dead trace", "Timing", "Amplitude"])
        self.manual_comment = QLineEdit()
        self.manual_comment.setPlaceholderText("Manual QC comment / reason")
        add_btn = QPushButton("Add Selected Trace")
        export_btn = QPushButton("Export Manual QC CSV")
        clear_btn = QPushButton("Clear Table")
        add_btn.clicked.connect(self._add_selected_manual_mark)
        export_btn.clicked.connect(self._export_manual_qc_csv)
        clear_btn.clicked.connect(self._clear_manual_qc)
        top.addWidget(QLabel("Status"))
        top.addWidget(self.manual_status_combo)
        top.addWidget(self.manual_comment, 1)
        top.addWidget(add_btn)
        top.addWidget(export_btn)
        top.addWidget(clear_btn)
        layout.addLayout(top)
        self.manual_qc_table = QTableWidget(0, 7)
        self.manual_qc_table.setHorizontalHeaderLabels(["Type", "Trace", "Sample", "Time ms", "Amplitude", "Status", "Comment"])
        self.manual_qc_table.setAlternatingRowColors(True)
        self.manual_qc_table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.SelectedClicked)
        self.manual_qc_table.verticalHeader().setVisible(False)
        self.manual_qc_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.manual_qc_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.manual_qc_table, 1)
        note = QLabel("Manual QC workflow: use Pick/Measure on the seismic canvas or right-drag a QC zoom box. Picks are stored here and can be exported for audit.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#35566E;background:#F2F8FD;border:1px solid #C5DBED;padding:4px;")
        layout.addWidget(note)
        return page

    def _append_manual_qc_from_canvas(self, mark_type: str, trace: int, sample: int, time_ms: float, amplitude: float, note: str) -> None:
        status = self.manual_status_combo.currentText() if hasattr(self, "manual_status_combo") else "Review"
        comment = self.manual_comment.text().strip() if hasattr(self, "manual_comment") and self.manual_comment.text().strip() else note
        self._append_manual_qc(mark_type, trace, sample, time_ms, amplitude, status, comment)

    def _append_manual_qc(self, mark_type: str, trace: int, sample: int, time_ms: float, amplitude: float, status: str, comment: str) -> None:
        if not hasattr(self, "manual_qc_table"):
            return
        row = self.manual_qc_table.rowCount()
        self.manual_qc_table.insertRow(row)
        values = [mark_type, str(trace + 1), str(sample + 1), f"{time_ms:.2f}", f"{amplitude:.6g}", status, comment]
        for col, value in enumerate(values):
            self.manual_qc_table.setItem(row, col, QTableWidgetItem(value))
        self.measure_status.setText(f"Manual QC mark added: {mark_type} Trc={trace + 1}")

    def _add_selected_manual_mark(self) -> None:
        if self.time_grid is None:
            return
        sample = int(np.clip((self._s0 + self._s1) // 2, 0, self.time_grid.sample_count - 1))
        time_ms = self.time_grid.start_ms + sample * self.time_grid.interval_ms
        amp = float("nan")
        if self._last_raw_window is not None and self._last_raw_window.size and self._last_trace_indices:
            try:
                nearest = int(np.argmin(np.abs(np.asarray(self._last_trace_indices) - self._selected_trace)))
                local_sample = int(np.clip(round((sample - self._s0) / max(1, self._s1 - self._s0 - 1) * (self._last_raw_window.shape[1] - 1)), 0, self._last_raw_window.shape[1] - 1))
                amp = float(self._last_raw_window[nearest, local_sample])
            except Exception:
                amp = float("nan")
        status = self.manual_status_combo.currentText()
        comment = self.manual_comment.text().strip() or "Manual selected-trace observation"
        self._append_manual_qc("Selected Trace", self._selected_trace, sample, time_ms, amp, status, comment)

    def _clear_manual_qc(self) -> None:
        if hasattr(self, "manual_qc_table"):
            self.manual_qc_table.setRowCount(0)
            self.measure_status.setText("Manual QC table cleared")

    def _export_manual_qc_csv(self) -> None:
        if not hasattr(self, "manual_qc_table") or self.manual_qc_table.rowCount() == 0:
            QMessageBox.information(self, "Manual QC", "There are no manual QC rows to export.")
            return
        path, _selected = QFileDialog.getSaveFileName(self, "Export Manual SEG-Y QC", str(self.file_path.with_name(self.file_path.stem + "_manual_qc.csv")), "CSV (*.csv)")
        if not path:
            return
        try:
            headers = [self.manual_qc_table.horizontalHeaderItem(c).text() for c in range(self.manual_qc_table.columnCount())]
            with Path(path).open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(headers)
                for row in range(self.manual_qc_table.rowCount()):
                    writer.writerow([(self.manual_qc_table.item(row, col).text() if self.manual_qc_table.item(row, col) else "") for col in range(self.manual_qc_table.columnCount())])
            self.measure_status.setText(f"Manual QC exported: {path}")
        except Exception as exc:
            QMessageBox.warning(self, "Manual QC Export", str(exc))

    def _trace_headers_page(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        self.trace_header = QTableWidget(0, 2)
        self.trace_header.setHorizontalHeaderLabels(["Trace Header", "Value"])
        self.binary = QTableWidget(0, 2)
        self.binary.setHorizontalHeaderLabels(["Binary Header", "Value"])
        for table in (self.trace_header, self.binary):
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setAlternatingRowColors(True)
            table.verticalHeader().setVisible(False)
        layout.addWidget(self.trace_header, 1)
        layout.addWidget(self.binary, 1)
        return page

    def _hardcopy_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        title = QLabel("Hardcopy / Export")
        title.setStyleSheet("font-weight:700;font-size:9pt;background:transparent;")
        layout.addWidget(title)
        row = QHBoxLayout()
        for text, callback in (
            ("Export PNG", self.export_image),
            ("Export BMP", self.export_bmp),
            ("Copy View", self.copy_view_to_clipboard),
            ("Export Trace Headers CSV", self.export_trace_headers_csv),
        ):
            btn = QPushButton(text)
            btn.clicked.connect(callback)
            row.addWidget(btn)
        row.addStretch(1)
        layout.addLayout(row)
        self.text_header = QTextEdit()
        self.text_header.setReadOnly(True)
        layout.addWidget(QLabel("Textual Header"))
        layout.addWidget(self.text_header, 1)
        return page

    def _build_status_bar(self, root: QVBoxLayout) -> None:
        status = QFrame()
        status.setObjectName("classicStatus")
        status.setStyleSheet("QFrame#classicStatus{background:#F7FBFF;border-top:1px solid #7CAAD8;} QLabel{font-size:7.6pt;background:transparent;color:#0B4D82;font-weight:600;}")
        row = QHBoxLayout(status)
        row.setContentsMargins(4, 1, 4, 1)
        row.setSpacing(10)
        self.file_status = QLabel("File:")
        self.trace_status = QLabel("Trc= -")
        self.time_status = QLabel("Time= -")
        self.sample_status = QLabel("Smp= -")
        self.processing_status = QLabel("Ready")
        self.measure_status = QLabel("")
        row.addWidget(self.file_status, 4)
        row.addWidget(self.trace_status)
        row.addWidget(self.time_status)
        row.addWidget(self.sample_status)
        row.addWidget(self.processing_status, 2)
        row.addWidget(self.measure_status, 3)
        root.addWidget(status)

    # ------------------------------------------------------------------
    # File handling
    # ------------------------------------------------------------------
    def _choose_file(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(
            self,
            "Open SEG-Y File",
            str(self.file_path.parent if self.file_path else Path.cwd()),
            "SEG-Y (*.sgy *.segy *.seg *.su);;All files (*.*)",
        )
        if path:
            self.open_file(path)

    def open_file(self, file_path: str | Path) -> None:
        try:
            path = Path(file_path).expanduser().resolve()
            self.reader = SegyReader(path)
            self.index = self.reader.scan_trace_headers()
            if self.index.trace_count <= 0:
                raise ValueError("No complete SEG-Y traces were found")
            self.file_path = path
            self._effective_intervals_us = np.asarray(self.index.sample_intervals_us, dtype=np.float64)
            self.time_grid = build_time_grid(
                self.index.sample_counts,
                self.index.sample_intervals_us,
                self.index.delay_time_ms,
            )
            self._selected_trace = 0
            self._t0 = 0
            self._t1 = min(self.index.trace_count, 451)
            if self.time_grid is not None:
                self._s0 = 0
                self._s1 = min(self.time_grid.sample_count, 4200)
            self.canvas.set_extent(
                self.index.trace_count,
                self.time_grid.sample_count,
                self.time_grid.interval_ms,
                self.time_grid.start_ms,
            )
            self._populate_file_tables()
            self.select_trace(0, render_after=False)
            self._load_directory(path.parent)
            self.file_status.setText(f"File: {path}")
            self.processing_status.setText(f"{self.index.trace_count:,} traces • {self.time_grid.sample_count:,} samples • {self.time_grid.interval_ms:g} ms")
            self.render()
        except Exception as exc:
            QMessageBox.critical(self, "Open SEG-Y", str(exc))

    def _load_directory(self, directory: Path) -> None:
        try:
            directory = Path(directory).expanduser().resolve()
            if not directory.is_dir():
                directory = directory.parent
            self._current_dir = directory
            self.path_edit.setText(str(directory))
            self.file_list.clear()
            parent = QListWidgetItem("..")
            parent.setData(Qt.ItemDataRole.UserRole, str(directory.parent))
            self.file_list.addItem(parent)
            entries = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            for entry in entries:
                if entry.is_dir() or entry.suffix.lower() in {".sgy", ".segy", ".seg", ".su"}:
                    label = "📁 " + entry.name if entry.is_dir() else "▧ " + entry.name
                    item = QListWidgetItem(label)
                    item.setData(Qt.ItemDataRole.UserRole, str(entry))
                    self.file_list.addItem(item)
                    if entry.resolve() == self.file_path.resolve():
                        item.setSelected(True)
        except Exception as exc:
            self.processing_status.setText(f"Directory error: {exc}")

    def _refresh_file_list(self) -> None:
        self._load_directory(getattr(self, "_current_dir", self.file_path.parent))

    def _go_parent_dir(self) -> None:
        self._load_directory(Path(getattr(self, "_current_dir", self.file_path.parent)).parent)

    def _open_list_item(self, item: QListWidgetItem) -> None:
        path = Path(item.data(Qt.ItemDataRole.UserRole))
        if path.is_dir():
            self._load_directory(path)
        else:
            self.open_file(path)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def fit(self) -> None:
        if self.index is None or self.time_grid is None:
            return
        self.set_window(0, self.index.trace_count, 0, self.time_grid.sample_count)

    def reset_to_initial_view(self) -> None:
        """Return the SEG-Y viewer to the same display state used after opening."""
        if self.index is None or self.time_grid is None:
            return
        blockers = [
            QSignalBlocker(self.wiggle_cb),
            QSignalBlocker(self.gray_cb),
            QSignalBlocker(self.color_cb),
            QSignalBlocker(self.timelines_cb),
            QSignalBlocker(self.fill_none),
            QSignalBlocker(self.fill_pos),
            QSignalBlocker(self.fill_neg),
            QSignalBlocker(self.use_delay_cb),
            QSignalBlocker(self.normal_rb),
            QSignalBlocker(self.reversed_rb),
            QSignalBlocker(self.inversion_cb),
            QSignalBlocker(self.filter_cb),
            QSignalBlocker(self.agc_cb),
            QSignalBlocker(self.norm_cb),
            QSignalBlocker(self.weight_cb),
            QSignalBlocker(self.trace_scale),
            QSignalBlocker(self.time_scale),
            QSignalBlocker(self.gain_w),
            QSignalBlocker(self.gain_c),
        ]
        try:
            self.wiggle_cb.setChecked(True)
            self.gray_cb.setChecked(True)
            self.color_cb.setChecked(False)
            self.timelines_cb.setChecked(True)
            self.fill_none.setChecked(True)
            self.use_delay_cb.setChecked(False)
            self.normal_rb.setChecked(True)
            self.inversion_cb.setChecked(False)
            self.filter_cb.setChecked(False)
            self.agc_cb.setChecked(False)
            self.norm_cb.setChecked(False)
            self.weight_cb.setChecked(False)
            self.trace_scale.setValue(155)
            self.time_scale.setValue(307)
            self.gain_w.setValue(22)
            self.gain_c.setValue(22)
            self.low_cut_hz = 8.0
            self.high_cut_hz = 70.0
            self.agc_window_ms = 500.0
            self.clip_percent = 98.0
            self.canvas.clear_marks()
            self.canvas.interaction_mode = "inspect"
        finally:
            del blockers
        self._selected_trace = 0
        self._t0 = 0
        self._t1 = min(self.index.trace_count, 451)
        self._s0 = 0
        self._s1 = min(self.time_grid.sample_count, 4200)
        self.select_trace(0, render_after=False)
        self.measure_status.setText("Normal SEG-Y opening state restored")
        self.render()

    def set_window(self, t0: int, t1: int, s0: int, s1: int) -> None:
        if self.index is None or self.time_grid is None:
            return
        trace_count = self.index.trace_count
        sample_count = self.time_grid.sample_count
        t0 = int(np.clip(t0, 0, trace_count - 1))
        t1 = int(np.clip(t1, t0 + 1, trace_count))
        s0 = int(np.clip(s0, 0, sample_count - 1))
        s1 = int(np.clip(s1, s0 + 1, sample_count))
        self._t0, self._t1, self._s0, self._s1 = t0, t1, s0, s1
        self.render()

    def _display_mode_from_checks(self) -> None:
        if self._building_ui:
            return
        if not self.wiggle_cb.isChecked() and not self.gray_cb.isChecked() and not self.color_cb.isChecked():
            self.gray_cb.setChecked(True)
        self.color_density_changed.emit(self.color_cb.isChecked())
        self.render()

    def _apply_compat_mode(self) -> None:
        if self._building_ui:
            return
        value = self.mode.currentData()
        if value == "wiggle":
            self.wiggle_cb.setChecked(True)
            self.gray_cb.setChecked(False)
            self.color_cb.setChecked(False)
            self.fill_none.setChecked(True)
        elif value == "va":
            self.wiggle_cb.setChecked(True)
            self.gray_cb.setChecked(False)
            self.color_cb.setChecked(False)
            self.fill_pos.setChecked(True)
        elif value == "vd":
            self.wiggle_cb.setChecked(False)
            self.gray_cb.setChecked(True)
            self.color_cb.setChecked(False)
        elif value == "color":
            self.wiggle_cb.setChecked(False)
            self.gray_cb.setChecked(False)
            self.color_cb.setChecked(True)
        self.render()

    def _read_visible_data(self) -> tuple[list[int], np.ndarray]:
        if self.reader is None or self.index is None:
            return [], np.empty((0, 0), dtype=np.float32)
        t0, t1, s0, s1 = self._t0, self._t1, self._s0, self._s1
        visible_traces = max(1, t1 - t0)
        visible_samples = max(1, s1 - s0)
        trace_step = max(1, int(math.ceil(visible_traces / self.MAX_RENDER_TRACES)))
        sample_step = max(1, int(math.ceil(visible_samples / self.MAX_RENDER_SAMPLES)))
        trace_indices = list(range(t0, t1, trace_step))
        if trace_indices[-1] != t1 - 1 and len(trace_indices) < self.MAX_RENDER_TRACES:
            trace_indices.append(t1 - 1)
        sample_start = s0
        sample_end = s1
        if trace_step == 1:
            data = self.reader.read_trace_window((t0, t1), (sample_start, sample_end))
            trace_indices = list(range(t0, t1))
        else:
            rows = []
            for _idx, trace in self.reader.iter_traces(self.index, trace_indices):
                rows.append(np.asarray(trace[sample_start:sample_end], dtype=np.float32))
            width = max(0, sample_end - sample_start)
            data = np.zeros((len(rows), width), dtype=np.float32)
            for i, row in enumerate(rows):
                data[i, : min(width, row.size)] = row[:width]
        if sample_step > 1 and data.size:
            data = data[:, ::sample_step]
        return trace_indices, np.asarray(data, dtype=np.float32)

    def _apply_processing(self, data: np.ndarray) -> np.ndarray:
        arr = np.asarray(data, dtype=np.float32).copy()
        if arr.size == 0:
            return arr
        if self.reversed_rb.isChecked():
            arr = arr[::-1, :]
        if self.inversion_cb.isChecked():
            arr = -arr
        interval_ms = self.time_grid.interval_ms if self.time_grid is not None else 1.0
        if self.filter_cb.isChecked():
            arr = self._bandpass_display(arr, interval_ms)
        if self.agc_cb.isChecked():
            arr = apply_display_gain(arr, "agc", interval_ms, self.agc_window_ms)
        elif self.norm_cb.isChecked() or self.weight_cb.isChecked():
            arr = apply_display_gain(arr, "balance", interval_ms, self.agc_window_ms)
        return arr

    def _bandpass_display(self, data: np.ndarray, interval_ms: float) -> np.ndarray:
        arr = np.asarray(data, dtype=np.float32).copy()
        ns = arr.shape[1] if arr.ndim == 2 else 0
        if ns < 8 or interval_ms <= 0:
            return arr
        dt = interval_ms / 1000.0
        freq = np.fft.rfftfreq(ns, d=dt)
        low = max(0.0, float(self.low_cut_hz))
        high = max(0.0, float(self.high_cut_hz))
        mask = np.ones(freq.shape, dtype=bool)
        if low > 0:
            mask &= freq >= low
        if high > 0 and high > low:
            mask &= freq <= high
        if mask.all():
            return arr
        out = np.empty_like(arr)
        for i in range(arr.shape[0]):
            x = arr[i].astype(np.float64)
            finite = np.isfinite(x)
            if not np.any(finite):
                out[i] = arr[i]
                continue
            x = np.where(finite, x, 0.0)
            spectrum = np.fft.rfft(x)
            spectrum[~mask] = 0
            out[i] = np.fft.irfft(spectrum, n=ns).astype(np.float32)
        return out

    def render(self) -> None:
        if self.reader is None or self.index is None or self.time_grid is None:
            return
        show_busy = hasattr(self, "busy_overlay") and not self._rendering_busy
        if show_busy:
            self._rendering_busy = True
            self.busy_overlay.show_busy("Applying SEG-Y display", "Rendering traces and applying selected QC options")
        try:
            trace_indices, raw = self._read_visible_data()
            if len(trace_indices) == 0 or raw.size == 0:
                self.canvas.set_display(QImage(), [], None, self._t0, self._t1, self._s0, self._s1, self._selected_trace)
                return
            processed = self._apply_processing(raw)
            display = normalize_for_display(processed, self.clip_percent)
            self._last_trace_indices = trace_indices[::-1] if self.reversed_rb.isChecked() else trace_indices
            self._last_raw_window = processed
            image = self._render_image(display, self._last_trace_indices)
            self.canvas.set_extent(
                self.index.trace_count,
                self.time_grid.sample_count,
                self.time_grid.interval_ms,
                self.time_grid.start_ms,
            )
            self.canvas.set_selected_color(self.selected_color.color())
            self.canvas.set_display(
                image,
                self._last_trace_indices,
                display,
                self._t0,
                self._t1,
                self._s0,
                self._s1,
                self._selected_trace,
            )
            self.processing_status.setText(
                f"Window Trc {self._t0 + 1:,}-{self._t1:,} • Time {self.time_grid.start_ms + self._s0 * self.time_grid.interval_ms:.0f}-{self.time_grid.start_ms + (self._s1 - 1) * self.time_grid.interval_ms:.0f} ms • Draw {len(trace_indices):,} traces"
            )
        except Exception as exc:
            self.processing_status.setText(f"Render error: {exc}")
            QMessageBox.warning(self, "SEG-Y Render", str(exc))
        finally:
            if show_busy:
                self.busy_overlay.hide_busy()
                self._rendering_busy = False


    def _render_image(self, data: np.ndarray, trace_indices: Sequence[int]) -> QImage:
        nt, ns = data.shape
        width = max(720, min(2600, int(max(1, self.width() - 310))))
        height = max(420, min(1800, int(max(1, self.height() - 120))))
        image = QImage(width, height, QImage.Format.Format_RGB32)
        image.fill(QColor(255, 255, 255))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, nt < 350)

        if self.gray_cb.isChecked() or self.color_cb.isChecked():
            self._draw_density(painter, data, width, height, color=self.color_cb.isChecked())
        if self.timelines_cb.isChecked():
            self._draw_timelines(painter, width, height)
        if self.wiggle_cb.isChecked():
            self._draw_wiggles(painter, data, width, height)
        painter.end()
        return image

    def _draw_density(self, painter: QPainter, data: np.ndarray, width: int, height: int, *, color: bool) -> None:
        nt, ns = data.shape
        xidx = np.clip(np.rint(np.linspace(0, nt - 1, width)).astype(int), 0, nt - 1)
        yidx = np.clip(np.rint(np.linspace(0, ns - 1, height)).astype(int), 0, ns - 1)
        z = data[xidx][:, yidx].T
        valid = np.isfinite(z)
        if color:
            rgb = np.full((height, width, 3), 255, dtype=np.uint8)
            values = np.clip(z[valid], -1.0, 1.0)
            lut = palette_to_rgb_array(self.color_palette_name, 256)
            palette_indices = np.clip(((values + 1.0) * 0.5 * 255.0).round().astype(np.int16), 0, 255)
            rgb[valid] = lut[palette_indices]
        else:
            gray = np.full((height, width), 255, dtype=np.uint8)
            gray[valid] = np.clip((1.0 - ((z[valid] + 1.0) * 0.5)) * 255, 0, 255).astype(np.uint8)
            rgb = np.dstack((gray, gray, gray))
        raster = QImage(rgb.data, width, height, 3 * width, QImage.Format.Format_RGB888).copy()
        painter.drawImage(0, 0, raster)

    def _draw_timelines(self, painter: QPainter, width: int, height: int) -> None:
        if self.time_grid is None:
            return
        painter.setPen(QPen(QColor(170, 170, 170), 1, Qt.PenStyle.DotLine))
        sample_span = max(1, self._s1 - self._s0)
        time_top = self.time_grid.start_ms + self._s0 * self.time_grid.interval_ms
        time_bottom = self.time_grid.start_ms + (self._s1 - 1) * self.time_grid.interval_ms
        step = 200 if (time_bottom - time_top) > 1000 else 100 if (time_bottom - time_top) > 300 else 50
        tick = int(math.ceil(time_top / step) * step)
        while tick <= time_bottom:
            sample = int(round((tick - self.time_grid.start_ms) / self.time_grid.interval_ms))
            y = int(round((sample - self._s0) / sample_span * height))
            painter.drawLine(0, y, width, y)
            tick += step

    def _draw_wiggles(self, painter: QPainter, data: np.ndarray, width: int, height: int) -> None:
        nt, ns = data.shape
        if nt <= 0 or ns <= 1:
            return
        spacing = width / max(1, nt)
        gain = max(0.05, self.gain_w.value() / 50.0)
        scale = min(0.48, 0.33 + 0.04 * math.log10(max(1.0, spacing))) * spacing * gain
        ycoords = np.linspace(0, height - 1, ns)
        pen_width = 0 if nt > 450 else 1
        painter.setPen(QPen(self.wiggle_color.color(), pen_width))
        fill_mode = "none"
        if self.fill_pos.isChecked():
            fill_mode = "positive"
        elif self.fill_neg.isChecked():
            fill_mode = "negative"
        fill_brush = QColor(self.fill_color.color())
        fill_brush.setAlpha(120)
        for i in range(nt):
            trace = data[i]
            valid = np.isfinite(trace)
            if np.count_nonzero(valid) < 2:
                continue
            base = (i + 0.5) * spacing
            idx = np.flatnonzero(valid)
            path = QPainterPath(QPointF(base + float(trace[idx[0]]) * scale, float(ycoords[idx[0]])))
            previous = idx[0]
            for j in idx[1:]:
                if j != previous + 1:
                    painter.drawPath(path)
                    path = QPainterPath(QPointF(base + float(trace[j]) * scale, float(ycoords[j])))
                else:
                    path.lineTo(base + float(trace[j]) * scale, float(ycoords[j]))
                previous = j
            painter.drawPath(path)
            if fill_mode != "none":
                mask = valid & (trace >= 0 if fill_mode == "positive" else trace <= 0)
                starts = np.flatnonzero(mask & ~np.r_[False, mask[:-1]])
                ends = np.flatnonzero(mask & ~np.r_[mask[1:], False])
                for start, end in zip(starts, ends):
                    if end <= start:
                        continue
                    fill_path = QPainterPath(QPointF(base, float(ycoords[start])))
                    for j in range(start, end + 1):
                        fill_path.lineTo(base + float(trace[j]) * scale, float(ycoords[j]))
                    fill_path.lineTo(base, float(ycoords[end]))
                    fill_path.closeSubpath()
                    painter.fillPath(fill_path, fill_brush)

    # ------------------------------------------------------------------
    # Selection, headers and QC readouts
    # ------------------------------------------------------------------
    def select_trace(self, trace_index: int, *, render_after: bool = True) -> None:
        if self.reader is None or self.index is None:
            return
        self._selected_trace = int(np.clip(trace_index, 0, self.index.trace_count - 1))
        try:
            header = self.reader.read_trace_header(self._selected_trace, self.index)
            self._set_table(self.trace_header, list(vars(header).items()))
            trace = self.reader.read_trace(self._selected_trace, self.index).astype(np.float64)
            finite = trace[np.isfinite(trace)]
            dt_us = float(self.index.sample_intervals_us[self._selected_trace])
            metrics = {
                "selected_trace_index": self._selected_trace + 1,
                "samples": trace.size,
                "sample_interval_us": dt_us,
                "delay_time_ms": int(self.index.delay_time_ms[self._selected_trace]),
                "min": np.min(finite) if finite.size else np.nan,
                "max": np.max(finite) if finite.size else np.nan,
                "mean": np.mean(finite) if finite.size else np.nan,
                "std": np.std(finite) if finite.size else np.nan,
                "rms": trace_rms(finite),
            }
            rows = list(vars(header).items()) + [("--- QC Metrics ---", "")] + list(metrics.items())
            self._set_table(self.trace_header, rows)
            self.trace_status.setText(f"Trc={self._selected_trace + 1}")
            if render_after:
                self.canvas._selected_trace = self._selected_trace
                self.canvas.update()
        except Exception as exc:
            self.processing_status.setText(f"Trace read error: {exc}")

    def _update_cursor(self, trace: int, sample: int, time_ms: float, amplitude: float) -> None:
        self.trace_status.setText(f"Trc={trace + 1}")
        self.time_status.setText(f"Time={time_ms:.1f}")
        self.sample_status.setText(f"Smp={amplitude:.6g}" if np.isfinite(amplitude) else f"Smp={sample + 1}")

    def _set_measure_status(self, text: str) -> None:
        self.measure_status.setText(text)

    def _populate_file_tables(self) -> None:
        if self.reader is None:
            return
        self._set_table(self.binary, list(vars(self.reader.binary_header).items()))
        self.text_header.setPlainText(self.reader.text_header.text)

    @staticmethod
    def _set_table(table: QTableWidget, items) -> None:
        rows = list(items)
        table.setRowCount(len(rows))
        for row, (key, value) in enumerate(rows):
            key_item = QTableWidgetItem(str(key))
            value_item = QTableWidgetItem(str(value))
            table.setItem(row, 0, key_item)
            table.setItem(row, 1, value_item)
        table.resizeRowsToContents()

    def _show_area_zoom_dialog(self, t0: int, t1: int, s0: int, s1: int) -> None:
        if self.reader is None or self.index is None or self.time_grid is None:
            return
        t0 = int(np.clip(t0, 0, self.index.trace_count - 1)); t1 = int(np.clip(t1, t0 + 1, self.index.trace_count))
        s0 = int(np.clip(s0, 0, self.time_grid.sample_count - 1)); s1 = int(np.clip(s1, s0 + 1, self.time_grid.sample_count))
        image = QImage()
        stats = "No samples"
        raw = np.asarray([], dtype=np.float32)
        try:
            raw = self.reader.read_trace_window((t0, t1), (s0, s1))
            raw = np.asarray(raw, dtype=np.float32)
            processed = self._apply_processing(raw)
            display = normalize_for_display(processed, self.clip_percent)
            old_window = (self._t0, self._t1, self._s0, self._s1)
            try:
                self._t0, self._t1, self._s0, self._s1 = t0, t1, s0, s1
                image = self._render_image(display, list(range(t0, t1)))
            finally:
                self._t0, self._t1, self._s0, self._s1 = old_window
            finite = raw[np.isfinite(raw)] if raw.size else np.asarray([])
            if finite.size:
                stats = f"min {float(np.min(finite)):.6g} | max {float(np.max(finite)):.6g} | rms {float(np.sqrt(np.mean(np.square(finite)))):.6g}"
        except Exception as exc:
            image = self.canvas._image.copy() if not self.canvas._image.isNull() else QImage()
            stats = f"Preview fallback: {exc}"
        start_ms = self.time_grid.start_ms + s0 * self.time_grid.interval_ms
        end_ms = self.time_grid.start_ms + (s1 - 1) * self.time_grid.interval_ms

        def _fmt(value: object, decimals: int = 5) -> str:
            try:
                number = float(value)
                if not np.isfinite(number):
                    return "—"
                return f"{number:.{decimals}g}"
            except Exception:
                return "—" if value is None else str(value)

        trace_rows: list[tuple[str, str, str, str, str, str, str]] = []
        max_trace_rows = 160
        for local_idx, trace_index in enumerate(range(t0, min(t1, t0 + max_trace_rows))):
            row_data = raw[local_idx] if raw.ndim == 2 and local_idx < raw.shape[0] else np.asarray([])
            finite_row = row_data[np.isfinite(row_data)] if row_data.size else np.asarray([])
            if finite_row.size:
                mn = float(np.min(finite_row)); mx = float(np.max(finite_row)); rms = float(np.sqrt(np.mean(np.square(finite_row))))
                peak_idx = int(np.argmax(np.abs(row_data))) if row_data.size else 0
                amp = float(row_data[peak_idx]) if row_data.size else float("nan")
                smp = s0 + peak_idx
                tms = self.time_grid.start_ms + smp * self.time_grid.interval_ms
            else:
                mn = mx = rms = amp = float("nan"); smp = s0; tms = self.time_grid.start_ms + s0 * self.time_grid.interval_ms
            trace_rows.append((str(trace_index + 1), str(smp + 1), f"{tms:.2f}", _fmt(amp), _fmt(mn), _fmt(mx), _fmt(rms)))

        details = [
            ("File", str(self.file_path)),
            ("Trace range", f"{t0 + 1} – {t1} ({t1 - t0} traces)"),
            ("Sample range", f"{s0 + 1} – {s1} ({s1 - s0} samples)"),
            ("Time range", f"{start_ms:.2f} – {end_ms:.2f} ms"),
            ("Amplitude statistics", stats),
            ("Display mode", "Wiggle" if self.wiggle_cb.isChecked() else "Colour" if self.color_cb.isChecked() else "Gray"),
            ("Trace detail rows", f"{len(trace_rows)} row(s) shown" + (f" of {t1 - t0}" if t1 - t0 > len(trace_rows) else "")),
            ("Manual QC", "Use the side trace values to check noisy/dead traces, high amplitude bursts, polarity reversals and timing continuity."),
        ]
        dialog = SelectionZoomDialog(
            "SEG-Y Selected Area QC Zoom",
            image,
            details,
            trace_rows,
            self,
            trace_data=raw if isinstance(raw, np.ndarray) and raw.ndim == 2 else None,
            trace_start=t0,
            sample_start=s0,
            sample_interval_ms=self.time_grid.interval_ms,
        )
        dialog.exec()
        if dialog.open_main_requested:
            self.set_window(t0, t1, s0, s1)

    # ------------------------------------------------------------------
    # Tools and export
    # ------------------------------------------------------------------
    def _set_tool_mode(self, mode: str) -> None:
        self.canvas.interaction_mode = mode
        for btn in getattr(self, "tool_buttons", []):
            btn.setChecked(False)
        sender = self.sender()
        if isinstance(sender, QPushButton):
            sender.setChecked(True)
        self.measure_status.setText(f"Tool: {mode}")

    def _clear_marks(self) -> None:
        self.canvas.clear_marks()
        self.measure_status.setText("Picks/measure cleared")

    def show_processing_dialog(self) -> None:
        dialog = ProcessingDialog(self)
        dialog.exec()

    def _show_short_help(self) -> None:
        QMessageBox.information(
            self,
            "SEG-Y Viewer Help",
            "Wheel: zoom trace/time\nCtrl+Wheel: traces only\nShift+Wheel: time only\nRight-drag: selected area QC zoom dialog\nMiddle-drag or Pan tool: pan\nZoom tool: draw a zoom box\nPick tool: store manual QC picks\nMeasure tool: click start and end points\nEsc: clear active measurement",
        )

    def show_display_page(self) -> None:
        self.tabs.setCurrentIndex(0)

    def show_file_info_page(self) -> None:
        self.tabs.setCurrentIndex(3)

    def show_manual_qc_page(self) -> None:
        self.tabs.setCurrentIndex(1)

    def show_headers_page(self) -> None:
        self.tabs.setCurrentIndex(2)

    def show_trace_analysis_page(self) -> None:
        self.tabs.setCurrentIndex(2)

    def show_hardcopy_page(self) -> None:
        self.tabs.setCurrentIndex(3)

    # ------------------------------------------------------------------
    # Main ribbon integration
    # ------------------------------------------------------------------
    def set_display_preset(self, preset: str) -> None:
        preset = str(preset).lower().strip()
        self._building_ui = True
        try:
            if preset == "wiggle":
                self.wiggle_cb.setChecked(True)
                self.gray_cb.setChecked(False)
                self.color_cb.setChecked(False)
                self.fill_none.setChecked(True)
            elif preset in {"va", "variable_area", "variable area"}:
                self.wiggle_cb.setChecked(True)
                self.gray_cb.setChecked(False)
                self.color_cb.setChecked(False)
                self.fill_pos.setChecked(True)
            elif preset in {"vd", "variable_density", "variable density", "gray"}:
                self.wiggle_cb.setChecked(False)
                self.gray_cb.setChecked(True)
                self.color_cb.setChecked(False)
            elif preset in {"color", "color_density", "color density"}:
                self.wiggle_cb.setChecked(False)
                self.gray_cb.setChecked(False)
                self.color_cb.setChecked(True)
            elif preset == "wiggle_gray":
                self.wiggle_cb.setChecked(True)
                self.gray_cb.setChecked(True)
                self.color_cb.setChecked(False)
        finally:
            self._building_ui = False
        self.color_density_changed.emit(self.color_cb.isChecked())
        self.render()

    def set_display_layer(self, layer: str, enabled: Optional[bool] = None) -> None:
        cb = {
            "wiggle": self.wiggle_cb,
            "gray": self.gray_cb,
            "grey": self.gray_cb,
            "color": self.color_cb,
            "colour": self.color_cb,
            "timelines": self.timelines_cb,
            "timeline": self.timelines_cb,
        }.get(str(layer).lower())
        if cb is None:
            return
        cb.setChecked((not cb.isChecked()) if enabled is None else bool(enabled))
        if not self.wiggle_cb.isChecked() and not self.gray_cb.isChecked() and not self.color_cb.isChecked():
            self.gray_cb.setChecked(True)
        self.color_density_changed.emit(self.color_cb.isChecked())
        self.render()

    def set_fill_mode(self, mode: str) -> None:
        mode = str(mode).lower().strip()
        if mode in {"none", "no", "off"}:
            self.fill_none.setChecked(True)
        elif mode in {"positive", "pos", "+"}:
            self.fill_pos.setChecked(True)
            self.wiggle_cb.setChecked(True)
        elif mode in {"negative", "neg", "-"}:
            self.fill_neg.setChecked(True)
            self.wiggle_cb.setChecked(True)
        self.render()

    def toggle_use_delay_header(self) -> None:
        self.use_delay_cb.setChecked(not self.use_delay_cb.isChecked())
        self.render()

    def set_color_palette(self, palette: str) -> None:
        requested = str(palette or "Seismic").strip()
        for name in COLOR_PALETTES:
            if name.lower() == requested.lower():
                self.color_palette_name = name
                self.render()
                return
        self.color_palette_name = "Seismic"
        self.render()

    def open_color_library(self) -> None:
        current = self.color_palette_name
        dialog = ColorPaletteDialog(current, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.set_color_palette(dialog.selected_palette)

    def choose_display_color(self, target: str) -> None:
        button = {
            "wiggle": self.wiggle_color,
            "fill": self.fill_color,
            "selected": self.selected_color,
            "selection": self.selected_color,
        }.get(str(target).lower())
        if button is not None:
            button._choose()

    def adjust_scale_control(self, target: str, delta: int) -> None:
        slider = {
            "traces": self.trace_scale,
            "trace": self.trace_scale,
            "time": self.time_scale,
            "gain_w": self.gain_w,
            "gain-w": self.gain_w,
            "wiggle_gain": self.gain_w,
            "gain_c": self.gain_c,
            "gain-c": self.gain_c,
            "color_gain": self.gain_c,
        }.get(str(target).lower())
        if slider is None:
            return
        slider.setValue(int(np.clip(slider.value() + int(delta), slider.minimum(), slider.maximum())))
        self.render()

    def set_direction(self, direction: str) -> None:
        direction = str(direction).lower().strip()
        if direction.startswith("rev"):
            self.reversed_rb.setChecked(True)
        else:
            self.normal_rb.setChecked(True)
        self.render()

    def toggle_processing_option(self, option: str) -> None:
        cb = {
            "inversion": self.inversion_cb,
            "invert": self.inversion_cb,
            "filter": self.filter_cb,
            "agc": self.agc_cb,
            "norm": self.norm_cb,
            "normalize": self.norm_cb,
            "weight": self.weight_cb,
        }.get(str(option).lower())
        if cb is not None:
            cb.setChecked(not cb.isChecked())
            self.render()

    def set_viewer_tool(self, mode: str) -> None:
        self._set_tool_mode(mode)

    def clear_picks_and_measurements(self) -> None:
        self._clear_marks()

    def open_from_dialog(self) -> None:
        self._choose_file()

    def export_image(self) -> None:
        if self.canvas._image.isNull():
            return
        path, selected = QFileDialog.getSaveFileName(
            self,
            "Export SEG-Y View",
            str(self.file_path.with_suffix(".png")),
            "PNG (*.png);;JPEG (*.jpg *.jpeg);;BMP (*.bmp)",
        )
        if not path:
            return
        output = Path(path)
        suffix = output.suffix.lower()
        if not suffix:
            if "BMP" in selected:
                output = output.with_suffix(".bmp")
            elif "JPEG" in selected:
                output = output.with_suffix(".jpg")
            else:
                output = output.with_suffix(".png")
        fmt = "BMP" if output.suffix.lower() == ".bmp" else "JPEG" if output.suffix.lower() in {".jpg", ".jpeg"} else "PNG"
        if not self.canvas._image.save(str(output), fmt):
            QMessageBox.warning(self, "Export", "Could not save image")

    def export_bmp(self) -> None:
        if self.canvas._image.isNull():
            return
        path, _selected = QFileDialog.getSaveFileName(self, "Export BMP", str(self.file_path.with_suffix(".bmp")), "BMP (*.bmp)")
        if path and not self.canvas._image.save(str(Path(path).with_suffix(".bmp")), "BMP"):
            QMessageBox.warning(self, "Export", "Could not save BMP")

    def copy_view_to_clipboard(self) -> None:
        if self.canvas._image.isNull():
            return
        QGuiApplication.clipboard().setImage(self.canvas._image)
        self.measure_status.setText("View copied to clipboard")

    def export_trace_headers_csv(self) -> None:
        if self.index is None:
            return
        path, _selected = QFileDialog.getSaveFileName(self, "Export Trace Headers CSV", str(self.file_path.with_name(self.file_path.stem + "_trace_headers.csv")), "CSV (*.csv)")
        if not path:
            return
        try:
            headers = [
                "trace_sequence_line", "trace_sequence_file", "field_record", "trace_number", "energy_source_point",
                "cdp", "cdp_trace", "trace_identification", "offset", "source_x", "source_y", "receiver_x", "receiver_y",
                "delay_time_ms", "sample_count", "sample_interval_us", "inline_3d", "crossline_3d", "shotpoint",
            ]
            with Path(path).open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(headers)
                for i in range(self.index.trace_count):
                    h = self.reader.read_trace_header(i, self.index) if self.reader is not None else None
                    writer.writerow([getattr(h, name) for name in headers])
            self.measure_status.setText(f"Trace headers exported: {path}")
        except Exception as exc:
            QMessageBox.warning(self, "Export Headers", str(exc))

