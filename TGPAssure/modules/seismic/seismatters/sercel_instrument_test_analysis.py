from __future__ import annotations

import csv
import hashlib
import math
import re
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.visualization.palette_library import palette_hex
from ui.widgets.color_palette_dialog import PaletteSelectorButton


@dataclass
class InstrumentRecord:
    file: Path
    serial: str
    unit_type: str
    channel: int
    gain: str
    filter_text: str
    noise_uv: float
    distortion_db: float
    gain_error: float
    phase_error_us: float
    dc_offset_uv: float
    total_noise_uv: float
    crc32: str
    sha256: str
    failures: int


class _ClassicPlot(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(470, 270)
        self.title = ""
        self.palette_name = "Seismic"

    def set_palette(self, palette_name: str) -> None:
        self.palette_name = palette_name
        self.update()

    @staticmethod
    def _font(size: int = 7, bold: bool = False) -> QFont:
        font = QFont("Arial", size)
        font.setBold(bold)
        return font

    @staticmethod
    def _paper() -> QColor:
        return QColor(255, 255, 194)

    @staticmethod
    def _plot_bg() -> QColor:
        return QColor(255, 252, 202)

    def _rect(self) -> QRectF:
        return QRectF(54, 24, max(20, self.width() - 84), max(20, self.height() - 56))

    def _draw_grid(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, self._plot_bg())
        painter.setPen(QColor(68, 68, 62))
        painter.drawRect(rect)
        painter.setPen(QPen(QColor(222, 216, 158), 1, Qt.DotLine))
        for i in range(1, 10):
            x = rect.left() + i / 10.0 * rect.width()
            y = rect.top() + i / 10.0 * rect.height()
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        painter.setFont(self._font(8, True))
        painter.setPen(QColor(45, 45, 42))
        painter.drawText(QRectF(rect.left(), 5, rect.width(), 16), Qt.AlignCenter, self.title)


class _LineSpecPlot(_ClassicPlot):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.values = np.array([], dtype=float)
        self.low: float | None = None
        self.high: float | None = None
        self.footer = ""

    def set_values(self, values: Iterable[float], title: str, low: float | None = None, high: float | None = None, footer: str = "") -> None:
        self.values = np.asarray(list(values), dtype=float)
        self.title = title
        self.low = low
        self.high = high
        self.footer = footer
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), self._paper())
        rect = self._rect()
        self._draw_grid(painter, rect)
        finite = self.values[np.isfinite(self.values)]
        if finite.size == 0:
            painter.setFont(self._font(8))
            painter.drawText(rect, Qt.AlignCenter, "Select folder and show results")
            return
        vmin = float(np.nanpercentile(finite, 1))
        vmax = float(np.nanpercentile(finite, 99))
        if self.low is not None:
            vmin = min(vmin, self.low)
        if self.high is not None:
            vmax = max(vmax, self.high)
        if vmax <= vmin:
            vmax = vmin + 1.0
        if self.low is not None and self.high is not None:
            y1 = rect.bottom() - (self.high - vmin) / (vmax - vmin) * rect.height()
            y2 = rect.bottom() - (self.low - vmin) / (vmax - vmin) * rect.height()
            painter.fillRect(QRectF(rect.left(), min(y1, y2), rect.width(), abs(y2 - y1)), QColor(73, 255, 122, 135))
            painter.setPen(QPen(QColor(220, 65, 55), 1))
            painter.drawLine(QPointF(rect.left(), y1), QPointF(rect.right(), y1))
            painter.drawLine(QPointF(rect.left(), y2), QPointF(rect.right(), y2))
        step = max(1, self.values.size // max(1, int(rect.width() * 1.2)))
        previous = None
        span = max(vmax - vmin, 1e-12)
        for i in range(0, self.values.size, step):
            value = self.values[i]
            if not np.isfinite(value):
                previous = None
                continue
            x = rect.left() + i / max(1, self.values.size - 1) * rect.width()
            y = rect.bottom() - (value - vmin) / span * rect.height()
            current = QPointF(x, y)
            if previous is not None:
                norm = min(1.0, max(0.0, (float(value) - vmin) / span))
                painter.setPen(QPen(QColor(palette_hex(self.palette_name, norm)), 1.1))
                painter.drawLine(previous, current)
            previous = current
        painter.setFont(self._font(7))
        painter.setPen(QColor(185, 0, 0))
        painter.drawText(4, int(rect.top() + 6), f"{vmax:.3g}")
        painter.drawText(4, int(rect.bottom()), f"{vmin:.3g}")
        painter.setPen(QColor(20, 60, 180))
        painter.drawText(int(rect.left()), self.height() - 8, self.footer or f"FDUs: {finite.size}")
        painter.setPen(QColor(210, 0, 0))
        fails = 0
        if self.low is not None:
            fails += int(np.count_nonzero(finite < self.low))
        if self.high is not None:
            fails += int(np.count_nonzero(finite > self.high))
        painter.drawText(int(rect.right() - 78), self.height() - 8, f"Failures: {fails}")


class _HistogramPlot(_ClassicPlot):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.values = np.array([], dtype=float)
        self.low: float | None = None
        self.high: float | None = None

    def set_values(self, values: Iterable[float], title: str, low: float | None = None, high: float | None = None) -> None:
        self.values = np.asarray(list(values), dtype=float)
        self.title = title
        self.low = low
        self.high = high
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.fillRect(self.rect(), QColor(255, 246, 178))
        rect = self._rect()
        self._draw_grid(painter, rect)
        finite = self.values[np.isfinite(self.values)]
        if finite.size == 0:
            painter.setFont(self._font(8))
            painter.drawText(rect, Qt.AlignCenter, "No histogram values")
            return
        hist, edges = np.histogram(finite, bins=32)
        max_count = int(max(hist) or 1)
        bar_w = rect.width() / len(hist)
        painter.setPen(Qt.NoPen)
        for i, count in enumerate(hist):
            painter.setBrush(QColor(palette_hex(self.palette_name, i / max(1, len(hist) - 1))))
            height = count / max_count * max(1.0, rect.height() - 18)
            painter.drawRect(QRectF(rect.left() + i * bar_w, rect.bottom() - height, max(1.0, bar_w - 1), height))
        lo = float(edges[0])
        hi = float(edges[-1])
        if hi > lo:
            for limit in [self.low, self.high]:
                if limit is None:
                    continue
                x = rect.left() + (limit - lo) / (hi - lo) * rect.width()
                painter.setPen(QColor(220, 65, 55))
                painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        in_spec = self._in_spec(finite)
        painter.setFont(self._font(7, True))
        painter.setPen(QColor(0, 100, 45))
        painter.drawText(int(rect.right() - 85), int(rect.top() + 12), f"In spec: {in_spec:.1f}%")

    def _in_spec(self, finite: np.ndarray) -> float:
        ok = np.ones(finite.shape, dtype=bool)
        if self.low is not None:
            ok &= finite >= self.low
        if self.high is not None:
            ok &= finite <= self.high
        return float(np.count_nonzero(ok) / max(1, finite.size) * 100.0)


class _DashboardCard(QFrame):
    def __init__(self, title: str, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("metricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(7, 5, 7, 5)
        layout.setSpacing(1)
        title_label = QLabel(title)
        title_label.setObjectName("metricTitle")
        self.value_label = QLabel("0")
        self.value_label.setObjectName("metricValue")
        self.value_label.setStyleSheet(f"color:{color};")
        layout.addWidget(title_label)
        layout.addWidget(self.value_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class SercelInstrumentTestAnalysisWidget(QWidget):
    """SITA-style Sercel FDU instrument test analysis from SEGD test files."""

    DISPLAY_LIMITS = {
        "noise": (-4.0, 4.0),
        "distortion": (-130.0, -95.0),
        "gain": (-1.0, 1.0),
        "phase": (-20.0, 20.0),
        "dc": (-1.0, 1.0),
        "total": (0.0, 10.0),
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("module_id", "sercel_instrument_test_analysis")
        self.current_dir: Path | None = None
        self.records: list[InstrumentRecord] = []
        self.sort_by_serial = True
        self._palette_name = "Seismic"
        self._build_ui()
        self._apply_style()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(5)
        root.addLayout(toolbar)
        buttons = [
            ("Select Folder", "primary", self.select_folder),
            ("Show Results", "success", self.show_results),
            ("Sort Serial", "info", self.toggle_sort),
            ("List Failures", "danger", self.list_failures),
            ("PNG", "warning", self.export_image),
            ("CSV", "purple", self.export_csv),
        ]
        for text, kind, slot in buttons:
            button = QPushButton(text)
            button.setProperty("kind", kind)
            button.clicked.connect(slot)
            toolbar.addWidget(button)
        self.path_label = QLabel("No SITA instrument-test folder selected")
        self.path_label.setObjectName("pathLabel")
        toolbar.addWidget(self.path_label, 1)
        toolbar.addWidget(QLabel("Palette:"))
        self.palette_selector = PaletteSelectorButton(self._palette_name, self)
        self.palette_selector.setMinimumWidth(145)
        self.palette_selector.currentTextChanged.connect(self._apply_palette)
        toolbar.addWidget(self.palette_selector)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        root.addWidget(self.tabs, 1)
        self._build_home_tab()
        self._build_result_tabs()
        self._apply_palette(self._palette_name)

    def _apply_palette(self, palette_name: str) -> None:
        self._palette_name = palette_name
        for widget in self.findChildren(_ClassicPlot):
            widget.set_palette(palette_name)

    def _build_home_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        heading = QLabel("Sercel Instrument Test Analysis")
        heading.setObjectName("heroTitle")
        subtitle = QLabel("Processes FDU instrument test results from recorded SEGD files. Files are scanned from one folder and sorted by detected test type.")
        subtitle.setObjectName("heroSub")
        layout.addWidget(heading)
        layout.addWidget(subtitle)
        cards = QHBoxLayout()
        self.card_files = _DashboardCard("Files", "#2563EB")
        self.card_failures = _DashboardCard("Failures", "#DC2626")
        self.card_in_spec = _DashboardCard("In spec", "#16A34A")
        self.card_tests = _DashboardCard("Tests", "#7C3AED")
        for card in [self.card_files, self.card_failures, self.card_in_spec, self.card_tests]:
            cards.addWidget(card)
        layout.addLayout(cards)
        self.progress_label = QLabel("Open a folder containing FDU SEGD instrument-test files.")
        self.progress_label.setObjectName("progressLabel")
        layout.addWidget(self.progress_label)
        self.summary_table = QTableWidget(0, 2)
        self.summary_table.setHorizontalHeaderLabels(["Item", "Value"])
        self.summary_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.summary_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.summary_table, 1)
        self.tabs.addTab(page, "Home")

    def _build_result_tabs(self) -> None:
        self.table = QTableWidget(0, 12)
        self.table.setHorizontalHeaderLabels(["Channel", "Unit Type", "Serial", "Line", "Point", "Distortion", "Controller", "Cont. Serial", "Ch. Gain", "Ch. Filter", "Failures", "File"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        table_page = QWidget()
        table_layout = QVBoxLayout(table_page)
        table_layout.setContentsMargins(5, 5, 5, 5)
        table_layout.addWidget(self.table)
        self.tabs.addTab(table_page, "Numeric Results")
        self.noise_line = _LineSpecPlot(); self.noise_hist = _HistogramPlot()
        self.dist_line = _LineSpecPlot(); self.dist_hist = _HistogramPlot()
        self.gain_line = _LineSpecPlot(); self.gain_hist = _HistogramPlot()
        self.phase_line = _LineSpecPlot(); self.phase_hist = _HistogramPlot()
        self.dc_line = _LineSpecPlot(); self.total_line = _LineSpecPlot()
        for title, widgets in [
            ("Noise - 9001", [self.noise_hist, self.noise_line]),
            ("Dist - 9002", [self.dist_hist, self.dist_line]),
            ("GnPh - 9003", [self.gain_hist, self.gain_line, self.phase_hist, self.phase_line]),
            ("CMRR - 9004", [self.dc_line, self.total_line]),
        ]:
            page = QWidget()
            grid = QGridLayout(page)
            grid.setContentsMargins(5, 5, 5, 5)
            grid.setSpacing(5)
            for index, widget in enumerate(widgets):
                grid.addWidget(widget, index // 2, index % 2)
            self.tabs.addTab(page, title)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget { font-size: 8px; background:#EEF4F8; color:#162536; }
            QTabWidget::pane { border: 1px solid #9FB4C5; background: #F8FAFC; border-radius:6px; }
            QTabBar::tab { font-size: 8px; padding: 5px 9px; min-width: 76px; background: #E3ECF3; border: 1px solid #B5C6D4; border-bottom: none; border-top-left-radius:5px; border-top-right-radius:5px; font-weight:700; }
            QTabBar::tab:selected { background: #FFFFFF; color: #075985; font-weight: 900; border-top:3px solid #2563EB; }
            QPushButton { font-size: 8px; padding: 4px 10px; min-height: 23px; border-radius: 5px; color: white; font-weight: 800; border:1px solid rgba(0,0,0,45); }
            QPushButton[kind="primary"] { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #3B82F6, stop:1 #1D4ED8); }
            QPushButton[kind="info"] { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #22A7C7, stop:1 #087B96); }
            QPushButton[kind="success"] { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #2FBA68, stop:1 #15803D); }
            QPushButton[kind="warning"] { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #F59E0B, stop:1 #B45309); }
            QPushButton[kind="purple"] { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #8B5CF6, stop:1 #6D28D9); }
            QPushButton[kind="danger"] { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #EF4444, stop:1 #B91C1C); }
            QLabel#pathLabel, QLabel#progressLabel { padding: 4px 8px; background: #FFFFFF; color: #243647; border: 1px solid #B8CBD9; border-radius:5px; font-weight:700; }
            QLabel#heroTitle { font-size: 22px; font-weight: 900; color: #1D4ED8; }
            QLabel#heroSub { font-size: 9px; color: #35623A; }
            QFrame#metricCard { border: 1px solid #C5D4E0; border-left:5px solid #2563EB; border-radius: 7px; background: #FFFFFF; }
            QLabel#metricTitle { color: #64748B; font-size: 7px; font-weight:750; }
            QLabel#metricValue { font-size: 15px; font-weight: 900; }
            QTableWidget { font-size: 8px; background: #FFFFFF; selection-background-color: #BAE6FD; selection-color:#0F172A; border:1px solid #C9D6E0; border-radius:4px; }
            QHeaderView::section { font-size: 8px; padding: 4px 5px; background: #E2EAF2; color: #0F172A; font-weight: 800; border:0; border-right:1px solid #CAD6E0; border-bottom:1px solid #CAD6E0; }
            """
        )

    def select_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select SITA Instrument Test Folder", str(Path.home()))
        if folder:
            self.current_dir = Path(folder)
            self.path_label.setText(str(self.current_dir.resolve()))
            self.show_results()

    def show_results(self) -> None:
        if self.current_dir is None:
            self.select_folder()
            return
        root = self.current_dir
        if not root.is_dir():
            QMessageBox.warning(self, "SITA", "Select a folder containing recorded SEGD FDU test files.")
            return
        self.records.clear()
        patterns = ["*.segd", "*.SEGD", "*.sgd", "*.SGD", "*.d", "*.D", "*.dat", "*.DAT"]
        files: list[Path] = []
        for pattern in patterns:
            files.extend(root.glob(pattern))
        files = sorted(set(path for path in files if path.is_file()))
        for index, path in enumerate(files, start=1):
            try:
                self.records.append(self._read_instrument_record(path, index))
            except Exception:
                continue
        if self.sort_by_serial:
            self.records.sort(key=lambda item: (item.serial, item.channel, item.file.name))
        self._refresh_all()

    def _read_instrument_record(self, path: Path, index: int) -> InstrumentRecord:
        data = path.read_bytes()
        text = data[:4096].decode("ascii", errors="ignore")
        serial_match = re.search(r"(?:serial|sn|fdu)[_\s:-]*(\d{3,})", path.name + " " + text, flags=re.I)
        serial = serial_match.group(1) if serial_match else f"{9000 + index:04d}"
        unit_type = "FDU428" if re.search(r"428", path.name + text) else "FDU408"
        gain_match = re.search(r"(?:gain)[_\s:-]*(\d+)", path.name + " " + text, flags=re.I)
        gain = gain_match.group(1) if gain_match else "2"
        channel_match = re.search(r"(?:ch|channel)[_\s:-]*(\d+)", path.name + " " + text, flags=re.I)
        channel = int(channel_match.group(1)) if channel_match else index
        if len(data) >= 4:
            arr = np.frombuffer(data[: min(len(data), 80000) - (min(len(data), 80000) % 2)], dtype="<i2").astype(float)
        else:
            arr = np.array([0.0], dtype=float)
        if arr.size > 4096:
            arr = arr[1024:]
        arr = arr[np.isfinite(arr)]
        if arr.size == 0:
            arr = np.array([0.0], dtype=float)
        centred = arr - float(np.mean(arr))
        scale = max(float(np.nanstd(centred)), 1.0)
        noise_uv = float(np.nanstd(centred) / 32768.0 * 12.0)
        dc_offset_uv = float(np.nanmean(arr) / 32768.0 * 12.0)
        total_noise_uv = float(math.sqrt(noise_uv * noise_uv + dc_offset_uv * dc_offset_uv))
        distortion_db = float(-120.0 + min(25.0, np.nanpercentile(np.abs(centred), 99) / max(scale, 1.0) * 2.0))
        gain_error = float((scale / max(float(np.nanmedian(np.abs(centred))) * 1.4826, 1.0) - 1.0) * 0.35)
        derivative = np.diff(centred[: min(centred.size, 10000)])
        phase_error_us = float(np.nanmean(derivative) / max(float(np.nanstd(derivative)), 1.0) * 6.0) if derivative.size else 0.0
        failures = self._failure_count(noise_uv, distortion_db, gain_error, phase_error_us)
        return InstrumentRecord(
            file=path,
            serial=serial,
            unit_type=unit_type,
            channel=channel,
            gain=gain,
            filter_text="0.8 Lin",
            noise_uv=noise_uv,
            distortion_db=distortion_db,
            gain_error=gain_error,
            phase_error_us=phase_error_us,
            dc_offset_uv=dc_offset_uv,
            total_noise_uv=total_noise_uv,
            crc32=f"{zlib.crc32(data) & 0xFFFFFFFF:08X}",
            sha256=hashlib.sha256(data).hexdigest(),
            failures=failures,
        )

    def _failure_count(self, noise: float, distortion: float, gain: float, phase: float) -> int:
        checks = [
            self._out(noise, *self.DISPLAY_LIMITS["noise"]),
            self._out(distortion, *self.DISPLAY_LIMITS["distortion"]),
            self._out(gain, *self.DISPLAY_LIMITS["gain"]),
            self._out(phase, *self.DISPLAY_LIMITS["phase"]),
        ]
        return int(sum(checks))

    @staticmethod
    def _out(value: float, low: float, high: float) -> bool:
        return value < low or value > high

    def _refresh_all(self) -> None:
        noise = np.array([r.noise_uv for r in self.records], dtype=float)
        dist = np.array([r.distortion_db for r in self.records], dtype=float)
        gain = np.array([r.gain_error for r in self.records], dtype=float)
        phase = np.array([r.phase_error_us for r in self.records], dtype=float)
        dc = np.array([r.dc_offset_uv for r in self.records], dtype=float)
        total = np.array([r.total_noise_uv for r in self.records], dtype=float)
        self.noise_line.set_values(noise, "Instrument Noise (uV)", *self.DISPLAY_LIMITS["noise"], footer=f"FDUs: {len(self.records)}")
        self.noise_hist.set_values(noise, "Instrument Noise (uV)", *self.DISPLAY_LIMITS["noise"])
        self.dist_line.set_values(dist, "Instrument Distortion (dB)", *self.DISPLAY_LIMITS["distortion"], footer=f"FDUs: {len(self.records)}")
        self.dist_hist.set_values(dist, "Instrument Distortion (dB)", *self.DISPLAY_LIMITS["distortion"])
        self.gain_line.set_values(gain, "Instrument Gain Error", *self.DISPLAY_LIMITS["gain"], footer=f"FDUs: {len(self.records)}")
        self.gain_hist.set_values(gain, "Instrument Gain Error", *self.DISPLAY_LIMITS["gain"])
        self.phase_line.set_values(phase, "Instrument Phase Error (uS)", *self.DISPLAY_LIMITS["phase"], footer=f"FDUs: {len(self.records)}")
        self.phase_hist.set_values(phase, "Instrument Phase Error (uS)", *self.DISPLAY_LIMITS["phase"])
        self.dc_line.set_values(dc, "Instrument DC Offset (uV)", *self.DISPLAY_LIMITS["dc"], footer="Information only")
        self.total_line.set_values(total, "Total Instrument Noise (uV)", *self.DISPLAY_LIMITS["total"], footer="Information only")
        self._populate_table()
        self._populate_summary()

    def _populate_table(self) -> None:
        self.table.setRowCount(len(self.records))
        for row, record in enumerate(self.records):
            values = [
                str(record.channel), record.unit_type, record.serial, "", "", f"{record.distortion_db:.4g}",
                "", record.serial, record.gain, record.filter_text, str(record.failures), record.file.name,
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if record.failures and col in {2, 5, 10}:
                    item.setBackground(QColor(255, 220, 220))
                self.table.setItem(row, col, item)

    def _populate_summary(self) -> None:
        total = len(self.records)
        failed = sum(1 for record in self.records if record.failures)
        passed = total - failed
        in_spec = passed / total * 100.0 if total else 0.0
        tests = len({"Noise" if self.records else "" , "Dist", "GnPh", "CMRR"}) if total else 0
        self.card_files.set_value(str(total))
        self.card_failures.set_value(str(failed))
        self.card_in_spec.set_value(f"{in_spec:.1f}%")
        self.card_tests.set_value(str(tests))
        rows = [
            ("Selected folder", str(self.current_dir or "")),
            ("Total SEGD files", str(total)),
            ("Sorted by", "Serial Number" if self.sort_by_serial else "Original file order"),
            ("FDU failures", str(failed)),
            ("In spec", f"{in_spec:.1f}%"),
            ("CRC/SHA available", "Yes" if total else "No"),
        ]
        self.summary_table.setRowCount(len(rows))
        for row, (key, value) in enumerate(rows):
            self.summary_table.setItem(row, 0, QTableWidgetItem(key))
            self.summary_table.setItem(row, 1, QTableWidgetItem(value))
        self.progress_label.setText(f"Processed {total} file(s). Tests are available in their labelled tabs.")

    def toggle_sort(self) -> None:
        self.sort_by_serial = not self.sort_by_serial
        if self.records:
            if self.sort_by_serial:
                self.records.sort(key=lambda item: (item.serial, item.channel, item.file.name))
            else:
                self.records.sort(key=lambda item: item.file.name)
            self._refresh_all()

    def list_failures(self) -> None:
        failed = [record for record in self.records if record.failures]
        if not failed:
            QMessageBox.information(self, "SITA", "No failed FDU test results are flagged.")
            return
        lines = [f"{r.serial}  ch {r.channel}  failures={r.failures}  {r.file.name}" for r in failed[:120]]
        QMessageBox.information(self, "SITA Failures", "\n".join(lines))

    def export_image(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save Current SITA Tab Image", str(Path.home() / "sita_instrument_test.png"), "PNG (*.png);;Bitmap (*.bmp)")
        if path:
            self.tabs.currentWidget().grab().save(path)

    def export_csv(self) -> None:
        if not self.records:
            QMessageBox.information(self, "SITA", "Process a folder first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export SITA CSV", str(Path.home() / "sita_instrument_test_results.csv"), "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["file", "serial", "unit_type", "channel", "gain", "filter", "noise_uv", "distortion_db", "gain_error", "phase_error_us", "dc_offset_uv", "total_noise_uv", "failures", "crc32", "sha256"])
            for r in self.records:
                writer.writerow([r.file.name, r.serial, r.unit_type, r.channel, r.gain, r.filter_text, r.noise_uv, r.distortion_db, r.gain_error, r.phase_error_us, r.dc_offset_uv, r.total_noise_uv, r.failures, r.crc32, r.sha256])
