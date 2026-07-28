from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QWheelEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
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


class SegyCanvas(QWidget):
    """Seismic canvas that zooms the underlying trace/time window, not a bitmap."""

    window_changed = Signal(int, int, int, int)
    trace_selected = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(420, 320)
        self.setMouseTracking(True)
        self._image = QImage()
        self._t0 = self._s0 = 0
        self._t1 = self._s1 = 1
        self._total_t = self._total_s = 1
        self._grid_start_ms = 0.0
        self._sample_interval_ms = 1.0
        self._drag: Optional[QPointF] = None

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

    def set_image(self, image: QImage, t0: int, t1: int, s0: int, s1: int) -> None:
        self._image = image
        self._t0, self._t1, self._s0, self._s1 = int(t0), int(t1), int(s0), int(s1)
        self.update()

    def plot_rect(self) -> QRectF:
        return QRectF(72, 30, max(1, self.width() - 84), max(1, self.height() - 58))

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(24, 30, 36))
        rect = self.plot_rect()
        painter.fillRect(rect, Qt.GlobalColor.white)
        if not self._image.isNull():
            painter.drawImage(rect, self._image)
        painter.setPen(QPen(QColor(91, 106, 119)))
        painter.drawRect(rect)
        painter.setPen(QColor(224, 229, 234))
        for i in range(9):
            fraction = i / 8
            x = rect.left() + fraction * rect.width()
            trace = self._t0 + fraction * max(1, self._t1 - self._t0 - 1)
            painter.drawText(QRectF(x - 30, 5, 60, 20), Qt.AlignmentFlag.AlignCenter, str(int(round(trace)) + 1))
        for i in range(9):
            fraction = i / 8
            y = rect.top() + fraction * rect.height()
            sample = self._s0 + fraction * max(1, self._s1 - self._s0 - 1)
            time_ms = self._grid_start_ms + sample * self._sample_interval_ms
            painter.drawText(
                QRectF(4, y - 9, 62, 18),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{time_ms:.0f}",
            )
        painter.setPen(QColor(160, 175, 187))
        painter.drawText(QRectF(4, 5, 64, 20), Qt.AlignmentFlag.AlignLeft, "ms")
        painter.end()

    def wheelEvent(self, event: QWheelEvent) -> None:
        rect = self.plot_rect()
        pos = event.position()
        if not rect.contains(pos):
            return
        trace_span = max(2, self._t1 - self._t0)
        sample_span = max(2, self._s1 - self._s0)
        factor = 0.72 if event.angleDelta().y() > 0 else 1 / 0.72
        fx = (pos.x() - rect.left()) / max(1.0, rect.width())
        fy = (pos.y() - rect.top()) / max(1.0, rect.height())
        only_x = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        only_y = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        new_t = trace_span if only_y else int(np.clip(round(trace_span * factor), 4, self._total_t))
        new_s = sample_span if only_x else int(np.clip(round(sample_span * factor), 16, self._total_s))
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
            fraction = (event.position().x() - rect.left()) / max(1.0, rect.width())
            trace = int(np.clip(self._t0 + fraction * (self._t1 - self._t0), 0, self._total_t - 1))
            self.trace_selected.emit(trace)
        if event.button() == Qt.MouseButton.MiddleButton:
            self._drag = event.position()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag is not None and event.buttons() & Qt.MouseButton.MiddleButton:
            rect = self.plot_rect()
            delta = event.position() - self._drag
            self._drag = event.position()
            trace_span = self._t1 - self._t0
            sample_span = self._s1 - self._s0
            dt = int(round(-delta.x() / max(1.0, rect.width()) * trace_span))
            ds = int(round(-delta.y() / max(1.0, rect.height()) * sample_span))
            t0 = max(0, min(self._t0 + dt, self._total_t - trace_span))
            s0 = max(0, min(self._s0 + ds, self._total_s - sample_span))
            self.window_changed.emit(t0, t0 + trace_span, s0, s0 + sample_span)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._drag = None
        super().mouseReleaseEvent(event)


class SegyViewerWidget(QWidget):
    """Professional SEG-Y viewer with exact trace timing and variable-length support."""

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
        self._build_ui()
        self.open_file(self.file_path)

    def _build_ui(self) -> None:
        self.setStyleSheet(
            "QFrame#segyTopBar{background:#f7f9fb;border-bottom:1px solid #d9e1e8;}"
            "QListWidget#segyNav{background:#172938;color:#eaf1f6;border:0;padding:6px;}"
            "QListWidget#segyNav::item{padding:11px 10px;margin:2px;border-radius:5px;}"
            "QListWidget#segyNav::item:selected{background:#1778b5;color:white;font-weight:700;}"
            "QListWidget#segyNav::item:hover{background:#24465d;}"
            "QGroupBox{font-weight:700;border:1px solid #d9e2e9;border-radius:5px;margin-top:8px;padding-top:8px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:10px;padding:0 4px;}"
            "QComboBox,QDoubleSpinBox,QSpinBox{min-height:22px;}"
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
        open_button.clicked.connect(self._choose_file)
        fit_button = QPushButton("Fit Data")
        fit_button.clicked.connect(self.fit)
        export_button = QPushButton("Export Image")
        export_button.clicked.connect(self.export_image)
        row.addWidget(self.file_label)
        row.addWidget(self.info)
        row.addStretch(1)
        row.addWidget(fit_button)
        row.addWidget(export_button)
        row.addWidget(open_button)
        root.addWidget(bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.canvas = SegyCanvas()
        self.canvas.window_changed.connect(self.set_window)
        self.canvas.trace_selected.connect(self.select_trace)
        splitter.addWidget(self.canvas)

        side = QFrame()
        side.setMinimumWidth(300)
        side.setMaximumWidth(430)
        side_layout = QHBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(0)
        self.nav = QListWidget()
        self.nav.setObjectName("segyNav")
        self.nav.setFixedWidth(92)
        self.pages = QStackedWidget()
        for title, page in (
            ("Display", self._display_page()),
            ("File Info", self._file_info_page()),
            ("Headers", self._headers_page()),
            ("Trace QC", self._analysis_page()),
        ):
            self.nav.addItem(QListWidgetItem(title))
            self.pages.addWidget(page)
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.setCurrentRow(0)
        side_layout.addWidget(self.nav)
        side_layout.addWidget(self.pages, 1)
        splitter.addWidget(side)
        splitter.setStretchFactor(0, 10)
        splitter.setStretchFactor(1, 0)
        splitter.setCollapsible(1, True)
        splitter.setSizes([1240, 335])
        root.addWidget(splitter, 1)

        hint = QLabel(
            "Wheel: true trace/time zoom • Ctrl+wheel: traces only • Shift+wheel: time only • "
            "Middle-drag: pan • Click trace: inspect exact trace header/QC"
        )
        hint.setStyleSheet("padding:2px 8px;background:#edf3f7;color:#536879;font-size:9px;border-top:1px solid #d9e1e8;")
        root.addWidget(hint)

    def _display_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 6, 8, 6)
        display_group = QGroupBox("Seismic Display")
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
        self.polarity = QCheckBox("Reverse polarity")
        self.polarity.toggled.connect(self.render)
        for control in (self.mode, self.attribute, self.gain, self.agc_window, self.clip):
            control.setMinimumWidth(110)
            control.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        form.addRow("Display", self.mode)
        form.addRow("Attribute", self.attribute)
        form.addRow("Gain", self.gain)
        form.addRow("AGC window", self.agc_window)
        form.addRow("Clip", self.clip)
        form.addRow(self.polarity)

        attribute_group = QGroupBox("Attribute Analysis")
        attribute_form = QFormLayout(attribute_group)
        self._configure_form(attribute_form)
        self.rms_window_ms = QDoubleSpinBox()
        self.rms_window_ms.setRange(2.0, 2000.0)
        self.rms_window_ms.setValue(40.0)
        self.rms_window_ms.setSuffix(" ms")
        self.coherence_window_ms = QDoubleSpinBox()
        self.coherence_window_ms.setRange(2.0, 2000.0)
        self.coherence_window_ms.setValue(32.0)
        self.coherence_window_ms.setSuffix(" ms")
        self.coherence_radius = QSpinBox()
        self.coherence_radius.setRange(0, 20)
        self.coherence_radius.setValue(2)
        self.sweetness_floor_hz = QDoubleSpinBox()
        self.sweetness_floor_hz.setRange(0.1, 100.0)
        self.sweetness_floor_hz.setDecimals(1)
        self.sweetness_floor_hz.setValue(1.0)
        self.sweetness_floor_hz.setSuffix(" Hz")
        for control in (self.rms_window_ms, self.coherence_window_ms, self.coherence_radius, self.sweetness_floor_hz):
            control.setMinimumWidth(95)
            control.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            control.valueChanged.connect(self.render)
        attribute_form.addRow("RMS window", self.rms_window_ms)
        attribute_form.addRow("Coherence window", self.coherence_window_ms)
        attribute_form.addRow("Trace aperture radius", self.coherence_radius)
        attribute_form.addRow("Sweetness freq. floor", self.sweetness_floor_hz)

        window_group = QGroupBox("Visible Data Window")
        window_form = QFormLayout(window_group)
        self._configure_form(window_form)
        self.tstart = QSpinBox()
        self.tend = QSpinBox()
        self.sstart = QSpinBox()
        self.send = QSpinBox()
        for spin in (self.tstart, self.tend, self.sstart, self.send):
            spin.setMinimum(1)
            spin.setMinimumWidth(95)
            spin.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            spin.editingFinished.connect(self._spins_window)
        window_form.addRow("First trace", self.tstart)
        window_form.addRow("Last trace", self.tend)
        window_form.addRow("First display sample", self.sstart)
        window_form.addRow("Last display sample", self.send)
        layout.addWidget(display_group)
        layout.addWidget(attribute_group)
        layout.addWidget(window_group)
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
        self.text_header = QTextEdit()
        self.text_header.setReadOnly(True)
        self.text_header.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
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
        self.analysis_table = self._make_property_table()
        layout.addWidget(self.analysis_label)
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
        try:
            self.file_path = Path(path)
            self.reader = SegyReader(self.file_path)
            self.index = self.reader.scan_trace_headers()
            if self.index.trace_count <= 0:
                raise ValueError("SEG-Y contains no complete traces")
            intervals = self.index.sample_intervals_us.copy()
            binary_dt = int(self.reader.binary_header.sample_interval_us)
            intervals[intervals <= 0] = binary_dt
            if np.any(intervals <= 0):
                raise ValueError("SEG-Y does not contain a valid sample interval")
            self._effective_intervals_us = intervals
            self.time_grid = build_time_grid(self.index.sample_counts, intervals, self.index.delay_time_ms)
            n = self.index.trace_count
            self.file_label.setText(self.file_path.name)
            bh = self.reader.binary_header
            self.info.setText(
                f"Rev {bh.revision}  •  {n:,} traces  •  {self.time_grid.interval_ms:g} ms display dt  •  "
                f"{self.reader.sample_format_name}  •  {self.reader.text_header.encoding}"
            )
            self.canvas.set_data_extent(n, self.time_grid.sample_count, self.time_grid.interval_ms, self.time_grid.start_ms)
            self.tstart.setMaximum(n)
            self.tend.setMaximum(n)
            self.sstart.setMaximum(self.time_grid.sample_count)
            self.send.setMaximum(self.time_grid.sample_count)
            self._populate_headers()
            self._populate_file_info()
            self.fit()
        except Exception as exc:
            QMessageBox.critical(self, "SEG-Y Open Error", str(exc))

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
        if self.reader is None or self.time_grid is None:
            return
        n = self.index.trace_count
        self.set_window(0, n, 0, self.time_grid.sample_count)

    def set_window(self, t0: int, t1: int, s0: int, s1: int) -> None:
        if self.reader is None or self.time_grid is None:
            return
        n = self.index.trace_count
        ns = self.time_grid.sample_count
        self._t0 = max(0, min(int(t0), n - 1))
        self._t1 = max(self._t0 + 1, min(int(t1), n))
        self._s0 = max(0, min(int(s0), ns - 1))
        self._s1 = max(self._s0 + 1, min(int(s1), ns))
        for spin, value in (
            (self.tstart, self._t0 + 1),
            (self.tend, self._t1),
            (self.sstart, self._s0 + 1),
            (self.send, self._s1),
        ):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        self.render()

    def _spins_window(self) -> None:
        self.set_window(self.tstart.value() - 1, self.tend.value(), self.sstart.value() - 1, self.send.value())

    def _read_aligned_window(self) -> np.ndarray:
        trace_indices = range(self._t0, self._t1)
        traces = [self.reader.read_trace(i, self.index).astype(np.float32, copy=False) for i in trace_indices]
        intervals = self._effective_intervals_us[self._t0:self._t1]
        delays = self.index.delay_time_ms[self._t0:self._t1]
        return align_traces_to_time_grid(
            traces,
            intervals,
            delays,
            self.time_grid,
            self._s0,
            self._s1,
        )

    def _data(self) -> np.ndarray:
        arr = self._read_aligned_window()
        if self.polarity.isChecked():
            arr = -arr
        attribute = str(self.attribute.currentData() or "amplitude")
        if attribute == "amplitude":
            arr = apply_display_gain(
                arr, str(self.gain.currentData()), self.time_grid.interval_ms, self.agc_window.value()
            )
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
        if self.reader is None or self.time_grid is None:
            return
        try:
            data = self._data()
            height = max(300, self.canvas.height() - 58)
            width = max(420, self.canvas.width() - 84)
            image = QImage(width, height, QImage.Format.Format_RGB32)
            image.fill(Qt.GlobalColor.white)
            painter = QPainter(image)
            nt, ns = data.shape
            if nt == 0 or ns == 0:
                painter.end()
                self.canvas.set_image(image, self._t0, self._t1, self._s0, self._s1)
                return
            ycoords = np.linspace(0, height - 1, ns)
            mode = str(self.mode.currentData())
            attribute = str(self.attribute.currentData() or "amplitude")
            # Derived seismic attributes are scalar rasters, not physical wiggle
            # amplitudes. Render them as density even when a wiggle mode is selected.
            if attribute != "amplitude" and mode in {"wiggle", "va"}:
                mode = "color"
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
                    red = np.clip(values, 0, 1) * 255 + (1 - np.abs(values)) * 255
                    blue = np.clip(-values, 0, 1) * 255 + (1 - np.abs(values)) * 255
                    green = (1 - np.abs(values)) * 255
                    rgb[..., 0][valid] = red.astype(np.uint8)
                    rgb[..., 1][valid] = green.astype(np.uint8)
                    rgb[..., 2][valid] = blue.astype(np.uint8)
                raster = QImage(rgb.data, width, height, 3 * width, QImage.Format.Format_RGB888).copy()
                painter.drawImage(0, 0, raster)
            else:
                spacing = width / max(1, nt)
                scale = 0.45 * spacing
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, nt < 350)
                painter.setPen(QPen(Qt.GlobalColor.black, 0 if nt > 450 else 1))
                for i, trace in enumerate(data):
                    valid = np.isfinite(trace)
                    if np.count_nonzero(valid) < 2:
                        continue
                    base = (i + 0.5) * spacing
                    idx = np.flatnonzero(valid)
                    path = QPainterPath(QPointF(base + float(trace[idx[0]]) * scale, float(ycoords[idx[0]])))
                    previous = idx[0]
                    for j in idx[1:]:
                        if j != previous + 1:
                            painter.drawPath(path)
                            path = QPainterPath(QPointF(base + float(trace[j]) * scale, float(ycoords[j])))
                        else:
                            path.lineTo(base + float(trace[j]) * scale, float(ycoords[j]))
                        previous = j
                    painter.drawPath(path)
                    if mode == "va":
                        # Variable-area fill is drawn per contiguous positive segment to avoid
                        # filling across missing samples or negative lobes.
                        positive = valid & (trace >= 0)
                        starts = np.flatnonzero(positive & ~np.r_[False, positive[:-1]])
                        ends = np.flatnonzero(positive & ~np.r_[positive[1:], False])
                        for start, end in zip(starts, ends):
                            if end <= start:
                                continue
                            fill = QPainterPath(QPointF(base, float(ycoords[start])))
                            for j in range(start, end + 1):
                                fill.lineTo(base + float(trace[j]) * scale, float(ycoords[j]))
                            fill.lineTo(base, float(ycoords[end]))
                            fill.closeSubpath()
                            painter.fillPath(fill, QColor(15, 25, 35, 105))
            painter.end()
            self.canvas.set_image(image, self._t0, self._t1, self._s0, self._s1)
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
        if self.reader is None:
            return
        self._selected_trace = int(np.clip(trace_index, 0, self.index.trace_count - 1))
        try:
            header = self.reader.read_trace_header(self._selected_trace, self.index)
            self._set_table(self.trace_header, list(vars(header).items()))
            trace = self.reader.read_trace(self._selected_trace, self.index).astype(np.float64)
            finite = trace[np.isfinite(trace)]
            dt_us = int(self._effective_intervals_us[self._selected_trace])
            dt_s = dt_us * 1e-6
            delay_ms = int(self.index.delay_time_ms[self._selected_trace])
            rms = trace_rms(finite)
            metrics = {
                "Trace index": self._selected_trace + 1,
                "Samples": trace.size,
                "Sample interval": f"{dt_us} µs ({dt_us / 1000:g} ms)",
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
            formatted = []
            for key, value in metrics.items():
                if isinstance(value, (float, np.floating)):
                    formatted.append((key, f"{value:.8g}"))
                else:
                    formatted.append((key, value))
            self._set_table(self.analysis_table, formatted)
            self.analysis_label.setText(
                f"Trace {self._selected_trace + 1} • Field Record {header.field_record} • "
                f"Trace {header.trace_number} • CDP {header.cdp} • Offset {header.offset:,.6g}"
            )
        except Exception as exc:
            self.analysis_label.setText(str(exc))

    def export_image(self) -> None:
        if self.canvas._image.isNull():
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export SEG-Y View",
            str(self.file_path.with_suffix(".png")),
            "PNG (*.png);;JPEG (*.jpg)",
        )
        if path and not self.canvas._image.save(path):
            QMessageBox.warning(self, "Export", "Could not save image")
