from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QBrush, QPolygonF, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QScrollArea,
    QSlider,
    QSplitter,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from modules.geophone_array.models import GeophoneArrayModel, load_gar_file, save_gar_file
from modules.geophone_array.response import calculate_response, frequency_to_velocity, wavenumber_to_frequency
from core.visualization.palette_library import palette_hex
from ui.widgets.color_palette_dialog import PaletteSelectorButton
from ui.widgets.palette_colorbar import PaletteColorBar


STYLE = """
QWidget#arrayResponseDashboard {
    background:#eef4fb;
    color:#172033;
    font-family:Segoe UI, Arial, sans-serif;
    font-size:9.5px;
}
QFrame#topHeader {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #102a43,stop:.55 #0e7490,stop:1 #164e63);
    border:1px solid #0e7490;
    border-radius:12px;
}
QLabel#headerTitle { color:#ffffff; font-size:12px; font-weight:900; letter-spacing:.4px; }
QLabel#headerSubtle { color:#d9f4ff; font-size:8.5px; font-weight:650; }
QFrame#metricTile {
    background:rgba(255,255,255,0.95);
    border:1px solid rgba(226,232,240,0.95);
    border-radius:8px;
}
QLabel#metricCaption { color:#64748b; font-size:8px; font-weight:800; }
QLabel#valueLabel { color:#0369a1; font-size:10px; font-weight:900; }
QGroupBox {
    border:1px solid #c3d0de;
    border-radius:10px;
    margin-top:8px;
    padding:8px;
    font-size:9.5px;
    font-weight:800;
    background:#ffffff;
}
QGroupBox::title { subcontrol-origin: margin; left:10px; padding:0 5px; color:#0f4c81; }
QLabel { font-size:9.5px; }
QPushButton {
    border:1px solid #b6c3d1;
    border-radius:8px;
    padding:5px 9px;
    min-height:24px;
    background:#ffffff;
    color:#182033;
    font-size:9.5px;
    font-weight:800;
}
QPushButton:hover { background:#e0f2fe; border-color:#38bdf8; }
QPushButton#accentButton { background:#0e7490; border-color:#0e7490; color:white; }
QPushButton#blueButton { background:#dbeafe; border-color:#60a5fa; color:#1d4ed8; }
QPushButton#greenButton { background:#dcfce7; border-color:#86efac; color:#166534; }
QPushButton#amberButton { background:#ffedd5; border-color:#fdba74; color:#9a3412; }
QPushButton#redButton { background:#fee2e2; border-color:#fca5a5; color:#991b1b; }
QPushButton#navButton { background:#eef6ff; border-color:#93c5fd; color:#0f4c81; min-width:34px; }
QPushButton#arrayToolButton { border-radius:9px; min-height:30px; padding:4px 8px; font-size:9px; font-weight:900; }
QPushButton#arrayToolButton[role="design"] { background:#0f766e; border-color:#0d9488; color:#ffffff; }
QPushButton#arrayToolButton[role="response"] { background:#2563eb; border-color:#1d4ed8; color:#ffffff; }
QPushButton#arrayToolButton[role="print"] { background:#f59e0b; border-color:#d97706; color:#1f2937; }
QPushButton#arrayToolButton[role="close"] { background:#dc2626; border-color:#b91c1c; color:#ffffff; }
QTabWidget::pane { border:1px solid #cbd5e1; border-radius:9px; background:#ffffff; }
QTabBar::tab { background:#eaf0f7; border:1px solid #c6d3e2; padding:5px 8px; font-size:8.5px; font-weight:800; min-height:18px; }
QTabBar::tab:selected { background:#0e7490; color:#ffffff; border-color:#0e7490; }
QTabBar::tab:hover { background:#d8ecfa; }
QDoubleSpinBox, QSpinBox, QComboBox, QLineEdit {
    background:#ffffff;
    border:1px solid #b8c6d8;
    border-radius:7px;
    min-height:23px;
    padding:2px 5px;
    font-size:9.5px;
}
QDoubleSpinBox:focus, QSpinBox:focus { border-color:#0ea5e9; background:#f8fcff; }
QRadioButton, QCheckBox { spacing:5px; font-size:9px; color:#223044; }
QFrame#plotCard, QFrame#designCard, QFrame#leftPanel {
    background:#ffffff;
    border:1px solid #cbd5e1;
    border-radius:12px;
}
QLabel#statusLabel {
    background:#ffffff;
    border:1px solid #d6dee8;
    border-radius:8px;
    padding:6px 10px;
    color:#334155;
    font-size:9.5px;
    font-weight:650;
}
"""


class ArrayDesignCanvas(QWidget):
    changed = Signal()
    cursorChanged = Signal(float, float)
    pointDetailsRequested = Signal(object)

    def __init__(self, model: GeophoneArrayModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = model
        self.grid_x = 5.0
        self.grid_y = 5.0
        self.nudge_x = 0.0
        self.nudge_y = 0.0
        self.snap = False
        self.show_grid = True
        self.setMouseTracking(True)
        self.cursor_x = 0.0
        self.cursor_y = 0.0
        self.cursor_visible = False
        self.setMinimumSize(320, 250)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def _plot_rect(self) -> QRectF:
        return QRectF(48, 28, max(120, self.width() - 74), max(120, self.height() - 68))

    def _to_screen(self, x: float, y: float) -> QPoint:
        r = self._plot_rect()
        sx = r.left() + (x / max(self.model.x_size, 1.0)) * r.width()
        sy = r.bottom() - (y / max(self.model.y_size, 1.0)) * r.height()
        return QPoint(round(sx), round(sy))

    def _from_screen(self, pos: QPoint) -> tuple[float, float]:
        r = self._plot_rect()
        x = (pos.x() - r.left()) / max(r.width(), 1.0) * self.model.x_size
        y = (r.bottom() - pos.y()) / max(r.height(), 1.0) * self.model.y_size
        x = max(0.0, min(self.model.x_size, x))
        y = max(0.0, min(self.model.y_size, y))
        if self.snap:
            gx = self.grid_x if self.grid_x > 0 else 1.0
            gy = self.grid_y if self.grid_y > 0 else 1.0
            x = round((x - self.nudge_x) / gx) * gx + self.nudge_x
            y = round((y - self.nudge_y) / gy) * gy + self.nudge_y
            x = max(0.0, min(self.model.x_size, x))
            y = max(0.0, min(self.model.y_size, y))
        return x, y

    def _nearest_design_point(self, pos: QPoint, tolerance_px: float = 10.0) -> dict | None:
        if not self.model.points:
            return None
        best_index = -1
        best_distance = float("inf")
        best_screen = None
        for index, point in enumerate(self.model.points, start=1):
            screen = self._to_screen(point.x, point.y)
            distance = math.hypot(screen.x() - pos.x(), screen.y() - pos.y())
            if distance < best_distance:
                best_index = index
                best_distance = distance
                best_screen = screen
        if best_index > 0 and best_distance <= tolerance_px:
            point = self.model.points[best_index - 1]
            return {
                "kind": "Array Element",
                "element": best_index,
                "x": float(point.x),
                "y": float(point.y),
                "screen_x": best_screen.x() if best_screen is not None else pos.x(),
                "screen_y": best_screen.y() if best_screen is not None else pos.y(),
                "distance_px": best_distance,
                "elements": int(self.model.elements),
                "x_size": float(self.model.x_size),
                "y_size": float(self.model.y_size),
            }
        return None

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor("#0b1220"))
        r = self._plot_rect()
        p.setPen(QPen(QColor("#e2e8f0"), 1.4))
        p.drawRect(r)
        font = QFont(self.font())
        font.setPointSize(7)
        p.setFont(font)
        if self.show_grid:
            p.setPen(QPen(QColor("#1e3a8a"), 0.7))
            gx = self.grid_x if self.grid_x > 0 else max(self.model.x_size / 5.0, 1.0)
            gy = self.grid_y if self.grid_y > 0 else max(self.model.y_size / 5.0, 1.0)
            x = self.nudge_x
            while x <= self.model.x_size + 1e-6:
                pt = self._to_screen(x, 0)
                p.drawLine(pt.x(), round(r.top()), pt.x(), round(r.bottom()))
                x += gx
            y = self.nudge_y
            while y <= self.model.y_size + 1e-6:
                pt = self._to_screen(0, y)
                p.drawLine(round(r.left()), pt.y(), round(r.right()), pt.y())
                y += gy
        p.setPen(QPen(QColor("#38bdf8"), 1.2))
        p.drawLine(round(r.left()), round(r.bottom()), round(r.right()), round(r.bottom()))
        p.drawLine(round(r.left()), round(r.top()), round(r.left()), round(r.bottom()))
        p.setPen(QPen(QColor("#94a3b8"), 1))
        tick_count = 10
        for i in range(tick_count + 1):
            xval = i * self.model.x_size / tick_count
            pt = self._to_screen(xval, 0)
            p.drawLine(pt.x(), round(r.bottom()), pt.x(), round(r.bottom()) + 6)
            p.drawText(pt.x() - 16, round(r.bottom()) + 22, f"{xval:.1f}")
            yval = i * self.model.y_size / tick_count
            py = self._to_screen(0, yval).y()
            p.drawLine(round(r.left()) - 6, py, round(r.left()), py)
            p.drawText(round(r.left()) - 52, py + 4, f"{yval:.1f}")
        p.setPen(QPen(QColor("#94a3b8"), 1))
        p.drawLine(round(r.left() + r.width() * 0.35), round(r.top()), round(r.left() + r.width() * 0.35), round(r.bottom()))
        p.drawLine(round(r.left()), round(r.bottom() - r.height() * 0.64), round(r.right()), round(r.bottom() - r.height() * 0.64))
        p.setPen(QPen(QColor("#FF0000"), 1))
        p.drawText(round(r.left() + r.width() * 0.18), round(r.top() - 12), "TGP Geophone Array Design")
        if self.cursor_visible:
            cpt = self._to_screen(self.cursor_x, self.cursor_y)
            p.setPen(QPen(QColor("#00E5FF"), 1.2, Qt.PenStyle.DashLine))
            p.drawLine(cpt.x(), round(r.top()), cpt.x(), round(r.bottom()))
            p.drawLine(round(r.left()), cpt.y(), round(r.right()), cpt.y())
            p.setPen(QPen(QColor("#00E5FF"), 1))
            p.drawText(cpt.x() + 6, max(round(r.top()) + 12, cpt.y() - 6), f"X {self.cursor_x:.2f}  Y {self.cursor_y:.2f}")
        for point in self.model.points:
            pt = self._to_screen(point.x, point.y)
            p.setBrush(QBrush(QColor("#13FF44")))
            p.setPen(QPen(QColor("#FFD400"), 1.2))
            p.drawEllipse(pt, 4, 4)
            p.setPen(QPen(QColor("#00AEEF"), 1))
            p.drawLine(pt.x() - 6, pt.y(), pt.x() + 6, pt.y())
            p.drawLine(pt.x(), pt.y() - 6, pt.x(), pt.y() + 6)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = event.position().toPoint()
        nearest = self._nearest_design_point(pos)
        if nearest is not None:
            x = float(nearest["x"])
            y = float(nearest["y"])
            self.setToolTip(f"Element {nearest['element']}\nX: {x:.3f}\nY: {y:.3f}")
        else:
            x, y = self._from_screen(pos)
            self.setToolTip(f"X: {x:.3f}\nY: {y:.3f}")
        self.cursor_x = x
        self.cursor_y = y
        self.cursor_visible = True
        self.cursorChanged.emit(x, y)
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.cursor_visible = False
        self.setToolTip("")
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = event.position().toPoint()
        x, y = self._from_screen(pos)
        nearest = self._nearest_design_point(pos, tolerance_px=12.0)
        if event.button() == Qt.MouseButton.RightButton:
            if self.model.remove_nearest(x, y, tolerance=max(self.grid_x, self.grid_y, 1.0) * 0.45):
                self.changed.emit(); self.update()
        elif event.button() == Qt.MouseButton.LeftButton:
            if nearest is not None:
                self.pointDetailsRequested.emit(nearest)
            else:
                self.model.add_point(x, y)
                self.changed.emit(); self.update()


class ResponseCanvas(QWidget):
    cursorChanged = Signal(float, float)
    pointDetailsRequested = Signal(object)

    def __init__(self, model: GeophoneArrayModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = model
        self.azimuth = 0.0
        self.cursor_x = 0.0
        self.cursor_y = 0.0
        self.cursor_mode = "wavenumber"
        self.velocity = 355.0
        self.frequency = 60.0
        self.palette_name = "Seismic"
        self._hover_sample: dict | None = None
        self._last_curve = None
        self.setMouseTracking(True)
        self.setMinimumSize(360, 260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def _plot_rect(self) -> QRectF:
        return QRectF(56, 44, max(160, self.width() - 86), max(150, self.height() - 86))

    def _response_curve(self):
        self._last_curve = calculate_response(self.model, self.azimuth, max_ratio=11.0, samples=700)
        return self._last_curve

    def _to_screen(self, x_value: float, y_value: float) -> QPoint:
        r = self._plot_rect()
        sx = r.left() + max(0.0, min(11.0, float(x_value))) / 11.0 * r.width()
        sy = r.bottom() - max(0.0, min(1.0, float(y_value))) * r.height()
        return QPoint(round(sx), round(sy))

    def _from_screen(self, pos: QPoint) -> tuple[float, float]:
        r = self._plot_rect()
        x_value = (pos.x() - r.left()) / max(r.width(), 1.0) * 11.0
        y_value = (r.bottom() - pos.y()) / max(r.height(), 1.0)
        return max(0.0, min(11.0, x_value)), max(0.0, min(1.0, y_value))

    def _nearest_response_sample(self, pos: QPoint, tolerance_px: float = 14.0) -> dict | None:
        curve = self._response_curve()
        if not curve.x_values:
            return None
        best_index = -1
        best_distance = float("inf")
        for index, (x_value, y_value) in enumerate(zip(curve.x_values, curve.y_values), start=1):
            screen = self._to_screen(x_value, y_value)
            distance = math.hypot(screen.x() - pos.x(), screen.y() - pos.y())
            if distance < best_distance:
                best_index = index
                best_distance = distance
        if best_index < 1 or best_distance > tolerance_px:
            return None
        x_value = float(curve.x_values[best_index - 1])
        y_value = float(curve.y_values[best_index - 1])
        projected_length = float(curve.projected_length)
        return {
            "kind": "Array Response Sample",
            "sample": best_index,
            "samples": len(curve.x_values),
            "ratio": x_value,
            "response": y_value,
            "azimuth": float(self.azimuth),
            "projected_length": projected_length,
            "frequency": wavenumber_to_frequency(x_value, float(self.velocity), max(projected_length, 1.0)),
            "velocity": frequency_to_velocity(x_value, float(self.frequency), max(projected_length, 1.0)),
            "reference_velocity": float(self.velocity),
            "reference_frequency": float(self.frequency),
            "elements": int(self.model.elements),
            "distance_px": best_distance,
        }

    def _tooltip_text(self, details: dict) -> str:
        if details.get("kind") == "Array Response Sample":
            return (
                f"Sample: {details['sample']} / {details['samples']}\n"
                f"Ratio: {details['ratio']:.4f}\n"
                f"Response: {details['response']:.4f}\n"
                f"Azimuth: {details['azimuth']:.1f}°\n"
                f"Length: {details['projected_length']:.3f}\n"
                f"Freq @ {details['reference_velocity']:.0f} m/s: {details['frequency']:.3f} Hz\n"
                f"Vel @ {details['reference_frequency']:.1f} Hz: {details['velocity']:.3f} m/s"
            )
        return ""

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor("#FFFFFF"))
        r = self._plot_rect()
        p.setPen(QPen(QColor("#303030"), 1.4))
        p.drawRect(r)
        p.setPen(QPen(QColor("#DFDFDF"), 1))
        for i in range(12):
            x = r.left() + i * r.width() / 11.0
            p.drawLine(round(x), round(r.top()), round(x), round(r.bottom()))
        for i in range(11):
            y = r.bottom() - i * r.height() / 10.0
            p.drawLine(round(r.left()), round(y), round(r.right()), round(y))
        p.setPen(QPen(QColor("#1C37FF"), 1.2))
        font = QFont(self.font()); font.setPointSize(7); p.setFont(font)
        for i in range(12):
            xval = i
            sx = r.left() + xval / 11.0 * r.width()
            p.drawText(round(sx) - 5, round(r.bottom()) + 20, str(xval))
        for i in range(11):
            yval = i / 10.0
            sy = r.bottom() - yval * r.height()
            p.drawText(round(r.left()) - 30, round(sy) + 3, f"{yval:.1f}")
        curve = self._response_curve()
        if curve.x_values:
            last = None
            values = curve.y_values
            lo = min(values) if values else 0.0
            hi = max(values) if values else 1.0
            span = max(hi - lo, 1e-12)
            for xval, yval in zip(curve.x_values, curve.y_values):
                sx = r.left() + xval / 11.0 * r.width()
                sy = r.bottom() - yval * r.height()
                if last is not None:
                    t = max(0.0, min(1.0, (yval - lo) / span))
                    p.setPen(QPen(QColor(palette_hex(self.palette_name, t)), 1.45))
                    p.drawLine(last[0], last[1], round(sx), round(sy))
                last = (round(sx), round(sy))
        cx = r.left() + max(0.0, min(11.0, self.cursor_x)) / 11.0 * r.width()
        cy = r.bottom() - max(0.0, min(1.0, self.cursor_y)) * r.height()
        p.setPen(QPen(QColor("#ef4444"), 1.2))
        p.drawLine(round(cx), round(r.top()), round(cx), round(r.bottom()))
        p.drawLine(round(r.left()), round(cy), round(r.right()), round(cy))
        p.setBrush(QBrush(QColor("#ef4444")))
        p.drawEllipse(QPoint(round(cx), round(cy)), 3, 3)
        if self._hover_sample is not None:
            sample_pt = self._to_screen(float(self._hover_sample["ratio"]), float(self._hover_sample["response"]))
            p.setBrush(QBrush(QColor("#FDBA74")))
            p.setPen(QPen(QColor("#EA580C"), 1.4))
            p.drawEllipse(sample_pt, 5, 5)
        p.setPen(QPen(QColor("#2563eb"), 1.1))
        p.drawText(round(r.left()), round(r.top()) - 8, f"Cursor X : {self.cursor_x:.2f}   Cursor Y : {self.cursor_y:.2f}")
        p.setPen(QPen(QColor("#1f2937"), 1))
        p.drawText(round(r.left()), 22, f"File : {self.model.file_name}")
        p.drawText(round(r.left() + r.width() * 0.43), 22, f"Elements : {self.model.elements}")
        p.drawText(round(r.left() + r.width() * 0.78), 22, f"Azimuth : {self.azimuth:.1f} Deg")
        if self.cursor_mode == "freq_velocity":
            p.drawText(round(r.left() + r.width() * 0.43), 38, f"Freq(V={self.velocity:.0f}) : {wavenumber_to_frequency(self.cursor_x, self.velocity, max(curve.projected_length,1)):.2f} Hz")
        elif self.cursor_mode == "velocity_frequency":
            p.drawText(round(r.left() + r.width() * 0.43), 38, f"Vel(F={self.frequency:.0f}) : {frequency_to_velocity(self.cursor_x, self.frequency, max(curve.projected_length,1)):.2f} m/s")
        p.drawText(round(r.left() + r.width() * 0.78), 38, f"Length : {curve.projected_length:.2f}")
        p.drawText(round(r.center().x()) - 76, round(r.bottom()) + 28, "Array Length/Wavelength")
        p.setPen(QPen(QColor("#0e7490"), 1))
        p.drawText(round(r.right()) - 170, round(r.bottom()) + 48, "TGP Geophone Array Analysis")

    def set_palette(self, palette_name: str) -> None:
        self.palette_name = str(palette_name or "Seismic")
        self.update()

    def _update_cursor_from_pos(self, pos: QPoint, snap_to_curve: bool = True) -> dict | None:
        details = self._nearest_response_sample(pos) if snap_to_curve else None
        if details is not None:
            self.cursor_x = float(details["ratio"])
            self.cursor_y = float(details["response"])
            self._hover_sample = details
            self.setToolTip(self._tooltip_text(details))
        else:
            self.cursor_x, self.cursor_y = self._from_screen(pos)
            self._hover_sample = None
            self.setToolTip(f"Ratio: {self.cursor_x:.4f}\nResponse: {self.cursor_y:.4f}")
        self.cursorChanged.emit(self.cursor_x, self.cursor_y)
        self.update()
        return details

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._update_cursor_from_pos(event.position().toPoint(), snap_to_curve=True)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover_sample = None
        self.setToolTip("")
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        details = self._update_cursor_from_pos(event.position().toPoint(), snap_to_curve=True)
        if event.button() == Qt.MouseButton.LeftButton:
            if details is None:
                details = self._nearest_response_sample(event.position().toPoint(), tolerance_px=22.0)
            if details is not None:
                self.pointDetailsRequested.emit(details)


class ArrayMapPreview(QWidget):
    def __init__(self, model: GeophoneArrayModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = model
        self.azimuth = 0.0
        self.setMinimumSize(118, 118); self.setMaximumHeight(150)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor("#0b1220"))
        cx, cy = self.width() / 2, self.height() / 2
        rad = min(self.width(), self.height()) * 0.42
        p.setPen(QPen(QColor("#38bdf8"), 1))
        p.drawEllipse(QPoint(round(cx), round(cy)), round(rad), round(rad))
        p.drawEllipse(QPoint(round(cx), round(cy)), round(rad * 0.72), round(rad * 0.72))
        rect_size = rad * 1.05
        p.setPen(QPen(QColor("#777777"), 1))
        p.drawRect(QRectF(cx - rect_size/2, cy - rect_size/2, rect_size, rect_size))
        p.setPen(QPen(QColor("#22c55e"), 2))
        for pt in self.model.points:
            sx = cx - rect_size/2 + (pt.x / max(self.model.x_size, 1.0)) * rect_size
            sy = cy + rect_size/2 - (pt.y / max(self.model.y_size, 1.0)) * rect_size
            p.drawPoint(round(sx), round(sy))
        angle = math.radians(self.azimuth)
        tip = QPoint(round(cx + math.cos(angle) * rad), round(cy - math.sin(angle) * rad))
        left = QPoint(round(cx + math.cos(angle + 2.7) * 12), round(cy - math.sin(angle + 2.7) * 12))
        right = QPoint(round(cx + math.cos(angle - 2.7) * 12), round(cy - math.sin(angle - 2.7) * 12))
        p.setBrush(QBrush(QColor("#FFFFFF")))
        p.setPen(QPen(QColor("#FFFFFF"), 1))
        p.drawPolygon(QPolygonF([tip, left, right]))


class ArrayResponseDashboard(QWidget):
    """GAR-style Geophone Array Analysis workspace with modern Qt panels."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("arrayResponseDashboard")
        self.setProperty("module_id", "array_response")
        self.model = GeophoneArrayModel()
        self.current_path: Path | None = None
        self._palette_name = "Seismic"
        self._build_ui()
        self._wire()
        self._reset_to_blank_dashboard()
        self._apply_compact_widgets()
        self.setStyleSheet(STYLE)


    def _metric_tile(self, caption: str, widget: QWidget) -> QFrame:
        tile = QFrame(self)
        tile.setObjectName("metricTile")
        layout = QVBoxLayout(tile)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(2)
        label = QLabel(caption)
        label.setObjectName("metricCaption")
        layout.addWidget(label)
        layout.addWidget(widget)
        return tile

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        self.header = QFrame()
        self.header.setObjectName("topHeader")
        hg = QGridLayout(self.header); hg.setContentsMargins(12, 8, 12, 8); hg.setHorizontalSpacing(10); hg.setVerticalSpacing(4)
        title = QLabel("Geophone Array Response")
        title.setObjectName("headerTitle")
        subtitle = QLabel("Interactive design, azimuth response and field-array QC")
        subtitle.setObjectName("headerSubtle")
        self.file_label = QLabel("Untitled.GAR"); self.file_label.setObjectName("valueLabel")
        self.elem_label = QLabel("0"); self.elem_label.setObjectName("valueLabel")
        self.x_size = QDoubleSpinBox(); self.x_size.setRange(1, 10000); self.x_size.setValue(25); self.x_size.setDecimals(2)
        self.y_size = QDoubleSpinBox(); self.y_size.setRange(1, 10000); self.y_size.setValue(25); self.y_size.setDecimals(2)
        hg.addWidget(title, 0, 0, 1, 2)
        hg.addWidget(subtitle, 1, 0, 1, 2)
        hg.addWidget(self._metric_tile("File Name", self.file_label), 0, 2, 2, 2)
        hg.addWidget(self._metric_tile("Elements", self.elem_label), 0, 4, 2, 1)
        hg.addWidget(self._metric_tile("X Size", self.x_size), 0, 5, 2, 1)
        hg.addWidget(self._metric_tile("Y Size", self.y_size), 0, 6, 2, 1)
        hg.setColumnStretch(2, 1)
        root.addWidget(self.header)

        body = QSplitter(Qt.Orientation.Horizontal, self)
        body.setChildrenCollapsible(False)
        root.addWidget(body, 1)
        self.left = QFrame(); self.left.setObjectName("leftPanel"); self.left.setMinimumWidth(210); self.left.setMaximumWidth(320)
        left_l = QVBoxLayout(self.left); left_l.setContentsMargins(5, 5, 5, 5); left_l.setSpacing(5)
        self.preview = ArrayMapPreview(self.model)
        left_l.addWidget(self.preview)

        self.control_tabs = QTabWidget()
        self.control_tabs.setTabPosition(QTabWidget.TabPosition.North)
        left_l.addWidget(self.control_tabs, 1)

        view_tab = QWidget(); view_l = QVBoxLayout(view_tab); view_l.setContentsMargins(6, 6, 6, 6); view_l.setSpacing(5)
        self.azimuth_label = QLabel("0"); self.azimuth_label.setAlignment(Qt.AlignmentFlag.AlignCenter); self.azimuth_label.setObjectName("valueLabel")
        self.azimuth_slider = QSlider(Qt.Orientation.Horizontal); self.azimuth_slider.setRange(0, 180); self.azimuth_slider.setValue(0)
        view_l.addWidget(QLabel("Azimuth")); view_l.addWidget(self.azimuth_label); view_l.addWidget(self.azimuth_slider)
        view_l.addWidget(QLabel("Response Palette"))
        self.palette_selector = PaletteSelectorButton(self._palette_name, view_tab)
        view_l.addWidget(self.palette_selector)
        tool_grid = QGridLayout()
        tool_grid.setContentsMargins(0, 3, 0, 0)
        tool_grid.setHorizontalSpacing(5)
        tool_grid.setVerticalSpacing(5)
        self.array_design_btn = QPushButton("Design"); self.array_design_btn.setObjectName("arrayToolButton"); self.array_design_btn.setProperty("role", "design")
        self.response_btn = QPushButton("Resp"); self.response_btn.setObjectName("arrayToolButton"); self.response_btn.setProperty("role", "response")
        self.print_btn = QPushButton("Print"); self.print_btn.setObjectName("arrayToolButton"); self.print_btn.setProperty("role", "print")
        self.end_btn = QPushButton("End"); self.end_btn.setObjectName("arrayToolButton"); self.end_btn.setProperty("role", "close")
        for btn, tip, row, col in (
            (self.array_design_btn, "Open the editable array design canvas", 0, 0),
            (self.response_btn, "Show the normalized array response plot", 0, 1),
            (self.print_btn, "Prepare the current array response view for print/export", 1, 0),
            (self.end_btn, "Close the Geophone Array Response workspace", 1, 1),
        ):
            btn.setToolTip(tip)
            btn.setMinimumWidth(58)
            btn.setMaximumWidth(86)
            tool_grid.addWidget(btn, row, col)
        view_l.addLayout(tool_grid)
        view_l.addStretch(1)
        self.control_tabs.addTab(view_tab, "View")

        cursor_tab = QWidget(); ml = QVBoxLayout(cursor_tab); ml.setContentsMargins(6, 6, 6, 6); ml.setSpacing(5)
        self.rb_wavenumber = QRadioButton("Wavenumber"); self.rb_wavenumber.setChecked(True)
        self.rb_freq_velocity = QRadioButton("Frequency at velocity")
        self.rb_velocity_freq = QRadioButton("Velocity at frequency")
        self.velocity_spin = QDoubleSpinBox(); self.velocity_spin.setRange(1, 10000); self.velocity_spin.setValue(355); self.velocity_spin.setSuffix(" m/s")
        self.freq_spin = QDoubleSpinBox(); self.freq_spin.setRange(0.1, 1000); self.freq_spin.setValue(60); self.freq_spin.setSuffix(" Hz")
        ml.addWidget(self.rb_wavenumber)
        ml.addWidget(self.rb_freq_velocity); ml.addWidget(QLabel("Velocity")); ml.addWidget(self.velocity_spin)
        ml.addWidget(self.rb_velocity_freq); ml.addWidget(QLabel("Frequency")); ml.addWidget(self.freq_spin)
        ml.addStretch(1)
        self.control_tabs.addTab(cursor_tab, "Cursor")

        file_tab = QWidget(); fl = QVBoxLayout(file_tab); fl.setContentsMargins(6, 6, 6, 6); fl.setSpacing(5)
        self.open_btn = QPushButton("Open File"); self.open_btn.setObjectName("greenButton")
        self.save_btn = QPushButton("Save File"); self.save_btn.setObjectName("blueButton")
        self.new_btn = QPushButton("New Sample"); self.new_btn.setObjectName("amberButton")
        self.close_btn = QPushButton("Clear"); self.close_btn.setObjectName("redButton")
        self.end2_btn = QPushButton("End"); self.end2_btn.setObjectName("redButton")
        for b in (self.open_btn, self.save_btn, self.new_btn, self.close_btn, self.end2_btn):
            fl.addWidget(b)
        fl.addStretch(1)
        self.control_tabs.addTab(file_tab, "File")

        body.addWidget(self.left)

        self.stack = QStackedWidget()
        self.response_card = QFrame(); self.response_card.setObjectName("plotCard")
        rc_l = QVBoxLayout(self.response_card)
        self.response_canvas = ResponseCanvas(self.model)
        self.response_canvas.set_palette(self._palette_name)
        rc_l.addWidget(self.response_canvas, 1)
        self.response_colorbar = PaletteColorBar(self.response_card)
        self.response_colorbar.set_state(0.0, 1.0, self._palette_name, unit="", label="Normalized array response")
        rc_l.addWidget(self.response_colorbar)
        response_footer = QHBoxLayout()
        response_footer.addStretch(1); response_footer.addWidget(QLabel("CTRL P To Print")); response_footer.addStretch(1)
        self.prev_btn = QPushButton("◀"); self.next_btn = QPushButton("▶"); self.prev_btn.setObjectName("navButton"); self.next_btn.setObjectName("navButton"); self.prev_btn.setMaximumWidth(42); self.next_btn.setMaximumWidth(42)
        response_footer.addWidget(self.prev_btn); response_footer.addWidget(self.next_btn)
        rc_l.addLayout(response_footer)
        self.design_card = QFrame(); self.design_card.setObjectName("designCard")
        self._build_design_card()
        self.stack.addWidget(self.response_card); self.stack.addWidget(self.design_card)
        body.addWidget(self.stack)
        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        body.setSizes([260, 980])
        self.status = QLabel("Ready. New array design created."); self.status.setObjectName("statusLabel")
        root.addWidget(self.status)

    def _build_design_card(self) -> None:
        row = QHBoxLayout(self.design_card); row.setContentsMargins(6, 6, 6, 6); row.setSpacing(7)
        controls_widget = QWidget()
        controls_widget.setMinimumWidth(175)
        controls_widget.setMaximumWidth(215)
        controls = QVBoxLayout(controls_widget); controls.setContentsMargins(0, 0, 0, 0); controls.setSpacing(5)

        self.design_tabs = QTabWidget()
        self.design_tabs.setTabPosition(QTabWidget.TabPosition.North)
        controls.addWidget(self.design_tabs)

        dims_tab = QWidget(); dl = QGridLayout(dims_tab); dl.setContentsMargins(6, 6, 6, 6); dl.setHorizontalSpacing(5); dl.setVerticalSpacing(4)
        self.design_x = QDoubleSpinBox(); self.design_x.setRange(1, 10000); self.design_x.setValue(25); self.design_x.setDecimals(2)
        self.design_y = QDoubleSpinBox(); self.design_y.setRange(1, 10000); self.design_y.setValue(25); self.design_y.setDecimals(2)
        self.dim_set_btn = QPushButton("Set Size"); self.dim_set_btn.setObjectName("blueButton")
        self.design_elements = QLabel("0"); self.design_elements.setObjectName("valueLabel")
        dl.addWidget(QLabel("X size"), 0, 0); dl.addWidget(self.design_x, 0, 1)
        dl.addWidget(QLabel("Y size"), 1, 0); dl.addWidget(self.design_y, 1, 1)
        dl.addWidget(QLabel("Elements"), 2, 0); dl.addWidget(self.design_elements, 2, 1)
        dl.addWidget(self.dim_set_btn, 3, 0, 1, 2)
        dl.setRowStretch(4, 1)
        self.design_tabs.addTab(dims_tab, "Size")

        grid_tab = QWidget(); gl = QGridLayout(grid_tab); gl.setContentsMargins(6, 6, 6, 6); gl.setHorizontalSpacing(5); gl.setVerticalSpacing(4)
        self.grid_x = QDoubleSpinBox(); self.grid_x.setRange(0.1, 1000); self.grid_x.setValue(4); self.grid_x.setDecimals(3)
        self.grid_y = QDoubleSpinBox(); self.grid_y.setRange(0.1, 1000); self.grid_y.setValue(4); self.grid_y.setDecimals(3)
        self.nudge_x = QDoubleSpinBox(); self.nudge_x.setRange(-1000, 1000); self.nudge_x.setValue(0.5); self.nudge_x.setDecimals(3)
        self.nudge_y = QDoubleSpinBox(); self.nudge_y.setRange(-1000, 1000); self.nudge_y.setValue(0); self.nudge_y.setDecimals(3)
        self.snap_cb = QCheckBox("Snap"); self.show_cb = QCheckBox("Show grid"); self.show_cb.setChecked(True)
        self.grid_set_btn = QPushButton("Apply Grid"); self.grid_set_btn.setObjectName("greenButton")
        for r, (label, widget) in enumerate((("Grid X", self.grid_x), ("Grid Y", self.grid_y), ("Nudge X", self.nudge_x), ("Nudge Y", self.nudge_y))):
            gl.addWidget(QLabel(label), r, 0); gl.addWidget(widget, r, 1)
        gl.addWidget(self.snap_cb, 4, 0); gl.addWidget(self.show_cb, 4, 1)
        gl.addWidget(self.grid_set_btn, 5, 0, 1, 2)
        gl.setRowStretch(6, 1)
        self.design_tabs.addTab(grid_tab, "Grid")

        cursor_tab = QWidget(); c_l = QGridLayout(cursor_tab); c_l.setContentsMargins(6, 6, 6, 6); c_l.setHorizontalSpacing(5); c_l.setVerticalSpacing(4)
        self.cursor_x = QLabel("0.00"); self.cursor_y = QLabel("0.00")
        self.cursor_x.setObjectName("valueLabel"); self.cursor_y.setObjectName("valueLabel")
        c_l.addWidget(QLabel("Cursor X"), 0, 0); c_l.addWidget(self.cursor_x, 0, 1)
        c_l.addWidget(QLabel("Cursor Y"), 1, 0); c_l.addWidget(self.cursor_y, 1, 1)
        note = QLabel("Move the mouse over the design canvas. The cyan guide lines now follow the cursor.")
        note.setWordWrap(True)
        c_l.addWidget(note, 2, 0, 1, 2)
        c_l.setRowStretch(3, 1)
        self.design_tabs.addTab(cursor_tab, "Cursor")

        controls.addStretch(1)
        row.addWidget(controls_widget, 0)
        self.design_canvas = ArrayDesignCanvas(self.model)
        row.addWidget(self.design_canvas, 1)


    def _apply_compact_widgets(self) -> None:
        font = QFont(self.font())
        font.setPointSize(7)
        self.setFont(font)
        for cls in (QDoubleSpinBox, QSpinBox):
            for spin in self.findChildren(cls):
                spin.setMaximumWidth(120)
                spin.setMinimumWidth(72)
        for btn in self.findChildren(QPushButton):
            if btn.objectName() == "arrayToolButton":
                btn.setMinimumHeight(28)
                btn.setMaximumHeight(34)
            else:
                btn.setMinimumHeight(22)
                btn.setMaximumHeight(28)
        self.response_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.design_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def _wire(self) -> None:
        self.open_btn.clicked.connect(self.open_file); self.save_btn.clicked.connect(self.save_file); self.new_btn.clicked.connect(self.new_design)
        self.close_btn.clicked.connect(self.clear_design); self.end2_btn.clicked.connect(self.close_workspace)
        self.array_design_btn.clicked.connect(self.show_design); self.response_btn.clicked.connect(self.show_response)
        self.print_btn.clicked.connect(self.print_view); self.end_btn.clicked.connect(self.close_workspace)
        self.dim_set_btn.clicked.connect(self.apply_dimensions); self.grid_set_btn.clicked.connect(self.apply_grid)
        self.x_size.valueChanged.connect(lambda _v: self._sync_sizes_from_header())
        self.y_size.valueChanged.connect(lambda _v: self._sync_sizes_from_header())
        self.azimuth_slider.valueChanged.connect(self.set_azimuth)
        self.palette_selector.currentTextChanged.connect(self._on_palette_changed)
        self.design_canvas.changed.connect(self.refresh_all)
        self.design_canvas.cursorChanged.connect(lambda x, y: (self.cursor_x.setText(f"{x:.2f}"), self.cursor_y.setText(f"{y:.2f}")))
        self.design_canvas.pointDetailsRequested.connect(self._show_point_details)
        self.response_canvas.cursorChanged.connect(lambda x, y: self.status.setText(f"Cursor X: {x:.2f}  Cursor Y: {y:.2f}"))
        self.response_canvas.pointDetailsRequested.connect(self._show_point_details)
        for rb in (self.rb_wavenumber, self.rb_freq_velocity, self.rb_velocity_freq): rb.toggled.connect(self.update_cursor_mode)
        self.velocity_spin.valueChanged.connect(lambda _v: self.response_canvas.update())
        self.freq_spin.valueChanged.connect(lambda _v: self.response_canvas.update())
        self.prev_btn.clicked.connect(lambda: self.set_azimuth(max(0, self.azimuth_slider.value() - 5)))
        self.next_btn.clicked.connect(lambda: self.set_azimuth(min(180, self.azimuth_slider.value() + 5)))

    def _show_point_details(self, details: object) -> None:
        if not isinstance(details, dict):
            return
        kind = str(details.get("kind", "Point"))
        if kind == "Array Element":
            text = (
                f"Element: {details.get('element')} / {details.get('elements')}\n"
                f"X: {float(details.get('x', 0.0)):.4f}\n"
                f"Y: {float(details.get('y', 0.0)):.4f}\n"
                f"X Size: {float(details.get('x_size', self.model.x_size)):.4f}\n"
                f"Y Size: {float(details.get('y_size', self.model.y_size)):.4f}\n"
                f"File: {self.model.file_name}"
            )
        elif kind == "Array Response Sample":
            text = (
                f"Sample: {details.get('sample')} / {details.get('samples')}\n"
                f"Array Length / Wavelength: {float(details.get('ratio', 0.0)):.5f}\n"
                f"Normalized Response: {float(details.get('response', 0.0)):.5f}\n"
                f"Azimuth: {float(details.get('azimuth', 0.0)):.2f}°\n"
                f"Projected Length: {float(details.get('projected_length', 0.0)):.5f}\n"
                f"Elements: {details.get('elements')}\n"
                f"Frequency @ {float(details.get('reference_velocity', 0.0)):.0f} m/s: {float(details.get('frequency', 0.0)):.5f} Hz\n"
                f"Velocity @ {float(details.get('reference_frequency', 0.0)):.1f} Hz: {float(details.get('velocity', 0.0)):.5f} m/s\n"
                f"Palette: {self._palette_name}\n"
                f"File: {self.model.file_name}"
            )
        else:
            text = "\n".join(f"{key}: {value}" for key, value in sorted(details.items()))
        QMessageBox.information(self, f"{kind} Details", text)

    def _sync_sizes_from_header(self) -> None:
        self.model.x_size = float(self.x_size.value()); self.model.y_size = float(self.y_size.value())
        self.design_x.blockSignals(True); self.design_y.blockSignals(True)
        self.design_x.setValue(self.model.x_size); self.design_y.setValue(self.model.y_size)
        self.design_x.blockSignals(False); self.design_y.blockSignals(False)
        self.refresh_all()

    def _reset_to_blank_dashboard(self) -> None:
        self.current_path = None
        self.model.file_name = "No file loaded"
        self.model.x_size = 25.0
        self.model.y_size = 25.0
        self.model.points.clear()
        self.x_size.setValue(25)
        self.y_size.setValue(25)
        self.design_x.setValue(25)
        self.design_y.setValue(25)
        self.apply_grid()
        self.refresh_all()
        self.show_response()
        self.status.setText("Ready. Open a GAR/TXT/CSV file, or use New Sample to create a test array.")

    def refresh_all(self) -> None:
        self.file_label.setText(self.model.file_name)
        self.elem_label.setText(str(self.model.elements)); self.design_elements.setText(str(self.model.elements))
        self.preview.update(); self.response_canvas.update(); self.design_canvas.update()

    def new_design(self) -> None:
        self.model.file_name = "Untitled.GAR"; self.current_path = None
        self.model.x_size = 25.0; self.model.y_size = 25.0; self.model.points.clear()
        for x, y in [(4.5, 16), (8.5, 16), (12.5, 16), (16.5, 16), (8.5, 12), (12.5, 12), (16.5, 12), (20.5, 12)]:
            self.model.add_point(x, y)
        self.x_size.setValue(25); self.y_size.setValue(25); self.design_x.setValue(25); self.design_y.setValue(25)
        self.apply_grid(); self.refresh_all(); self.show_response(); self.status.setText("New 8-element sample array ready.")

    def clear_design(self) -> None:
        self.model.points.clear(); self.current_path = None; self.model.file_name = "No file loaded"; self.refresh_all(); self.status.setText("Dashboard cleared. Open a file to load real array data.")

    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open GAR File", "", "GAR / Text Files (*.gar *.GAR *.txt *.csv);;All Files (*.*)")
        if not path: return
        try:
            loaded = load_gar_file(path)
        except Exception as exc:
            QMessageBox.critical(self, "Array Response", f"Unable to open file:\n{exc}"); return
        self.model.file_name = loaded.file_name; self.model.x_size = loaded.x_size; self.model.y_size = loaded.y_size; self.model.points = loaded.points
        self.current_path = Path(path)
        self.x_size.setValue(self.model.x_size); self.y_size.setValue(self.model.y_size); self.design_x.setValue(self.model.x_size); self.design_y.setValue(self.model.y_size)
        self.refresh_all(); self.show_response(); self.status.setText(f"Loaded {self.model.file_name} with {self.model.elements} elements.")

    def save_file(self) -> None:
        path = str(self.current_path) if self.current_path else ""
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "Save GAR File", self.model.file_name, "GAR Files (*.GAR *.gar);;JSON Files (*.json);;All Files (*.*)")
        if not path: return
        try:
            save_gar_file(path, self.model)
        except Exception as exc:
            QMessageBox.critical(self, "Array Response", f"Unable to save file:\n{exc}"); return
        self.current_path = Path(path); self.model.file_name = self.current_path.name; self.refresh_all(); self.status.setText(f"Saved {self.model.file_name}.")

    def apply_dimensions(self) -> None:
        self.x_size.setValue(self.design_x.value()); self.y_size.setValue(self.design_y.value()); self._sync_sizes_from_header()

    def apply_grid(self) -> None:
        self.design_canvas.grid_x = float(self.grid_x.value()); self.design_canvas.grid_y = float(self.grid_y.value())
        self.design_canvas.nudge_x = float(self.nudge_x.value()); self.design_canvas.nudge_y = float(self.nudge_y.value())
        self.design_canvas.snap = self.snap_cb.isChecked(); self.design_canvas.show_grid = self.show_cb.isChecked(); self.design_canvas.update()

    def set_azimuth(self, value: int | float) -> None:
        self.azimuth_slider.blockSignals(True); self.azimuth_slider.setValue(int(value)); self.azimuth_slider.blockSignals(False)
        az = float(value); self.azimuth_label.setText(f"{az:.0f}")
        self.preview.azimuth = az; self.response_canvas.azimuth = az
        self.preview.update(); self.response_canvas.update(); self.status.setText(f"Azimuth set to {az:.1f}°.")

    def _on_palette_changed(self, palette_name: str) -> None:
        self._palette_name = str(palette_name or "Seismic")
        self.response_canvas.set_palette(self._palette_name)
        self.response_colorbar.set_state(0.0, 1.0, self._palette_name, unit="", label="Normalized array response")
        self.status.setText(f"Response palette: {self._palette_name}")

    def update_cursor_mode(self) -> None:
        if self.rb_freq_velocity.isChecked(): self.response_canvas.cursor_mode = "freq_velocity"
        elif self.rb_velocity_freq.isChecked(): self.response_canvas.cursor_mode = "velocity_frequency"
        else: self.response_canvas.cursor_mode = "wavenumber"
        self.response_canvas.velocity = self.velocity_spin.value(); self.response_canvas.frequency = self.freq_spin.value(); self.response_canvas.update()

    def show_design(self) -> None:
        self.stack.setCurrentWidget(self.design_card); self.status.setText("Array Design: left click adds an element, right click deletes nearest element.")

    def show_response(self) -> None:
        self.stack.setCurrentWidget(self.response_card); self.response_canvas.update(); self.status.setText("Array Response view active.")

    def print_view(self) -> None:
        QMessageBox.information(self, "Array Response", "Use the system print/export option from the main application. Current view is ready for capture/printing.")

    def close_workspace(self) -> None:
        self.close()

    def handle_ribbon_action(self, action_id: str) -> None:
        actions = {
            "array_response_open": self.open_file,
            "array_response_save": self.save_file,
            "array_response_new": self.new_design,
            "array_response_clear": self.clear_design,
            "array_response_design": self.show_design,
            "array_response_response": self.show_response,
            "array_response_print": self.print_view,
            "array_response_azimuth_0": lambda: self.set_azimuth(0),
            "array_response_azimuth_45": lambda: self.set_azimuth(45),
            "array_response_azimuth_90": lambda: self.set_azimuth(90),
        }
        func = actions.get(action_id)
        if func: func()
