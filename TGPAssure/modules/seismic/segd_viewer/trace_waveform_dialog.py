from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pyqtgraph as pg

try:
    pg.setConfigOptions(antialias=True)
except Exception:
    pass
from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QColorDialog,
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
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules.seismic.segd_viewer.segd_reader import SegdReader


DIALOG_STYLE = """
    QDialog { background:#EEF2F6; font-size:8.5pt; }
    QFrame#headerCard, QFrame#metricCard, QFrame#plotCard, QFrame#controlGrid, QFrame#controlGroup {
        background:#FFFFFF;
        border:1px solid #AEB7C2;
        border-radius:4px;
    }
    QFrame#controlGrid { background:#F7FAFC; }
    QFrame#controlGroup { background:#FFFFFF; }
    QWidget#rangeLegend {
        background:#FFFFFF;
        border:1px solid #C9D2DC;
        border-radius:5px;
    }
    QLabel { background:transparent; color:#0000CC; font-family:Arial; font-size:8.5pt; font-weight:700; }
    QLabel#titleLabel { color:#0000CC; font-size:10pt; font-weight:900; }
    QLabel#subtleLabel { color:#202020; font-size:8pt; font-weight:400; }
    QLabel#metricTitle { color:#202020; font-size:8pt; font-weight:700; }
    QLabel#metricValue { color:#0000CC; font-size:9.5pt; font-weight:900; }
    QLabel#controlGroupLabel { color:#263746; font-size:8pt; font-weight:900; }
    QLabel#rangeLegendTitle { color:#263746; font-size:8pt; font-weight:900; }
    QLabel#rangeChip { font-family:Arial; font-size:8pt; font-weight:900; }
    QPushButton {
        min-height:22px;
        max-height:24px;
        padding:1px 5px;
        border-radius:3px;
        border:1px solid #7E8A97;
        background:#F4F7FA;
        font-size:8.5pt;
        font-weight:700;
        color:#1F2D3A;
    }
    QPushButton:hover { background:#FFFFFF; border-color:#1E88E5; }
    QPushButton:pressed { background:#DDE7F0; }
    QPushButton#exportButton { background:#EAF4FF; color:#075985; border-color:#7DB7E8; min-width:38px; }
    QPushButton#analysisButton { background:#EAFBF4; color:#116149; border-color:#78D7B0; min-width:38px; }
    QPushButton#navigationButton { background:#FFF7E6; color:#8A4B00; border-color:#F2BE62; min-width:34px; }
    QPushButton#gainButton { background:#F2EDFF; color:#4C1D95; border-color:#B89BFF; min-width:34px; }
    QPushButton#viewButton { background:#E8F7FF; color:#075985; border-color:#60B9E8; min-width:38px; }
    QPushButton#dangerButton { background:#FFF1F2; color:#8A1022; border-color:#F29AA7; min-width:54px; }
    QSpinBox,QDoubleSpinBox,QLineEdit {
        background:#FFFFFF;
        border:1px solid #7E8A97;
        border-radius:3px;
        padding:1px 3px;
        min-height:20px;
        max-height:22px;
        color:#111827;
        font-size:8.5pt;
        font-weight:700;
    }
    QTableWidget { background:#FFFFFF; alternate-background-color:#F4F4F4; border:1px solid #B8B8B8; gridline-color:#C0C0C0; font-size:8.5pt; }
    QHeaderView::section { background:#E8E8E8; color:#202020; padding:3px; border:1px solid #B8B8B8; font-weight:700; }
"""


def _spectral_lut() -> np.ndarray:
    """Small built-in blue/cyan/yellow/red lookup table, avoiding optional colormap APIs."""
    stops = np.array(
        [
            [18, 36, 82],
            [18, 96, 160],
            [19, 166, 185],
            [255, 213, 79],
            [218, 60, 45],
        ],
        dtype=float,
    )
    positions = np.linspace(0.0, 1.0, len(stops))
    x = np.linspace(0.0, 1.0, 256)
    lut = np.vstack([np.interp(x, positions, stops[:, c]) for c in range(3)]).T
    return np.clip(lut, 0, 255).astype(np.ubyte)


_PALETTES: dict[str, list[str]] = {
    "TGP Spectral": ["#122452", "#1260A0", "#13A6B9", "#FFD54F", "#DA3C2D"],
    "Blue Ice": ["#071A2F", "#0F4C81", "#1FA2FF", "#A7F3D0", "#FFFFFF"],
    "Copper Heat": ["#1C1210", "#7C2D12", "#EA580C", "#FDBA74", "#FFF7ED"],
    "Seismic Red Blue": ["#173B8E", "#FFFFFF", "#B91C1C"],
    "Viridis Safe": ["#440154", "#31688E", "#35B779", "#FDE725"],
}


_RANGE_PRESETS: dict[str, dict[str, list[tuple[float, float, str]]]] = {
    "fft_db": {
        "Legacy dB": [
            (-200.0, -150.0, "#7F7F7F"),
            (-150.0, -120.0, "#806080"),
            (-120.0, -96.0, "#2F80ED"),
            (-96.0, -72.0, "#00B050"),
            (-72.0, -48.0, "#FFFF00"),
            (-48.0, -24.0, "#FF9900"),
            (-24.0, 6.0, "#FF0000"),
        ],
        "Soft QC": [
            (-200.0, -140.0, "#8C8C8C"),
            (-140.0, -100.0, "#5B8DEF"),
            (-100.0, -70.0, "#20C997"),
            (-70.0, -40.0, "#FFD43B"),
            (-40.0, 6.0, "#E03131"),
        ],
        "High Contrast": [
            (-200.0, -130.0, "#808080"),
            (-130.0, -90.0, "#0000FF"),
            (-90.0, -60.0, "#00FF00"),
            (-60.0, -30.0, "#FFFF00"),
            (-30.0, 6.0, "#FF0000"),
        ],
    },
    "frequency_hz": {
        "Legacy Hz": [
            (0.0, 6.0, "#808080"),
            (6.0, 10.0, "#1E88E5"),
            (10.0, 14.0, "#00A36C"),
            (14.0, 18.0, "#FFD700"),
            (18.0, 22.0, "#FF8C00"),
            (22.0, 10000.0, "#FF0000"),
        ],
        "Low Mid High": [
            (0.0, 8.0, "#2F80ED"),
            (8.0, 16.0, "#00B050"),
            (16.0, 24.0, "#FF9900"),
            (24.0, 10000.0, "#FF0000"),
        ],
        "Receiver QC": [
            (0.0, 5.0, "#7F7F7F"),
            (5.0, 12.0, "#00A2FF"),
            (12.0, 20.0, "#00C853"),
            (20.0, 32.0, "#FFD600"),
            (32.0, 10000.0, "#D50000"),
        ],
    },
}


def _copy_ranges(ranges: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    return [(float(lo), float(hi), str(color)) for lo, hi, color in ranges]


def _normalise_ranges(ranges: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    cleaned: list[tuple[float, float, str]] = []
    for low, high, color in ranges:
        low_f = float(low)
        high_f = float(high)
        if not np.isfinite(low_f) or not np.isfinite(high_f) or high_f <= low_f:
            continue
        qcolor = QColor(str(color))
        cleaned.append((low_f, high_f, qcolor.name() if qcolor.isValid() else "#000000"))
    return sorted(cleaned, key=lambda item: item[0])


def _range_color(value: float, ranges: list[tuple[float, float, str]], fallback: str = "#111111") -> str:
    if not np.isfinite(value) or not ranges:
        return fallback
    for low, high, color in ranges:
        if low <= float(value) < high:
            return color
    if float(value) < ranges[0][0]:
        return ranges[0][2]
    return ranges[-1][2]


def _range_index_map(values: np.ndarray, ranges: list[tuple[float, float, str]]) -> np.ndarray:
    if not ranges:
        return np.zeros_like(values, dtype=np.float64)
    mapped = np.zeros_like(values, dtype=np.float64)
    for index, (low, high, _color) in enumerate(ranges):
        mapped[(values >= low) & (values < high)] = float(index)
    mapped[values < ranges[0][0]] = 0.0
    mapped[values >= ranges[-1][1]] = float(len(ranges) - 1)
    return mapped


def _range_lut(ranges: list[tuple[float, float, str]]) -> np.ndarray:
    if not ranges:
        return _colors_to_lut(_PALETTES["TGP Spectral"])
    colors = []
    for _low, _high, color in ranges:
        qcolor = QColor(color)
        if not qcolor.isValid():
            qcolor = QColor("#000000")
        colors.append([qcolor.red(), qcolor.green(), qcolor.blue()])
    return np.asarray(colors, dtype=np.ubyte)


def _legend_html(ranges: list[tuple[float, float, str]], units: str) -> str:
    parts = []
    for low, high, color in ranges[:8]:
        parts.append(
            f"<span style='background:{color};color:#111111;border:1px solid #777;padding:1px 5px;'>"
            f"{low:g}–{high:g} {units}</span>"
        )
    return " &nbsp; ".join(parts)


class _RangeLegend(QWidget):
    """Professional color-range chip legend for FFT and frequency-time panels."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("rangeLegend")
        self._title_text = title
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(8, 5, 8, 5)
        self._layout.setSpacing(5)
        self._title = QLabel(title)
        self._title.setObjectName("rangeLegendTitle")
        self._layout.addWidget(self._title)
        self._layout.addSpacing(3)
        self._layout.addStretch(1)

    @staticmethod
    def _text_color_for(background: str) -> str:
        color = QColor(background)
        if not color.isValid():
            return "#111827"
        luminance = (0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()) / 255.0
        return "#FFFFFF" if luminance < 0.45 else "#111827"

    def set_ranges(self, ranges: list[tuple[float, float, str]], units: str) -> None:
        while self._layout.count() > 3:
            item = self._layout.takeAt(2)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        display_ranges = ranges[:8]
        for low, high, color in display_ranges:
            chip = QLabel(f"{low:g}–{high:g} {units}")
            chip.setObjectName("rangeChip")
            qcolor = QColor(color)
            if not qcolor.isValid():
                qcolor = QColor("#808080")
            border = qcolor.darker(135).name()
            foreground = self._text_color_for(qcolor.name())
            chip.setStyleSheet(
                "QLabel#rangeChip {"
                f"background:{qcolor.name()}; color:{foreground}; border:1px solid {border}; "
                "border-radius:4px; padding:2px 7px; font-size:8pt; font-weight:900;"
                "}"
            )
            self._layout.insertWidget(max(2, self._layout.count() - 1), chip)
        if len(ranges) > len(display_ranges):
            more = QLabel(f"+{len(ranges) - len(display_ranges)} more")
            more.setObjectName("rangeLegendTitle")
            self._layout.insertWidget(max(2, self._layout.count() - 1), more)


def _clear_plot_items(plot: pg.PlotWidget, items: list[object]) -> None:
    for item in list(items):
        try:
            plot.removeItem(item)
        except Exception:
            pass
    items.clear()


def _plot_range_colored_line(
    plot: pg.PlotWidget,
    x_values: np.ndarray,
    y_values: np.ndarray,
    value_values: np.ndarray,
    ranges: list[tuple[float, float, str]],
    items: list[object],
    width: float = 1.8,
) -> None:
    _clear_plot_items(plot, items)
    x = np.asarray(x_values, dtype=float)
    y = np.asarray(y_values, dtype=float)
    values = np.asarray(value_values, dtype=float)
    valid = np.isfinite(x) & np.isfinite(y) & np.isfinite(values)
    if x.size == 0 or y.size == 0 or values.size == 0:
        return
    if not ranges:
        item = plot.plot(x, y, pen=pg.mkPen("#111111", width=max(width, 1.7)), connect="finite")
        items.append(item)
        return

    # Underlay improves visibility on white grid, especially for yellow/green ranges.
    outline = QColor("#111827")
    outline.setAlpha(135)
    underlay = plot.plot(
        x,
        np.where(valid, y, np.nan),
        pen=pg.mkPen(outline, width=max(width + 1.15, 2.4)),
        connect="finite",
    )
    underlay.setZValue(1)
    items.append(underlay)

    for low, high, color in ranges:
        mask = (values >= low) & (values < high) & valid
        if not np.any(mask):
            continue
        y_masked = np.where(mask, y, np.nan)
        item = plot.plot(x, y_masked, pen=pg.mkPen(color, width=width), connect="finite")
        item.setZValue(2)
        items.append(item)
    below = (values < ranges[0][0]) & valid
    above = (values >= ranges[-1][1]) & valid
    for mask, color in ((below, ranges[0][2]), (above, ranges[-1][2])):
        if np.any(mask):
            y_masked = np.where(mask, y, np.nan)
            item = plot.plot(x, y_masked, pen=pg.mkPen(color, width=width), connect="finite")
            item.setZValue(2)
            items.append(item)


class _RangeEditorDialog(QDialog):
    """Simple range-color editor used by FFT and frequency-time dialogs."""

    def __init__(
        self,
        title: str,
        ranges: list[tuple[float, float, str]],
        defaults: list[tuple[float, float, str]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(500, 360)
        self.setStyleSheet(DIALOG_STYLE)
        self._defaults = _copy_ranges(defaults)
        self.table = QTableWidget(0, 3, self)
        self.table.setHorizontalHeaderLabels(["Min", "Max", "Color"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.cellDoubleClicked.connect(self._choose_cell_color)
        self._populate(ranges)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(QLabel("Set value ranges and colors. Values outside the limits use nearest range color."))
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        add_btn = QPushButton("Add")
        add_btn.setObjectName("analysisButton")
        add_btn.clicked.connect(lambda: self._add_row(0.0, 1.0, "#000000"))
        remove_btn = QPushButton("Remove")
        remove_btn.setObjectName("dangerButton")
        remove_btn.clicked.connect(self._remove_selected)
        default_btn = QPushButton("Load Default")
        default_btn.setObjectName("viewButton")
        default_btn.clicked.connect(lambda: self._populate(self._defaults))
        ok_btn = QPushButton("OK")
        ok_btn.setObjectName("analysisButton")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        for btn in (add_btn, remove_btn, default_btn):
            buttons.addWidget(btn)
        buttons.addStretch(1)
        buttons.addWidget(ok_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)

    def _populate(self, ranges: list[tuple[float, float, str]]) -> None:
        self.table.setRowCount(0)
        for low, high, color in _normalise_ranges(ranges):
            self._add_row(low, high, color)

    def _add_row(self, low: float, high: float, color: str) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(f"{float(low):g}"))
        self.table.setItem(row, 1, QTableWidgetItem(f"{float(high):g}"))
        item = QTableWidgetItem(str(color))
        qcolor = QColor(str(color))
        if qcolor.isValid():
            item.setBackground(qcolor)
        self.table.setItem(row, 2, item)

    def _remove_selected(self) -> None:
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.table.removeRow(row)

    def _choose_cell_color(self, row: int, column: int) -> None:
        if column != 2:
            return
        item = self.table.item(row, column)
        if item is None:
            return
        color = QColorDialog.getColor(QColor(item.text()), self, "Choose range color")
        if color.isValid():
            item.setText(color.name())
            item.setBackground(color)

    def ranges(self) -> list[tuple[float, float, str]]:
        ranges: list[tuple[float, float, str]] = []
        for row in range(self.table.rowCount()):
            try:
                low = float(self.table.item(row, 0).text())
                high = float(self.table.item(row, 1).text())
                color = self.table.item(row, 2).text().strip()
                ranges.append((low, high, color))
            except Exception:
                continue
        return _normalise_ranges(ranges)


class _RangeSelector(QWidget):
    """Preset + editable range coloring control."""

    changed = Signal()

    def __init__(self, mode: str, units: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.mode = mode
        self.units = units
        presets = _RANGE_PRESETS.get(mode, {})
        first_name = next(iter(presets), "Default")
        self._ranges = _copy_ranges(presets.get(first_name, []))
        self.combo = QComboBox(self)
        for name in presets:
            self.combo.addItem(name, name)
        self.combo.currentIndexChanged.connect(self._preset_changed)
        self.edit_button = QPushButton("Edit Ranges", self)
        self.edit_button.setObjectName("analysisButton")
        self.edit_button.clicked.connect(self._edit_ranges)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.addWidget(QLabel("Color by value:"))
        layout.addWidget(self.combo)
        layout.addWidget(self.edit_button)

    def ranges(self) -> list[tuple[float, float, str]]:
        return _copy_ranges(self._ranges)

    def _preset_changed(self) -> None:
        preset_name = str(self.combo.currentData() or self.combo.currentText())
        presets = _RANGE_PRESETS.get(self.mode, {})
        if preset_name in presets:
            self._ranges = _copy_ranges(presets[preset_name])
            self.changed.emit()

    def _edit_ranges(self) -> None:
        preset_name = str(self.combo.currentData() or self.combo.currentText())
        defaults = _RANGE_PRESETS.get(self.mode, {}).get(preset_name, self._ranges)
        dlg = _RangeEditorDialog(f"Edit {self.units} Color Ranges", self._ranges, defaults, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            edited = dlg.ranges()
            if edited:
                self._ranges = edited
                self.changed.emit()


def _colors_to_lut(colors: list[str]) -> np.ndarray:
    stops = []
    for color in colors:
        c = QColor(color)
        stops.append([c.red(), c.green(), c.blue()])
    stops_array = np.asarray(stops, dtype=float)
    positions = np.linspace(0.0, 1.0, len(stops_array))
    x = np.linspace(0.0, 1.0, 256)
    lut = np.vstack([np.interp(x, positions, stops_array[:, channel]) for channel in range(3)]).T
    return np.clip(lut, 0, 255).astype(np.ubyte)


def _palette_lut(name: str, custom_color: str | None = None) -> np.ndarray:
    if name == "Custom" and custom_color:
        base = QColor(custom_color)
        dark = base.darker(265).name()
        mid = base.name()
        light = base.lighter(190).name()
        return _colors_to_lut(["#07131F", dark, mid, light, "#FFFFFF"])
    return _colors_to_lut(_PALETTES.get(name, _PALETTES["TGP Spectral"]))


def _palette_pen(name: str, custom_color: str | None = None) -> str:
    if name == "Custom" and custom_color:
        return custom_color
    colors = _PALETTES.get(name, _PALETTES["TGP Spectral"])
    return colors[min(2, len(colors) - 1)]


class _PaletteSelector(QWidget):
    """Compact palette selector with an optional custom color chosen by the user."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.combo = QComboBox(self)
        for name in list(_PALETTES) + ["Custom"]:
            self.combo.addItem(name, name)
        self.combo.setCurrentText("TGP Spectral")
        self.combo.currentIndexChanged.connect(lambda *_: self.changed.emit())
        self.custom_color = "#0B6FA4"
        self.custom_button = QPushButton("Pick Color", self)
        self.custom_button.setObjectName("analysisButton")
        self.custom_button.clicked.connect(self._choose_color)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(QLabel("Palette:"))
        layout.addWidget(self.combo)
        layout.addWidget(self.custom_button)
        self._refresh_button()

    @property
    def name(self) -> str:
        return str(self.combo.currentData() or "TGP Spectral")

    def lut(self) -> np.ndarray:
        return _palette_lut(self.name, self.custom_color)

    def pen(self) -> str:
        return _palette_pen(self.name, self.custom_color)

    def _refresh_button(self) -> None:
        self.custom_button.setStyleSheet(
            f"QPushButton#analysisButton{{background:{self.custom_color};color:#FFFFFF;border-color:{QColor(self.custom_color).darker(125).name()};}}"
        )

    def _choose_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.custom_color), self, "Choose analysis color")
        if color.isValid():
            self.custom_color = color.name()
            index = self.combo.findData("Custom")
            if index >= 0:
                self.combo.setCurrentIndex(index)
            self._refresh_button()
            self.changed.emit()


def _format_number(value: float, digits: int = 4) -> str:
    if not np.isfinite(value):
        return "—"
    if abs(value) >= 1e5 or (0 < abs(value) < 1e-3):
        return f"{value:.{digits}e}"
    return f"{value:.{digits}g}"


def _metric_card(title: str, value: str, accent: str = "#0A86C7") -> QFrame:
    card = QFrame()
    card.setObjectName("metricCard")
    card.setStyleSheet(f"QFrame#metricCard{{border-left:5px solid {accent};}}")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(10, 7, 10, 7)
    layout.setSpacing(1)
    title_label = QLabel(title)
    title_label.setObjectName("metricTitle")
    value_label = QLabel(value)
    value_label.setObjectName("metricValue")
    layout.addWidget(title_label)
    layout.addWidget(value_label)
    return card


class WaveformPlotWidget(QWidget):
    """Single-trace amplitude-vs-time plot with gain, cursor and sample navigation."""

    cursor_changed = Signal(int, float, float)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(210)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._samples: np.ndarray = np.zeros(0, dtype=np.float64)
        self._sample_interval_ms: float = 1.0
        self._cursor_x: Optional[float] = None
        self._plot_rect = QRectF()
        self._gain = 1.0
        self._selected_sample = 0
        self._polarity = 1
        self._view_start = 0
        self._view_end = 0

    @property
    def samples(self) -> np.ndarray:
        return self._samples

    @property
    def sample_interval_ms(self) -> float:
        return self._sample_interval_ms

    def set_data(self, samples: np.ndarray, sample_interval_ms: float) -> None:
        self._samples = np.nan_to_num(np.asarray(samples, dtype=np.float64))
        self._sample_interval_ms = sample_interval_ms if sample_interval_ms > 0 else 1.0
        self._cursor_x = None
        self._selected_sample = 0
        self._view_start = 0
        self._view_end = int(self._samples.size)
        self.update()

    def set_gain(self, gain: float) -> None:
        self._gain = max(0.01, min(float(gain), 1000.0))
        self.update()

    def set_polarity(self, polarity: int) -> None:
        self._polarity = -1 if int(polarity) < 0 else 1
        self.update()

    def reset_view(self) -> None:
        self._view_start = 0
        self._view_end = int(self._samples.size)
        self.set_selected_sample(self._selected_sample)
        self.update()

    def zoom_around_sample(self, sample_index: int, fraction: float = 0.18) -> None:
        if self._samples.size < 2:
            return
        current_width = max(2, self._view_end - self._view_start)
        width = max(16, int(round(current_width * float(fraction))))
        width = min(width, int(self._samples.size))
        sample_index = max(0, min(int(sample_index), self._samples.size - 1))
        start = max(0, sample_index - width // 2)
        end = min(int(self._samples.size), start + width)
        start = max(0, end - width)
        self._view_start, self._view_end = start, end
        self.set_selected_sample(sample_index)
        self.update()

    def visible_range(self) -> tuple[int, int]:
        start = max(0, min(int(self._view_start), int(self._samples.size)))
        end = max(start + 1, min(int(self._view_end or self._samples.size), int(self._samples.size)))
        return start, end

    def set_selected_sample(self, sample_index: int) -> None:
        if self._samples.size == 0:
            return
        self._selected_sample = max(0, min(int(sample_index), self._samples.size - 1))
        rect = self._compute_plot_rect()
        start, end = self.visible_range()
        if end - start > 1 and start <= self._selected_sample < end:
            self._cursor_x = rect.left() + ((self._selected_sample - start) / max(end - start - 1, 1)) * rect.width()
        else:
            self._cursor_x = None
        self.update()

    def _margins(self) -> tuple[int, int, int, int]:
        return 14, 24, 14, 28

    def _compute_plot_rect(self) -> QRectF:
        left, top, right, bottom = self._margins()
        return QRectF(left, top, max(1, self.width() - left - right), max(1, self.height() - top - bottom))

    def _display_y(self, values: np.ndarray, rect: QRectF, mid_y: float, scale: float) -> np.ndarray:
        clipped = np.clip(values / max(scale, 1e-20), -1.0, 1.0)
        return mid_y - clipped * rect.height() * 0.47

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#FFFFFF"))
        self._plot_rect = self._compute_plot_rect()
        rect = self._plot_rect

        painter.setPen(QPen(QColor("#9A9A9A"), 1))
        painter.drawRect(rect)
        if self._samples.size < 2:
            painter.setPen(QColor("#404040"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "No trace data")
            return

        start, end = self.visible_range()
        visible = self._samples[start:end] * float(self._polarity)
        n = visible.size
        max_abs = float(np.max(np.abs(visible))) if n else 1.0
        if max_abs <= 1e-20:
            max_abs = 1.0
        display_scale = max_abs / self._gain
        mid_y = rect.top() + rect.height() / 2.0

        painter.setPen(QPen(QColor("#CFCFCF"), 1, Qt.PenStyle.SolidLine))
        painter.drawLine(rect.left(), mid_y, rect.right(), mid_y)

        pixel_count = max(2, int(rect.width()))
        if n > pixel_count * 2:
            edges = np.linspace(0, n, pixel_count + 1, dtype=int)
            painter.setPen(QPen(QColor(120, 120, 120, 110), 1))
            for px in range(pixel_count):
                segment = visible[edges[px]:edges[px + 1]]
                if not segment.size:
                    continue
                x_pos = rect.left() + px
                lo, hi = float(np.min(segment)), float(np.max(segment))
                y1, y2 = self._display_y(np.array([hi, lo]), rect, mid_y, display_scale)
                painter.drawLine(x_pos, float(y1), x_pos, float(y2))

        target_points = min(n, max(600, pixel_count * 2))
        indices = np.unique(np.linspace(0, n - 1, target_points).astype(int))
        path = QPainterPath()
        for j, local_index in enumerate(indices):
            x = rect.left() + (float(local_index) / max(n - 1, 1)) * rect.width()
            y = float(self._display_y(np.array([visible[local_index]]), rect, mid_y, display_scale)[0])
            if j == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        painter.setPen(QPen(QColor("#111111"), 1.15))
        painter.drawPath(path)

        total_ms = (self._samples.size - 1) * self._sample_interval_ms
        left_ms = start * self._sample_interval_ms
        right_ms = (end - 1) * self._sample_interval_ms
        painter.setFont(QFont(painter.font().family(), 8))
        painter.setPen(QColor("#0000CC"))
        painter.drawText(int(rect.left()), int(rect.bottom() + 19), f"{left_ms:.1f}mS")
        right_text = f"{right_ms:.1f}mS" if end < self._samples.size else f"{total_ms:.1f}mS"
        painter.drawText(int(rect.right() - painter.fontMetrics().horizontalAdvance(right_text)), int(rect.bottom() + 19), right_text)

        if self._cursor_x is not None and rect.left() <= self._cursor_x <= rect.right():
            painter.setPen(QPen(QColor("#008DD2"), 1, Qt.PenStyle.DashLine))
            painter.drawLine(self._cursor_x, rect.top(), self._cursor_x, rect.bottom())

    def _sample_from_x(self, x: float) -> int:
        rect = self._plot_rect if self._plot_rect.width() > 0 else self._compute_plot_rect()
        x = min(max(x, rect.left()), rect.right())
        fraction = (x - rect.left()) / max(rect.width(), 1.0)
        start, end = self.visible_range()
        return max(0, min(self._samples.size - 1, start + int(round(fraction * max(end - start - 1, 1)))))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._samples.size < 2:
            return
        rect = self._plot_rect
        pos = event.position()
        if not rect.contains(pos):
            return
        sample = self._sample_from_x(pos.x())
        self._selected_sample = sample
        self._cursor_x = pos.x()
        self.cursor_changed.emit(sample, sample * self._sample_interval_ms, float(self._samples[sample]) * float(self._polarity))
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._samples.size:
            sample = self._sample_from_x(event.position().x())
            self._selected_sample = sample
            # Legacy close-up behavior: a left click on any waveform point opens a tighter
            # view around that sample instead of only moving the cursor.
            self.zoom_around_sample(sample, fraction=0.12)
            self.cursor_changed.emit(sample, sample * self._sample_interval_ms, float(self._samples[sample]) * float(self._polarity))
            event.accept()
            return
        super().mousePressEvent(event)


class TraceWaveformDialog(QDialog):
    """Professional SEG-D trace inspector with waveform, FFT and frequency-time analysis."""

    def __init__(self, reader: SegdReader, trace_index: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Trace {trace_index + 1}")
        self.resize(980, 500)
        self.setMinimumSize(780, 420)
        self.setObjectName("traceWaveDialog")
        self.setStyleSheet(DIALOG_STYLE)
        self._reader = reader
        self._trace_index = max(0, min(trace_index, max(0, reader.get_trace_count() - 1)))
        self._gain = 1.0
        self._samples = np.zeros(0, dtype=np.float64)
        self._building_cursor = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        header = QFrame(self)
        header.setObjectName("headerCard")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)
        self.info_label = QLabel("")
        self.info_label.setObjectName("titleLabel")
        self.rms_label = QLabel("")
        self.rms_label.setObjectName("titleLabel")
        header_layout.addWidget(self.info_label, 1)
        header_layout.addWidget(self.rms_label)
        layout.addWidget(header)

        plot_card = QFrame(self)
        plot_card.setObjectName("plotCard")
        plot_layout = QVBoxLayout(plot_card)
        plot_layout.setContentsMargins(5, 5, 5, 5)
        self.plot = WaveformPlotWidget(self)
        self.plot.cursor_changed.connect(self._on_cursor_changed)
        plot_layout.addWidget(self.plot, 1)
        layout.addWidget(plot_card, 1)

        controls = QFrame(self)
        controls.setObjectName("controlGrid")
        controls_grid = QGridLayout(controls)
        controls_grid.setContentsMargins(6, 5, 6, 5)
        controls_grid.setHorizontalSpacing(6)
        controls_grid.setVerticalSpacing(4)

        def group_label(text: str) -> QLabel:
            label = QLabel(text)
            label.setObjectName("controlGroupLabel")
            return label

        def button_group(title: str, items: list[tuple[str, object, str, str]], max_columns: int = 3) -> QFrame:
            frame = QFrame(controls)
            frame.setObjectName("controlGroup")
            grid = QGridLayout(frame)
            grid.setContentsMargins(5, 3, 5, 5)
            grid.setHorizontalSpacing(3)
            grid.setVerticalSpacing(3)
            grid.addWidget(group_label(title), 0, 0, 1, max_columns)
            for index, (label, slot, style_name, tip) in enumerate(items):
                row = 1 + index // max_columns
                col = index % max_columns
                button = self._tool_button(label, slot, style_name, tip)
                button.setFixedSize(42, 23)
                grid.addWidget(button, row, col)
            return frame

        controls_grid.addWidget(
            button_group(
                "Export",
                [
                    ("BMP", self._export_bmp, "exportButton", "Save current trace view as BMP"),
                    ("PRN", self._export_png, "exportButton", "Export current trace view as PNG"),
                    ("No.", self._show_trace_header, "exportButton", "Show detailed trace header"),
                ],
                3,
            ),
            0,
            0,
        )
        controls_grid.addWidget(
            button_group(
                "Analysis",
                [
                    ("FFT", self._show_fft, "analysisButton", "Open FFT trace selection"),
                    ("F/T", self._show_spectrogram, "analysisButton", "Open frequency versus time curve"),
                    ("FT", self._show_ft_analysis, "analysisButton", "Open colour frequency-time analysis"),
                ],
                3,
            ),
            0,
            1,
        )
        controls_grid.addWidget(
            button_group(
                "Trace",
                [
                    ("◀", lambda: self._step_trace(-1), "navigationButton", "Previous trace"),
                    ("▶", lambda: self._step_trace(1), "navigationButton", "Next trace"),
                ],
                2,
            ),
            0,
            2,
        )
        controls_grid.addWidget(
            button_group(
                "View / Gain",
                [
                    ("G−", lambda: self._change_gain(1 / 1.5), "gainButton", "Decrease display gain"),
                    ("G+", lambda: self._change_gain(1.5), "gainButton", "Increase display gain"),
                    ("Z", self._zoom_current, "viewButton", "Zoom around selected sample"),
                    ("1:1", self._normal_view, "viewButton", "Back to normal trace view"),
                    ("REV", self._toggle_reverse, "viewButton", "Reverse waveform polarity"),
                    ("R", self._reset_gain, "gainButton", "Reset display gain"),
                ],
                3,
            ),
            0,
            3,
        )

        cursor_group = QFrame(controls)
        cursor_group.setObjectName("controlGroup")
        cursor_grid = QGridLayout(cursor_group)
        cursor_grid.setContentsMargins(5, 3, 5, 5)
        cursor_grid.setHorizontalSpacing(4)
        cursor_grid.setVerticalSpacing(3)
        cursor_grid.addWidget(group_label("Cursor"), 0, 0, 1, 2)
        cursor_grid.addWidget(QLabel("Time"), 1, 0)
        self.time_spin = QDoubleSpinBox()
        self.time_spin.setDecimals(3)
        self.time_spin.setRange(0.0, 1e9)
        self.time_spin.setKeyboardTracking(False)
        self.time_spin.setFixedWidth(92)
        self.time_spin.valueChanged.connect(self._time_changed)
        cursor_grid.addWidget(self.time_spin, 1, 1)
        cursor_grid.addWidget(QLabel("Sample"), 2, 0)
        self.sample_spin = QSpinBox()
        self.sample_spin.setRange(0, 0)
        self.sample_spin.setKeyboardTracking(False)
        self.sample_spin.setFixedWidth(76)
        self.sample_spin.valueChanged.connect(self._sample_changed)
        cursor_grid.addWidget(self.sample_spin, 2, 1)
        controls_grid.addWidget(cursor_group, 0, 4)
        controls_grid.setColumnStretch(5, 1)
        layout.addWidget(controls)


        footer = QFrame(self)
        footer.setObjectName("headerCard")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(8, 3, 8, 3)
        self.readout_label = QLabel(" ")
        self.readout_label.setStyleSheet("color:#21313D; font-family:Consolas,monospace; font-weight:700;")
        self.gain_label = QLabel("Gain 1.00×")
        self.gain_label.setObjectName("subtleLabel")
        close_btn = QPushButton("Close")
        close_btn.setObjectName("dangerButton")
        close_btn.setFixedSize(68, 26)
        close_btn.clicked.connect(self.close)
        footer_layout.addWidget(self.readout_label, 1)
        footer_layout.addWidget(self.gain_label)
        footer_layout.addWidget(close_btn)
        layout.addWidget(footer)

        self._load_trace()

    def _tool_button(self, text: str, slot, object_name: str, tooltip: str = "") -> QPushButton:
        button = QPushButton(text)
        button.setObjectName(object_name)
        if tooltip:
            button.setToolTip(tooltip)
        button.clicked.connect(slot)
        return button

    def _show_trace_header(self) -> None:
        try:
            info = self._reader.get_trace_info(self._trace_index)
            text = (
                f"Channel {info.trace_number}\n"
                f"Line {info.receiver_line}\n"
                f"Point {info.receiver_point}\n"
                f"FDU {info.receiver_index}\n"
                f"Channel Set {info.channel_set}\n"
                f"Samples {info.sample_count}\n"
                f"Interval {info.sample_interval_ms:g} ms"
            )
        except Exception as error:
            text = str(error)
        QMessageBox.information(self, "Trace Header", text)

    def _toggle_reverse(self) -> None:
        self.plot.set_polarity(-1 if self.plot._polarity > 0 else 1)
        self._set_cursor_sample(self.sample_spin.value())

    def _normal_view(self) -> None:
        self.plot.reset_view()
        self._set_cursor_sample(self.sample_spin.value())

    def _zoom_current(self) -> None:
        self.plot.zoom_around_sample(self.sample_spin.value())
        self._set_cursor_sample(self.sample_spin.value())

    def _load_trace(self) -> None:
        try:
            data = self._reader.read_channel_data((self._trace_index, self._trace_index + 1), 0, None)
        except Exception as error:
            self.info_label.setText(f"Failed to read trace: {error}")
            return
        if data.size == 0:
            self.info_label.setText("Trace contains no samples")
            return

        self._samples = np.asarray(data[0], dtype=np.float64)
        interval = max(float(self._reader.get_sample_interval()), 1e-9)
        self.plot.set_data(self._samples, interval)
        self.plot.set_gain(self._gain)
        self.sample_spin.setRange(0, max(0, self._samples.size - 1))
        self.time_spin.setRange(0.0, max(0.0, (self._samples.size - 1) * interval))

        try:
            info = self._reader.get_trace_info(self._trace_index)
            sensor = getattr(info, "sensor_type", "")
            receiver = getattr(info, "receiver_index", "")
            self.info_label.setText(
                f"Channel {info.trace_number}     Line {info.receiver_line:g}     Point {info.receiver_point:g}"
            )
        except Exception:
            self.info_label.setText(f"Trace {self._trace_index + 1}")

        rms = float(np.sqrt(np.mean(np.square(self._samples))))
        self.rms_label.setText(f"Trace RMS {_format_number(rms, 12)} uV")
        self._set_cursor_sample(0)
        self.setWindowTitle(f"Trace {self._trace_index + 1}")

    def _step_trace(self, step: int) -> None:
        new_index = max(0, min(self._reader.get_trace_count() - 1, self._trace_index + int(step)))
        if new_index != self._trace_index:
            self._trace_index = new_index
            self._load_trace()

    def _change_gain(self, factor: float) -> None:
        self._gain = max(0.01, min(1000.0, self._gain * factor))
        self.plot.set_gain(self._gain)
        self.gain_label.setText(f"Gain {self._gain:.2f}×")

    def _reset_gain(self) -> None:
        self._gain = 1.0
        self.plot.set_gain(1.0)
        self.gain_label.setText("Gain 1.00×")

    def _on_cursor_changed(self, sample: int, time_ms: float, amplitude: float) -> None:
        self.readout_label.setText(f"Sample {sample}   Time {time_ms:.3f} ms   Amplitude {_format_number(amplitude, 7)}")
        self._building_cursor = True
        self.sample_spin.setValue(sample)
        self.time_spin.setValue(time_ms)
        self._building_cursor = False

    def _set_cursor_sample(self, sample: int) -> None:
        if self._samples.size == 0:
            return
        sample = max(0, min(int(sample), self._samples.size - 1))
        interval = self.plot.sample_interval_ms
        self.plot.set_selected_sample(sample)
        self._on_cursor_changed(sample, sample * interval, float(self._samples[sample]) * float(self.plot._polarity))

    def _sample_changed(self, sample: int) -> None:
        if not self._building_cursor:
            self._set_cursor_sample(sample)

    def _time_changed(self, time_ms: float) -> None:
        if not self._building_cursor:
            self._set_cursor_sample(round(time_ms / max(self.plot.sample_interval_ms, 1e-12)))

    def _fft_values(self) -> tuple[np.ndarray, np.ndarray]:
        if self._samples.size < 2:
            return np.zeros(0), np.zeros(0)
        signal = self._samples.astype(float) - float(np.mean(self._samples))
        window = np.hanning(signal.size)
        spectrum = np.fft.rfft(signal * window)
        amplitude = 2.0 * np.abs(spectrum) / max(float(np.sum(window)), 1e-12)
        dt_seconds = self.plot.sample_interval_ms / 1000.0
        frequency = np.fft.rfftfreq(signal.size, d=max(dt_seconds, 1e-12))
        return frequency, amplitude

    def _spectral_summary(self) -> dict[str, float]:
        x = self._samples.astype(float)
        frequency, amplitude = self._fft_values()
        usable = frequency > 0
        if np.any(usable):
            power = amplitude[usable] ** 2
            f = frequency[usable]
            dominant = float(f[int(np.argmax(power))])
            denom = max(float(np.sum(power)), 1e-20)
            centroid = float(np.sum(f * power) / denom)
            bandwidth = float(np.sqrt(np.sum(((f - centroid) ** 2) * power) / denom))
        else:
            dominant = centroid = bandwidth = 0.0
        rms = float(np.sqrt(np.mean(x ** 2))) if x.size else 0.0
        peak = float(np.max(np.abs(x))) if x.size else 0.0
        crest = peak / max(rms, 1e-20)
        zero_crossings = int(np.count_nonzero(np.diff(np.signbit(x - np.mean(x))))) if x.size > 1 else 0
        duration_s = max((x.size - 1) * self.plot.sample_interval_ms / 1000.0, 1e-12)
        return {
            "samples": float(x.size),
            "sample_interval_ms": float(self.plot.sample_interval_ms),
            "duration_s": duration_s,
            "mean": float(np.mean(x)) if x.size else 0.0,
            "std": float(np.std(x)) if x.size else 0.0,
            "rms": rms,
            "peak": peak,
            "crest": crest,
            "dominant": dominant,
            "centroid": centroid,
            "bandwidth": bandwidth,
            "zcr": zero_crossings / duration_s,
        }

    def _show_fft(self) -> None:
        """Legacy-style FFT Trace Selection with working graphic toggles and selection controls."""
        trace_count = max(1, int(self._reader.get_trace_count()))
        sample_interval = max(float(self.plot.sample_interval_ms), 1e-12)
        total_samples = max(1, int(getattr(self._reader, "get_sample_count", lambda: self._samples.size)() or self._samples.size))
        total_end_time = max(0.0, (total_samples - 1) * sample_interval)

        dlg = QDialog(self)
        dlg.setWindowTitle("Trace Selection")
        dlg.resize(930, 610)
        dlg.setMinimumSize(820, 520)
        dlg.setStyleSheet(DIALOG_STYLE + """
            QDialog { background:#F3F3F3; }
            QLineEdit#legacyValue {
                background:#FFFFFF; border:1px solid #777777; border-radius:0px;
                padding:1px 4px; min-height:20px; max-height:22px;
                font-size:8.5pt; font-weight:700; color:#111111;
            }
            QCheckBox { color:#202020; font-size:8.5pt; font-weight:500; spacing:4px; }
            QCheckBox::indicator { width:15px; height:15px; border:1px solid #777777; background:#FFFFFF; }
            QCheckBox::indicator:checked { background:#FFFFFF; image:none; }
            QCheckBox::indicator:checked:pressed { background:#E8E8E8; }
            QCheckBox::indicator:checked { border:1px solid #555555; }
            QCheckBox::indicator:checked:!disabled { background:qradialgradient(cx:0.5, cy:0.5, radius:0.45, fx:0.5, fy:0.5, stop:0 #111111, stop:0.44 #111111, stop:0.46 #FFFFFF, stop:1 #FFFFFF); }
            QSpinBox#legacySpin, QDoubleSpinBox#legacySpin {
                background:#FFFFFF; border:1px solid #777777; border-radius:0px;
                padding:1px 3px; min-height:20px; max-height:22px;
                font-size:8.5pt; font-weight:700; color:#111111;
            }
            QPushButton#legacyButton, QPushButton#legacyCloseButton, QPushButton#legacyBmpButton, QPushButton#legacyPrintButton {
                border:1px solid #6B7280; border-radius:3px;
                min-height:28px; max-height:32px; padding:2px 6px; font-size:9pt; font-weight:700;
            }
            QPushButton#legacyButton { background:#F7F7F7; color:#202020; }
            QPushButton#legacyCloseButton { background:#FFF1F2; color:#9F1239; border-color:#FDA4AF; }
            QPushButton#legacyBmpButton { background:#E0F2FE; color:#075985; border-color:#7DD3FC; }
            QPushButton#legacyPrintButton { background:#ECFDF5; color:#065F46; border-color:#6EE7B7; }
            QPushButton#legacyButton:hover, QPushButton#legacyCloseButton:hover, QPushButton#legacyBmpButton:hover, QPushButton#legacyPrintButton:hover {
                background:#FFFFFF; border-color:#0078D4;
            }
            QPushButton#legacyNav {
                background:#FEF3C7; color:#7C2D12; border:1px solid #F59E0B; border-radius:4px;
                min-width:48px; min-height:36px; font-size:18pt; font-weight:900;
            }
            QPushButton#legacyNav:hover { background:#FFFBEB; border-color:#EA580C; color:#9A3412; }
            QPushButton#legacyNav:pressed { background:#FED7AA; border-color:#C2410C; }
            QLabel#legacyText { color:#202020; font-size:8.5pt; font-weight:500; }
        """)

        root = QHBoxLayout(dlg)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(7)

        # Left-side legacy controls: Close / BMP / Print and On Graphic toggles.
        left_panel = QFrame(dlg)
        left_panel.setObjectName("controlGroup")
        left_panel.setFixedWidth(116)
        left = QVBoxLayout(left_panel)
        left.setContentsMargins(6, 10, 6, 8)
        left.setSpacing(8)

        close_top = QPushButton("Close")
        close_top.setObjectName("legacyCloseButton")
        close_top.clicked.connect(dlg.accept)
        bmp_btn = QPushButton("BMP")
        bmp_btn.setObjectName("legacyBmpButton")
        print_btn = QPushButton("Print")
        print_btn.setObjectName("legacyPrintButton")
        left.addWidget(close_top)
        left.addWidget(bmp_btn)
        left.addWidget(print_btn)
        left.addSpacing(18)

        graphic_box = QGroupBox("On Graphic")
        graphic_box.setStyleSheet("QGroupBox{font-size:8.5pt;font-weight:600;color:#202020;border:1px solid #B8B8B8;margin-top:8px;padding-top:8px;background:#F7F7F7;}")
        graphic_layout = QVBoxLayout(graphic_box)
        graphic_layout.setContentsMargins(7, 8, 7, 7)
        graphic_layout.setSpacing(7)
        title_check = QCheckBox("Title")
        db_scale_check = QCheckBox("dB Scale")
        values_check = QCheckBox("Values")
        for check in (title_check, db_scale_check, values_check):
            check.setChecked(True)
            graphic_layout.addWidget(check)
        left.addWidget(graphic_box)
        left.addStretch(1)
        root.addWidget(left_panel)

        main = QVBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(6)
        root.addLayout(main, 1)

        def value_field(width: int = 92) -> QLineEdit:
            field = QLineEdit()
            field.setObjectName("legacyValue")
            field.setReadOnly(True)
            field.setFixedWidth(width)
            return field

        top = QHBoxLayout()
        top.setSpacing(8)
        top.addStretch(1)
        lbl = QLabel("Selection RMS")
        lbl.setObjectName("legacyText")
        top.addWidget(lbl)
        rms_edit = value_field(105)
        top.addWidget(rms_edit)
        top.addSpacing(35)
        lbl = QLabel("Selection Peak")
        lbl.setObjectName("legacyText")
        top.addWidget(lbl)
        peak_edit = value_field(105)
        top.addWidget(peak_edit)
        top.addSpacing(35)
        lbl = QLabel("Cursor")
        lbl.setObjectName("legacyText")
        top.addWidget(lbl)
        cursor_edit = value_field(92)
        top.addWidget(cursor_edit)
        main.addLayout(top)

        range_selector = _RangeSelector("fft_db", "dB", dlg)
        range_row = QHBoxLayout()
        range_row.setSpacing(6)
        range_row.addWidget(range_selector)
        range_row.addStretch(1)
        main.addLayout(range_row)
        legend = _RangeLegend("dB Colour Ranges", dlg)
        main.addWidget(legend)

        plot = pg.PlotWidget()
        plot.setBackground("#FFFFFF")
        plot.setLabel("bottom", "Frequency", units="Hz")
        plot.setLabel("left", "dB")
        plot.showGrid(x=False, y=False)
        plot.setMenuEnabled(False)
        try:
            plot.getPlotItem().hideButtons()
        except Exception:
            pass
        main.addWidget(plot, 1)

        colored_items: list[object] = []
        grid_items: list[object] = []
        info_text = pg.TextItem(color="#202020", anchor=(1, 0))
        info_text.setZValue(30)
        plot.addItem(info_text)
        cursor_line = pg.InfiniteLine(pos=0.0, angle=90, pen=pg.mkPen("#FF0000", width=1.4))
        cursor_line.setZValue(20)
        plot.addItem(cursor_line)

        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        main.addLayout(bottom)

        def make_spin(minimum: int, maximum: int, value: int, width: int = 78) -> QSpinBox:
            spin = QSpinBox()
            spin.setObjectName("legacySpin")
            spin.setRange(minimum, maximum)
            spin.setValue(value)
            spin.setKeyboardTracking(False)
            spin.setFixedWidth(width)
            return spin

        def make_time(value: float, width: int = 96) -> QDoubleSpinBox:
            spin = QDoubleSpinBox()
            spin.setObjectName("legacySpin")
            spin.setRange(0.0, max(0.0, total_end_time))
            spin.setDecimals(1)
            spin.setSingleStep(sample_interval)
            spin.setKeyboardTracking(False)
            spin.setValue(value)
            spin.setFixedWidth(width)
            return spin

        first_trace_spin = make_spin(1, trace_count, self._trace_index + 1)
        last_trace_spin = make_spin(1, trace_count, self._trace_index + 1)
        minimum_time_spin = make_time(0.0)
        maximum_time_spin = make_time(total_end_time)

        trace_form = QGridLayout()
        trace_form.setHorizontalSpacing(5)
        trace_form.setVerticalSpacing(4)
        for row, (caption, widget) in enumerate((("First Trace", first_trace_spin), ("Last Trace", last_trace_spin))):
            lab = QLabel(caption)
            lab.setObjectName("legacyText")
            trace_form.addWidget(lab, row, 0)
            trace_form.addWidget(widget, row, 1)
        time_form = QGridLayout()
        time_form.setHorizontalSpacing(5)
        time_form.setVerticalSpacing(4)
        for row, (caption, widget) in enumerate((("Minimum Time", minimum_time_spin), ("Maximum Time", maximum_time_spin))):
            lab = QLabel(caption)
            lab.setObjectName("legacyText")
            time_form.addWidget(lab, row, 0)
            time_form.addWidget(widget, row, 1)
        bottom.addLayout(trace_form)
        bottom.addSpacing(48)
        bottom.addLayout(time_form)
        bottom.addStretch(1)
        prev_btn = QPushButton("<")
        prev_btn.setObjectName("legacyNav")
        prev_btn.setToolTip("Previous trace: decreases First/Last Trace and redraws FFT from the actual SEG-D trace data")
        prev_btn.setAutoRepeat(True)
        prev_btn.setAutoRepeatDelay(350)
        prev_btn.setAutoRepeatInterval(90)
        next_btn = QPushButton(">")
        next_btn.setObjectName("legacyNav")
        next_btn.setToolTip("Next trace: increases First/Last Trace and redraws FFT from the actual SEG-D trace data")
        next_btn.setAutoRepeat(True)
        next_btn.setAutoRepeatDelay(350)
        next_btn.setAutoRepeatInterval(90)
        bottom.addWidget(prev_btn)
        bottom.addWidget(next_btn)

        state: dict[str, object] = {}
        updating = {"active": False}

        def _selection_arrays() -> tuple[np.ndarray, np.ndarray, np.ndarray, float, float, int, int, float, float]:
            first = max(1, min(trace_count, int(first_trace_spin.value())))
            last = max(1, min(trace_count, int(last_trace_spin.value())))
            if last < first:
                last = first
                if not updating["active"]:
                    updating["active"] = True
                    last_trace_spin.setValue(last)
                    updating["active"] = False
            start_time = max(0.0, min(float(minimum_time_spin.value()), total_end_time))
            end_time = max(0.0, min(float(maximum_time_spin.value()), total_end_time))
            if end_time <= start_time:
                end_time = min(total_end_time, start_time + sample_interval)
                if not updating["active"]:
                    updating["active"] = True
                    maximum_time_spin.setValue(end_time)
                    updating["active"] = False
            start_sample = max(0, min(total_samples - 1, int(round(start_time / sample_interval))))
            end_sample = max(start_sample + 2, min(total_samples, int(round(end_time / sample_interval)) + 1))
            try:
                # Current SegdReader signature is read_channel_data(trace_range, channel, sample_range).
                # The previous call accidentally passed start/end samples as channel/sample_range,
                # so the exception path used self._samples and every arrow-selected trace showed
                # the same FFT. Read the selected SEG-D trace window directly and keep the
                # fallback only for older/custom readers.
                if hasattr(self._reader, "read_channel_data"):
                    selection = self._reader.read_channel_data((first - 1, last), 0, (start_sample, end_sample))
                else:
                    selection = self._reader.read_trace_window((first - 1, last), (start_sample, end_sample))[:, 0, :]
            except TypeError:
                try:
                    selection = self._reader.read_trace_window((first - 1, last), (start_sample, end_sample))[:, 0, :]
                except Exception:
                    selection = self._samples[start_sample:end_sample][None, :]
            except Exception:
                selection = self._samples[start_sample:end_sample][None, :]
            selection = np.asarray(selection, dtype=np.float64)
            if selection.ndim == 1:
                selection = selection[None, :]
            selection = np.nan_to_num(selection)
            if selection.size == 0 or selection.shape[-1] < 2:
                selection = np.zeros((1, 2), dtype=np.float64)
            signal = np.nanmean(selection, axis=0)
            signal = signal - float(np.mean(signal))
            window = np.hanning(signal.size)
            spectrum = np.fft.rfft(signal * window)
            amplitude = 2.0 * np.abs(spectrum) / max(float(np.sum(window)), 1e-12)
            frequency = np.fft.rfftfreq(signal.size, d=sample_interval / 1000.0)
            max_amp = max(float(np.nanmax(amplitude)), 1e-20)
            db_values = 20.0 * np.log10(np.maximum(amplitude, 1e-20) / max_amp)
            rms = float(np.sqrt(np.mean(np.square(selection)))) if selection.size else 0.0
            peak = float(np.max(np.abs(selection))) if selection.size else 0.0
            return frequency, db_values, selection, rms, peak, first, last, start_time, end_time

        def add_legacy_grid(x_min: float, x_max: float, y_min: float, y_max: float) -> None:
            for item in list(grid_items):
                try:
                    plot.removeItem(item)
                except Exception:
                    pass
            grid_items.clear()
            # Red dashed dB scale lines like the legacy 408 viewer.
            start_db = int(np.floor(y_min / 6.0) * 6)
            for y_value in range(start_db, 1, 6):
                if y_min <= y_value <= y_max:
                    line = pg.InfiniteLine(pos=float(y_value), angle=0, pen=pg.mkPen("#FF0000", width=0.8, style=Qt.PenStyle.DashLine))
                    line.setZValue(-10)
                    plot.addItem(line)
                    grid_items.append(line)
            if x_max > x_min:
                step = 25.0 if x_max <= 300 else max(25.0, round((x_max - x_min) / 10.0, -1))
                x_value = np.ceil(x_min / step) * step
                while x_value <= x_max:
                    line = pg.InfiniteLine(pos=float(x_value), angle=90, pen=pg.mkPen("#222222", width=0.6, style=Qt.PenStyle.DashLine))
                    line.setZValue(-11)
                    plot.addItem(line)
                    grid_items.append(line)
                    x_value += step

        def set_overlay_text(first: int, last: int, start_time: float, end_time: float, rms: float, peak: float) -> None:
            text = (
                f"First Trace&nbsp;&nbsp;{first}<br>"
                f"Last Trace&nbsp;&nbsp;{last}<br>"
                f"Start Time&nbsp;&nbsp;{start_time:g}<br>"
                f"End Time&nbsp;&nbsp;{end_time:g}<br>"
                f"RMS&nbsp;&nbsp;{_format_number(rms, 4)}<br>"
                f"Peak&nbsp;&nbsp;{_format_number(peak, 4)}"
            )
            info_text.setHtml(f"<div style='font-size:9pt;color:#202020;background:rgba(255,255,255,160);'>{text}</div>")
            info_text.setVisible(values_check.isChecked())

        def update_cursor(freq: float) -> None:
            frequency = np.asarray(state.get("frequency", np.zeros(0)), dtype=float)
            db_values = np.asarray(state.get("db", np.zeros(0)), dtype=float)
            if not frequency.size or not db_values.size:
                return
            freq = max(float(frequency[0]), min(float(freq), float(frequency[-1])))
            level = float(np.interp(freq, frequency, db_values))
            color = _range_color(level, range_selector.ranges(), "#FF0000")
            cursor_line.setPen(pg.mkPen(color, width=1.5))
            cursor_line.setPos(freq)
            state["cursor_frequency"] = freq
            cursor_edit.setText(f"{freq:.1f} Hz")
            cursor_edit.setToolTip(f"Frequency {freq:.3f} Hz\nLevel {level:.3f} dB")

        def refresh_graphic_options() -> None:
            if title_check.isChecked():
                plot.setTitle("<span style='color:#0000CC;font-weight:900;font-size:13pt'>FFT Trace Selection</span>")
            else:
                plot.setTitle("")
            plot.showAxis("left", db_scale_check.isChecked())
            if db_scale_check.isChecked():
                plot.setLabel("left", "dB")
            else:
                plot.setLabel("left", "")
            info_text.setVisible(values_check.isChecked())

        def redraw() -> None:
            if updating["active"]:
                return
            frequency, db_values, _selection, rms, peak, first, last, start_time, end_time = _selection_arrays()
            state["frequency"] = frequency
            state["db"] = db_values
            rms_edit.setText(_format_number(rms, 4))
            peak_edit.setText(_format_number(peak, 4))
            x_min = float(np.nanmin(frequency)) if frequency.size else 0.0
            x_max = float(np.nanmax(frequency)) if frequency.size else 1.0
            y_min = min(-186.0, float(np.nanmin(db_values)) - 3.0) if db_values.size else -186.0
            y_max = 3.0
            plot.setXRange(x_min, x_max, padding=0.02)
            plot.setYRange(y_min, y_max, padding=0.02)
            add_legacy_grid(x_min, x_max, y_min, y_max)
            _plot_range_colored_line(plot, frequency, db_values, db_values, range_selector.ranges(), colored_items, width=2.1)
            legend.set_ranges(range_selector.ranges(), "dB")
            set_overlay_text(first, last, start_time, end_time, rms, peak)
            info_text.setPos(x_min + (x_max - x_min) * 0.985, y_max - 3.0)
            cursor_line.setZValue(20)
            info_text.setZValue(30)
            refresh_graphic_options()
            dominant_freq = float(frequency[int(np.argmax(db_values))]) if frequency.size and db_values.size else 0.0
            update_cursor(dominant_freq)

        def set_trace_window(first: int, last: int) -> None:
            first = max(1, min(trace_count, first))
            last = max(1, min(trace_count, last))
            if last < first:
                last = first
            updating["active"] = True
            first_trace_spin.setValue(first)
            last_trace_spin.setValue(last)
            updating["active"] = False
            redraw()

        def step_selection(step: int) -> None:
            # Legacy bottom arrows: increment/decrement the selected trace number(s) and
            # redraw from that exact SEG-D trace data. This is navigation, not frequency zoom.
            width = max(0, int(last_trace_spin.value()) - int(first_trace_spin.value()))
            max_first = max(1, trace_count - width)
            first = int(first_trace_spin.value()) + int(step)
            first = max(1, min(max_first, first))
            last = min(trace_count, first + width)
            set_trace_window(first, last)
            update_cursor(float(state.get("cursor_frequency", 0.0) or 0.0))

        def save_bmp() -> None:
            path, _ = QFileDialog.getSaveFileName(
                dlg,
                "Export FFT Bitmap",
                str(Path.home() / f"fft_trace_{first_trace_spin.value()}.bmp"),
                "Bitmap Image (*.bmp);;PNG Image (*.png)",
            )
            if path:
                output = Path(path)
                if not output.suffix:
                    output = output.with_suffix(".bmp")
                plot.grab().save(str(output))

        def print_plot() -> None:
            try:
                from PySide6.QtPrintSupport import QPrintDialog, QPrinter

                printer = QPrinter(QPrinter.PrinterMode.HighResolution)
                dialog = QPrintDialog(printer, dlg)
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    pixmap = plot.grab()
                    painter = QPainter(printer)
                    rect = painter.viewport()
                    scaled = pixmap.scaled(rect.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    x = rect.x() + (rect.width() - scaled.width()) // 2
                    y = rect.y() + (rect.height() - scaled.height()) // 2
                    painter.drawPixmap(x, y, scaled)
                    painter.end()
            except Exception as error:
                QMessageBox.warning(dlg, "Print", f"Could not print FFT view: {error}")

        def mouse_moved(pos) -> None:
            if plot.sceneBoundingRect().contains(pos):
                mapped = plot.plotItem.vb.mapSceneToView(pos)
                update_cursor(mapped.x())

        first_trace_spin.valueChanged.connect(lambda value: set_trace_window(int(value), max(int(value), last_trace_spin.value())))
        last_trace_spin.valueChanged.connect(lambda value: set_trace_window(first_trace_spin.value(), int(value)))
        minimum_time_spin.valueChanged.connect(lambda _value: redraw())
        maximum_time_spin.valueChanged.connect(lambda _value: redraw())
        range_selector.changed.connect(redraw)
        title_check.toggled.connect(refresh_graphic_options)
        db_scale_check.toggled.connect(refresh_graphic_options)
        values_check.toggled.connect(refresh_graphic_options)
        prev_btn.clicked.connect(lambda: step_selection(-1))
        next_btn.clicked.connect(lambda: step_selection(1))
        bmp_btn.clicked.connect(save_bmp)
        print_btn.clicked.connect(print_plot)
        plot.scene().sigMouseMoved.connect(mouse_moved)

        redraw()
        dlg.exec()

    def _show_spectrogram(self) -> None:
        """Legacy F vs T: dominant frequency tracked through time with value-range colors."""
        if self._samples.size < 16:
            QMessageBox.information(self, "F vs T", "The trace is too short for frequency-time analysis.")
            return
        try:
            from scipy.signal import spectrogram
        except Exception as error:
            QMessageBox.warning(self, "F vs T", f"SciPy spectrogram support is unavailable: {error}")
            return
        fs = 1000.0 / max(self.plot.sample_interval_ms, 1e-12)
        base = max(32, self._samples.size // 10)
        nperseg = min(512, max(32, 2 ** int(np.floor(np.log2(base)))))
        nperseg = min(nperseg, self._samples.size)
        noverlap = min(nperseg - 1, int(nperseg * 0.80))
        f, t, power = spectrogram(
            self._samples - np.mean(self._samples),
            fs=fs,
            window="hann",
            nperseg=nperseg,
            noverlap=noverlap,
            detrend="constant",
            scaling="density",
            mode="psd",
        )
        if not power.size or not t.size or not f.size:
            QMessageBox.information(self, "F vs T", "No valid frequency-time samples were produced for this trace.")
            return
        dominant = f[np.argmax(power, axis=0)]
        time_ms = t * 1000.0
        dlg = QDialog(self)
        dlg.setWindowTitle("Frequency vs Time")
        dlg.resize(920, 380)
        dlg.setStyleSheet(DIALOG_STYLE)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        top = QHBoxLayout()
        cursor_readout = QLabel("Cursor Time — ms    Frequency — Hz")
        cursor_readout.setObjectName("titleLabel")
        top.addWidget(cursor_readout)
        top.addStretch(1)
        range_selector = _RangeSelector("frequency_hz", "Hz", dlg)
        top.addWidget(range_selector)
        lay.addLayout(top)
        legend = _RangeLegend("Frequency Colour Ranges", dlg)
        lay.addWidget(legend)

        plot = pg.PlotWidget()
        plot.setBackground("#FFFFFF")
        plot.setTitle("<span style='color:#202020;font-weight:700'>Frequency vs Time</span>")
        plot.setLabel("bottom", "Time", units="ms")
        plot.setLabel("left", "Frequency", units="Hz")
        plot.showGrid(x=True, y=True, alpha=0.55)
        colored_items: list[object] = []
        cursor_line = pg.InfiniteLine(angle=90, pen=pg.mkPen("#0048FF", width=1.4, style=Qt.PenStyle.DashLine))
        cursor_line.setZValue(20)
        plot.addItem(cursor_line)
        lay.addWidget(plot, 1)

        def apply_ranges() -> None:
            ranges = range_selector.ranges()
            _plot_range_colored_line(plot, time_ms, dominant, dominant, ranges, colored_items, width=2.4)
            legend.set_ranges(ranges, "Hz")
            cursor_line.setZValue(20)
            plot.repaint()

        def update_cursor(time_value: float) -> None:
            if not time_ms.size:
                return
            time_value = max(float(time_ms[0]), min(float(time_value), float(time_ms[-1])))
            freq_value = float(np.interp(time_value, time_ms, dominant))
            color = _range_color(freq_value, range_selector.ranges(), "#0048FF")
            cursor_line.setPen(pg.mkPen(color, width=1.6, style=Qt.PenStyle.DashLine))
            cursor_line.setPos(time_value)
            cursor_readout.setText(f"Cursor Time {time_value:.1f} ms    Frequency {freq_value:.2f} Hz")

        def mouse_moved(pos) -> None:
            if plot.sceneBoundingRect().contains(pos):
                mapped = plot.plotItem.vb.mapSceneToView(pos)
                update_cursor(mapped.x())

        plot.scene().sigMouseMoved.connect(mouse_moved)
        range_selector.changed.connect(lambda: (apply_ranges(), update_cursor(cursor_line.value())))
        apply_ranges()
        update_cursor(float(time_ms[0]))

        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton("Close")
        close.setObjectName("dangerButton")
        close.clicked.connect(dlg.accept)
        row.addWidget(close)
        lay.addLayout(row)
        dlg.exec()

    def _show_ft_analysis(self) -> None:
        """Legacy FT Analysis: classified colour frequency-time amplitude panel."""
        if self._samples.size < 16:
            return
        try:
            from scipy.signal import spectrogram
        except Exception as error:
            QMessageBox.warning(self, "FT Analysis", f"SciPy spectrogram support is unavailable: {error}")
            return
        fs = 1000.0 / max(self.plot.sample_interval_ms, 1e-12)
        base = max(32, self._samples.size // 10)
        nperseg = min(512, max(32, 2 ** int(np.floor(np.log2(base)))))
        nperseg = min(nperseg, self._samples.size)
        noverlap = min(nperseg - 1, int(nperseg * 0.80))
        f, t, power = spectrogram(
            self._samples - np.mean(self._samples),
            fs=fs,
            window="hann",
            nperseg=nperseg,
            noverlap=noverlap,
            detrend="constant",
            scaling="density",
            mode="psd",
        )
        db = 10.0 * np.log10(np.maximum(power, np.finfo(float).tiny))
        if not db.size:
            return
        max_db = float(np.nanmax(db))
        db_relative = db - max_db

        dlg = QDialog(self)
        dlg.setWindowTitle("FT Analysis")
        dlg.resize(960, 390)
        dlg.setStyleSheet(DIALOG_STYLE)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        top = QHBoxLayout()
        cursor_readout = QLabel("Cursor Time — ms    Frequency — Hz    Level — dB")
        cursor_readout.setObjectName("titleLabel")
        top.addWidget(cursor_readout)
        top.addStretch(1)
        range_selector = _RangeSelector("fft_db", "dB", dlg)
        top.addWidget(range_selector)
        lay.addLayout(top)
        legend = _RangeLegend("dB Colour Ranges", dlg)
        lay.addWidget(legend)

        plot = pg.PlotWidget()
        plot.setBackground("#BFBFBF")
        plot.setTitle("<span style='color:#202020;font-weight:700'>Frequency-Time Analysis</span>")
        plot.setLabel("bottom", "Time", units="ms")
        plot.setLabel("left", "Frequency", units="Hz")
        plot.showGrid(x=True, y=True, alpha=0.30)
        image = pg.ImageItem()
        try:
            image.setOpts(axisOrder="row-major")
            image.setOpts(autoDownsample=False)
        except Exception:
            pass
        if f.size > 1 and t.size > 1:
            image.setRect(
                QRectF(
                    float(t[0] * 1000.0),
                    float(f[0]),
                    max(float((t[-1] - t[0]) * 1000.0), self.plot.sample_interval_ms),
                    max(float(f[-1] - f[0]), 1.0),
                )
            )
        plot.addItem(image)
        time_line = pg.InfiniteLine(angle=90, pen=pg.mkPen("#FFFFFF", width=1.2, style=Qt.PenStyle.DashLine))
        freq_line = pg.InfiniteLine(angle=0, pen=pg.mkPen("#FFFFFF", width=1.2, style=Qt.PenStyle.DashLine))
        time_line.setZValue(20)
        freq_line.setZValue(20)
        plot.addItem(time_line)
        plot.addItem(freq_line)
        lay.addWidget(plot, 1)

        row = QHBoxLayout()
        row.addWidget(QLabel("Time"))
        self.ft_time_readout = QDoubleSpinBox()
        self.ft_time_readout.setRange(0.0, max(0.0, (self._samples.size - 1) * self.plot.sample_interval_ms))
        self.ft_time_readout.setValue(float(self.sample_spin.value()) * self.plot.sample_interval_ms)
        self.ft_time_readout.setFixedWidth(90)
        row.addWidget(self.ft_time_readout)
        row.addWidget(QLabel("Sample"))
        self.ft_sample_readout = QSpinBox()
        self.ft_sample_readout.setRange(0, max(0, self._samples.size - 1))
        self.ft_sample_readout.setValue(int(self.sample_spin.value()))
        self.ft_sample_readout.setFixedWidth(74)
        row.addWidget(self.ft_sample_readout)
        row.addStretch(1)
        close = QPushButton("Close")
        close.setObjectName("dangerButton")
        close.clicked.connect(dlg.accept)
        row.addWidget(close)
        lay.addLayout(row)

        time_axis_ms = t * 1000.0

        def apply_ranges() -> None:
            ranges = range_selector.ranges()
            classified = _range_index_map(db_relative, ranges)
            image.setLookupTable(_range_lut(ranges))
            image.setImage(classified.T, autoLevels=False, levels=(0.0, max(1.0, float(len(ranges) - 1))))
            legend.set_ranges(ranges, "dB")
            plot.repaint()

        def update_cursor(time_value: float, freq_value: float) -> None:
            if not time_axis_ms.size or not f.size:
                return
            time_value = max(float(time_axis_ms[0]), min(float(time_value), float(time_axis_ms[-1])))
            freq_value = max(float(f[0]), min(float(freq_value), float(f[-1])))
            time_idx = int(np.argmin(np.abs(time_axis_ms - time_value)))
            freq_idx = int(np.argmin(np.abs(f - freq_value)))
            level = float(db_relative[freq_idx, time_idx])
            color = _range_color(level, range_selector.ranges(), "#FFFFFF")
            line_pen = pg.mkPen(color, width=1.4, style=Qt.PenStyle.DashLine)
            time_line.setPen(line_pen)
            freq_line.setPen(line_pen)
            time_line.setPos(time_value)
            freq_line.setPos(freq_value)
            sample = int(round(time_value / max(self.plot.sample_interval_ms, 1e-12)))
            sample = max(0, min(sample, max(0, self._samples.size - 1)))
            self.ft_time_readout.blockSignals(True)
            self.ft_sample_readout.blockSignals(True)
            self.ft_time_readout.setValue(time_value)
            self.ft_sample_readout.setValue(sample)
            self.ft_time_readout.blockSignals(False)
            self.ft_sample_readout.blockSignals(False)
            cursor_readout.setText(f"Cursor Time {time_value:.1f} ms    Frequency {freq_value:.2f} Hz    Level {level:.1f} dB")

        def mouse_moved(pos) -> None:
            if plot.sceneBoundingRect().contains(pos):
                mapped = plot.plotItem.vb.mapSceneToView(pos)
                update_cursor(mapped.x(), mapped.y())

        def time_spin_changed(value: float) -> None:
            update_cursor(value, float(freq_line.value()))

        def sample_spin_changed(value: int) -> None:
            update_cursor(float(value) * self.plot.sample_interval_ms, float(freq_line.value()))

        plot.scene().sigMouseMoved.connect(mouse_moved)
        self.ft_time_readout.valueChanged.connect(time_spin_changed)
        self.ft_sample_readout.valueChanged.connect(sample_spin_changed)
        range_selector.changed.connect(lambda: (apply_ranges(), update_cursor(float(time_line.value()), float(freq_line.value()))))
        apply_ranges()
        initial_time = float(self.sample_spin.value()) * self.plot.sample_interval_ms
        initial_freq = float(f[min(len(f) - 1, max(0, int(len(f) * 0.25)))])
        update_cursor(initial_time, initial_freq)
        dlg.exec()

    def _save_plot(self, suffix: str, filter_text: str) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Trace Image",
            str(Path.home() / f"trace_{self._trace_index + 1}{suffix}"),
            filter_text,
        )
        if path:
            output = Path(path)
            if not output.suffix:
                output = output.with_suffix(suffix)
            self.plot.grab().save(str(output))

    def _export_bmp(self) -> None:
        self._save_plot(".bmp", "Bitmap Image (*.bmp)")

    def _export_png(self) -> None:
        self._save_plot(".png", "PNG Image (*.png)")
