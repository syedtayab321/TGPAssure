from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Optional

import numpy as np
from PySide6.QtCore import QObject, QPointF, QRectF, QRunnable, QSignalBlocker, QThreadPool, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCloseEvent, QContextMenuEvent, QImage, QMouseEvent, QPainter, QPainterPath, QPen, QResizeEvent, QWheelEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QMessageBox,
    QMenu,
    QProgressBar,
    QPushButton,
    QButtonGroup,
    QRadioButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from modules.seismic.segd_viewer.header_viewer import HeaderViewer
from modules.seismic.segd_viewer.segd_reader import SegdReader
from modules.seismic.segd_viewer.trace_waveform_dialog import TraceWaveformDialog
from modules.seismic.segd_viewer.segd_interaction_dialogs import (
    SegdMeasureActionsDialog,
    SegdPickActionsDialog,
)
from modules.seismic.segd_viewer.segd_qc_results_dialog import SegdQcResultsDialog


STATUS_COLORS = {
    "Normal": QColor(0, 0, 0),
    "Auxiliary": QColor(165, 165, 165),
    "Resistance": QColor(230, 35, 35),
    "Capacitance": QColor(230, 0, 220),
    "Leakage": QColor(30, 80, 235),
    "Tilt": QColor(0, 190, 45),
    "Multiple": QColor(240, 205, 0),
    "Dead": QColor(150, 0, 0),
    "Edited": QColor(235, 125, 20),
}


TRACE_ATTRIBUTE_TEXT_COLORS = {
    # Legacy SEG-D attribute panel colours.  These mirror the field-viewer
    # convention shown in the receiver attribute card while leaving the data
    # values and layout unchanged.
    "channel_set": QColor(158, 158, 0),
    "line": QColor(158, 158, 0),
    "point": QColor(158, 158, 0),
    "x": QColor(158, 158, 0),
    "y": QColor(158, 158, 0),
    "z": QColor(158, 158, 0),
    "channel_type": QColor(255, 255, 0),
    "sensor": QColor(255, 255, 0),
    "resistance": QColor(0, 0, 255),
    "capacitance": QColor(0, 0, 255),
    "tilt": QColor(0, 0, 255),
    "leakage": QColor(0, 0, 255),
    "receiver_index": QColor(0, 160, 0),
    "trace": QColor(0, 160, 0),
    "status": QColor(255, 0, 0),
    "sample": QColor(175, 175, 175),
    "time": QColor(175, 175, 175),
    "amplitude": QColor(175, 175, 175),
}


@dataclass(frozen=True)
class RenderParameters:
    trace_start: int
    trace_end: int
    sample_start: int
    sample_end: int
    gain_mode: str
    fixed_gain_db: float
    agc_window_ms: float
    clip_percentile: float
    display_mode: str
    wiggle_scale: float
    color_palette: str
    color_gain: float
    polarity: int
    fill_positive: bool
    remove_dc: bool
    qc_colors: bool
    filter_enabled: bool
    filter_low_hz: float
    filter_high_hz: float
    width: int
    height: int


class WorkerSignals(QObject):
    progress = Signal(int, int, str)
    result = Signal(int, object)
    error = Signal(int, str)
    finished = Signal(int)


class OpenFileWorker(QRunnable):
    def __init__(self, generation: int, path: Path) -> None:
        super().__init__()
        self.generation = generation
        self.path = path
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            reader = SegdReader(
                self.path,
                progress_callback=lambda value, message: self.signals.progress.emit(
                    self.generation, value, message
                ),
            )
            self.signals.result.emit(self.generation, reader)
        except Exception as error:
            self.signals.error.emit(self.generation, str(error))
        finally:
            self.signals.finished.emit(self.generation)


class RenderWorker(QRunnable):
    def __init__(self, generation: int, reader: SegdReader, params: RenderParameters) -> None:
        super().__init__()
        self.generation = generation
        self.reader = reader
        self.params = params
        self.signals = WorkerSignals()
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def run(self) -> None:
        try:
            if self.cancelled:
                return
            self.signals.progress.emit(self.generation, 8, "Reading selected traces")
            data = self.reader.read_channel_data(
                (self.params.trace_start, self.params.trace_end),
                0,
                (self.params.sample_start, self.params.sample_end),
            ).astype(np.float32, copy=False)
            if data.size == 0:
                raise ValueError("The selected SEG-D trace and sample window contains no data.")

            if self.cancelled:
                return
            raw = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32, copy=False)
            self.signals.progress.emit(self.generation, 28, "Applying gain and polarity")
            processed = self._process(raw)
            if self.cancelled:
                return

            self.signals.progress.emit(self.generation, 52, "Preparing trace display")
            display_data = self._peak_preserving_resample(processed, self.params.height)
            statuses = self._classify_traces(raw)
            if self.cancelled:
                return

            self.signals.progress.emit(self.generation, 74, "Drawing seismic traces")
            if self.params.display_mode == "wiggle":
                image = self._render_wiggle(display_data, statuses)
            elif self.params.display_mode == "variable_area":
                image = self._render_variable_area(display_data, statuses)
            elif self.params.display_mode == "color_density":
                image = self._render_variable_density(display_data, colored=True)
            elif self.params.display_mode == "wiggle_color":
                image = self._render_wiggle_color(display_data, statuses)
            else:
                image = self._render_variable_density(display_data, colored=False)

            if self.cancelled:
                return
            if image.isNull():
                raise ValueError("The SEG-D renderer produced an empty image.")

            self.signals.progress.emit(self.generation, 100, "Render complete")
            self.signals.result.emit(
                self.generation,
                {
                    "image": image,
                    "raw": raw,
                    "statuses": statuses,
                    "params": self.params,
                },
            )
        except Exception as error:
            self.signals.error.emit(self.generation, str(error))
        finally:
            self.signals.finished.emit(self.generation)

    def _process(self, data: np.ndarray) -> np.ndarray:
        work = data.astype(np.float32, copy=True)

        if self.params.remove_dc and work.shape[1] > 1:
            work -= np.mean(work, axis=1, keepdims=True, dtype=np.float64).astype(np.float32)

        if self.params.polarity < 0:
            work *= -1.0

        if self.params.gain_mode == "fixed":
            work *= np.float32(10.0 ** (self.params.fixed_gain_db / 20.0))
        elif self.params.gain_mode == "trace_balance":
            # Match the legacy 408 viewer default: every trace is normalised
            # independently to its own peak before the display gain/clip is
            # applied.  This prevents the first high-amplitude traces from
            # flooding the section and keeps weak traces visible.
            peak = np.max(np.abs(work), axis=1, keepdims=True).astype(np.float32)
            peak[peak <= 1e-12] = 1.0
            work = work / peak
            work *= np.float32(10.0 ** (self.params.fixed_gain_db / 20.0))
        elif self.params.gain_mode == "agc":
            interval = max(float(self.reader.get_sample_interval()), 1e-9)
            window = max(3, int(round(self.params.agc_window_ms / interval)))
            window = min(window, work.shape[1])
            if window % 2 == 0:
                window = max(3, window - 1)
            work = self._agc(work, window)

        if self.params.filter_enabled and work.shape[1] >= 16:
            try:
                from scipy.signal import butter, sosfiltfilt
                interval_ms = max(float(self.reader.get_sample_interval()), 1e-9)
                fs = 1000.0 / interval_ms
                nyquist = fs * 0.5
                low = max(0.0, float(self.params.filter_low_hz))
                high = max(0.0, float(self.params.filter_high_hz))
                if low > 0.0 and high > low and high < nyquist:
                    sos = butter(4, [low / nyquist, high / nyquist], btype="bandpass", output="sos")
                elif low > 0.0 and low < nyquist:
                    sos = butter(4, low / nyquist, btype="highpass", output="sos")
                elif high > 0.0 and high < nyquist:
                    sos = butter(4, high / nyquist, btype="lowpass", output="sos")
                else:
                    sos = None
                if sos is not None:
                    work = sosfiltfilt(sos, work, axis=1).astype(np.float32, copy=False)
            except Exception:
                # Filtering is display-only; a bad/unsupported filter must never prevent raw SEG-D viewing.
                pass

        absolute = np.abs(work)
        if self.params.clip_percentile <= 4.0:
            # Legacy "Trace Clip (0.5 - 4)" style control.  The entered value
            # is an amplitude-deflection clip, not a percentile.
            clip = float(max(0.05, self.params.clip_percentile))
        else:
            percentile = min(100.0, max(0.1, self.params.clip_percentile))
            clip = float(np.percentile(absolute, percentile)) if absolute.size else 1.0
        if not np.isfinite(clip) or clip <= 1e-20:
            clip = float(np.max(absolute)) if absolute.size else 1.0
        if not np.isfinite(clip) or clip <= 1e-20:
            clip = 1.0
        return np.clip(work / clip, -1.0, 1.0).astype(np.float32, copy=False)

    def _agc(self, data: np.ndarray, window: int) -> np.ndarray:
        if window <= 1 or data.shape[1] <= 1:
            return data
        half = window // 2
        energy = np.square(data.astype(np.float64))
        padded = np.pad(energy, ((0, 0), (half, half)), mode="edge")
        cumulative = np.cumsum(padded, axis=1, dtype=np.float64)
        cumulative = np.concatenate([np.zeros((data.shape[0], 1), dtype=np.float64), cumulative], axis=1)
        window_sum = cumulative[:, window:] - cumulative[:, :-window]
        rms = np.sqrt(np.maximum(window_sum / float(window), 1e-20))
        return (data / rms.astype(np.float32)).astype(np.float32, copy=False)

    def _peak_preserving_resample(self, data: np.ndarray, target_height: int) -> np.ndarray:
        trace_count, sample_count = data.shape
        target_height = max(2, int(target_height))
        if sample_count == target_height:
            return data
        if sample_count < target_height:
            old_x = np.arange(sample_count, dtype=np.float64)
            new_x = np.linspace(0.0, float(sample_count - 1), target_height)
            output = np.empty((trace_count, target_height), dtype=np.float32)
            for trace_index in range(trace_count):
                output[trace_index] = np.interp(new_x, old_x, data[trace_index]).astype(np.float32)
            return output

        edges = np.linspace(0, sample_count, target_height + 1, dtype=np.int64)
        output = np.empty((trace_count, target_height), dtype=np.float32)
        rows = np.arange(trace_count)
        for pixel in range(target_height):
            start = int(edges[pixel])
            end = max(start + 1, int(edges[pixel + 1]))
            chunk = data[:, start:end]
            peak_index = np.argmax(np.abs(chunk), axis=1)
            output[:, pixel] = chunk[rows, peak_index]
        return output

    def _classify_traces(self, raw: np.ndarray) -> list[str]:
        statuses: list[str] = []
        for local_index in range(raw.shape[0]):
            trace_index = self.params.trace_start + local_index
            try:
                info = self.reader.get_trace_info(trace_index)
                flags = list(getattr(info, "qc_flags", ()) or ())
                if len(flags) > 1:
                    status = "Multiple"
                elif len(flags) == 1 and flags[0] in STATUS_COLORS:
                    status = flags[0]
                elif info.channel_type != 1:
                    status = "Auxiliary"
                elif info.trace_edit != 0:
                    status = "Edited"
                elif float(np.max(np.abs(raw[local_index]))) <= 1e-20:
                    status = "Dead"
                else:
                    status = "Normal"
            except Exception:
                status = "Dead" if float(np.max(np.abs(raw[local_index]))) <= 1e-20 else "Normal"
            statuses.append(status)
        return statuses

    def _trace_color(self, status: str) -> QColor:
        if not self.params.qc_colors:
            return STATUS_COLORS["Normal"]
        return STATUS_COLORS.get(status, STATUS_COLORS["Normal"])

    @staticmethod
    def _crowded_trace_scale(spacing: float) -> float:
        """Reduce wiggle deflection automatically when traces are very close."""
        if spacing >= 3.25:
            return 1.0
        return max(0.28, float(spacing) / 3.25)

    @staticmethod
    def _trace_pen_width(spacing: float) -> float:
        """Thin, stable line width for dense SEG-D trace windows."""
        return max(0.32, min(1.20, float(spacing) * 0.28))

    @staticmethod
    def _display_color(color: QColor, spacing: float, *, fill: bool = False) -> QColor:
        """Apply transparency in dense displays so adjacent traces remain readable."""
        output = QColor(color)
        if fill:
            output.setAlpha(72 if spacing < 2.0 else 118)
        elif spacing < 1.50:
            output.setAlpha(205)
        return output

    def _render_wiggle(self, data: np.ndarray, statuses: list[str]) -> QImage:
        trace_count, sample_count = data.shape
        width = max(2, self.params.width)
        height = max(2, self.params.height)
        image = QImage(width, height, QImage.Format_RGB32)
        image.fill(Qt.white)
        painter = QPainter(image)
        spacing = width / max(1, trace_count)
        painter.setRenderHint(QPainter.Antialiasing, trace_count <= 2200)
        amplitude_scale = spacing * self.params.wiggle_scale * self._crowded_trace_scale(spacing)
        line_width = self._trace_pen_width(spacing)
        y_scale = (height - 1) / max(1, sample_count - 1)

        for trace_index in range(trace_count):
            if self.cancelled:
                painter.end()
                return QImage()
            trace = data[trace_index]
            baseline = (trace_index + 0.5) * spacing
            path = QPainterPath()
            path.moveTo(baseline + float(trace[0]) * amplitude_scale, 0.0)
            for sample_index in range(1, sample_count):
                path.lineTo(
                    baseline + float(trace[sample_index]) * amplitude_scale,
                    sample_index * y_scale,
                )
            pen = QPen(self._display_color(self._trace_color(statuses[trace_index]), spacing))
            pen.setWidthF(line_width)
            painter.setPen(pen)
            painter.drawPath(path)

        painter.end()
        return image

    def _render_variable_area(self, data: np.ndarray, statuses: list[str]) -> QImage:
        trace_count, sample_count = data.shape
        width = max(2, self.params.width)
        height = max(2, self.params.height)
        image = QImage(width, height, QImage.Format_RGB32)
        image.fill(Qt.white)
        painter = QPainter(image)
        spacing = width / max(1, trace_count)
        painter.setRenderHint(QPainter.Antialiasing, trace_count <= 2200)
        amplitude_scale = spacing * self.params.wiggle_scale * self._crowded_trace_scale(spacing)
        line_width = self._trace_pen_width(spacing)
        y_scale = (height - 1) / max(1, sample_count - 1)

        for trace_index in range(trace_count):
            if self.cancelled:
                painter.end()
                return QImage()
            trace = data[trace_index]
            baseline = (trace_index + 0.5) * spacing
            color = self._display_color(self._trace_color(statuses[trace_index]), spacing)
            fill_color = self._display_color(color, spacing, fill=True)
            
            wiggle = QPainterPath()
            wiggle.moveTo(baseline + float(trace[0]) * amplitude_scale, 0.0)
            
            fill = QPainterPath()
            fill.moveTo(baseline, 0.0)
            first = float(trace[0])
            first_fill = max(first, 0.0) if self.params.fill_positive else min(first, 0.0)
            fill.lineTo(baseline + first_fill * amplitude_scale, 0.0)

            for sample_index in range(1, sample_count):
                y = sample_index * y_scale
                value = float(trace[sample_index])
                wiggle.lineTo(baseline + value * amplitude_scale, y)
                fill_value = max(value, 0.0) if self.params.fill_positive else min(value, 0.0)
                fill.lineTo(baseline + fill_value * amplitude_scale, y)

            fill.lineTo(baseline, height - 1)
            fill.closeSubpath()
            
            painter.setPen(Qt.NoPen)
            painter.fillPath(fill, fill_color)
            
            pen = QPen(color)
            pen.setWidthF(line_width)
            painter.setPen(pen)
            painter.drawPath(wiggle)

        painter.end()
        return image

    def _render_variable_density(self, data: np.ndarray, *, colored: bool) -> QImage:
        matrix = self._density_matrix(data)
        enhanced = np.clip(matrix * np.float32(max(0.05, self.params.color_gain)), -1.0, 1.0)

        if not colored:
            signed = np.sign(enhanced)
            contrast = signed * np.power(np.abs(enhanced), 0.62)
            gray = np.ascontiguousarray(np.clip((1.0 - contrast) * 127.5, 0, 255).astype(np.uint8))
            image = QImage(gray.data, gray.shape[1], gray.shape[0], gray.strides[0], QImage.Format_Grayscale8)
            return image.copy()

        rgb = self._apply_color_palette(enhanced, self.params.color_palette)
        image = QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format_RGB888)
        return image.copy()

    def _density_matrix(self, data: np.ndarray) -> np.ndarray:
        trace_count, sample_count = data.shape
        width = max(2, self.params.width)
        height = max(2, self.params.height)
        matrix = data.T

        if sample_count != height:
            source_y = np.arange(sample_count, dtype=np.float64)
            target_y = np.linspace(0.0, float(sample_count - 1), height)
            resized_y = np.empty((height, trace_count), dtype=np.float32)
            for trace_index in range(trace_count):
                resized_y[:, trace_index] = np.interp(target_y, source_y, matrix[:, trace_index]).astype(np.float32)
            matrix = resized_y

        if trace_count != width:
            source_x = np.arange(trace_count, dtype=np.float64)
            target_x = np.linspace(0.0, float(trace_count - 1), width)
            resized = np.empty((height, width), dtype=np.float32)
            for row in range(height):
                resized[row] = np.interp(target_x, source_x, matrix[row]).astype(np.float32)
            matrix = resized

        return np.ascontiguousarray(matrix, dtype=np.float32)

    @staticmethod
    def _apply_color_palette(values: np.ndarray, palette: str) -> np.ndarray:
        values = np.clip(values, -1.0, 1.0)
        normalized = (values + 1.0) * 0.5
        palette_key = str(palette or "seismic").lower()

        if palette_key == "grayscale":
            gray = np.clip((1.0 - normalized) * 255.0, 0, 255).astype(np.uint8)
            return np.ascontiguousarray(np.repeat(gray[:, :, None], 3, axis=2))

        if palette_key == "viridis":
            stops = np.asarray([0.0, 0.25, 0.50, 0.75, 1.0], dtype=np.float32)
            colors = np.asarray(
                [[68, 1, 84], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37]],
                dtype=np.float32,
            )
        elif palette_key == "blue_white_red":
            stops = np.asarray([0.0, 0.5, 1.0], dtype=np.float32)
            colors = np.asarray([[25, 70, 185], [250, 250, 250], [190, 30, 35]], dtype=np.float32)
        else:  # Traditional seismic: deep blue -> cyan/white -> yellow/red.
            stops = np.asarray([0.0, 0.24, 0.50, 0.76, 1.0], dtype=np.float32)
            colors = np.asarray(
                [[20, 45, 155], [35, 170, 225], [248, 248, 245], [250, 185, 45], [190, 25, 30]],
                dtype=np.float32,
            )

        flat = normalized.reshape(-1)
        rgb = np.empty((flat.size, 3), dtype=np.float32)
        for channel in range(3):
            rgb[:, channel] = np.interp(flat, stops, colors[:, channel])
        return np.ascontiguousarray(np.clip(rgb.reshape(values.shape + (3,)), 0, 255).astype(np.uint8))

    def _render_wiggle_color(self, data: np.ndarray, statuses: list[str]) -> QImage:
        image = self._render_variable_density(data, colored=True)
        if image.isNull():
            return image

        trace_count, sample_count = data.shape
        width = max(2, self.params.width)
        height = max(2, self.params.height)
        painter = QPainter(image)
        spacing = width / max(1, trace_count)
        painter.setRenderHint(QPainter.Antialiasing, trace_count <= 2200)
        amplitude_scale = spacing * self.params.wiggle_scale * self._crowded_trace_scale(spacing)
        y_scale = (height - 1) / max(1, sample_count - 1)
        line_width = self._trace_pen_width(spacing)

        for trace_index in range(trace_count):
            if self.cancelled:
                painter.end()
                return QImage()
            trace = data[trace_index]
            baseline = (trace_index + 0.5) * spacing
            path = QPainterPath()
            path.moveTo(baseline + float(trace[0]) * amplitude_scale, 0.0)
            for sample_index in range(1, sample_count):
                path.lineTo(baseline + float(trace[sample_index]) * amplitude_scale, sample_index * y_scale)
            trace_color = self._trace_color(statuses[trace_index]) if self.params.qc_colors else QColor(20, 20, 20)
            pen = QPen(self._display_color(trace_color, spacing))
            pen.setWidthF(line_width)
            painter.setPen(pen)
            painter.drawPath(path)

        painter.end()
        return image


class BusyOverlay(QFrame):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("segdBusyOverlay")
        self.setStyleSheet(
            "QFrame#segdBusyOverlay{background:rgba(12,25,38,185);border:0;}"
            "QLabel{color:white;background:transparent;font-size:12px;font-weight:600;}"
            "QProgressBar{background:#25384A;border:1px solid #57748B;border-radius:5px;color:white;text-align:center;min-height:14px;}"
            "QProgressBar::chunk{background:#1EA7D8;border-radius:4px;}"
        )
        layout = QVBoxLayout(self)
        layout.addStretch(1)
        card = QFrame(self)
        card.setStyleSheet("QFrame{background:rgba(16,45,66,235);border:1px solid #5A7E98;border-radius:8px;}")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 18, 24, 18)
        self.title = QLabel("Processing SEG-D")
        self.title.setAlignment(Qt.AlignCenter)
        self.message = QLabel("Please wait")
        self.message.setAlignment(Qt.AlignCenter)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedWidth(280)
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

    def show_busy(self, title: str, message: str, progress: Optional[int] = None) -> None:
        self.title.setText(title)
        self.message.setText(message)
        if progress is None:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(max(0, min(100, int(progress))))
        self.show()
        self.raise_()

    def update_progress(self, value: int, message: str) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(max(0, min(100, int(value))))
        self.message.setText(message)


class TraceStatusLegend(QGroupBox):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Trace Status", parent)
        self.setStyleSheet(
            "QGroupBox{font-weight:900;color:#173B53;}"
            "QLabel{background:transparent;color:#102A3D;font-size:8pt;}"
        )
        layout = QGridLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setHorizontalSpacing(5)
        layout.setVerticalSpacing(2)
        entries = [
            "Normal", "Auxiliary", "Resistance",
            "Capacitance", "Leakage", "Tilt",
            "Multiple", "Dead", "Edited",
        ]
        for index, name in enumerate(entries):
            item = QFrame(self)
            item.setObjectName("legendItem")
            item_layout = QHBoxLayout(item)
            item_layout.setContentsMargins(2, 1, 2, 1)
            item_layout.setSpacing(4)
            chip = QLabel(item)
            chip.setFixedSize(10, 10)
            color = STATUS_COLORS[name]
            chip.setStyleSheet(
                f"background:rgb({color.red()},{color.green()},{color.blue()});"
                "border:1px solid #475569;border-radius:2px;"
            )
            label = QLabel(name, item)
            label.setMinimumWidth(0)
            item_layout.addWidget(chip)
            item_layout.addWidget(label, 1)
            row = index // 3
            col = index % 3
            layout.addWidget(item, row, col)



class ErrorStatusPanel(QGroupBox):
    """Legacy right-side error-status legend."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Error Status", parent)
        self.setStyleSheet(
            "QGroupBox{font-weight:700;color:#202020;border:1px solid #404040;margin-top:8px;background:#FFFFFF;}"
            "QGroupBox::title{subcontrol-origin:margin;left:7px;padding:0 2px;}"
            "QLabel{background:transparent;color:#202020;font-size:8pt;}"
        )
        layout = QGridLayout(self)
        layout.setContentsMargins(5, 9, 5, 5)
        layout.setHorizontalSpacing(4)
        layout.setVerticalSpacing(2)
        entries = [
            ("Normal", STATUS_COLORS["Normal"]),
            ("Aux.", STATUS_COLORS["Auxiliary"]),
            ("Resistance", STATUS_COLORS["Resistance"]),
            ("Capacitance", STATUS_COLORS["Capacitance"]),
            ("Leakage", STATUS_COLORS["Leakage"]),
            ("Tilt", STATUS_COLORS["Tilt"]),
            ("Multiple", STATUS_COLORS["Multiple"]),
        ]
        for row, (name, color) in enumerate(entries):
            label = QLabel(name, self)
            chip = QLabel(self)
            chip.setFixedSize(13, 13)
            chip.setStyleSheet(
                f"background:rgb({color.red()},{color.green()},{color.blue()});"
                "border:1px solid #D0D0D0;"
            )
            layout.addWidget(label, row, 0)
            layout.addWidget(chip, row, 1, Qt.AlignmentFlag.AlignRight)


class FileHeaderPanel(QGroupBox):
    """Legacy file-header card shown beside the seismic view."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("File Header", parent)
        self.setStyleSheet(
            "QGroupBox{font-weight:700;color:#202020;border:1px solid #404040;margin-top:8px;background:#FFFFFF;}"
            "QGroupBox::title{subcontrol-origin:margin;left:7px;padding:0 2px;}"
            "QLabel{background:transparent;color:#202020;font-size:8pt;}"
        )
        form = QFormLayout(self)
        form.setContentsMargins(4, 9, 4, 5)
        form.setVerticalSpacing(0)
        form.setHorizontalSpacing(5)
        self._labels: dict[str, QLabel] = {}
        rows = [
            ("file", "File"), ("date", "Date"), ("time", "Time"), ("record", "Record"),
            ("tape", "Tape #"), ("label", "Label"), ("sr", "SR (mS)"), ("length", "Length"),
            ("tot_trc", "Tot Trc"), ("tot_aux", "Tot Aux"), ("tot_seis", "Tot Seis"),
            ("src_ln", "Src Ln"), ("src_pt", "Src Pt"), ("src_x", "Src X"), ("src_y", "Src Y"),
            ("src_z", "Src Z"), ("first_ln", "First Ln"), ("first_pt", "First Pt"),
            ("blast_id", "Blast ID"), ("itb", "ITB"), ("tb_time", "TB Time"), ("uh_time", "UH Time"),
            ("filter", "Filter"), ("max_aux", "Max Aux"), ("max_seis", "Max Seis"),
        ]
        for key, caption in rows:
            label = QLabel("", self)
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self._labels[key] = label
            form.addRow(caption, label)
        self.clear_values()

    def clear_values(self) -> None:
        for label in self._labels.values():
            label.setText("0")
        for key in ("file", "date", "time", "record", "label"):
            self._labels[key].setText("")

    def set_reader(self, reader: SegdReader) -> None:
        summary = reader.metadata_summary()
        self._labels["file"].setText(str(summary.get("file_number", "")))
        date = getattr(reader.general_header_1, "date", "")
        time = getattr(reader.general_header_1, "time", "")
        self._labels["date"].setText(str(date))
        self._labels["time"].setText(str(time))
        self._labels["record"].setText("Normal")
        self._labels["label"].setText("")
        self._labels["sr"].setText(f"{float(summary.get('sample_interval_ms', 0.0)):g}")
        self._labels["length"].setText(str(int(summary.get("sample_count", 0)) * int(round(float(summary.get("sample_interval_ms", 0.0)) or 1))))
        self._labels["tot_trc"].setText(str(summary.get("trace_count", 0)))
        self._labels["tot_aux"].setText(str(summary.get("aux_trace_count", 0)))
        self._labels["tot_seis"].setText(str(summary.get("seismic_trace_count", 0)))
        try:
            self.set_trace(reader, 0)
        except Exception:
            pass

    def set_trace(self, reader: SegdReader, trace_index: int) -> None:
        try:
            info = reader.get_trace_info(max(0, min(trace_index, reader.get_trace_count() - 1)))
        except Exception:
            return
        def fmt(value: Any) -> str:
            if value is None:
                return "0"
            try:
                number = float(value)
                if not np.isfinite(number):
                    return "0"
                return f"{number:g}"
            except Exception:
                return str(value)
        self._labels["src_ln"].setText(fmt(getattr(info, "receiver_line", 0)))
        self._labels["src_pt"].setText(fmt(getattr(info, "receiver_point", 0)))
        self._labels["src_x"].setText(fmt(getattr(info, "receiver_x", 0)))
        self._labels["src_y"].setText(fmt(getattr(info, "receiver_y", 0)))
        self._labels["src_z"].setText(fmt(getattr(info, "receiver_elevation", 0)))
        self._labels["first_ln"].setText(fmt(getattr(info, "receiver_line", 0)))
        self._labels["first_pt"].setText(fmt(getattr(info, "receiver_point", 0)))

class TraceAttributesPanel(QGroupBox):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Trace Attributes", parent)
        form = QFormLayout(self)
        form.setContentsMargins(4, 4, 4, 4)
        form.setVerticalSpacing(1)
        form.setHorizontalSpacing(3)
        self._captions: dict[str, QLabel] = {}
        self._labels: dict[str, QLabel] = {}
        self.setStyleSheet(
            "QGroupBox{font-weight:700;color:#202020;border:1px solid #C8C8C8;margin-top:8px;background:#EFEFEF;}"
            "QGroupBox::title{subcontrol-origin:margin;left:7px;padding:0 2px;}"
            "QLabel{background:transparent;font-size:8pt;}"
        )
        rows = [
            ("channel_set", "Chan"),
            ("line", "Line"),
            ("point", "Point"),
            ("x", "X"),
            ("y", "Y"),
            ("z", "Z"),
            ("channel_type", "Type"),
            ("sensor", "Sensor"),
            ("resistance", "Res"),
            ("capacitance", "Cap"),
            ("tilt", "Tilt"),
            ("leakage", "Lkg"),
            ("receiver_index", "Cont"),
            ("trace", "Cont"),
            ("status", "Interp"),
            ("sample", "Sample"),
            ("time", "Time"),
            ("amplitude", "Amp"),
        ]
        for key, caption in rows:
            caption_label = QLabel(caption)
            caption_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            value = QLabel("—")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._captions[key] = caption_label
            self._labels[key] = value
            self._apply_attribute_color(key)
            form.addRow(caption_label, value)

    @staticmethod
    def _attribute_style(color: QColor) -> str:
        return (
            f"color:rgb({color.red()},{color.green()},{color.blue()});"
            "background:transparent;font-size:8pt;font-weight:700;"
        )

    def _apply_attribute_color(self, key: str) -> None:
        color = TRACE_ATTRIBUTE_TEXT_COLORS.get(key, QColor(32, 32, 32))
        style = self._attribute_style(color)
        caption = self._captions.get(key)
        if caption is not None:
            caption.setStyleSheet(style)
        value = self._labels.get(key)
        if value is not None:
            value.setStyleSheet(style)

    def clear_values(self) -> None:
        for key, label in self._labels.items():
            label.setText("—")
            self._apply_attribute_color(key)

    def set_trace(
        self,
        reader: SegdReader,
        trace_index: int,
        sample_index: int,
        time_ms: float,
        amplitude: float,
        status: str,
    ) -> None:
        try:
            info = reader.get_trace_info(trace_index)
        except Exception:
            return

        def optional_value(name: str, unit: str = "", decimals: int = 3) -> str:
            value = getattr(info, name, None)
            if value is None:
                return "—"
            try:
                number = float(value)
                if not np.isfinite(number):
                    return "—"
                text = f"{number:,.{decimals}f}".rstrip("0").rstrip(".")
                return f"{text} {unit}".strip()
            except (TypeError, ValueError):
                return str(value)

        self._labels["trace"].setText(str(trace_index + 1))
        self._labels["channel_set"].setText(str(info.channel_set))
        self._labels["line"].setText(optional_value("receiver_line", decimals=4))
        self._labels["point"].setText(optional_value("receiver_point", decimals=4))
        self._labels["receiver_index"].setText(str(info.receiver_index))
        self._labels["x"].setText(optional_value("receiver_x", decimals=3))
        self._labels["y"].setText(optional_value("receiver_y", decimals=3))
        self._labels["z"].setText(optional_value("receiver_elevation", "m", 3))
        self._labels["channel_type"].setText(str(info.channel_type))
        self._labels["sensor"].setText(str(info.sensor_type))
        self._labels["resistance"].setText(optional_value("resistance", "Ω", 3))
        self._labels["capacitance"].setText(optional_value("capacitance", "nF", 3))
        self._labels["leakage"].setText(optional_value("leakage", "MΩ", 3))
        self._labels["tilt"].setText(optional_value("tilt", "°", 3))

        limit_tooltips = {
            "resistance": ("resistance_low_limit", "resistance_high_limit", "Ω"),
            "capacitance": ("capacitance_low_limit", "capacitance_high_limit", "nF"),
            "leakage": ("leakage_limit", None, "MΩ"),
            "tilt": ("tilt_limit", None, "°"),
        }
        for key, (low_name, high_name, unit) in limit_tooltips.items():
            low = getattr(info, low_name, None) if low_name else None
            high = getattr(info, high_name, None) if high_name else None
            parts = []
            if low is not None:
                parts.append(f"Low/limit: {float(low):.6g} {unit}")
            if high is not None:
                parts.append(f"High: {float(high):.6g} {unit}")
            self._labels[key].setToolTip(" | ".join(parts))
        self._labels["sample"].setText(str(sample_index + 1))
        self._labels["time"].setText(f"{time_ms:.2f} ms")
        self._labels["amplitude"].setText(f"{amplitude:.6g}")
        self._labels["status"].setText(status)
        for key in self._labels:
            self._apply_attribute_color(key)


class SegdImageView(QWidget):
    picked = Signal(int, int)
    measured = Signal(int, int, int, int)
    hovered = Signal(int, int)
    hover_cleared = Signal()
    trace_inspect_requested = Signal(int, int)
    copy_trace_requested = Signal(int, int)
    copy_view_requested = Signal()
    fit_requested = Signal()
    view_resized = Signal()
    data_window_changed = Signal(int, int, int, int)

    MODE_PAN = "pan"
    MODE_PICK = "pick"
    MODE_MEASURE = "measure"

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(420, 280)
        self._image = QImage()
        self._trace_start = 0
        self._trace_end = 1
        self._sample_start = 0
        self._sample_end = 1
        self._sample_interval_ms = 1.0
        self._total_traces = 1
        self._total_samples = 1
        self._mode = self.MODE_PAN
        self._view_rect = QRectF(0.0, 0.0, 1.0, 1.0)
        self._cursor: Optional[QPointF] = None
        self._pick: Optional[tuple[int, int]] = None
        self._measure_start: Optional[tuple[int, int]] = None
        self._measure_end: Optional[tuple[int, int]] = None
        self._measurement: Optional[tuple[int, int, int, int]] = None
        self._pan_start: Optional[QPointF] = None
        self._pan_view_start: Optional[QRectF] = None
        self._trace_statuses: list[str] = []

    def set_trace_statuses(self, statuses: list[str]) -> None:
        self._trace_statuses = list(statuses or [])
        self.update()

    def _status_for_trace(self, trace_index: int) -> str:
        local = int(trace_index) - self._trace_start
        if 0 <= local < len(self._trace_statuses):
            return self._trace_statuses[local]
        return "Normal"

    def _status_color_for_trace(self, trace_index: int) -> QColor:
        return QColor(STATUS_COLORS.get(self._status_for_trace(trace_index), STATUS_COLORS["Normal"]))

    def set_data_extent(self, total_traces: int, total_samples: int) -> None:
        self._total_traces = max(1, int(total_traces))
        self._total_samples = max(1, int(total_samples))

    def set_image(
        self,
        image: QImage,
        trace_start: int,
        trace_end: int,
        sample_start: int,
        sample_end: int,
        sample_interval_ms: float,
        reset_view: bool = False,
    ) -> None:
        self._image = image
        self._trace_start = trace_start
        self._trace_end = max(trace_start + 1, trace_end)
        self._sample_start = sample_start
        self._sample_end = max(sample_start + 1, sample_end)
        self._sample_interval_ms = max(sample_interval_ms, 1e-9)
        if reset_view or not self._view_rect.isValid():
            self.fit_to_view()
        self.update()

    def set_mode(self, mode: str) -> None:
        if mode not in {self.MODE_PAN, self.MODE_PICK, self.MODE_MEASURE}:
            mode = self.MODE_PAN
        self._mode = mode
        self._measure_start = None
        self._measure_end = None
        if mode == self.MODE_MEASURE:
            self._measurement = None
        self.setCursor(Qt.OpenHandCursor if mode == self.MODE_PAN else Qt.CrossCursor)
        self.update()

    def clear_picks(self) -> None:
        self._pick = None
        self._measure_start = None
        self._measure_end = None
        self._measurement = None
        self.update()

    def fit_to_view(self) -> None:
        self._view_rect = QRectF(0.0, 0.0, 1.0, 1.0)
        self.update()

    def plot_rect(self) -> QRectF:
        return QRectF(58.0, 28.0, max(1.0, self.width() - 68.0), max(1.0, self.height() - 48.0))

    def target_render_size(self) -> tuple[int, int]:
        rect = self.plot_rect()
        # Render at the canvas logical size and request a fresh render on zoom.
        # This avoids stretching/down-sampling a previous bitmap, which made
        # traces look soft or distorted in the packaged viewer.
        width = max(420, min(6000, int(rect.width())))
        height = max(280, min(6000, int(rect.height())))
        return width, height

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
        painter.fillRect(self.rect(), QColor(26, 30, 35))
        plot = self.plot_rect()
        painter.fillRect(plot, Qt.white)

        if not self._image.isNull():
            source = QRectF(
                self._view_rect.left() * self._image.width(),
                self._view_rect.top() * self._image.height(),
                self._view_rect.width() * self._image.width(),
                self._view_rect.height() * self._image.height(),
            )
            painter.drawImage(plot, self._image, source)

        painter.setPen(QPen(QColor(90, 98, 108), 1.0))
        painter.drawRect(plot)
        self._draw_axes(painter, plot)
        self._draw_measurement(painter, plot)
        self._draw_pick(painter, plot)
        self._draw_crosshair(painter, plot)
        painter.end()

    def _draw_axes(self, painter: QPainter, plot: QRectF) -> None:
        painter.setPen(QColor(225, 230, 235))
        painter.drawText(QRectF(plot.left(), 2, plot.width(), 20), Qt.AlignCenter, "Trace / Channel")
        painter.save()
        painter.translate(12, plot.center().y())
        painter.rotate(-90)
        painter.drawText(QRectF(-plot.height() / 2, -10, plot.height(), 20), Qt.AlignCenter, "Time (ms)")
        painter.restore()

        painter.setPen(QPen(QColor(215, 220, 225), 1.0))
        trace_count = max(1, self._trace_end - self._trace_start)
        sample_count = max(1, self._sample_end - self._sample_start)
        visible_trace_start = self._trace_start + self._view_rect.left() * trace_count
        visible_trace_end = self._trace_start + self._view_rect.right() * trace_count
        visible_sample_start = self._sample_start + self._view_rect.top() * sample_count
        visible_sample_end = self._sample_start + self._view_rect.bottom() * sample_count

        tick_count_x = 10
        for tick in range(tick_count_x + 1):
            fraction = tick / tick_count_x
            x = plot.left() + fraction * plot.width()
            trace_value = visible_trace_start + fraction * (visible_trace_end - visible_trace_start)
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.top() - 4))
            label = str(int(round(trace_value)) + 1)
            painter.drawText(QRectF(x - 28, 8, 56, 18), Qt.AlignCenter, label)

        tick_count_y = 8
        for tick in range(tick_count_y + 1):
            fraction = tick / tick_count_y
            y = plot.top() + fraction * plot.height()
            sample_value = visible_sample_start + fraction * (visible_sample_end - visible_sample_start)
            time_ms = sample_value * self._sample_interval_ms
            painter.drawLine(QPointF(plot.left() - 4, y), QPointF(plot.left(), y))
            painter.drawText(QRectF(18, y - 9, 36, 18), Qt.AlignRight | Qt.AlignVCenter, f"{time_ms:.0f}")

    def _draw_crosshair(self, painter: QPainter, plot: QRectF) -> None:
        if self._cursor is None or not plot.contains(self._cursor):
            return
        shadow = QPen(QColor(0, 0, 0, 170))
        shadow.setWidthF(3.2)
        painter.setPen(shadow)
        painter.drawLine(QPointF(self._cursor.x(), plot.top()), QPointF(self._cursor.x(), plot.bottom()))
        painter.drawLine(QPointF(plot.left(), self._cursor.y()), QPointF(plot.right(), self._cursor.y()))
        data_point = self._widget_to_data(self._cursor)
        trace_color = self._status_color_for_trace(data_point[0]) if data_point is not None else QColor(0, 225, 255)
        pen = QPen(trace_color)
        pen.setWidthF(1.8)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.drawLine(QPointF(self._cursor.x(), plot.top()), QPointF(self._cursor.x(), plot.bottom()))
        painter.drawLine(QPointF(plot.left(), self._cursor.y()), QPointF(plot.right(), self._cursor.y()))

    def _draw_pick(self, painter: QPainter, plot: QRectF) -> None:
        if self._pick is None:
            return
        point = self._data_to_widget(self._pick[0], self._pick[1], plot)
        if point is None:
            return
        painter.setBrush(QColor(255, 245, 130, 95))
        painter.setPen(QPen(QColor(255, 185, 0), 2.0))
        painter.drawEllipse(point, 6.0, 6.0)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(20, 20, 20, 180), 3.0))
        painter.drawLine(QPointF(point.x() - 9, point.y()), QPointF(point.x() + 9, point.y()))
        painter.drawLine(QPointF(point.x(), point.y() - 9), QPointF(point.x(), point.y() + 9))
        painter.setPen(QPen(QColor(255, 220, 0), 1.5))
        painter.drawLine(QPointF(point.x() - 9, point.y()), QPointF(point.x() + 9, point.y()))
        painter.drawLine(QPointF(point.x(), point.y() - 9), QPointF(point.x(), point.y() + 9))

    def _draw_measurement(self, painter: QPainter, plot: QRectF) -> None:
        active_measurement = self._measurement
        if active_measurement is None and self._measure_start is not None and self._measure_end is not None:
            active_measurement = (
                self._measure_start[0],
                self._measure_start[1],
                self._measure_end[0],
                self._measure_end[1],
            )
        if active_measurement is None:
            if self._measure_start is not None:
                start_only = self._data_to_widget(self._measure_start[0], self._measure_start[1], plot)
                if start_only is not None:
                    painter.setPen(QPen(QColor(255, 190, 0), 2.0))
                    painter.setBrush(QColor(255, 235, 120, 100))
                    painter.drawEllipse(start_only, 6.0, 6.0)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
            return
        trace_1, sample_1, trace_2, sample_2 = active_measurement
        start = self._data_to_widget(trace_1, sample_1, plot)
        end = self._data_to_widget(trace_2, sample_2, plot)
        if start is None or end is None:
            return
        shadow = QPen(QColor(0, 0, 0, 150), 4.0)
        shadow.setStyle(Qt.PenStyle.DashLine if self._measurement is None else Qt.PenStyle.SolidLine)
        painter.setPen(shadow)
        painter.drawLine(start, end)
        pen = QPen(QColor(255, 190, 0), 2.2)
        pen.setStyle(Qt.PenStyle.DashLine if self._measurement is None else Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        painter.drawLine(start, end)
        painter.setBrush(QColor(255, 235, 120, 110))
        painter.drawEllipse(start, 5.5, 5.5)
        painter.drawEllipse(end, 5.5, 5.5)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        delta_trace = trace_2 - trace_1
        delta_time = (sample_2 - sample_1) * self._sample_interval_ms
        label_rect = QRectF(
            min(start.x(), end.x()) + abs(end.x() - start.x()) / 2.0 - 60.0,
            min(start.y(), end.y()) - 22.0,
            120.0,
            18.0,
        )
        if label_rect.top() < plot.top() + 2:
            label_rect.moveTop(min(plot.bottom() - 20.0, max(plot.top() + 2.0, max(start.y(), end.y()) + 6.0)))
        painter.fillRect(label_rect, QColor(255, 255, 255, 220))
        painter.setPen(QPen(QColor(20, 20, 20), 1.0))
        painter.drawRect(label_rect)
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, f"ΔTr {delta_trace:+d}  ΔT {delta_time:+.2f} ms")

    def _widget_to_data(self, point: QPointF) -> Optional[tuple[int, int]]:
        plot = self.plot_rect()
        if not plot.contains(point):
            return None
        fx = (point.x() - plot.left()) / max(1.0, plot.width())
        fy = (point.y() - plot.top()) / max(1.0, plot.height())
        source_x = self._view_rect.left() + fx * self._view_rect.width()
        source_y = self._view_rect.top() + fy * self._view_rect.height()
        trace_count = max(1, self._trace_end - self._trace_start)
        sample_count = max(1, self._sample_end - self._sample_start)
        trace = self._trace_start + int(np.clip(source_x * trace_count, 0, trace_count - 1))
        sample = self._sample_start + int(np.clip(source_y * sample_count, 0, sample_count - 1))
        return trace, sample

    def _data_to_widget(self, trace: int, sample: int, plot: QRectF) -> Optional[QPointF]:
        trace_count = max(1, self._trace_end - self._trace_start)
        sample_count = max(1, self._sample_end - self._sample_start)
        tx = (trace - self._trace_start + 0.5) / trace_count
        sy = (sample - self._sample_start + 0.5) / sample_count
        if not self._view_rect.contains(QPointF(tx, sy)):
            return None
        fx = (tx - self._view_rect.left()) / max(1e-12, self._view_rect.width())
        fy = (sy - self._view_rect.top()) / max(1e-12, self._view_rect.height())
        return QPointF(plot.left() + fx * plot.width(), plot.top() + fy * plot.height())

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Zoom by requesting a smaller/larger trace/sample window.

        This deliberately avoids magnifying an already-rasterized bitmap, which
        made wiggles look blurry and horizontally stretched. Every zoom step is
        re-read and re-rendered from the original SEG-D samples.
        """
        plot = self.plot_rect()
        point = event.position()
        if not plot.contains(point):
            return
        trace_count = max(1, self._trace_end - self._trace_start)
        sample_count = max(1, self._sample_end - self._sample_start)
        factor = 0.72 if event.angleDelta().y() > 0 else (1.0 / 0.72)
        fx = (point.x() - plot.left()) / max(1.0, plot.width())
        fy = (point.y() - plot.top()) / max(1.0, plot.height())
        horizontal_only = bool(event.modifiers() & Qt.ControlModifier)
        vertical_only = bool(event.modifiers() & Qt.ShiftModifier)
        new_traces = trace_count if vertical_only else max(1, int(round(trace_count * factor)))
        new_samples = sample_count if horizontal_only else max(32, int(round(sample_count * factor)))
        # The loaded render window is the hard bound for zoom-out here; the
        # parent expands further using its full-file spin ranges when possible.
        max_traces = max(trace_count, self._total_traces)
        max_samples = max(sample_count, self._total_samples)
        new_traces = min(new_traces, max_traces)
        new_samples = min(new_samples, max_samples)
        anchor_trace = self._trace_start + fx * trace_count
        anchor_sample = self._sample_start + fy * sample_count
        start_trace = int(round(anchor_trace - fx * new_traces))
        start_sample = int(round(anchor_sample - fy * new_samples))
        start_trace = max(0, start_trace)
        start_sample = max(0, start_sample)
        self._view_rect = QRectF(0.0, 0.0, 1.0, 1.0)
        self.data_window_changed.emit(start_trace, start_trace + new_traces, start_sample, start_sample + new_samples)
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        point = event.position()
        data_point = self._widget_to_data(point)
        if event.button() == Qt.LeftButton and self._mode == self.MODE_PAN:
            self._pan_start = point
            self._pan_view_start = QRectF(self._view_rect)
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        if event.button() == Qt.LeftButton and data_point is not None:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            if self._mode == self.MODE_PICK:
                self._pick = data_point
                self.picked.emit(data_point[0], data_point[1])
                self.update()
            elif self._mode == self.MODE_MEASURE:
                if self._measure_start is None:
                    self._measure_start = data_point
                    self._measure_end = data_point
                    self._measurement = None
                else:
                    self._measure_end = data_point
                    self._measurement = (
                        self._measure_start[0],
                        self._measure_start[1],
                        self._measure_end[0],
                        self._measure_end[1],
                    )
                    self.measured.emit(*self._measurement)
                    self._measure_start = None
                    self._measure_end = None
                self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        point = event.position()
        if self._pan_start is not None and self._pan_view_start is not None and event.buttons() & Qt.LeftButton:
            plot = self.plot_rect()
            dx = (point.x() - self._pan_start.x()) / max(1.0, plot.width()) * self._pan_view_start.width()
            dy = (point.y() - self._pan_start.y()) / max(1.0, plot.height()) * self._pan_view_start.height()
            moved = QRectF(
                self._pan_view_start.left() - dx,
                self._pan_view_start.top() - dy,
                self._pan_view_start.width(),
                self._pan_view_start.height(),
            )
            self._view_rect = self._clamp_view_rect(moved)
            self.update()
            event.accept()
            return

        data_point = self._widget_to_data(point)
        if data_point is not None:
            self._cursor = point
            if self._mode == self.MODE_MEASURE and self._measure_start is not None:
                self._measure_end = data_point
            self.hovered.emit(data_point[0], data_point[1])
        else:
            self._cursor = None
            self.hover_cleared.emit()
        self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton and self._pan_start is not None:
            self._pan_start = None
            self._pan_view_start = None
            self.setCursor(Qt.OpenHandCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:
        self._cursor = None
        if self._mode == self.MODE_MEASURE and self._measure_start is not None:
            self._measure_end = None
        self.hover_cleared.emit()
        self.update()
        super().leaveEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and self._mode in {self.MODE_PICK, self.MODE_MEASURE}:
            self.clear_picks()
            event.accept()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        data_point = self._widget_to_data(QPointF(event.pos()))
        menu = QMenu(self)
        inspect_action = menu.addAction("Inspect Trace Waveform")
        zoom_trace_action = menu.addAction("Zoom to Trace")
        normal_view_action = menu.addAction("Back to Normal View")
        copy_trace_action = menu.addAction("Copy Trace Details")
        menu.addSeparator()
        copy_view_action = menu.addAction("Copy Current View Image")
        fit_action = menu.addAction("Fit to Window")
        inspect_action.setEnabled(data_point is not None)
        zoom_trace_action.setEnabled(data_point is not None)
        normal_view_action.setEnabled(True)
        copy_trace_action.setEnabled(data_point is not None)
        chosen = menu.exec(event.globalPos())
        if chosen is inspect_action and data_point is not None:
            self.trace_inspect_requested.emit(data_point[0], data_point[1])
        elif chosen is zoom_trace_action and data_point is not None:
            trace = data_point[0]
            sample_count = max(1, self._sample_end - self._sample_start)
            self.data_window_changed.emit(trace, trace + 1, self._sample_start, self._sample_start + sample_count)
        elif chosen is normal_view_action:
            self._view_rect = QRectF(0.0, 0.0, 1.0, 1.0)
            self.data_window_changed.emit(0, self._total_traces, 0, self._total_samples)
        elif chosen is copy_trace_action and data_point is not None:
            self.copy_trace_requested.emit(data_point[0], data_point[1])
        elif chosen is copy_view_action:
            self.copy_view_requested.emit()
        elif chosen is fit_action:
            self.fit_requested.emit()
        event.accept()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.view_resized.emit()

    def _clamp_view_rect(self, rect: QRectF) -> QRectF:
        width = min(1.0, max(0.02, rect.width()))
        height = min(1.0, max(0.02, rect.height()))
        left = min(max(0.0, rect.left()), 1.0 - width)
        top = min(max(0.0, rect.top()), 1.0 - height)
        return QRectF(left, top, width, height)


class SegdViewerWidget(QWidget):
    loading_started = Signal(str, str)
    loading_progress = Signal(int, str)
    loading_finished = Signal()

    def __init__(
        self,
        file_path: str | Path,
        parent: Optional[QWidget] = None,
        db_engine: Optional[Any] = None,
        auto_open: bool = True,
    ) -> None:
        super().__init__(parent)
        self.file_path = Path(file_path)
        self.db_engine = db_engine
        self.reader: Optional[SegdReader] = None
        self._reader_history: list[SegdReader] = []
        self._raw_data = np.empty((0, 0), dtype=np.float32)
        self._trace_statuses: list[str] = []
        self._trace_start = 0
        self._trace_end = 0
        self._sample_start = 0
        self._sample_end = 0
        self._last_hover_trace = -1
        self._closing = False
        self._opening_file = False
        self._open_started_at = 0.0
        self._open_generation = 0
        self._render_generation = 0
        self._workers: dict[str, QRunnable] = {}
        self._active_render_worker: Optional[RenderWorker] = None
        self._filter_enabled = False
        self._filter_low_hz = 0.0
        self._filter_high_hz = 0.0
        self._open_pool = QThreadPool(self)
        self._open_pool.setMaxThreadCount(1)
        self._render_pool = QThreadPool(self)
        self._render_pool.setMaxThreadCount(1)
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._start_render)
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(lambda: self._schedule_render(0))
        self._build_ui()
        if auto_open:
            self.open_file(self.file_path)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame(self)
        header.setObjectName("segdViewerHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 5, 10, 5)
        header_layout.setSpacing(8)
        self.file_label = QLabel("No SEG-D file loaded")
        self.file_label.setStyleSheet("font-weight:700;")
        self.info_label = QLabel("")
        self.position_label = QLabel("")
        self.position_label.setMinimumWidth(300)
        self.position_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.header_render_button = QPushButton("Render")
        self.header_render_button.clicked.connect(self.render_current_view)
        header_layout.addWidget(self.file_label)
        header_layout.addWidget(self.info_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self.position_label)
        header_layout.addWidget(self.header_render_button)
        # Keep these labels for internal status updates, but do not show the
        # modern summary strip.  The legacy SEG-D view uses the right File Header
        # card and left Trace Attributes panel instead.
        self._legacy_summary_header = header
        header.hide()

        # Build configuration widgets once.  They are controlled from the legacy
        # Configure dialog instead of occupying the screen permanently.
        self.trace_attributes = TraceAttributesPanel(self)
        self.view_controls = self._create_view_controls_tab()
        self.gain_controls = self._create_gain_controls_tab()
        self.status_legend = ErrorStatusPanel(self)
        self.file_header_panel = FileHeaderPanel(self)
        self.header_viewer = HeaderViewer(self)
        self.tools_page = self._create_tools_tab()
        for hidden_panel in (self.view_controls, self.gain_controls, self.header_viewer, self.tools_page):
            hidden_panel.hide()

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        left_panel = QFrame(self)
        left_panel.setObjectName("segdLegacyLeftPanel")
        left_panel.setFixedWidth(118)
        left_panel.setStyleSheet(
            "QFrame#segdLegacyLeftPanel{background:#EEEEEE;border-right:1px solid #C6C6C6;}"
            "QPushButton{min-height:21px;border:1px solid #8F8F8F;background:#F4F4F4;color:#202020;font-size:8pt;padding:0 2px;}"
            "QPushButton#legacyOpenButton{background:#F6C343;color:#151515;font-weight:700;}"
            "QPushButton#legacyConfigureButton{background:#2D9CDB;color:#FFFFFF;font-weight:700;}"
            "QPushButton#legacyToolsButton{background:#27AE60;color:#FFFFFF;font-weight:700;}"
            "QPushButton#legacyExportButton{background:#DCEBFF;color:#173B53;font-weight:700;}"
            "QPushButton#legacyNavButton{background:#FFFFFF;color:#202020;}"
            "QPushButton:hover{background:#FFFFFF;color:#111111;}"
        )
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(5, 4, 5, 4)
        left_layout.setSpacing(3)
        open_button = QPushButton("Open")
        open_button.setObjectName("legacyOpenButton")
        open_button.clicked.connect(self._choose_file)
        config_button = QPushButton("Configure")
        config_button.setObjectName("legacyConfigureButton")
        config_button.clicked.connect(self._open_configuration_dialog)
        tools_button = QPushButton("Tools")
        tools_button.setObjectName("legacyToolsButton")
        tools_button.clicked.connect(self._open_tools_dialog)
        left_layout.addWidget(open_button)
        left_layout.addWidget(config_button)
        left_layout.addWidget(tools_button)
        left_layout.addWidget(self.trace_attributes, 1)
        left_layout.addStretch(1)
        export_row = QHBoxLayout()
        print_button = QPushButton("Print")
        print_button.setObjectName("legacyExportButton")
        bmp_button = QPushButton("BMP")
        bmp_button.setObjectName("legacyExportButton")
        print_button.clicked.connect(self._print_current_view)
        bmp_button.clicked.connect(self.export_image)
        export_row.addWidget(print_button)
        export_row.addWidget(bmp_button)
        left_layout.addLayout(export_row)
        nav_row = QHBoxLayout()
        prev_button = QPushButton("<Prev")
        prev_button.setObjectName("legacyNavButton")
        next_button = QPushButton("Next>")
        next_button.setObjectName("legacyNavButton")
        prev_button.clicked.connect(lambda: self._step_trace_window(-1))
        next_button.clicked.connect(lambda: self._step_trace_window(1))
        nav_row.addWidget(prev_button)
        nav_row.addWidget(next_button)
        left_layout.addLayout(nav_row)
        nav_row2 = QHBoxLayout()
        first_button = QPushButton("<<First")
        first_button.setObjectName("legacyNavButton")
        last_button = QPushButton("Last>>")
        last_button.setObjectName("legacyNavButton")
        first_button.clicked.connect(lambda: self._jump_trace_window(False))
        last_button.clicked.connect(lambda: self._jump_trace_window(True))
        nav_row2.addWidget(first_button)
        nav_row2.addWidget(last_button)
        left_layout.addLayout(nav_row2)
        center = QFrame(self)
        center.setObjectName("segdCanvasFrame")
        center_grid = QGridLayout(center)
        center_grid.setContentsMargins(0, 0, 0, 0)
        center_grid.setSpacing(0)
        center_content = QWidget(center)
        center_layout = QVBoxLayout(center_content)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        self.canvas = SegdImageView(center_content)
        self.canvas.picked.connect(self._on_pick)
        self.canvas.measured.connect(self._on_measurement)
        self.canvas.hovered.connect(self._on_hover)
        self.canvas.hover_cleared.connect(self._on_hover_cleared)
        self.canvas.trace_inspect_requested.connect(self._on_trace_inspect_requested)
        self.canvas.copy_trace_requested.connect(self._copy_trace_details)
        self.canvas.copy_view_requested.connect(self._copy_view_image)
        self.canvas.fit_requested.connect(self.zoom_to_fit)
        self.canvas.view_resized.connect(self._on_view_resized)
        self.canvas.data_window_changed.connect(self._on_canvas_window_changed)
        center_layout.addWidget(self.canvas, 1)
        self.hint_label = QLabel("Mouse wheel: zoom | Ctrl+wheel: horizontal | Shift+wheel: vertical | Right-click: trace waveform")
        self.hint_label.setStyleSheet("color:#0A37FF;font-size:8pt;padding:1px 5px;background:#F4F4F4;")
        center_layout.addWidget(self.hint_label)
        center_grid.addWidget(center_content, 0, 0)

        right_panel = QFrame(self)
        right_panel.setObjectName("segdLegacyRightPanel")
        right_panel.setFixedWidth(138)
        right_panel.setStyleSheet("QFrame#segdLegacyRightPanel{background:#EEEEEE;border-left:1px solid #C6C6C6;}")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(5, 4, 5, 4)
        right_layout.setSpacing(4)
        right_layout.addWidget(self.status_legend)
        right_layout.addWidget(self.file_header_panel, 1)

        body.addWidget(left_panel)
        body.addWidget(center, 1)
        body.addWidget(right_panel)
        root.addLayout(body, 1)

        self.busy_overlay = BusyOverlay(self)
        self.busy_overlay.setGeometry(self.rect())

    def _create_view_controls_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(7)

        view_group = QGroupBox("Display Settings")
        view_form = QFormLayout(view_group)

        self.display_combo = QComboBox()
        self.display_combo.addItem("Wiggle", "wiggle")
        self.display_combo.addItem("Variable Area", "variable_area")
        self.display_combo.addItem("Variable Density (Grayscale)", "variable_density")
        self.display_combo.addItem("Color Density", "color_density")
        self.display_combo.addItem("Wiggle + Color", "wiggle_color")
        self.display_combo.setCurrentIndex(1)
        self.display_combo.currentIndexChanged.connect(self._on_control_changed)

        self.trace_start_spin = QSpinBox()
        self.trace_start_spin.setMinimum(1)
        self.trace_start_spin.setMaximum(1)
        self.trace_start_spin.editingFinished.connect(self._on_control_changed)

        self.trace_end_spin = QSpinBox()
        self.trace_end_spin.setMinimum(1)
        self.trace_end_spin.setMaximum(1)
        self.trace_end_spin.editingFinished.connect(self._on_control_changed)

        self.sample_start_spin = QSpinBox()
        self.sample_start_spin.setMinimum(1)
        self.sample_start_spin.setMaximum(1)
        self.sample_start_spin.editingFinished.connect(self._on_control_changed)

        self.sample_end_spin = QSpinBox()
        self.sample_end_spin.setMinimum(1)
        self.sample_end_spin.setMaximum(1)
        self.sample_end_spin.editingFinished.connect(self._on_control_changed)

        self.wiggle_scale_spin = QDoubleSpinBox()
        self.wiggle_scale_spin.setRange(0.10, 8.00)
        self.wiggle_scale_spin.setSingleStep(0.10)
        self.wiggle_scale_spin.setDecimals(2)
        self.wiggle_scale_spin.setValue(1.00)
        self.wiggle_scale_spin.setSuffix(" x")
        self.wiggle_scale_spin.valueChanged.connect(self._on_control_changed)

        self.polarity_combo = QComboBox()
        self.polarity_combo.addItem("Normal", 1)
        self.polarity_combo.addItem("Reverse", -1)
        self.polarity_combo.currentIndexChanged.connect(self._on_control_changed)

        self.fill_polarity_combo = QComboBox()
        self.fill_polarity_combo.addItem("Positive", True)
        self.fill_polarity_combo.addItem("Negative", False)
        self.fill_polarity_combo.currentIndexChanged.connect(self._on_control_changed)

        self.qc_colors_check = QCheckBox("Color traces by QC status")
        self.qc_colors_check.setChecked(True)
        self.qc_colors_check.toggled.connect(self._on_control_changed)

        view_form.addRow("Display", self.display_combo)
        view_form.addRow("First Trace", self.trace_start_spin)
        view_form.addRow("Last Trace", self.trace_end_spin)
        view_form.addRow("First Sample", self.sample_start_spin)
        view_form.addRow("Last Sample", self.sample_end_spin)
        view_form.addRow("Wiggle Scale", self.wiggle_scale_spin)
        view_form.addRow("Polarity", self.polarity_combo)
        view_form.addRow("Fill Polarity", self.fill_polarity_combo)
        view_form.addRow(self.qc_colors_check)

        layout.addWidget(view_group)
        layout.addStretch(1)
        return widget

    def _create_gain_controls_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(7)

        gain_group = QGroupBox("Gain Settings")
        gain_form = QFormLayout(gain_group)

        self.gain_combo = QComboBox()
        self.gain_combo.addItem("Fixed Gain Display", "fixed")
        self.gain_combo.addItem("Display Normalised to Peak (by Trace)", "trace_balance")
        self.gain_combo.addItem("AGC", "agc")
        self.gain_combo.addItem("No Gain", "none")
        self.gain_combo.setCurrentIndex(1)
        self.gain_combo.currentIndexChanged.connect(self._on_control_changed)

        self.fixed_gain_spin = QDoubleSpinBox()
        self.fixed_gain_spin.setRange(-60.0, 60.0)
        self.fixed_gain_spin.setValue(18.0)
        self.fixed_gain_spin.setSuffix(" dB")
        self.fixed_gain_spin.valueChanged.connect(self._on_control_changed)

        self.agc_window_spin = QDoubleSpinBox()
        self.agc_window_spin.setRange(10.0, 4000.0)
        self.agc_window_spin.setSingleStep(10.0)
        self.agc_window_spin.setValue(100.0)
        self.agc_window_spin.setSuffix(" ms")
        self.agc_window_spin.valueChanged.connect(self._on_control_changed)

        self.clip_spin = QDoubleSpinBox()
        self.clip_spin.setRange(0.50, 4.00)
        self.clip_spin.setDecimals(2)
        self.clip_spin.setValue(0.75)
        self.clip_spin.setSuffix("")
        self.clip_spin.valueChanged.connect(self._on_control_changed)

        self.remove_dc_check = QCheckBox("Remove DC bias")
        self.remove_dc_check.setChecked(True)
        self.remove_dc_check.toggled.connect(self._on_control_changed)

        gain_form.addRow("Mode", self.gain_combo)
        gain_form.addRow("Fixed Gain", self.fixed_gain_spin)
        gain_form.addRow("AGC Window", self.agc_window_spin)
        gain_form.addRow("Trace Clip (0.5 - 4)", self.clip_spin)
        gain_form.addRow(self.remove_dc_check)

        color_group = QGroupBox("Color Gain / Density")
        color_form = QFormLayout(color_group)

        self.color_palette_combo = QComboBox()
        self.color_palette_combo.addItem("Seismic Blue–White–Red", "seismic")
        self.color_palette_combo.addItem("Blue–White–Red", "blue_white_red")
        self.color_palette_combo.addItem("Viridis", "viridis")
        self.color_palette_combo.addItem("Grayscale", "grayscale")
        self.color_palette_combo.setToolTip("Palette used by Color Density and Wiggle + Color display modes.")
        self.color_palette_combo.currentIndexChanged.connect(self._on_control_changed)

        self.color_gain_spin = QDoubleSpinBox()
        self.color_gain_spin.setRange(0.10, 8.00)
        self.color_gain_spin.setSingleStep(0.10)
        self.color_gain_spin.setDecimals(2)
        self.color_gain_spin.setValue(1.00)
        self.color_gain_spin.setSuffix(" x")
        self.color_gain_spin.setToolTip(
            "Display-only color amplitude gain. Values above 1 strengthen weak color amplitudes; "
            "the original SEG-D samples are never modified."
        )
        self.color_gain_spin.valueChanged.connect(self._on_control_changed)

        color_hint = QLabel(
            "Use View → Color Density or Wiggle + Color. Color Gain changes only the visual contrast, not source data."
        )
        color_hint.setWordWrap(True)
        color_hint.setStyleSheet("color:#607080;font-size:10px;")

        color_form.addRow("Palette", self.color_palette_combo)
        color_form.addRow("Color Gain", self.color_gain_spin)
        color_form.addRow(color_hint)

        layout.addWidget(gain_group)
        layout.addWidget(color_group)
        layout.addStretch(1)
        return widget

    def _create_tools_tab(self) -> QWidget:
        from modules.seismic.segd_viewer import segd_tools

        widget = QWidget()
        widget.setStyleSheet(
            "QWidget{background:#F3F6F9;color:#173B53;}"
            "QTabWidget::pane{border:1px solid #C7D3DD;border-radius:6px;background:#FFFFFF;top:-1px;}"
            "QTabBar::tab{background:#E8EEF4;color:#263746;border:1px solid #C7D3DD;"
            "border-bottom:0;border-top-left-radius:5px;border-top-right-radius:5px;"
            "padding:6px 16px;font-weight:800;min-width:78px;}"
            "QTabBar::tab:selected{background:#FFFFFF;color:#0B4F76;}"
            "QTabBar::tab:hover{background:#F9FCFF;}"
            "QPushButton#segdToolAction{background:#FFFFFF;color:#102A3D;border:1px solid #B9C8D3;"
            "border-radius:6px;min-height:30px;padding:5px 10px;text-align:left;font-weight:850;}"
            "QPushButton#segdToolAction:hover{background:#EAF6FF;border-color:#2D9CDB;color:#073B5A;}"
            "QPushButton#segdToolAction:pressed{background:#D9EDF9;}"
        )
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("SEG-D Field Tools")
        title.setStyleSheet("font-size:13px;font-weight:900;color:#0F3D5D;background:transparent;")
        subtitle = QLabel("Receiver spread, trace diagnostics and file utilities. Use the main SEG-D Pick/Measure controls for canvas picking and measurement.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#657B8A;font-size:8pt;background:transparent;")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        tabs = QTabWidget(widget)
        tabs.setObjectName("segdToolsTabs")
        tabs.setDocumentMode(True)
        layout.addWidget(tabs, 1)

        pages = [
            ("Spread", "Receiver and field-spread QC", [
                ("Spread View", "Graphical receiver spread, sensor QC and time/frequency slices", segd_tools.spread_view),
                ("Panels", "Inspect receiver/channel panels and channel-set grouping", segd_tools.panels),
                ("Radio Sims", "Review radio similarity and telemetry diagnostics", segd_tools.radio_sims),
            ]),
            ("Trace", "Trace and record analysis", [
                ("Trace Analysis", "Waveform statistics, spectrum and trace-level diagnostics", segd_tools.trace_analysis),
                ("Record Sum / Diff", "Compare paired traces using sum and difference responses", segd_tools.record_sum_diff),
                ("Multi Vib Sim", "Multi-vibrator waveform similarity and correlation analysis", segd_tools.multi_vib_sim),
                ("Filters", "Display-only high-pass, low-pass and band-pass filtering", segd_tools.filters),
            ]),
            ("Files", "Safe file utilities", [
                ("Split Proc File", "Create safe derivative subsets from supported process files", segd_tools.split_proc_file),
                ("Fix Radio Sim File", "Inspect and safely repair supported radio-sim derivatives", segd_tools.fix_radio_sim_file),
                ("DSD Bin Files", "Inspect binary DSD-style content without modifying source data", segd_tools.dsd_bin_files),
            ]),
        ]

        for tab_name, caption, actions in pages:
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(10, 10, 10, 10)
            page_layout.setSpacing(8)
            cap = QLabel(caption)
            cap.setStyleSheet("color:#516A7B;font-size:8pt;font-weight:800;background:transparent;")
            page_layout.addWidget(cap)
            for label, tip, function in actions:
                button = QPushButton(label)
                button.setObjectName("segdToolAction")
                button.setToolTip(tip)
                button.clicked.connect(lambda _checked=False, fn=function: fn(self))
                page_layout.addWidget(button)
            page_layout.addStretch(1)
            tabs.addTab(page, tab_name)

        return widget

    def _open_configuration_dialog(self) -> None:
        if self.reader is None:
            QMessageBox.information(self, "SEG-D Configure", "Open a SEG-D file first.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Configure")
        dialog.setModal(True)
        dialog.setStyleSheet(
            "QDialog{background:#EEEEEE;}"
            "QGroupBox{border:1px solid #B8B8B8;margin-top:8px;background:#EEEEEE;font-size:8pt;}"
            "QGroupBox::title{subcontrol-origin:margin;left:8px;padding:0 2px;}"
            "QLineEdit,QSpinBox,QDoubleSpinBox{background:white;border:1px solid #8F8F8F;min-height:18px;font-size:8pt;}"
            "QPushButton{min-width:68px;min-height:22px;font-size:8pt;}"
        )
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(10, 8, 10, 8)
        options = QGroupBox("Options", dialog)
        form = QFormLayout(options)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(4)

        number_spin = QSpinBox(options)
        number_spin.setRange(1, max(1, self.reader.get_trace_count() * 10))
        number_spin.setValue(max(1, self.trace_end_spin.value() - self.trace_start_spin.value() + 1))
        start_time = QDoubleSpinBox(options)
        start_time.setRange(0.0, max(0.0, (self.reader.get_sample_count() - 1) * self.reader.get_sample_interval()))
        start_time.setDecimals(0)
        start_time.setValue((self.sample_start_spin.value() - 1) * self.reader.get_sample_interval())
        end_time = QDoubleSpinBox(options)
        end_time.setRange(0.0, max(0.0, (self.reader.get_sample_count() - 1) * self.reader.get_sample_interval()))
        end_time.setDecimals(0)
        end_time.setValue((self.sample_end_spin.value() - 1) * self.reader.get_sample_interval())
        omega_check = QCheckBox("Omega Tape Image Format", options)
        micro_check = QCheckBox("MicroSeismic Mode", options)
        form.addRow("Number of Traces to Display", number_spin)
        form.addRow("Display Start Time", start_time)
        form.addRow("Display EndTime", end_time)
        form.addRow(omega_check)
        form.addRow(micro_check)

        display_group = QGroupBox("Display Mode", options)
        display_layout = QVBoxLayout(display_group)
        fixed_radio = QRadioButton("Fixed Gain Display", display_group)
        peak_radio = QRadioButton("Display Normalised to Peak (by Trace)", display_group)
        display_layout.addWidget(fixed_radio)
        display_layout.addWidget(peak_radio)
        peak_radio.setChecked(str(self.gain_combo.currentData()) == "trace_balance")
        fixed_radio.setChecked(str(self.gain_combo.currentData()) == "fixed")
        clip_spin = QDoubleSpinBox(display_group)
        clip_spin.setRange(0.50, 4.00)
        clip_spin.setDecimals(2)
        clip_spin.setSingleStep(0.05)
        clip_spin.setValue(float(self.clip_spin.value()))
        gain_spin = QDoubleSpinBox(display_group)
        gain_spin.setRange(-60.0, 60.0)
        gain_spin.setDecimals(1)
        gain_spin.setValue(float(self.fixed_gain_spin.value()))
        display_form = QFormLayout()
        display_form.addRow("Trace Clip (0.5 - 4)", clip_spin)
        display_form.addRow("Initial Gain (db)", gain_spin)
        display_layout.addLayout(display_form)
        form.addRow(display_group)

        ignore_tilt = QCheckBox("Ignore Tilt Errors if more than 100", options)
        by_line = QRadioButton("Display By Line", options)
        specified = QRadioButton("Display by Specified Number of Traces", options)
        display_all = QRadioButton("Display All", options)
        specified.setChecked(True)
        form.addRow(ignore_tilt)
        form.addRow(by_line)
        form.addRow(specified)
        form.addRow(display_all)

        header_group = QGroupBox("Headers", options)
        header_form = QFormLayout(header_group)
        oil_company = QLineEdit("A. Company", header_group)
        contractor = QLineEdit("Geosource", header_group)
        crew = QLineEdit("6824", header_group)
        header_form.addRow("Oil Company", oil_company)
        header_form.addRow("Contractor", contractor)
        header_form.addRow("Crew", crew)
        form.addRow(header_group)
        layout.addWidget(options)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dialog)
        layout.addWidget(buttons)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        total_traces = self.reader.get_trace_count()
        total_samples = self.reader.get_sample_count()
        interval = max(float(self.reader.get_sample_interval()), 1e-9)
        count_requested = int(number_spin.value())
        if display_all.isChecked():
            count_requested = total_traces
        count = max(1, min(total_traces, count_requested))
        trace_start = max(1, min(self.trace_start_spin.value(), total_traces))
        trace_end = min(total_traces, trace_start + count - 1)
        if trace_end - trace_start + 1 < count:
            trace_start = max(1, trace_end - count + 1)
        sample_start = max(1, min(total_samples, int(round(start_time.value() / interval)) + 1))
        sample_end = max(sample_start, min(total_samples, int(round(end_time.value() / interval)) + 1))
        blockers = [QSignalBlocker(self.trace_start_spin), QSignalBlocker(self.trace_end_spin), QSignalBlocker(self.sample_start_spin), QSignalBlocker(self.sample_end_spin)]
        self.trace_start_spin.setValue(trace_start)
        self.trace_end_spin.setValue(trace_end)
        self.sample_start_spin.setValue(sample_start)
        self.sample_end_spin.setValue(sample_end)
        del blockers
        if peak_radio.isChecked():
            self.gain_combo.setCurrentIndex(max(0, self.gain_combo.findData("trace_balance")))
        elif fixed_radio.isChecked():
            self.gain_combo.setCurrentIndex(max(0, self.gain_combo.findData("fixed")))
        self.clip_spin.setValue(float(clip_spin.value()))
        self.fixed_gain_spin.setValue(float(gain_spin.value()))
        self.render_current_view()

    def _open_tools_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Tools")
        dialog.resize(560, 500)
        dialog.setStyleSheet(
            "QDialog{background:#F3F6F9;}"
            "QPushButton{background:#FFFFFF;color:#102A3D;border:1px solid #B9C8D3;"
            "border-radius:5px;padding:5px 12px;font-weight:800;}"
            "QPushButton:hover{background:#EAF6FF;border-color:#2D9CDB;}"
        )
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        tools = self._create_tools_tab()
        layout.addWidget(tools, 1)
        close = QPushButton("Close", dialog)
        close.clicked.connect(dialog.accept)
        layout.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
        dialog.exec()

    def _nudge_wiggle_scale(self, factor: float) -> None:
        self.wiggle_scale_spin.setValue(max(self.wiggle_scale_spin.minimum(), min(self.wiggle_scale_spin.maximum(), self.wiggle_scale_spin.value() * float(factor))))
        self.render_current_view()

    def _step_trace_window(self, direction: int) -> None:
        if self.reader is None:
            return
        total = self.reader.get_trace_count()
        width = max(1, self.trace_end_spin.value() - self.trace_start_spin.value() + 1)
        step = width * int(direction)
        start = max(1, min(total - width + 1, self.trace_start_spin.value() + step))
        self.trace_start_spin.setValue(start)
        self.trace_end_spin.setValue(min(total, start + width - 1))
        self.render_current_view()

    def _jump_trace_window(self, last: bool) -> None:
        if self.reader is None:
            return
        total = self.reader.get_trace_count()
        width = max(1, self.trace_end_spin.value() - self.trace_start_spin.value() + 1)
        start = max(1, total - width + 1) if last else 1
        self.trace_start_spin.setValue(start)
        self.trace_end_spin.setValue(min(total, start + width - 1))
        self.render_current_view()

    def _print_current_view(self) -> None:
        self.export_image()

    def _choose_file(self) -> None:
        start_folder = self.file_path.parent if self.file_path else Path.home()
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open SEG-D File",
            str(start_folder),
            "SEG-D Files (*.segd *.sgd *.d *.dat);;All Files (*.*)",
        )
        if path:
            self.open_file(path)

    def open_file(self, file_path: str | Path) -> None:
        path = Path(file_path)
        if not path.is_file():
            QMessageBox.critical(self, "SEG-D Open Error", f"SEG-D file not found:\n{path}")
            return
        self.file_path = path
        self._open_generation += 1
        generation = self._open_generation
        self._render_generation += 1
        self._opening_file = True
        self._open_started_at = perf_counter()
        self.loading_started.emit("Opening SEG-D", f"Reading and indexing {path.name}")
        self.busy_overlay.show_busy("Opening SEG-D", "Reading headers and indexing traces", None)
        worker = OpenFileWorker(generation, path)
        key = f"open:{generation}"
        self._workers[key] = worker
        worker.signals.progress.connect(self._on_open_progress)
        worker.signals.result.connect(self._on_open_result)
        worker.signals.error.connect(self._on_open_error)
        worker.signals.finished.connect(lambda gen: self._workers.pop(f"open:{gen}", None))
        self._open_pool.start(worker)

    def _on_open_progress(self, generation: int, value: int, message: str) -> None:
        if self._closing or generation != self._open_generation:
            return
        self.busy_overlay.update_progress(value, message)
        # File indexing is the first phase of opening; reserve the final part of
        # the full-page progress bar for the initial seismic render so progress
        # never jumps backwards from 100% to a low render percentage.
        self.loading_progress.emit(min(78, max(0, int(value * 0.78))), message)

    def _on_open_result(self, generation: int, reader: SegdReader) -> None:
        if self._closing or generation != self._open_generation:
            try:
                reader.close()
            except Exception:
                pass
            return

        trace_count = reader.get_trace_count()
        sample_count = reader.get_sample_count()
        if trace_count <= 0 or sample_count <= 0:
            reader.close()
            self._on_open_error(generation, "The SEG-D reader returned zero traces or zero samples.")
            return

        if self.reader is not None:
            self._reader_history.append(self.reader)
        self.reader = reader
        self.setProperty("segd_file_path", str(self.file_path.resolve()))
        self.setProperty("module_id", "segd")

        blockers = [
            QSignalBlocker(self.trace_start_spin),
            QSignalBlocker(self.trace_end_spin),
            QSignalBlocker(self.sample_start_spin),
            QSignalBlocker(self.sample_end_spin),
        ]
        self.trace_start_spin.setMaximum(trace_count)
        self.trace_end_spin.setMaximum(trace_count)
        self.trace_start_spin.setValue(1)
        canvas_width, _ = self.canvas.target_render_size()
        initial_trace_count = min(trace_count, 300)
        self.trace_end_spin.setValue(min(trace_count, initial_trace_count))
        self.sample_start_spin.setMaximum(sample_count)
        self.sample_end_spin.setMaximum(sample_count)
        self.sample_start_spin.setValue(1)
        self.sample_end_spin.setValue(sample_count)
        del blockers

        summary = reader.metadata_summary()
        self.file_label.setText(self.file_path.name)
        self.info_label.setText(
            f"Format: {summary['format_code']}   Rev: {summary['revision']}   "
            f"Traces: {summary['trace_count']:,}   Seismic: {summary['seismic_trace_count']:,}   "
            f"Aux: {summary['aux_trace_count']:,}   Samples: {summary['sample_count']:,}   "
            f"Interval: {summary['sample_interval_ms']:g} ms"
        )
        self.canvas.set_data_extent(trace_count, sample_count)
        self.header_viewer.set_reader(reader)
        self.file_header_panel.set_reader(reader)
        self.trace_attributes.clear_values()
        self._last_hover_trace = -1
        self._schedule_render(0)

    def _on_open_error(self, generation: int, message: str) -> None:
        if self._closing or generation != self._open_generation:
            return
        self.busy_overlay.hide()
        self._opening_file = False
        self.loading_finished.emit()
        QMessageBox.critical(self, "SEG-D Open Error", f"Failed to open SEG-D file:\n{self.file_path}\n\n{message}")

    def reload_file(self) -> None:
        self.open_file(self.file_path)

    def close_file(self) -> None:
        self._closing = True
        self._open_generation += 1
        self._render_generation += 1
        self._render_timer.stop()
        self._resize_timer.stop()
        if self._active_render_worker is not None:
            self._active_render_worker.cancel()
        self._open_pool.waitForDone(2000)
        self._render_pool.waitForDone(2000)
        readers: list[SegdReader] = []
        if self.reader is not None:
            readers.append(self.reader)
            self.reader = None
        readers.extend(self._reader_history)
        self._reader_history.clear()
        for reader in readers:
            try:
                reader.close()
            except Exception:
                pass

    def toggle_headers(self) -> None:
        self._show_headers_panel()

    def _show_headers_panel(self, trace_index: Optional[int] = None) -> None:
        if trace_index is not None:
            self.header_viewer.set_trace(trace_index)
            if self.reader is not None:
                self.file_header_panel.set_trace(self.reader, trace_index)
        dialog = QDialog(self)
        dialog.setWindowTitle("Headers")
        dialog.resize(520, 620)
        layout = QVBoxLayout(dialog)
        viewer = HeaderViewer(dialog)
        if self.reader is not None:
            viewer.set_reader(self.reader)
            if trace_index is not None:
                viewer.set_trace(trace_index)
        layout.addWidget(viewer, 1)
        close = QPushButton("Close", dialog)
        close.clicked.connect(dialog.accept)
        layout.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
        dialog.exec()

    def set_display_mode(self, mode: str) -> None:
        index = self.display_combo.findData(mode)
        if index >= 0:
            if self.display_combo.currentIndex() == index:
                self.render_current_view()
            else:
                self.display_combo.setCurrentIndex(index)

    def set_color_palette(self, palette: str) -> None:
        index = self.color_palette_combo.findData(palette)
        if index >= 0:
            self.color_palette_combo.setCurrentIndex(index)

    def set_color_gain(self, gain: float) -> None:
        self.color_gain_spin.setValue(float(gain))

    def set_gain_mode(self, mode: str) -> None:
        index = self.gain_combo.findData(mode)
        if index >= 0:
            if self.gain_combo.currentIndex() == index:
                self.render_current_view()
            else:
                self.gain_combo.setCurrentIndex(index)

    def set_interaction_mode(self, mode: str) -> None:
        self.canvas.set_mode(mode)
        self.canvas.setFocus(Qt.FocusReason.OtherFocusReason)
        if mode == "pick":
            self.position_label.setText("Pick mode: click one trace/sample point. An action menu opens after the pick.")
            if hasattr(self, "hint_label"):
                self.hint_label.setText("Pick mode: click any trace/sample. Press Esc to clear the mark.")
        elif mode == "measure":
            self.position_label.setText("Measure mode: click the start point, move the cursor to preview, then click the end point.")
            if hasattr(self, "hint_label"):
                self.hint_label.setText("Measure mode: click start, move to preview, click end. Press Esc to clear.")
        else:
            self.position_label.setText("Pan mode: drag to pan, mouse wheel to zoom, right-click for trace options.")
            if hasattr(self, "hint_label"):
                self.hint_label.setText("Mouse wheel: zoom | Ctrl+wheel: horizontal | Shift+wheel: vertical | Right-click: trace waveform")

    def zoom_to_fit(self) -> None:
        self.canvas.fit_to_view()

    def clear_picks(self) -> None:
        self.canvas.clear_picks()
        for attr in ("_pick_action_dialog", "_measure_action_dialog"):
            dialog = getattr(self, attr, None)
            if dialog is not None:
                try:
                    dialog.close()
                except Exception:
                    pass
                setattr(self, attr, None)
        self.position_label.setText("Pick and measurement marks cleared")

    def export_image(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export SEG-D View",
            str(Path.home() / f"{self.file_path.stem}_view.png"),
            "PNG Image (*.png);;Bitmap Image (*.bmp)",
        )
        if not path:
            return
        output = Path(path)
        if not output.suffix:
            output = output.with_suffix(".bmp" if "Bitmap" in _ else ".png")
        self.canvas.grab().save(str(output))

    def run_qc(self, qc_type: str = "full") -> None:
        if self.reader is None:
            QMessageBox.warning(self, "SEG-D QC", "Open a SEG-D file first.")
            return
        self.loading_started.emit("Running SEG-D QC", f"Executing {qc_type.title()} QC checks")
        self.loading_progress.emit(5, "Preparing SEG-D QC inputs")
        QApplication.processEvents()
        try:
            self._run_qc_impl(qc_type)
            try:
                from core.data_access.local_file_cache import LocalActivityHistory
                LocalActivityHistory().record(
                    module="segd",
                    action=f"run_{qc_type}_qc",
                    file_path=self.file_path,
                    details={"trace_count": self.reader.get_trace_count(), "sample_count": self.reader.get_sample_count()},
                )
            except Exception:
                pass
        finally:
            self.loading_finished.emit()

    def _run_qc_impl(self, qc_type: str = "full") -> None:
        if self.reader is None:
            return

        started = perf_counter()
        findings: list[dict[str, Any]] = []
        stages: list[dict[str, Any]] = []

        def add_finding(stage_key: str, code: str, severity: str, category: str, title: str, description: str, action: str = "Review the acquisition notes and original SEG-D export.", observed: Any = None, unit: str = "") -> None:
            item: dict[str, Any] = {
                "stage_key": stage_key,
                "code": code,
                "severity": severity,
                "category": category,
                "title": title,
                "description": description,
                "suggested_action": action,
            }
            if observed is not None:
                item["observed_value"] = observed
            if unit:
                item["unit"] = unit
            findings.append(item)

        def stage_result(score: float, stage_findings: int = 0, hard_fail: bool = False) -> str:
            if hard_fail or score < 60:
                return "fail"
            if stage_findings or score < 90:
                return "warn"
            return "pass"

        def add_stage(stage_key: str, stage_name: str, score: float, metrics: dict[str, Any], message: str, stage_findings: int = 0, hard_fail: bool = False) -> None:
            result = stage_result(score, stage_findings, hard_fail)
            stages.append({
                "stage_key": stage_key,
                "stage_name": stage_name,
                "status": "completed",
                "result": result,
                "score": float(max(0.0, min(100.0, score))),
                "metrics": metrics,
                "message": message,
            })

        self.loading_progress.emit(10, "Reading SEG-D record, header and trace dimensions")
        QApplication.processEvents()
        trace_count = int(self.reader.get_trace_count())
        sample_count = int(self.reader.get_sample_count())
        seismic_count = int(self.reader.get_seismic_trace_count())
        aux_count = int(self.reader.get_aux_trace_count())
        channel_count = int(self.reader.get_channel_count())
        sample_interval = float(self.reader.get_sample_interval())
        format_code = int(self.reader.get_format_code())
        revision = str(self.reader.get_revision())

        header_findings = 0
        header_score = 100.0
        if trace_count <= 0:
            header_findings += 1; header_score -= 65
            add_finding("header_integrity", "SEGD-NO-TRACES", "error", "header", "No traces detected", "The SEG-D file did not expose any physical traces.", "Verify file completeness and SEG-D format/export settings.")
        if sample_count <= 0:
            header_findings += 1; header_score -= 45
            add_finding("header_integrity", "SEGD-NO-SAMPLES", "error", "header", "No samples detected", "Trace/channel descriptors do not provide a valid sample count.", "Review channel-set descriptors and acquisition export settings.")
        if sample_interval <= 0:
            header_findings += 1; header_score -= 25
            add_finding("header_integrity", "SEGD-BAD-SAMPLE-INTERVAL", "error", "header", "Invalid sample interval", "The SEG-D sample interval is not positive.", "Confirm the channel-set descriptor and trace header sample-rate fields.", sample_interval, "ms")
        if format_code != 8058:
            header_findings += 1; header_score -= 10
            add_finding("header_integrity", "SEGD-FORMAT", "warning", "header", "Non-optimized SEG-D format code", f"Format code {format_code} was detected; this viewer is optimized for 8058.", "Review the format code before final client delivery.", format_code)
        add_stage(
            "header_integrity", "Header Integrity", header_score,
            {
                "format_code": format_code,
                "revision": revision,
                "physical_traces": trace_count,
                "seismic_traces": seismic_count,
                "auxiliary_traces": aux_count,
                "channel_sets": channel_count,
                "samples_per_trace": sample_count,
                "sample_interval_ms": sample_interval,
            },
            "Record-level SEG-D header values, trace count and sample interval checked.",
            header_findings,
            hard_fail=trace_count <= 0 or sample_count <= 0 or sample_interval <= 0,
        )

        self.loading_progress.emit(28, "Auditing trace headers and channel-set consistency")
        QApplication.processEvents()
        trace_infos = []
        max_scan = min(trace_count, 2500)
        header_decode_errors = 0
        for i in range(max_scan):
            try:
                trace_infos.append(self.reader.get_trace_info(i))
            except Exception:
                header_decode_errors += 1
        sample_counts = [int(getattr(info, "sample_count", 0) or 0) for info in trace_infos]
        intervals = [float(getattr(info, "sample_interval_ms", 0.0) or 0.0) for info in trace_infos]
        channel_sets = [int(getattr(info, "channel_set", 0) or 0) for info in trace_infos]
        trace_numbers = [int(getattr(info, "trace_number", 0) or 0) for info in trace_infos]
        bad_samples = sum(1 for value in sample_counts if value <= 0 or (sample_count > 0 and value != sample_count))
        bad_intervals = sum(1 for value in intervals if value <= 0 or (sample_interval > 0 and abs(value - sample_interval) > max(0.001, sample_interval * 0.01)))
        duplicate_trace_numbers = max(0, len(trace_numbers) - len(set(trace_numbers))) if trace_numbers else 0
        trace_header_findings = 0
        trace_header_score = 100.0
        if header_decode_errors:
            trace_header_findings += 1; trace_header_score -= min(35, 5 + header_decode_errors)
            add_finding("trace_headers", "SEGD-TRACE-DECODE", "warning", "trace header", "Trace header decode errors", f"{header_decode_errors} trace header(s) could not be decoded during QC scan.", "Check trace-header extensions and manufacturer-specific fields.", header_decode_errors)
        if bad_samples:
            trace_header_findings += 1; trace_header_score -= min(35, 5 + bad_samples * 0.5)
            add_finding("trace_headers", "SEGD-SAMPLE-COUNT-MISMATCH", "warning", "trace header", "Inconsistent trace sample counts", f"{bad_samples} scanned trace(s) have missing or inconsistent sample counts.", "Confirm trace length consistency and re-export if required.", bad_samples)
        if bad_intervals:
            trace_header_findings += 1; trace_header_score -= min(35, 5 + bad_intervals * 0.5)
            add_finding("trace_headers", "SEGD-SAMPLE-INTERVAL-MISMATCH", "warning", "trace header", "Inconsistent trace sample intervals", f"{bad_intervals} scanned trace(s) have missing or inconsistent sample intervals.", "Verify sample-rate/header encoding before processing.", bad_intervals)
        if duplicate_trace_numbers:
            trace_header_findings += 1; trace_header_score -= min(18, 3 + duplicate_trace_numbers * 0.2)
            add_finding("trace_headers", "SEGD-DUPLICATE-TRACE-NUMBER", "info", "trace header", "Duplicate trace numbers in scanned window", f"{duplicate_trace_numbers} duplicate trace-number value(s) were found in the scanned trace headers.", "Review whether duplicates are expected within channel sets.", duplicate_trace_numbers)
        add_stage(
            "trace_headers", "Trace Header Consistency", trace_header_score,
            {
                "scanned_traces": max_scan,
                "decoded_trace_headers": len(trace_infos),
                "decode_errors": header_decode_errors,
                "unique_channel_sets": len(set(channel_sets)) if channel_sets else 0,
                "inconsistent_sample_counts": bad_samples,
                "inconsistent_sample_intervals": bad_intervals,
                "duplicate_trace_numbers": duplicate_trace_numbers,
            },
            "Trace headers, channel sets, sample counts and trace-number sequence checked.",
            trace_header_findings,
        )

        self.loading_progress.emit(48, "Checking receiver/channel QC flags")
        QApplication.processEvents()
        flag_counts: dict[str, int] = {"Resistance": 0, "Capacitance": 0, "Leakage": 0, "Tilt": 0, "Multiple": 0, "Edited": 0, "Auxiliary": 0, "Dead": 0}
        status_source = list(self._trace_statuses)
        if len(status_source) < trace_count:
            # Rebuild a status snapshot from trace headers where possible so QC does not depend only on the displayed window.
            for info in trace_infos:
                if getattr(info, "channel_type", 1) != 1:
                    status_source.append("Auxiliary")
                elif getattr(info, "trace_edit", 0) != 0:
                    status_source.append("Edited")
                else:
                    flags = tuple(getattr(info, "qc_flags", ()) or ())
                    if "Resistance" in flags:
                        status_source.append("Resistance")
                    elif "Capacitance" in flags:
                        status_source.append("Capacitance")
                    elif "Leakage" in flags:
                        status_source.append("Leakage")
                    elif "Tilt" in flags:
                        status_source.append("Tilt")
                    elif len(flags) > 1:
                        status_source.append("Multiple")
                    else:
                        status_source.append("Normal")
        for status in status_source:
            if status in flag_counts:
                flag_counts[status] += 1
        flagged_total = int(sum(v for k, v in flag_counts.items() if k not in {"Auxiliary"}))
        receiver_score = max(0.0, 100.0 - min(70.0, flagged_total * 3.0) - min(20.0, aux_count * 0.2))
        receiver_findings = 0
        if flagged_total:
            receiver_findings += 1
            add_finding("receiver_flags", "SEGD-RECEIVER-QC-FLAGS", "warning", "receiver", f"{flagged_total} receiver/channel QC flag(s)", "Receiver health attributes include resistance, capacitance, leakage, tilt, edited or dead-channel flags.", "Inspect flagged channels before accepting the spread for processing.", flagged_total, "traces")
        add_stage(
            "receiver_flags", "Receiver / Channel QC Flags", receiver_score,
            {**flag_counts, "flagged_total": flagged_total, "auxiliary_trace_count": aux_count},
            "Receiver resistance, capacitance, leakage, tilt, edited and auxiliary-channel flags summarized.",
            receiver_findings,
        )

        self.loading_progress.emit(68, "Analysing amplitude window statistics")
        QApplication.processEvents()
        data = np.asarray(self._raw_data, dtype=float) if getattr(self, "_raw_data", np.asarray([])).size else np.asarray([])
        amp_metrics: dict[str, Any]
        amplitude_score = 100.0
        amplitude_findings = 0
        if data.size:
            finite = data[np.isfinite(data)]
            zero_trace_count = int(np.sum(np.all(np.nan_to_num(data) == 0, axis=1))) if data.ndim == 2 else 0
            nan_count = int(data.size - finite.size)
            if finite.size:
                abs_finite = np.abs(finite)
                peak = float(np.nanmax(abs_finite))
                rms = float(np.sqrt(np.nanmean(finite * finite)))
                p50 = float(np.nanpercentile(abs_finite, 50))
                p95 = float(np.nanpercentile(abs_finite, 95))
                p99 = float(np.nanpercentile(abs_finite, 99))
                clip_limit = p99 if p99 > 0 else peak
                clipped_ratio = float(np.count_nonzero(abs_finite >= max(clip_limit, 1e-12)) / max(1, finite.size))
            else:
                peak = rms = p50 = p95 = p99 = clipped_ratio = 0.0
            if zero_trace_count:
                amplitude_findings += 1; amplitude_score -= min(45, 8 + zero_trace_count * 2)
                add_finding("amplitude_window", "SEGD-ZERO-TRACE", "warning", "amplitude", "Zero-amplitude traces detected", f"{zero_trace_count} trace(s) in the displayed/full render window contain only zero samples.", "Inspect acquisition status, dead channels and edit flags.", zero_trace_count, "traces")
            if nan_count:
                amplitude_findings += 1; amplitude_score -= min(30, 5 + nan_count * 0.001)
                add_finding("amplitude_window", "SEGD-NON-FINITE-SAMPLES", "warning", "amplitude", "Non-finite sample values", f"{nan_count} non-finite sample value(s) were detected in the QC window.", "Review the SEG-D decode and trace sample format.", nan_count, "samples")
            if clipped_ratio > 0.025:
                amplitude_findings += 1; amplitude_score -= min(25, clipped_ratio * 300)
                add_finding("amplitude_window", "SEGD-AMPLITUDE-CLIPPING", "warning", "amplitude", "Possible amplitude clipping/outliers", f"{100*clipped_ratio:.2f}% of finite samples sit at the upper 99th-percentile envelope.", "Review gain, clipping and field electronics before final processing.", f"{100*clipped_ratio:.2f}", "%")
            amp_metrics = {
                "window_trace_count": int(data.shape[0]) if data.ndim == 2 else 0,
                "window_sample_count": int(data.shape[1]) if data.ndim == 2 else 0,
                "finite_sample_count": int(finite.size),
                "non_finite_sample_count": nan_count,
                "zero_trace_count": zero_trace_count,
                "rms_amplitude": rms,
                "peak_abs_amplitude": peak,
                "median_abs_amplitude": p50,
                "p95_abs_amplitude": p95,
                "p99_abs_amplitude": p99,
                "clipped_ratio_pct": 100.0 * clipped_ratio,
            }
        else:
            amplitude_score = 72.0
            amplitude_findings = 1
            amp_metrics = {"window_trace_count": 0, "window_sample_count": 0, "finite_sample_count": 0}
            add_finding("amplitude_window", "SEGD-NO-RENDERED-SAMPLES", "info", "amplitude", "No rendered trace window available", "QC could not inspect amplitudes because no trace window has been rendered yet.", "Click Render View or open the file again before rerunning amplitude QC.")
        add_stage(
            "amplitude_window", "Amplitude / Dead Trace QC", amplitude_score,
            amp_metrics,
            "Displayed trace-window amplitudes, zero traces, RMS, peak and clipping indicators checked.",
            amplitude_findings,
        )

        self.loading_progress.emit(82, "Preparing QC score, charts and exportable result tables")
        QApplication.processEvents()
        if stages:
            score = float(np.nanmean([float(stage.get("score", 0.0)) for stage in stages]))
        else:
            score = 0.0
        if any(str(item.get("severity", "")).lower() == "error" for item in findings) or any(stage.get("result") == "fail" for stage in stages):
            overall_result = "fail"
        elif findings or any(stage.get("result") == "warn" for stage in stages):
            overall_result = "warn"
        else:
            overall_result = "pass"
        duration_ms = int((perf_counter() - started) * 1000)
        summary_data = {
            "physical_traces": trace_count,
            "seismic_traces": seismic_count,
            "auxiliary_traces": aux_count,
            "samples_per_trace": sample_count,
            "sample_interval_ms": sample_interval,
            "format_code": format_code,
            "revision": revision,
            "qc_type": qc_type,
            "findings": len(findings),
            "stage_count": len(stages),
            "flagged_trace_statuses": flag_counts,
            "mean_stage_score": score,
            "duration_ms": duration_ms,
        }

        run_uuid = ""
        if self.db_engine is not None:
            try:
                from core.data_access.qc_history_repository import QcHistoryRepository
                run_uuid = QcHistoryRepository(self.db_engine).record_run(
                    module="segd", file_path=self.file_path, profile=f"SEG-D {qc_type.title()} QC",
                    status="completed", overall_result=overall_result, score=score, summary=summary_data,
                    parameters={"qc_type": qc_type, "scanned_trace_headers": max_scan}, stages=stages, findings=findings, duration_ms=duration_ms,
                )
            except Exception as error:
                self.position_label.setText(f"QC completed; history save failed: {error}")

        self.loading_progress.emit(100, "SEG-D QC is complete")
        QApplication.processEvents()
        dialog = SegdQcResultsDialog(
            file_path=self.file_path,
            qc_type=qc_type,
            summary=summary_data,
            stages=stages,
            findings=findings,
            overall_result=overall_result,
            score=score,
            run_uuid=run_uuid,
            duration_ms=duration_ms,
            parent=self,
        )
        dialog.exec()

    def _on_control_changed(self, *_args) -> None:
        self._schedule_render(320)

    def _schedule_render(self, delay_ms: int = 320) -> None:
        if self.reader is None or self._closing:
            return
        self._render_timer.stop()
        self._render_timer.start(max(0, int(delay_ms)))

    def render_current_view(self, *_args) -> None:
        if self.reader is None:
            QMessageBox.information(self, "SEG-D Render", "Open a SEG-D file before rendering.")
            return
        self.position_label.setText("Rendering current SEG-D view…")
        self._schedule_render(0)

    def _start_render(self) -> None:
        if self.reader is None or self._closing:
            return
        trace_start = min(self.trace_start_spin.value(), self.trace_end_spin.value()) - 1
        trace_end = max(self.trace_start_spin.value(), self.trace_end_spin.value())
        sample_start = min(self.sample_start_spin.value(), self.sample_end_spin.value()) - 1
        sample_end = max(self.sample_start_spin.value(), self.sample_end_spin.value())
        width, height = self.canvas.target_render_size()
        params = RenderParameters(
            trace_start=trace_start,
            trace_end=trace_end,
            sample_start=sample_start,
            sample_end=sample_end,
            gain_mode=str(self.gain_combo.currentData()),
            fixed_gain_db=float(self.fixed_gain_spin.value()),
            agc_window_ms=float(self.agc_window_spin.value()),
            clip_percentile=float(self.clip_spin.value()),
            display_mode=str(self.display_combo.currentData()),
            wiggle_scale=float(self.wiggle_scale_spin.value()),
            color_palette=str(self.color_palette_combo.currentData()),
            color_gain=float(self.color_gain_spin.value()),
            polarity=int(self.polarity_combo.currentData()),
            fill_positive=bool(self.fill_polarity_combo.currentData()),
            remove_dc=bool(self.remove_dc_check.isChecked()),
            qc_colors=bool(self.qc_colors_check.isChecked()),
            filter_enabled=bool(self._filter_enabled),
            filter_low_hz=float(self._filter_low_hz),
            filter_high_hz=float(self._filter_high_hz),
            width=width,
            height=height,
        )
        self._render_generation += 1
        generation = self._render_generation
        self.busy_overlay.show_busy("Rendering SEG-D", "Preparing seismic display", 0)
        for button in (getattr(self, "render_button", None), getattr(self, "header_render_button", None)):
            if button is not None:
                button.setEnabled(False)
                button.setText("Rendering…")
        worker = RenderWorker(generation, self.reader, params)
        key = f"render:{generation}"
        self._workers[key] = worker
        if self._active_render_worker is not None:
            self._active_render_worker.cancel()
        self._active_render_worker = worker
        worker.signals.progress.connect(self._on_render_progress)
        worker.signals.result.connect(self._on_render_result)
        worker.signals.error.connect(self._on_render_error)
        worker.signals.finished.connect(self._on_render_finished)
        self._render_pool.start(worker)

    def _on_render_finished(self, generation: int) -> None:
        self._workers.pop(f"render:{generation}", None)
        if generation == self._render_generation:
            self._active_render_worker = None
            for button, text in ((getattr(self, "render_button", None), "Render View"), (getattr(self, "header_render_button", None), "Render")):
                if button is not None:
                    button.setEnabled(True)
                    button.setText(text)

    def _on_render_progress(self, generation: int, value: int, message: str) -> None:
        if generation == self._render_generation and not self._closing:
            self.busy_overlay.update_progress(value, message)
            if self._opening_file:
                mapped = 78 + int(max(0, min(100, value)) * 0.22)
                self.loading_progress.emit(min(100, mapped), message)

    def _on_render_result(self, generation: int, result: dict[str, Any]) -> None:
        if self._closing or generation != self._render_generation or self.reader is None:
            return
        params: RenderParameters = result["params"]
        self._trace_start = params.trace_start
        self._trace_end = params.trace_end
        self._sample_start = params.sample_start
        self._sample_end = params.sample_end
        self._raw_data = result["raw"]
        self._trace_statuses = list(result["statuses"])
        self.canvas.set_image(
            result["image"],
            params.trace_start,
            params.trace_end,
            params.sample_start,
            params.sample_end,
            self.reader.get_sample_interval(),
            reset_view=True,
        )
        self.canvas.set_trace_statuses(self._trace_statuses)
        record_length = (self._sample_end - 1) * self.reader.get_sample_interval()
        self.position_label.setText(
            f"Trace {self._trace_start + 1}-{self._trace_end} | "
            f"Time {self._sample_start * self.reader.get_sample_interval():.0f}-{record_length:.0f} ms"
        )
        self.canvas.update()
        self.canvas.repaint()
        self.busy_overlay.hide()
        if not self._opening_file:
            self.position_label.setText(self.position_label.text() + " | Rendered")
        if self._opening_file:
            self._opening_file = False
            self.loading_finished.emit()

    def _on_render_error(self, generation: int, message: str) -> None:
        if self._closing or generation != self._render_generation:
            return
        self.busy_overlay.hide()
        self.position_label.setText("SEG-D render failed")
        for button, text in ((getattr(self, "render_button", None), "Render View"), (getattr(self, "header_render_button", None), "Render")):
            if button is not None:
                button.setEnabled(True)
                button.setText(text)
        if self._opening_file:
            self._opening_file = False
            self.loading_finished.emit()
        QMessageBox.critical(self, "SEG-D Render Error", message)

    def _on_canvas_window_changed(self, trace_start: int, trace_end: int, sample_start: int, sample_end: int) -> None:
        if self.reader is None:
            return
        total_traces = self.reader.get_trace_count()
        total_samples = self.reader.get_sample_count()
        width = max(1, min(total_traces, trace_end - trace_start))
        height = max(32, min(total_samples, sample_end - sample_start))
        trace_start = max(0, min(trace_start, total_traces - width))
        sample_start = max(0, min(sample_start, total_samples - height))
        trace_end = trace_start + width
        sample_end = sample_start + height
        blockers = [QSignalBlocker(self.trace_start_spin), QSignalBlocker(self.trace_end_spin), QSignalBlocker(self.sample_start_spin), QSignalBlocker(self.sample_end_spin)]
        self.trace_start_spin.setValue(trace_start + 1)
        self.trace_end_spin.setValue(trace_end)
        self.sample_start_spin.setValue(sample_start + 1)
        self.sample_end_spin.setValue(sample_end)
        del blockers
        self._schedule_render(0)

    def _on_view_resized(self) -> None:
        if self.reader is not None and not self._closing:
            self._resize_timer.start(260)

    def _trace_status(self, trace_index: int) -> str:
        local = trace_index - self._trace_start
        if 0 <= local < len(self._trace_statuses):
            return self._trace_statuses[local]
        if self.reader is not None:
            try:
                info = self.reader.get_trace_info(trace_index)
                if info.channel_type != 1:
                    return "Auxiliary"
                if info.trace_edit != 0:
                    return "Edited"
            except Exception:
                pass
        return "Normal"

    def _amplitude_at(self, trace: int, sample: int) -> float:
        trace_row = trace - self._trace_start
        sample_col = sample - self._sample_start
        if 0 <= trace_row < self._raw_data.shape[0] and 0 <= sample_col < self._raw_data.shape[1]:
            return float(self._raw_data[trace_row, sample_col])
        return 0.0

    def _on_pick(self, trace: int, sample: int) -> None:
        if self.reader is None:
            return
        old_dialog = getattr(self, "_pick_action_dialog", None)
        if old_dialog is not None:
            try:
                old_dialog.close()
            except Exception:
                pass
        amplitude = self._amplitude_at(trace, sample)
        time_ms = sample * self.reader.get_sample_interval()
        status = self._trace_status(trace)
        self.position_label.setText(
            f"Picked Trace {trace + 1} | Sample {sample + 1} | Time {time_ms:.2f} ms | Amplitude {amplitude:.6g}"
        )
        self.header_viewer.set_trace(trace)
        self.file_header_panel.set_trace(self.reader, trace)
        self.trace_attributes.set_trace(self.reader, trace, sample, time_ms, amplitude, status)
        dialog = SegdPickActionsDialog(
            trace=trace,
            sample=sample,
            time_ms=time_ms,
            amplitude=amplitude,
            status=status,
            on_inspect=lambda: self._on_trace_inspect_requested(trace, sample),
            on_headers=lambda: self._show_headers_panel(trace),
            on_copy=lambda: self._copy_trace_details(trace, sample),
            on_clear=self.clear_picks,
            parent=self,
        )
        dialog.setModal(False)
        dialog.show()
        self._pick_action_dialog = dialog

    def _on_hover(self, trace: int, sample: int) -> None:
        if self.reader is None:
            return
        amplitude = self._amplitude_at(trace, sample)
        time_ms = sample * self.reader.get_sample_interval()
        status = self._trace_status(trace)
        hover_text = (
            f"Trace {trace + 1}   Sample {sample + 1}   Time {time_ms:.2f} ms   "
            f"Amplitude {amplitude:.6g}   Status {status}"
        )
        self.position_label.setText(hover_text)
        if hasattr(self, "hint_label"):
            color = STATUS_COLORS.get(status, STATUS_COLORS["Normal"])
            self.hint_label.setText(hover_text)
            self.hint_label.setStyleSheet(
                f"color:rgb({color.red()},{color.green()},{color.blue()});"
                "font-size:8pt;padding:1px 5px;background:#F4F4F4;font-weight:700;"
            )
        self.trace_attributes.set_trace(self.reader, trace, sample, time_ms, amplitude, status)
        if trace != self._last_hover_trace:
            self._last_hover_trace = trace
            self.header_viewer.set_trace(trace)
            self.file_header_panel.set_trace(self.reader, trace)

    def _on_hover_cleared(self) -> None:
        if self.reader is None:
            self.position_label.clear()
            return
        text = (
            f"Trace {self._trace_start + 1}-{self._trace_end} | "
            f"Sample {self._sample_start + 1}-{self._sample_end}"
        )
        self.position_label.setText(text)
        if hasattr(self, "hint_label"):
            self.hint_label.setText("Mouse wheel: zoom | Ctrl+wheel: horizontal | Shift+wheel: vertical | Right-click: trace waveform")
            self.hint_label.setStyleSheet("color:#0A37FF;font-size:8pt;padding:1px 5px;background:#F4F4F4;")

    def _on_trace_inspect_requested(self, trace: int, sample: int) -> None:
        if self.reader is None:
            return
        try:
            dialog = TraceWaveformDialog(self.reader, trace, self)
            dialog.setModal(False)
            dialog.show()
            self._trace_dialog = dialog
        except Exception as error:
            QMessageBox.critical(self, "Trace Viewer Error", str(error))

    def _copy_trace_details(self, trace: int, sample: int) -> None:
        if self.reader is None:
            return
        try:
            info = self.reader.get_trace_info(trace)
            amplitude = self._amplitude_at(trace, sample)
            fields = [
                ("Trace", trace + 1), ("Sample", sample + 1), ("Channel Set", info.channel_set),
                ("Line", info.receiver_line), ("Point", info.receiver_point), ("Receiver Index", info.receiver_index),
                ("X", info.receiver_x), ("Y", info.receiver_y), ("Z", info.receiver_elevation),
                ("Resistance", info.resistance), ("Capacitance", info.capacitance),
                ("Leakage", info.leakage), ("Tilt", info.tilt), ("Status", self._trace_status(trace)),
                ("Amplitude", amplitude), ("Time ms", sample * self.reader.get_sample_interval()),
            ]
            text = "\n".join(f"{name}: {'—' if value is None else value}" for name, value in fields)
            QApplication.clipboard().setText(text)
            self.position_label.setText(f"Copied details for Trace {trace + 1}")
        except Exception as error:
            QMessageBox.warning(self, "Copy Trace Details", str(error))

    def _copy_view_image(self) -> None:
        pixmap = self.canvas.grab()
        if not pixmap.isNull():
            QApplication.clipboard().setPixmap(pixmap)
            self.position_label.setText("Current SEG-D view copied to clipboard")

    def _on_measurement(self, trace_1: int, sample_1: int, trace_2: int, sample_2: int) -> None:
        interval = self.reader.get_sample_interval() if self.reader is not None else 0.0
        start_time = sample_1 * interval
        end_time = sample_2 * interval
        delta_time_signed = end_time - start_time
        delta_time = abs(delta_time_signed)
        start_amp = self._amplitude_at(trace_1, sample_1)
        end_amp = self._amplitude_at(trace_2, sample_2)
        delta_amp = end_amp - start_amp
        text = (
            f"Measurement: T{trace_1 + 1}/S{sample_1 + 1} → T{trace_2 + 1}/S{sample_2 + 1} | "
            f"Δtrace {trace_2 - trace_1:+d} | Δsample {sample_2 - sample_1:+d} | "
            f"Δtime {delta_time_signed:+.3f} ms | Δamp {delta_amp:+.6g}"
        )
        self.position_label.setText(text)
        old_dialog = getattr(self, "_measure_action_dialog", None)
        if old_dialog is not None:
            try:
                old_dialog.close()
            except Exception:
                pass

        def copy_measurement() -> None:
            QApplication.clipboard().setText(
                "SEG-D Measurement\n"
                f"Start Trace: {trace_1 + 1}\nStart Sample: {sample_1 + 1}\n"
                f"Start Time ms: {start_time:.6g}\nStart Amplitude: {start_amp:.6g}\n"
                f"End Trace: {trace_2 + 1}\nEnd Sample: {sample_2 + 1}\n"
                f"End Time ms: {end_time:.6g}\nEnd Amplitude: {end_amp:.6g}\n"
                f"Delta Trace: {trace_2 - trace_1:+d}\n"
                f"Delta Sample: {sample_2 - sample_1:+d}\n"
                f"Delta Time ms: {delta_time_signed:+.6g}\n"
                f"Delta Amplitude: {delta_amp:+.6g}"
            )
            self.position_label.setText("Measurement copied to clipboard")

        dialog = SegdMeasureActionsDialog(
            trace_1=trace_1,
            sample_1=sample_1,
            trace_2=trace_2,
            sample_2=sample_2,
            delta_time_ms=delta_time,
            on_copy=copy_measurement,
            on_clear=self.clear_picks,
            parent=self,
        )
        dialog.setModal(False)
        dialog.show()
        self._measure_action_dialog = dialog

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if hasattr(self, "busy_overlay"):
            self.busy_overlay.setGeometry(self.rect())
            if self.busy_overlay.isVisible():
                self.busy_overlay.raise_()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.close_file()
        self.loading_finished.emit()
        super().closeEvent(event)