from __future__ import annotations

import csv
import hashlib
import re
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


@dataclass
class LogFileSummary:
    path: Path
    category: str
    size: int
    sha256: str
    crc32_text: str
    line_count: int
    number_count: int
    failures: int
    metric: float
    first_number: float | None
    last_number: float | None


class _BaseClassicPlot(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(460, 260)

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

    @staticmethod
    def _grid() -> QColor:
        return QColor(220, 215, 160)

    def _draw_panel_title(self, painter: QPainter, title: str, rect: QRectF, right_text: str = "") -> None:
        painter.setFont(self._font(8, True))
        painter.setPen(QColor(52, 52, 48))
        painter.drawText(QRectF(rect.left(), 4, rect.width(), 18), Qt.AlignCenter, title)
        if right_text:
            painter.setFont(self._font(7, True))
            painter.setPen(QColor(0, 130, 45))
            painter.drawText(QRectF(rect.left(), 4, rect.width() - 6, 18), Qt.AlignRight | Qt.AlignVCenter, right_text)


class _ArealBarWidget(_BaseClassicPlot):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rows: list[tuple[str, float, int]] = []
        self.title = "Phase Error (uS)"
        self.setMinimumSize(460, 150)

    def set_rows(self, rows: list[tuple[str, float, int]], title: str = "Phase Error (uS)") -> None:
        self.rows = rows[:72]
        self.title = title
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.fillRect(self.rect(), self._paper())
        plot = QRectF(68, 24, max(20, self.width() - 116), max(24, self.height() - 52))
        failures = sum(max(0, row[2]) for row in self.rows)
        self._draw_panel_title(painter, self.title, plot, f"Failures: {failures}")
        painter.setPen(QColor(90, 90, 80))
        painter.drawRect(plot)
        if not self.rows:
            painter.setFont(self._font(8))
            painter.setPen(QColor(65, 65, 60))
            painter.drawText(plot, Qt.AlignCenter, "Select a daily SN408/SN428 QC folder")
            return
        max_val = max(abs(value) for _, value, _ in self.rows) or 1.0
        row_h = max(5.0, plot.height() / len(self.rows))
        painter.setFont(self._font(7))
        for index, (name, value, fail) in enumerate(self.rows):
            y = plot.top() + index * row_h + 1
            width = max(3.0, abs(value) / max_val * plot.width())
            color = QColor(0, 225, 28) if fail == 0 else QColor(238, 54, 54)
            painter.fillRect(QRectF(plot.left(), y, width, max(2.0, row_h - 2)), color)
            painter.setPen(QColor(55, 55, 55))
            painter.drawText(4, int(y + row_h - 2), name[:13])
        painter.setFont(self._font(7, True))
        painter.setPen(QColor(0, 120, 40))
        painter.drawText(int(plot.left()), self.height() - 8, f"FDUs/files: {len(self.rows)}")


class _LinePlotWidget(_BaseClassicPlot):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.values = np.array([], dtype=float)
        self.good_low: float | None = None
        self.good_high: float | None = None
        self.title = "Resistance (Ohms)"
        self.footer = ""

    def set_values(self, values: Iterable[float], title: str = "Resistance (Ohms)", footer: str = "") -> None:
        self.values = np.asarray(list(values), dtype=float)
        self.title = title
        self.footer = footer
        finite = self.values[np.isfinite(self.values)]
        if finite.size:
            median = float(np.nanmedian(finite))
            spread = float(np.nanstd(finite) or 1.0)
            self.good_low = median - 2.0 * spread
            self.good_high = median + 2.0 * spread
        else:
            self.good_low = self.good_high = None
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), self._paper())
        plot = QRectF(54, 24, max(20, self.width() - 84), max(20, self.height() - 56))
        painter.fillRect(plot, self._plot_bg())
        painter.setPen(QColor(70, 70, 62))
        painter.drawRect(plot)
        self._draw_panel_title(painter, self.title, plot)
        finite = self.values[np.isfinite(self.values)]
        if finite.size == 0:
            painter.setFont(self._font(8))
            painter.drawText(plot, Qt.AlignCenter, "No numeric line data found")
            return
        vmin = float(np.nanpercentile(finite, 1))
        vmax = float(np.nanpercentile(finite, 99))
        if self.good_low is not None and self.good_high is not None:
            vmin = min(vmin, self.good_low)
            vmax = max(vmax, self.good_high)
        if vmax <= vmin:
            vmax = vmin + 1.0
        painter.setPen(QPen(self._grid(), 1, Qt.DotLine))
        for i in range(1, 10):
            x = plot.left() + i / 10.0 * plot.width()
            y = plot.top() + i / 10.0 * plot.height()
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
        if self.good_low is not None and self.good_high is not None:
            y_hi = plot.bottom() - (self.good_high - vmin) / (vmax - vmin) * plot.height()
            y_lo = plot.bottom() - (self.good_low - vmin) / (vmax - vmin) * plot.height()
            painter.fillRect(QRectF(plot.left(), min(y_hi, y_lo), plot.width(), abs(y_lo - y_hi)), QColor(74, 255, 122, 145))
        painter.setPen(QPen(QColor(0, 62, 214), 1.1))
        step = max(1, self.values.size // max(1, int(plot.width() * 1.15)))
        path = QPainterPath()
        started = False
        for i in range(0, self.values.size, step):
            value = self.values[i]
            if not np.isfinite(value):
                started = False
                continue
            x = plot.left() + i / max(1, self.values.size - 1) * plot.width()
            y = plot.bottom() - (value - vmin) / (vmax - vmin) * plot.height()
            if not started:
                path.moveTo(x, y)
                started = True
            else:
                path.lineTo(x, y)
        painter.drawPath(path)
        painter.setFont(self._font(7))
        painter.setPen(QColor(190, 0, 0))
        painter.drawText(4, int(plot.top() + 5), f"{vmax:.2f}")
        painter.drawText(4, int(plot.bottom()), f"{vmin:.2f}")
        painter.setPen(QColor(20, 60, 180))
        painter.drawText(int(plot.left()), self.height() - 8, self.footer or f"FDUs / samples: {self.values.size}")


class _HistogramGrid(_BaseClassicPlot):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.series: list[tuple[str, np.ndarray]] = []

    def set_series(self, series: list[tuple[str, Iterable[float]]]) -> None:
        self.series = [(name, np.asarray(list(values), dtype=float)) for name, values in series[:4]]
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.fillRect(self.rect(), QColor(255, 246, 178))
        if not self.series:
            painter.setFont(self._font(8))
            painter.setPen(QColor(70, 70, 65))
            painter.drawText(self.rect(), Qt.AlignCenter, "Histograms")
            return
        cell_w = self.width() / 2.0
        cell_h = self.height() / 2.0
        defaults = ["Instrument Noise", "Instrument Distortion", "Instrument Gain Error", "Instrument Phase Error"]
        for index in range(4):
            title = self.series[index][0] if index < len(self.series) else defaults[index]
            values = self.series[index][1] if index < len(self.series) else np.array([], dtype=float)
            rect = QRectF((index % 2) * cell_w + 24, (index // 2) * cell_h + 18, cell_w - 42, cell_h - 38)
            painter.fillRect(rect, QColor(255, 248, 190))
            painter.setPen(QColor(65, 65, 60))
            painter.drawRect(rect)
            painter.setFont(self._font(7, True))
            painter.drawText(QRectF(rect.left(), rect.top() - 13, rect.width(), 12), Qt.AlignCenter, title)
            values = values[np.isfinite(values)]
            if values.size == 0:
                continue
            hist, edges = np.histogram(values, bins=28)
            max_count = int(max(hist) or 1)
            bar_w = rect.width() / len(hist)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 225, 28))
            for i, count in enumerate(hist):
                height = count / max_count * max(1.0, rect.height() - 18)
                painter.drawRect(QRectF(rect.left() + i * bar_w, rect.bottom() - height, max(1.0, bar_w - 1), height))
            mean = float(np.mean(values))
            lo, hi = float(edges[0]), float(edges[-1])
            if hi > lo:
                x = rect.left() + (mean - lo) / (hi - lo) * rect.width()
                painter.setPen(QColor(220, 70, 55))
                painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            painter.setFont(self._font(7, True))
            painter.setPen(QColor(0, 92, 40))
            painter.drawText(int(rect.right() - 72), int(rect.top() + 10), f"In spec: {self._in_spec(values):.1f}%")

    @staticmethod
    def _in_spec(values: np.ndarray) -> float:
        if values.size == 0:
            return 0.0
        median = float(np.nanmedian(values))
        spread = float(np.nanstd(values) or 1.0)
        ok = np.logical_and(values >= median - 2.0 * spread, values <= median + 2.0 * spread)
        return float(np.count_nonzero(ok) / values.size * 100.0)


class _ProductionTimeline(_BaseClassicPlot):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.segments: list[tuple[float, float, QColor]] = []
        self.date_text = ""
        self.setMinimumSize(460, 82)
        self.setMaximumHeight(120)

    def set_stats(self, count: int, failures: int, date_text: str = "") -> None:
        self.date_text = date_text
        self.segments.clear()
        if count > 0:
            failure = min(0.38, max(0.0, failures / max(1, count * 10)))
            self.segments = [
                (0.00, 0.33, QColor(255, 255, 255)),
                (0.33, 0.33 + failure, QColor(238, 20, 20)),
                (0.33 + failure, 0.78, QColor(0, 226, 0)),
                (0.78, 1.00, QColor(255, 255, 255)),
            ]
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.fillRect(self.rect(), QColor(229, 229, 220))
        painter.setFont(self._font(7))
        rect = QRectF(36, 30, max(10, self.width() - 72), 20)
        painter.setPen(QColor(90, 90, 88))
        painter.drawRect(rect)
        for hour in range(25):
            x = rect.left() + hour / 24.0 * rect.width()
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            if hour % 2 == 0:
                painter.drawText(int(x - 10), 20, f"{hour}:00")
        for start, end, color in self.segments:
            painter.fillRect(QRectF(rect.left() + start * rect.width(), rect.top() + 1, (end - start) * rect.width(), rect.height() - 1), color)
        painter.setPen(QColor(0, 80, 180))
        painter.drawText(38, self.height() - 12, f"Date: {self.date_text}" if self.date_text else "Daily production / downtime distribution")


class _MiniStatusBar(QFrame):
    def __init__(self, title: str, value: str = "0", color: str = "#0EA5E9", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("miniStatus")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(7, 5, 7, 5)
        layout.setSpacing(1)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("miniTitle")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("miniValue")
        self.value_label.setStyleSheet(f"color:{color};")
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class SercelLogAnalysisWidget(QWidget):
    """SLX2-style Sercel SN408/SN428 daily recorder QC display."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("module_id", "sercel_log_analysis")
        self.current_dir: Path | None = None
        self.summaries: list[LogFileSummary] = []
        self.numeric_values: list[float] = []
        self.failure_count = 0
        self.category_counts: Counter[str] = Counter()
        self._build_ui()
        self._apply_style()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(5)
        root.addLayout(toolbar)
        button_specs = [
            ("Open Day Folder", "primary", self.open_folder),
            ("Reload", "info", self.reload_folder),
            ("Run QC", "success", self.run_qc),
            ("CRC CSV", "warning", self.export_crc_csv),
            ("Export Image", "purple", self.export_image),
        ]
        for text, kind, slot in button_specs:
            button = QPushButton(text)
            button.setProperty("kind", kind)
            button.clicked.connect(slot)
            toolbar.addWidget(button)
        self.path_label = QLabel("No daily recorder QC folder loaded")
        self.path_label.setObjectName("pathLabel")
        self.path_label.setFrameShape(QFrame.StyledPanel)
        toolbar.addWidget(self.path_label, 1)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        root.addWidget(self.tabs, 1)
        self._build_overview_tab()
        self._build_areal_tab()
        self._build_line_tab()
        self._build_histogram_tab()
        self._build_production_tab()
        self._build_files_tab()
        self._build_logs_tab()

    def _build_overview_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        cards = QHBoxLayout()
        self.card_files = _MiniStatusBar("Files")
        self.card_failures = _MiniStatusBar("Failures", color="#DC2626")
        self.card_numbers = _MiniStatusBar("Numeric values", color="#16A34A")
        self.card_categories = _MiniStatusBar("QC groups", color="#7C3AED")
        for card in [self.card_files, self.card_failures, self.card_numbers, self.card_categories]:
            cards.addWidget(card)
        layout.addLayout(cards)
        splitter = QSplitter(Qt.Horizontal)
        self.overview_stats = QGroupBox("Production results")
        form = QFormLayout(self.overview_stats)
        form.setContentsMargins(7, 11, 7, 7)
        form.setSpacing(2)
        self.date_box = self._ro_line()
        self.first_box = self._ro_line()
        self.last_box = self._ro_line()
        self.down_box = self._ro_line()
        self.true_box = self._ro_line()
        self.vp_box = self._ro_line()
        self.failure_box = self._ro_line()
        self.inst_box = self._ro_line()
        self.sensor_box = self._ro_line()
        self.rsx_box = self._ro_line()
        for label, widget in [
            ("Date", self.date_box),
            ("First Shot", self.first_box),
            ("Last Shot", self.last_box),
            ("Down Time", self.down_box),
            ("True Total Recording Time", self.true_box),
            ("Total VPs", self.vp_box),
            ("Failures", self.failure_box),
            ("Instrument Tests", self.inst_box),
            ("Sensor Tests", self.sensor_box),
            ("R/S/X Files", self.rsx_box),
        ]:
            form.addRow(label, widget)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)
        self.overview_areal = _ArealBarWidget()
        self.overview_timeline = _ProductionTimeline()
        right_layout.addWidget(self.overview_areal, 1)
        right_layout.addWidget(self.overview_timeline, 0)
        splitter.addWidget(self.overview_stats)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        layout.addWidget(splitter, 1)
        self.tabs.addTab(page, "Overview")

    def _build_areal_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(5, 5, 5, 5)
        self.areal = _ArealBarWidget()
        layout.addWidget(self.areal, 1)
        self.tabs.addTab(page, "Areal Display")

    def _build_line_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(5, 5, 5, 5)
        self.line_plot = _LinePlotWidget()
        layout.addWidget(self.line_plot, 1)
        self.tabs.addTab(page, "Line Plots")

    def _build_histogram_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(5, 5, 5, 5)
        self.hist = _HistogramGrid()
        layout.addWidget(self.hist, 1)
        self.tabs.addTab(page, "Histograms")

    def _build_production_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(5, 5, 5, 5)
        self.production_table = QTableWidget(0, 2)
        self.production_table.setHorizontalHeaderLabels(["Item", "Value"])
        self.production_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.production_table.horizontalHeader().setStretchLastSection(True)
        self.timeline = _ProductionTimeline()
        layout.addWidget(self.production_table, 1)
        layout.addWidget(self.timeline, 0)
        self.tabs.addTab(page, "Production Reports")

    def _build_files_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(5, 5, 5, 5)
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(["Category", "File", "Size", "Lines", "Numbers", "Failures", "Metric", "CRC32", "SHA256"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        self.tabs.addTab(page, "Files / CRC")

    def _build_logs_tab(self) -> None:
        page = QWidget()
        layout = QGridLayout(page)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        self.comments = QPlainTextEdit()
        self.comments.setPlaceholderText("Log Comments / Void file(s) / Failures")
        self.file_list = QListWidget()
        layout.addWidget(QLabel("Log Comments"), 0, 0)
        layout.addWidget(QLabel("Void File List"), 0, 1)
        layout.addWidget(self.comments, 1, 0)
        layout.addWidget(self.file_list, 1, 1)
        layout.setColumnStretch(0, 3)
        layout.setColumnStretch(1, 1)
        self.tabs.addTab(page, "Logs / Voids")

    def _ro_line(self) -> QLineEdit:
        widget = QLineEdit()
        widget.setReadOnly(True)
        widget.setMaximumHeight(18)
        return widget

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget { font-size: 8px; }
            QTabWidget::pane { border: 1px solid #A8B0B8; background: #F8FAFC; }
            QTabBar::tab { font-size: 8px; padding: 4px 8px; min-width: 78px; background: #E8EEF5; border: 1px solid #BAC7D3; border-bottom: none; }
            QTabBar::tab:selected { background: #FFFFFF; color: #0F766E; font-weight: 700; }
            QPushButton { font-size: 8px; padding: 3px 8px; min-height: 20px; border-radius: 4px; color: white; font-weight: 700; }
            QPushButton[kind="primary"] { background: #2563EB; }
            QPushButton[kind="info"] { background: #0891B2; }
            QPushButton[kind="success"] { background: #16A34A; }
            QPushButton[kind="warning"] { background: #D97706; }
            QPushButton[kind="purple"] { background: #7C3AED; }
            QLabel { font-size: 8px; }
            QLabel#pathLabel { padding: 3px 6px; background: #FFFFFF; color: #334155; border: 1px solid #CBD5E1; }
            QGroupBox { font-size: 8px; font-weight: 700; margin-top: 8px; border: 1px solid #CBD5E1; border-radius: 5px; background: #FFFFFF; }
            QGroupBox::title { subcontrol-origin: margin; left: 7px; padding: 0 3px; color: #0F766E; }
            QLineEdit, QPlainTextEdit, QTableWidget, QListWidget { font-size: 8px; background: #FFFFFF; selection-background-color: #0EA5E9; }
            QHeaderView::section { font-size: 8px; padding: 3px 4px; background: #E2E8F0; color: #0F172A; font-weight: 700; }
            QFrame#miniStatus { border: 1px solid #CBD5E1; border-radius: 6px; background: #FFFFFF; }
            QLabel#miniTitle { color: #64748B; font-size: 7px; }
            QLabel#miniValue { font-size: 14px; font-weight: 800; }
            """
        )

    def open_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Open Sercel Daily QC Folder", str(Path.home()))
        if folder:
            self.load_folder(folder)

    def reload_folder(self) -> None:
        if self.current_dir:
            self.load_folder(self.current_dir)
        else:
            self.open_folder()

    def load_folder(self, folder: str | Path) -> None:
        root = Path(folder)
        if not root.is_dir():
            QMessageBox.warning(self, "SLX Recorder QC", "Select a folder containing daily recorder QC files.")
            return
        self.current_dir = root
        self.summaries.clear()
        self.numeric_values.clear()
        self.failure_count = 0
        self.category_counts.clear()
        file_rows: list[tuple[str, float, int]] = []
        comments: list[str] = []
        patterns = ["*.txt", "*.log", "*.lst", "*.csv", "*.r", "*.s", "*.x", "*.R", "*.S", "*.X", "*.cog", "*.COG", "*.setup", "*.SETUP", "*.xml", "*.raw", "*.RAW", "*.obs", "*.OBS"]
        files: list[Path] = []
        for pattern in patterns:
            files.extend(root.glob(pattern))
        files = sorted(set(path for path in files if path.is_file()))
        for path in files:
            data = path.read_bytes()
            text = data.decode("utf-8", errors="ignore") if data else ""
            numbers = [float(match) for match in re.findall(r"[-+]?\d+(?:\.\d+)?", text)[:10000]]
            self.numeric_values.extend(numbers)
            category = self._category_for_name(path.name.lower())
            failures = len(re.findall(r"fail|error|void|bad|dead|fault|reject|distortion|noise", text, flags=re.I))
            metric = float(np.nanmedian(numbers)) if numbers else float(len(data))
            summary = LogFileSummary(
                path=path,
                category=category,
                size=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                crc32_text=f"{zlib.crc32(data) & 0xFFFFFFFF:08X}",
                line_count=text.count("\n") + (1 if text else 0),
                number_count=len(numbers),
                failures=failures,
                metric=metric,
                first_number=numbers[0] if numbers else None,
                last_number=numbers[-1] if numbers else None,
            )
            self.summaries.append(summary)
            self.failure_count += failures
            self.category_counts[category] += 1
            file_rows.append((path.stem[:16], metric, failures))
            extracted = self._extract_comments(text, path.name)
            if extracted:
                comments.append(extracted)
        self.path_label.setText(str(root.resolve()))
        self.setProperty("sercel_folder", str(root.resolve()))
        self._populate_table()
        self.comments.setPlainText("\n\n".join(comments).strip())
        self._update_displays(file_rows)

    def _category_for_name(self, name: str) -> str:
        if name.endswith((".r", ".s", ".x")):
            return "R/S/X"
        if "instrument" in name or "inst" in name:
            return "Instrument Tests"
        if "sensor" in name or "geophone" in name:
            return "Sensor Tests"
        if "observer" in name or name.endswith(".obs"):
            return "Observer Log"
        if "raw" in name or "log" in name:
            return "Raw Log"
        if "setup" in name:
            return "Setup"
        if "cog" in name:
            return "COG"
        return "Other QC"

    def _extract_comments(self, text: str, name: str) -> str:
        lines = [line[:240] for line in text.splitlines() if re.search(r"comment|void|fail|error|downtime|down time|bad|fault|reject|dead", line, flags=re.I)]
        return f"[{name}]\n" + "\n".join(lines[:100]) if lines else ""

    def _populate_table(self) -> None:
        self.table.setRowCount(len(self.summaries))
        self.file_list.clear()
        for row, item in enumerate(self.summaries):
            values = [item.category, item.path.name, str(item.size), str(item.line_count), str(item.number_count), str(item.failures), f"{item.metric:.4g}", item.crc32_text, item.sha256[:24]]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if item.failures and col in {0, 1, 5}:
                    cell.setBackground(QColor(255, 220, 220))
                elif item.category in {"Instrument Tests", "Sensor Tests"} and col == 0:
                    cell.setBackground(QColor(220, 255, 225))
                self.table.setItem(row, col, cell)
            if item.failures or re.search(r"void|fail|bad|reject|fault", item.path.name, re.I):
                self.file_list.addItem(QListWidgetItem(item.path.name))

    def _update_displays(self, rows: list[tuple[str, float, int]]) -> None:
        numeric = np.asarray(self.numeric_values, dtype=float)
        finite = numeric[np.isfinite(numeric)]
        date = self._infer_date()
        for widget in (self.areal, self.overview_areal):
            widget.set_rows(rows, "Phase Error (uS)")
        self.line_plot.set_values(finite[:8000] if finite.size else [], "Resistance (Ohms)", f"Samples: {finite.size}  Files: {len(self.summaries)}")
        if finite.size:
            chunks = np.array_split(finite[: min(finite.size, 16000)], 4)
            names = ["Instrument Noise", "Instrument Distortion", "Instrument Gain Error", "Instrument Phase Error"]
            self.hist.set_series(list(zip(names, chunks)))
        else:
            self.hist.set_series([])
        self.timeline.set_stats(len(self.summaries), self.failure_count, date)
        self.overview_timeline.set_stats(len(self.summaries), self.failure_count, date)
        self._update_production_fields(date)
        self._populate_production_table()
        self.card_files.set_value(str(len(self.summaries)))
        self.card_failures.set_value(str(self.failure_count))
        self.card_numbers.set_value(str(finite.size))
        self.card_categories.set_value(str(len(self.category_counts)))

    def _update_production_fields(self, date: str) -> None:
        self.date_box.setText(date)
        self.first_box.setText(self._infer_time(first=True))
        self.last_box.setText(self._infer_time(first=False))
        self.down_box.setText(f"{self.failure_count / 60:.3f} Hours")
        self.true_box.setText(f"{max(0.0, len(self.summaries) * 0.25):.3f} Hours")
        self.vp_box.setText(str(self._estimate_vps()))
        self.failure_box.setText(str(self.failure_count))
        self.inst_box.setText(str(self.category_counts.get("Instrument Tests", 0)))
        self.sensor_box.setText(str(self.category_counts.get("Sensor Tests", 0)))
        self.rsx_box.setText(str(self.category_counts.get("R/S/X", 0)))

    def _populate_production_table(self) -> None:
        rows = [("Date", self.date_box.text()), ("First Shot", self.first_box.text()), ("Last Shot", self.last_box.text()), ("Down Time", self.down_box.text()), ("True Total Recording Time", self.true_box.text()), ("Total VPs", self.vp_box.text()), ("Failures", self.failure_box.text())]
        for category in ["Instrument Tests", "Sensor Tests", "Raw Log", "Observer Log", "R/S/X", "Setup", "COG", "Other QC"]:
            rows.append((category, str(self.category_counts.get(category, 0))))
        self.production_table.setRowCount(len(rows))
        for r, (key, value) in enumerate(rows):
            self.production_table.setItem(r, 0, QTableWidgetItem(key))
            self.production_table.setItem(r, 1, QTableWidgetItem(value))

    def _infer_date(self) -> str:
        if not self.summaries:
            return ""
        names = " ".join(item.path.name for item in self.summaries)
        match = re.search(r"(20\d{2}[-_]?\d{2}[-_]?\d{2}|\d{2}[-_/]\d{2}[-_/]20\d{2})", names)
        if match:
            return match.group(1)
        try:
            return datetime.fromtimestamp(self.summaries[0].path.stat().st_mtime).strftime("%d/%m/%Y")
        except OSError:
            return ""

    def _infer_time(self, first: bool) -> str:
        times: list[str] = []
        for item in self.summaries:
            matches = re.findall(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)(?:[:.]([0-5]\d))?\b", item.path.name)
            for hh, mm, ss in matches:
                times.append(f"{int(hh):02d}:{mm}:{ss or '00'}")
        return sorted(times)[0 if first else -1] if times else ""

    def _estimate_vps(self) -> int:
        names = " ".join(item.path.name for item in self.summaries)
        named_count = len(re.findall(r"\bvp\b|vibrator|source|shot", names, re.I))
        data_count = len(self.numeric_values) // 120 if self.numeric_values else 0
        return max(named_count, data_count)

    def export_crc_csv(self) -> None:
        if not self.summaries:
            QMessageBox.information(self, "SLX Recorder QC", "Load a folder first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export CRC CSV", str(Path.home() / "sercel_file_crc_summary.csv"), "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["category", "file", "size", "lines", "number_count", "failures", "metric", "crc32", "sha256"])
            for item in self.summaries:
                writer.writerow([item.category, item.path.name, item.size, item.line_count, item.number_count, item.failures, item.metric, item.crc32_text, item.sha256])

    def run_qc(self) -> None:
        if not self.summaries:
            QMessageBox.information(self, "SLX Recorder QC", "Open a daily QC folder first.")
            return
        missing = [name for name in ["Instrument Tests", "Sensor Tests", "Raw Log", "Observer Log", "R/S/X", "Setup", "COG"] if self.category_counts.get(name, 0) == 0]
        text = f"Files: {len(self.summaries)}\nFailures/comments flagged: {self.failure_count}"
        if missing:
            text += "\nMissing groups: " + ", ".join(missing)
        QMessageBox.information(self, "SLX Recorder QC", text)

    def export_image(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save Current SLX Tab Image", str(Path.home() / "slx_recorder_qc.png"), "PNG (*.png);;Bitmap (*.bmp)")
        if path:
            self.tabs.currentWidget().grab().save(path)
