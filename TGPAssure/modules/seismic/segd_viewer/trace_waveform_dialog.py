from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from modules.seismic.segd_viewer.segd_reader import SegdReader


class WaveformPlotWidget(QWidget):
    """Single-trace amplitude-vs-time plot with gain, cursor and sample navigation."""

    cursor_changed = Signal(int, float, float)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(320)
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
        return 10, 30, 10, 28

    def _compute_plot_rect(self) -> QRectF:
        left, top, right, bottom = self._margins()
        return QRectF(left, top, max(1, self.width() - left - right), max(1, self.height() - top - bottom))

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#FCFEFF"))
        self._plot_rect = self._compute_plot_rect()
        rect = self._plot_rect

        painter.setPen(QPen(QColor(105, 112, 120), 1))
        painter.drawRect(rect)
        if self._samples.size < 2:
            painter.setPen(QColor(150, 150, 150))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "No trace data")
            return

        n = self._samples.size
        max_abs = float(np.max(np.abs(self._samples)))
        if max_abs <= 1e-20:
            max_abs = 1.0
        display_scale = max_abs / self._gain
        mid_y = rect.top() + rect.height() / 2.0

        painter.setPen(QPen(QColor(215, 220, 225), 1, Qt.PenStyle.DashLine))
        painter.drawLine(rect.left(), mid_y, rect.right(), mid_y)

        # Pixel-aware min/max envelope prevents high-frequency detail from disappearing
        # when the trace has more samples than horizontal display pixels.
        pixel_count = max(2, int(rect.width()))
        if n > pixel_count * 2:
            edges = np.linspace(0, n, pixel_count + 1, dtype=int)
            painter.setPen(QPen(QColor("#123B56"), 1.0))
            for px in range(pixel_count):
                segment = self._samples[edges[px]:edges[px + 1]]
                if not segment.size:
                    continue
                lo, hi = float(np.min(segment)), float(np.max(segment))
                x = rect.left() + px
                y1 = mid_y - np.clip(hi / display_scale, -1, 1) * rect.height() * 0.47
                y2 = mid_y - np.clip(lo / display_scale, -1, 1) * rect.height() * 0.47
                painter.drawLine(x, y1, x, y2)
        else:
            path = QPainterPath()
            for i, amplitude in enumerate(self._samples):
                x = rect.left() + (i / (n - 1)) * rect.width()
                y = mid_y - np.clip(amplitude / display_scale, -1, 1) * rect.height() * 0.47
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            painter.setPen(QPen(QColor("#123B56"), 1.2))
            painter.drawPath(path)

        total_ms = (n - 1) * self._sample_interval_ms
        painter.setFont(QFont(painter.font().family(), 9))
        painter.setPen(QColor(25, 65, 170))
        painter.drawText(int(rect.left()), int(rect.bottom() + 19), "0.0 ms")
        right_text = f"{total_ms:.1f} ms"
        painter.drawText(int(rect.right() - painter.fontMetrics().horizontalAdvance(right_text)), int(rect.bottom() + 19), right_text)

        if self._cursor_x is not None and rect.left() <= self._cursor_x <= rect.right():
            painter.setPen(QPen(QColor(0, 135, 200), 1, Qt.PenStyle.DashLine))
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
    """428-style SEG-D trace inspector with waveform, FFT and frequency-time analysis."""

    def __init__(self, reader: SegdReader, trace_index: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Wave Inspect - Trace {trace_index + 1}")
        self.resize(1180, 650)
        self.setObjectName("traceWaveDialog")
        self.setStyleSheet("""
            QDialog#traceWaveDialog { background:#EEF4F8; }
            QLabel { background:transparent; }
            QPushButton { min-height:28px; padding:4px 12px; border-radius:5px; border:1px solid #9FB2C3; background:#FFFFFF; font-weight:600; }
            QPushButton:hover { background:#E2F0FA; border-color:#3A8BC2; }
            QPushButton#analysisButton { background:#E7F3FF; color:#0B5D8A; border-color:#7DB3D8; }
            QPushButton#exportButton { background:#EAF8EF; color:#216A3A; border-color:#82C79B; }
            QPushButton#navigationButton { background:#FFF4DB; color:#7A5400; border-color:#E3BA5A; }
            QPushButton#gainButton { background:#F0EAFE; color:#5A3B91; border-color:#A995D0; min-width:34px; }
            QPushButton#dangerButton { background:#FDEBEC; color:#A12D34; border-color:#E5A0A5; }
            QSpinBox,QDoubleSpinBox { background:#FFFFFF; border:1px solid #A9BAC8; border-radius:4px; padding:3px; }
        """)
        self._reader = reader
        self._trace_index = max(0, min(trace_index, max(0, reader.get_trace_count() - 1)))
        self._gain = 1.0
        self._samples = np.zeros(0, dtype=np.float64)
        self._building_cursor = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(5)

        header_row = QHBoxLayout()
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color:#1241B5; font-weight:700;")
        self.rms_label = QLabel("")
        self.rms_label.setStyleSheet("color:#1241B5; font-weight:700;")
        header_row.addWidget(self.info_label, 1)
        header_row.addWidget(self.rms_label)
        layout.addLayout(header_row)

        self.plot = WaveformPlotWidget(self)
        self.plot.cursor_changed.connect(self._on_cursor_changed)
        layout.addWidget(self.plot, 1)

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

        toolbar.addSpacing(12)
        prev_btn = QPushButton("◀ Trace")
        prev_btn.setToolTip("Inspect previous physical trace")
        prev_btn.clicked.connect(lambda: self._step_trace(-1))
        next_btn = QPushButton("Trace ▶")
        prev_btn.setObjectName("navigationButton")
        next_btn.setObjectName("navigationButton")
        next_btn.setToolTip("Inspect next physical trace")
        next_btn.clicked.connect(lambda: self._step_trace(1))
        gain_down = QPushButton("−")
        gain_down.setToolTip("Decrease display gain")
        gain_down.clicked.connect(lambda: self._change_gain(1 / 1.5))
        gain_up = QPushButton("+")
        gain_up.setToolTip("Increase display gain")
        gain_up.clicked.connect(lambda: self._change_gain(1.5))
        reset = QPushButton("R")
        for _b in (gain_down, gain_up, reset):
            _b.setObjectName("gainButton")
        reset.setToolTip("Reset display gain")
        reset.clicked.connect(self._reset_gain)
        toolbar.addWidget(prev_btn)
        toolbar.addWidget(next_btn)
        toolbar.addWidget(QLabel("Gain:"))
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

        footer = QHBoxLayout()
        self.readout_label = QLabel(" ")
        self.readout_label.setStyleSheet("color:#333; font-family:monospace;")
        self.gain_label = QLabel("Gain 1.00×")
        close_btn = QPushButton("Close")
        close_btn.setObjectName("dangerButton")
        close_btn.clicked.connect(self.close)
        footer.addWidget(self.readout_label, 1)
        footer.addWidget(self.gain_label)
        footer.addWidget(close_btn)
        layout.addLayout(footer)

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
                f"Channel {info.trace_number}    Line {info.receiver_line:g}    Point {info.receiver_point:g}    "
                f"Channel Set {info.channel_set}    Sensor {sensor}    Receiver {receiver}"
            )
        except Exception:
            self.info_label.setText(f"Trace {self._trace_index + 1}")

        rms = float(np.sqrt(np.mean(np.square(self._samples))))
        self.rms_label.setText(f"Trace RMS {rms:.7g}")
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
        self.readout_label.setText(f"Sample {sample}   Time {time_ms:.3f} ms   Amplitude {amplitude:.7g}")
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
        signal = self._samples - float(np.mean(self._samples))
        # Hann window reduces leakage in single-record spectral inspection.
        window = np.hanning(signal.size)
        spectrum = np.fft.rfft(signal * window)
        amplitude = 2.0 * np.abs(spectrum) / max(float(np.sum(window)), 1e-12)
        dt_seconds = self.plot.sample_interval_ms / 1000.0
        frequency = np.fft.rfftfreq(signal.size, d=max(dt_seconds, 1e-12))
        return frequency, amplitude

    def _show_fft(self) -> None:
        frequency, amplitude = self._fft_values()
        if not frequency.size:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"FFT - Trace {self._trace_index + 1}")
        dlg.resize(850, 520)
        lay = QVBoxLayout(dlg)
        plot = pg.PlotWidget()
        plot.setBackground("w")
        plot.setLabel("bottom", "Frequency", units="Hz")
        plot.setLabel("left", "Amplitude")
        plot.showGrid(x=True, y=True, alpha=0.2)
        plot.plot(frequency, amplitude, pen=pg.mkPen("k", width=1))
        lay.addWidget(plot, 1)
        close = QPushButton("Close")
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
        nperseg = min(256, max(16, 2 ** int(np.floor(np.log2(max(16, self._samples.size // 8))))))
        noverlap = int(nperseg * 0.75)
        f, t, power = spectrogram(
            self._samples - np.mean(self._samples), fs=fs, window="hann", nperseg=nperseg,
            noverlap=noverlap, detrend="constant", scaling="density", mode="psd"
        )
        db = 10.0 * np.log10(np.maximum(power, np.finfo(float).tiny))
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Frequency vs Time - Trace {self._trace_index + 1}")
        dlg.resize(900, 560)
        lay = QVBoxLayout(dlg)
        plot = pg.PlotWidget()
        plot.setBackground("w")
        image = pg.ImageItem(db.T)
        plot.addItem(image)
        if f.size > 1 and t.size > 1:
            image.setRect(QRectF(float(t[0] * 1000), float(f[0]), float((t[-1] - t[0]) * 1000), float(f[-1] - f[0])))
        plot.setLabel("bottom", "Time", units="ms")
        plot.setLabel("left", "Frequency", units="Hz")
        lay.addWidget(plot, 1)
        note = QLabel(f"STFT/spectrogram: Hann window {nperseg} samples, 75% overlap, PSD displayed in dB.")
        lay.addWidget(note)
        close = QPushButton("Close")
        close.clicked.connect(dlg.accept)
        lay.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
        dlg.exec()

    def _show_ft_analysis(self) -> None:
        if self._samples.size < 2:
            return
        x = self._samples
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
        rms = float(np.sqrt(np.mean(x ** 2)))
        peak = float(np.max(np.abs(x)))
        crest = peak / max(rms, 1e-20)
        zero_crossings = int(np.count_nonzero(np.diff(np.signbit(x - np.mean(x)))))
        duration_s = max((x.size - 1) * self.plot.sample_interval_ms / 1000.0, 1e-12)
        zcr = zero_crossings / duration_s
        text = (
            f"Trace {self._trace_index + 1}\n"
            f"Samples: {x.size:,}\n"
            f"Sample interval: {self.plot.sample_interval_ms:.6g} ms\n"
            f"Duration: {duration_s:.6g} s\n\n"
            f"Mean amplitude: {np.mean(x):.7g}\n"
            f"Standard deviation: {np.std(x):.7g}\n"
            f"RMS: {rms:.7g}\n"
            f"Absolute peak: {peak:.7g}\n"
            f"Crest factor: {crest:.4f}\n\n"
            f"Dominant frequency: {dominant:.3f} Hz\n"
            f"Spectral centroid: {centroid:.3f} Hz\n"
            f"Spectral RMS bandwidth: {bandwidth:.3f} Hz\n"
            f"Zero-crossing rate: {zcr:.3f} crossings/s\n"
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("FT Analysis")
        dlg.resize(520, 430)
        lay = QVBoxLayout(dlg)
        label = QLabel(text)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setStyleSheet("font-family:monospace;")
        lay.addWidget(label, 1)
        close = QPushButton("Close")
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
            self.plot.grab().save(path)

    def _export_bmp(self) -> None:
        self._save_plot(".bmp", "Bitmap Image (*.bmp)")

    def _export_png(self) -> None:
        self._save_plot(".png", "PNG Image (*.png)")
