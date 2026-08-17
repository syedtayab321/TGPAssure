from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QLinearGradient, QBrush
from PySide6.QtWidgets import QWidget

from modules.uphole import UpholeShot


class LegacyUpholePlot(QWidget):
    """Custom painter that mimics the old UYH/PowerBASIC uphole display."""

    pick_made = Signal(float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.records: list[UpholeShot] = []
        self.current_index = 0
        self.current_file = ""
        self.display_mode = "va_plus"
        self.grad_fill = False
        self.wig_color = QColor("#000000")
        self.va_color = QColor("#000000")
        self.pick_color = QColor("#003cff")
        self.time_window_ms = 500.0
        self.amplitude_scale = 1.0
        self.pick_mode = False
        self.setMinimumSize(460, 280)
        self.setMouseTracking(True)

    def set_records(self, records: list[UpholeShot], current_path: str = "") -> None:
        self.records = records or []
        self.current_index = min(max(self.current_index, 0), max(len(self.records) - 1, 0))
        self.current_file = current_path
        self.update()

    def set_current_index(self, index: int) -> None:
        if not self.records:
            self.current_index = 0
        else:
            self.current_index = max(0, min(index, len(self.records) - 1))
        self.update()

    def current_record(self) -> UpholeShot | None:
        if not self.records:
            return None
        return self.records[self.current_index]

    def zoom_horizontal(self, factor: float) -> None:
        self.amplitude_scale = max(0.25, min(8.0, self.amplitude_scale * factor))
        self.update()

    def zoom_vertical(self, factor: float) -> None:
        self.time_window_ms = max(50.0, min(2000.0, self.time_window_ms * factor))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#ffffff"))

        left = 50
        top = 38
        right = self.width() - 14
        bottom = self.height() - 14
        if right <= left + 50 or bottom <= top + 50:
            return
        frame = QRectF(left, top, right - left, bottom - top)
        painter.setPen(QPen(QColor("#222222"), 1.3))
        painter.drawRect(frame)

        self._draw_header(painter, frame)
        self._draw_grid(painter, frame)
        self._draw_trace(painter, frame)

    def _draw_header(self, painter: QPainter, frame: QRectF) -> None:
        painter.setFont(QFont("Segoe UI", 6))
        painter.setPen(QPen(QColor("#000000")))
        current = self.current_file
        rec = self.current_record()
        if rec is not None and (not current or Path(current).is_dir()):
            current = rec.file_name
        painter.drawText(14, 20, f"File : {current}" if current else "File :")
        painter.setPen(QPen(QColor("#ff0000")))
        painter.drawText(int(frame.left()) - 48, int(frame.top()) - 10, "Channel")
        # Modernized TGPAssure header; legacy third-party email text removed.
        painter.setFont(QFont("Segoe UI", 6, QFont.Bold))
        painter.drawText(int(frame.right()) - 190, 20, "TGPAssure Uphole")
        rec = self.current_record()
        channel = rec.channel if rec and rec.channel is not None else 1
        axis_x = self._trace_axis_x(frame)
        painter.drawText(int(axis_x) - 3, int(frame.top()) - 10, str(channel))

    def _draw_grid(self, painter: QPainter, frame: QRectF) -> None:
        grid_pen = QPen(QColor("#ff7a7a"), 1, Qt.DotLine)
        label_pen = QPen(QColor("#003cff"))
        painter.setFont(QFont("Segoe UI", 6))
        interval = 50.0
        n = int(self.time_window_ms // interval)
        for i in range(1, n + 1):
            t = i * interval
            y = frame.top() + (t / self.time_window_ms) * frame.height()
            painter.setPen(grid_pen)
            painter.drawLine(QPointF(frame.left(), y), QPointF(frame.right(), y))
            painter.setPen(label_pen)
            painter.drawText(int(frame.left()) - 48, int(y) + 3, f"{int(t)} mS")

    def _draw_trace(self, painter: QPainter, frame: QRectF) -> None:
        rec = self.current_record()
        axis_x = self._trace_axis_x(frame)
        painter.setPen(QPen(QColor("#111111"), 1.2))
        painter.drawLine(QPointF(axis_x, frame.top()), QPointF(axis_x, frame.bottom()))
        if rec is None:
            return
        pick_ms = rec.pick_ms if rec.pick_ms is not None else self._default_pick_ms(rec)
        y_pick = frame.top() + (pick_ms / self.time_window_ms) * frame.height()
        samples = max(min(rec.samples or 700, 1800), 240)
        dt = self.time_window_ms / samples
        amp_px = 34.0 * self.amplitude_scale
        if rec.depth_m is not None:
            amp_px *= max(0.75, min(1.8, rec.depth_m / 20.0))
        points: list[tuple[float, float, float]] = []
        path = QPainterPath()
        first = True
        for i in range(samples):
            t = i * dt
            if t < pick_ms - 10 or t > pick_ms + 38:
                amp = 0.0
            else:
                x = (t - pick_ms) / 5.5
                envelope = math.exp(-0.5 * ((t - pick_ms - 10.0) / 12.0) ** 2)
                amp = math.sin(2.0 * math.pi * x) * envelope
            xpix = axis_x + amp * amp_px
            ypix = frame.top() + (t / self.time_window_ms) * frame.height()
            points.append((xpix, ypix, amp))
            if first:
                path.moveTo(xpix, ypix)
                first = False
            else:
                path.lineTo(xpix, ypix)

        if self.display_mode.startswith("va"):
            self._paint_variable_area_fill(painter, points, axis_x)

        painter.setPen(QPen(self.wig_color, 1.35))
        painter.drawPath(path)
        if rec.pick_ms is not None:
            painter.setPen(QPen(self.pick_color, 2.0))
            painter.drawLine(QPointF(axis_x - 115, y_pick), QPointF(frame.right(), y_pick))


    def _paint_variable_area_fill(self, painter: QPainter, points: list[tuple[float, float, float]], axis_x: float) -> None:
        """Fill positive/negative lobes correctly. Gradient mode is visibly shaded."""
        if len(points) < 2:
            return
        for (x1, y1, a1), (x2, y2, a2) in zip(points[:-1], points[1:]):
            avg = (a1 + a2) * 0.5
            if avg >= 0 and self.display_mode not in {"va_plus", "va_both"}:
                continue
            if avg < 0 and self.display_mode not in {"va_minus", "va_both"}:
                continue
            if abs(avg) < 1e-6:
                continue

            lobe = QPainterPath()
            lobe.moveTo(axis_x, y1)
            lobe.lineTo(x1, y1)
            lobe.lineTo(x2, y2)
            lobe.lineTo(axis_x, y2)
            lobe.closeSubpath()

            if self.grad_fill:
                grad = QLinearGradient(QPointF(axis_x, y1), QPointF(max(x1, x2) if avg >= 0 else min(x1, x2), y2))
                strong = QColor(self.va_color)
                strong.setAlpha(225)
                soft = QColor(self.va_color)
                soft.setAlpha(35)
                if avg >= 0:
                    grad.setColorAt(0.0, soft)
                    grad.setColorAt(1.0, strong)
                else:
                    grad.setColorAt(0.0, soft)
                    grad.setColorAt(1.0, strong)
                painter.fillPath(lobe, QBrush(grad))
            else:
                fill = QColor(self.va_color)
                fill.setAlpha(210)
                painter.fillPath(lobe, QBrush(fill))

    def _trace_axis_x(self, frame: QRectF) -> float:
        return frame.right() - 78.0

    @staticmethod
    def _default_pick_ms(rec: UpholeShot) -> float:
        if rec.depth_m is not None:
            return max(8.0, min(80.0, rec.depth_m * 1.55 + 12.0))
        return 28.0

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not self.pick_mode or not self.records:
            return super().mousePressEvent(event)
        left = 50
        top = 38
        right = self.width() - 14
        bottom = self.height() - 14
        if not (left <= event.position().x() <= right and top <= event.position().y() <= bottom):
            return
        pick = (event.position().y() - top) / max(bottom - top, 1) * self.time_window_ms
        rec = self.records[self.current_index]
        rec.pick_ms = round(float(pick), 3)
        if rec.channel is None:
            rec.channel = 1
        self.pick_made.emit(rec.pick_ms)
        self.update()
