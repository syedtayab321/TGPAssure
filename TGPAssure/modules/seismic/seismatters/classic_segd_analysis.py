from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QAction, QPixmap
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QFileDialog,
    QPushButton, QLabel, QLineEdit, QSpinBox, QDoubleSpinBox, QRadioButton,
    QCheckBox, QGroupBox, QButtonGroup, QMessageBox, QColorDialog, QDialog,
    QDialogButtonBox, QScrollArea, QFrame, QSizePolicy
)

try:
    from scipy.signal import butter, sosfiltfilt
except Exception:  # pragma: no cover
    butter = None
    sosfiltfilt = None

from modules.seismic.segd_viewer.segd_reader import SegdReader


class _SmallBox(QLineEdit):
    def __init__(self, text: str = "", width: int = 48, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedWidth(width)
        self.setMaximumHeight(18)
        self.setStyleSheet("font-size:8px; padding:0px 2px;")


class _SegdTraceCanvas(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.samples = np.empty((0, 0), dtype=np.float32)
        self.sample_interval_ms = 1.0
        self.start_trace = 0
        self.display_mode = "wiggle"
        self.trace_color = QColor(0, 0, 0)
        self.fill_color = QColor(20, 210, 45)
        self.clip = 2.0
        self.traces_per_inch = 24
        self.inches_per_second = 7.0
        self.grid_ms = 500.0
        self.line_labels: list[str] = []
        self.setMinimumSize(900, 520)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAutoFillBackground(True)

    def set_data(self, samples: np.ndarray, sample_interval_ms: float, start_trace: int = 0) -> None:
        arr = np.asarray(samples, dtype=np.float32)
        if arr.ndim == 3:
            arr = arr[:, 0, :]
        self.samples = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
        self.sample_interval_ms = max(float(sample_interval_ms or 1.0), 0.001)
        self.start_trace = int(start_trace)
        self.update()

    def set_controls(self, *, display_mode: str, trace_color: QColor, fill_color: QColor, clip: float,
                     traces_per_inch: int, inches_per_second: float) -> None:
        self.display_mode = display_mode
        self.trace_color = QColor(trace_color)
        self.fill_color = QColor(fill_color)
        self.clip = max(float(clip), 0.05)
        self.traces_per_inch = max(int(traces_per_inch), 1)
        self.inches_per_second = max(float(inches_per_second), 0.1)
        self.update()

    def _amplitude_norm(self, data: np.ndarray) -> np.ndarray:
        if data.size == 0:
            return data
        scale = np.nanpercentile(np.abs(data), 98)
        if not np.isfinite(scale) or scale <= 0:
            scale = float(np.max(np.abs(data)) or 1.0)
        return np.clip(data / scale, -self.clip, self.clip) / self.clip

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.fillRect(self.rect(), QColor(248, 248, 246))
        margin_l, margin_t, margin_r, margin_b = 56, 24, 14, 28
        plot = QRectF(margin_l, margin_t, max(10, self.width() - margin_l - margin_r), max(10, self.height() - margin_t - margin_b))
        painter.fillRect(plot, QColor(255, 255, 255))
        painter.setPen(QPen(QColor(150, 150, 150), 1))
        painter.drawRect(plot)

        if self.samples.size == 0:
            painter.setPen(QColor(70, 70, 70))
            painter.drawText(plot, Qt.AlignCenter, "Open a SEG-D V2/V2.1 demultiplexed file to display traces")
            return

        traces, ns = self.samples.shape
        data = self._amplitude_norm(self.samples)
        dt = self.sample_interval_ms
        total_ms = max(ns * dt, 1.0)

        # grid and axis labels
        painter.setPen(QPen(QColor(190, 80, 80, 150), 1))
        step = 500.0 if total_ms <= 4000 else 1000.0
        t = 0.0
        while t <= total_ms:
            y = plot.top() + (t / total_ms) * plot.height()
            painter.drawLine(plot.left(), y, plot.right(), y)
            painter.setPen(QColor(80, 80, 150))
            painter.drawText(4, int(y + 4), f"{t/1000:.1f}s")
            painter.setPen(QPen(QColor(190, 80, 80, 150), 1))
            t += step

        top_step = max(1, traces // 18)
        painter.setPen(QColor(40, 40, 120))
        for i in range(0, traces, top_step):
            x = plot.left() + (i + 0.5) * plot.width() / traces
            painter.drawText(int(x - 12), 10, str(self.start_trace + i + 1))

        dx = plot.width() / max(traces, 1)
        amp = dx * 0.45
        yvals = plot.top() + np.linspace(0.0, plot.height(), ns)
        mode = self.display_mode
        for i in range(traces):
            x0 = plot.left() + (i + 0.5) * dx
            x = x0 + data[i] * amp
            path = QPainterPath(QPointF(float(x[0]), float(yvals[0])))
            for k in range(1, ns, max(1, ns // 900)):
                path.lineTo(float(x[k]), float(yvals[k]))
            if mode in {"va_plus", "va_minus", "va_both", "gradient"}:
                pos = data[i] >= 0
                neg = data[i] <= 0
                painter.setPen(Qt.NoPen)
                painter.setBrush(self.fill_color)
                if mode in {"va_plus", "va_both", "gradient"}:
                    self._draw_fill(painter, x0, x, yvals, pos, ns)
                if mode in {"va_minus", "va_both"}:
                    painter.setBrush(QColor(0, 0, 0))
                    self._draw_fill(painter, x0, x, yvals, neg, ns)
            painter.setPen(QPen(self.trace_color, 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)

        painter.setPen(QColor(30, 30, 30))
        painter.drawText(int(plot.left()), self.height() - 8, f"Traces {self.start_trace + 1}-{self.start_trace + traces}    Samples {ns}    dt {dt:g} ms")

    def _draw_fill(self, painter: QPainter, x0: float, x: np.ndarray, yvals: np.ndarray, mask: np.ndarray, ns: int) -> None:
        step = max(1, ns // 900)
        active = False
        poly: list[QPointF] = []
        for k in range(0, ns, step):
            if bool(mask[k]) and not active:
                active = True
                poly = [QPointF(float(x0), float(yvals[k])), QPointF(float(x[k]), float(yvals[k]))]
            elif bool(mask[k]) and active:
                poly.append(QPointF(float(x[k]), float(yvals[k])))
            elif active:
                poly.append(QPointF(float(x0), float(yvals[k - step])))
                painter.drawPolygon(poly)
                active = False
        if active and poly:
            poly.append(QPointF(float(x0), float(yvals[min(ns - 1, len(yvals) - 1)])))
            painter.drawPolygon(poly)


class _FilterDialog(QDialog):
    def __init__(self, parent: QWidget | None, low1: float, low2: float, high1: float, high2: float, use_low: bool, use_high: bool) -> None:
        super().__init__(parent)
        self.setWindowTitle("Filter Setup")
        layout = QFormLayout(self)
        self.low1 = QDoubleSpinBox(); self.low1.setRange(0.01, 500.0); self.low1.setValue(low1); self.low1.setSuffix(" Hz")
        self.low2 = QDoubleSpinBox(); self.low2.setRange(0.01, 500.0); self.low2.setValue(low2); self.low2.setSuffix(" Hz")
        self.high1 = QDoubleSpinBox(); self.high1.setRange(0.01, 1000.0); self.high1.setValue(high1); self.high1.setSuffix(" Hz")
        self.high2 = QDoubleSpinBox(); self.high2.setRange(0.01, 1000.0); self.high2.setValue(high2); self.high2.setSuffix(" Hz")
        self.use_low = QCheckBox("Apply Low Cut"); self.use_low.setChecked(use_low)
        self.use_high = QCheckBox("Apply High Cut"); self.use_high.setChecked(use_high)
        layout.addRow("F1", self.low1); layout.addRow("F2", self.low2); layout.addRow(self.use_low)
        layout.addRow("F3", self.high1); layout.addRow("F4", self.high2); layout.addRow(self.use_high)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addRow(buttons)


class _GainCurveDialog(QDialog):
    def __init__(self, parent: QWidget | None, a: float, b: float, c: float) -> None:
        super().__init__(parent)
        self.setWindowTitle("Applied Gain Curve Setup")
        layout = QVBoxLayout(self)
        eq = QLabel("Gain Recovery Equation\nGain (db)=A*t + B*20*Log(t) + C")
        eq.setAlignment(Qt.AlignCenter)
        layout.addWidget(eq)
        form = QFormLayout()
        self.a = QDoubleSpinBox(); self.a.setRange(-1000, 1000); self.a.setValue(a); self.a.setDecimals(3)
        self.b = QDoubleSpinBox(); self.b.setRange(-1000, 1000); self.b.setValue(b); self.b.setDecimals(3)
        self.c = QDoubleSpinBox(); self.c.setRange(-1000, 1000); self.c.setValue(c); self.c.setDecimals(3)
        form.addRow("A", self.a); form.addRow("B", self.b); form.addRow("C", self.c)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class SegdAnalysisWidget(QWidget):
    """Compact SEG-D analysis viewer modelled on the documented Seismatters SEG-D Viewer controls."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("module_id", "segd_analysis")
        self.reader: Optional[SegdReader] = None
        self.file_path: Optional[Path] = None
        self.raw = np.empty((0, 0), dtype=np.float32)
        self.start_trace = 0
        self.window_traces = 260
        self.trace_color = QColor(0, 0, 0)
        self.fill_color = QColor(20, 210, 45)
        self.low1, self.low2, self.high1, self.high2 = 3.0, 15.0, 40.0, 50.0
        self.use_low = False
        self.use_high = False
        self.gain_a, self.gain_b, self.gain_c = 0.0, 2.0, 30.0
        self._build_ui()
        self._apply_small_style()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self); root.setContentsMargins(3, 3, 3, 3); root.setSpacing(4)
        left = QFrame(); left.setFixedWidth(104); left.setObjectName("legacySide")
        lv = QVBoxLayout(left); lv.setContentsMargins(3, 3, 3, 3); lv.setSpacing(3)
        for text, slot in [("Open", self.open_file), ("BMP", self.export_bmp), ("Print", self.print_view), ("End", self.close)]:
            b = QPushButton(text); b.setFixedHeight(20); b.clicked.connect(slot); lv.addWidget(b)
        nav = QHBoxLayout(); self.prev_btn = QPushButton("≪"); self.next_btn = QPushButton("≫")
        self.prev_btn.clicked.connect(lambda: self.scroll_records(-1)); self.next_btn.clicked.connect(lambda: self.scroll_records(1))
        nav.addWidget(self.prev_btn); nav.addWidget(self.next_btn); lv.addLayout(nav)

        info = QGroupBox("File Information"); form = QFormLayout(info); form.setContentsMargins(4, 8, 4, 4); form.setSpacing(1)
        self.box_file = _SmallBox("", 44); self.box_rate = _SmallBox("", 44); self.box_len = _SmallBox("", 44)
        self.box_traces = _SmallBox("", 44); self.box_aux = _SmallBox("", 44)
        for label, box in [("File Number", self.box_file), ("Sample Rate", self.box_rate), ("Record Length", self.box_len), ("Total Traces", self.box_traces), ("Total Aux", self.box_aux)]:
            form.addRow(label, box)
        lv.addWidget(info)

        scale = QGroupBox("Trace Scaling"); sf = QFormLayout(scale); sf.setContentsMargins(4, 8, 4, 4); sf.setSpacing(1)
        self.traces_per_inch = QSpinBox(); self.traces_per_inch.setRange(1, 200); self.traces_per_inch.setValue(24)
        self.inches_per_second = QDoubleSpinBox(); self.inches_per_second.setRange(0.1, 50); self.inches_per_second.setValue(7); self.inches_per_second.setDecimals(1)
        self.clip = QDoubleSpinBox(); self.clip.setRange(0.1, 10); self.clip.setValue(2); self.clip.setSingleStep(0.1)
        for w in (self.traces_per_inch, self.inches_per_second, self.clip):
            w.valueChanged.connect(self.refresh_canvas)
        sf.addRow("Traces/Inch X", self.traces_per_inch); sf.addRow("Inches/Sec Y", self.inches_per_second); sf.addRow("Clip", self.clip)
        lv.addWidget(scale)

        mode_box = QGroupBox("Display"); mv = QVBoxLayout(mode_box); mv.setContentsMargins(4, 8, 4, 4); mv.setSpacing(1)
        self.mode_group = QButtonGroup(self)
        for text, key, checked in [
            ("Wiggle Trace", "wiggle", True), ("VA Fill +", "va_plus", False), ("VA Fill -", "va_minus", False),
            ("VA Fill Both", "va_both", False), ("Gradient Fill", "gradient", False)]:
            rb = QRadioButton(text); rb.setProperty("mode", key); rb.setChecked(checked); self.mode_group.addButton(rb); mv.addWidget(rb)
        self.mode_group.buttonClicked.connect(self.refresh_canvas)
        color_row = QHBoxLayout(); self.left_color = QPushButton(); self.right_color = QPushButton();
        self.left_color.setFixedSize(30, 18); self.right_color.setFixedSize(30, 18)
        self.left_color.clicked.connect(lambda: self.pick_color("trace")); self.right_color.clicked.connect(lambda: self.pick_color("fill"))
        color_row.addWidget(self.left_color); color_row.addWidget(self.right_color); mv.addLayout(color_row)
        lv.addWidget(mode_box)

        gain = QGroupBox("Gain Control"); gv = QVBoxLayout(gain); gv.setContentsMargins(4, 8, 4, 4); gv.setSpacing(1)
        self.filter_on = QCheckBox("Filter"); self.filter_on.stateChanged.connect(self.refresh_canvas)
        self.filter_setup = QPushButton("Setup"); self.filter_setup.clicked.connect(self.setup_filter)
        row = QHBoxLayout(); row.addWidget(self.filter_on); row.addWidget(self.filter_setup); gv.addLayout(row)
        self.gain_group = QButtonGroup(self)
        for text, key, checked in [("Fixed gain", "fixed", True), ("Normalised Peak", "peak", False), ("AGC", "agc", False)]:
            rb = QRadioButton(text); rb.setProperty("gain", key); rb.setChecked(checked); self.gain_group.addButton(rb); gv.addWidget(rb)
        self.gain_group.buttonClicked.connect(self.refresh_canvas)
        self.gain_setup = QPushButton("Setup"); self.gain_setup.clicked.connect(self.setup_gain_curve); gv.addWidget(self.gain_setup)
        self.gain_set = QSpinBox(); self.gain_set.setRange(1, 999); self.gain_set.setValue(18); self.gain_set.valueChanged.connect(self.refresh_canvas)
        gf = QFormLayout(); gf.addRow("Gain Set", self.gain_set); gv.addLayout(gf)
        lv.addWidget(gain)
        lv.addStretch(1)
        root.addWidget(left)

        self.canvas = _SegdTraceCanvas()
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(self.canvas)
        root.addWidget(scroll, 1)
        self._update_color_buttons()

    def _apply_small_style(self) -> None:
        self.setStyleSheet("""
        QWidget { font-size: 8px; }
        QGroupBox { font-size: 8px; font-weight: 600; margin-top: 8px; }
        QGroupBox::title { subcontrol-origin: margin; left: 4px; padding: 0px 2px; }
        QPushButton { font-size: 8px; padding: 1px 3px; }
        QSpinBox, QDoubleSpinBox, QLineEdit { font-size: 8px; min-height: 15px; max-height: 18px; padding:0px; }
        QRadioButton, QCheckBox, QLabel { font-size: 8px; }
        #legacySide { background:#d6d2c8; border:1px solid #a9a59d; }
        """)

    def _selected_mode(self) -> str:
        btn = self.mode_group.checkedButton()
        return str(btn.property("mode") if btn else "wiggle")

    def _selected_gain(self) -> str:
        btn = self.gain_group.checkedButton()
        return str(btn.property("gain") if btn else "fixed")

    def pick_color(self, which: str) -> None:
        current = self.trace_color if which == "trace" else self.fill_color
        color = QColorDialog.getColor(current, self, "Select display colour")
        if color.isValid():
            if which == "trace": self.trace_color = color
            else: self.fill_color = color
            self._update_color_buttons(); self.refresh_canvas()

    def _update_color_buttons(self) -> None:
        self.left_color.setStyleSheet(f"background:{self.trace_color.name()};")
        self.right_color.setStyleSheet(f"background:{self.fill_color.name()};")

    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open SEG-D File", str(Path.home()), "SEG-D Files (*.segd *.sgd *.d *.dat);;All Files (*.*)")
        if path:
            self.open_path(path)

    def open_path(self, path: str | Path) -> None:
        try:
            self.file_path = Path(path)
            self.reader = SegdReader(self.file_path)
            self.start_trace = 0
            self.load_window()
            self.setProperty("segd_file_path", str(self.file_path.resolve()))
        except Exception as exc:
            QMessageBox.critical(self, "SEG-D Analysis", f"Unable to open SEG-D file:\n{path}\n\n{exc}")

    def load_window(self) -> None:
        if self.reader is None:
            return
        end = min(self.reader.get_trace_count(), self.start_trace + self.window_traces)
        self.raw = self.reader.read_channel_data((self.start_trace, end), 0)
        self.box_file.setText(str(getattr(getattr(self.reader, 'general_header_1', None), 'file_number', '')))
        self.box_rate.setText(f"{self.reader.get_sample_interval():g}")
        self.box_len.setText(f"{self.reader.get_sample_count() * self.reader.get_sample_interval() / 1000:g}")
        self.box_traces.setText(str(self.reader.get_trace_count()))
        self.box_aux.setText(str(self.reader.get_aux_trace_count()))
        self.refresh_canvas()

    def scroll_records(self, direction: int) -> None:
        if self.reader is None:
            return
        step = max(1, self.window_traces // 2)
        self.start_trace = max(0, min(self.reader.get_trace_count() - 1, self.start_trace + direction * step))
        self.load_window()

    def _processed(self) -> np.ndarray:
        data = np.array(self.raw, dtype=np.float32, copy=True)
        if data.size == 0:
            return data
        data -= np.mean(data, axis=1, keepdims=True)
        mode = self._selected_gain()
        if mode == "peak":
            peak = np.max(np.abs(data), axis=1, keepdims=True)
            data = data / np.maximum(peak, 1e-9)
        elif mode == "agc":
            win = max(5, min(data.shape[1] // 2, int(500.0 / max(self.reader.get_sample_interval() if self.reader else 1.0, 0.001))))
            kernel = np.ones(win, dtype=np.float32) / win
            rms = np.sqrt(np.apply_along_axis(lambda x: np.convolve(x * x, kernel, mode="same"), 1, data))
            data = data / np.maximum(rms, 1e-9)
        else:
            data *= 10 ** (self.gain_set.value() / 20.0)
        if self.filter_on.isChecked() and (self.use_low or self.use_high) and butter is not None and sosfiltfilt is not None:
            fs = 1000.0 / max(self.reader.get_sample_interval() if self.reader else 1.0, 0.001)
            try:
                if self.use_low and self.use_high:
                    low = max(min(self.low1, self.low2), 0.01); high = min(max(self.high1, self.high2), fs / 2.1)
                    if low < high:
                        sos = butter(3, [low, high], btype="bandpass", fs=fs, output="sos")
                        data = sosfiltfilt(sos, data, axis=1)
                elif self.use_low:
                    sos = butter(3, max(self.low1, 0.01), btype="highpass", fs=fs, output="sos")
                    data = sosfiltfilt(sos, data, axis=1)
                elif self.use_high:
                    sos = butter(3, min(self.high2, fs / 2.1), btype="lowpass", fs=fs, output="sos")
                    data = sosfiltfilt(sos, data, axis=1)
            except Exception:
                pass
        return data

    def refresh_canvas(self) -> None:
        dt = self.reader.get_sample_interval() if self.reader else 1.0
        self.canvas.set_data(self._processed(), dt, self.start_trace)
        self.canvas.set_controls(display_mode=self._selected_mode(), trace_color=self.trace_color, fill_color=self.fill_color,
                                 clip=self.clip.value(), traces_per_inch=self.traces_per_inch.value(), inches_per_second=self.inches_per_second.value())

    def setup_filter(self) -> None:
        dlg = _FilterDialog(self, self.low1, self.low2, self.high1, self.high2, self.use_low, self.use_high)
        if dlg.exec() == QDialog.Accepted:
            self.low1, self.low2, self.high1, self.high2 = dlg.low1.value(), dlg.low2.value(), dlg.high1.value(), dlg.high2.value()
            self.use_low, self.use_high = dlg.use_low.isChecked(), dlg.use_high.isChecked()
            self.filter_on.setChecked(self.use_low or self.use_high)
            self.refresh_canvas()

    def setup_gain_curve(self) -> None:
        dlg = _GainCurveDialog(self, self.gain_a, self.gain_b, self.gain_c)
        if dlg.exec() == QDialog.Accepted:
            self.gain_a, self.gain_b, self.gain_c = dlg.a.value(), dlg.b.value(), dlg.c.value()
            # curve is represented by the AGC option in this compact implementation
            self.refresh_canvas()

    def export_bmp(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save Display", str(Path.home() / "segd_display.bmp"), "Bitmap (*.bmp);;PNG (*.png);;JPEG (*.jpg)")
        if path:
            self.canvas.grab().save(path)

    def export_image(self) -> None:
        self.export_bmp()

    def print_view(self) -> None:
        printer = QPrinter(QPrinter.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QDialog.Accepted:
            return
        painter = QPainter(printer)
        pix = self.canvas.grab()
        rect = painter.viewport()
        scaled = pix.scaled(rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        painter.drawPixmap(rect.x(), rect.y(), scaled)
        painter.end()

    # Ribbon compatibility
    def set_display_mode(self, mode: str) -> None:
        mapping = {"variable_area": "va_plus", "variable_density": "wiggle", "color_density": "va_both", "wiggle_color": "gradient"}
        wanted = mapping.get(mode, mode)
        for btn in self.mode_group.buttons():
            if btn.property("mode") == wanted:
                btn.setChecked(True); break
        self.refresh_canvas()

    def set_gain_mode(self, mode: str) -> None:
        mapping = {"none": "fixed", "trace_balance": "peak", "fixed": "fixed", "agc": "agc"}
        wanted = mapping.get(mode, mode)
        for btn in self.gain_group.buttons():
            if btn.property("gain") == wanted:
                btn.setChecked(True); break
        self.refresh_canvas()

    def zoom_to_fit(self) -> None:
        self.refresh_canvas()

    def reset_to_initial_view(self) -> None:
        self.start_trace = 0
        self.load_window()

    def reload_file(self) -> None:
        if self.file_path:
            self.open_path(self.file_path)

    def run_qc(self, qc_type: str = "full") -> None:
        if self.reader is None:
            QMessageBox.information(self, "SEG-D QC", "Open a SEG-D file first.")
            return
        QMessageBox.information(self, "SEG-D QC", f"{qc_type.title()} QC\nTraces: {self.reader.get_trace_count()}\nAux: {self.reader.get_aux_trace_count()}\nSample interval: {self.reader.get_sample_interval():g} ms")

    def set_interaction_mode(self, mode: str) -> None:
        pass
