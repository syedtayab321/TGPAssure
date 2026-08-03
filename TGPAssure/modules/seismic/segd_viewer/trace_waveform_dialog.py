from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QColorDialog,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
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
    QDialog { background:#EEF4F8; }
    QFrame#headerCard, QFrame#metricCard, QFrame#plotCard { background:#FFFFFF; border:1px solid #D5E1EA; border-radius:8px; }
    QLabel { background:transparent; }
    QLabel#titleLabel { color:#102A3D; font-size:13px; font-weight:900; }
    QLabel#subtleLabel { color:#607486; font-size:10px; }
    QLabel#metricTitle { color:#607486; font-size:10px; font-weight:800; }
    QLabel#metricValue { color:#102A3D; font-size:15px; font-weight:900; }
    QPushButton { min-height:27px; padding:4px 12px; border-radius:6px; border:1px solid #9FB2C3; background:#FFFFFF; font-weight:700; color:#173B53; }
    QPushButton:hover { background:#E2F0FA; border-color:#3A8BC2; }
    QPushButton#analysisButton { background:#E7F3FF; color:#0B5D8A; border-color:#7DB3D8; }
    QPushButton#exportButton { background:#EAF8EF; color:#216A3A; border-color:#82C79B; }
    QPushButton#navigationButton { background:#FFF4DB; color:#7A5400; border-color:#E3BA5A; }
    QPushButton#gainButton { background:#F0EAFE; color:#5A3B91; border-color:#A995D0; min-width:34px; }
    QPushButton#dangerButton { background:#FDEBEC; color:#A12D34; border-color:#E5A0A5; }
    QSpinBox,QDoubleSpinBox { background:#FFFFFF; border:1px solid #A9BAC8; border-radius:5px; padding:3px; min-height:25px; }
    QTableWidget { background:#FFFFFF; alternate-background-color:#F4F8FB; border:1px solid #D5E1EA; gridline-color:#E4ECF2; }
    QHeaderView::section { background:#173B53; color:white; padding:5px; border:0; font-weight:800; }
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
        self.setMinimumHeight(250)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._samples: np.ndarray = np.zeros(0, dtype=np.float64)
        self._sample_interval_ms: float = 1.0
        self._cursor_x: Optional[float] = None
        self._plot_rect = QRectF()
        self._gain = 1.0
        self._selected_sample = 0

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
        self.update()

    def set_gain(self, gain: float) -> None:
        self._gain = max(0.01, min(float(gain), 1000.0))
        self.update()

    def set_selected_sample(self, sample_index: int) -> None:
        if self._samples.size == 0:
            return
        self._selected_sample = max(0, min(int(sample_index), self._samples.size - 1))
        rect = self._compute_plot_rect()
        if self._samples.size > 1:
            self._cursor_x = rect.left() + (self._selected_sample / (self._samples.size - 1)) * rect.width()
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
        painter.fillRect(self.rect(), QColor("#FCFEFF"))
        self._plot_rect = self._compute_plot_rect()
        rect = self._plot_rect

        painter.setPen(QPen(QColor("#A9B6C2"), 1))
        painter.drawRect(rect)
        if self._samples.size < 2:
            painter.setPen(QColor("#8A98A6"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "No trace data")
            return

        n = self._samples.size
        max_abs = float(np.max(np.abs(self._samples)))
        if max_abs <= 1e-20:
            max_abs = 1.0
        display_scale = max_abs / self._gain
        mid_y = rect.top() + rect.height() / 2.0

        painter.setPen(QPen(QColor("#D5DEE7"), 1, Qt.PenStyle.DashLine))
        painter.drawLine(rect.left(), mid_y, rect.right(), mid_y)

        # Light peak envelope preserves large excursions, while the main polyline is
        # continuous. This avoids the dotted / missing-sample look visible when one
        # vertical min-max bar is drawn for every screen pixel.
        pixel_count = max(2, int(rect.width()))
        if n > pixel_count * 2:
            edges = np.linspace(0, n, pixel_count + 1, dtype=int)
            env_pen = QPen(QColor(132, 168, 190, 105), 1)
            painter.setPen(env_pen)
            for px in range(pixel_count):
                segment = self._samples[edges[px]:edges[px + 1]]
                if not segment.size:
                    continue
                x_pos = rect.left() + px
                lo, hi = float(np.min(segment)), float(np.max(segment))
                y1, y2 = self._display_y(np.array([hi, lo]), rect, mid_y, display_scale)
                painter.drawLine(x_pos, float(y1), x_pos, float(y2))

        target_points = min(n, max(600, pixel_count * 2))
        indices = np.unique(np.linspace(0, n - 1, target_points).astype(int))
        path = QPainterPath()
        for j, index in enumerate(indices):
            x = rect.left() + (float(index) / max(n - 1, 1)) * rect.width()
            y = float(self._display_y(np.array([self._samples[index]]), rect, mid_y, display_scale)[0])
            if j == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        painter.setPen(QPen(QColor("#123B56"), 1.35))
        painter.drawPath(path)

        total_ms = (n - 1) * self._sample_interval_ms
        painter.setFont(QFont(painter.font().family(), 9))
        painter.setPen(QColor("#1557B0"))
        painter.drawText(int(rect.left()), int(rect.bottom() + 19), "0.0 ms")
        right_text = f"{total_ms:.1f} ms"
        painter.drawText(int(rect.right() - painter.fontMetrics().horizontalAdvance(right_text)), int(rect.bottom() + 19), right_text)

        if self._cursor_x is not None and rect.left() <= self._cursor_x <= rect.right():
            painter.setPen(QPen(QColor("#008DD2"), 1, Qt.PenStyle.DashLine))
            painter.drawLine(self._cursor_x, rect.top(), self._cursor_x, rect.bottom())

    def _sample_from_x(self, x: float) -> int:
        rect = self._plot_rect if self._plot_rect.width() > 0 else self._compute_plot_rect()
        x = min(max(x, rect.left()), rect.right())
        fraction = (x - rect.left()) / max(rect.width(), 1.0)
        return max(0, min(self._samples.size - 1, int(round(fraction * (self._samples.size - 1)))))

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
        self.cursor_changed.emit(sample, sample * self._sample_interval_ms, float(self._samples[sample]))
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._samples.size:
            sample = self._sample_from_x(event.position().x())
            self._selected_sample = sample
            self.set_selected_sample(sample)
            self.cursor_changed.emit(sample, sample * self._sample_interval_ms, float(self._samples[sample]))


class TraceWaveformDialog(QDialog):
    """Professional SEG-D trace inspector with waveform, FFT and frequency-time analysis."""

    def __init__(self, reader: SegdReader, trace_index: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Wave Inspect - Trace {trace_index + 1}")
        self.resize(1120, 560)
        self.setMinimumSize(920, 480)
        self.setObjectName("traceWaveDialog")
        self.setStyleSheet(DIALOG_STYLE)
        self._reader = reader
        self._trace_index = max(0, min(trace_index, max(0, reader.get_trace_count() - 1)))
        self._gain = 1.0
        self._samples = np.zeros(0, dtype=np.float64)
        self._building_cursor = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QFrame(self)
        header.setObjectName("headerCard")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 6, 10, 6)
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
        plot_layout.setContentsMargins(6, 6, 6, 6)
        self.plot = WaveformPlotWidget(self)
        self.plot.cursor_changed.connect(self._on_cursor_changed)
        plot_layout.addWidget(self.plot, 1)
        layout.addWidget(plot_card, 1)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(5)
        for label, slot in (
            ("BMP", self._export_bmp),
            ("Export PNG", self._export_png),
            ("FFT", self._show_fft),
            ("F vs T", self._show_spectrogram),
            ("FT Analysis", self._show_ft_analysis),
        ):
            button = QPushButton(label)
            button.setObjectName("exportButton" if label in {"BMP", "Export PNG"} else "analysisButton")
            button.clicked.connect(slot)
            toolbar.addWidget(button)

        toolbar.addSpacing(8)
        prev_btn = QPushButton("◀ Trace")
        prev_btn.setObjectName("navigationButton")
        prev_btn.setToolTip("Inspect previous physical trace")
        prev_btn.clicked.connect(lambda: self._step_trace(-1))
        next_btn = QPushButton("Trace ▶")
        next_btn.setObjectName("navigationButton")
        next_btn.setToolTip("Inspect next physical trace")
        next_btn.clicked.connect(lambda: self._step_trace(1))
        toolbar.addWidget(prev_btn)
        toolbar.addWidget(next_btn)

        toolbar.addWidget(QLabel("Gain:"))
        gain_down = QPushButton("−")
        gain_up = QPushButton("+")
        reset = QPushButton("R")
        for button in (gain_down, gain_up, reset):
            button.setObjectName("gainButton")
        gain_down.setToolTip("Decrease display gain")
        gain_up.setToolTip("Increase display gain")
        reset.setToolTip("Reset display gain")
        gain_down.clicked.connect(lambda: self._change_gain(1 / 1.5))
        gain_up.clicked.connect(lambda: self._change_gain(1.5))
        reset.clicked.connect(self._reset_gain)
        toolbar.addWidget(gain_down)
        toolbar.addWidget(gain_up)
        toolbar.addWidget(reset)

        toolbar.addStretch(1)
        toolbar.addWidget(QLabel("Time (ms):"))
        self.time_spin = QDoubleSpinBox()
        self.time_spin.setDecimals(3)
        self.time_spin.setRange(0.0, 1e9)
        self.time_spin.setKeyboardTracking(False)
        self.time_spin.valueChanged.connect(self._time_changed)
        toolbar.addWidget(self.time_spin)
        toolbar.addWidget(QLabel("Sample:"))
        self.sample_spin = QSpinBox()
        self.sample_spin.setRange(0, 0)
        self.sample_spin.setKeyboardTracking(False)
        self.sample_spin.valueChanged.connect(self._sample_changed)
        toolbar.addWidget(self.sample_spin)
        layout.addLayout(toolbar)

        footer = QFrame(self)
        footer.setObjectName("headerCard")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(10, 4, 10, 4)
        self.readout_label = QLabel(" ")
        self.readout_label.setStyleSheet("color:#21313D; font-family:Consolas,monospace; font-weight:700;")
        self.gain_label = QLabel("Gain 1.00×")
        self.gain_label.setObjectName("subtleLabel")
        close_btn = QPushButton("Close")
        close_btn.setObjectName("dangerButton")
        close_btn.clicked.connect(self.close)
        footer_layout.addWidget(self.readout_label, 1)
        footer_layout.addWidget(self.gain_label)
        footer_layout.addWidget(close_btn)
        layout.addWidget(footer)

        self._load_trace()

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
                f"Ch {info.trace_number}  •  Line {info.receiver_line:g}  •  Point {info.receiver_point:g}  •  "
                f"Set {info.channel_set}  •  Sensor {sensor}  •  Receiver {receiver}"
            )
        except Exception:
            self.info_label.setText(f"Trace {self._trace_index + 1}")

        rms = float(np.sqrt(np.mean(np.square(self._samples))))
        self.rms_label.setText(f"RMS {_format_number(rms, 5)}")
        self._set_cursor_sample(0)
        self.setWindowTitle(f"Wave Inspect - Trace {self._trace_index + 1}")

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
        self._on_cursor_changed(sample, sample * interval, float(self._samples[sample]))

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
        frequency, amplitude = self._fft_values()
        if not frequency.size:
            return
        summary = self._spectral_summary()
        dlg = QDialog(self)
        dlg.setWindowTitle(f"FFT - Trace {self._trace_index + 1}")
        dlg.resize(880, 520)
        dlg.setStyleSheet(DIALOG_STYLE)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(10, 10, 10, 10)
        top = QHBoxLayout()
        top.addWidget(_metric_card("Dominant Frequency", f"{summary['dominant']:.2f} Hz", "#0A86C7"))
        top.addWidget(_metric_card("Spectral Centroid", f"{summary['centroid']:.2f} Hz", "#14A3A8"))
        top.addWidget(_metric_card("Bandwidth", f"{summary['bandwidth']:.2f} Hz", "#6C5CE7"))
        lay.addLayout(top)

        palette = _PaletteSelector(dlg)
        palette_bar = QHBoxLayout()
        palette_bar.addWidget(QLabel("FFT colour palette:"))
        palette_bar.addWidget(palette)
        palette_bar.addStretch(1)
        lay.addLayout(palette_bar)

        plot = pg.PlotWidget()
        plot.setBackground("#FFFFFF")
        plot.setLabel("bottom", "Frequency", units="Hz")
        plot.setLabel("left", "Amplitude")
        plot.showGrid(x=True, y=True, alpha=0.22)
        curve = plot.plot(frequency, amplitude, pen=pg.mkPen(palette.pen(), width=2.4))
        if summary["dominant"] > 0:
            line = pg.InfiniteLine(pos=summary["dominant"], angle=90, pen=pg.mkPen("#0B6FA4", width=1.6))
            plot.addItem(line)
        lay.addWidget(plot, 1)

        def apply_palette() -> None:
            curve.setPen(pg.mkPen(palette.pen(), width=2.4))
            plot.repaint()

        palette.changed.connect(apply_palette)
        note = QLabel("FFT uses a Hann window and single-sided amplitude. Use the palette control above for the analysis colour.")
        note.setObjectName("subtleLabel")
        lay.addWidget(note)
        close = QPushButton("Close")
        close.setObjectName("dangerButton")
        close.clicked.connect(dlg.accept)
        lay.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
        dlg.exec()

    def _show_spectrogram(self) -> None:
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
        db = 10.0 * np.log10(np.maximum(power, np.finfo(float).tiny))
        if not db.size:
            QMessageBox.information(self, "F vs T", "No valid spectrogram samples were produced for this trace.")
            return
        lo, hi = np.nanpercentile(db, [3, 99])
        if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
            lo, hi = float(np.nanmin(db)), float(np.nanmax(db))
        if hi <= lo:
            hi = lo + 1.0

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Frequency vs Time - Trace {self._trace_index + 1}")
        dlg.resize(920, 540)
        dlg.setStyleSheet(DIALOG_STYLE)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(10, 10, 10, 10)
        header = QHBoxLayout()
        header.addWidget(_metric_card("Window", f"{nperseg} samples", "#0A86C7"))
        header.addWidget(_metric_card("Overlap", f"{int(100 * noverlap / max(nperseg, 1))}%", "#14A3A8"))
        header.addWidget(_metric_card("Power Range", f"{lo:.1f} to {hi:.1f} dB", "#6C5CE7"))
        lay.addLayout(header)

        palette = _PaletteSelector(dlg)
        palette_bar = QHBoxLayout()
        palette_bar.addWidget(QLabel("F vs T colour palette:"))
        palette_bar.addWidget(palette)
        palette_bar.addStretch(1)
        lay.addLayout(palette_bar)

        plot = pg.PlotWidget()
        plot.setBackground("#FFFFFF")
        plot.setLabel("bottom", "Time", units="ms")
        plot.setLabel("left", "Frequency", units="Hz")
        plot.showGrid(x=True, y=True, alpha=0.18)
        image = pg.ImageItem()
        try:
            image.setOpts(axisOrder="row-major")
            image.setOpts(autoDownsample=False)
        except Exception:
            pass
        image.setLookupTable(palette.lut())
        image.setImage(db.T, autoLevels=False, levels=(float(lo), float(hi)))
        if f.size > 1 and t.size > 1:
            width_ms = max(float((t[-1] - t[0]) * 1000.0), self.plot.sample_interval_ms)
            height_hz = max(float(f[-1] - f[0]), 1.0)
            image.setRect(QRectF(float(t[0] * 1000.0), float(f[0]), width_ms, height_hz))
        plot.addItem(image)
        lay.addWidget(plot, 1)

        def apply_palette() -> None:
            image.setLookupTable(palette.lut())
            image.update()
            plot.repaint()

        palette.changed.connect(apply_palette)
        note = QLabel("STFT spectrogram displayed as PSD in dB with fixed percentile levels. Use the palette control above for analysis colour mapping.")
        note.setObjectName("subtleLabel")
        lay.addWidget(note)
        close = QPushButton("Close")
        close.setObjectName("dangerButton")
        close.clicked.connect(dlg.accept)
        lay.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
        dlg.exec()

    def _show_ft_analysis(self) -> None:
        if self._samples.size < 2:
            return
        summary = self._spectral_summary()
        frequency, amplitude = self._fft_values()
        dlg = QDialog(self)
        dlg.setWindowTitle(f"FT Analysis - Trace {self._trace_index + 1}")
        dlg.resize(840, 520)
        dlg.setStyleSheet(DIALOG_STYLE)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(10, 10, 10, 10)

        cards = QGridLayout()
        items = [
            ("Samples", f"{int(summary['samples']):,}", "#0A86C7"),
            ("Duration", f"{summary['duration_s']:.3f} s", "#14A3A8"),
            ("RMS", _format_number(summary["rms"], 5), "#6C5CE7"),
            ("Peak", _format_number(summary["peak"], 5), "#C83D3D"),
            ("Dominant", f"{summary['dominant']:.2f} Hz", "#0B6FA4"),
            ("Centroid", f"{summary['centroid']:.2f} Hz", "#0A86C7"),
        ]
        for i, (title, value, color) in enumerate(items):
            cards.addWidget(_metric_card(title, value, color), i // 3, i % 3)
        lay.addLayout(cards)

        palette = _PaletteSelector(dlg)
        palette_bar = QHBoxLayout()
        palette_bar.addWidget(QLabel("FT analysis colour palette:"))
        palette_bar.addWidget(palette)
        palette_bar.addStretch(1)
        lay.addLayout(palette_bar)

        plot = pg.PlotWidget()
        plot.setBackground("#FFFFFF")
        plot.setLabel("bottom", "Frequency", units="Hz")
        plot.setLabel("left", "Amplitude")
        plot.showGrid(x=True, y=True, alpha=0.22)
        curve = plot.plot(frequency, amplitude, pen=pg.mkPen(palette.pen(), width=2.4))
        lay.addWidget(plot, 1)

        def apply_palette() -> None:
            curve.setPen(pg.mkPen(palette.pen(), width=2.4))
            plot.repaint()

        palette.changed.connect(apply_palette)

        table = QTableWidget(0, 2)
        table.setHorizontalHeaderLabels(["Metric", "Value"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setMaximumHeight(132)
        rows = [
            ("Sample interval", f"{summary['sample_interval_ms']:.6g} ms"),
            ("Mean amplitude", _format_number(summary["mean"], 7)),
            ("Standard deviation", _format_number(summary["std"], 7)),
            ("Crest factor", f"{summary['crest']:.4f}"),
            ("Spectral RMS bandwidth", f"{summary['bandwidth']:.3f} Hz"),
            ("Zero-crossing rate", f"{summary['zcr']:.3f} crossings/s"),
        ]
        table.setRowCount(len(rows))
        for row, (name, value) in enumerate(rows):
            table.setItem(row, 0, QTableWidgetItem(name))
            table.setItem(row, 1, QTableWidgetItem(value))
        lay.addWidget(table)

        close = QPushButton("Close")
        close.setObjectName("dangerButton")
        close.clicked.connect(dlg.accept)
        lay.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
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
