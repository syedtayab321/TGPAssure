from __future__ import annotations

import csv
from pathlib import Path
import numpy as np

import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer, QRectF, QSize
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QColorDialog,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from modules.uphole import UpholeInterpreter, UpholeReader, UpholeShot
from core.visualization.palette_library import palette_hex, palette_rgb_array
from ui.widgets.color_palette_dialog import PaletteSelectorButton
from ui.widgets.palette_colorbar import PaletteColorBar

_QSS = """
QWidget#upholeDashboard {
    background:#F4F5F7;
    color:#1F2937;
    font-family:Segoe UI, Arial, sans-serif;
    font-size:8pt;
}
QFrame#sideRail {
    background:#F1F3F6;
    border-right:1px solid #C9D0DA;
}
QLabel#railBrand {
    color:#1F2937;
    background:#FFFFFF;
    border:1px solid #CED6E0;
    border-left:4px solid #F0A500;
    border-radius:4px;
    font-size:8.6pt;
    font-weight:900;
    letter-spacing:.3px;
    padding:5px 6px;
}
QLabel#railSubTitle {
    color:#536274;
    background:#E7EBF0;
    border:1px solid #D3D9E2;
    border-radius:3px;
    font-size:6.9pt;
    font-weight:650;
    padding:3px 6px;
}
QLabel#sideCaption {
    color:#344256;
    background:#E2E6EC;
    border:1px solid #D0D6DF;
    border-radius:3px;
    font-size:6.9pt;
    font-weight:900;
    letter-spacing:.4px;
    padding:4px 7px;
}
QPushButton#sideCommand {
    background:#FFFFFF;
    color:#1F2937;
    border:1px solid #C4CCD7;
    border-radius:6px;
    padding:5px 8px;
    font-size:7.8pt;
    font-weight:800;
    text-align:left;
}
QPushButton#sideCommand:hover {
    background:#FFF7E6;
    border-color:#F0A500;
    color:#111827;
}
QPushButton#sideCommand:pressed {
    background:#F0A500;
    border-color:#CC8700;
    color:#111827;
}
QPushButton#sideCommand[primary="true"] {
    background:#F0A500;
    border-color:#C98A00;
    color:#111827;
}
QPushButton#sideCommand[primary="true"]:hover {
    background:#E59A00;
    border-color:#B97800;
    color:#111827;
}
QPushButton#sideCommand[active="true"] {
    background:#2F343A;
    border-color:#2F343A;
    color:#FFFFFF;
}
QPushButton#sideCommand:disabled {
    background:#F2F4F7;
    color:#8A96A6;
    border-color:#D6DCE5;
}
QPushButton#exitCommand {
    background:#FFFFFF;
    color:#7A1E1E;
    border:1px solid #D0A2A2;
    border-radius:6px;
    padding:5px 8px;
    font-size:7.8pt;
    font-weight:900;
    text-align:left;
}
QPushButton#exitCommand:hover {
    background:#C62828;
    border-color:#A31818;
    color:#FFFFFF;
}
QFrame#topPanel {
    background:#F7F8FA;
    border:1px solid #C9D0DA;
    border-radius:6px;
}
QLabel#barTitle {
    color:#1F2937;
    font-size:8pt;
    font-weight:900;
    padding:4px 8px;
    background:#FFFFFF;
    border:1px solid #C8D1DD;
    border-left:4px solid #F0A500;
    border-radius:4px;
}
QLabel#modeHint {
    color:#5F6B7A;
    font-size:7pt;
    font-weight:650;
}
QRadioButton, QCheckBox {
    color:#1F2937;
    font-size:7.8pt;
    font-weight:800;
    spacing:4px;
}
QRadioButton:disabled, QCheckBox:disabled {
    color:#8A96A6;
}
QPushButton#smallCommand {
    background:#FFFFFF;
    border:1px solid #C4CCD7;
    border-radius:6px;
    color:#1F2937;
    padding:4px 10px;
    font-size:7.8pt;
    font-weight:900;
}
QPushButton#smallCommand:hover {
    background:#FFF7E6;
    border-color:#F0A500;
    color:#111827;
}
QPushButton#colorSwatch {
    border:1px solid #AAB3C0;
    border-radius:3px;
    min-width:23px;
    max-width:23px;
    min-height:17px;
    max-height:17px;
    padding:0;
}
QToolButton#navIcon {
    border:1px solid #C4CCD7;
    color:#1F2937;
    background:#FFFFFF;
    border-radius:6px;
    font-size:11px;
    font-weight:900;
    min-width:25px;
    max-width:25px;
    min-height:22px;
    max-height:22px;
}
QToolButton#navIcon:hover {
    color:#111827;
    background:#F0A500;
    border-color:#C98A00;
}
QFrame#canvasFrame {
    background:#FFFFFF;
    border:1px solid #C9D0DA;
    border-radius:7px;
}
QFrame#pageHeader {
    background:#FFFFFF;
    border:1px solid #D2D8E1;
    border-left:4px solid #F0A500;
    border-radius:6px;
}
QLabel#pageTitle {
    color:#111827;
    font-size:9.5pt;
    font-weight:900;
}
QLabel#pageSubtitle {
    color:#5A6675;
    font-size:7.2pt;
    font-weight:650;
}
QFrame#metricCard {
    background:#FFFFFF;
    border:1px solid #D2D8E1;
    border-radius:6px;
}
QLabel#metricName {
    color:#566477;
    font-size:6.7pt;
    font-weight:850;
    letter-spacing:.25px;
}
QLabel#metricValue {
    color:#111827;
    font-size:9.4pt;
    font-weight:950;
}
QLabel#metricAccent {
    color:#B17600;
    font-size:6.8pt;
    font-weight:900;
}
QFrame#plotCard {
    background:#FFFFFF;
    border:1px solid #D2D8E1;
    border-radius:7px;
}
QLabel#plotTitle {
    color:#111827;
    font-size:10pt;
    font-weight:950;
}
QLabel#plotModeChip {
    color:#111827;
    background:#FFF2CC;
    border:1px solid #F0A500;
    border-radius:6px;
    padding:2px 7px;
    font-size:7.6pt;
    font-weight:900;
}
QLabel#emptyTitle {
    color:#5C6675;
    background:#F4F6F8;
    border-top:1px solid #E0E4EA;
    font-size:8.2pt;
    font-weight:800;
    padding:4px;
}
QFrame#statusStrip {
    background:#F8F9FB;
    border-top:1px solid #C9D0DA;
    border-bottom-left-radius:7px;
    border-bottom-right-radius:7px;
}
QLabel#statusText {
    color:#2E3B4D;
    font-size:7.7pt;
    font-weight:750;
}
QLabel#metricText {
    color:#1F2937;
    font-size:7.7pt;
    font-weight:950;
}
QTableWidget {
    background:#FFFFFF;
    alternate-background-color:#F7F8FA;
    border:1px solid #D2D8E1;
    border-radius:6px;
    gridline-color:#E4E8EE;
    color:#1F2937;
    font-size:7.7pt;
    selection-background-color:#FFF2CC;
    selection-color:#111827;
}
QTableWidget::item {
    padding:3px;
}
QHeaderView::section {
    background:#E9EDF2;
    color:#2F3A4A;
    border:0;
    border-right:1px solid #D2D8E1;
    border-bottom:1px solid #D2D8E1;
    padding:4px 5px;
    font-size:7.5pt;
    font-weight:900;
}
QPlainTextEdit {
    background:#FFFFFF;
    border:1px solid #D2D8E1;
    border-radius:6px;
    color:#1F2937;
    font-family:Consolas, Segoe UI, monospace;
    font-size:7.8pt;
    padding:8px;
}
"""



class _TogglePaintMixin:
    """Paints compact, high-contrast legacy-style radio/checkbox controls."""

    _accent = QColor("#F0A500")
    _accent_dark = QColor("#B97800")
    _text = QColor("#1F2937")
    _muted = QColor("#8A96A6")
    _border = QColor("#5D6673")
    _border_disabled = QColor("#C6CDD8")
    _white = QColor("#FFFFFF")
    _hover = QColor("#FFF7E6")

    def _init_toggle_paint(self) -> None:
        self.setMouseTracking(True)
        self._hovered = False
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(22)

    def enterEvent(self, event):  # noqa: N802 - Qt override
        self._hovered = True
        self.update()
        return super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802 - Qt override
        self._hovered = False
        self.update()
        return super().leaveEvent(event)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        fm = self.fontMetrics()
        return QSize(max(42, fm.horizontalAdvance(self.text()) + 27), 22)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return self.sizeHint()

    def _draw_focus(self, painter: QPainter) -> None:
        if not self.hasFocus():
            return
        painter.setPen(QPen(QColor("#F0A500"), 1, Qt.DashLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 4, 4)

    def _draw_text(self, painter: QPainter, x: int) -> None:
        painter.setPen(self._text if self.isEnabled() else self._muted)
        font = self.font()
        font.setBold(True)
        painter.setFont(font)
        rect = QRectF(x, 0, self.width() - x, self.height())
        painter.drawText(rect, Qt.AlignVCenter | Qt.AlignLeft, self.text())


class ProfessionalRadioButton(_TogglePaintMixin, QRadioButton):
    """Small custom radio button with a clear selected dot and amber ring."""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self._init_toggle_paint()

    def paintEvent(self, event):  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        self._draw_focus(painter)

        d = 13.0
        y = (self.height() - d) / 2.0
        rect = QRectF(2.0, y, d, d)
        if self.isChecked() and self.isEnabled():
            painter.setBrush(self._white)
            painter.setPen(QPen(self._accent, 2.0))
            painter.drawEllipse(rect)
            painter.setPen(Qt.NoPen)
            painter.setBrush(self._accent)
            painter.drawEllipse(QRectF(rect.center().x() - 3.2, rect.center().y() - 3.2, 6.4, 6.4))
        else:
            fill = self._hover if self._hovered and self.isEnabled() else self._white
            painter.setBrush(fill)
            painter.setPen(QPen(self._border if self.isEnabled() else self._border_disabled, 1.2))
            painter.drawEllipse(rect)

        self._draw_text(painter, 21)


class ProfessionalCheckBox(_TogglePaintMixin, QCheckBox):
    """Small custom checkbox with a visible tick when selected."""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self._init_toggle_paint()

    def paintEvent(self, event):  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        self._draw_focus(painter)

        d = 14.0
        y = (self.height() - d) / 2.0
        rect = QRectF(2.0, y, d, d)
        if self.isChecked() and self.isEnabled():
            painter.setBrush(self._accent)
            painter.setPen(QPen(self._accent_dark, 1.2))
            painter.drawRoundedRect(rect, 3, 3)
            painter.setPen(QPen(self._white, 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawLine(rect.left() + 3.1, rect.top() + 7.3, rect.left() + 6.1, rect.bottom() - 3.4)
            painter.drawLine(rect.left() + 6.1, rect.bottom() - 3.4, rect.right() - 2.7, rect.top() + 3.7)
        else:
            fill = self._hover if self._hovered and self.isEnabled() else self._white
            painter.setBrush(fill)
            painter.setPen(QPen(self._border if self.isEnabled() else self._border_disabled, 1.2))
            painter.drawRoundedRect(rect, 3, 3)

        self._draw_text(painter, 22)



class UpholeDashboard(QWidget):
    """Modern uphole first-break and time-depth interpretation workspace."""

    PAGE_DISPLAY = 0
    PAGE_ASSIGNMENT = 1
    PAGE_LAYERS = 2
    PAGE_HEADERS = 3
    PAGE_GUIDE = 4

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("upholeDashboard")
        self.setProperty("module_id", "uphole")
        self.setStyleSheet(_QSS)
        self.records: list[UpholeShot] = []
        self.layers = []
        self.interpreter = UpholeInterpreter()
        self._interpreting = False
        self._current_path: str | None = None
        self.metric_values: dict[str, QLabel] = {}
        self._page_buttons: dict[int, QPushButton] = {}
        self._loading_table = False
        self.wig_color = "#020617"
        self.va_color = "#EF4444"
        self.fill_color = "#0EA5E9"
        self._palette_name = "Seismic"
        self._build_ui()
        self._refresh_all()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("sideRail")
        self.sidebar.setFixedWidth(118)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(7, 8, 7, 8)
        side.setSpacing(4)

        brand = QLabel("TGP UPHOLE")
        brand.setObjectName("railBrand")
        sub = QLabel("QC + velocity")
        sub.setObjectName("railSubTitle")
        side.addWidget(brand)
        side.addWidget(sub)

        self.open_file_btn = self._side_button("Open File", self.open_file, primary=True)
        self.pick_breaks_btn = self._side_button("Pick Breaks", self.show_assignment)
        self.uphole_btn = self._side_button("Uphole", self.interpret, primary=True)
        self.load_hole_btn = self._side_button("Load a Hole", self.open_folder)
        self.configure_btn = self._side_button("Configure", self.show_guide)
        self.headers_btn = self._side_button("Headers", self.show_headers)
        self.write_segy_btn = self._side_button("Write SEGY", self.write_segy)
        self.save_image_btn = self._side_button("Save Image", self.save_image)

        for label, buttons in (
            ("INPUT", (self.open_file_btn, self.pick_breaks_btn, self.uphole_btn)),
            ("HOLE", (self.load_hole_btn, self.configure_btn)),
            ("OUTPUT", (self.headers_btn, self.write_segy_btn, self.save_image_btn)),
        ):
            side.addWidget(self._side_caption(label))
            for button in buttons:
                side.addWidget(button)
            side.addSpacing(3)
        side.addStretch(1)

        self.exit_btn = self._side_button("Exit", self.close_dashboard)
        self.exit_btn.setObjectName("exitCommand")
        side.addWidget(self.exit_btn)
        root.addWidget(self.sidebar)

        self._page_buttons = {
            self.PAGE_DISPLAY: self.uphole_btn,
            self.PAGE_ASSIGNMENT: self.pick_breaks_btn,
            self.PAGE_LAYERS: self.uphole_btn,
            self.PAGE_HEADERS: self.headers_btn,
            self.PAGE_GUIDE: self.configure_btn,
        }

        body_widget = QWidget()
        body = QVBoxLayout(body_widget)
        body.setContentsMargins(8, 8, 8, 8)
        body.setSpacing(7)
        body.addWidget(self._build_options_bar())

        self.canvas_frame = QFrame()
        self.canvas_frame.setObjectName("canvasFrame")
        canvas = QVBoxLayout(self.canvas_frame)
        canvas.setContentsMargins(0, 0, 0, 0)
        canvas.setSpacing(0)

        self.stack = QStackedWidget()
        canvas.addWidget(self.stack, 1)
        self._build_display_page()
        self._build_assignment_page()
        self._build_layers_page()
        self._build_headers_page()
        self._build_guide_page()

        self.status_strip = QFrame()
        self.status_strip.setObjectName("statusStrip")
        status = QHBoxLayout(self.status_strip)
        status.setContentsMargins(10, 4, 10, 4)
        status.setSpacing(8)
        self.status_label = QLabel("Ready. Load an uphole file or folder.")
        self.status_label.setObjectName("statusText")
        status.addWidget(self.status_label, 1)
        self.metrics_label = QLabel("Records: 0   Points: 0   Layers: 0   Avg V: —")
        self.metrics_label.setObjectName("metricText")
        status.addWidget(self.metrics_label)
        canvas.addWidget(self.status_strip)

        body.addWidget(self.canvas_frame, 1)
        root.addWidget(body_widget, 1)

    def _build_options_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("topPanel")
        bar.setMinimumHeight(38)
        bar.setMaximumHeight(42)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(7)

        title = QLabel("Display Options")
        title.setObjectName("barTitle")
        layout.addWidget(title)

        self.display_group = QButtonGroup(self)
        self.display_radios: dict[str, QRadioButton] = {}
        for mode, label in (("wig", "Wig"), ("va_plus", "VA+"), ("va_minus", "VA-"), ("va_both", "VA+/-")):
            radio = ProfessionalRadioButton(label)
            radio.setProperty("display_mode", mode)
            self.display_group.addButton(radio)
            self.display_radios[mode] = radio
            radio.toggled.connect(self._on_display_mode_changed)
            layout.addWidget(radio)
        self.display_radios["va_plus"].setChecked(True)

        self.grad_fill_check = ProfessionalCheckBox("Grad Fill")
        self.grad_fill_check.toggled.connect(self._refresh_display_plot)
        layout.addWidget(self.grad_fill_check)

        self.black_swatch = QPushButton("")
        self.black_swatch.setObjectName("colorSwatch")
        self.black_swatch.setStyleSheet("QPushButton#colorSwatch { background:#020617; border:1px solid #CBD5E1; border-radius:4px; }")
        self.black_swatch.setToolTip("Wiggle / axis color")
        self.black_swatch.clicked.connect(lambda: self._choose_plot_color("wig"))
        layout.addWidget(self.black_swatch)

        self.red_swatch = QPushButton("")
        self.red_swatch.setObjectName("colorSwatch")
        self.red_swatch.setStyleSheet("QPushButton#colorSwatch { background:#EF4444; border:1px solid #CBD5E1; border-radius:4px; }")
        self.red_swatch.setToolTip("Variable-area fill color")
        self.red_swatch.clicked.connect(lambda: self._choose_plot_color("va"))
        layout.addWidget(self.red_swatch)

        layout.addWidget(QLabel("Palette:"))
        self.palette_selector = PaletteSelectorButton(self._palette_name, bar)
        self.palette_selector.setMinimumWidth(140)
        self.palette_selector.currentTextChanged.connect(self._on_palette_changed)
        layout.addWidget(self.palette_selector)

        self.clear_results_btn = QPushButton("Clear Results File")
        self.clear_results_btn.setObjectName("smallCommand")
        self.clear_results_btn.clicked.connect(self.clear_results)
        layout.addWidget(self.clear_results_btn)

        hint = QLabel("F11 full screen  |  F5 normal")
        hint.setObjectName("modeHint")
        layout.addWidget(hint)

        layout.addStretch(1)
        for symbol, tip, handler in (
            ("≪", "Previous view", self.previous_page),
            ("≫", "Next view", self.next_page),
            ("˄", "Show display", lambda: self._set_page(self.PAGE_DISPLAY)),
            ("˅", "Show configure guide", self.show_guide),
        ):
            button = QToolButton()
            button.setObjectName("navIcon")
            button.setText(symbol)
            button.setToolTip(tip)
            button.clicked.connect(handler)
            layout.addWidget(button)
        return bar

    @staticmethod
    def _side_caption(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sideCaption")
        return label

    def _side_button(self, text: str, handler, *, primary: bool = False) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("sideCommand")
        if primary:
            button.setProperty("primary", "true")
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(handler)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        button.setMinimumHeight(30)
        button.setMaximumHeight(34)
        return button

    def _build_display_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(7)

        header = QFrame()
        header.setObjectName("pageHeader")
        header.setMaximumHeight(50)
        h = QHBoxLayout(header)
        h.setContentsMargins(10, 6, 10, 6)
        h.setSpacing(8)
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(1)
        title = QLabel("Uphole Interpretation")
        title.setObjectName("pageTitle")
        subtitle = QLabel("First-break QC, time-depth curve and interval velocity model")
        subtitle.setObjectName("pageSubtitle")
        text_col.addWidget(title)
        text_col.addWidget(subtitle)
        h.addLayout(text_col, 1)
        for key, title_text, accent in (
            ("records", "Records", "shots"),
            ("points", "Points", "picks"),
            ("layers", "Layers", "intervals"),
            ("avg_v", "Avg V", "m/s"),
        ):
            card, value_label = self._metric_card(title_text, accent)
            self.metric_values[key] = value_label
            h.addWidget(card)
        layout.addWidget(header)

        plot_card = QFrame()
        plot_card.setObjectName("plotCard")
        plot_layout = QVBoxLayout(plot_card)
        plot_layout.setContentsMargins(10, 8, 10, 8)
        plot_layout.setSpacing(5)

        plot_header = QHBoxLayout()
        self.plot_title_label = QLabel("UYH Uphole Interpretation")
        self.plot_title_label.setObjectName("plotTitle")
        plot_header.addWidget(self.plot_title_label, 1)
        self.plot_mode_label = QLabel("VA+")
        self.plot_mode_label.setObjectName("plotModeChip")
        plot_header.addWidget(self.plot_mode_label)
        plot_layout.addLayout(plot_header)

        self.display_plot = pg.PlotWidget()
        self.display_plot.setBackground("#FFFFFF")
        self.display_plot.showGrid(x=True, y=True, alpha=0.18)
        self.display_plot.setLabel("bottom", "Time", units="ms")
        self.display_plot.setLabel("left", "Depth", units="m")
        self.display_plot.getPlotItem().setTitle("")
        self.display_plot.getAxis("bottom").setPen(pg.mkPen("#8B9AAC"))
        self.display_plot.getAxis("left").setPen(pg.mkPen("#8B9AAC"))
        self.display_plot.getAxis("bottom").setTextPen(pg.mkPen("#65758A"))
        self.display_plot.getAxis("left").setTextPen(pg.mkPen("#65758A"))
        plot_layout.addWidget(self.display_plot, 1)
        self.display_colorbar = PaletteColorBar(plot_card, orientation=Qt.Horizontal)
        self.display_colorbar.set_state(0.0, 1.0, self._palette_name, unit="m", label="Depth / time-depth value")
        plot_layout.addWidget(self.display_colorbar)

        self.empty_overlay = QLabel("Open File / Load a Hole to start uphole interpretation")
        self.empty_overlay.setObjectName("emptyTitle")
        self.empty_overlay.setAlignment(Qt.AlignCenter)
        self.empty_overlay.setMaximumHeight(28)
        plot_layout.addWidget(self.empty_overlay)
        layout.addWidget(plot_card, 1)
        self.stack.addWidget(page)

    def _build_assignment_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(7)
        layout.addWidget(self._page_header("Pick Breaks", "Review and edit depth, offset, first-break picks, correction time and channel information."))
        self.assignment_table = QTableWidget(0, 9)
        self.assignment_table.setHorizontalHeaderLabels(["File", "Shot", "Depth m", "Offset m", "Pick ms", "Corrected ms", "Channel", "dt ms", "Note"])
        self._prep_table(self.assignment_table)
        self.assignment_table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed | QTableWidget.AnyKeyPressed)
        self.assignment_table.itemChanged.connect(self._on_assignment_item_changed)
        layout.addWidget(self.assignment_table, 1)
        self.stack.addWidget(page)

    def _build_layers_page(self) -> None:
        page = QWidget()
        layout = QGridLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(7)
        layout.addWidget(self._page_header("Velocity Layers", "Calculated interval velocities from the interpreted uphole time-depth curve."), 0, 0, 1, 2)

        self.layers_table = QTableWidget(0, 5)
        self.layers_table.setHorizontalHeaderLabels(["Top m", "Base m", "Top ms", "Base ms", "Velocity m/s"])
        self._prep_table(self.layers_table)
        self.layers_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.layers_table, 1, 0)

        velocity_card = QFrame()
        velocity_card.setObjectName("plotCard")
        v_layout = QVBoxLayout(velocity_card)
        v_layout.setContentsMargins(10, 8, 10, 8)
        title = QLabel("Interval Velocity Profile")
        title.setObjectName("plotTitle")
        v_layout.addWidget(title)
        self.velocity_plot = pg.PlotWidget()
        self.velocity_plot.setBackground("#FFFFFF")
        self.velocity_plot.showGrid(x=True, y=True, alpha=0.22)
        self.velocity_plot.setLabel("left", "Velocity", units="m/s")
        self.velocity_plot.setLabel("bottom", "Layer")
        self.velocity_plot.getAxis("bottom").setPen(pg.mkPen("#94A3B8"))
        self.velocity_plot.getAxis("left").setPen(pg.mkPen("#94A3B8"))
        self.velocity_plot.getAxis("bottom").setTextPen(pg.mkPen("#64748B"))
        self.velocity_plot.getAxis("left").setTextPen(pg.mkPen("#64748B"))
        v_layout.addWidget(self.velocity_plot, 1)
        self.velocity_colorbar = PaletteColorBar(velocity_card, orientation=Qt.Horizontal)
        self.velocity_colorbar.set_state(0.0, 1.0, self._palette_name, unit="m/s", label="Interval velocity")
        v_layout.addWidget(self.velocity_colorbar)
        layout.addWidget(velocity_card, 1, 1)
        layout.setColumnStretch(0, 2)
        layout.setColumnStretch(1, 1)
        self.stack.addWidget(page)

    def _build_headers_page(self) -> None:
        page = QWidget()
        layout = QGridLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(7)
        layout.addWidget(self._page_header("Headers & QC Summary", "Imported source/header information and quick completeness statistics."), 0, 0, 1, 2)

        self.headers_table = QTableWidget(0, 5)
        self.headers_table.setHorizontalHeaderLabels(["File", "Shot", "Samples", "Traces", "Source Line"])
        self._prep_table(self.headers_table)
        self.headers_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.headers_table, 1, 0)

        self.stats_table = QTableWidget(0, 2)
        self.stats_table.setHorizontalHeaderLabels(["Metric", "Value"])
        self._prep_table(self.stats_table)
        self.stats_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.stats_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.stats_table, 1, 1)
        layout.setColumnStretch(0, 2)
        layout.setColumnStretch(1, 1)
        self.stack.addWidget(page)

    def _build_guide_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(7)
        layout.addWidget(self._page_header("Configure / Workflow Guide", "Operational guide for importing, editing, interpreting and exporting uphole deliverables."))
        self.guide_text = QPlainTextEdit()
        self.guide_text.setReadOnly(True)
        self.guide_text.setPlainText(
            "UPHOLE WORKFLOW\n\n"
            "1. Open File: import SEG-2/OYO/header files or CSV/TXT pick tables.\n"
            "2. Load a Hole: import a folder containing multiple uphole files for one hole.\n"
            "3. Pick Breaks: review and edit depth, offset, first-break pick, corrected time and channel.\n"
            "4. Run Uphole: calculate the time-depth curve and interval velocity layers.\n"
            "5. Headers: review imported file/header statistics and completeness.\n"
            "6. Write SEGY: exports an interpretation-ready sidecar table when decoded seismic trace samples are not available.\n"
            "7. Save Image: saves the active uphole display/table view as a PNG image.\n\n"
            "CSV aliases accepted by the reader:\n"
            "depth, depth_m, pick_ms, corrected_ms, offset, offset_m, channel, sample_interval, samples, trace_count and note.\n\n"
            "Display modes match the legacy uphole screen: Wig, VA+, VA-, VA+/-, with optional Grad Fill.\n\n"
            "Keyboard shortcuts retained from the main application:\n"
            "F11 = full screen, F5 = normal view, Esc = exit full screen."
        )
        layout.addWidget(self.guide_text, 1)
        self.stack.addWidget(page)

    def _page_header(self, title: str, subtitle: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("pageHeader")
        frame.setMaximumHeight(52)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(1)
        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("pageSubtitle")
        subtitle_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        return frame

    def _metric_card(self, title: str, accent: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName("metricCard")
        card.setMinimumWidth(92)
        card.setMaximumWidth(125)
        card.setMaximumHeight(38)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(7, 4, 7, 4)
        layout.setSpacing(0)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(3)
        name = QLabel(title)
        name.setObjectName("metricName")
        value = QLabel("0")
        value.setObjectName("metricValue")
        top.addWidget(name)
        top.addWidget(value, 1, Qt.AlignRight)
        accent_label = QLabel(accent)
        accent_label.setObjectName("metricAccent")
        layout.addLayout(top)
        layout.addWidget(accent_label)
        return card, value

    @staticmethod
    def _prep_table(table: QTableWidget) -> None:
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(23)
        table.horizontalHeader().setStretchLastSection(True)
        table.setShowGrid(True)

    def _set_page(self, index: int) -> None:
        index = max(0, min(index, self.stack.count() - 1))
        self.stack.setCurrentIndex(index)
        names = ["Display", "Pick Breaks", "Layers / Velocity", "Headers", "Configure / Guide"]
        if 0 <= index < len(names):
            self.status_label.setText(f"{names[index]} view")
        self._set_active_side_button(index)

    def _set_active_side_button(self, index: int) -> None:
        for button in self._page_buttons.values():
            button.setProperty("active", "false")
            button.style().unpolish(button)
            button.style().polish(button)
        button = self._page_buttons.get(index)
        if button is not None:
            button.setProperty("active", "true")
            button.style().unpolish(button)
            button.style().polish(button)

    def previous_page(self) -> None:
        self._set_page(self.stack.currentIndex() - 1)

    def next_page(self) -> None:
        self._set_page(self.stack.currentIndex() + 1)

    def _on_display_mode_changed(self, checked: bool = True) -> None:
        if checked:
            self._refresh_display_plot()


    def _on_assignment_item_changed(self, _item: QTableWidgetItem | None = None) -> None:
        if self._loading_table:
            return
        self._sync_from_table()
        self.layers = self.interpreter.layers(self.records)
        self._populate_layers()
        self._populate_qc_tables()
        self._refresh_display_plot()
        self.status_label.setText("Pick/depth assignment updated")

    def _choose_plot_color(self, target: str) -> None:
        current = QColor(self.wig_color if target == "wig" else self.va_color)
        color = QColorDialog.getColor(current, self, "Choose uphole display colour")
        if not color.isValid():
            return
        html = color.name()
        if target == "wig":
            self.wig_color = html
            self.black_swatch.setStyleSheet(f"QPushButton#colorSwatch {{ background:{html}; border:1px solid #CBD5E1; border-radius:4px; }}")
        else:
            self.va_color = html
            self.red_swatch.setStyleSheet(f"QPushButton#colorSwatch {{ background:{html}; border:1px solid #CBD5E1; border-radius:4px; }}")
        self._refresh_display_plot()

    def _active_display_mode(self) -> str:
        for mode, radio in self.display_radios.items():
            if radio.isChecked():
                return mode
        return "va_plus"

    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open uphole file",
            str(Path.home()),
            "Uphole (*.sg2 *.seg2 *.dat *.oyo *.csv *.txt *.tsv *.fda *.hol *.cho);;All files (*.*)",
        )
        if path:
            self._load(path)

    def open_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Load an uphole folder", str(Path.home()))
        if path:
            self._load(path)

    def _load(self, path: str) -> None:
        main_window = self.window()
        task_id = f"uphole:file:{Path(path).name}"
        if hasattr(main_window, "begin_busy_task"):
            main_window.begin_busy_task(task_id, "Opening Uphole File", f"Reading {Path(path).name}", 10)
        try:
            self.records = UpholeReader().read(path)
            self._current_path = path
            self.layers = []
            if hasattr(main_window, "update_busy_task"):
                main_window.update_busy_task(task_id, 70, "Preparing uphole tables")
            self._populate_assignment()
            self._populate_headers()
            self._populate_qc_tables()
            self._refresh_display_plot()
            self._set_page(self.PAGE_ASSIGNMENT)
            self.status_label.setText(f"Loaded {len(self.records):,} record(s) from {Path(path).name}")
            if hasattr(main_window, "update_busy_task"):
                main_window.update_busy_task(task_id, 100, "Uphole file is ready")
        except Exception as exc:
            QMessageBox.critical(self, "Uphole Import", str(exc))
        finally:
            if hasattr(main_window, "end_busy_task"):
                main_window.end_busy_task(task_id)
            self._refresh_buttons()

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

            records.append(
                UpholeShot(
                    file_name=txt(0),
                    shot_id=txt(1),
                    depth_m=fl(2),
                    offset_m=fl(3),
                    pick_ms=fl(4),
                    corrected_ms=fl(5),
                    channel=integer(6),
                    sample_interval_ms=fl(7),
                    note=txt(8),
                )
            )
        self.records = records

    def interpret(self) -> None:
        if self._interpreting:
            return
        if not self.records:
            QMessageBox.information(self, "Uphole", "Load uphole files or a pick table first.")
            return
        self._interpreting = True
        self.uphole_btn.setEnabled(False)
        self.status_label.setText("Running uphole interpretation…")
        QTimer.singleShot(50, self._finish_interpret)

    def _finish_interpret(self) -> None:
        try:
            self._sync_from_table()
            self.layers = self.interpreter.layers(self.records)
            self._populate_layers()
            self._populate_qc_tables()
            self._refresh_display_plot()
            self._set_page(self.PAGE_DISPLAY)
            self.status_label.setText("Uphole interpretation complete")
        except Exception as exc:
            QMessageBox.critical(self, "Uphole Interpretation", str(exc))
        finally:
            self._interpreting = False
            self.uphole_btn.setEnabled(True)
            self._refresh_buttons()

    def _populate_assignment(self) -> None:
        self._loading_table = True
        self.assignment_table.setRowCount(0)
        for r in self.records:
            row = self.assignment_table.rowCount()
            self.assignment_table.insertRow(row)
            values = [r.file_name, r.shot_id, r.depth_m, r.offset_m, r.pick_ms, r.corrected_ms, r.channel, r.sample_interval_ms, r.note]
            for col, value in enumerate(values):
                self.assignment_table.setItem(row, col, QTableWidgetItem("" if value is None else str(value)))
        self.assignment_table.resizeRowsToContents()
        self._loading_table = False

    def _populate_headers(self) -> None:
        self.headers_table.setRowCount(0)
        for r in self.records:
            row = self.headers_table.rowCount()
            self.headers_table.insertRow(row)
            values = [r.file_name, r.shot_id, r.samples, r.trace_count, r.source_line]
            for col, value in enumerate(values):
                self.headers_table.setItem(row, col, QTableWidgetItem("" if value is None else str(value)))
        self.headers_table.resizeRowsToContents()

    def _time_depth_xy(self) -> tuple[list[float], list[float]]:
        td = self.interpreter.build_time_depth(self.records)
        x = [float(self.interpreter.interpreted_time(r) or 0.0) for r in td]
        y = [float(r.depth_m or 0.0) for r in td]
        return x, y

    def _refresh_display_plot(self) -> None:
        if not hasattr(self, "display_plot"):
            return
        self.display_plot.clear()
        x, y = self._time_depth_xy()
        mode = self._active_display_mode()
        self.empty_overlay.setVisible(not bool(x))
        self.plot_mode_label.setText(self._display_mode_label(mode))
        if not x:
            self.plot_title_label.setText("UYH Uphole Interpretation")
            self.display_plot.setXRange(0, 1, padding=0)
            self.display_plot.setYRange(0, 1, padding=0)
            self._update_metrics()
            return
        pen = pg.mkPen(self.wig_color, width=1.25 if mode == "wig" else 1.8)
        # Time-depth curve. Y-axis is inverted because depth increases downward.
        self.display_plot.plot(x, y, pen=pen)
        yarr = np.asarray(y, dtype=float)
        lo, hi = float(np.nanmin(yarr)), float(np.nanmax(yarr))
        span = max(hi - lo, 1e-12)
        lut = palette_rgb_array(self._palette_name, 256)
        norm = np.clip((yarr - lo) / span, 0.0, 1.0)
        idx = np.clip(np.rint(norm * 255).astype(int), 0, 255)
        brushes = [pg.mkBrush(int(r), int(g), int(b)) for r, g, b in lut[idx]]
        spots = [{"pos": (float(px), float(py)), "brush": brush, "pen": pg.mkPen("#FFFFFF", width=0.8), "size": 6} for px, py, brush in zip(x, y, brushes)]
        self.display_plot.addItem(pg.ScatterPlotItem(spots=spots))
        self.display_colorbar.set_state(lo, hi, self._palette_name, unit="m", label="Depth / time-depth value")
        if mode in {"va_plus", "va_minus", "va_both"}:
            brush_pos = pg.mkBrush(QColor(self.va_color))
            brush_neg = pg.mkBrush(QColor(self.wig_color))
            width = max(0.35, (max(x) - min(x)) / max(len(x) * 4, 1)) if len(x) > 1 else 0.35
            for xi, yi in zip(x, y):
                if mode in {"va_plus", "va_both"}:
                    self.display_plot.addItem(pg.BarGraphItem(x=[xi], y0=[0], height=[yi], width=width, brush=brush_pos, pen=None))
                if mode in {"va_minus", "va_both"}:
                    self.display_plot.addItem(pg.BarGraphItem(x=[xi - width * 0.55], y0=[0], height=[yi], width=width * 0.45, brush=brush_neg, pen=None))
        if self.grad_fill_check.isChecked() and len(x) > 1:
            fill = QColor(self.fill_color); fill.setAlpha(45)
            self.display_plot.plot(x, y, pen=pg.mkPen(self.wig_color, width=2), fillLevel=0, brush=pg.mkBrush(fill))
        self.display_plot.invertY(True)
        self.plot_title_label.setText(f"UYH Uphole Interpretation — {self._display_mode_label(mode)}")
        self.display_plot.enableAutoRange()
        self._update_metrics()

    @staticmethod
    def _display_mode_label(mode: str) -> str:
        return {"wig": "Wig", "va_plus": "VA+", "va_minus": "VA-", "va_both": "VA+/-"}.get(mode, "VA+")

    def _populate_layers(self) -> None:
        self.layers_table.setRowCount(0)
        for layer in self.layers:
            row = self.layers_table.rowCount()
            self.layers_table.insertRow(row)
            vals = [layer.top_depth_m, layer.base_depth_m, layer.top_time_ms, layer.base_time_ms, round(layer.interval_velocity_m_s, 2)]
            for col, value in enumerate(vals):
                self.layers_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.layers_table.resizeRowsToContents()
        self._populate_velocity_plot()

    def _populate_velocity_plot(self) -> None:
        self.velocity_plot.clear()
        if not self.layers:
            self.velocity_plot.setXRange(0, 1, padding=0)
            self.velocity_plot.setYRange(0, 1, padding=0)
            return
        x = list(range(1, len(self.layers) + 1))
        y = [float(layer.interval_velocity_m_s) for layer in self.layers]
        yarr = np.asarray(y, dtype=float)
        lo, hi = float(np.nanmin(yarr)), float(np.nanmax(yarr))
        self.velocity_plot.addItem(pg.BarGraphItem(x=x, height=y, width=0.65, brush=pg.mkBrush(palette_hex(self._palette_name, 0.48)), pen=pg.mkPen(palette_hex(self._palette_name, 0.72))))
        self.velocity_plot.plot(x, y, pen=pg.mkPen(palette_hex(self._palette_name, 0.72), width=1.5))
        span = max(hi - lo, 1e-12)
        lut = palette_rgb_array(self._palette_name, 256)
        idx = np.clip(np.rint(np.clip((yarr - lo) / span, 0.0, 1.0) * 255).astype(int), 0, 255)
        spots = [{"pos": (float(px), float(py)), "brush": pg.mkBrush(int(r), int(g), int(b)), "pen": pg.mkPen("#FFFFFF", width=0.8), "size": 6} for px, py, (r, g, b) in zip(x, y, lut[idx])]
        self.velocity_plot.addItem(pg.ScatterPlotItem(spots=spots))
        self.velocity_colorbar.set_state(lo, hi, self._palette_name, unit="m/s", label="Interval velocity")

    def _on_palette_changed(self, palette_name: str) -> None:
        self._palette_name = palette_name
        self._refresh_display_plot()
        self._populate_velocity_plot()

    def _field_count(self, attr: str) -> int:
        return sum(1 for record in self.records if getattr(record, attr, None) is not None and getattr(record, attr, None) != "")

    def _populate_qc_tables(self) -> None:
        summary = self.interpreter.summary(self.records)
        velocities = [float(layer.interval_velocity_m_s) for layer in self.layers]
        fields = [
            ("Records", f"{summary['records']:,}"),
            ("Usable time-depth points", f"{summary['usable_time_depth_points']:,}"),
            ("Interpreted layers", f"{summary['layers']:,}"),
            ("Depth completeness", self._percent_text("depth_m")),
            ("Pick-time completeness", self._percent_text("pick_ms")),
            ("Corrected-time completeness", self._percent_text("corrected_ms")),
            ("Average velocity", f"{summary.get('average_velocity_m_s'):,.2f} m/s" if summary.get("average_velocity_m_s") is not None else "—"),
            ("Minimum velocity", f"{min(velocities):,.2f} m/s" if velocities else "—"),
            ("Maximum velocity", f"{max(velocities):,.2f} m/s" if velocities else "—"),
        ]
        self.stats_table.setRowCount(0)
        for key, value in fields:
            row = self.stats_table.rowCount()
            self.stats_table.insertRow(row)
            self.stats_table.setItem(row, 0, QTableWidgetItem(key))
            self.stats_table.setItem(row, 1, QTableWidgetItem(str(value)))
        self._update_metrics()

    def _percent_text(self, attr: str) -> str:
        total = max(len(self.records), 1)
        present = self._field_count(attr)
        return f"{present:,} / {len(self.records):,} ({present / total * 100:.1f}%)"

    def _update_metrics(self) -> None:
        summary = self.interpreter.summary(self.records)
        avg = summary.get("average_velocity_m_s")
        avg_text = f"{avg:,.1f} m/s" if avg is not None else "—"
        if hasattr(self, "metrics_label"):
            self.metrics_label.setText(
                f"Records: {summary['records']:,}   Points: {summary['usable_time_depth_points']:,}   "
                f"Layers: {summary['layers']:,}   Avg V: {avg_text}"
            )
        if self.metric_values:
            self.metric_values["records"].setText(f"{summary['records']:,}")
            self.metric_values["points"].setText(f"{summary['usable_time_depth_points']:,}")
            self.metric_values["layers"].setText(f"{summary['layers']:,}")
            self.metric_values["avg_v"].setText(avg_text)

    def _refresh_all(self) -> None:
        self._populate_assignment()
        self._populate_headers()
        self._populate_layers()
        self._populate_qc_tables()
        self._refresh_display_plot()
        self._refresh_buttons()
        self._set_active_side_button(self.stack.currentIndex())

    def _refresh_buttons(self) -> None:
        has_records = bool(self.records)
        for button in (self.pick_breaks_btn, self.uphole_btn, self.headers_btn, self.write_segy_btn, self.save_image_btn):
            button.setEnabled(has_records or button is self.save_image_btn)

    def clear_results(self) -> None:
        self.layers = []
        self._populate_layers()
        self._populate_qc_tables()
        self._refresh_display_plot()
        self.status_label.setText("Results cleared; loaded records were kept for re-interpretation")

    def write_segy(self) -> None:
        if not self.records:
            QMessageBox.information(self, "Write SEGY", "Load uphole records before writing output.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Write uphole SEG-Y sidecar", "uphole_interpretation_segy_sidecar.csv", "CSV (*.csv);;All files (*.*)")
        if not path:
            return
        self._write_interpretation_csv(path)
        QMessageBox.information(
            self,
            "Write SEGY",
            "The current uphole reader imports headers and picks. A SEG-Y sidecar CSV has been written for the interpretation results. Full binary SEG-Y writing should be enabled only when decoded trace samples are available.",
        )

    def export_csv(self) -> None:
        if not self.records:
            QMessageBox.information(self, "Uphole", "Nothing to export.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export uphole interpretation", "uphole_interpretation.csv", "CSV (*.csv)")
        if not path:
            return
        self._write_interpretation_csv(path)
        QMessageBox.information(self, "Uphole", f"Exported:\n{path}")

    def _write_interpretation_csv(self, path: str) -> None:
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
        self._refresh_all()

    def save_image(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save Uphole Image", "uphole_interpretation.png", "PNG Image (*.png)")
        if not path:
            return
        pixmap = self.canvas_frame.grab()
        if not pixmap.save(path, "PNG"):
            QMessageBox.warning(self, "Save Image", "Could not save the image.")
            return
        QMessageBox.information(self, "Save Image", f"Saved:\n{path}")

    def close_dashboard(self) -> None:
        parent = self.parentWidget()
        while parent is not None:
            if hasattr(parent, "indexOf") and hasattr(parent, "removeTab"):
                index = parent.indexOf(self)
                if index >= 0:
                    parent.removeTab(index)
                    self.deleteLater()
                    return
            parent = parent.parentWidget()
        self.close()

    def show_assignment(self) -> None:
        self._set_page(self.PAGE_ASSIGNMENT)

    def show_time_depth(self) -> None:
        self._set_page(self.PAGE_DISPLAY)

    def show_layers(self) -> None:
        self._set_page(self.PAGE_LAYERS)

    def show_headers(self) -> None:
        self._populate_headers()
        self._populate_qc_tables()
        self._set_page(self.PAGE_HEADERS)

    def show_guide(self) -> None:
        self._set_page(self.PAGE_GUIDE)

    def can_execute(self, action_id: str) -> bool:
        if action_id in {"uphole_open", "uphole_open_folder", "uphole_guide"}:
            return True
        if action_id in {"uphole_interpret", "uphole_export", "uphole_time_depth", "uphole_layers", "uphole_assignments"}:
            return bool(self.records)
        return True
