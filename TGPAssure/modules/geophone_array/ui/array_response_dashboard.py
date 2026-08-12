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
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from modules.geophone_array.models import GeophoneArrayModel, load_gar_file, save_gar_file
from modules.geophone_array.response import calculate_response, frequency_to_velocity, wavenumber_to_frequency


STYLE = """
QWidget#arrayResponseDashboard { background: #F5F7FA; color: #172033; font-size: 10px; }
QGroupBox { border: 1px solid #CBD5E1; border-radius: 6px; margin-top: 7px; padding: 6px; font-size: 10px; font-weight: 600; background: #FFFFFF; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; color: #24364F; }
QLabel { font-size: 10px; }
QLabel#valueLabel { color: #0E7490; font-size: 10px; font-weight: 700; }
QPushButton { border: 1px solid #B6C3D1; border-radius: 5px; padding: 4px 7px; min-height: 20px; background: #FFFFFF; font-size: 10px; font-weight: 600; }
QPushButton:hover { background: #EAF4FF; border-color: #5BA6D8; }
QPushButton#accentButton { background: #0E7490; border-color: #0E7490; color: white; }
QPushButton#blueButton { background: #2563EB; border-color: #1D4ED8; color: white; }
QPushButton#greenButton { background: #16A34A; border-color: #15803D; color: white; }
QPushButton#amberButton { background: #D97706; border-color: #B45309; color: white; }
QPushButton#redButton { background: #DC2626; border-color: #B91C1C; color: white; }
QPushButton#navButton { background: #EEF6FF; border-color: #93C5FD; color: #0F4C81; }
QTabWidget::pane { border: 1px solid #CBD5E1; border-radius: 7px; background: #FFFFFF; }
QTabBar::tab { background: #EAF0F7; border: 1px solid #C6D3E2; padding: 5px 8px; font-size: 9px; font-weight: 600; min-height: 18px; }
QTabBar::tab:selected { background: #0E7490; color: #FFFFFF; border-color: #0E7490; }
QTabBar::tab:hover { background: #D8ECFA; }
QDoubleSpinBox, QSpinBox, QComboBox, QLineEdit { min-height: 20px; padding: 1px 4px; font-size: 10px; }
QRadioButton, QCheckBox { spacing: 5px; font-size: 10px; }
QFrame#plotCard, QFrame#designCard { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 8px; }
QFrame#leftPanel { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 8px; }
QLabel#statusLabel { background: #FFFFFF; border: 1px solid #D6DEE8; border-radius: 5px; padding: 4px 8px; color: #334155; font-size: 10px; }
"""


class ArrayDesignCanvas(QWidget):
    changed = Signal()
    cursorChanged = Signal(float, float)

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
        self.setMinimumSize(340, 300)
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

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor("#050505"))
        r = self._plot_rect()
        p.setPen(QPen(QColor("#E6E6E6"), 1.4))
        p.drawRect(r)
        font = QFont(self.font())
        font.setPointSize(7)
        p.setFont(font)
        if self.show_grid:
            p.setPen(QPen(QColor("#008D96"), 1))
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
        p.setPen(QPen(QColor("#FF1B1B"), 1.2))
        p.drawLine(round(r.left()), round(r.bottom()), round(r.right()), round(r.bottom()))
        p.drawLine(round(r.left()), round(r.top()), round(r.left()), round(r.bottom()))
        p.setPen(QPen(QColor("#FF2A2A"), 1))
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
        p.setPen(QPen(QColor("#FF2A2A"), 1))
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
        x, y = self._from_screen(event.position().toPoint())
        self.cursor_x = x
        self.cursor_y = y
        self.cursor_visible = True
        self.cursorChanged.emit(x, y)
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.cursor_visible = False
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        x, y = self._from_screen(event.position().toPoint())
        if event.button() == Qt.MouseButton.RightButton:
            if self.model.remove_nearest(x, y, tolerance=max(self.grid_x, self.grid_y, 1.0) * 0.45):
                self.changed.emit(); self.update()
        elif event.button() == Qt.MouseButton.LeftButton:
            self.model.add_point(x, y)
            self.changed.emit(); self.update()


class ResponseCanvas(QWidget):
    cursorChanged = Signal(float, float)

    def __init__(self, model: GeophoneArrayModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = model
        self.azimuth = 0.0
        self.cursor_x = 0.0
        self.cursor_y = 0.0
        self.cursor_mode = "wavenumber"
        self.velocity = 355.0
        self.frequency = 60.0
        self.setMouseTracking(True)
        self.setMinimumSize(460, 310)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def _plot_rect(self) -> QRectF:
        return QRectF(56, 44, max(160, self.width() - 86), max(150, self.height() - 86))

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
        curve = calculate_response(self.model, self.azimuth, max_ratio=11.0, samples=700)
        if curve.x_values:
            p.setPen(QPen(QColor("#1D39FF"), 1.3))
            last = None
            for xval, yval in zip(curve.x_values, curve.y_values):
                sx = r.left() + xval / 11.0 * r.width()
                sy = r.bottom() - yval * r.height()
                if last is not None:
                    p.drawLine(last[0], last[1], round(sx), round(sy))
                last = (round(sx), round(sy))
        cx = r.left() + max(0.0, min(11.0, self.cursor_x)) / 11.0 * r.width()
        cy = r.bottom() - max(0.0, min(1.0, self.cursor_y)) * r.height()
        p.setPen(QPen(QColor("#FF2020"), 1.2))
        p.drawLine(round(cx), round(r.top()), round(cx), round(r.bottom()))
        p.drawLine(round(r.left()), round(cy), round(r.right()), round(cy))
        p.setBrush(QBrush(QColor("#FF2020")))
        p.drawEllipse(QPoint(round(cx), round(cy)), 3, 3)
        p.setPen(QPen(QColor("#0E31FF"), 1.1))
        p.drawText(round(r.left()), round(r.top()) - 8, f"Cursor X : {self.cursor_x:.2f}   Cursor Y : {self.cursor_y:.2f}")
        p.setPen(QPen(QColor("#242424"), 1))
        p.drawText(round(r.left()), 22, f"File : {self.model.file_name}")
        p.drawText(round(r.left() + r.width() * 0.43), 22, f"Elements : {self.model.elements}")
        p.drawText(round(r.left() + r.width() * 0.78), 22, f"Azimuth : {self.azimuth:.1f} Deg")
        if self.cursor_mode == "freq_velocity":
            p.drawText(round(r.left() + r.width() * 0.43), 38, f"Freq(V={self.velocity:.0f}) : {wavenumber_to_frequency(self.cursor_x, self.velocity, max(curve.projected_length,1)):.2f} Hz")
        elif self.cursor_mode == "velocity_frequency":
            p.drawText(round(r.left() + r.width() * 0.43), 38, f"Vel(F={self.frequency:.0f}) : {frequency_to_velocity(self.cursor_x, self.frequency, max(curve.projected_length,1)):.2f} m/s")
        p.drawText(round(r.left() + r.width() * 0.78), 38, f"Length : {curve.projected_length:.2f}")
        p.drawText(round(r.center().x()) - 76, round(r.bottom()) + 28, "Array Length/Wavelength")
        p.setPen(QPen(QColor("#FF1D1D"), 1))
        p.drawText(round(r.right()) - 170, round(r.bottom()) + 48, "TGP Geophone Array Analysis")

    def _update_cursor_from_pos(self, pos: QPoint) -> None:
        r = self._plot_rect()
        self.cursor_x = max(0.0, min(11.0, (pos.x() - r.left()) / max(r.width(), 1.0) * 11.0))
        self.cursor_y = max(0.0, min(1.0, (r.bottom() - pos.y()) / max(r.height(), 1.0)))
        self.cursorChanged.emit(self.cursor_x, self.cursor_y)
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._update_cursor_from_pos(event.position().toPoint())

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._update_cursor_from_pos(event.position().toPoint())


class ArrayMapPreview(QWidget):
    def __init__(self, model: GeophoneArrayModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = model
        self.azimuth = 0.0
        self.setMinimumSize(118, 118); self.setMaximumHeight(150)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor("#050505"))
        cx, cy = self.width() / 2, self.height() / 2
        rad = min(self.width(), self.height()) * 0.42
        p.setPen(QPen(QColor("#001CFF"), 1))
        p.drawEllipse(QPoint(round(cx), round(cy)), round(rad), round(rad))
        p.drawEllipse(QPoint(round(cx), round(cy)), round(rad * 0.72), round(rad * 0.72))
        rect_size = rad * 1.05
        p.setPen(QPen(QColor("#777777"), 1))
        p.drawRect(QRectF(cx - rect_size/2, cy - rect_size/2, rect_size, rect_size))
        p.setPen(QPen(QColor("#28FF55"), 2))
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
        self._build_ui()
        self._wire()
        self._reset_to_blank_dashboard()
        self._apply_compact_widgets()
        self.setStyleSheet(STYLE)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(5)
        self.header = QGroupBox("Array Information")
        hg = QGridLayout(self.header); hg.setContentsMargins(8, 8, 8, 6); hg.setHorizontalSpacing(8); hg.setVerticalSpacing(4)
        self.file_label = QLabel("Untitled.GAR"); self.file_label.setObjectName("valueLabel")
        self.elem_label = QLabel("0"); self.elem_label.setObjectName("valueLabel")
        self.x_size = QDoubleSpinBox(); self.x_size.setRange(1, 10000); self.x_size.setValue(25); self.x_size.setDecimals(2); self.x_size.setMaximumWidth(84)
        self.y_size = QDoubleSpinBox(); self.y_size.setRange(1, 10000); self.y_size.setValue(25); self.y_size.setDecimals(2); self.y_size.setMaximumWidth(84)
        hg.addWidget(QLabel("File Name"), 0, 0); hg.addWidget(self.file_label, 0, 1, 1, 3)
        hg.addWidget(QLabel("Elements"), 0, 4); hg.addWidget(self.elem_label, 0, 5)
        hg.addWidget(QLabel("X Size"), 0, 6); hg.addWidget(self.x_size, 0, 7)
        hg.addWidget(QLabel("Y Size"), 0, 8); hg.addWidget(self.y_size, 0, 9)
        root.addWidget(self.header)

        body = QHBoxLayout(); body.setSpacing(7)
        root.addLayout(body, 1)
        self.left = QFrame(); self.left.setObjectName("leftPanel"); self.left.setMinimumWidth(230); self.left.setMaximumWidth(275)
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
        self.array_design_btn = QPushButton("Array Design"); self.array_design_btn.setObjectName("accentButton")
        self.response_btn = QPushButton("Array Response"); self.response_btn.setObjectName("blueButton")
        self.print_btn = QPushButton("Print"); self.print_btn.setObjectName("amberButton")
        self.end_btn = QPushButton("End"); self.end_btn.setObjectName("redButton")
        for btn in (self.array_design_btn, self.response_btn, self.print_btn, self.end_btn):
            view_l.addWidget(btn)
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
        rc_l.addWidget(self.response_canvas, 1)
        response_footer = QHBoxLayout()
        response_footer.addStretch(1); response_footer.addWidget(QLabel("CTRL P To Print")); response_footer.addStretch(1)
        self.prev_btn = QPushButton("◀"); self.next_btn = QPushButton("▶"); self.prev_btn.setObjectName("navButton"); self.next_btn.setObjectName("navButton"); self.prev_btn.setMaximumWidth(42); self.next_btn.setMaximumWidth(42)
        response_footer.addWidget(self.prev_btn); response_footer.addWidget(self.next_btn)
        rc_l.addLayout(response_footer)
        self.design_card = QFrame(); self.design_card.setObjectName("designCard")
        self._build_design_card()
        self.stack.addWidget(self.response_card); self.stack.addWidget(self.design_card)
        body.addWidget(self.stack, 1)
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
        font.setPointSize(8)
        self.setFont(font)
        for cls in (QDoubleSpinBox, QSpinBox):
            for spin in self.findChildren(cls):
                spin.setMaximumWidth(92)
                spin.setMinimumWidth(68)
        for btn in self.findChildren(QPushButton):
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
        self.design_canvas.changed.connect(self.refresh_all)
        self.design_canvas.cursorChanged.connect(lambda x, y: (self.cursor_x.setText(f"{x:.2f}"), self.cursor_y.setText(f"{y:.2f}")))
        self.response_canvas.cursorChanged.connect(lambda x, y: self.status.setText(f"Cursor X: {x:.2f}  Cursor Y: {y:.2f}"))
        for rb in (self.rb_wavenumber, self.rb_freq_velocity, self.rb_velocity_freq): rb.toggled.connect(self.update_cursor_mode)
        self.velocity_spin.valueChanged.connect(lambda _v: self.response_canvas.update())
        self.freq_spin.valueChanged.connect(lambda _v: self.response_canvas.update())
        self.prev_btn.clicked.connect(lambda: self.set_azimuth(max(0, self.azimuth_slider.value() - 5)))
        self.next_btn.clicked.connect(lambda: self.set_azimuth(min(180, self.azimuth_slider.value() + 5)))

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
