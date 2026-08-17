from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

from core.visualization.palette_library import DEFAULT_PALETTE, palette_rgb_array


class PaletteColorBar(QWidget):
    """Compact reusable numeric color bar for maps, traces, QC and scalar plots."""

    def __init__(self, parent: Optional[QWidget] = None, *, orientation: Qt.Orientation = Qt.Horizontal) -> None:
        super().__init__(parent)
        self._palette_name = DEFAULT_PALETTE
        self._minimum = 0.0
        self._maximum = 1.0
        self._unit = ""
        self._label = "Value"
        self._orientation = orientation
        if orientation == Qt.Horizontal:
            self.setMinimumHeight(42)
            self.setMaximumHeight(48)
        else:
            self.setMinimumWidth(72)
            self.setMaximumWidth(88)

    def set_state(
        self,
        minimum: float | None,
        maximum: float | None,
        palette_name: str = DEFAULT_PALETTE,
        *,
        unit: str = "",
        label: str = "Value",
    ) -> None:
        if minimum is None or maximum is None or not np.isfinite(minimum) or not np.isfinite(maximum):
            self._minimum, self._maximum = 0.0, 1.0
        else:
            self._minimum = float(minimum)
            self._maximum = float(maximum if maximum > minimum else minimum + 1.0)
        self._palette_name = str(palette_name or DEFAULT_PALETTE)
        self._unit = str(unit or "")
        self._label = str(label or "Value")
        self.update()

    @staticmethod
    def _fmt(value: float, unit: str) -> str:
        av = abs(value)
        if av >= 1e5 or (0 < av < 1e-3):
            text = f"{value:.3e}"
        elif av >= 1000:
            text = f"{value:.2f}"
        else:
            text = f"{value:.4g}"
        return f"{text} {unit}".strip()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), self.palette().window().color())
        if self._orientation == Qt.Vertical:
            self._paint_vertical(painter)
        else:
            self._paint_horizontal(painter)

    def _gradient_image(self, width: int, height: int, *, vertical: bool = False) -> QImage:
        width = max(2, int(width)); height = max(2, int(height))
        if vertical:
            rgb = palette_rgb_array(self._palette_name, height)[::-1]
            rgba = np.concatenate((rgb, np.full((height, 1), 255, dtype=np.uint8)), axis=1)
            rgba = np.repeat(rgba[:, None, :], width, axis=1)
        else:
            rgb = palette_rgb_array(self._palette_name, width)
            rgba = np.concatenate((rgb, np.full((width, 1), 255, dtype=np.uint8)), axis=1)
            rgba = np.repeat(rgba[None, :, :], height, axis=0)
        rgba = np.ascontiguousarray(rgba, dtype=np.uint8)
        return QImage(rgba.data, width, height, width * 4, QImage.Format.Format_RGBA8888).copy()

    def _paint_horizontal(self, painter: QPainter) -> None:
        left = 92.0; right = 92.0
        bar = QRectF(left, 6.0, max(20.0, self.width() - left - right), 16.0)
        image = self._gradient_image(int(bar.width()), int(bar.height()))
        painter.drawImage(bar, image)
        painter.setPen(QPen(QColor("#9AA7B4"), 1))
        painter.drawRect(bar)
        painter.setPen(QColor("#334155"))
        painter.drawText(QRectF(0, 2, left - 6, 24), Qt.AlignRight | Qt.AlignVCenter, self._fmt(self._minimum, self._unit))
        painter.drawText(QRectF(self.width() - right + 6, 2, right - 6, 24), Qt.AlignLeft | Qt.AlignVCenter, self._fmt(self._maximum, self._unit))
        midpoint = (self._minimum + self._maximum) / 2.0
        painter.setPen(QColor("#64748B"))
        painter.drawText(QRectF(left, 23, bar.width(), 18), Qt.AlignCenter, f"{self._label}  •  {self._fmt(midpoint, self._unit)}")

    def _paint_vertical(self, painter: QPainter) -> None:
        bar = QRectF(10.0, 28.0, 18.0, max(40.0, self.height() - 52.0))
        image = self._gradient_image(int(bar.width()), int(bar.height()), vertical=True)
        painter.drawImage(bar, image)
        painter.setPen(QPen(QColor("#9AA7B4"), 1))
        painter.drawRect(bar)
        painter.setPen(QColor("#334155"))
        painter.drawText(QRectF(34, bar.top() - 8, self.width() - 36, 20), Qt.AlignLeft | Qt.AlignVCenter, self._fmt(self._maximum, self._unit))
        painter.drawText(QRectF(34, bar.bottom() - 10, self.width() - 36, 20), Qt.AlignLeft | Qt.AlignVCenter, self._fmt(self._minimum, self._unit))
        painter.save()
        painter.translate(self.width() - 8, self.height() / 2)
        painter.rotate(-90)
        painter.setPen(QColor("#64748B"))
        painter.drawText(QRectF(-self.height() / 2 + 12, -16, self.height() - 24, 16), Qt.AlignCenter, self._label)
        painter.restore()
