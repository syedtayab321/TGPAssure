from __future__ import annotations

from pathlib import Path
import traceback
from typing import Any, Callable

import numpy as np
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot, QRectF, QSize
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.data_access.db_engine import DatabaseEngine
from core.data_access.local_file_cache import FileCacheManager, LocalActivityHistory
from core.domain.spatial_visualization import geographic_to_local_xy
from modules.geodetic.dc_reader import DcFileReader
from modules.geodetic.models import FIELD_LABELS, GeodeticDataset, GeodeticMetric, GeodeticQcResult, RECORD_SCHEMAS
from modules.geodetic.qc_engine import GeodeticQcEngine, METRIC_DEFINITIONS, QC_PROFILES
from modules.geodetic.reporting import export_qc_pdf, export_selected_text, export_selected_xlsx
from ui.widgets.full_page_loader import FullPageLoader


_pg_module = None

def _get_pg():
    """Import pyqtgraph only when QC graphs are actually opened.

    The geodetic ribbon tab should appear immediately; loading OpenGL/plotting
    libraries during dashboard construction makes the first click feel frozen.
    """
    global _pg_module
    if _pg_module is None:
        import pyqtgraph as pg
        import pyqtgraph.exporters
        _pg_module = pg
    return _pg_module




class ProfessionalCheckBox(QCheckBox):
    """Compact painted checkbox with a visible tick on light geodetic pages."""

    _accent = QColor("#22AEEA")
    _accent_dark = QColor("#0A86C7")
    _text = QColor("#102A3D")
    _muted = QColor("#8B9BA8")
    _border = QColor("#6F8393")
    _border_disabled = QColor("#C3CED7")
    _white = QColor("#FFFFFF")
    _hover = QColor("#EEF8FD")

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
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
        return QSize(max(58, fm.horizontalAdvance(self.text()) + 28), 22)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return self.sizeHint()

    def paintEvent(self, event):  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        if self.hasFocus():
            painter.setPen(QPen(self._accent_dark, 1, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 4, 4)

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

        painter.setPen(self._text if self.isEnabled() else self._muted)
        font = self.font()
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(QRectF(23, 0, self.width() - 23, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self.text())


_QSS = """
QWidget#geodeticDashboard {
    background: #F3F6FA;
    color: #102A3D;
    font-size: 7.6pt;
}
QWidget#geodeticDashboard QLabel { background: transparent; }
QFrame#geoTopBand {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #09273D, stop:0.55 #0F4868, stop:1 #126C92);
    border: 0;
    border-radius: 7px;
}
QLabel#geoTitle {
    color: #FFFFFF;
    background: transparent;
    font-size: 11px;
    font-weight: 900;
}
QLabel#geoSubtitle {
    color: #C8E5F5;
    background: transparent;
    font-size: 7.2px;
}
QLabel#geoHeaderLabel {
    color: #D8ECF6;
    background: transparent;
    font-size: 7.8px;
    font-weight: 800;
}
QLabel#geoBadge {
    background: #E8F7EF;
    color: #0F6C43;
    border: 1px solid #B8DEC9;
    border-radius: 8px;
    padding: 4px 10px;
    font-size: 7.8px;
    font-weight: 900;
}
QLabel#geoStatusBadge {
    background: rgba(255,255,255,0.14);
    color: #FFFFFF;
    border: 1px solid rgba(255,255,255,0.24);
    border-radius: 8px;
    padding: 4px 10px;
    font-size: 7.8px;
    font-weight: 800;
}
QFrame#geoSideNav {
    background: #FFFFFF;
    border: 1px solid #D3DFE8;
    border-radius: 7px;
}
QLabel#geoNavTitle {
    color: #587287;
    font-size: 7.8px;
    font-weight: 900;
    letter-spacing: .5px;
    padding: 3px 4px 4px 5px;
}
QPushButton#geoNavButton {
    text-align: left;
    min-height: 24px;
    max-height: 26px;
    padding: 2px 7px;
    border: 1px solid transparent;
    border-radius: 5px;
    background: transparent;
    color: #24465D;
    font-size: 7.4pt;
    font-weight: 700;
}
QLabel#geoNavGroup {
    color: #7890A1;
    font-size: 7px;
    font-weight: 900;
    letter-spacing: .5px;
    padding: 5px 5px 1px 5px;
}
QPushButton#geoNavButton:hover {
    background: #EDF5FB;
    border-color: #D2E6F1;
    color: #0A6EA8;
}
QPushButton#geoNavButton:checked {
    background: #22AEEA;
    border-color: #0A86C7;
    color: #FFFFFF;
    font-weight: 900;
}
QPushButton#geoNavButton:checked:hover {
    background: #1A9FD7;
    border-color: #0873AB;
    color: #FFFFFF;
}
QFrame#geoCard, QFrame#geoPanel, QFrame#geoControlBand, QFrame#geoQcBanner, QFrame#geoSummaryTile {
    background: #FFFFFF;
    border: 1px solid #D4DEE8;
    border-radius: 7px;
}
QFrame#geoMetricCard {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #FFFFFF, stop:1 #F5F8FB);
    border: 1px solid #D6E2EA;
    border-left: 3px solid #0A86C7;
    border-radius: 7px;
}
QLabel#geoMetricTitle {
    color: #607587;
    font-size: 7.8px;
    font-weight: 900;
    letter-spacing: .4px;
}
QLabel#geoMetricValue {
    color: #0F3149;
    font-size: 15px;
    font-weight: 900;
}
QLabel#geoMetricHint {
    color: #778897;
    font-size: 7.2px;
}
QLabel#geoSection {
    color: #123047;
    font-size: 10px;
    font-weight: 900;
}
QLabel#geoMicroTitle {
    color: #496171;
    font-size: 7.8px;
    font-weight: 900;
}
QLabel#geoInfoText {
    color: #5D7080;
    font-size: 7.2px;
}
QLabel#geoQcScore {
    color: #0D2B45;
    font-size: 19px;
    font-weight: 900;
}
QLabel#geoPass {
    background: #E7F6EF;
    color: #156B41;
    border: 1px solid #CBEBD9;
    border-radius: 8px;
    padding: 3px 8px;
    font-size: 7.8px;
    font-weight: 900;
}
QLabel#geoWarn {
    background: #FFF6E3;
    color: #8A5A00;
    border: 1px solid #F1DCAB;
    border-radius: 8px;
    padding: 3px 8px;
    font-size: 7.8px;
    font-weight: 900;
}
QLabel#geoFail {
    background: #FCEDED;
    color: #A43B3B;
    border: 1px solid #F0C9C9;
    border-radius: 8px;
    padding: 3px 8px;
    font-size: 7.8px;
    font-weight: 900;
}
QLabel#geoInfo {
    background: #E9F4FB;
    color: #176B93;
    border: 1px solid #C8E4F2;
    border-radius: 8px;
    padding: 3px 8px;
    font-size: 7.8px;
    font-weight: 900;
}
QFrame#geoQcCompactBanner {
    background: #FFFFFF;
    border: 1px solid #D4DEE8;
    border-radius: 7px;
}
QFrame#geoQcTile {
    background: #F8FBFD;
    border: 1px solid #D7E3EC;
    border-radius: 6px;
}
QLabel#geoTileNumber {
    color: #0D2B45;
    font-size: 16px;
    font-weight: 900;
}
QLabel#geoTileCaption {
    color: #607587;
    font-size: 7.4px;
    font-weight: 900;
    letter-spacing: .35px;
}
QTabWidget#geoQcTabs::pane {
    border: 1px solid #D4DEE8;
    background: #FFFFFF;
    top: -1px;
}
QTabWidget#geoQcTabs QTabBar::tab {
    background:#EAF1F6;
    color:#335064;
    border:1px solid #D4DEE8;
    padding:4px 10px;
    min-height:18px;
    font-size:7.8pt;
}
QTabWidget#geoQcTabs QTabBar::tab:selected {
    background:#FFFFFF;
    color:#0A6EA8;
    border-bottom-color:#FFFFFF;
    font-weight:900;
}
QTabWidget#geoGraphTabs::pane {
    border: 1px solid #D4DEE8;
    background: #FFFFFF;
    top: -1px;
}
QTabWidget#geoGraphTabs QTabBar::tab {
    background:#EEF4F8;
    color:#335064;
    border:1px solid #D4DEE8;
    padding:4px 9px;
    min-height:18px;
    font-size:7.8pt;
}
QTabWidget#geoGraphTabs QTabBar::tab:selected {
    background:#FFFFFF;
    color:#0A6EA8;
    border-bottom-color:#FFFFFF;
    font-weight:900;
}
QFrame#geoGraphCard {
    background: #FFFFFF;
    border: 1px solid #D4DEE8;
    border-radius: 6px;
}
QGroupBox {
    font-weight: 800;
    color: #173A52;
    border: 1px solid #D7E0E7;
    border-radius: 6px;
    margin-top: 8px;
    padding-top: 8px;
    background: #FFFFFF;
    font-size: 7.8pt;
}
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
QTabWidget::pane { border: 1px solid #D7E0E7; background: #FFFFFF; top: -1px; }
QTabBar::tab { background:#E9EEF3; color:#455A6C; border:1px solid #D7E0E7; padding:4px 8px; min-width:0; font-size:8.2pt; }
QTabBar::tab:selected { background:#FFFFFF; color:#0B6FA4; border-bottom-color:#FFFFFF; font-weight:800; }
QTableWidget {
    background: #FFFFFF;
    alternate-background-color: #F7FAFC;
    border: 1px solid #DCE5EC;
    gridline-color: #E7EDF2;
    selection-background-color: #D6EBF7;
    selection-color: #0E2E44;
    font-size: 7.8pt;
}
QHeaderView::section {
    background: #E8F0F6;
    color: #29495E;
    border: 0;
    border-bottom: 1px solid #D3DFE8;
    border-right: 1px solid #E1E8EF;
    padding: 3px 4px;
    font-weight: 900;
    font-size: 8.1pt;
}
QPlainTextEdit {
    background: #FFFFFF;
    border: 1px solid #D4DEE8;
    border-radius: 6px;
    color: #173A52;
    font-size: 7.6pt;
}
QPushButton {
    min-height: 21px;
    max-height: 26px;
    padding: 2px 8px;
    font-size: 7.8pt;
    border: 1px solid #B8C7D3;
    border-radius: 5px;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #FFFFFF, stop:1 #EDF3F8);
    color: #102A3D;
    font-weight: 700;
}
QPushButton:hover { border-color: #0A86C7; background: #F2F9FD; }
QPushButton:pressed { background: #DFECF5; }
QPushButton#geoPrimaryButton {
    background: #0A86C7;
    border-color: #0873AB;
    color: #FFFFFF;
    font-weight: 900;
}
QComboBox, QDoubleSpinBox {
    min-height: 21px;
    max-height: 25px;
    font-size: 7.8pt;
    border: 1px solid #C3D0DB;
    border-radius: 5px;
    background: #FFFFFF;
    padding: 1px 6px;
    color: #102A3D;
}

QPushButton#geoOpenButton {
    background: #0A86C7;
    border-color: #0873AB;
    color: #FFFFFF;
    font-weight: 900;
}
QPushButton#geoSuccessButton {
    background: #168A55;
    border-color: #107244;
    color: #FFFFFF;
    font-weight: 900;
}
QPushButton#geoExportButton {
    background: #FFFFFF;
    border-color: #9FB6C7;
    color: #123047;
    font-weight: 800;
}
QCheckBox {
    color: #102A3D;
    font-size: 7.8pt;
    min-height: 18px;
    spacing: 5px;
}
QCheckBox::indicator {
    width: 13px;
    height: 13px;
}
QCheckBox::indicator:unchecked {
    border: 1px solid #8DA3B4;
    border-radius: 3px;
    background: #FFFFFF;
}
QCheckBox::indicator:checked {
    border: 1px solid #0A86C7;
    border-radius: 3px;
    background: #22AEEA;
}
QTabWidget#geoRecordTabs::pane {
    border: 1px solid #D4DEE8;
    background: #FFFFFF;
    top: -1px;
}
QTabWidget#geoRecordTabs QTabBar::tab {
    background:#EAF1F6;
    color:#335064;
    border:1px solid #D4DEE8;
    padding:3px 8px;
    min-height:17px;
    font-size:7.4pt;
}
QTabWidget#geoRecordTabs QTabBar::tab:selected {
    background:#22AEEA;
    color:#FFFFFF;
    border-color:#0A86C7;
    font-weight:900;
}
QFrame#geoSideNav QPushButton#geoNavButton {
    background: transparent;
    color: #24465D;
    text-align: left;
}
QFrame#geoSideNav QPushButton#geoNavButton:checked,
QFrame#geoSideNav QPushButton#geoNavButton[active="true"] {
    background: #22AEEA;
    border: 1px solid #0A86C7;
    color: #FFFFFF;
    font-weight: 900;
}

QScrollArea { border: 0; background: transparent; }
QSplitter::handle { background: #CAD5DE; }
"""

class _MetricGraphCard(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("geoGraphCard")
        self.graph_metric: GeodeticMetric | None = None
        self.limit_line = None
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 8)
        root.setSpacing(5)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        self.title = QLabel("Metric")
        self.title.setObjectName("geoSection")
        title_row.addWidget(self.title, 1)
        self.summary = QLabel("No graph loaded")
        self.summary.setObjectName("geoInfoText")
        self.summary.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        title_row.addWidget(self.summary, 2)
        root.addLayout(title_row)

        controls = QHBoxLayout()
        controls.setSpacing(5)
        controls.addStretch(1)
        for label, spin in (("Y min", self._spin()), ("Limit", self._spin()), ("Y max", self._spin())):
            lbl = QLabel(label)
            lbl.setObjectName("geoInfoText")
            controls.addWidget(lbl)
            controls.addWidget(spin)
            if label == "Y min":
                self.min_spin = spin
            elif label == "Limit":
                self.limit_spin = spin
            else:
                self.max_spin = spin
        self.set_button = QPushButton("Apply range")
        self.set_button.setMaximumWidth(84)
        self.export_button = QPushButton("Export PNG")
        self.export_button.setMaximumWidth(92)
        self.set_button.clicked.connect(self.apply_range)
        self.export_button.clicked.connect(self.export_png)
        controls.addWidget(self.set_button)
        controls.addWidget(self.export_button)
        root.addLayout(controls)

        pg = _get_pg()
        self.plot = pg.PlotWidget(background="w")
        self.plot.showGrid(x=True, y=True, alpha=0.20)
        self.plot.setLabel("bottom", "Observation Number")
        self.plot.setMinimumHeight(330)
        try:
            self.plot.getAxis("left").setWidth(54)
            self.plot.getAxis("left").setStyle(tickFont=QFont("Arial", 8))
            self.plot.getAxis("bottom").setStyle(tickFont=QFont("Arial", 8))
        except Exception:
            pass
        root.addWidget(self.plot, 1)

    @staticmethod
    def _spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setDecimals(5)
        spin.setRange(-1e12, 1e12)
        spin.setKeyboardTracking(False)
        spin.setFixedWidth(78)
        spin.setMaximumHeight(24)
        return spin

    def set_metric(self, metric: GeodeticMetric) -> None:
        self.graph_metric = metric
        self.title.setText(metric.label)
        self.plot.clear()
        values = np.asarray(metric.values, dtype=float)
        finite = np.isfinite(values)
        x = np.arange(1, values.size + 1, dtype=float)
        if np.any(finite):
            finite_values = values[finite]
            pg = _get_pg()
            self.plot.plot(x[finite], finite_values, pen=pg.mkPen("#16823B", width=2.0))
            lo, hi = float(np.min(finite_values)), float(np.max(finite_values))
            med = float(np.median(finite_values))
            span = max(abs(hi - lo), abs(hi) * 0.05, 1e-6)
            self.min_spin.setValue(lo - 0.08 * span)
            self.max_spin.setValue(hi + 0.08 * span)
            self.summary.setText(f"Count {finite_values.size:,}  •  Min {lo:.3g}  •  Median {med:.3g}  •  Max {hi:.3g}")
        else:
            self.min_spin.setValue(0)
            self.max_spin.setValue(1)
            self.summary.setText("No finite values available for this metric")
        if metric.threshold is not None:
            self.limit_spin.setValue(float(metric.threshold))
            self.limit_line = pg.InfiniteLine(
                pos=float(metric.threshold), angle=0,
                pen=_get_pg().mkPen("#C63C32", width=1.2, style=Qt.DashLine),
            )
            self.plot.addItem(self.limit_line)
        else:
            self.limit_line = None
            self.limit_spin.setEnabled(False)
        axis_label = metric.unit or metric.label
        self.plot.setLabel("left", axis_label)
        try:
            self.plot.setTitle(metric.label, color="#123047", size="10pt")
        except Exception:
            pass
        self.apply_range()

    def apply_range(self) -> None:
        lo, hi = self.min_spin.value(), self.max_spin.value()
        if hi > lo:
            self.plot.setYRange(lo, hi, padding=0)
        if self.limit_line is not None:
            self.limit_line.setValue(self.limit_spin.value())

    def export_png(self, target: str | None = None) -> None:
        if self.graph_metric is None:
            return
        if not target:
            path, _ = QFileDialog.getSaveFileName(
                self, "Export QC Graph", f"{self.graph_metric.key}.png",
                "PNG image (*.png);;Bitmap image (*.bmp)",
            )
            if not path:
                return
            target = path
        pg = _get_pg()
        exporter = pg.exporters.ImageExporter(self.plot.plotItem)
        exporter.parameters()["width"] = 1600
        exporter.export(str(target))


class _GeodeticWorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    progress = Signal(int, str)


class _GeodeticRunnable(QRunnable):
    def __init__(self, function: Callable[[Callable[[int, str], None]], Any]) -> None:
        super().__init__()
        self.function = function
        self.signals = _GeodeticWorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.function(self.signals.progress.emit)
            self.signals.result.emit(result)
        except Exception:
            self.signals.error.emit(traceback.format_exc())


class GeodeticDashboard(QWidget):
    state_changed = Signal()
    activity_started = Signal(str, str)
    activity_progress = Signal(int, str)
    activity_finished = Signal()

    MAX_TABLE_PREVIEW_ROWS = 2000
    MAX_TEXT_PREVIEW_LINES = 12000

    TAB_OVERVIEW = 0
    TAB_EXAMINER = 1
    TAB_TEXT_RESULTS = 2
    TAB_QC = 3
    TAB_GRAPHS = 4
    TAB_COORDINATES = 5
    TAB_SPATIAL = 6
    TAB_GEOSPATIAL = 7
    TAB_REPORT = 8

    def __init__(self, db_engine: DatabaseEngine | QWidget | None = None, parent: QWidget | None = None) -> None:
        # Backward compatible constructor: GeodeticDashboard(parent) still works,
        # while GeodeticDashboard(db_engine, parent) enables persisted history.
        if parent is None and isinstance(db_engine, QWidget):
            parent = db_engine
            db_engine = None
        super().__init__(parent)
        self.db_engine = db_engine if isinstance(db_engine, DatabaseEngine) else None
        self.file_cache = FileCacheManager()
        self.local_history = LocalActivityHistory()
        self.setObjectName("geodeticDashboard")
        self.setProperty("module_id", "geodetic")
        self.setStyleSheet(_QSS)
        self.reader = DcFileReader()
        self.dataset: GeodeticDataset | None = None
        self.qc_result: GeodeticQcResult | None = None
        self._field_checks: dict[str, QCheckBox] = {}
        self._graph_cards: list[_MetricGraphCard] = []
        self._graph_pages: list[list[str]] = []
        self._thread_pool = QThreadPool(self)
        self._thread_pool.setMaxThreadCount(1)
        self._active_workers: set[_GeodeticRunnable] = set()
        self._background_busy_count = 0
        self._dataset_summary: dict[str, Any] | None = None
        self._build_ui()
        self._local_loader = FullPageLoader(self)
        self._local_loader.sync_geometry()
        self._refresh_all()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_local_loader"):
            self._sync_local_loader_geometry()

    # --------------------------- background activity ---------------------------
    def _loader_host(self) -> QWidget:
        host = self.window()
        return host if isinstance(host, QWidget) else self

    def _sync_local_loader_geometry(self) -> None:
        if not hasattr(self, "_local_loader"):
            return
        host = self._loader_host()
        if self._local_loader.parentWidget() is not host:
            self._local_loader.setParent(host)
        self._local_loader.sync_geometry()

    def _begin_activity(self, title: str, message: str) -> None:
        title = str(title)
        message = str(message)
        if hasattr(self, "_local_loader"):
            self._sync_local_loader_geometry()
            self._local_loader.show_loader(title, message, 0)
        self.activity_started.emit(title, message)
        QApplication.processEvents()

    def _update_activity(self, progress: int, message: str) -> None:
        value = max(0, min(100, int(progress)))
        message = str(message)
        if hasattr(self, "_local_loader"):
            self._sync_local_loader_geometry()
            self._local_loader.update_loader(value, message)
        self.activity_progress.emit(value, message)
        QApplication.processEvents()

    def _finish_activity(self) -> None:
        if hasattr(self, "_local_loader"):
            self._local_loader.finish()
        self.activity_finished.emit()
        QApplication.processEvents()

    def _run_background(
        self,
        function: Callable[[Callable[[int, str], None]], Any],
        on_result: Callable[[Any], None],
        title: str,
        detail: str,
    ) -> None:
        worker = _GeodeticRunnable(function)
        self._active_workers.add(worker)
        self._background_busy_count += 1
        self._begin_activity(title, detail)
        worker.signals.progress.connect(self._update_activity)
        worker.signals.result.connect(
            lambda result, active_worker=worker: self._background_success(active_worker, on_result, result)
        )
        worker.signals.error.connect(
            lambda text, active_worker=worker: self._background_error(active_worker, title, text)
        )
        self._thread_pool.start(worker)

    def _background_success(
        self,
        worker: _GeodeticRunnable,
        on_result: Callable[[Any], None],
        result: Any,
    ) -> None:
        try:
            on_result(result)
        except Exception as exc:
            self._release_worker(worker)
            QMessageBox.critical(self, "Geodetic/DC Processing Error", str(exc))
            return
        self._release_worker(worker)

    def _background_error(self, worker: _GeodeticRunnable, title: str, traceback_text: str) -> None:
        self._release_worker(worker)
        message = traceback_text.strip().splitlines()[-1] if traceback_text.strip() else "Unknown error"
        QMessageBox.critical(self, title, message)

    def _release_worker(self, worker: _GeodeticRunnable) -> None:
        self._active_workers.discard(worker)
        self._background_busy_count = max(0, self._background_busy_count - 1)
        if self._background_busy_count == 0:
            self._finish_activity()

    # --------------------------- public ribbon actions ---------------------------
    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Geodetic / DC Survey File", "",
            "Survey/DC files (*.dc *.dcf *.txt *.csv *.tsv *.dat);;All files (*.*)",
        )
        if path:
            self.open_path(path)

    def open_path(self, path: str | Path) -> None:
        source = Path(path).expanduser().resolve()

        def load(report: Callable[[int, str], None]) -> tuple[GeodeticDataset, dict[str, Any], bool]:
            report(3, f"Preparing {source.name}")

            def parse() -> tuple[GeodeticDataset, dict[str, Any]]:
                dataset = DcFileReader().read(source)
                report(68, f"Parsed {dataset.record_count:,} geodetic/DC records")
                summary = dataset.summary()
                report(75, "Indexed record families and coordinate coverage")
                return dataset, summary

            (dataset, summary), cache_status = self.file_cache.get_or_compute(
                "geodetic_dc_dataset",
                source,
                parse,
                schema_version="geodetic_dc_dataset_v3",
                progress_callback=report,
            )
            dataset.source_path = source
            dataset.metadata["cache_status"] = "hit" if cache_status.hit else "miss"
            report(90, "Preparing Geodetic workspace from cached data" if cache_status.hit else "Preparing Geodetic workspace")
            return dataset, summary, bool(cache_status.hit)

        self._run_background(
            load,
            lambda payload: self._accept_loaded_dataset(source, payload),
            "Loading Geodetic / DC File",
            f"Reading, parsing and caching {source.name}",
        )

    def _accept_loaded_dataset(
        self, source: Path, payload: tuple[GeodeticDataset, dict[str, Any], bool]
    ) -> None:
        dataset, summary, cache_hit = payload
        self.dataset = dataset
        self._dataset_summary = summary
        self.qc_result = None
        self._update_activity(78, "Preparing DC examiner preview")
        self._refresh_text_preview()
        self._update_activity(84, "Preparing coordinate and equipment tables")
        self._refresh_coordinate_tables()
        self._update_activity(91, "Resetting QC workspace")
        self._refresh_qc()

        # Do not eagerly build OpenGL/Google-map views while a file is opening.
        # Large control files can contain many thousands of observations; these
        # views are rendered on demand when the user opens the corresponding tab.
        if hasattr(self, "native_view"):
            self.native_view.clear("Dataset loaded. Open 2D / 3D Data to render geodetic positions.")
        elif hasattr(self, "native_placeholder_text"):
            self.native_placeholder_text.setText("Dataset loaded. Open 2D / 3D Data to render geodetic positions.")
        if hasattr(self, "geo_view"):
            self.geo_view.clear_tracks()
            self.geo_view.set_status_message("Dataset loaded. Open Satellite / Terrain to render geographic context.")
        elif hasattr(self, "geo_placeholder_text"):
            self.geo_placeholder_text.setText("Dataset loaded. Open Satellite / Terrain to render geographic context.")

        self.badge.setText(f"{dataset.source_path.name} • {dataset.record_count:,} records")
        self.header_status.setText("Dataset loaded — QC not run" + (" • cache hit" if cache_hit else ""))
        self.local_history.record(
            module="geodetic",
            action="open_file",
            file_path=source,
            details={"records": dataset.record_count, "cache_hit": cache_hit, "source_format": dataset.source_format},
        )
        self._refresh_overview()
        self._show_page(self.TAB_OVERVIEW)
        self._update_activity(100, f"{source.name} is ready" + (" from cache" if cache_hit else ""))
        self.state_changed.emit()

    def show_examiner(self) -> None:
        self._show_page(self.TAB_EXAMINER)

    def show_text_results(self) -> None:
        self._show_page(self.TAB_TEXT_RESULTS)
        self._refresh_text_preview()

    def export_text(self) -> None:
        if not self._require_dataset(): return
        path, _ = QFileDialog.getSaveFileName(self, "Export Selected DC Fields", "geodetic_examiner.txt", "Text (*.txt)")
        if path:
            export_selected_text(self.dataset, path, self.selected_fields())

    def export_xlsx(self) -> None:
        if not self._require_dataset(): return
        path, _ = QFileDialog.getSaveFileName(self, "Export Selected DC Fields", "geodetic_examiner.xlsx", "Excel (*.xlsx)")
        if path:
            export_selected_xlsx(self.dataset, path, self.selected_fields())

    def run_qc(self) -> None:
        if not self._require_dataset():
            return
        profile = str(self.profile_combo.currentData() or "project_default")
        overrides = self._threshold_overrides()
        self._begin_activity("Running Geodetic QC", "Evaluating DOP, precision, timing, datum and coordinate checks")
        try:
            self._update_activity(20, "Preparing QC criteria")
            self.qc_result = GeodeticQcEngine(profile, overrides=overrides).run(self.dataset)
            self._update_activity(72, "Refreshing QC tables and graph tabs")
            self._refresh_qc()
            self._show_page(self.TAB_QC)
            self._persist_qc_history(profile, overrides)
            self.local_history.record(
                module="geodetic",
                action="run_qc",
                file_path=self.dataset.source_path,
                details={
                    "profile": profile,
                    "status": self.qc_result.status,
                    "score": round(float(self.qc_result.score), 2),
                    "findings": len(self.qc_result.findings),
                },
            )
            self._update_activity(100, f"Geodetic QC complete — {self.qc_result.status} {self.qc_result.score:.1f}/100")
        finally:
            self._finish_activity()
        self.state_changed.emit()

    def _persist_qc_history(self, profile: str, overrides: dict[str, float]) -> None:
        if self.db_engine is None or self.dataset is None or self.qc_result is None:
            return
        try:
            from core.data_access.qc_history_repository import QcHistoryRepository

            stages = []
            for order, metric in enumerate(self.qc_result.metrics.values(), start=1):
                finite = metric.finite
                metrics = {
                    "count": int(finite.size),
                    "min": float(np.min(finite)) if finite.size else None,
                    "median": float(np.median(finite)) if finite.size else None,
                    "max": float(np.max(finite)) if finite.size else None,
                    "threshold": metric.threshold,
                    "direction": metric.direction,
                    "unit": metric.unit,
                }
                if metric.threshold is None or not finite.size:
                    result = "info"
                elif metric.direction == "min":
                    result = "pass" if float(np.min(finite)) >= float(metric.threshold) else "warn"
                else:
                    result = "pass" if float(np.max(finite)) <= float(metric.threshold) else "warn"
                stages.append({
                    "stage_key": metric.key,
                    "stage_name": metric.label,
                    "stage_order": order,
                    "status": "completed",
                    "result": result,
                    "score": 100.0 if result == "pass" else (75.0 if result == "warn" else None),
                    "metrics": metrics,
                    "message": f"{metric.label} evaluated from C6/DC quality records.",
                })
            findings = []
            for item in self.qc_result.findings:
                findings.append({
                    "stage_key": (item.code or "geodetic").lower(),
                    "finding_code": item.code,
                    "severity": item.severity,
                    "category": "geodetic",
                    "title": item.title,
                    "description": item.message,
                    "observed_value": item.observed,
                    "expected_max": item.limit,
                    "record_id": item.record_id,
                    "line_number": item.line_number,
                    "suggested_action": item.suggested_action,
                    "context": {"record_id": item.record_id, "source_line": item.line_number},
                })
            QcHistoryRepository(self.db_engine).record_run(
                module="geodetic",
                file_path=self.dataset.source_path,
                profile=profile,
                status="completed",
                overall_result=self.qc_result.status.lower(),
                score=float(self.qc_result.score),
                summary={**self.dataset.summary(), "qc_checks": self.qc_result.checks},
                parameters={"threshold_overrides": overrides},
                stages=stages,
                findings=findings,
            )
        except Exception as exc:
            self.dataset.metadata["qc_history_error"] = str(exc)

    def show_qc(self) -> None:
        self._show_page(self.TAB_QC)

    def previous_graph_page(self) -> None:
        self._show_page(self.TAB_GRAPHS)
        target = getattr(self, "graph_tabs", None)
        if target is not None and target.count():
            target.setCurrentIndex((target.currentIndex() - 1) % target.count())
            self._sync_graph_page_label()

    def next_graph_page(self) -> None:
        self._show_page(self.TAB_GRAPHS)
        target = getattr(self, "graph_tabs", None)
        if target is not None and target.count():
            target.setCurrentIndex((target.currentIndex() + 1) % target.count())
            self._sync_graph_page_label()

    def export_graphs(self) -> None:
        if self.qc_result is None:
            self.run_qc()
            if self.qc_result is None: return
        folder = QFileDialog.getExistingDirectory(self, "Export Geodetic QC Graphs")
        if not folder: return
        target = Path(folder)
        for card in self._graph_cards:
            if card.graph_metric is not None:
                card.export_png(str(target / f"geodetic_qc_{card.graph_metric.key}.png"))
        QMessageBox.information(self, "QC Graph Export", f"QC graphs exported to:\n{target}")

    def show_positions(self) -> None:
        self._show_page(self.TAB_COORDINATES); self.coordinate_tabs.setCurrentIndex(0)

    def show_vectors(self) -> None:
        self._show_page(self.TAB_COORDINATES); self.coordinate_tabs.setCurrentIndex(1)

    def show_datum_crs(self) -> None:
        self._show_page(self.TAB_COORDINATES); self.coordinate_tabs.setCurrentIndex(2)

    def show_equipment(self) -> None:
        self._show_page(self.TAB_COORDINATES); self.coordinate_tabs.setCurrentIndex(3)

    def show_native_view(self, mode: str = "2d") -> None:
        if not self._require_dataset():
            return
        self._show_page(self.TAB_SPATIAL)
        self._ensure_native_view()
        if hasattr(self, "native_view"):
            self.native_view.set_mode(mode)
        self._refresh_spatial()

    def show_geospatial_view(self, mode: str = "2d") -> None:
        if not self._require_dataset():
            return
        self._show_page(self.TAB_GEOSPATIAL)
        self._ensure_geo_view()
        if hasattr(self, "geo_view"):
            self.geo_view.set_mode(mode)
        self._refresh_geospatial()

    def generate_report(self) -> None:
        if not self._require_dataset(): return
        if self.qc_result is None:
            self.run_qc()
            if self.qc_result is None: return
        path, _ = QFileDialog.getSaveFileName(self, "Export Geodetic QC Report", "geodetic_qc_report.pdf", "PDF (*.pdf)")
        if path:
            export_qc_pdf(self.dataset, self.qc_result, path)
            self.report_status.setText(f"QC report written to {path}")
            self._show_page(self.TAB_REPORT)

    def can_execute(self, action_id: str) -> bool:
        always = {"geodetic_open", "geodetic_examiner"}
        if action_id in always: return True
        if self.dataset is None: return False
        if action_id in {"geodetic_export_graphs", "geodetic_report_pdf"}: return self.qc_result is not None
        return True

    # ----------------------------------- UI -----------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        top = QFrame(self)
        top.setObjectName("geoTopBand")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(10, 4, 10, 4)
        top_layout.setSpacing(10)
        top.setMaximumHeight(64)

        title_block = QVBoxLayout()
        title_block.setSpacing(1)
        title = QLabel("Geodetic Survey QC & Control")
        title.setObjectName("geoTitle")
        subtitle = QLabel("DC examiner • GNSS precision • datum/CRS audit • native 2D/3D • satellite/terrain context")
        subtitle.setObjectName("geoSubtitle")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        command_row = QHBoxLayout()
        command_row.setSpacing(6)
        label = QLabel("Profile")
        label.setObjectName("geoHeaderLabel")
        command_row.addWidget(label)
        self.profile_combo = QComboBox()
        for key, profile in QC_PROFILES.items():
            self.profile_combo.addItem(profile.label, key)
        self.profile_combo.currentIndexChanged.connect(self._populate_threshold_table)
        self.profile_combo.setFixedWidth(220)
        command_row.addWidget(self.profile_combo)
        open_button = QPushButton("Open Data")
        open_button.setObjectName("geoOpenButton")
        open_button.clicked.connect(self.open_file)
        command_row.addWidget(open_button)
        run_button = QPushButton("Run QC")
        run_button.setObjectName("geoPrimaryButton")
        run_button.clicked.connect(self.run_qc)
        command_row.addWidget(run_button)
        command_row.addStretch(1)
        title_block.addLayout(command_row)
        top_layout.addLayout(title_block, 1)

        self.badge = QLabel("No file loaded")
        self.badge.setObjectName("geoBadge")
        self.badge.setMinimumWidth(230)
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setStyleSheet("background:#FFFFFF;color:#0B5F41;border:1px solid #BFE8D0;border-radius:8px;padding:4px 10px;font-weight:900;")
        top_layout.addWidget(self.badge)
        self.header_status = QLabel("QC not run")
        self.header_status.setObjectName("geoStatusBadge")
        self.header_status.setMinimumWidth(180)
        self.header_status.setAlignment(Qt.AlignCenter)
        self.header_status.setStyleSheet("background:rgba(255,255,255,0.18);color:#FFFFFF;border:1px solid rgba(255,255,255,0.30);border-radius:8px;padding:4px 10px;font-weight:900;")
        top_layout.addWidget(self.header_status)
        root.addWidget(top)

        body = QHBoxLayout()
        body.setSpacing(6)
        self.nav_frame = QFrame(self)
        self.nav_frame.setObjectName("geoSideNav")
        self.nav_frame.setFixedWidth(174)
        nav_outer = QVBoxLayout(self.nav_frame)
        nav_outer.setContentsMargins(5, 6, 5, 6)
        nav_outer.setSpacing(3)
        nav_title = QLabel("WORKSPACE")
        nav_title.setObjectName("geoNavTitle")
        nav_outer.addWidget(nav_title)

        nav_scroll = QScrollArea(self.nav_frame)
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QFrame.Shape.NoFrame)
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        nav_host = QWidget()
        nav_host.setStyleSheet("background: transparent;")
        nav_layout = QVBoxLayout(nav_host)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(3)
        self._nav_buttons: list[QPushButton] = []
        nav_items = (
            ("DATA", None, None),
            (None, self.TAB_OVERVIEW, "Overview"),
            (None, self.TAB_EXAMINER, "Field Selection"),
            (None, self.TAB_TEXT_RESULTS, "Text Results"),
            ("QUALITY", None, None),
            (None, self.TAB_QC, "QC Results"),
            (None, self.TAB_GRAPHS, "QC Graphs"),
            ("CONTROL", None, None),
            (None, self.TAB_COORDINATES, "Coordinates / Datum"),
            ("VIEW", None, None),
            (None, self.TAB_SPATIAL, "2D / 3D Data"),
            (None, self.TAB_GEOSPATIAL, "Satellite / Terrain"),
            ("OUTPUT", None, None),
            (None, self.TAB_REPORT, "Reports / Export"),
        )
        for group, index, label_text in nav_items:
            if group is not None:
                group_label = QLabel(group)
                group_label.setObjectName("geoNavGroup")
                nav_layout.addWidget(group_label)
                continue
            button = QPushButton(str(label_text))
            button.setObjectName("geoNavButton")
            button.setCheckable(True)
            button.setToolTip(str(label_text))
            button.setMinimumWidth(0)
            button.setMaximumHeight(24)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._apply_nav_button_style(button, False)
            button.clicked.connect(lambda _checked=False, page=int(index): self._show_page(page))
            nav_layout.addWidget(button)
            self._nav_buttons.append(button)
        nav_layout.addStretch(1)
        nav_scroll.setWidget(nav_host)
        nav_outer.addWidget(nav_scroll, 1)
        body.addWidget(self.nav_frame)

        self.tabs = QStackedWidget(self)
        self.tabs.currentChanged.connect(self._page_changed)
        self.tabs.addWidget(self._build_overview_tab())
        self.tabs.addWidget(self._build_examiner_tab())
        self.tabs.addWidget(self._build_text_results_tab())
        self.tabs.addWidget(self._build_qc_tab())
        self.tabs.addWidget(self._build_graphs_tab())
        self.tabs.addWidget(self._build_coordinates_tab())
        self.tabs.addWidget(self._build_spatial_tab())
        self.tabs.addWidget(self._build_geospatial_tab())
        self.tabs.addWidget(self._build_report_tab())
        body.addWidget(self.tabs, 1)
        root.addLayout(body, 1)
        self._sync_nav_buttons(0)

    def _show_page(self, index: int) -> None:
        if not hasattr(self, "tabs"):
            return
        index = max(0, min(int(index), self.tabs.count() - 1))
        if self.tabs.currentIndex() != index:
            self.tabs.setCurrentIndex(index)
        else:
            self._page_changed(index)

    def _page_changed(self, index: int) -> None:
        self._sync_nav_buttons(index)
        if index == self.TAB_OVERVIEW:
            self._refresh_overview()
        elif index == self.TAB_TEXT_RESULTS:
            self._refresh_text_preview()
        elif index == self.TAB_GRAPHS:
            self._sync_graph_page_label()
        elif index == self.TAB_SPATIAL:
            self._refresh_spatial()
        elif index == self.TAB_GEOSPATIAL:
            self._refresh_geospatial()

    def _apply_nav_button_style(self, button: QPushButton, active: bool) -> None:
        """Force the side navigation contrast regardless of application-level QSS."""
        button.setProperty("active", "true" if active else "false")
        if active:
            button.setStyleSheet(
                "QPushButton {"
                "background:#22AEEA; color:#FFFFFF; border:1px solid #0A86C7;"
                "border-radius:5px; padding:2px 7px; text-align:left;"
                "font-size:7.4pt; font-weight:900; min-height:22px; max-height:24px;"
                "}"
                "QPushButton:hover { background:#1A9FD7; color:#FFFFFF; border-color:#0873AB; }"
            )
        else:
            button.setStyleSheet(
                "QPushButton {"
                "background:transparent; color:#24465D; border:1px solid transparent;"
                "border-radius:5px; padding:2px 7px; text-align:left;"
                "font-size:7.4pt; font-weight:700; min-height:22px; max-height:24px;"
                "}"
                "QPushButton:hover { background:#EDF5FB; color:#0A6EA8; border-color:#D2E6F1; }"
            )
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    def _sync_nav_buttons(self, index: int) -> None:
        for button_index, button in enumerate(getattr(self, "_nav_buttons", [])):
            active = button_index == index
            button.blockSignals(True)
            button.setChecked(active)
            button.blockSignals(False)
            self._apply_nav_button_style(button, active)

    def _metric_card(self, title: str, value: str = "—", hint: str = "") -> tuple[QFrame, QLabel, QLabel]:
        card = QFrame(self)
        card.setObjectName("geoMetricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(9, 7, 9, 7)
        layout.setSpacing(2)
        label = QLabel(title.upper())
        label.setObjectName("geoMetricTitle")
        value_label = QLabel(value)
        value_label.setObjectName("geoMetricValue")
        hint_label = QLabel(hint)
        hint_label.setObjectName("geoMetricHint")
        hint_label.setWordWrap(True)
        layout.addWidget(label)
        layout.addWidget(value_label)
        layout.addWidget(hint_label)
        return card, value_label, hint_label

    def _build_overview_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        card_row = QGridLayout()
        card_row.setSpacing(6)
        self.overview_cards: dict[str, tuple[QLabel, QLabel]] = {}
        for col, (key, title, hint) in enumerate((
            ("records", "Records", "parsed DC/table records"),
            ("positions", "Positions", "valid WGS84/local points"),
            ("qc", "QC Score", "run QC to evaluate"),
            ("format", "Format", "detected source type"),
        )):
            card, value, hint_label = self._metric_card(title, "—", hint)
            self.overview_cards[key] = (value, hint_label)
            card_row.addWidget(card, 0, col)
        layout.addLayout(card_row)

        splitter = QSplitter(Qt.Horizontal)
        left = QFrame()
        left.setObjectName("geoPanel")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(5)
        heading = QLabel("Dataset & Coordinate Coverage")
        heading.setObjectName("geoSection")
        left_layout.addWidget(heading)
        self.overview_table = self._table(["Parameter", "Value"])
        self.overview_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        left_layout.addWidget(self.overview_table, 1)
        splitter.addWidget(left)

        right = QFrame()
        right.setObjectName("geoPanel")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(5)
        heading2 = QLabel("Readiness Workflow")
        heading2.setObjectName("geoSection")
        right_layout.addWidget(heading2)
        self.workflow_table = self._table(["Step", "Status", "Purpose"])
        self.workflow_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        right_layout.addWidget(self.workflow_table, 1)
        splitter.addWidget(right)
        splitter.setSizes([620, 760])
        layout.addWidget(splitter, 1)
        return widget

    def _build_examiner_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        action_bar = QFrame()
        action_bar.setObjectName("geoControlBand")
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(7, 5, 7, 5)
        action_layout.setSpacing(6)

        open_btn = QPushButton("Open Data")
        open_btn.setObjectName("geoOpenButton")
        open_btn.clicked.connect(self.open_file)
        action_layout.addWidget(open_btn)

        action_layout.addWidget(QLabel("Export:"))
        self.output_text_check = ProfessionalCheckBox("Text")
        self.output_text_check.setChecked(True)
        self.output_xls_check = ProfessionalCheckBox("XLSX")
        self.output_xls_check.setChecked(True)
        self.select_all_fields_check = ProfessionalCheckBox("All fields")
        self.select_all_fields_check.setChecked(True)
        self.select_all_fields_check.setToolTip("Tick/untick every examiner field checkbox on this page.")
        self.select_all_fields_check.toggled.connect(self._set_all_field_checks)
        action_layout.addWidget(self.output_text_check)
        action_layout.addWidget(self.output_xls_check)
        action_layout.addWidget(self.select_all_fields_check)

        text_btn = QPushButton("Text Results")
        text_btn.setObjectName("geoExportButton")
        text_btn.clicked.connect(self.show_text_results)
        action_layout.addWidget(text_btn)

        graphs_btn = QPushButton("QC Graphs")
        graphs_btn.setObjectName("geoExportButton")
        graphs_btn.clicked.connect(lambda: (self.run_qc() if self.qc_result is None and self.dataset is not None else self._show_page(self.TAB_GRAPHS)))
        action_layout.addWidget(graphs_btn)
        action_layout.addStretch(1)
        layout.addWidget(action_bar)

        intro = QLabel("All selectable DC examiner fields are now on this single page. Use the section All/None buttons to control a record family without changing the rest of the page.")
        intro.setObjectName("geoInfoText")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        host = QWidget()
        host_layout = QVBoxLayout(host)
        host_layout.setContentsMargins(0, 0, 4, 0)
        host_layout.setSpacing(7)

        for schema in RECORD_SCHEMAS:
            section = QFrame()
            section.setObjectName("geoPanel")
            section_layout = QVBoxLayout(section)
            section_layout.setContentsMargins(7, 6, 7, 7)
            section_layout.setSpacing(5)

            header_layout = QHBoxLayout()
            header_layout.setContentsMargins(0, 0, 0, 0)
            header_layout.setSpacing(6)
            title = QLabel(f"Record ID {' / '.join(schema.record_ids)} — {schema.title}")
            title.setObjectName("geoSection")
            header_layout.addWidget(title, 1)
            all_btn = QPushButton("All")
            none_btn = QPushButton("None")
            all_btn.setObjectName("geoSuccessButton")
            none_btn.setObjectName("geoExportButton")
            all_btn.setFixedWidth(44)
            none_btn.setFixedWidth(52)
            header_layout.addWidget(all_btn)
            header_layout.addWidget(none_btn)
            section_layout.addLayout(header_layout)

            fields_grid = QGridLayout()
            fields_grid.setContentsMargins(0, 0, 0, 0)
            fields_grid.setHorizontalSpacing(7)
            fields_grid.setVerticalSpacing(4)
            checks: list[ProfessionalCheckBox] = []
            columns = 4 if len(schema.fields) >= 8 else 3
            for field_index, (key, label) in enumerate(schema.fields):
                cell = QFrame()
                cell.setObjectName("geoQcTile")
                cell_layout = QHBoxLayout(cell)
                cell_layout.setContentsMargins(6, 3, 6, 3)
                cell_layout.setSpacing(4)
                check = ProfessionalCheckBox(label)
                check.setChecked(True)
                check.setToolTip(f"{key} • Record {', '.join(schema.record_ids)}")
                self._field_checks[key] = check
                checks.append(check)
                check.toggled.connect(self._refresh_text_preview)
                cell_layout.addWidget(check, 1)
                fields_grid.addWidget(cell, field_index // columns, field_index % columns)
            for column in range(columns):
                fields_grid.setColumnStretch(column, 1)
            section_layout.addLayout(fields_grid)

            all_btn.clicked.connect(lambda _=False, items=checks: [item.setChecked(True) for item in items])
            none_btn.clicked.connect(lambda _=False, items=checks: [item.setChecked(False) for item in items])
            host_layout.addWidget(section)

        host_layout.addStretch(1)
        scroll.setWidget(host)
        layout.addWidget(scroll, 1)
        return widget

    def _set_all_field_checks(self, checked: bool) -> None:
        for check in getattr(self, "_field_checks", {}).values():
            check.blockSignals(True)
            check.setChecked(bool(checked))
            check.blockSignals(False)
        self._refresh_text_preview()

    def _build_text_results_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(5)
        top_row = QHBoxLayout()
        self.examiner_summary = QLabel("Open a DC/survey export to inspect records.")
        self.examiner_summary.setObjectName("geoInfoText")
        self.examiner_summary.setWordWrap(True)
        top_row.addWidget(self.examiner_summary, 1)
        fields_btn = QPushButton("Field Selection")
        fields_btn.clicked.connect(lambda: self._show_page(self.TAB_EXAMINER))
        top_row.addWidget(fields_btn)
        export_text_btn = QPushButton("Export Text")
        export_text_btn.clicked.connect(self.export_text)
        top_row.addWidget(export_text_btn)
        export_xlsx_btn = QPushButton("Export XLSX")
        export_xlsx_btn.clicked.connect(self.export_xlsx)
        top_row.addWidget(export_xlsx_btn)
        layout.addLayout(top_row)
        self.text_preview = QPlainTextEdit()
        self.text_preview.setReadOnly(True)
        layout.addWidget(self.text_preview, 1)
        return widget

    def _build_qc_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        banner = QFrame()
        banner.setObjectName("geoQcCompactBanner")
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(8, 5, 8, 5)
        banner_layout.setSpacing(7)

        def add_tile(caption: str, value: str, object_name: str = "") -> QLabel:
            tile = QFrame()
            tile.setObjectName("geoQcTile")
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(8, 4, 8, 4)
            tile_layout.setSpacing(1)
            cap = QLabel(caption.upper())
            cap.setObjectName("geoTileCaption")
            val = QLabel(value)
            val.setObjectName(object_name or "geoTileNumber")
            val.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            tile_layout.addWidget(cap)
            tile_layout.addWidget(val)
            banner_layout.addWidget(tile)
            return val

        self.qc_score_value = add_tile("Overall score", "—/100", "geoQcScore")
        status_tile = QFrame()
        status_tile.setObjectName("geoQcTile")
        status_layout = QVBoxLayout(status_tile)
        status_layout.setContentsMargins(8, 4, 8, 4)
        status_layout.setSpacing(2)
        status_title = QLabel("STATUS")
        status_title.setObjectName("geoTileCaption")
        self.qc_badge = QLabel("QC not run")
        self.qc_badge.setObjectName("geoInfo")
        self.qc_badge.setAlignment(Qt.AlignCenter)
        status_layout.addWidget(status_title)
        status_layout.addWidget(self.qc_badge)
        banner_layout.addWidget(status_tile, 1)
        self.qc_fail_tile = add_tile("Fail", "0", "geoFail")
        self.qc_warn_tile = add_tile("Warn", "0", "geoWarn")
        self.qc_info_tile = add_tile("Info", "0", "geoInfo")
        run = QPushButton("Run QC")
        run.setObjectName("geoPrimaryButton")
        run.clicked.connect(self.run_qc)
        banner_layout.addWidget(run)
        graphs = QPushButton("Open Graphs")
        graphs.clicked.connect(lambda: self._show_page(self.TAB_GRAPHS))
        banner_layout.addWidget(graphs)
        layout.addWidget(banner)

        self.qc_note = QLabel("Criteria, metric results, findings and audit details are separated below. Graphs have a dedicated full-size workspace.")
        self.qc_note.setObjectName("geoInfoText")
        self.qc_note.setWordWrap(True)
        layout.addWidget(self.qc_note)

        self.qc_score_bar = QProgressBar()
        self.qc_score_bar.setRange(0, 100)
        self.qc_score_bar.setValue(0)
        self.qc_score_bar.setTextVisible(False)
        self.qc_score_bar.setMaximumHeight(7)
        layout.addWidget(self.qc_score_bar)

        qc_tabs = QTabWidget()
        qc_tabs.setObjectName("geoQcTabs")
        layout.addWidget(qc_tabs, 1)

        summary_page = QWidget()
        summary_layout = QVBoxLayout(summary_page)
        summary_layout.setContentsMargins(6, 6, 6, 6)
        self.qc_stage_table = self._table(["Metric", "Count", "Median", "Max / Min", "Limit", "Result"])
        self.qc_stage_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, 6):
            self.qc_stage_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeToContents)
        summary_layout.addWidget(self.qc_stage_table, 1)
        qc_tabs.addTab(summary_page, "Metric Summary")

        findings_page = QWidget()
        findings_layout = QVBoxLayout(findings_page)
        findings_layout.setContentsMargins(6, 6, 6, 6)
        self.findings_table = self._table(["Severity", "Code", "Finding", "Evidence", "Recommended action"])
        self.findings_table.setWordWrap(True)
        header = self.findings_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        for column in (2, 3, 4):
            header.setSectionResizeMode(column, QHeaderView.Stretch)
        findings_layout.addWidget(self.findings_table, 1)
        qc_tabs.addTab(findings_page, "Findings / Actions")

        criteria_page = QWidget()
        criteria_layout = QVBoxLayout(criteria_page)
        criteria_layout.setContentsMargins(6, 6, 6, 6)
        criteria_help = QLabel("Editable acceptance criteria. Change limits here, then run QC again.")
        criteria_help.setObjectName("geoInfoText")
        criteria_help.setWordWrap(True)
        criteria_layout.addWidget(criteria_help)
        self.threshold_table = self._table(["Metric", "Criterion", "Limit", "Unit"])
        self.threshold_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, 4):
            self.threshold_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeToContents)
        criteria_layout.addWidget(self.threshold_table, 1)
        qc_tabs.addTab(criteria_page, "QC Criteria")

        checks_page = QWidget()
        checks_layout = QVBoxLayout(checks_page)
        checks_layout.setContentsMargins(6, 6, 6, 6)
        self.qc_checks_table = self._table(["Check", "Value"])
        self.qc_checks_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.qc_checks_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        checks_layout.addWidget(self.qc_checks_table, 1)
        qc_tabs.addTab(checks_page, "Audit Details")

        self._populate_threshold_table()
        return widget

    def _build_graphs_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(5)
        toolbar = QFrame()
        toolbar.setObjectName("geoControlBand")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(7, 5, 7, 5)
        title = QLabel("Geodetic QC Graphs")
        title.setObjectName("geoSection")
        toolbar_layout.addWidget(title)
        self.graph_page_label = QLabel("No QC graphs loaded")
        self.graph_page_label.setObjectName("geoInfoText")
        toolbar_layout.addWidget(self.graph_page_label, 1)
        previous = QPushButton("Previous")
        previous.clicked.connect(self.previous_graph_page)
        toolbar_layout.addWidget(previous)
        next_button = QPushButton("Next")
        next_button.clicked.connect(self.next_graph_page)
        toolbar_layout.addWidget(next_button)
        export = QPushButton("Export All Graphs")
        export.clicked.connect(self.export_graphs)
        toolbar_layout.addWidget(export)
        layout.addWidget(toolbar)
        self.graph_tabs = QTabWidget()
        self.graph_tabs.setObjectName("geoGraphTabs")
        self.graph_tabs.setDocumentMode(True)
        self.graph_tabs.currentChanged.connect(lambda _index: self._sync_graph_page_label())
        layout.addWidget(self.graph_tabs, 1)
        return widget

    def _build_coordinates_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.coordinate_tabs = QTabWidget()
        layout.addWidget(self.coordinate_tabs)
        self.position_table = self._table(["Point", "Latitude", "Longitude", "Northing / Y", "Easting / X", "Height", "H Precision", "V Precision", "Method", "Class"])
        self.position_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.position_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.position_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.position_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.position_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.position_table.horizontalHeader().setSectionResizeMode(9, QHeaderView.Stretch)
        self.coordinate_tabs.addTab(self.position_table, "Positions")
        self.vector_table = self._table(["Point", "ΔX", "ΔY", "ΔZ", "3D Length", "H Precision", "V Precision"])
        self.coordinate_tabs.addTab(self.vector_table, "Vectors")
        self.datum_table = self._table(["Record", "Field", "Value"])
        self.datum_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.coordinate_tabs.addTab(self.datum_table, "Datum / CRS")
        self.equipment_table = self._table(["Field", "Value"])
        self.equipment_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.coordinate_tabs.addTab(self.equipment_table, "Equipment")
        return widget

    def _build_lazy_view_placeholder(self, title_text: str, message: str, button_text: str, callback: Callable[[], None]) -> QFrame:
        card = QFrame()
        card.setObjectName("geoPanel")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(8)
        title = QLabel(title_text)
        title.setObjectName("geoSection")
        title.setAlignment(Qt.AlignCenter)
        text = QLabel(message)
        text.setObjectName("geoInfoText")
        text.setWordWrap(True)
        text.setAlignment(Qt.AlignCenter)
        button = QPushButton(button_text)
        button.setObjectName("geoOpenButton")
        button.setFixedWidth(150)
        button.clicked.connect(callback)
        layout.addStretch(1)
        layout.addWidget(title)
        layout.addWidget(text)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)
        if "2D / 3D" in title_text:
            self.native_placeholder_text = text
        else:
            self.geo_placeholder_text = text
        return card

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _build_spatial_tab(self) -> QWidget:
        widget = QWidget()
        self.native_view_layout = QVBoxLayout(widget)
        self.native_view_layout.setContentsMargins(0, 0, 0, 0)
        self.native_view_layout.addWidget(
            self._build_lazy_view_placeholder(
                "Native 2D / 3D Data",
                "The 2D/3D graphics engine is loaded only when this page is opened. This keeps the Geodetic dashboard fast from the ribbon.",
                "Load 2D / 3D View",
                lambda: (self._ensure_native_view(), self._refresh_spatial()),
            )
        )
        return widget

    def _build_geospatial_tab(self) -> QWidget:
        widget = QWidget()
        self.geo_view_layout = QVBoxLayout(widget)
        self.geo_view_layout.setContentsMargins(0, 0, 0, 0)
        self.geo_view_layout.addWidget(
            self._build_lazy_view_placeholder(
                "Satellite / Terrain Context",
                "The web-map and terrain view are loaded only when this page is opened. This avoids slow dashboard startup.",
                "Load Map View",
                lambda: (self._ensure_geo_view(), self._refresh_geospatial()),
            )
        )
        return widget

    def _ensure_native_view(self) -> None:
        if hasattr(self, "native_view"):
            return
        if not hasattr(self, "native_view_layout"):
            return
        try:
            from ui.widgets.scientific_spatial_view import ScientificSpatialView

            view = ScientificSpatialView(title="Geodetic Native 2D / 3D Position View")
        except Exception as exc:
            if hasattr(self, "native_placeholder_text"):
                self.native_placeholder_text.setText(f"2D/3D view could not be initialized: {exc}")
            return
        self._clear_layout(self.native_view_layout)
        self.native_view = view
        self.native_view_layout.addWidget(self.native_view)

    def _ensure_geo_view(self) -> None:
        if hasattr(self, "geo_view"):
            return
        if not hasattr(self, "geo_view_layout"):
            return
        try:
            from ui.widgets.geospatial_view import GoogleGeospatialView

            view = GoogleGeospatialView(title="Geodetic Satellite & 3D Terrain Context")
        except Exception as exc:
            if hasattr(self, "geo_placeholder_text"):
                self.geo_placeholder_text.setText(f"Satellite/terrain view could not be initialized: {exc}")
            return
        self._clear_layout(self.geo_view_layout)
        self.geo_view = view
        self.geo_view_layout.addWidget(self.geo_view)

    def _build_report_tab(self) -> QWidget:
        widget = QWidget(); layout = QVBoxLayout(widget); layout.setContentsMargins(12, 12, 12, 12); title = QLabel("Client-ready QC and examination outputs"); title.setObjectName("geoSection"); layout.addWidget(title)
        row = QHBoxLayout();
        for label, callback in (("Export Selected Text", self.export_text), ("Export Selected Excel", self.export_xlsx), ("Export QC PDF", self.generate_report), ("Export QC Graphs", self.export_graphs)):
            button = QPushButton(label); button.clicked.connect(callback); row.addWidget(button)
        row.addStretch(1); layout.addLayout(row); self.report_status = QLabel("Exports preserve source-line traceability and configured QC criteria."); self.report_status.setWordWrap(True); layout.addWidget(self.report_status); layout.addStretch(1); return widget

    @staticmethod
    def _table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSortingEnabled(False)
        table.setWordWrap(False)
        table.setTextElideMode(Qt.ElideRight)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(21)
        table.horizontalHeader().setMinimumSectionSize(56)
        table.horizontalHeader().setDefaultSectionSize(105)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return table

    @staticmethod
    def _style_item(item: QTableWidgetItem, severity: str | None = None) -> None:
        if not severity:
            return
        sev = str(severity).upper()
        if sev in {"FAIL", "ERROR"}:
            item.setForeground(QColor("#9B2C2C"))
            item.setBackground(QColor("#FCEDED"))
        elif sev in {"WARN", "WARNING"}:
            item.setForeground(QColor("#8A5A00"))
            item.setBackground(QColor("#FFF6E3"))
        elif sev in {"PASS", "OK"}:
            item.setForeground(QColor("#146C43"))
            item.setBackground(QColor("#E8F7EF"))
        elif sev == "INFO":
            item.setForeground(QColor("#176B93"))
            item.setBackground(QColor("#E9F4FB"))

    def _append_row(self, table: QTableWidget, values: list[Any], *, severity: str | None = None) -> None:
        row = table.rowCount()
        table.insertRow(row)
        for col, value in enumerate(values):
            item = QTableWidgetItem("" if value is None else str(value))
            if col == 0 or severity:
                self._style_item(item, severity or str(value))
            table.setItem(row, col, item)
        height = 21
        if getattr(self, "findings_table", None) is table:
            height = 38
        elif getattr(self, "threshold_table", None) is table:
            height = 24
        table.setRowHeight(row, height)



    # -------------------------------- refresh --------------------------------
    def selected_fields(self) -> set[str]:
        return {key for key, check in self._field_checks.items() if check.isChecked()}

    def _refresh_all(self) -> None:
        self._refresh_overview()
        self._refresh_text_preview()
        self._refresh_coordinate_tables()
        self._refresh_qc()
        if self.tabs.currentIndex() == self.TAB_SPATIAL:
            self._refresh_spatial()
        if self.tabs.currentIndex() == self.TAB_GEOSPATIAL:
            self._refresh_geospatial()
        if self.dataset is None:
            self.badge.setText("No file loaded")
            self.header_status.setText("QC not run")
        else:
            self.badge.setText(f"{self.dataset.source_path.name} • {self.dataset.record_count:,} records")

    def _refresh_overview(self) -> None:
        if not hasattr(self, "overview_table"):
            return
        self.overview_table.setRowCount(0)
        self.workflow_table.setRowCount(0)
        if self.dataset is None:
            for key, value in (("records", "—"), ("positions", "—"), ("qc", "—"), ("format", "—")):
                self.overview_cards[key][0].setText(value)
            self._append_row(self.overview_table, ["Source File", "No geodetic/DC file loaded"])
            for row in (
                ["1. Import", "PENDING", "Open a DC/text/CSV geodetic survey export."],
                ["2. Examine", "PENDING", "Review parsed records, selected fields and source-line traceability."],
                ["3. Coordinate audit", "PENDING", "Validate WGS84/local positions, datum, equipment and antenna metadata."],
                ["4. QC", "PENDING", "Run GNSS precision, DOP, RMS, timing and completeness checks."],
                ["5. 2D/3D & satellite", "PENDING", "Render spatial quality context after valid coordinates are loaded."],
            ):
                self._append_row(self.workflow_table, row, severity=row[1])
            return

        summary = self._dataset_summary or self.dataset.summary()
        qc_text = "not run"
        if self.qc_result is not None:
            qc_text = f"{self.qc_result.score:.1f}/100"
        self.overview_cards["records"][0].setText(f"{summary.get('record_count', 0):,}")
        position_total = int(summary.get("position_count", 0) or 0) + int(summary.get("local_position_count", 0) or 0)
        self.overview_cards["positions"][0].setText(f"{position_total:,}")
        self.overview_cards["qc"][0].setText(qc_text)
        self.overview_cards["format"][0].setText(str(summary.get("source_format", "—")))
        self.overview_cards["records"][1].setText("source lines retained for audit")
        if summary.get("position_count"):
            self.overview_cards["positions"][1].setText("usable for native and satellite views")
        elif summary.get("local_position_count"):
            self.overview_cards["positions"][1].setText("local XY usable for native 2D/3D")
        else:
            self.overview_cards["positions"][1].setText("no renderable coordinates")
        self.overview_cards["qc"][1].setText(self.qc_result.status if self.qc_result else "run QC to evaluate")
        self.overview_cards["format"][1].setText(str(summary.get("encoding", "")))

        rows = [
            ["Source File", summary.get("source_file", self.dataset.source_path.name)],
            ["Source Format", summary.get("source_format", "")],
            ["Record Count", f"{summary.get('record_count', 0):,}"],
            ["WGS84 Position Count", f"{summary.get('position_count', 0):,}"],
            ["Local XY Position Count", f"{summary.get('local_position_count', 0):,}"],
            ["Latitude Range", self._range_text(summary.get("latitude_min"), summary.get("latitude_max"), "°")],
            ["Longitude Range", self._range_text(summary.get("longitude_min"), summary.get("longitude_max"), "°")],
            ["Local Easting Range", self._range_text(summary.get("local_easting_min"), summary.get("local_easting_max"), " m")],
            ["Local Northing Range", self._range_text(summary.get("local_northing_min"), summary.get("local_northing_max"), " m")],
            ["Recognized Values", f"{summary.get('recognized_value_count', 0):,}"],
            ["Parser Note", summary.get("parser_note", "")],
        ]
        for row in rows:
            self._append_row(self.overview_table, row)

        qc_status = self.qc_result.status if self.qc_result else "PENDING"
        coords_ready = "READY" if (summary.get("position_count", 0) or summary.get("local_position_count", 0)) else "PENDING"
        for row in (
            ["1. Import", "READY", "File parsed with source-line traceability and semantic field mapping."],
            ["2. Examine", "READY", "Selected DC fields can be reviewed/exported without changing raw data."],
            ["3. Coordinate audit", coords_ready, "GPS/local coordinates, datum/CRS and equipment tables are populated."],
            ["4. QC", qc_status, "GNSS precision, DOP, RMS, timing and survey-setting checks are available."],
            ["5. 2D/3D & satellite", coords_ready, "Native view and satellite/terrain view render automatically from valid WGS84 positions."],
        ):
            self._append_row(self.workflow_table, row, severity=row[1])

    @staticmethod
    def _range_text(lo: Any, hi: Any, unit: str = "") -> str:
        if lo is None or hi is None:
            return "—"
        try:
            return f"{float(lo):.8f} to {float(hi):.8f}{unit}"
        except Exception:
            return f"{lo} to {hi}{unit}"

    def _refresh_text_preview(self) -> None:
        if not hasattr(self, "text_preview"): return
        if self.dataset is None:
            self.text_preview.setPlainText("No geodetic/DC file loaded."); self.examiner_summary.setText("Open a DC/survey export to inspect records."); return
        selected = self.selected_fields(); lines: list[str] = []; preview_records = 0
        truncated = False
        for record in self.dataset.records:
            items = [(key, value) for key, value in record.values.items() if key in selected]
            if not items:
                continue
            block = [f"Record {record.record_id} | source line {record.line_number}"]
            block.extend(f"  {FIELD_LABELS.get(key, key)}: {value}" for key, value in items)
            block.append("")
            if len(lines) + len(block) > self.MAX_TEXT_PREVIEW_LINES:
                truncated = True
                break
            lines.extend(block)
            preview_records += 1
        if truncated:
            lines.extend(["", "[Preview truncated for responsive display; QC/export still use the complete dataset.]"])
        self.text_preview.setPlainText("\n".join(lines))
        summary = self._dataset_summary or self.dataset.summary()
        preview_note = f" • previewing {preview_records:,} matching records" if truncated else ""
        self.examiner_summary.setText(
            f"{summary['record_count']:,} parsed records • {summary['position_count']:,} position records • "
            f"format: {summary['source_format']}{preview_note} • raw source lines retained for audit."
        )

    def _refresh_coordinate_tables(self) -> None:
        tables = (
            getattr(self, "position_table", None),
            getattr(self, "vector_table", None),
            getattr(self, "datum_table", None),
            getattr(self, "equipment_table", None),
        )
        for table in tables:
            if table is not None:
                table.setUpdatesEnabled(False)
                table.setSortingEnabled(False)
                table.setRowCount(0)
        if self.dataset is None or not hasattr(self, "position_table"):
            for table in tables:
                if table is not None:
                    table.setUpdatesEnabled(True)
            return

        datum_ids = {"49", "50", "65", "81", "C8", "D5", "56", "57"}
        position_rows = vector_rows = datum_rows = equipment_rows = 0
        limit = self.MAX_TABLE_PREVIEW_ROWS

        try:
            # One source pass avoids repeatedly scanning a very large DC file for
            # each record family while the UI thread is preparing previews.
            for record in self.dataset.records:
                record_id = record.record_id.upper()
                if record_id in {"66", "68"} and position_rows < limit:
                    height_key = "ellipsoid_height_m" if record_id == "66" else "local_ellipsoid_height_m"
                    row = [
                        record.values.get("point_name", ""),
                        record.values.get("latitude_deg", ""),
                        record.values.get("longitude_deg", ""),
                        record.values.get("local_northing_m", ""),
                        record.values.get("local_easting_m", ""),
                        record.values.get(height_key, ""),
                        record.values.get("horizontal_precision_m", ""),
                        record.values.get("vertical_precision_m", ""),
                        record.values.get("measurement_method", ""),
                        record.values.get("point_classification", ""),
                    ]
                    self._append_row(self.position_table, row)
                    position_rows += 1

                if record_id == "67" and vector_rows < limit:
                    try:
                        length = float(
                            np.sqrt(
                                sum(
                                    float(record.values.get(key, np.nan)) ** 2
                                    for key in ("delta_x_m", "delta_y_m", "delta_z_m")
                                )
                            )
                        )
                    except Exception:
                        length = ""
                    row = [record.values.get(key, "") for key in ("point_name", "delta_x_m", "delta_y_m", "delta_z_m")]
                    row += [length, record.values.get("horizontal_precision_m", ""), record.values.get("vertical_precision_m", "")]
                    self._append_row(self.vector_table, row)
                    vector_rows += 1

                if record_id in datum_ids and datum_rows < limit:
                    for key, value in record.values.items():
                        if datum_rows >= limit:
                            break
                        self._append_row(self.datum_table, [record_id, FIELD_LABELS.get(key, key), value])
                        datum_rows += 1

                if record_id == "E2" and equipment_rows < limit:
                    for key, value in record.values.items():
                        if equipment_rows >= limit:
                            break
                        self._append_row(self.equipment_table, [FIELD_LABELS.get(key, key), value])
                        equipment_rows += 1
        finally:
            for table in tables:
                if table is not None:
                    table.setUpdatesEnabled(True)
                    table.viewport().update()

    def _populate_threshold_table(self) -> None:
        if not hasattr(self, "threshold_table"): return
        profile = QC_PROFILES[str(self.profile_combo.currentData() or "project_default")]
        definitions = {key: (label, unit, direction) for key, label, unit, direction in METRIC_DEFINITIONS}
        self.threshold_table.setRowCount(0)
        for key, limit in profile.thresholds.items():
            label, unit, direction = definitions.get(key, (FIELD_LABELS.get(key, key), "", "max"))
            row = self.threshold_table.rowCount(); self.threshold_table.insertRow(row)
            self.threshold_table.setItem(row, 0, QTableWidgetItem(label)); self.threshold_table.item(row, 0).setData(Qt.UserRole, key)
            self.threshold_table.setItem(row, 1, QTableWidgetItem("≥ minimum" if direction == "min" else "≤ maximum"))
            spin = QDoubleSpinBox(); spin.setDecimals(5); spin.setRange(-1e9, 1e9); spin.setValue(float(limit)); self.threshold_table.setCellWidget(row, 2, spin)
            self.threshold_table.setItem(row, 3, QTableWidgetItem(unit))

    def _threshold_overrides(self) -> dict[str, float]:
        output: dict[str, float] = {}
        for row in range(self.threshold_table.rowCount()):
            item = self.threshold_table.item(row, 0); widget = self.threshold_table.cellWidget(row, 2)
            if item is not None and isinstance(widget, QDoubleSpinBox): output[str(item.data(Qt.UserRole))] = widget.value()
        return output

    def _refresh_qc(self) -> None:
        if not hasattr(self, "findings_table"):
            return
        self.findings_table.setRowCount(0)
        if hasattr(self, "qc_stage_table"):
            self.qc_stage_table.setRowCount(0)
        if hasattr(self, "qc_checks_table"):
            self.qc_checks_table.setRowCount(0)
        self._clear_graph_stack()
        if self.qc_result is None:
            self.header_status.setText("QC not run")
            self.qc_badge.setText("QC not run")
            self.qc_badge.setObjectName("geoInfo")
            self.qc_badge.setStyleSheet("")
            self.qc_score_value.setText("—/100")
            self.qc_score_bar.setValue(0)
            self.qc_fail_tile.setText("0")
            self.qc_warn_tile.setText("0")
            self.qc_info_tile.setText("0")
            self.qc_note.setText("Load a geodetic/DC file and run QC. Thresholds remain editable from the table below.")
            self.graph_page_label.setText("Page 0/0")
            return

        status = str(self.qc_result.status).upper()
        self.header_status.setText(f"Geodetic QC: {status} — {self.qc_result.score:.1f}/100")
        self.qc_badge.setText(status)
        self._apply_status_label(self.qc_badge, status)
        self.qc_score_value.setText(f"{self.qc_result.score:.1f}/100")
        self.qc_score_bar.setValue(max(0, min(100, int(round(self.qc_result.score)))))
        failures = int(self.qc_result.checks.get("failures", sum(1 for item in self.qc_result.findings if item.severity == "FAIL")))
        warnings = int(self.qc_result.checks.get("warnings", sum(1 for item in self.qc_result.findings if item.severity == "WARN")))
        info = int(self.qc_result.checks.get("information", sum(1 for item in self.qc_result.findings if item.severity == "INFO")))
        self.qc_fail_tile.setText(str(failures))
        self.qc_warn_tile.setText(str(warnings))
        self.qc_info_tile.setText(str(info))
        self.qc_note.setText(
            f"{len(self.qc_result.metrics):,} metric groups evaluated under profile: {self.qc_result.profile_name}. "
            "Review high-severity findings before accepting coordinates or generating reports."
        )

        if hasattr(self, "qc_checks_table"):
            checks = self.qc_result.checks or {}
            audit_rows = [
                ["Profile", self.qc_result.profile_name],
                ["Record IDs", ", ".join(checks.get("record_ids", []))],
                ["Failures", failures],
                ["Warnings", warnings],
                ["Information", info],
            ]
            for group, values in checks.items():
                if group in {"metrics", "record_ids", "failures", "warnings", "information"}:
                    continue
                audit_rows.append([str(group).replace("_", " ").title(), values])
            for row in audit_rows:
                self._append_row(self.qc_checks_table, row)

        metrics_summary = self.qc_result.checks.get("metrics", {}) if self.qc_result.checks else {}
        for key, metric in self.qc_result.metrics.items():
            finite = metric.finite
            if finite.size:
                median = f"{float(np.median(finite)):.4g}"
                extreme = float(np.min(finite)) if metric.direction == "min" else float(np.max(finite))
                extreme_text = f"{extreme:.4g}"
            else:
                median = "—"
                extreme_text = "—"
            limit_text = "—" if metric.threshold is None else f"{metric.threshold:g}{(' ' + metric.unit) if metric.unit else ''}"
            violations = int(metrics_summary.get(key, {}).get("violations", 0) or 0)
            result = "PASS" if violations == 0 else ("WARN" if violations <= max(1, int(0.10 * max(1, finite.size))) else "FAIL")
            self._append_row(
                self.qc_stage_table,
                [metric.label, str(int(finite.size)), median, extreme_text, limit_text, result],
                severity=result,
            )

        for finding in self.qc_result.findings:
            sev = "WARN" if str(finding.severity).upper() == "WARNING" else str(finding.severity).upper()
            evidence = finding.message
            if finding.observed is not None or finding.limit is not None:
                evidence = f"{finding.message}  Observed: {finding.observed if finding.observed is not None else '—'}; limit: {finding.limit if finding.limit is not None else '—'}"
            self._append_row(
                self.findings_table,
                [sev, finding.code, finding.title, evidence, finding.suggested_action],
                severity=sev,
            )

        if not self.qc_result.findings:
            self._append_row(self.findings_table, ["PASS", "NO_FINDINGS", "No QC findings", "All configured checks passed.", "Proceed to review/export."], severity="PASS")

        metric_keys = [key for key, metric in self.qc_result.metrics.items() if metric.finite.size]
        self._graph_pages = [[key] for key in metric_keys]
        if hasattr(self, "graph_tabs"):
            if not metric_keys:
                empty = QLabel("No finite C6/QC metric values are available for plotting. Confirm that the source file contains satellite, DOP, RMS or precision fields.")
                empty.setObjectName("geoInfoText")
                empty.setAlignment(Qt.AlignCenter)
                self.graph_tabs.addTab(empty, "No Graphs")
            for key in metric_keys:
                card = _MetricGraphCard()
                card.set_metric(self.qc_result.metrics[key])
                self._graph_cards.append(card)
                self.graph_tabs.addTab(card, self._short_graph_title(self.qc_result.metrics[key]))
        elif hasattr(self, "graph_stack"):
            for key in metric_keys:
                card = _MetricGraphCard()
                card.set_metric(self.qc_result.metrics[key])
                self._graph_cards.append(card)
                self.graph_stack.addWidget(card)
        self._sync_graph_page_label()
        self._refresh_overview()

    @staticmethod
    def _apply_status_label(label: QLabel, status: str) -> None:
        status = str(status).upper()
        if status in {"PASS", "READY"}:
            label.setStyleSheet("background:#E7F6EF;color:#156B41;border:1px solid #CBEBD9;border-radius:8px;padding:3px 8px;font-weight:900;")
        elif status in {"WARN", "WARNING", "PENDING"}:
            label.setStyleSheet("background:#FFF6E3;color:#8A5A00;border:1px solid #F1DCAB;border-radius:8px;padding:3px 8px;font-weight:900;")
        elif status in {"FAIL", "ERROR"}:
            label.setStyleSheet("background:#FCEDED;color:#A43B3B;border:1px solid #F0C9C9;border-radius:8px;padding:3px 8px;font-weight:900;")
        else:
            label.setStyleSheet("background:#E9F4FB;color:#176B93;border:1px solid #C8E4F2;border-radius:8px;padding:3px 8px;font-weight:900;")

    def _clear_graph_stack(self) -> None:
        self._graph_cards.clear(); self._graph_pages.clear()
        if hasattr(self, "graph_tabs"):
            while self.graph_tabs.count():
                widget = self.graph_tabs.widget(0)
                self.graph_tabs.removeTab(0)
                widget.deleteLater()
        if hasattr(self, "graph_stack"):
            while self.graph_stack.count():
                widget = self.graph_stack.widget(0); self.graph_stack.removeWidget(widget); widget.deleteLater()

    @staticmethod
    def _short_graph_title(metric: GeodeticMetric) -> str:
        labels = {
            "min_satellites": "Satellites",
            "relative_dops": "Relative DOPs",
            "positions_used": "Positions Used",
            "horizontal_sd_m": "Horizontal SD",
            "vertical_sd_m": "Vertical SD",
            "delta_time_s": "Delta Time",
        }
        return labels.get(metric.key, metric.label)

    def _sync_graph_page_label(self) -> None:
        if hasattr(self, "graph_tabs"):
            count = self.graph_tabs.count()
            current = self.graph_tabs.currentIndex() + 1 if count else 0
            label = "No QC graphs loaded" if count == 0 else f"Graph {current}/{count} • each metric opens in its own tab"
            self.graph_page_label.setText(label)
            return
        count = self.graph_stack.count() if hasattr(self, "graph_stack") else 0
        current = self.graph_stack.currentIndex() + 1 if count else 0
        self.graph_page_label.setText(f"Graph {current}/{count}")

    def _refresh_spatial(self) -> None:
        self._ensure_native_view()
        if not hasattr(self, "native_view"):
            return
        if self.dataset is None:
            self.native_view.clear("Load GPS/local position records to enable native 2D/3D visualization.")
            return
        lon, lat, height, _names = self.dataset.gps_positions()
        if lon.size:
            x, y, _lon0, _lat0 = geographic_to_local_xy(lon, lat)
            precision = self.dataset.numeric_series("66", "horizontal_precision_m")
            coordinate_label = "Local metric display derived from WGS84 latitude/longitude"
        else:
            x, y, height, _names = self.dataset.local_positions()
            precision = self.dataset.numeric_series(("66", "68"), "horizontal_precision_m")
            coordinate_label = "Native local/project XY coordinates from controller export"
        if x.size == 0:
            self.native_view.clear("No valid WGS84 or local easting/northing position records are available.")
            return
        if precision.size != x.size or not np.any(np.isfinite(precision)):
            values = np.arange(1, x.size + 1, dtype=float)
            label, units = "Observation", ""
        else:
            values = precision
            label, units = "Horizontal Precision", "m"
        self.native_view.set_data(
            x, y, values, z=height, title=self.dataset.source_path.name, value_label=label,
            value_units=units, coordinate_label=coordinate_label, allow_surface=False,
        )

    def _refresh_geospatial(self) -> None:
        self._ensure_geo_view()
        if not hasattr(self, "geo_view"): return
        if self.dataset is None:
            self.geo_view.clear_tracks(); return
        lon, lat, height, _names = self.dataset.gps_positions()
        if lon.size == 0:
            self.geo_view.clear_tracks(); self.geo_view.set_status_message("No valid WGS84 position records are available for satellite/terrain context."); return
        from ui.widgets.geospatial_view import GeoTrack

        self.geo_view.set_tracks([GeoTrack(self.dataset.source_path.stem, lon, lat, height)], render=True)

    def _require_dataset(self) -> bool:
        if self.dataset is not None: return True
        QMessageBox.information(self, "Geodetic", "Open a geodetic/DC survey file first."); return False