from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QWheelEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from modules.seismic.segy_qc.segy_reader import SegyReader
from modules.seismic.visualization.seismic_attributes import (
    ATTRIBUTE_NAMES,
    AttributeParameters,
    compute_attribute,
)
from modules.seismic.segy_viewer.segy_display import (
    DisplayGrid,
    align_traces_to_time_grid,
    apply_display_gain,
    build_time_grid,
    normalize_for_display,
    trace_rms,
)


@dataclass(frozen=True)
class SegyPick:
    trace_index: int
    sample_index: int
    time_ms: float
    amplitude: float
    kind: str = "Pick"

    def row(self) -> tuple[str, str, str, str, str]:
        return (
            self.kind,
            str(self.trace_index + 1),
            str(self.sample_index + 1),
            f"{self.time_ms:.3f}",
            f"{self.amplitude:.6g}",
        )


class _ColorButton(QPushButton):
    color_changed = Signal(QColor)

    def __init__(self, color: QColor, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self.setMinimumWidth(58)
        self.clicked.connect(self._choose)
        self._refresh()

    @property
    def color(self) -> QColor:
        return QColor(self._color)

    def set_color(self, color: QColor) -> None:
        if not color.isValid():
            return
        self._color = QColor(color)
        self._refresh()
        self.color_changed.emit(QColor(self._color))

    def _refresh(self) -> None:
        self.setText(self._color.name().upper())
        fg = "#000000" if self._color.lightness() > 145 else "#FFFFFF"
        self.setStyleSheet(
            f"QPushButton{{background:{self._color.name()};color:{fg};font-weight:900;"
            "border:1px solid #53606B;border-radius:4px;min-height:22px;padding:2px 5px;}}"
        )

    def _choose(self) -> None:
        selected = QColorDialog.getColor(self._color, self, "Select SEG-Y FT range colour")
        if selected.isValid():
            self.set_color(selected)


class _FTCanvas(QWidget):
    cursor_changed = Signal(float, float, float)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(720, 390)
        self.setMouseTracking(True)
        self._image = QImage()
        self._time_ms = np.array([], dtype=np.float64)
        self._frequency_hz = np.array([], dtype=np.float64)
        self._db = np.empty((0, 0), dtype=np.float32)
        self._cursor: Optional[QPointF] = None
        self._title = "Frequency-Time Analysis"

    def set_spectrogram(
        self,
        image: QImage,
        time_ms: np.ndarray,
        frequency_hz: np.ndarray,
        db_matrix: np.ndarray,
        title: str,
    ) -> None:
        self._image = image
        self._time_ms = np.asarray(time_ms, dtype=np.float64)
        self._frequency_hz = np.asarray(frequency_hz, dtype=np.float64)
        self._db = np.asarray(db_matrix, dtype=np.float32)
        self._title = title
        self.update()

    def plot_rect(self) -> QRectF:
        return QRectF(70, 42, max(1, self.width() - 92), max(1, self.height() - 92))

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(244, 247, 250))
        rect = self.plot_rect()
        painter.fillRect(rect, QColor(255, 255, 255))
        if not self._image.isNull():
            painter.drawImage(rect, self._image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(194, 205, 216), 1))
        for i in range(1, 6):
            x = rect.left() + rect.width() * i / 6
            y = rect.top() + rect.height() * i / 6
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        painter.setPen(QPen(QColor(25, 43, 59), 1))
        painter.drawRect(rect)
        painter.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        painter.drawText(QRectF(0, 8, self.width(), 25), Qt.AlignmentFlag.AlignCenter, self._title)
        painter.setFont(QFont("Arial", 8, QFont.Weight.Normal))
        if self._time_ms.size:
            lo = float(self._time_ms[0])
            hi = float(self._time_ms[-1])
            for i in range(7):
                frac = i / 6
                x = rect.left() + rect.width() * frac
                value = lo + (hi - lo) * frac
                painter.drawText(QRectF(x - 42, rect.bottom() + 5, 84, 18), Qt.AlignmentFlag.AlignCenter, f"{value:.0f}")
        if self._frequency_hz.size:
            lo = float(self._frequency_hz[0])
            hi = float(self._frequency_hz[-1])
            for i in range(6):
                frac = i / 5
                y = rect.bottom() - rect.height() * frac
                value = lo + (hi - lo) * frac
                painter.drawText(
                    QRectF(6, y - 9, 58, 18),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    f"{value:g}",
                )
        painter.setPen(QColor(72, 91, 108))
        painter.drawText(QRectF(0, rect.bottom() + 28, self.width(), 20), Qt.AlignmentFlag.AlignCenter, "Time (ms)")
        painter.save()
        painter.translate(14, rect.center().y() + 48)
        painter.rotate(-90)
        painter.drawText(QRectF(0, 0, 120, 18), Qt.AlignmentFlag.AlignCenter, "Frequency (Hz)")
        painter.restore()
        if self._cursor is not None and rect.contains(self._cursor):
            painter.setPen(QPen(QColor(255, 30, 30), 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(self._cursor.x(), rect.top()), QPointF(self._cursor.x(), rect.bottom()))
            painter.drawLine(QPointF(rect.left(), self._cursor.y()), QPointF(rect.right(), self._cursor.y()))
        painter.end()

    def mouseMoveEvent(self, event) -> None:
        rect = self.plot_rect()
        pos = event.position()
        self._cursor = QPointF(pos) if rect.contains(pos) else None
        if self._cursor is not None and self._time_ms.size and self._frequency_hz.size and self._db.size:
            fx = (pos.x() - rect.left()) / max(1.0, rect.width())
            fy = 1.0 - (pos.y() - rect.top()) / max(1.0, rect.height())
            ti = int(np.clip(round(fx * (self._db.shape[1] - 1)), 0, self._db.shape[1] - 1))
            fi = int(np.clip(round(fy * (self._db.shape[0] - 1)), 0, self._db.shape[0] - 1))
            self.cursor_changed.emit(float(self._time_ms[ti]), float(self._frequency_hz[fi]), float(self._db[fi, ti]))
        self.update()
        super().mouseMoveEvent(event)


class SegyFTAnalysisDialog(QDialog):
    """Crash-safe Qt spectrogram dialog for manual SEG-Y trace QC."""

    DEFAULT_RANGES = [
        (-90.0, -72.0, QColor(12, 18, 42)),
        (-72.0, -54.0, QColor(26, 66, 154)),
        (-54.0, -42.0, QColor(25, 145, 220)),
        (-42.0, -30.0, QColor(42, 185, 125)),
        (-30.0, -18.0, QColor(245, 220, 45)),
        (-18.0, -8.0, QColor(245, 132, 27)),
        (-8.0, 0.0, QColor(214, 32, 42)),
    ]

    def __init__(
        self,
        trace: np.ndarray,
        sample_interval_us: float,
        delay_ms: float,
        trace_number: int,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"SEG-Y FT Analysis — Trace {trace_number:,}")
        self.resize(980, 620)
        self.trace = np.asarray(trace, dtype=np.float64)
        self.dt_s = max(float(sample_interval_us) * 1e-6, 1e-9)
        self.delay_ms = float(delay_ms)
        self.trace_number = int(trace_number)
        self._ranges = [(lo, hi, QColor(color)) for lo, hi, color in self.DEFAULT_RANGES]
        self._time_ms = np.array([], dtype=np.float64)
        self._frequency_hz = np.array([], dtype=np.float64)
        self._db = np.empty((0, 0), dtype=np.float32)
        self._build_ui()
        self._recalculate()

    def _build_ui(self) -> None:
        self.setStyleSheet(
            "QDialog{background:#EEF2F6;font-size:8.5pt;}"
            "QLabel{color:#0A2F52;font-weight:700;}"
            "QPushButton{min-height:24px;padding:2px 8px;border:1px solid #8EA2B2;border-radius:4px;background:#FFFFFF;font-weight:800;}"
            "QPushButton:hover{background:#F1F8FF;border-color:#1D7FC0;}"
            "QDoubleSpinBox,QSpinBox{min-height:22px;border:1px solid #B7C5D1;border-radius:4px;background:#FFFFFF;padding:1px 4px;}"
            "QFrame#topCard,QFrame#rangeCard{background:#FFFFFF;border:1px solid #C6D0DA;border-radius:6px;}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        top = QFrame()
        top.setObjectName("topCard")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(8, 6, 8, 6)
        self.summary = QLabel("Preparing FT analysis…")
        self.summary.setStyleSheet("font-size:10pt;color:#0000CC;font-weight:900;")
        self.cursor_label = QLabel("Cursor: —")
        self.cursor_label.setStyleSheet("color:#0A5B7D;font-weight:900;")
        edit = QPushButton("Edit Ranges")
        edit.clicked.connect(self._edit_ranges)
        defaults = QPushButton("Defaults")
        defaults.clicked.connect(self._default_ranges)
        export = QPushButton("Export PNG")
        export.clicked.connect(self._export_png)
        top_layout.addWidget(self.summary, 1)
        top_layout.addWidget(self.cursor_label)
        top_layout.addWidget(edit)
        top_layout.addWidget(defaults)
        top_layout.addWidget(export)
        root.addWidget(top)
        self.canvas = _FTCanvas()
        self.canvas.cursor_changed.connect(self._cursor_changed)
        root.addWidget(self.canvas, 1)
        self.legend = QFrame()
        self.legend.setObjectName("rangeCard")
        self.legend_layout = QHBoxLayout(self.legend)
        self.legend_layout.setContentsMargins(8, 5, 8, 5)
        self.legend_layout.setSpacing(5)
        root.addWidget(self.legend)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        root.addWidget(close)

    def _compute_ft(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        trace = np.asarray(self.trace, dtype=np.float64)
        finite = np.isfinite(trace)
        if np.count_nonzero(finite) < 8:
            raise ValueError("Selected trace does not contain enough valid samples for FT analysis")
        if not finite.all():
            x = np.arange(trace.size)
            trace = np.interp(x, x[finite], trace[finite])
        trace = trace - float(np.mean(trace))
        max_samples = 16384
        if trace.size > max_samples:
            step = int(np.ceil(trace.size / max_samples))
            trace = trace[::step]
            dt_s = self.dt_s * step
        else:
            dt_s = self.dt_s
        n = trace.size
        win = min(1024, max(64, 2 ** int(np.floor(np.log2(max(64, n // 10))))))
        win = min(win, max(8, n))
        if win < 8:
            raise ValueError("Trace is too short for FT analysis")
        step = max(1, win // 6)
        frame_count = 1 + max(0, (n - win) // step)
        if frame_count > 720:
            step = int(np.ceil((n - win) / 719)) if n > win else win
            step = max(1, step)
            frame_count = 1 + max(0, (n - win) // step)
        window = np.hanning(win)
        scale = np.sqrt(np.sum(window * window)) or 1.0
        spectra = []
        centres = []
        for start in range(0, max(1, n - win + 1), step):
            segment = trace[start:start + win]
            if segment.size < win:
                break
            spec = np.abs(np.fft.rfft(segment * window)) / scale
            spectra.append(spec)
            centres.append(start + win * 0.5)
            if len(spectra) >= 720:
                break
        if not spectra:
            spec = np.abs(np.fft.rfft(trace * np.hanning(n)))
            spectra = [spec]
            centres = [n * 0.5]
            win = n
        amp = np.asarray(spectra, dtype=np.float64).T
        amp = np.maximum(amp, np.max(amp) * 1e-6 if np.max(amp) > 0 else 1e-12)
        db = 20.0 * np.log10(amp / max(np.max(amp), 1e-12))
        # Small separable smoothing makes the display closer to a field FT panel
        # without using SciPy or blocking the GUI.
        if db.shape[0] > 2 and db.shape[1] > 2:
            db = (db + np.roll(db, 1, axis=0) + np.roll(db, -1, axis=0) + np.roll(db, 1, axis=1) + np.roll(db, -1, axis=1)) / 5.0
        freq = np.fft.rfftfreq(win, d=dt_s)
        time_ms = self.delay_ms + np.asarray(centres, dtype=np.float64) * dt_s * 1000.0
        return time_ms, freq, db.astype(np.float32)

    def _build_image(self) -> QImage:
        db = np.asarray(self._db, dtype=np.float32)
        if db.size == 0:
            return QImage()
        height, width = db.shape
        rgb = np.full((height, width, 3), 255, dtype=np.uint8)
        # Continuous colour interpolation between the configured range colours.
        stops = []
        for lo, hi, color in sorted(self._ranges, key=lambda item: item[0]):
            stops.append((lo, color))
            stops.append((hi, color))
        stops = sorted(stops, key=lambda item: item[0])
        values = np.clip(db, stops[0][0], stops[-1][0])
        flat = values.ravel()
        out = np.zeros((flat.size, 3), dtype=np.float64)
        stop_values = np.asarray([v for v, _ in stops], dtype=np.float64)
        stop_colors = np.asarray([[c.red(), c.green(), c.blue()] for _, c in stops], dtype=np.float64)
        for channel in range(3):
            out[:, channel] = np.interp(flat, stop_values, stop_colors[:, channel])
        rgb[:, :, :] = out.reshape(height, width, 3).astype(np.uint8)
        rgb = np.flipud(rgb)
        return QImage(rgb.data, width, height, 3 * width, QImage.Format.Format_RGB888).copy()

    def _recalculate(self) -> None:
        try:
            self._time_ms, self._frequency_hz, self._db = self._compute_ft()
            image = self._build_image()
            nyquist = 0.5 / self.dt_s if self.dt_s > 0 else 0.0
            self.summary.setText(
                f"Trace {self.trace_number:,} • {self.trace.size:,} samples • dt {self.dt_s * 1000:g} ms • Nyquist {nyquist:.3g} Hz"
            )
            self.canvas.set_spectrogram(
                image,
                self._time_ms,
                self._frequency_hz,
                self._db,
                f"SEG-Y Frequency-Time Analysis — Trace {self.trace_number:,}",
            )
            self._refresh_legend()
        except Exception as exc:
            QMessageBox.warning(self, "SEG-Y FT Analysis", str(exc))

    def _refresh_legend(self) -> None:
        while self.legend_layout.count():
            item = self.legend_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.legend_layout.addWidget(QLabel("dB ranges:"))
        for lo, hi, color in self._ranges:
            label = QLabel(f"{lo:g}–{hi:g} dB")
            fg = "#000000" if color.lightness() > 145 else "#FFFFFF"
            label.setStyleSheet(
                f"background:{color.name()};color:{fg};border:1px solid #73808C;border-radius:4px;"
                "padding:4px 8px;font-weight:900;"
            )
            self.legend_layout.addWidget(label)
        self.legend_layout.addStretch(1)

    def _cursor_changed(self, time_ms: float, frequency_hz: float, db: float) -> None:
        self.cursor_label.setText(f"Cursor Time {time_ms:.1f} ms   Frequency {frequency_hz:.2f} Hz   Level {db:.1f} dB")

    def _default_ranges(self) -> None:
        self._ranges = [(lo, hi, QColor(color)) for lo, hi, color in self.DEFAULT_RANGES]
        image = self._build_image()
        self.canvas.set_spectrogram(image, self._time_ms, self._frequency_hz, self._db, f"SEG-Y Frequency-Time Analysis — Trace {self.trace_number:,}")
        self._refresh_legend()

    def _edit_ranges(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit SEG-Y FT dB Colour Ranges")
        dialog.resize(560, 340)
        layout = QVBoxLayout(dialog)
        table = QTableWidget(len(self._ranges), 3)
        table.setHorizontalHeaderLabels(["Low dB", "High dB", "Colour"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        buttons: list[_ColorButton] = []
        for row, (lo, hi, color) in enumerate(self._ranges):
            low = QDoubleSpinBox()
            low.setRange(-240.0, 60.0)
            low.setDecimals(1)
            low.setValue(float(lo))
            high = QDoubleSpinBox()
            high.setRange(-240.0, 60.0)
            high.setDecimals(1)
            high.setValue(float(hi))
            color_button = _ColorButton(color)
            buttons.append(color_button)
            table.setCellWidget(row, 0, low)
            table.setCellWidget(row, 1, high)
            table.setCellWidget(row, 2, color_button)
        layout.addWidget(table)
        row = QHBoxLayout()
        add = QPushButton("Add Range")
        remove = QPushButton("Remove Selected")
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch(1)
        layout.addLayout(row)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(box)

        def add_range() -> None:
            r = table.rowCount()
            table.insertRow(r)
            low = QDoubleSpinBox(); low.setRange(-240, 60); low.setDecimals(1); low.setValue(-60)
            high = QDoubleSpinBox(); high.setRange(-240, 60); high.setDecimals(1); high.setValue(-48)
            color_button = _ColorButton(QColor(80, 120, 220))
            buttons.append(color_button)
            table.setCellWidget(r, 0, low)
            table.setCellWidget(r, 1, high)
            table.setCellWidget(r, 2, color_button)

        def remove_range() -> None:
            r = table.currentRow()
            if r >= 0 and table.rowCount() > 1:
                table.removeRow(r)

        add.clicked.connect(add_range)
        remove.clicked.connect(remove_range)
        box.accepted.connect(dialog.accept)
        box.rejected.connect(dialog.reject)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_ranges = []
            for row_idx in range(table.rowCount()):
                low_widget = table.cellWidget(row_idx, 0)
                high_widget = table.cellWidget(row_idx, 1)
                color_widget = table.cellWidget(row_idx, 2)
                if not isinstance(low_widget, QDoubleSpinBox) or not isinstance(high_widget, QDoubleSpinBox) or not isinstance(color_widget, _ColorButton):
                    continue
                lo = float(low_widget.value())
                hi = float(high_widget.value())
                if hi <= lo:
                    hi = lo + 0.1
                new_ranges.append((lo, hi, color_widget.color))
            if new_ranges:
                self._ranges = sorted(new_ranges, key=lambda item: item[0])
                image = self._build_image()
                self.canvas.set_spectrogram(image, self._time_ms, self._frequency_hz, self._db, f"SEG-Y Frequency-Time Analysis — Trace {self.trace_number:,}")
                self._refresh_legend()

    def _export_png(self) -> None:
        image = self.canvas.grab().toImage()
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export SEG-Y FT Analysis",
            f"segy_ft_trace_{self.trace_number}.png",
            "PNG (*.png);;JPEG (*.jpg)",
        )
        if not path:
            return
        output = Path(path)
        if not output.suffix:
            output = output.with_suffix(".jpg" if "JPEG" in selected_filter else ".png")
        ok = image.save(str(output), "JPEG" if output.suffix.lower() in {".jpg", ".jpeg"} else "PNG")
        if not ok:
            QMessageBox.warning(self, "Export", "Could not save FT analysis image")


class _TraceWaveformCanvas(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(760, 360)
        self.trace = np.array([], dtype=np.float64)
        self.time_ms = np.array([], dtype=np.float64)
        self._cursor: Optional[QPointF] = None
        self.setMouseTracking(True)

    def set_trace(self, trace: np.ndarray, time_ms: np.ndarray) -> None:
        self.trace = np.asarray(trace, dtype=np.float64)
        self.time_ms = np.asarray(time_ms, dtype=np.float64)
        self.update()

    def plot_rect(self) -> QRectF:
        return QRectF(66, 26, max(1, self.width() - 84), max(1, self.height() - 66))

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(244, 247, 250))
        rect = self.plot_rect()
        painter.fillRect(rect, QColor(255, 255, 255))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(220, 228, 235), 1))
        for i in range(1, 8):
            x = rect.left() + rect.width() * i / 8
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        for i in range(1, 6):
            y = rect.top() + rect.height() * i / 6
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        if self.trace.size and self.time_ms.size:
            finite = np.isfinite(self.trace)
            if np.any(finite):
                clip = float(np.percentile(np.abs(self.trace[finite]), 99.0))
                if not np.isfinite(clip) or clip <= 1e-12:
                    clip = 1.0
                xcoords = rect.left() + (self.time_ms - self.time_ms[0]) / max(1e-9, self.time_ms[-1] - self.time_ms[0]) * rect.width()
                ybase = rect.center().y()
                yscale = rect.height() * 0.45
                painter.setPen(QPen(QColor(180, 190, 198), 1, Qt.PenStyle.DashLine))
                painter.drawLine(QPointF(rect.left(), ybase), QPointF(rect.right(), ybase))
                idx = np.flatnonzero(finite)
                step = max(1, int(np.ceil(idx.size / max(1.0, rect.width() * 2.0))))
                idx = idx[::step]
                path = QPainterPath(QPointF(float(xcoords[idx[0]]), ybase - float(np.clip(self.trace[idx[0]] / clip, -1, 1)) * yscale))
                for j in idx[1:]:
                    path.lineTo(float(xcoords[j]), ybase - float(np.clip(self.trace[j] / clip, -1, 1)) * yscale)
                painter.setPen(QPen(QColor(12, 26, 39), 1.1))
                painter.drawPath(path)
                painter.setFont(QFont("Arial", 8))
                for i in range(7):
                    frac = i / 6
                    x = rect.left() + rect.width() * frac
                    t = self.time_ms[0] + (self.time_ms[-1] - self.time_ms[0]) * frac
                    painter.drawText(QRectF(x - 42, rect.bottom() + 4, 84, 18), Qt.AlignmentFlag.AlignCenter, f"{t:.0f}")
        painter.setPen(QPen(QColor(28, 45, 61), 1))
        painter.drawRect(rect)
        painter.drawText(QRectF(0, rect.bottom() + 24, self.width(), 18), Qt.AlignmentFlag.AlignCenter, "Time (ms)")
        painter.end()


class SegyTraceWaveformDialog(QDialog):
    def __init__(
        self,
        trace: np.ndarray,
        sample_interval_us: float,
        delay_ms: float,
        trace_number: int,
        metrics: Sequence[tuple[str, str]],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"SEG-Y Trace Waveform — Trace {trace_number:,}")
        self.resize(920, 560)
        self.trace = np.asarray(trace, dtype=np.float64)
        self.sample_interval_us = float(sample_interval_us)
        self.delay_ms = float(delay_ms)
        self.trace_number = int(trace_number)
        self.metrics = list(metrics)
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(
            "QDialog{background:#EEF2F6;font-size:8.5pt;}"
            "QFrame#card{background:#FFFFFF;border:1px solid #C6D0DA;border-radius:6px;}"
            "QLabel{color:#12324C;font-weight:800;}"
            "QPushButton{min-height:24px;padding:2px 8px;border:1px solid #8EA2B2;border-radius:4px;background:#FFFFFF;font-weight:800;}"
            "QTableWidget{background:#FFFFFF;alternate-background-color:#F7FAFC;border:1px solid #D7E1E9;}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        top = QFrame(); top.setObjectName("card")
        row = QHBoxLayout(top); row.setContentsMargins(8, 6, 8, 6)
        row.addWidget(QLabel(f"Trace {self.trace_number:,} waveform"), 1)
        ft = QPushButton("FT Analysis")
        ft.clicked.connect(self._show_ft)
        export = QPushButton("Export PNG")
        export.clicked.connect(self._export_png)
        row.addWidget(ft); row.addWidget(export)
        root.addWidget(top)
        body = QSplitter(Qt.Orientation.Horizontal)
        self.canvas = _TraceWaveformCanvas()
        dt_ms = self.sample_interval_us / 1000.0
        times = self.delay_ms + np.arange(self.trace.size, dtype=np.float64) * dt_ms
        self.canvas.set_trace(self.trace, times)
        body.addWidget(self.canvas)
        table = QTableWidget(0, 2)
        table.setHorizontalHeaderLabels(["Metric", "Value"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setRowCount(len(self.metrics))
        for i, (k, v) in enumerate(self.metrics):
            table.setItem(i, 0, QTableWidgetItem(str(k)))
            table.setItem(i, 1, QTableWidgetItem(str(v)))
        body.addWidget(table)
        body.setSizes([700, 220])
        root.addWidget(body, 1)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        root.addWidget(close)

    def _show_ft(self) -> None:
        SegyFTAnalysisDialog(self.trace, self.sample_interval_us, self.delay_ms, self.trace_number, self).exec()

    def _export_png(self) -> None:
        image = self.grab().toImage()
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export SEG-Y Trace Waveform",
            f"segy_trace_{self.trace_number}.png",
            "PNG (*.png);;JPEG (*.jpg)",
        )
        if not path:
            return
        output = Path(path)
        if not output.suffix:
            output = output.with_suffix(".jpg" if "JPEG" in selected_filter else ".png")
        ok = image.save(str(output), "JPEG" if output.suffix.lower() in {".jpg", ".jpeg"} else "PNG")
        if not ok:
            QMessageBox.warning(self, "Export", "Could not save trace waveform image")


class SegyCanvas(QWidget):
    """Interactive SEG-Y seismic canvas for manual QC of traces."""

    window_changed = Signal(int, int, int, int)
    trace_selected = Signal(int)
    cursor_changed = Signal(str)
    pick_added = Signal(object)
    measure_changed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(520, 360)
        self.setMouseTracking(True)
        self._image = QImage()
        self._t0 = self._s0 = 0
        self._t1 = self._s1 = 1
        self._total_t = self._total_s = 1
        self._grid_start_ms = 0.0
        self._sample_interval_ms = 1.0
        self._drag: Optional[QPointF] = None
        self._mode = "inspect"
        self._selected_trace: Optional[int] = None
        self._picks: list[SegyPick] = []
        self._measure_start: Optional[SegyPick] = None
        self._measure_end: Optional[SegyPick] = None
        self._cursor: Optional[SegyPick] = None
        self._visible_normalized = np.empty((0, 0), dtype=np.float32)
        self._visible_trace_indices = np.array([], dtype=np.int64)

    def set_data_extent(
        self,
        total_traces: int,
        total_samples: int,
        sample_interval_ms: float,
        grid_start_ms: float = 0.0,
    ) -> None:
        self._total_t = max(1, int(total_traces))
        self._total_s = max(1, int(total_samples))
        self._sample_interval_ms = max(1e-9, float(sample_interval_ms))
        self._grid_start_ms = float(grid_start_ms)

    def set_image(
        self,
        image: QImage,
        t0: int,
        t1: int,
        s0: int,
        s1: int,
        normalized_window: Optional[np.ndarray] = None,
        visible_trace_indices: Optional[np.ndarray] = None,
    ) -> None:
        self._image = image
        self._t0, self._t1, self._s0, self._s1 = int(t0), int(t1), int(s0), int(s1)
        self._visible_normalized = np.asarray(normalized_window, dtype=np.float32) if normalized_window is not None else np.empty((0, 0), dtype=np.float32)
        self._visible_trace_indices = np.asarray(visible_trace_indices, dtype=np.int64) if visible_trace_indices is not None else np.array([], dtype=np.int64)
        self.update()

    def set_interaction_mode(self, mode: str) -> None:
        self._mode = mode if mode in {"inspect", "pick", "measure"} else "inspect"
        if self._mode != "measure":
            self._measure_start = None
            self._measure_end = None
        self.update()

    def clear_marks(self) -> None:
        self._picks.clear()
        self._measure_start = None
        self._measure_end = None
        self.update()

    def set_selected_trace(self, trace_index: int) -> None:
        self._selected_trace = int(np.clip(trace_index, 0, self._total_t - 1))
        self.update()

    def plot_rect(self) -> QRectF:
        return QRectF(72, 30, max(1, self.width() - 86), max(1, self.height() - 62))

    def _sample_to_time(self, sample_index: int) -> float:
        return self._grid_start_ms + int(sample_index) * self._sample_interval_ms

    def _pick_from_position(self, pos: QPointF, kind: str = "Pick") -> Optional[SegyPick]:
        rect = self.plot_rect()
        if not rect.contains(pos):
            return None
        fx = (pos.x() - rect.left()) / max(1.0, rect.width())
        fy = (pos.y() - rect.top()) / max(1.0, rect.height())
        trace = int(np.clip(round(self._t0 + fx * max(0, self._t1 - self._t0 - 1)), 0, self._total_t - 1))
        sample = int(np.clip(round(self._s0 + fy * max(0, self._s1 - self._s0 - 1)), 0, self._total_s - 1))
        amp = float("nan")
        if self._visible_normalized.size and self._visible_trace_indices.size:
            nearest = int(np.argmin(np.abs(self._visible_trace_indices - trace)))
            sample_local = int(np.clip(sample - self._s0, 0, self._visible_normalized.shape[1] - 1))
            if 0 <= nearest < self._visible_normalized.shape[0]:
                value = self._visible_normalized[nearest, sample_local]
                amp = float(value) if np.isfinite(value) else float("nan")
        return SegyPick(trace, sample, self._sample_to_time(sample), amp, kind)

    def _pick_to_point(self, pick: SegyPick) -> QPointF:
        rect = self.plot_rect()
        fx = (pick.trace_index - self._t0 + 0.5) / max(1.0, self._t1 - self._t0)
        fy = (pick.sample_index - self._s0) / max(1.0, self._s1 - self._s0 - 1)
        return QPointF(rect.left() + fx * rect.width(), rect.top() + fy * rect.height())

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(24, 30, 36))
        rect = self.plot_rect()
        painter.fillRect(rect, Qt.GlobalColor.white)
        if not self._image.isNull():
            painter.drawImage(rect, self._image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(222, 229, 236), 1))
        for i in range(1, 8):
            x = rect.left() + rect.width() * i / 8
            y = rect.top() + rect.height() * i / 8
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        if self._selected_trace is not None and self._t0 <= self._selected_trace < self._t1:
            x = self._pick_to_point(SegyPick(self._selected_trace, self._s0, 0.0, 0.0)).x()
            painter.setPen(QPen(QColor(255, 50, 40), 1.2, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        painter.setPen(QPen(QColor(91, 106, 119), 1))
        painter.drawRect(rect)
        painter.setFont(QFont("Arial", 8))
        painter.setPen(QColor(224, 229, 234))
        for i in range(9):
            fraction = i / 8
            x = rect.left() + fraction * rect.width()
            trace = self._t0 + fraction * max(0, self._t1 - self._t0 - 1)
            painter.drawText(QRectF(x - 34, 5, 68, 20), Qt.AlignmentFlag.AlignCenter, str(int(round(trace)) + 1))
        for i in range(9):
            fraction = i / 8
            y = rect.top() + fraction * rect.height()
            sample = self._s0 + fraction * max(0, self._s1 - self._s0 - 1)
            time_ms = self._grid_start_ms + sample * self._sample_interval_ms
            painter.drawText(
                QRectF(4, y - 9, 62, 18),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{time_ms:.0f}",
            )
        painter.setPen(QColor(160, 175, 187))
        painter.drawText(QRectF(4, 5, 64, 20), Qt.AlignmentFlag.AlignLeft, "ms")
        painter.drawText(QRectF(rect.left(), 5, rect.width(), 20), Qt.AlignmentFlag.AlignCenter, "Trace number")
        self._draw_pick_overlays(painter, rect)
        mode_text = {"inspect": "Inspect", "pick": "Pick", "measure": "Measure"}.get(self._mode, "Inspect")
        painter.setPen(QColor(208, 220, 230))
        painter.drawText(QRectF(rect.right() - 210, rect.bottom() + 8, 206, 18), Qt.AlignmentFlag.AlignRight, f"Mode: {mode_text}")
        painter.end()

    def _draw_pick_overlays(self, painter: QPainter, rect: QRectF) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for pick in self._picks:
            if self._t0 <= pick.trace_index < self._t1 and self._s0 <= pick.sample_index < self._s1:
                point = self._pick_to_point(pick)
                painter.setPen(QPen(QColor(255, 0, 0), 1.4))
                painter.drawLine(QPointF(point.x() - 7, point.y()), QPointF(point.x() + 7, point.y()))
                painter.drawLine(QPointF(point.x(), point.y() - 7), QPointF(point.x(), point.y() + 7))
        if self._measure_start is not None:
            start = self._pick_to_point(self._measure_start)
            end_pick = self._measure_end or self._cursor
            painter.setPen(QPen(QColor(0, 90, 220), 1.5))
            painter.drawEllipse(start, 4.0, 4.0)
            if end_pick is not None:
                end = self._pick_to_point(end_pick)
                painter.drawLine(start, end)
                painter.drawEllipse(end, 4.0, 4.0)
                dt = end_pick.time_ms - self._measure_start.time_ms
                dtr = end_pick.trace_index - self._measure_start.trace_index
                label = f"Δt {dt:.2f} ms  Δtr {dtr:+d}"
                label_rect = QRectF(min(start.x(), end.x()) + 8, min(start.y(), end.y()) - 24, 160, 20)
                painter.fillRect(label_rect, QColor(255, 255, 255, 210))
                painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, label)

    def wheelEvent(self, event: QWheelEvent) -> None:
        rect = self.plot_rect()
        pos = event.position()
        if not rect.contains(pos):
            return
        trace_span = max(1, self._t1 - self._t0)
        sample_span = max(2, self._s1 - self._s0)
        factor = 0.72 if event.angleDelta().y() > 0 else 1 / 0.72
        fx = (pos.x() - rect.left()) / max(1.0, rect.width())
        fy = (pos.y() - rect.top()) / max(1.0, rect.height())
        only_x = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        only_y = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        new_t = trace_span if only_y else int(np.clip(round(trace_span * factor), 1, self._total_t))
        new_s = sample_span if only_x else int(np.clip(round(sample_span * factor), 8, self._total_s))
        anchor_t = self._t0 + fx * trace_span
        anchor_s = self._s0 + fy * sample_span
        t0 = int(round(anchor_t - fx * new_t))
        s0 = int(round(anchor_s - fy * new_s))
        t0 = max(0, min(t0, self._total_t - new_t))
        s0 = max(0, min(s0, self._total_s - new_s))
        self.window_changed.emit(t0, t0 + new_t, s0, s0 + new_s)
        event.accept()

    def mousePressEvent(self, event) -> None:
        rect = self.plot_rect()
        if event.button() == Qt.MouseButton.LeftButton and rect.contains(event.position()):
            pick = self._pick_from_position(event.position(), "Pick")
            if pick is not None:
                self._selected_trace = pick.trace_index
                self.trace_selected.emit(pick.trace_index)
                if self._mode == "pick":
                    self._picks.append(pick)
                    self.pick_added.emit(pick)
                    self.update()
                elif self._mode == "measure":
                    if self._measure_start is None or self._measure_end is not None:
                        self._measure_start = SegyPick(pick.trace_index, pick.sample_index, pick.time_ms, pick.amplitude, "Start")
                        self._measure_end = None
                    else:
                        self._measure_end = SegyPick(pick.trace_index, pick.sample_index, pick.time_ms, pick.amplitude, "End")
                    self._emit_measurement()
                    self.update()
        if event.button() == Qt.MouseButton.MiddleButton or event.button() == Qt.MouseButton.RightButton:
            self._drag = event.position()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        rect = self.plot_rect()
        pos = event.position()
        pick = self._pick_from_position(pos, "Cursor")
        self._cursor = pick
        if pick is not None:
            self.cursor_changed.emit(
                f"Trace {pick.trace_index + 1:,}   Sample {pick.sample_index + 1:,}   Time {pick.time_ms:.3f} ms   Display amp {pick.amplitude:.4g}"
            )
            if self._mode == "measure" and self._measure_start is not None and self._measure_end is None:
                self._emit_measurement(preview=pick)
        else:
            self.cursor_changed.emit("Move cursor over SEG-Y display")
        if self._drag is not None and event.buttons() & (Qt.MouseButton.MiddleButton | Qt.MouseButton.RightButton):
            delta = event.position() - self._drag
            self._drag = event.position()
            trace_span = self._t1 - self._t0
            sample_span = self._s1 - self._s0
            dt = int(round(-delta.x() / max(1.0, rect.width()) * trace_span))
            ds = int(round(-delta.y() / max(1.0, rect.height()) * sample_span))
            t0 = max(0, min(self._t0 + dt, self._total_t - trace_span))
            s0 = max(0, min(self._s0 + ds, self._total_s - sample_span))
            self.window_changed.emit(t0, t0 + trace_span, s0, s0 + sample_span)
        self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() in {Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton}:
            self._drag = None
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._mode = "inspect"
            self._measure_start = None
            self._measure_end = None
            self.update()
            event.accept()
            return
        super().keyPressEvent(event)

    def _emit_measurement(self, preview: Optional[SegyPick] = None) -> None:
        if self._measure_start is None:
            return
        end = self._measure_end or preview
        if end is None:
            self.measure_changed.emit("Click second point to finish measurement")
            return
        dt = end.time_ms - self._measure_start.time_ms
        dtr = end.trace_index - self._measure_start.trace_index
        ds = end.sample_index - self._measure_start.sample_index
        self.measure_changed.emit(
            f"Start T{self._measure_start.trace_index + 1} {self._measure_start.time_ms:.3f} ms  →  "
            f"End T{end.trace_index + 1} {end.time_ms:.3f} ms  |  Δtime {dt:.3f} ms, Δsample {ds:+d}, Δtrace {dtr:+d}"
        )


class SegyViewerWidget(QWidget):
    """Professional SEG-Y viewer restructured for manual trace QC."""

    def __init__(self, file_path: str | Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setProperty("module_id", "segy_viewer")
        self.file_path = Path(file_path)
        self.reader: Optional[SegyReader] = None
        self.index = None
        self.time_grid: Optional[DisplayGrid] = None
        self._t0 = self._s0 = 0
        self._t1 = self._s1 = 1
        self._selected_trace = 0
        self._effective_intervals_us = np.array([], dtype=np.float64)
        self._last_metrics: list[tuple[str, str]] = []
        self._build_ui()
        self.open_file(self.file_path)

    def _build_ui(self) -> None:
        self.setStyleSheet(
            "QWidget{font-size:8.0pt;color:#17324A;}"
            "QFrame#segyTopBar{background:#F5F8FB;border-bottom:1px solid #D7E2EA;}"
            "QPushButton{min-height:23px;padding:2px 9px;border:1px solid #AFC2D1;border-radius:5px;background:#FFFFFF;font-weight:800;color:#17324A;}"
            "QPushButton:hover{background:#EEF6FB;}"
            "QPushButton#primaryButton{background:#0A86C7;border-color:#0873AB;color:#FFFFFF;}"
            "QPushButton#dangerButton{background:#FFF1F0;border-color:#E5A3A0;color:#8A1C17;}"
            "QPushButton#activeTool{background:#E5F4FF;border:2px solid #0A86C7;color:#063D60;}"
            "QFrame#segySide{background:#FFFFFF;border-left:1px solid #D7E2EA;}"
            "QTabWidget#sideTabs::pane{border:1px solid #D5E1EA;border-radius:6px;background:#FFFFFF;top:-1px;}"
            "QTabWidget#sideTabs QTabBar::tab{background:#EAF0F4;color:#38566B;border:1px solid #D4DFE7;border-bottom:0;min-height:22px;padding:3px 7px;margin-right:1px;font-size:7.7pt;font-weight:800;}"
            "QTabWidget#sideTabs QTabBar::tab:selected{background:#FFFFFF;color:#075C84;font-weight:900;}"
            "QGroupBox{font-weight:900;color:#17364B;border:1px solid #D9E2E9;border-radius:6px;margin-top:8px;padding-top:8px;background:#FFFFFF;}"
            "QGroupBox::title{subcontrol-origin:margin;left:8px;padding:0 4px;background:#FFFFFF;}"
            "QComboBox,QDoubleSpinBox,QSpinBox{min-height:21px;font-size:7.8pt;border:1px solid #C9D4DF;border-radius:4px;background:#FFFFFF;padding:1px 4px;}"
            "QLabel{font-size:7.9pt;}"
            "QTableWidget{font-size:7.6pt;background:#FFFFFF;alternate-background-color:#F7FAFC;border:1px solid #DCE5EC;gridline-color:#E7EDF2;}"
            "QHeaderView::section{background:#E7F0F6;color:#29495E;border:0;border-right:1px solid #D3DFE8;border-bottom:1px solid #D3DFE8;padding:3px 4px;font-weight:900;font-size:7.5pt;}"
            "QTextEdit{font-size:7.6pt;font-family:Consolas, Courier New, monospace;}"
            "QScrollArea{border:0;background:transparent;}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar = QFrame()
        bar.setObjectName("segyTopBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(8, 4, 8, 4)
        self.file_label = QLabel("SEG-Y Viewer")
        self.file_label.setStyleSheet("font-size:14px;font-weight:800;color:#18384f;")
        self.info = QLabel("")
        self.info.setStyleSheet("color:#607080")
        self.info.setMinimumWidth(0)
        self.info.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        open_button = QPushButton("Open SEG-Y")
        open_button.setObjectName("primaryButton")
        open_button.clicked.connect(self._choose_file)
        fit_button = QPushButton("Fit")
        fit_button.clicked.connect(self.fit)
        trace_button = QPushButton("Trace")
        trace_button.clicked.connect(self.show_trace_waveform)
        ft_button = QPushButton("FT")
        ft_button.clicked.connect(self.show_ft_analysis)
        export_button = QPushButton("Export")
        export_button.clicked.connect(self.export_image)
        row.addWidget(self.file_label)
        row.addWidget(self.info)
        row.addStretch(1)
        row.addWidget(fit_button)
        row.addWidget(trace_button)
        row.addWidget(ft_button)
        row.addWidget(export_button)
        row.addWidget(open_button)
        root.addWidget(bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.canvas = SegyCanvas()
        self.canvas.window_changed.connect(self.set_window)
        self.canvas.trace_selected.connect(self.select_trace)
        self.canvas.cursor_changed.connect(self._update_cursor_status)
        self.canvas.pick_added.connect(self._record_pick)
        self.canvas.measure_changed.connect(self._update_measurement_status)
        splitter.addWidget(self.canvas)

        side = QFrame()
        side.setObjectName("segySide")
        side.setMinimumWidth(285)
        side.setMaximumWidth(390)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(7, 7, 7, 7)
        side_layout.setSpacing(6)
        self.side_tabs = QTabWidget()
        self.side_tabs.setObjectName("sideTabs")
        self.side_tabs.setDocumentMode(True)
        self.side_tabs.setUsesScrollButtons(True)
        for title, page in (
            ("Display", self._display_page()),
            ("Window", self._window_page()),
            ("Manual QC", self._manual_qc_page()),
            ("Attrib.", self._attribute_page()),
            ("File", self._file_info_page()),
            ("Headers", self._headers_page()),
            ("Trace", self._analysis_page()),
        ):
            self.side_tabs.addTab(page, title)
        self.pages = self.side_tabs
        side_layout.addWidget(self.side_tabs, 1)
        splitter.addWidget(side)
        splitter.setStretchFactor(0, 10)
        splitter.setStretchFactor(1, 0)
        splitter.setCollapsible(1, True)
        splitter.setSizes([1260, 330])
        root.addWidget(splitter, 1)

        self.cursor_status = QLabel("Wheel: zoom • Ctrl+wheel: traces only • Shift+wheel: time only • Right/middle-drag: pan • Click trace: inspect")
        self.cursor_status.setStyleSheet("padding:3px 8px;background:#edf3f7;color:#536879;font-size:9px;border-top:1px solid #d9e1e8;")
        root.addWidget(self.cursor_status)

    def _display_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(7, 6, 7, 6)
        layout.setSpacing(6)
        display_group = QGroupBox("Display Mode")
        form = QFormLayout(display_group)
        self._configure_form(form)
        self.mode = QComboBox()
        for name, value in (("Wiggle", "wiggle"), ("Variable Area", "va"), ("Variable Density", "vd"), ("Color Density", "color")):
            self.mode.addItem(name, value)
        self.mode.currentIndexChanged.connect(self.render)
        self.attribute = QComboBox()
        for key, label in ATTRIBUTE_NAMES.items():
            self.attribute.addItem(label, key)
        self.attribute.currentIndexChanged.connect(self.render)
        self.gain = QComboBox()
        for name, value in (("AGC", "agc"), ("Trace Balance", "balance"), ("No Gain", "none")):
            self.gain.addItem(name, value)
        self.gain.currentIndexChanged.connect(self.render)
        self.agc_window = QDoubleSpinBox()
        self.agc_window.setRange(5.0, 5000.0)
        self.agc_window.setValue(100.0)
        self.agc_window.setSuffix(" ms")
        self.agc_window.valueChanged.connect(self.render)
        self.clip = QDoubleSpinBox()
        self.clip.setRange(80, 100)
        self.clip.setDecimals(1)
        self.clip.setValue(99)
        self.clip.setSuffix(" %")
        self.clip.valueChanged.connect(self.render)
        self.trace_density = QSpinBox()
        self.trace_density.setRange(10, 100)
        self.trace_density.setSingleStep(5)
        self.trace_density.setValue(100)
        self.trace_density.setSuffix(" %")
        self.trace_density.setToolTip("Controls how many traces are drawn in wiggle/variable-area mode. Lower values keep dense 2D/3D SEG-Y displays readable and fast.")
        self.trace_density.valueChanged.connect(self.render)
        self.display_status = QLabel("Trace density 100% • all visible traces are drawn")
        self.display_status.setWordWrap(True)
        self.display_status.setStyleSheet("color:#3A6176;background:#F1F8FC;border:1px solid #D5E9F3;border-radius:5px;padding:5px;font-weight:700;")
        self.polarity = QCheckBox("Reverse polarity")
        self.polarity.toggled.connect(self.render)
        for control in (self.mode, self.attribute, self.gain, self.agc_window, self.clip, self.trace_density):
            control.setMinimumWidth(100)
            control.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        form.addRow("Display", self.mode)
        form.addRow("Attribute", self.attribute)
        form.addRow("Gain", self.gain)
        form.addRow("AGC", self.agc_window)
        form.addRow("Clip", self.clip)
        form.addRow("Trace density", self.trace_density)
        form.addRow(self.polarity)
        layout.addWidget(display_group)
        layout.addWidget(self.display_status)
        hint = QLabel("Use wheel on the seismic panel for true trace/time zoom. Zoom now reaches one trace for close manual QC.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#657B8D;background:#F6FAFC;border:1px solid #E1E9EF;border-radius:5px;padding:6px;")
        layout.addWidget(hint)
        layout.addStretch(1)
        return self._scrollable_page(w)

    def _window_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(7, 6, 7, 6)
        layout.setSpacing(6)
        window_group = QGroupBox("Visible Data Window")
        window_form = QFormLayout(window_group)
        self._configure_form(window_form)
        self.tstart = QSpinBox(); self.tend = QSpinBox(); self.sstart = QSpinBox(); self.send = QSpinBox()
        for spin in (self.tstart, self.tend, self.sstart, self.send):
            spin.setMinimum(1)
            spin.setMinimumWidth(90)
            spin.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            spin.editingFinished.connect(self._spins_window)
        window_form.addRow("First trace", self.tstart)
        window_form.addRow("Last trace", self.tend)
        window_form.addRow("First sample", self.sstart)
        window_form.addRow("Last sample", self.send)
        fit_button = QPushButton("Fit Full Data")
        fit_button.setObjectName("primaryButton")
        fit_button.clicked.connect(self.fit)
        window_form.addRow(fit_button)
        layout.addWidget(window_group)
        layout.addStretch(1)
        return self._scrollable_page(w)

    def _manual_qc_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(7, 6, 7, 6)
        layout.setSpacing(6)
        tools = QGroupBox("Manual SEG-Y QC Tools")
        grid = QGridLayout(tools)
        grid.setContentsMargins(8, 12, 8, 8)
        grid.setSpacing(5)
        self.inspect_btn = QPushButton("Inspect")
        self.pick_btn = QPushButton("Pick")
        self.measure_btn = QPushButton("Measure")
        self.clear_btn = QPushButton("Clear Marks")
        self.clear_btn.setObjectName("dangerButton")
        self.inspect_btn.clicked.connect(lambda: self._set_tool_mode("inspect"))
        self.pick_btn.clicked.connect(lambda: self._set_tool_mode("pick"))
        self.measure_btn.clicked.connect(lambda: self._set_tool_mode("measure"))
        self.clear_btn.clicked.connect(self.clear_manual_marks)
        grid.addWidget(self.inspect_btn, 0, 0)
        grid.addWidget(self.pick_btn, 0, 1)
        grid.addWidget(self.measure_btn, 1, 0)
        grid.addWidget(self.clear_btn, 1, 1)
        trace = QPushButton("Open Trace Waveform")
        ft = QPushButton("FT Analysis")
        copy = QPushButton("Copy Measurement")
        trace.clicked.connect(self.show_trace_waveform)
        ft.clicked.connect(self.show_ft_analysis)
        copy.clicked.connect(self.copy_measurement)
        grid.addWidget(trace, 2, 0, 1, 2)
        grid.addWidget(ft, 3, 0, 1, 2)
        grid.addWidget(copy, 4, 0, 1, 2)
        layout.addWidget(tools)
        self.measurement_label = QLabel("Measurement: click Measure, then click start and end points on the trace panel.")
        self.measurement_label.setWordWrap(True)
        self.measurement_label.setStyleSheet("color:#0A5B7D;background:#F1F8FC;border:1px solid #D5E9F3;border-radius:5px;padding:6px;font-weight:800;")
        layout.addWidget(self.measurement_label)
        self.pick_table = QTableWidget(0, 5)
        self.pick_table.setHorizontalHeaderLabels(["Type", "Trace", "Sample", "Time ms", "Amp"])
        self.pick_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.pick_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.pick_table.setAlternatingRowColors(True)
        layout.addWidget(self.pick_table, 1)
        self._set_tool_mode("inspect")
        return self._scrollable_page(w)

    def _attribute_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(7, 6, 7, 6)
        layout.setSpacing(6)
        attribute_group = QGroupBox("Attribute Analysis")
        attribute_form = QFormLayout(attribute_group)
        self._configure_form(attribute_form)
        self.rms_window_ms = QDoubleSpinBox(); self.rms_window_ms.setRange(2.0, 2000.0); self.rms_window_ms.setValue(40.0); self.rms_window_ms.setSuffix(" ms")
        self.coherence_window_ms = QDoubleSpinBox(); self.coherence_window_ms.setRange(2.0, 2000.0); self.coherence_window_ms.setValue(32.0); self.coherence_window_ms.setSuffix(" ms")
        self.coherence_radius = QSpinBox(); self.coherence_radius.setRange(0, 20); self.coherence_radius.setValue(2)
        self.sweetness_floor_hz = QDoubleSpinBox(); self.sweetness_floor_hz.setRange(0.1, 100.0); self.sweetness_floor_hz.setDecimals(1); self.sweetness_floor_hz.setValue(1.0); self.sweetness_floor_hz.setSuffix(" Hz")
        for control in (self.rms_window_ms, self.coherence_window_ms, self.coherence_radius, self.sweetness_floor_hz):
            control.setMinimumWidth(90)
            control.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            control.valueChanged.connect(self.render)
        attribute_form.addRow("RMS", self.rms_window_ms)
        attribute_form.addRow("Coherence", self.coherence_window_ms)
        attribute_form.addRow("Aperture", self.coherence_radius)
        attribute_form.addRow("Sweetness floor", self.sweetness_floor_hz)
        layout.addWidget(attribute_group)
        hint = QLabel("Choose the active attribute on Display. Attribute rasters are rendered as density/colour instead of wiggle.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#657B8D;background:#F6FAFC;border:1px solid #E1E9EF;border-radius:5px;padding:6px;")
        layout.addWidget(hint)
        layout.addStretch(1)
        return self._scrollable_page(w)

    @staticmethod
    def _configure_form(form: QFormLayout) -> None:
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(6)
        form.setVerticalSpacing(4)

    @staticmethod
    def _scrollable_page(content: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        return scroll

    def _file_info_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(10, 10, 10, 10)
        self.file_table = QTableWidget(0, 2)
        self.file_table.setHorizontalHeaderLabels(["Property", "Value"])
        self.file_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.file_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.file_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.file_table.setAlternatingRowColors(True)
        layout.addWidget(self.file_table)
        return w

    def _headers_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        self.header_tabs = QTabWidget()
        self.text_header = QTextEdit(); self.text_header.setReadOnly(True); self.text_header.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.binary = self._make_property_table()
        self.trace_header = self._make_property_table()
        self.header_tabs.addTab(self.text_header, "Textual")
        self.header_tabs.addTab(self.binary, "Binary")
        self.header_tabs.addTab(self.trace_header, "Selected Trace")
        layout.addWidget(self.header_tabs)
        return w

    def _analysis_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(10, 10, 10, 10)
        self.analysis_label = QLabel("Select a trace in the seismic display")
        self.analysis_label.setWordWrap(True)
        self.analysis_label.setStyleSheet("font-weight:700;color:#29485f;padding:6px;background:#edf4f8;border-radius:4px;")
        buttons = QHBoxLayout()
        waveform = QPushButton("Waveform")
        ft = QPushButton("FT")
        waveform.clicked.connect(self.show_trace_waveform)
        ft.clicked.connect(self.show_ft_analysis)
        buttons.addWidget(waveform); buttons.addWidget(ft)
        self.analysis_table = self._make_property_table()
        layout.addWidget(self.analysis_label)
        layout.addLayout(buttons)
        layout.addWidget(self.analysis_table, 1)
        return w

    @staticmethod
    def _make_property_table() -> QTableWidget:
        table = QTableWidget(0, 2)
        table.setHorizontalHeaderLabels(["Field", "Value"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        return table

    def _choose_file(self) -> None:
        start = self.file_path.parent if self.file_path else Path.home()
        path, _ = QFileDialog.getOpenFileName(self, "Open SEG-Y", str(start), "SEG-Y (*.sgy *.segy);;All files (*.*)")
        if path:
            self.open_file(path)

    def open_file(self, path: str | Path) -> None:
        main_window = self.window()
        source = Path(path)
        task_id = f"segy-viewer:file:{source.name}"
        if hasattr(main_window, "begin_busy_task"):
            main_window.begin_busy_task(task_id, "Opening SEG-Y File", f"Reading {source.name}", 10)
        try:
            self.file_path = source
            self.reader = SegyReader(self.file_path)
            if hasattr(main_window, "update_busy_task"):
                main_window.update_busy_task(task_id, 35, "Scanning SEG-Y trace headers")
            self.index = self.reader.scan_trace_headers()
            if self.index.trace_count <= 0:
                raise ValueError("SEG-Y contains no complete traces")
            intervals = self.index.sample_intervals_us.copy()
            binary_dt = float(self.reader.binary_header.sample_interval_us)
            intervals[intervals <= 0] = binary_dt
            if np.any(intervals <= 0):
                raise ValueError("SEG-Y does not contain a valid sample interval")
            self._effective_intervals_us = intervals
            if hasattr(main_window, "update_busy_task"):
                main_window.update_busy_task(task_id, 62, "Building display time grid and trace controls")
            self.time_grid = build_time_grid(self.index.sample_counts, intervals, self.index.delay_time_ms)
            n = self.index.trace_count
            self.file_label.setText(self.file_path.name)
            bh = self.reader.binary_header
            self.info.setText(
                f"Rev {bh.revision}  •  {n:,} traces  •  {self.time_grid.interval_ms:g} ms display dt  •  "
                f"{self.reader.sample_format_name}  •  {self.reader.text_header.encoding}"
            )
            self.canvas.set_data_extent(n, self.time_grid.sample_count, self.time_grid.interval_ms, self.time_grid.start_ms)
            self.tstart.setMaximum(n); self.tend.setMaximum(n)
            self.sstart.setMaximum(self.time_grid.sample_count); self.send.setMaximum(self.time_grid.sample_count)
            self._populate_headers()
            self._populate_file_info()
            if hasattr(main_window, "update_busy_task"):
                main_window.update_busy_task(task_id, 88, "Rendering initial SEG-Y view")
            self.fit()
            if hasattr(main_window, "update_busy_task"):
                main_window.update_busy_task(task_id, 100, "SEG-Y file is ready")
        except Exception as exc:
            QMessageBox.critical(self, "SEG-Y Open Error", str(exc))
        finally:
            if hasattr(main_window, "end_busy_task"):
                main_window.end_busy_task(task_id)

    def _populate_file_info(self) -> None:
        if self.reader is None or self.index is None or self.time_grid is None:
            return
        bh = self.reader.binary_header
        intervals = self._effective_intervals_us
        counts = self.index.sample_counts
        delays = self.index.delay_time_ms
        unique_dt = np.unique(intervals[intervals > 0])
        unique_ns = np.unique(counts[counts > 0])
        fields = [
            ("File", str(self.file_path)),
            ("File size", f"{self.reader.file_size:,} bytes"),
            ("SEG-Y revision", bh.revision),
            ("Byte order", "Big-endian" if bh.endian == ">" else "Little-endian"),
            ("Byte-order detection", bh.byte_order_detection),
            ("Endian sentinel", f"0x{int(bh.byte_order_sentinel):08X}"),
            ("Text header encoding", self.reader.text_header.encoding),
            ("Sample format", f"{bh.sample_format_code} — {self.reader.sample_format_name}"),
            ("Indexed traces", f"{self.index.trace_count:,}"),
            ("Declared Rev 2 trace count", f"{int(bh.declared_trace_count):,}" if bh.declared_trace_count else "Not declared"),
            ("First trace byte offset", f"{self.reader.trace_data_start:,} ({self.reader.trace_data_start_source})"),
            ("Trace header bytes", f"{int(np.min(self.index.header_sizes))} to {int(np.max(self.index.header_sizes))}"),
            ("Maximum additional trace headers", str(bh.maximum_additional_trace_headers)),
            ("SEG00001 extension traces", f"{int(np.count_nonzero(self.index.trace_extension_1_present)):,}"),
            ("Trace sample counts", f"{int(np.min(counts)):,} to {int(np.max(counts)):,}"),
            ("Trace sample intervals", ", ".join(f"{v / 1000:g} ms" for v in unique_dt[:12]) + (" …" if unique_dt.size > 12 else "")),
            ("Delay recording times", f"{int(np.min(delays))} to {int(np.max(delays))} ms"),
            ("Display time grid", f"{self.time_grid.start_ms:g} to {self.time_grid.end_ms:g} ms @ {self.time_grid.interval_ms:g} ms"),
            ("Fixed-length trace flag", str(bh.fixed_length_trace_flag)),
            ("Variable trace length detected", "Yes" if unique_ns.size > 1 else "No"),
            ("Mixed sample intervals detected", "Yes" if unique_dt.size > 1 else "No"),
            ("Extended textual headers", str(self.reader.extended_header_count)),
            ("Trailing bytes", f"{self.index.trailing_bytes:,}"),
            ("Truncated", "Yes" if self.index.truncated else "No"),
        ]
        self._set_table(self.file_table, fields)

    def fit(self) -> None:
        if self.reader is None or self.time_grid is None or self.index is None:
            return
        n = self.index.trace_count
        self.set_window(0, n, 0, self.time_grid.sample_count)

    def set_window(self, t0: int, t1: int, s0: int, s1: int) -> None:
        if self.reader is None or self.time_grid is None or self.index is None:
            return
        n = self.index.trace_count
        ns = self.time_grid.sample_count
        self._t0 = max(0, min(int(t0), n - 1))
        self._t1 = max(self._t0 + 1, min(int(t1), n))
        self._s0 = max(0, min(int(s0), ns - 1))
        self._s1 = max(self._s0 + 1, min(int(s1), ns))
        for spin, value in ((self.tstart, self._t0 + 1), (self.tend, self._t1), (self.sstart, self._s0 + 1), (self.send, self._s1)):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        self.render()

    def _spins_window(self) -> None:
        self.set_window(self.tstart.value() - 1, self.tend.value(), self.sstart.value() - 1, self.send.value())

    def _display_trace_indices(self, visible_count: int, mode: str) -> np.ndarray:
        if visible_count <= 0:
            return np.array([], dtype=np.int64)
        if mode in {"vd", "color"}:
            cap = 1800
        else:
            density_pct = int(self.trace_density.value()) if hasattr(self, "trace_density") else 100
            cap = max(1, int(round(visible_count * max(10, min(100, density_pct)) / 100.0)))
            cap = min(cap, 950)
        if visible_count <= cap:
            return np.arange(self._t0, self._t1, dtype=np.int64)
        return np.unique(np.rint(np.linspace(self._t0, self._t1 - 1, cap)).astype(np.int64))

    def _read_aligned_window(self, trace_indices: Optional[np.ndarray] = None) -> np.ndarray:
        if trace_indices is None:
            trace_indices = np.arange(self._t0, self._t1, dtype=np.int64)
        traces = [self.reader.read_trace(int(i), self.index).astype(np.float32, copy=False) for i in trace_indices]
        intervals = self._effective_intervals_us[trace_indices]
        delays = self.index.delay_time_ms[trace_indices]
        return align_traces_to_time_grid(traces, intervals, delays, self.time_grid, self._s0, self._s1)

    def _data_for_indices(self, trace_indices: np.ndarray) -> np.ndarray:
        arr = self._read_aligned_window(trace_indices)
        if self.polarity.isChecked():
            arr = -arr
        attribute = str(self.attribute.currentData() or "amplitude")
        if attribute == "amplitude":
            arr = apply_display_gain(arr, str(self.gain.currentData()), self.time_grid.interval_ms, self.agc_window.value())
            return normalize_for_display(arr, self.clip.value())
        derived = compute_attribute(
            arr.T,
            self.time_grid.interval_ms,
            attribute,
            AttributeParameters(
                rms_window_ms=float(self.rms_window_ms.value()),
                coherence_window_ms=float(self.coherence_window_ms.value()),
                coherence_trace_radius=int(self.coherence_radius.value()),
                minimum_frequency_hz=float(self.sweetness_floor_hz.value()),
            ),
        ).T
        finite = derived[np.isfinite(derived)]
        if finite.size == 0:
            return derived.astype(np.float32, copy=False)
        if attribute == "instantaneous_phase":
            normalized = derived / 180.0
        elif attribute == "semblance":
            normalized = 2.0 * derived - 1.0
        elif attribute in {"envelope", "rms_amplitude", "sweetness"}:
            scale = float(np.percentile(finite, self.clip.value()))
            normalized = np.divide(derived, max(scale, 1e-12))
        else:
            scale = float(np.percentile(np.abs(finite), self.clip.value()))
            normalized = np.divide(derived, max(scale, 1e-12))
        normalized = np.clip(normalized, -1.0, 1.0).astype(np.float32)
        normalized[~np.isfinite(derived)] = np.nan
        return normalized

    def render(self, *_args) -> None:
        if self.reader is None or self.time_grid is None or self.index is None:
            return
        try:
            height = max(300, self.canvas.height() - 62)
            width = max(520, self.canvas.width() - 86)
            mode = str(self.mode.currentData())
            attribute = str(self.attribute.currentData() or "amplitude")
            if attribute != "amplitude" and mode in {"wiggle", "va"}:
                mode = "color"
            trace_indices = self._display_trace_indices(self._t1 - self._t0, mode)
            data = self._data_for_indices(trace_indices)
            image = QImage(width, height, QImage.Format.Format_RGB32)
            image.fill(Qt.GlobalColor.white)
            painter = QPainter(image)
            nt, ns = data.shape
            if nt == 0 or ns == 0:
                painter.end()
                self.canvas.set_image(image, self._t0, self._t1, self._s0, self._s1, data, trace_indices)
                return
            ycoords = np.linspace(0, height - 1, ns)
            if mode in {"vd", "color"}:
                xidx = np.clip(np.rint(np.linspace(0, nt - 1, width)).astype(int), 0, nt - 1)
                yidx = np.clip(np.rint(np.linspace(0, ns - 1, height)).astype(int), 0, ns - 1)
                z = data[xidx][:, yidx].T
                valid = np.isfinite(z)
                if mode == "vd":
                    gray = np.full(z.shape, 255, dtype=np.uint8)
                    gray[valid] = np.clip((z[valid] + 1.0) * 127.5, 0, 255).astype(np.uint8)
                    rgb = np.dstack((gray, gray, gray))
                else:
                    rgb = np.full((height, width, 3), 255, dtype=np.uint8)
                    values = np.clip(z[valid], -1, 1)
                    red = np.clip(values, 0, 1) * 255 + (1 - np.abs(values)) * 245
                    blue = np.clip(-values, 0, 1) * 255 + (1 - np.abs(values)) * 245
                    green = (1 - np.abs(values)) * 245
                    rgb[..., 0][valid] = red.astype(np.uint8)
                    rgb[..., 1][valid] = green.astype(np.uint8)
                    rgb[..., 2][valid] = blue.astype(np.uint8)
                raster = QImage(rgb.data, width, height, 3 * width, QImage.Format.Format_RGB888).copy()
                painter.drawImage(0, 0, raster)
                if hasattr(self, "display_status"):
                    self.display_status.setText(
                        f"Density/raster view • rendering {nt:,} traces from {self._t1 - self._t0:,} visible traces × {ns:,} samples • "
                        f"window traces {self._t0 + 1:,}-{self._t1:,}, samples {self._s0 + 1:,}-{self._s1:,}"
                    )
            else:
                spacing = width / max(1, nt)
                # Adaptive wiggle scaling fixes bad display when zoomed deeply into close traces.
                if nt <= 4:
                    scale = 0.28 * spacing
                    pen_width = 1.35
                    antialias = True
                elif nt <= 30:
                    scale = 0.34 * spacing
                    pen_width = 1.05
                    antialias = True
                elif nt <= 180:
                    scale = 0.42 * spacing
                    pen_width = 0.8
                    antialias = True
                else:
                    scale = 0.46 * spacing
                    pen_width = 0.0 if nt > 450 else 0.7
                    antialias = nt < 350
                if hasattr(self, "display_status"):
                    self.display_status.setText(
                        f"Manual QC wiggle view • drawing {nt:,} traces from {self._t1 - self._t0:,} visible traces • "
                        f"window traces {self._t0 + 1:,}-{self._t1:,}, samples {self._s0 + 1:,}-{self._s1:,}"
                    )
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, antialias)
                if nt <= 40:
                    painter.setPen(QPen(QColor(218, 226, 233), 1))
                    for i in range(nt):
                        base = (i + 0.5) * spacing
                        painter.drawLine(QPointF(base, 0), QPointF(base, height))
                painter.setPen(QPen(Qt.GlobalColor.black, pen_width))
                sample_step = max(1, int(np.ceil(ns / max(1.0, height * 2.2))))
                for i in range(nt):
                    trace = data[i]
                    valid = np.isfinite(trace)
                    if np.count_nonzero(valid) < 2:
                        continue
                    base = (i + 0.5) * spacing
                    idx = np.flatnonzero(valid)[::sample_step]
                    if idx.size < 2:
                        idx = np.flatnonzero(valid)
                    path = QPainterPath(QPointF(base + float(trace[idx[0]]) * scale, float(ycoords[idx[0]])))
                    previous = idx[0]
                    for j in idx[1:]:
                        if j > previous + sample_step * 2:
                            painter.drawPath(path)
                            path = QPainterPath(QPointF(base + float(trace[j]) * scale, float(ycoords[j])))
                        else:
                            path.lineTo(base + float(trace[j]) * scale, float(ycoords[j]))
                        previous = j
                    painter.drawPath(path)
                    if mode == "va":
                        positive = valid & (trace >= 0)
                        starts = np.flatnonzero(positive & ~np.r_[False, positive[:-1]])
                        ends = np.flatnonzero(positive & ~np.r_[positive[1:], False])
                        for start, end in zip(starts, ends):
                            if end <= start:
                                continue
                            segment_idx = np.arange(start, end + 1, sample_step)
                            if segment_idx.size < 2:
                                continue
                            fill = QPainterPath(QPointF(base, float(ycoords[segment_idx[0]])))
                            for j in segment_idx:
                                fill.lineTo(base + float(trace[j]) * scale, float(ycoords[j]))
                            fill.lineTo(base, float(ycoords[segment_idx[-1]]))
                            fill.closeSubpath()
                            painter.fillPath(fill, QColor(15, 25, 35, 100))
                if nt <= 24 and trace_indices.size == nt:
                    painter.setFont(QFont("Arial", 7))
                    painter.setPen(QColor(75, 88, 99))
                    for i, trace_no in enumerate(trace_indices):
                        painter.drawText(QRectF((i + 0.5) * spacing - 24, 4, 48, 14), Qt.AlignmentFlag.AlignCenter, str(int(trace_no) + 1))
            painter.end()
            self.canvas.set_image(image, self._t0, self._t1, self._s0, self._s1, data, trace_indices)
            self.canvas.set_selected_trace(self._selected_trace)
        except Exception as exc:
            QMessageBox.warning(self, "SEG-Y Render", str(exc))

    def _populate_headers(self) -> None:
        self.text_header.setPlainText(self.reader.text_header.text)
        self._set_table(self.binary, list(vars(self.reader.binary_header).items()))
        self.select_trace(0)

    @staticmethod
    def _set_table(table: QTableWidget, items) -> None:
        rows = list(items)
        table.setRowCount(len(rows))
        for row, (key, value) in enumerate(rows):
            table.setItem(row, 0, QTableWidgetItem(str(key)))
            table.setItem(row, 1, QTableWidgetItem(str(value)))

    def select_trace(self, trace_index: int) -> None:
        if self.reader is None or self.index is None:
            return
        self._selected_trace = int(np.clip(trace_index, 0, self.index.trace_count - 1))
        self.canvas.set_selected_trace(self._selected_trace)
        try:
            header = self.reader.read_trace_header(self._selected_trace, self.index)
            self._set_table(self.trace_header, list(vars(header).items()))
            trace = self.reader.read_trace(self._selected_trace, self.index).astype(np.float64)
            finite = trace[np.isfinite(trace)]
            dt_us = float(self._effective_intervals_us[self._selected_trace])
            dt_s = dt_us * 1e-6
            delay_ms = int(self.index.delay_time_ms[self._selected_trace])
            rms = trace_rms(finite)
            metrics: dict[str, object] = {
                "Trace index": self._selected_trace + 1,
                "Trace sequence line": header.trace_sequence_line,
                "Trace sequence file": header.trace_sequence_file,
                "Field record": header.field_record,
                "Trace number": header.trace_number,
                "Energy source point": header.energy_source_point,
                "CDP": header.cdp,
                "CDP trace": header.cdp_trace,
                "Inline 3D": header.inline_3d,
                "Crossline 3D": header.crossline_3d,
                "Offset": f"{header.offset:,.6g}",
                "Source X/Y": f"{header.source_x:,.6g}, {header.source_y:,.6g}",
                "Receiver X/Y": f"{header.receiver_x:,.6g}, {header.receiver_y:,.6g}",
                "CDP X/Y": f"{header.cdp_x:,.6g}, {header.cdp_y:,.6g}",
                "Samples": trace.size,
                "Sample interval": f"{dt_us:g} µs ({dt_us / 1000:g} ms)",
                "Delay recording time": f"{delay_ms} ms",
                "Trace end time": f"{delay_ms + max(trace.size - 1, 0) * dt_us / 1000.0:g} ms",
                "Minimum": np.min(finite) if finite.size else np.nan,
                "Maximum": np.max(finite) if finite.size else np.nan,
                "Mean": np.mean(finite) if finite.size else np.nan,
                "Standard deviation": np.std(finite) if finite.size else np.nan,
                "RMS": rms,
                "Peak/RMS": (np.max(np.abs(finite)) / rms) if finite.size and np.isfinite(rms) and rms > 1e-12 else np.nan,
            }
            if finite.size > 4 and dt_s > 0:
                demeaned = finite - np.mean(finite)
                window = np.hanning(finite.size)
                spectrum = np.abs(np.fft.rfft(demeaned * window))
                frequency = np.fft.rfftfreq(finite.size, d=dt_s)
                power = spectrum * spectrum
                if spectrum.size > 1:
                    dominant_index = int(np.argmax(spectrum[1:]) + 1)
                    metrics["Dominant frequency"] = f"{frequency[dominant_index]:.6g} Hz"
                total_power = float(np.sum(power))
                if total_power > 0:
                    centroid = float(np.sum(frequency * power) / total_power)
                    bandwidth = float(np.sqrt(np.sum(((frequency - centroid) ** 2) * power) / total_power))
                    metrics["Spectral centroid"] = f"{centroid:.6g} Hz"
                    metrics["RMS bandwidth"] = f"{bandwidth:.6g} Hz"
            formatted: list[tuple[str, str]] = []
            for key, value in metrics.items():
                if isinstance(value, (float, np.floating)):
                    formatted.append((key, f"{value:.8g}"))
                else:
                    formatted.append((key, str(value)))
            self._last_metrics = formatted
            self._set_table(self.analysis_table, formatted)
            self.analysis_label.setText(
                f"Trace {self._selected_trace + 1:,} • Field Record {header.field_record} • "
                f"Trace {header.trace_number} • CDP {header.cdp} • Offset {header.offset:,.6g}"
            )
        except Exception as exc:
            self.analysis_label.setText(str(exc))

    def _selected_trace_data(self) -> tuple[np.ndarray, float, float, int]:
        if self.reader is None or self.index is None:
            raise ValueError("No SEG-Y file is open")
        trace = self.reader.read_trace(self._selected_trace, self.index).astype(np.float64)
        dt_us = float(self._effective_intervals_us[self._selected_trace])
        delay_ms = float(self.index.delay_time_ms[self._selected_trace])
        return trace, dt_us, delay_ms, self._selected_trace + 1

    def show_trace_waveform(self) -> None:
        try:
            trace, dt_us, delay_ms, trace_number = self._selected_trace_data()
            dialog = SegyTraceWaveformDialog(trace, dt_us, delay_ms, trace_number, self._last_metrics, self)
            dialog.exec()
        except Exception as exc:
            QMessageBox.warning(self, "SEG-Y Trace", str(exc))

    def show_ft_analysis(self) -> None:
        try:
            trace, dt_us, delay_ms, trace_number = self._selected_trace_data()
            dialog = SegyFTAnalysisDialog(trace, dt_us, delay_ms, trace_number, self)
            dialog.exec()
        except Exception as exc:
            QMessageBox.warning(self, "SEG-Y FT Analysis", str(exc))

    def _set_tool_mode(self, mode: str) -> None:
        self.canvas.set_interaction_mode(mode)
        for name, button in (("inspect", self.inspect_btn), ("pick", self.pick_btn), ("measure", self.measure_btn)):
            button.setObjectName("activeTool" if name == mode else "")
            button.style().unpolish(button)
            button.style().polish(button)
        if mode == "inspect":
            self.measurement_label.setText("Inspect mode: click any trace to read exact trace header and QC metrics.")
        elif mode == "pick":
            self.measurement_label.setText("Pick mode: click trace/time positions to store manual QC picks.")
        else:
            self.measurement_label.setText("Measure mode: click start point, then click end point. Preview follows the cursor.")

    def clear_manual_marks(self) -> None:
        self.canvas.clear_marks()
        self.pick_table.setRowCount(0)
        self.measurement_label.setText("Manual marks cleared.")

    def _record_pick(self, pick_obj: object) -> None:
        if not isinstance(pick_obj, SegyPick):
            return
        row = self.pick_table.rowCount()
        self.pick_table.insertRow(row)
        for col, value in enumerate(pick_obj.row()):
            self.pick_table.setItem(row, col, QTableWidgetItem(value))

    def _update_cursor_status(self, text: str) -> None:
        self.cursor_status.setText(text)

    def _update_measurement_status(self, text: str) -> None:
        self.measurement_label.setText(text)

    def copy_measurement(self) -> None:
        text = self.measurement_label.text()
        QApplication.clipboard().setText(text)

    def show_display_page(self) -> None:
        self.side_tabs.setCurrentIndex(0)

    def show_file_info_page(self) -> None:
        self.side_tabs.setCurrentIndex(4)

    def show_headers_page(self) -> None:
        self.side_tabs.setCurrentIndex(5)

    def show_trace_analysis_page(self) -> None:
        self.side_tabs.setCurrentIndex(6)

    def export_image(self) -> None:
        if self.canvas._image.isNull():
            return
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export SEG-Y View",
            str(self.file_path.with_suffix(".png")),
            "PNG (*.png);;JPEG (*.jpg)",
        )
        if not path:
            return
        output = Path(path)
        if not output.suffix:
            output = output.with_suffix(".jpg" if "JPEG" in selected_filter else ".png")
        ok = self.grab().toImage().save(str(output), "JPEG" if output.suffix.lower() in {".jpg", ".jpeg"} else "PNG")
        if not ok:
            QMessageBox.warning(self, "Export", "Could not save image")
