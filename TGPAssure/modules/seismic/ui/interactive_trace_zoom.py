from __future__ import annotations

import math
from typing import Optional, Sequence

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget


STATUS_PALETTE: dict[str, QColor] = {
    "Normal": QColor(31, 154, 85),
    "High amplitude": QColor(224, 133, 0),
    "Dead/Flat": QColor(185, 35, 35),
    "Invalid": QColor(168, 30, 70),
    "Auxiliary": QColor(132, 132, 132),
    "Resistance": QColor(230, 35, 35),
    "Capacitance": QColor(214, 0, 208),
    "Leakage": QColor(30, 80, 235),
    "Tilt": QColor(0, 170, 58),
    "Multiple": QColor(220, 185, 0),
    "Dead": QColor(150, 0, 0),
    "Edited": QColor(225, 117, 22),
    "Unknown": QColor(95, 110, 125),
}


class InteractiveTraceZoomCanvas(QWidget):
    """Crisp interactive seismic trace preview for SEG-D and SEG-Y zoom dialogs.

    The widget draws the selected window as vector wiggle traces rather than a
    scaled bitmap.  Hover feedback is intentionally smooth: mouse events update a
    target cursor, and a short timer eases the visible crosshair to that target.
    Values are emitted to the dialog-side tables so the plot remains clean.
    """

    cursor_changed = Signal(dict)
    cursor_cleared = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(540, 340)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._data = np.empty((0, 0), dtype=np.float32)
        self._trace_start = 0
        self._sample_start = 0
        self._sample_interval_ms = 1.0
        self._trace_labels: list[str] = []
        self._trace_statuses: list[str] = []
        self._title = "Selected trace window"
        self._cursor_target: Optional[QPointF] = None
        self._cursor_display: Optional[QPointF] = None
        self._last_info: Optional[dict] = None
        self._positive_fill = True
        self._amp_scale: float | None = None
        self._trace_peak: np.ndarray = np.empty(0, dtype=np.float32)
        self._trace_rms: np.ndarray = np.empty(0, dtype=np.float32)
        self._animation_timer = QTimer(self)
        self._animation_timer.setInterval(22)
        self._last_emit_signature: tuple[int, int, str] | None = None
        self._static_cache: QPixmap | None = None
        self._animation_timer.timeout.connect(self._animate_cursor)

    def set_data(
        self,
        data: np.ndarray | Sequence[Sequence[float]] | None,
        *,
        trace_start: int,
        sample_start: int,
        sample_interval_ms: float,
        trace_labels: Sequence[str] | None = None,
        trace_statuses: Sequence[str] | None = None,
        title: str = "Selected trace window",
    ) -> None:
        array = np.asarray(data if data is not None else [], dtype=np.float32)
        if array.ndim == 3 and array.shape[1] == 1:
            array = array[:, 0, :]
        if array.ndim == 1:
            array = array.reshape(1, -1)
        if array.ndim != 2:
            array = np.empty((0, 0), dtype=np.float32)
        self._data = array
        self._trace_start = int(trace_start)
        self._sample_start = int(sample_start)
        self._sample_interval_ms = max(float(sample_interval_ms), 1e-12)
        self._trace_labels = [str(v) for v in (trace_labels or [])]
        self._trace_statuses = [str(v or "Normal") for v in (trace_statuses or [])]
        self._title = title
        self._cursor_target = None
        self._cursor_display = None
        self._last_info = None
        self._amp_scale = self._robust_amplitude_scale()
        self._prepare_trace_stats()
        self._last_emit_signature = None
        self._invalidate_static_cache()
        self.update()

    def _invalidate_static_cache(self) -> None:
        self._static_cache = None

    def resizeEvent(self, event) -> None:
        self._invalidate_static_cache()
        super().resizeEvent(event)

    def has_data(self) -> bool:
        return bool(self._data.ndim == 2 and self._data.shape[0] > 0 and self._data.shape[1] > 0)

    def plot_rect(self) -> QRectF:
        return QRectF(46.0, 26.0, max(1.0, self.width() - 60.0), max(1.0, self.height() - 48.0))

    def _prepare_trace_stats(self) -> None:
        if not self.has_data():
            self._trace_peak = np.empty(0, dtype=np.float32)
            self._trace_rms = np.empty(0, dtype=np.float32)
            return
        peaks: list[float] = []
        rms_values: list[float] = []
        for row in self._data:
            finite = row[np.isfinite(row)] if row.size else np.asarray([])
            if finite.size:
                peaks.append(float(np.nanmax(np.abs(finite))))
                rms_values.append(float(np.sqrt(np.nanmean(np.square(finite, dtype=np.float64)))))
            else:
                peaks.append(float("nan"))
                rms_values.append(float("nan"))
        self._trace_peak = np.asarray(peaks, dtype=np.float32)
        self._trace_rms = np.asarray(rms_values, dtype=np.float32)

    def _robust_amplitude_scale(self) -> float:
        if not self.has_data():
            return 1.0
        finite = self._data[np.isfinite(self._data)]
        if finite.size == 0:
            return 1.0
        scale = float(np.nanpercentile(np.abs(finite), 98.0))
        if not np.isfinite(scale) or scale <= 0.0:
            scale = float(np.nanmax(np.abs(finite))) if finite.size else 1.0
        return max(scale, 1e-12)

    def _trace_x(self, local_trace: int) -> float:
        plot = self.plot_rect()
        ntr = max(1, self._data.shape[0])
        return plot.left() + (float(local_trace) + 0.5) / ntr * plot.width()

    def _sample_y(self, local_sample: int) -> float:
        plot = self.plot_rect()
        ns = max(1, self._data.shape[1] - 1)
        return plot.top() + float(local_sample) / ns * plot.height()

    def _position_to_indices(self, pos: QPointF) -> tuple[int, int] | None:
        if not self.has_data():
            return None
        plot = self.plot_rect()
        if not plot.contains(pos):
            return None
        ntr, ns = self._data.shape
        fx = (pos.x() - plot.left()) / max(1.0, plot.width())
        fy = (pos.y() - plot.top()) / max(1.0, plot.height())
        lt = int(np.clip(math.floor(fx * ntr), 0, ntr - 1))
        ls = int(np.clip(round(fy * max(1, ns - 1)), 0, ns - 1))
        return lt, ls

    def _status_for(self, local_trace: int, local_sample: int, amplitude: float) -> tuple[str, QColor]:
        status = self._trace_statuses[local_trace] if local_trace < len(self._trace_statuses) else "Normal"
        status = status if status and status.lower() not in {"ok", "pass", "good"} else "Normal"
        if not np.isfinite(amplitude):
            status = "Invalid"
        elif status == "Normal":
            peak = float(self._trace_peak[local_trace]) if local_trace < self._trace_peak.size else float("nan")
            rms = float(self._trace_rms[local_trace]) if local_trace < self._trace_rms.size else float("nan")
            amp_scale = max(float(self._amp_scale or 1.0), 1e-12)
            if np.isfinite(peak) and peak <= amp_scale * 1e-5:
                status = "Dead/Flat"
            elif np.isfinite(rms) and rms <= amp_scale * 1e-6:
                status = "Dead/Flat"
            elif abs(float(amplitude)) >= amp_scale * 0.92:
                status = "High amplitude"
        color = STATUS_PALETTE.get(status, STATUS_PALETTE.get("Unknown", QColor(95, 110, 125)))
        return status, color

    def _info_at(self, pos: QPointF) -> Optional[dict]:
        indices = self._position_to_indices(pos)
        if indices is None:
            return None
        lt, ls = indices
        row = self._data[lt]
        amp = float(row[ls]) if 0 <= ls < row.size and np.isfinite(row[ls]) else float("nan")
        finite = row[np.isfinite(row)] if row.size else np.asarray([])
        status, color = self._status_for(lt, ls, amp)
        return {
            "trace": self._trace_start + lt,
            "sample": self._sample_start + ls,
            "time_ms": (self._sample_start + ls) * self._sample_interval_ms,
            "amplitude": amp,
            "local_trace": lt,
            "local_sample": ls,
            "min": float(np.min(finite)) if finite.size else float("nan"),
            "max": float(np.max(finite)) if finite.size else float("nan"),
            "rms": float(np.sqrt(np.mean(np.square(finite, dtype=np.float64)))) if finite.size else float("nan"),
            "peak": float(self._trace_peak[lt]) if lt < self._trace_peak.size else float("nan"),
            "status": status,
            "status_color": (color.red(), color.green(), color.blue()),
        }

    def mouseMoveEvent(self, event) -> None:
        point = event.position()
        info = self._info_at(point)
        if info is None:
            self._clear_cursor()
        else:
            self._cursor_target = QPointF(point)
            if self._cursor_display is None:
                self._cursor_display = QPointF(point)
            self._last_info = info
            signature = (
                int(info.get("local_trace", -1)),
                int(info.get("local_sample", -1)),
                str(info.get("status", "Normal")),
            )
            if signature != self._last_emit_signature:
                self._last_emit_signature = signature
                self.cursor_changed.emit(info)
            if not self._animation_timer.isActive():
                self._animation_timer.start()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self._clear_cursor()
        super().leaveEvent(event)

    def _clear_cursor(self) -> None:
        had_cursor = self._last_info is not None or self._cursor_display is not None
        self._cursor_target = None
        self._cursor_display = None
        self._last_info = None
        self._last_emit_signature = None
        self._animation_timer.stop()
        if had_cursor:
            self.cursor_cleared.emit()
            self.update()

    def _animate_cursor(self) -> None:
        if self._cursor_target is None:
            self._animation_timer.stop()
            self.update()
            return
        if self._cursor_display is None:
            self._cursor_display = QPointF(self._cursor_target)
        dx = self._cursor_target.x() - self._cursor_display.x()
        dy = self._cursor_target.y() - self._cursor_display.y()
        if abs(dx) < 0.25 and abs(dy) < 0.25:
            self._cursor_display = QPointF(self._cursor_target)
            self._animation_timer.stop()
        else:
            self._cursor_display.setX(self._cursor_display.x() + dx * 0.42)
            self._cursor_display.setY(self._cursor_display.y() + dy * 0.42)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        if self._static_cache is None or self._static_cache.size() != self.size():
            self._rebuild_static_cache()
        if self._static_cache is not None:
            painter.drawPixmap(0, 0, self._static_cache)
        if self.has_data():
            plot = self.plot_rect()
            self._draw_hover_trace(painter, plot)
            self._draw_crosshair(painter, plot)
        painter.end()

    def _rebuild_static_cache(self) -> None:
        cache = QPixmap(max(1, self.width()), max(1, self.height()))
        cache.fill(QColor(240, 244, 248))
        painter = QPainter(cache)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        plot = self.plot_rect()
        painter.fillRect(plot, QColor(255, 255, 255))
        painter.setPen(QPen(QColor(112, 132, 148), 1))
        painter.drawRect(plot)
        self._draw_title(painter, plot)
        if not self.has_data():
            painter.setPen(QPen(QColor(90, 104, 116), 1))
            painter.drawText(plot, Qt.AlignmentFlag.AlignCenter, "No selected trace samples are available.")
        else:
            self._draw_axes(painter, plot)
            saved_info = self._last_info
            self._last_info = None
            try:
                self._draw_wiggles(painter, plot)
            finally:
                self._last_info = saved_info
        painter.end()
        self._static_cache = cache

    def _draw_title(self, painter: QPainter, plot: QRectF) -> None:
        font = QFont(painter.font())
        font.setPointSizeF(8.0)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(QColor(20, 48, 67), 1))
        painter.drawText(QRectF(plot.left(), 4, plot.width(), 18), Qt.AlignmentFlag.AlignCenter, self._title)

    def _draw_axes(self, painter: QPainter, plot: QRectF) -> None:
        ntr, ns = self._data.shape
        font = QFont(painter.font())
        font.setPointSizeF(6.8)
        painter.setFont(font)
        painter.setPen(QPen(QColor(70, 82, 92), 1))
        y0 = self._sample_start * self._sample_interval_ms
        y1 = (self._sample_start + ns - 1) * self._sample_interval_ms
        ticks_y = 6
        for i in range(ticks_y + 1):
            f = i / ticks_y
            y = plot.top() + f * plot.height()
            value = y0 + f * (y1 - y0)
            painter.drawLine(int(plot.left() - 4), int(y), int(plot.left()), int(y))
            painter.drawText(QRectF(1, y - 8, 41, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{value:.0f}")
        painter.drawText(QRectF(1, plot.top() - 18, 41, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "ms")

        step = max(1, int(math.ceil(ntr / 10.0)))
        for lt in range(0, ntr, step):
            x = self._trace_x(lt)
            painter.drawLine(int(x), int(plot.bottom()), int(x), int(plot.bottom() + 4))
            label = self._trace_labels[lt] if lt < len(self._trace_labels) else str(self._trace_start + lt + 1)
            painter.drawText(QRectF(x - 24, plot.bottom() + 4, 48, 14), Qt.AlignmentFlag.AlignCenter, label)

    def _draw_wiggles(self, painter: QPainter, plot: QRectF) -> None:
        ntr, ns = self._data.shape
        trace_spacing = plot.width() / max(1, ntr)
        amp_scale = self._amp_scale or 1.0
        x_scale = 0.42 * trace_spacing / amp_scale
        sample_step = max(1, int(math.ceil(ns / max(110.0, plot.height() * 2.4))))
        hovered_trace = int(self._last_info.get("local_trace", -1)) if self._last_info else -1
        painter.setClipRect(plot.adjusted(1, 1, -1, -1))
        zero_pen = QPen(QColor(224, 229, 234), 1)
        trace_pen = QPen(QColor(18, 28, 36), 1)
        fill_brush = QColor(28, 96, 170, 38)
        for lt in range(ntr):
            x0 = self._trace_x(lt)
            if trace_spacing >= 4.0:
                painter.setPen(zero_pen)
                painter.drawLine(QPointF(x0, plot.top()), QPointF(x0, plot.bottom()))
            values = np.asarray(self._data[lt], dtype=np.float64)
            if values.size == 0:
                continue
            indices = np.arange(0, ns, sample_step, dtype=int)
            if indices[-1] != ns - 1:
                indices = np.append(indices, ns - 1)
            path = QPainterPath()
            first = True
            positive_poly: list[QPointF] = []
            for idx in indices:
                value = values[idx]
                if not np.isfinite(value):
                    first = True
                    positive_poly.clear()
                    continue
                x = x0 + float(value) * x_scale
                y = self._sample_y(int(idx))
                point = QPointF(x, y)
                if first:
                    path.moveTo(point)
                    first = False
                else:
                    path.lineTo(point)
                if self._positive_fill and value >= 0.0 and trace_spacing >= 5.0:
                    positive_poly.append(point)
                    positive_poly.append(QPointF(x0, y))
            if lt == hovered_trace:
                status_color = QColor(*self._last_info.get("status_color", (30, 120, 190)))
                painter.setPen(QPen(status_color, 2.0))
            else:
                painter.setPen(trace_pen)
            painter.drawPath(path)
            if self._positive_fill and positive_poly and trace_spacing >= 5.0:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(fill_brush)
                for i in range(0, len(positive_poly) - 1, 2):
                    p = positive_poly[i]
                    z = positive_poly[i + 1]
                    painter.drawLine(z, p)
                painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setClipping(False)

    def _build_trace_path(self, local_trace: int, plot: QRectF) -> QPainterPath:
        path = QPainterPath()
        if not self.has_data() or not (0 <= local_trace < self._data.shape[0]):
            return path
        ntr, ns = self._data.shape
        trace_spacing = plot.width() / max(1, ntr)
        amp_scale = self._amp_scale or 1.0
        x_scale = 0.42 * trace_spacing / max(amp_scale, 1e-12)
        sample_step = max(1, int(math.ceil(ns / max(110.0, plot.height() * 2.4))))
        indices = np.arange(0, ns, sample_step, dtype=int)
        if indices.size == 0 or indices[-1] != ns - 1:
            indices = np.append(indices, ns - 1)
        x0 = self._trace_x(local_trace)
        first = True
        values = np.asarray(self._data[local_trace], dtype=np.float64)
        for idx in indices:
            value = values[idx]
            if not np.isfinite(value):
                first = True
                continue
            point = QPointF(x0 + float(value) * x_scale, self._sample_y(int(idx)))
            if first:
                path.moveTo(point)
                first = False
            else:
                path.lineTo(point)
        return path

    def _draw_hover_trace(self, painter: QPainter, plot: QRectF) -> None:
        if self._last_info is None:
            return
        local_trace = int(self._last_info.get("local_trace", -1))
        if not (0 <= local_trace < self._data.shape[0]):
            return
        status_color = QColor(*self._last_info.get("status_color", (30, 120, 190)))
        painter.save()
        painter.setClipRect(plot.adjusted(1, 1, -1, -1))
        pen = QPen(status_color, 2.25)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawPath(self._build_trace_path(local_trace, plot))
        painter.restore()

    def _draw_crosshair(self, painter: QPainter, plot: QRectF) -> None:
        if self._cursor_display is None or self._last_info is None or not plot.contains(self._cursor_display):
            return
        status_color = QColor(*self._last_info.get("status_color", (210, 40, 40)))
        pen = QPen(status_color, 1.35, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawLine(QPointF(plot.left(), self._cursor_display.y()), QPointF(plot.right(), self._cursor_display.y()))
        painter.drawLine(QPointF(self._cursor_display.x(), plot.top()), QPointF(self._cursor_display.x(), plot.bottom()))

        # Small status-only badge; numeric values are shown in the side table.
        status = str(self._last_info.get("status", "Normal"))
        badge = QRectF(plot.left() + 7, plot.top() + 6, 112, 18)
        painter.fillRect(badge, QColor(status_color.red(), status_color.green(), status_color.blue(), 230))
        painter.setPen(QPen(QColor(255, 255, 255), 1))
        font = QFont(painter.font())
        font.setPointSizeF(7.2)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(badge.adjusted(5, 0, -5, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, status[:18])
