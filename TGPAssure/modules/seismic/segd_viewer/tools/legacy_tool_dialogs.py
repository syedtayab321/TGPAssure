from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from modules.seismic.segd_viewer.segd_reader import SegdReader

TOOL_STYLE = """
QDialog{background:#EAF0F5;font-family:Arial,Segoe UI,sans-serif;font-size:8.5pt;}
QFrame#toolCard{background:#F7FAFC;border:1px solid #B7C5D2;border-radius:5px;}
QGroupBox{background:#F7FAFC;border:1px solid #B7C5D2;border-radius:5px;margin-top:8px;padding-top:7px;font-weight:700;color:#0D2D44;}
QGroupBox::title{subcontrol-origin:margin;left:7px;padding:0 4px;background:#F7FAFC;}
QLabel{background:transparent;border:0;color:#111;font-size:8.5pt;}
QLabel#title{font-size:13pt;font-weight:900;color:#000;}
QLabel#status{font-weight:700;color:#074E87;}
QLineEdit,QSpinBox,QDoubleSpinBox,QPlainTextEdit,QListWidget{background:#FFFFFF;border:1px solid #8FA3B5;border-radius:3px;padding:1px 2px;min-height:20px;font-size:8.5pt;color:#111;}
QPushButton{min-height:23px;padding:3px 7px;border-radius:4px;border:1px solid #8798A7;background:#F2F2F2;color:#111;font-weight:700;font-size:8.5pt;}
QPushButton:hover{background:#FFFFFF;}
QPushButton:checked{background:#CFE6FF;border:1px solid #2A75BB;color:#062F52;}
QProgressBar{background:#FFFFFF;border:1px solid #9AA9B5;border-radius:2px;text-align:center;height:16px;font-size:8pt;color:#111;}
QProgressBar::chunk{background:#1D86E2;}
QSlider::groove:horizontal{height:5px;background:#AAB4BD;border-radius:3px;}
QSlider::handle:horizontal{width:13px;margin:-5px 0;background:#1D86E2;border:2px solid white;border-radius:7px;}
QRadioButton,QCheckBox{font-size:8.5pt;color:#111;background:transparent;border:0;}
"""


def _fit_center(dialog: QDialog, max_w: int = 1040, max_h: int = 610) -> None:
    """Resize and center legacy dialogs so they never overflow the visible screen."""
    screen = QApplication.primaryScreen()
    if dialog.parentWidget() is not None:
        try:
            pt = dialog.parentWidget().mapToGlobal(QPoint(0, 0))
            screen = QApplication.screenAt(pt) or screen
        except Exception:
            pass
    if screen is None:
        dialog.resize(max_w, max_h)
        return
    geom = screen.availableGeometry()
    w = min(max_w, max(760, int(geom.width() * 0.88)))
    h = min(max_h, max(480, int(geom.height() * 0.78)))
    dialog.setMaximumSize(max(760, int(geom.width() * 0.96)), max(480, int(geom.height() * 0.90)))
    dialog.resize(w, h)
    dialog.move(geom.x() + (geom.width() - w) // 2, geom.y() + (geom.height() - h) // 2)


def _button(text: str, role: str = "gray", width: int | None = None) -> QPushButton:
    colors = {
        "blue": ("#DDEEFF", "#4B87C3", "#0E4F8C"),
        "green": ("#E2F7E8", "#65B47A", "#17682E"),
        "orange": ("#FFF0D2", "#CE9330", "#815300"),
        "red": ("#FBE4E4", "#D47C7C", "#8C1F1F"),
        "purple": ("#EFE5FF", "#9272CE", "#4F2F88"),
        "gray": ("#F3F3F3", "#8D8D8D", "#1B1B1B"),
    }
    bg, border, fg = colors.get(role, colors["gray"])
    b = QPushButton(text)
    b.setStyleSheet(
        f"QPushButton{{background:{bg};border:1px solid {border};color:{fg};font-weight:800;border-radius:4px;min-height:23px;}}"
        "QPushButton:hover{background:#FFFFFF;}"
        "QPushButton:checked{background:#CFE6FF;border:1px solid #2A75BB;color:#062F52;}"
    )
    if width:
        b.setFixedWidth(width)
    return b


def _field(text: str = "", width: int = 82, readonly: bool = False) -> QLineEdit:
    e = QLineEdit(text)
    e.setFixedWidth(width)
    e.setReadOnly(readonly)
    return e


def _format_number(value: Any, digits: int = 4) -> str:
    try:
        v = float(value)
    except Exception:
        return "—"
    if not np.isfinite(v):
        return "—"
    if abs(v) >= 1e5 or (0 < abs(v) < 1e-3):
        return f"{v:.{digits}e}"
    return f"{v:.{digits}g}"


def _spectral_lut() -> np.ndarray:
    stops = np.array([[18, 36, 82], [18, 96, 160], [19, 166, 185], [255, 213, 79], [218, 60, 45]], dtype=float)
    pos = np.linspace(0, 1, len(stops))
    x = np.linspace(0, 1, 256)
    return np.clip(np.vstack([np.interp(x, pos, stops[:, i]) for i in range(3)]).T, 0, 255).astype(np.ubyte)


def _status_from_trace_info(ti: Any) -> str:
    flags = [str(v) for v in (getattr(ti, "qc_flags", ()) or ())]
    if len(flags) > 1:
        return "Multiple"
    if flags:
        label = flags[0].strip()
        return label.title() if label.islower() else label
    if getattr(ti, "channel_type", 1) != 1:
        return "Auxiliary"
    if getattr(ti, "trace_edit", 0) not in (0, None):
        return "Other"
    return "None"


class SpreadCanvas(QWidget):
    ERROR_COLORS = {
        "None": QColor("#1DFF00"),
        "Normal": QColor("#1DFF00"),
        "Leakage": QColor("#173BFF"),
        "Tilt": QColor("#F018F0"),
        "Multiple": QColor("#FFF200"),
        "Capacitance": QColor("#000000"),
        "Resistance": QColor("#FF1B12"),
        "Other": QColor("#18D7DF"),
        "Auxiliary": QColor("#BFBFBF"),
    }
    RES_LEGEND = [(">1152", "#FF1A12"), ("896-1152", "#FFCC99"), ("640-896", "#FFFF00"), ("560-640", "#00FF00"), ("336-560", "#666633"), ("112-336", "#0099FF"), ("<112", "#000000")]
    LEAK_LEGEND = [(">10K", "#1DFF00"), ("8-10K", "#FFFF00"), ("5-8K", "#FFCC99"), ("<5K", "#FF1A12")]
    SLICE_COLORS = [QColor("#004BFF"), QColor("#00E5FF"), QColor("#00FF3B"), QColor("#FFFF00"), QColor("#FF9900"), QColor("#FF1A12")]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(600, 300)
        self._rows: list[dict[str, Any]] = []
        self._mode = "Errors"
        self._title = "Errors"
        self._slice_values: dict[int, float] = {}
        self._cursor_frac = 0.0
        self._slice_minmax = (0.0, 1.0)

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.update()

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self._title = mode
        self._slice_values = {}
        self.update()

    def set_slice(self, mode: str, values: dict[int, float]) -> None:
        self._mode = mode
        self._title = "Time Slice" if mode == "TSlice" else "Frequency Slice"
        self._slice_values = values
        vals = np.array([v for v in values.values() if np.isfinite(v)], dtype=float)
        if vals.size:
            # Spread peak scaling like the legacy viewer: one scale is used for
            # the full row/spread.  This keeps the row green overall and only
            # paints narrow colored clips where the selected sample/frequency is
            # actually stronger than the spread background.
            abs_vals = np.abs(vals)
            scale = float(np.nanpercentile(abs_vals, 98)) if abs_vals.size else 1.0
            if not np.isfinite(scale) or scale < 1e-12:
                scale = float(np.nanmax(abs_vals)) if abs_vals.size else 1.0
            if not np.isfinite(scale) or scale < 1e-12:
                scale = 1.0
            self._slice_minmax = (-scale, scale)
        else:
            self._slice_minmax = (-1.0, 1.0)
        self.update()

    def set_cursor_position(self, frac: float) -> None:
        self._cursor_frac = max(0.0, min(1.0, float(frac)))
        self.update()

    def _slice_clip_color(self, value: Any) -> QColor:
        """Legacy-like T/F slice color: green base, only stronger values become clips."""
        try:
            v = float(value)
        except Exception:
            return QColor("#1DFF00")
        if not np.isfinite(v):
            return QColor("#1DFF00")
        lo, hi = self._slice_minmax
        scale = max(abs(float(lo)), abs(float(hi)), 1e-12)
        ratio = max(-1.0, min(1.0, v / scale))
        mag = abs(ratio)
        # Most traces must remain green like the old 408 animation.
        if mag < 0.18:
            return QColor("#1DFF00")
        if ratio < 0:
            if mag >= 0.72:
                return QColor("#103BFF")
            if mag >= 0.42:
                return QColor("#00D9FF")
            return QColor("#12D96C")
        if mag >= 0.72:
            return QColor("#FF1A12")
        if mag >= 0.42:
            return QColor("#FFB000")
        return QColor("#FFFF00")

    def _metric_color(self, mode: str, row: dict[str, Any]) -> QColor:
        def f(v: Any) -> float | None:
            try:
                vv = float(v)
            except Exception:
                return None
            return vv if np.isfinite(vv) else None
        if mode == "Errors":
            return self.ERROR_COLORS.get(str(row.get("status", "None")), self.ERROR_COLORS["Other"])
        if mode == "Resistance":
            v = f(row.get("resistance"))
            if v is None: return QColor("#C8C8C8")
            if v < 112: return QColor("#000000")
            if v < 336: return QColor("#0099FF")
            if v < 560: return QColor("#666633")
            if v < 640: return QColor("#00FF00")
            if v < 896: return QColor("#FFFF00")
            if v < 1152: return QColor("#FFCC99")
            return QColor("#FF1A12")
        if mode == "Leakage":
            v = f(row.get("leakage"))
            if v is None: return QColor("#C8C8C8")
            if v < 5000: return QColor("#FF1A12")
            if v < 8000: return QColor("#FFCC99")
            if v < 10000: return QColor("#FFFF00")
            return QColor("#1DFF00")
        if mode in ("Capacitance", "Tilt"):
            key = "capacitance" if mode == "Capacitance" else "tilt"
            v = f(row.get(key))
            if v is None: return QColor("#C8C8C8")
            # Dynamic three-range look using all visible values.
            all_vals = [f(r.get(key)) for r in self._rows]
            all_vals = [x for x in all_vals if x is not None]
            if not all_vals: return QColor("#C8C8C8")
            lo, hi = float(np.nanmin(all_vals)), float(np.nanmax(all_vals))
            if abs(hi - lo) < 1e-12: return QColor("#00FF00")
            frac = (v - lo) / (hi - lo)
            return self.SLICE_COLORS[min(len(self.SLICE_COLORS)-1, max(0, int(frac * len(self.SLICE_COLORS))))]
        if mode in ("TSlice", "FSlice"):
            return self._slice_clip_color(self._slice_values.get(int(row.get("index", 0))))
        return QColor("#C8C8C8")

    def _legend_items(self) -> list[tuple[str, QColor]]:
        if self._mode == "Errors":
            return [("None", self.ERROR_COLORS["None"]), ("Leakage", self.ERROR_COLORS["Leakage"]), ("Tilt", self.ERROR_COLORS["Tilt"]), ("Multiple", self.ERROR_COLORS["Multiple"]), ("Capacitance", self.ERROR_COLORS["Capacitance"]), ("Resistance", self.ERROR_COLORS["Resistance"]), ("Other", self.ERROR_COLORS["Other"])]
        if self._mode == "Resistance":
            return [(label, QColor(color)) for label, color in self.RES_LEGEND]
        if self._mode == "Leakage":
            return [(label, QColor(color)) for label, color in self.LEAK_LEGEND]
        if self._mode in ("TSlice", "FSlice"):
            return [("Base", QColor("#1DFF00")), ("Neg Clip", QColor("#103BFF")), ("Mid Clip", QColor("#FFB000")), ("Peak Clip", QColor("#FF1A12"))]
        return [("Low", self.SLICE_COLORS[0]), ("Normal", self.SLICE_COLORS[2]), ("High", self.SLICE_COLORS[-1])]

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(self.rect(), QColor("#F4F7FA"))
        if not self._rows:
            painter.setPen(QColor("#555"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No SEG-D spread data")
            return
        legend_w = 118
        left_margin = 68
        right_margin = legend_w + 40
        axis_h = 46
        title_h = 30
        plot_h = max(190, self.height() - 46 - axis_h)
        plot_w = max(320, self.width() - left_margin - right_margin)
        plot = QRectF(left_margin, 46, plot_w, plot_h)
        legend_h = min(plot.height() - 24, max(122, 22 * len(self._legend_items()) + 12))
        legend = QRectF(plot.right() + 14, plot.top() + max(40, (plot.height() - legend_h) / 2), legend_w, legend_h)
        painter.fillRect(plot, QColor("#FFFFFF"))
        painter.setPen(QPen(QColor("#B6B6B6"), 1))
        painter.drawRect(plot)
        painter.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        painter.setPen(QColor("#000"))
        painter.drawText(QRectF(plot.left(), plot.top() - title_h, plot.width(), title_h), Qt.AlignmentFlag.AlignCenter, self._title)

        points = [float(r.get("point", r.get("index", 0) + 1)) for r in self._rows]
        pmin, pmax = min(points), max(points)
        if abs(pmax - pmin) < 1e-9:
            pmax = pmin + 1.0
        lines = sorted({float(r.get("line", 0.0)) for r in self._rows}) or [0.0]
        bar_h = max(8, min(20, int(plot.height() / max(8, len(lines) * 3))))
        painter.setFont(QFont("Arial", 9))
        for li, line in enumerate(lines):
            yy = plot.top() + ((li + 0.5) / max(1, len(lines))) * plot.height()
            row_group = sorted([r for r in self._rows if float(r.get("line", 0.0)) == line], key=lambda r: float(r.get("point", r.get("index", 0) + 1)))
            if not row_group:
                continue
            xs = [plot.left() + ((float(r.get("point", r.get("index", 0) + 1)) - pmin) / (pmax - pmin)) * plot.width() for r in row_group]
            painter.setPen(QColor("#111"))
            painter.drawText(QRectF(4, yy - 11, plot.left() - 12, 22), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{line:g}")
            if self._mode in ("TSlice", "FSlice"):
                # Legacy behaviour: the full receiver row remains the base QC
                # colour (normally green).  The animated slice only appears as
                # small narrow colored clips at individual receiver positions.
                base_status = "None"
                non_none = [str(r.get("status", "None")) for r in row_group if str(r.get("status", "None")) not in ("None", "Normal", "Auxiliary")]
                if non_none:
                    base_status = non_none[0]
                base_color = self.ERROR_COLORS.get(base_status, self.ERROR_COLORS["None"])
                painter.fillRect(QRectF(plot.left(), yy - bar_h / 2, plot.width(), bar_h), base_color)
                clip_w = max(2.0, min(5.0, plot.width() / max(160.0, len(row_group) * 1.8)))
                for j, row in enumerate(row_group):
                    clip_color = self._metric_color(self._mode, row)
                    if clip_color == base_color or clip_color == QColor("#1DFF00"):
                        continue
                    x = xs[j]
                    painter.fillRect(QRectF(x - clip_w / 2.0, yy - bar_h / 2, clip_w, bar_h), clip_color)
            else:
                for j, row in enumerate(row_group):
                    left = plot.left() if j == 0 else (xs[j-1] + xs[j]) / 2.0
                    right = plot.right() if j == len(xs) - 1 else (xs[j] + xs[j+1]) / 2.0
                    if right < left:
                        left, right = right, left
                    color = self._metric_color(self._mode, row)
                    painter.fillRect(QRectF(left, yy - bar_h / 2, max(1.0, right - left), bar_h), color)
            cx = plot.left() + self._cursor_frac * plot.width()
            painter.setPen(QPen(QColor("#1396D9"), 1.4))
            painter.drawLine(int(cx), int(yy - bar_h / 2 - 1), int(cx), int(yy + bar_h / 2 + 1))

        painter.setFont(QFont("Arial", 8))
        painter.setPen(QColor("#111"))
        for frac in np.linspace(0, 1, 7):
            x = plot.left() + frac * plot.width()
            val = pmin + frac * (pmax - pmin)
            painter.drawLine(int(x), int(plot.bottom()), int(x), int(plot.bottom() + 4))
            label_x = max(plot.left(), min(x - 36, plot.right() - 72))
            painter.drawText(QRectF(label_x, plot.bottom() + 5, 72, 18), Qt.AlignmentFlag.AlignCenter, f"{val:g}")
        painter.setFont(QFont("Arial", 9))
        painter.drawText(QRectF(plot.left(), min(self.height() - 24, plot.bottom() + 24), plot.width(), 20), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, "Position")

        painter.fillRect(legend, QColor("#FFFFFF"))
        painter.setPen(QPen(QColor("#C4CCD4"), 1))
        painter.drawRect(legend)
        painter.setFont(QFont("Arial", 7))
        items = self._legend_items()
        y = legend.top() + 8
        for label, color in items:
            painter.fillRect(QRectF(legend.left() + 7, y, 18, 16), color)
            painter.setPen(QColor("#000"))
            painter.drawText(QRectF(legend.left() + 30, y, legend.width() - 34, 16), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label)
            y += 19


class SpreadViewDialog(QDialog):
    def __init__(self, viewer: Any) -> None:
        super().__init__(viewer)
        self.viewer = viewer
        self.reader = viewer.reader
        self.setWindowTitle("Spread View")
        self.setStyleSheet(TOOL_STYLE)
        self._rows = self._load_rows()
        self._run_values: list[float] = []
        self._run_index = 0
        self._run_mode: str | None = None
        self._paused = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._run_next_step)
        self._build_ui()
        _fit_center(self, 1010, 600)
        QTimer.singleShot(0, lambda: _fit_center(self, 1010, 600))
        self._set_mode("Errors")

    def _load_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for i in range(self.reader.get_trace_count()):
            ti = self.reader.get_trace_info(i)
            rows.append({
                "index": i,
                "line": float(getattr(ti, "receiver_line", 0.0) or 0.0),
                "point": float(getattr(ti, "receiver_point", i + 1) or (i + 1)),
                "channel_type": getattr(ti, "channel_type", 1),
                "status": _status_from_trace_info(ti),
                "resistance": getattr(ti, "resistance", np.nan),
                "capacitance": getattr(ti, "capacitance", np.nan),
                "leakage": getattr(ti, "leakage", np.nan),
                "tilt": getattr(ti, "tilt", np.nan),
            })
        # The legacy 408 spread view displays the receiver spread, not the
        # auxiliary/header traces.  Some SEG-D files decode a few traces with
        # receiver line 0; keeping those produces the unwanted top row seen in
        # the new dialog.  When real receiver lines exist, keep only those.
        seismic_rows = [r for r in rows if int(r.get("channel_type", 1) or 1) == 1]
        if seismic_rows:
            rows = seismic_rows
        if any(abs(float(r.get("line", 0.0))) > 1e-9 for r in rows):
            rows = [r for r in rows if abs(float(r.get("line", 0.0))) > 1e-9]
        return rows

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)
        top_box = QFrame()
        top_box.setObjectName("toolCard")
        top = QHBoxLayout(top_box)
        top.setContentsMargins(8, 5, 8, 5)
        top.setSpacing(6)
        self.print_btn = _button("Print", "green", 76)
        self.bmp_btn = _button("BMP", "blue", 76)
        self.tslice_btn = _button("TSlice", "orange", 82)
        self.fslice_btn = _button("FSlice", "orange", 82)
        self.pause_btn = _button("Pause", "purple", 82)
        self.abandon_btn = _button("Abandon", "red", 84)
        self.print_btn.clicked.connect(self._print_canvas)
        self.bmp_btn.clicked.connect(self._export_bmp)
        self.tslice_btn.clicked.connect(self._start_time_slice)
        self.fslice_btn.clicked.connect(self._start_frequency_slice)
        self.pause_btn.clicked.connect(self._toggle_pause)
        self.abandon_btn.clicked.connect(self._abandon)
        for w in (self.print_btn, self.bmp_btn): top.addWidget(w)
        top.addSpacing(6)
        for w in (self.tslice_btn, self.fslice_btn): top.addWidget(w)
        top.addSpacing(6)
        top.addWidget(QLabel("From"))
        self.from_spin = QDoubleSpinBox(); self.from_spin.setDecimals(1); self.from_spin.setRange(-1e6, 1e6); self.from_spin.setValue(10.0); self.from_spin.setFixedWidth(72)
        self.to_spin = QDoubleSpinBox(); self.to_spin.setDecimals(1); self.to_spin.setRange(-1e6, 1e6); self.to_spin.setValue(80.0); self.to_spin.setFixedWidth(72)
        top.addWidget(self.from_spin); top.addWidget(QLabel("To")); top.addWidget(self.to_spin)
        norm = QGroupBox("Normalisation")
        nv = QVBoxLayout(norm); nv.setContentsMargins(8, 3, 8, 4); nv.setSpacing(2)
        self.spread_peak_radio = QRadioButton("Spread Pea")
        self.trace_peak_radio = QRadioButton("Trace Peak")
        self.spread_peak_radio.setChecked(True)
        nv.addWidget(self.spread_peak_radio); nv.addWidget(self.trace_peak_radio)
        top.addWidget(norm)
        top.addStretch(1)
        top.addWidget(self.pause_btn); top.addWidget(self.abandon_btn)
        root.addWidget(top_box)

        body = QHBoxLayout()
        body.setSpacing(6)
        left_box = QFrame()
        left_box.setObjectName("toolCard")
        left = QVBoxLayout(left_box)
        left.setContentsMargins(6, 6, 6, 6)
        left.setSpacing(6)
        self.mode_buttons: dict[str, QPushButton] = {}
        for mode in ("Resistance", "Capacitance", "Leakage", "Tilt", "Errors"):
            b = _button(mode, "gray", 96)
            b.setCheckable(True)
            b.clicked.connect(lambda checked=False, m=mode: self._set_mode(m))
            self.mode_buttons[mode] = b
            left.addWidget(b)
        left.addStretch(1)
        close = _button("Close", "red", 96)
        close.clicked.connect(self.accept)
        left.addWidget(close)
        body.addWidget(left_box, 0)
        self.canvas = SpreadCanvas(self)
        body.addWidget(self.canvas, 1)
        root.addLayout(body, 1)

        bottom_box = QFrame()
        bottom_box.setObjectName("toolCard")
        bottom = QHBoxLayout(bottom_box)
        bottom.setContentsMargins(8, 4, 8, 4)
        bottom.setSpacing(8)
        self.progress_bar = QProgressBar(); self.progress_bar.setRange(0, 100); self.progress_bar.setFixedWidth(220)
        bottom.addWidget(self.progress_bar)
        bottom.addWidget(QLabel("Position"))
        self.position_slider = QSlider(Qt.Orientation.Horizontal); self.position_slider.setRange(0, 1000); self.position_slider.valueChanged.connect(self._position_changed)
        bottom.addWidget(self.position_slider, 1)
        self.position_edit = _field("0", 58, True); bottom.addWidget(self.position_edit)
        bottom.addWidget(QLabel("Update Delay")); bottom.addWidget(QLabel("Fast"))
        self.delay_slider = QSlider(Qt.Orientation.Horizontal); self.delay_slider.setRange(25, 450); self.delay_slider.setValue(120); self.delay_slider.valueChanged.connect(self._delay_changed)
        bottom.addWidget(self.delay_slider, 0); bottom.addWidget(QLabel("Slow"))
        root.addWidget(bottom_box)
        self.status_label = QLabel("Ready"); self.status_label.setObjectName("status")
        root.addWidget(self.status_label)
        pts = [r["point"] for r in self._rows] or [0.0, 1.0]
        self.point_min, self.point_max = min(pts), max(pts)

    def _set_mode(self, mode: str) -> None:
        self._timer.stop(); self._run_mode = None; self._paused = False; self.pause_btn.setText("Pause")
        for name, btn in self.mode_buttons.items(): btn.setChecked(name == mode)
        self.canvas.set_rows(self._rows); self.canvas.set_mode(mode)
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Showing {mode} for {len(self._rows):,} traces.")

    def _position_changed(self, value: int) -> None:
        frac = value / 1000.0
        self.canvas.set_cursor_position(frac)
        pt = self.point_min + frac * (self.point_max - self.point_min)
        self.position_edit.setText(f"{pt:.0f}")

    def _delay_changed(self, value: int) -> None:
        if self._timer.isActive(): self._timer.setInterval(value)

    def _trace_for_index(self, index: int) -> np.ndarray:
        data = self.reader.read_channel_data((index, index + 1), 0, None)
        if data.size == 0:
            return np.zeros(max(1, self.reader.get_sample_count()), dtype=float)
        x = np.nan_to_num(data[0].astype(float))
        if self.trace_peak_radio.isChecked():
            x = x / max(float(np.max(np.abs(x))), 1e-12)
        return x

    def _start_time_slice(self) -> None:
        a, b = float(self.from_spin.value()), float(self.to_spin.value())
        steps = max(2, min(160, int(abs(b - a)) + 1))
        self._run_values = list(np.linspace(a, b, steps)); self._run_mode = "TSlice"; self._run_index = 0; self._paused = False
        self.pause_btn.setText("Pause"); self.progress_bar.setValue(0); self.status_label.setText("Time Slice running...")
        self._timer.start(self.delay_slider.value())

    def _start_frequency_slice(self) -> None:
        a, b = float(self.from_spin.value()), float(self.to_spin.value())
        steps = max(2, min(160, int(abs(b - a)) + 1))
        self._run_values = list(np.linspace(a, b, steps)); self._run_mode = "FSlice"; self._run_index = 0; self._paused = False
        self.pause_btn.setText("Pause"); self.progress_bar.setValue(0); self.status_label.setText("Frequency Slice running...")
        self._timer.start(self.delay_slider.value())

    def _run_next_step(self) -> None:
        if not self._run_mode or self._run_index >= len(self._run_values):
            self._timer.stop(); self.status_label.setText("Completed."); return
        value = float(self._run_values[self._run_index]); values: dict[int, float] = {}
        if self._run_mode == "TSlice":
            sample = int(round(value / max(float(self.reader.get_sample_interval()), 1e-12)))
            for row in self._rows:
                tr = self._trace_for_index(int(row["index"]))
                if 0 <= sample < tr.size: values[int(row["index"])] = float(tr[sample])
            self.status_label.setText(f"Time Slice running: {value:.1f} ms")
        else:
            dt = max(float(self.reader.get_sample_interval()), 1e-12) / 1000.0
            for row in self._rows:
                tr = self._trace_for_index(int(row["index"]))
                if tr.size < 4: continue
                spec = np.abs(np.fft.rfft((tr - np.mean(tr)) * np.hanning(tr.size)))
                freq = np.fft.rfftfreq(tr.size, d=dt)
                k = int(np.argmin(np.abs(freq - value)))
                values[int(row["index"])] = float(spec[k]) if k < spec.size else 0.0
            self.status_label.setText(f"Frequency Slice running: {value:.1f} Hz")
        frac = (self._run_index + 1) / max(1, len(self._run_values))
        self.canvas.set_rows(self._rows); self.canvas.set_slice(self._run_mode, values)
        self.progress_bar.setValue(int(frac * 100)); self.position_slider.setValue(int(frac * 1000))
        self._run_index += 1

    def _toggle_pause(self) -> None:
        if not self._run_mode: return
        self._paused = not self._paused
        if self._paused:
            self._timer.stop(); self.pause_btn.setText("Continue")
        else:
            self._timer.start(self.delay_slider.value()); self.pause_btn.setText("Pause")

    def _abandon(self) -> None:
        self._timer.stop(); self._run_mode = None; self._paused = False; self.pause_btn.setText("Pause")
        self.progress_bar.setValue(0); self.status_label.setText("Processing abandoned."); self._set_mode("Errors")

    def _export_bmp(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save Spread View", "spread_view.bmp", "Bitmap (*.bmp)")
        if path: self.canvas.grab().save(path)

    def _print_canvas(self) -> None:
        path = str(Path.cwd() / "spread_view_print_preview.png")
        self.canvas.grab().save(path)
        QMessageBox.information(self, "Print", f"Print preview image created:\n{path}")


class FileSplitterDialog(QDialog):
    def __init__(self, viewer: Any) -> None:
        super().__init__(viewer); self.viewer = viewer; self.setWindowTitle("File Splitter"); self.setStyleSheet(TOOL_STYLE)
        root = QVBoxLayout(self); grid = QGridLayout(); root.addLayout(grid)
        self.select_btn = _button("Select File", "blue", 130); self.close_btn = _button("Close", "red", 130)
        self.file_edit = _field(width=140, readonly=True); self.traces_edit = _field("0", 90, True); self.current_trace_edit = _field("", 90, True)
        grid.addWidget(self.select_btn,0,0); grid.addWidget(QLabel("File"),0,1); grid.addWidget(self.file_edit,0,2)
        grid.addWidget(self.close_btn,1,0); grid.addWidget(QLabel("Traces in File"),1,1); grid.addWidget(self.traces_edit,1,2)
        grid.addWidget(QLabel("Current Trace"),2,1); grid.addWidget(self.current_trace_edit,2,2)
        root.addStretch(1); root.addWidget(QLabel("Current File Progress")); self.current_progress = QProgressBar(); root.addWidget(self.current_progress)
        root.addWidget(QLabel("Overall Progress")); self.overall_progress = QProgressBar(); root.addWidget(self.overall_progress)
        self.status = QLabel(""); root.addWidget(self.status)
        self.select_btn.clicked.connect(self._select_file); self.close_btn.clicked.connect(self.reject)
        _fit_center(self, 450, 430)

    def _select_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select SEG-D File", str(self.viewer.file_path.parent), "SEG-D (*.segd *.seg *.dat *.bin);;All files (*.*)")
        if not path: return
        reader = SegdReader(Path(path)); count = reader.get_trace_count(); self.file_edit.setText(Path(path).name); self.traces_edit.setText(str(count))
        out_dir = Path(path).with_suffix(""); out_dir = out_dir.parent / f"{out_dir.name}_split"; out_dir.mkdir(exist_ok=True)
        chunk = 100; pieces = max(1, int(np.ceil(count / chunk)))
        for part in range(pieces):
            a, b = part * chunk, min(count, (part + 1) * chunk)
            data = reader.read_channel_data((a, b), 0, None); np.savez_compressed(out_dir / f"part_{part + 1:03d}.npz", data=data)
            self.current_trace_edit.setText(str(b)); self.current_progress.setValue(int(b / max(count,1) * 100)); self.overall_progress.setValue(int((part+1)/pieces*100)); QApplication.processEvents()
        self.status.setText(f"Split into {pieces} file(s): {out_dir}")


class FixRadioSimDialog(QDialog):
    def __init__(self, viewer: Any) -> None:
        super().__init__(viewer); self.viewer = viewer; self.setWindowTitle("Fix Radio Sim File"); self.setStyleSheet(TOOL_STYLE)
        root = QGridLayout(self)
        select_btn = _button("Select File(s)", "blue", 120); close_btn = _button("Close", "red", 110)
        root.addWidget(select_btn,0,0); root.addWidget(close_btn,0,2)
        self.traces_required = QSpinBox(); self.traces_required.setRange(1,999999); self.traces_required.setValue(3); self.traces_required.setFixedWidth(70)
        self.end_time = QSpinBox(); self.end_time.setRange(1,999999); self.end_time.setValue(12000); self.end_time.setFixedWidth(90)
        self.prefix = _field("RS", 70); self.delete_check = QCheckBox("Delete Original After Fix")
        root.addWidget(QLabel("Traces Required"),1,0); root.addWidget(self.traces_required,1,1)
        root.addWidget(QLabel("End Time (mS)"),2,0); root.addWidget(self.end_time,2,1)
        root.addWidget(QLabel("Output File Prefix"),3,0); root.addWidget(self.prefix,3,1)
        root.addWidget(self.delete_check,4,0,1,2); self.progress = QProgressBar(); root.addWidget(self.progress,5,0,1,3); self.status = QLabel(""); root.addWidget(self.status,6,0,1,3)
        select_btn.clicked.connect(self._process); close_btn.clicked.connect(self.reject); _fit_center(self, 420, 320)

    def _process(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Select File(s)", str(self.viewer.file_path.parent), "All files (*.*)")
        for i, path in enumerate(paths, start=1):
            raw = Path(path).read_bytes().replace(b"\x00", b"").replace(b"\r\r\n", b"\r\n")
            out = Path(path).with_name(f"{self.prefix.text().strip() or 'RS'}_{Path(path).name}"); out.write_bytes(raw)
            if self.delete_check.isChecked():
                try: Path(path).unlink()
                except Exception: pass
            self.progress.setValue(int(i/max(1,len(paths))*100)); self.status.setText(f"Processed {i}/{len(paths)}: {out.name}"); QApplication.processEvents()


class RecordSumDiffDialog(QDialog):
    def __init__(self, viewer: Any) -> None:
        super().__init__(viewer); self.viewer = viewer; self.file1 = ""; self.file2 = ""; self.setWindowTitle("Sum/Difference of Records"); self.setStyleSheet(TOOL_STYLE)
        root = QGridLayout(self)
        self.f1 = _field(width=220, readonly=True); self.f2 = _field(width=220, readonly=True)
        s1 = _button("Select File 1", "blue", 110); s2 = _button("Select File 2", "blue", 110); go = _button("Go", "green", 110); cancel = _button("Cancel", "red", 110)
        root.addWidget(s1,0,0); root.addWidget(self.f1,0,1); root.addWidget(s2,1,0); root.addWidget(self.f2,1,1); root.addWidget(go,2,0); root.addWidget(cancel,3,0)
        op = QGroupBox("Operation"); ov = QVBoxLayout(op); self.sum_radio = QRadioButton("Sum"); self.diff_radio = QRadioButton("Difference"); self.diff_radio.setChecked(True); self.norm_check = QCheckBox("Normalise to Trace Peak")
        for w in (self.sum_radio,self.diff_radio,self.norm_check): ov.addWidget(w)
        root.addWidget(op,2,1,2,1); self.read1 = _field(width=220, readonly=True); self.read2 = _field(width=220, readonly=True); self.operation_field = _field(width=220, readonly=True)
        root.addWidget(QLabel("Read File"),4,0); root.addWidget(self.read1,4,1); root.addWidget(QLabel("Read File"),5,0); root.addWidget(self.read2,5,1); root.addWidget(QLabel("Operation"),6,0); root.addWidget(self.operation_field,6,1)
        s1.clicked.connect(lambda: self._choose(1)); s2.clicked.connect(lambda: self._choose(2)); go.clicked.connect(self._process); cancel.clicked.connect(self.reject); _fit_center(self, 480, 380)

    def _choose(self, which: int) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select File", str(self.viewer.file_path.parent), "SEG-D (*.segd *.seg *.dat *.bin);;All files (*.*)")
        if path:
            if which == 1: self.file1 = path; self.f1.setText(Path(path).name)
            else: self.file2 = path; self.f2.setText(Path(path).name)

    def _process(self) -> None:
        if not self.file1 or not self.file2:
            QMessageBox.information(self, "Sum/Difference", "Select both files first."); return
        r1, r2 = SegdReader(Path(self.file1)), SegdReader(Path(self.file2)); n = min(r1.get_trace_count(), r2.get_trace_count()); s = min(r1.get_sample_count(), r2.get_sample_count())
        d1 = r1.read_channel_data((0,n),0,(0,s)).astype(float); d2 = r2.read_channel_data((0,n),0,(0,s)).astype(float)
        if self.norm_check.isChecked():
            d1 = d1 / np.maximum(np.max(np.abs(d1), axis=1, keepdims=True), 1e-12); d2 = d2 / np.maximum(np.max(np.abs(d2), axis=1, keepdims=True), 1e-12)
        result = d1 + d2 if self.sum_radio.isChecked() else d1 - d2; op_name = "sum" if self.sum_radio.isChecked() else "difference"
        out, _ = QFileDialog.getSaveFileName(self, "Save Result", f"record_{op_name}.npz", "NPZ (*.npz)")
        if out: np.savez_compressed(out, data=result)
        self.read1.setText(f"{Path(self.file1).name}: {n} traces"); self.read2.setText(f"{Path(self.file2).name}: {n} traces"); self.operation_field.setText(f"{op_name.title()} complete")


class FiltersDialog(QDialog):
    def __init__(self, viewer: Any) -> None:
        super().__init__(viewer); self.viewer = viewer; self.setWindowTitle("Filters"); self.setStyleSheet(TOOL_STYLE)
        root = QVBoxLayout(self); grid = QGridLayout(); root.addLayout(grid)
        for i, h in enumerate(("F1","F2","F3","F4"), start=1): grid.addWidget(QLabel(h),0,i)
        self.rows = {}
        for r, (name, vals) in enumerate((("Low Cut",(8,12,"","")), ("High Cut",(70,90,"","")), ("Band Pass",(8,12,70,90)), ("Band Reject",(47,49,51,53))), start=1):
            chk = QCheckBox(name); grid.addWidget(chk,r,0); edits=[]
            for c, val in enumerate(vals, start=1):
                e = _field(str(val), 46); edits.append(e); grid.addWidget(e,r,c)
            self.rows[name]=(chk,edits)
        self.progress = QProgressBar(); root.addSpacing(20); root.addWidget(self.progress)
        buttons = QHBoxLayout(); buttons.addStretch(1); ok = _button("OK","green",100); cancel = _button("Cancel","red",100); buttons.addWidget(ok); buttons.addWidget(cancel); root.addLayout(buttons)
        ok.clicked.connect(self._apply); cancel.clicked.connect(self.reject); _fit_center(self, 520, 310)

    def _apply(self) -> None:
        selected = None
        for name, (chk, edits) in self.rows.items():
            if chk.isChecked(): selected=(name,edits); break
        if selected is None:
            self.viewer._filter_enabled = False
        else:
            name, edits = selected; vals = [float(e.text() or 0) for e in edits]
            self.viewer._filter_enabled = True
            if name == "Low Cut": self.viewer._filter_low_hz, self.viewer._filter_high_hz = vals[0], 0.0
            elif name == "High Cut": self.viewer._filter_low_hz, self.viewer._filter_high_hz = 0.0, vals[0]
            elif name == "Band Pass": self.viewer._filter_low_hz, self.viewer._filter_high_hz = vals[1] or vals[0], vals[2] or vals[3]
            else:
                self.viewer._filter_low_hz, self.viewer._filter_high_hz = 0.0, 0.0
                QMessageBox.information(self, "Band Reject", "Band-reject setup is saved in the dialog; display renderer remains raw for reject mode.")
        self.progress.setValue(100); self.viewer.render_current_view(); self.accept()


class FilterPanelsDialog(QDialog):
    def __init__(self, viewer: Any) -> None:
        super().__init__(viewer); self.viewer = viewer; self.folder = ""; self.setWindowTitle("Filter Panels"); self.setStyleSheet(TOOL_STYLE)
        root = QHBoxLayout(self); root.setContentsMargins(8,8,8,8); root.setSpacing(8)
        left = QVBoxLayout(); root.addLayout(left, 0)
        select = _button("Select Folder", "blue", 150); select.clicked.connect(self._choose_folder); left.addWidget(select)
        rng = QGroupBox("Specify Range"); rg = QGridLayout(rng); self.trace_from=_field("40",55); self.trace_to=_field("200",55); self.time_from=_field("1000",65); self.time_to=_field("2000",65)
        for i,(lab,e) in enumerate((("Trace From",self.trace_from),("Trace To",self.trace_to),("Time From (mS)",self.time_from),("Time To (mS)",self.time_to))): rg.addWidget(QLabel(lab),i,0); rg.addWidget(e,i,1)
        left.addWidget(rng)
        gain = QGroupBox("Gains"); gg = QGridLayout(gain); self.initial_gain=_field("24",55); self.trace_clip=_field(".7",55); self.agc_check=QCheckBox("AGC Window"); self.agc_window=_field(".5",55)
        gg.addWidget(QLabel("Initial Gain dB"),0,0); gg.addWidget(self.initial_gain,0,1); gg.addWidget(QLabel("Trace Clip"),1,0); gg.addWidget(self.trace_clip,1,1); gg.addWidget(self.agc_check,2,0); gg.addWidget(self.agc_window,2,1)
        for i,(txt,fn) in enumerate((("Gain +",lambda:self._change_gain(3)),("Gain -",lambda:self._change_gain(-3)),("Set",self._apply_preview))): b=_button(txt,"orange",58); b.clicked.connect(fn); gg.addWidget(b,3,i)
        left.addWidget(gain)
        filters_box = QGroupBox("Specify Filters to Try on Each File"); fl = QGridLayout(filters_box); self.filter_checks=[]
        defaults=[(1,8,12,60,70,True),(2,9,13,65,75,True),(3,10,14,70,80,True),(4,11,15,75,85,False),(5,12,16,80,95,False),(6,13,17,85,100,False)]
        for row,(idx,a,b,c,d,on) in enumerate(defaults):
            chk=QCheckBox(f"BP Filter {idx}"); chk.setChecked(on); edits=[_field(str(x),35) for x in (a,b,c,d)]; test=_button("Test","green",44); test.clicked.connect(lambda _=False, ed=edits: self._test_filter(ed))
            fl.addWidget(chk,row,0); [fl.addWidget(ed,row,i+1) for i,ed in enumerate(edits)]; fl.addWidget(test,row,5); self.filter_checks.append((chk,*edits))
        left.addWidget(filters_box)
        self.file_list=QListWidget(); self.file_list.setMaximumWidth(240); self.file_list.currentRowChanged.connect(self._apply_preview); left.addWidget(self.file_list,1)
        self.header_line=_field("Sweep Tests ...",210); self.info_line=_field("Crew 123",210); left.addWidget(QLabel("Header Line")); left.addWidget(self.header_line); left.addWidget(QLabel("Info Line")); left.addWidget(self.info_line); self.generate_bmp=QCheckBox("Generate BMP Files"); left.addWidget(self.generate_bmp)
        btnrow=QHBoxLayout();
        for txt,fn,role in (("Go",self._go,"green"),("Save",self._save_cfg,"blue"),("Load",self._load_cfg,"purple"),("Cancel",self.reject,"red")):
            b=_button(txt,role,60); b.clicked.connect(fn); btnrow.addWidget(b)
        left.addLayout(btnrow)
        right=QVBoxLayout(); root.addLayout(right,1); self.preview=pg.PlotWidget(); self.preview.setBackground("#FFFFFF"); self.preview.showGrid(x=True,y=True,alpha=0.2); right.addWidget(self.preview,1)
        opts=QGroupBox(""); og=QGridLayout(opts); self.display_trace=QRadioButton("Display Traces"); self.display_fft=QRadioButton("Display FFT"); self.display_energy=QRadioButton("Display Energy Distribution"); self.display_trace.setChecked(True)
        for i,w in enumerate((self.display_trace,self.display_fft,self.display_energy)): og.addWidget(w,0,i)
        self.wiggle=QRadioButton("Wiggle"); self.va_plus=QRadioButton("VA+"); self.va_minus=QRadioButton("VA-"); self.va_both=QRadioButton("VA Both"); self.wiggle.setChecked(True)
        for i,w in enumerate((self.wiggle,self.va_plus,self.va_minus,self.va_both)): og.addWidget(w,1+i,0)
        self.gradient_fill=QCheckBox("Gradient Fill"); og.addWidget(self.gradient_fill,5,0); og.addWidget(QLabel("Max"),1,1); self.max_edit=_field("100",55); self.max2_edit=_field("100",55); og.addWidget(self.max_edit,1,2); og.addWidget(self.max2_edit,1,3)
        self.norm_trace=QRadioButton("Normalise Peak Trace"); self.norm_panel=QRadioButton("Normalise Peak Panel"); self.norm_trace.setChecked(True); og.addWidget(self.norm_trace,2,2,1,2); og.addWidget(self.norm_panel,3,2,1,2); og.addWidget(QLabel("Floor (-dB)"),4,2); self.floor_edit=_field("40",55); og.addWidget(self.floor_edit,4,3)
        right.addWidget(opts)
        _fit_center(self, 1160, 680)

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self,"Select Folder",str(self.viewer.file_path.parent))
        if not folder: return
        self.folder=folder; self.file_list.clear()
        for p in sorted(Path(folder).glob("*")):
            if p.is_file() and p.suffix.lower() in {".segd",".seg",".dat",".bin"}: self.file_list.addItem(str(p))
        if self.file_list.count(): self.file_list.setCurrentRow(0)

    def _preview_file(self) -> Path:
        item=self.file_list.currentItem(); return Path(item.text()) if item else self.viewer.file_path
    def _change_gain(self, delta: float) -> None:
        self.initial_gain.setText(str(int(float(self.initial_gain.text() or 24)+delta))); self._apply_preview()
    def _read_window(self, low: float | None=None, high: float | None=None) -> tuple[np.ndarray,float]:
        path=self._preview_file(); reader=self.viewer.reader if path==self.viewer.file_path else SegdReader(path)
        t0=max(0,int(float(self.trace_from.text() or 1))-1); t1=min(reader.get_trace_count(),int(float(self.trace_to.text() or reader.get_trace_count())))
        si=max(0,int(float(self.time_from.text() or 0)/max(reader.get_sample_interval(),1e-12))); ei=min(reader.get_sample_count(),int(float(self.time_to.text() or reader.get_sample_count())/max(reader.get_sample_interval(),1e-12)))
        data=reader.read_channel_data((t0,t1),0,(si,ei)).astype(float)
        if (low or high) and data.size:
            try:
                from scipy.signal import butter, sosfiltfilt
                fs=1000.0/max(float(reader.get_sample_interval()),1e-12); ny=fs*0.5
                if low and high and 0<low<high<ny: sos=butter(4,[low/ny,high/ny],btype='bandpass',output='sos')
                elif low and 0<low<ny: sos=butter(4,low/ny,btype='highpass',output='sos')
                elif high and 0<high<ny: sos=butter(4,high/ny,btype='lowpass',output='sos')
                else: sos=None
                if sos is not None: data=sosfiltfilt(sos,data,axis=1)
            except Exception: pass
        data*=10.0**(float(self.initial_gain.text() or 24)/20.0); return data,float(reader.get_sample_interval())
    def _apply_preview(self,*args) -> None:
        data,dt=self._read_window(); self.preview.clear()
        if data.size==0: return
        if self.display_fft.isChecked():
            tr=np.mean(data,axis=0); spec=np.abs(np.fft.rfft(tr*np.hanning(tr.size))); freq=np.fft.rfftfreq(tr.size,d=dt/1000.0); self.preview.plot(freq,20*np.log10(np.maximum(spec,1e-12)),pen=pg.mkPen('#0A6BC7',width=2))
        elif self.display_energy.isChecked():
            img=pg.ImageItem(data**2); img.setLookupTable(_spectral_lut()); self.preview.addItem(img)
        else:
            ns=data.shape[1]; t=np.arange(ns)*dt; step=max(1,int(np.ceil(data.shape[0]/16))); scale=max(np.max(np.abs(data)),1e-9)
            for i,tr in enumerate(data[::step]): self.preview.plot(t,tr+i*scale*1.4,pen=pg.mkPen('#000',width=1))
    def _test_filter(self, edits: list[QLineEdit]) -> None:
        low=float(edits[1].text() or edits[0].text() or 0); high=float(edits[2].text() or edits[3].text() or 0); data,dt=self._read_window(low,high); self._apply_preview()
    def _go(self) -> None:
        if not self.folder: self._choose_folder()
        for i in range(self.file_list.count()):
            self.file_list.setCurrentRow(i); self._apply_preview(); QApplication.processEvents()
            if self.generate_bmp.isChecked(): self.preview.grab().save(str(Path(self.file_list.item(i).text()).with_suffix('.bmp')))
        QMessageBox.information(self,"Filter Panels","Batch test finished.")
    def _save_cfg(self) -> None:
        path,_=QFileDialog.getSaveFileName(self,"Save Filter Panel Setup","filter_panels.json","JSON (*.json)")
        if path: Path(path).write_text(json.dumps({'trace_from':self.trace_from.text(),'trace_to':self.trace_to.text(),'time_from':self.time_from.text(),'time_to':self.time_to.text(),'initial_gain':self.initial_gain.text()},indent=2),encoding='utf-8')
    def _load_cfg(self) -> None:
        path,_=QFileDialog.getOpenFileName(self,"Load Filter Panel Setup","","JSON (*.json)")
        if not path: return
        cfg=json.loads(Path(path).read_text(encoding='utf-8'))
        for name in ('trace_from','trace_to','time_from','time_to','initial_gain'):
            getattr(self,name).setText(str(cfg.get(name,getattr(self,name).text())))
        self._apply_preview()


class TraceAnalysisOptionsDialog(QDialog):
    def __init__(self, viewer: Any) -> None:
        super().__init__(viewer); self.viewer=viewer; self.setWindowTitle("Trace Analysis"); self.setStyleSheet(TOOL_STYLE)
        root=QVBoxLayout(self)
        a=QGroupBox("Analyse"); av=QVBoxLayout(a); self.a_rms=QRadioButton("RMS"); self.a_avg=QRadioButton("Average"); self.a_pos=QRadioButton("Positive Peak"); self.a_abs=QRadioButton("Absolute Peak"); self.a_fft=QRadioButton("Fundamental Peak (FFT Peak)"); self.a_elev=QRadioButton("Elevation"); self.a_rms.setChecked(True)
        for w in (self.a_rms,self.a_avg,self.a_pos,self.a_abs,self.a_fft,self.a_elev): av.addWidget(w)
        root.addWidget(a); n=QGroupBox("Normalisation"); nv=QVBoxLayout(n); self.n_peak=QRadioButton("Normalised to Peak"); self.n_avg=QRadioButton("Normalised to Average"); self.n_raw=QRadioButton("Raw Values"); self.n_raw.setChecked(True); self.debiased=QCheckBox("Debiased (Ignore highest and lowest 10%)"); self.ignore_aux=QCheckBox("Ignore Aux Traces"); self.ignore_aux.setChecked(True)
        for w in (self.n_peak,self.n_avg,self.n_raw,self.debiased,self.ignore_aux): nv.addWidget(w)
        root.addWidget(n); d=QGroupBox("Display"); dv=QVBoxLayout(d); self.d_raw=QRadioButton("Raw Results"); self.d_peak=QRadioButton("% Deviation From Peak"); self.d_avgd=QRadioButton("% Deviation From Average"); self.d_raw.setChecked(True); self.debias_display=QCheckBox("Debias"); self.ignore_aux_display=QCheckBox("Ignore Aux"); self.out_list=QRadioButton("Display as List"); self.out_graph=QRadioButton("Display Graphically"); self.out_list.setChecked(True)
        for w in (self.d_raw,self.d_peak,self.d_avgd,self.debias_display,self.ignore_aux_display,self.out_list,self.out_graph): dv.addWidget(w)
        root.addWidget(d); btns=QHBoxLayout(); btns.addStretch(1); go=_button("Go","green",90); cancel=_button("Cancel","red",90); go.clicked.connect(self._go); cancel.clicked.connect(self.reject); btns.addWidget(go); btns.addWidget(cancel); root.addLayout(btns); _fit_center(self, 400, 530)
    def _go(self) -> None:
        data=getattr(self.viewer,"_raw_data",np.array([]))
        if not isinstance(data,np.ndarray) or data.size==0: QMessageBox.information(self,"Trace Analysis","Render traces first."); return
        data=data.astype(float)
        if self.a_rms.isChecked(): metric=np.sqrt(np.mean(data**2,axis=1)); title="RMS"
        elif self.a_avg.isChecked(): metric=np.mean(data,axis=1); title="Average"
        elif self.a_pos.isChecked(): metric=np.max(data,axis=1); title="Positive Peak"
        elif self.a_abs.isChecked(): metric=np.max(np.abs(data),axis=1); title="Absolute Peak"
        elif self.a_fft.isChecked():
            dt=max(float(self.viewer.reader.get_sample_interval()),1e-12)/1000.0; vals=[]
            for tr in data:
                spec=np.abs(np.fft.rfft(tr-np.mean(tr))); freq=np.fft.rfftfreq(tr.size,d=dt); vals.append(float(freq[np.argmax(spec[1:])+1]) if spec.size>1 else 0.0)
            metric=np.array(vals); title="FFT Peak Hz"
        else: metric=np.arange(1,data.shape[0]+1,dtype=float); title="Elevation/Index"
        if self.debiased.isChecked() and metric.size>10:
            lo,hi=np.percentile(metric,[10,90]); metric=np.clip(metric,lo,hi)
        if self.n_peak.isChecked(): metric=metric/max(float(np.max(np.abs(metric))),1e-12)
        elif self.n_avg.isChecked(): metric=metric/max(float(np.mean(np.abs(metric))),1e-12)
        plot=pg.PlotWidget(); plot.setBackground('#FFF'); plot.showGrid(x=True,y=True,alpha=0.2); plot.plot(np.arange(1,len(metric)+1),metric,pen=pg.mkPen('#0A6BC7',width=2))
        dlg=QDialog(self); dlg.setWindowTitle(f"Trace Analysis - {title}"); dlg.setStyleSheet(TOOL_STYLE); lay=QVBoxLayout(dlg); lay.addWidget(plot); lay.addWidget(QLabel(f"Count {len(metric):,} | Mean {_format_number(np.mean(metric),5)} | Peak {_format_number(np.max(metric),5)}")); close=_button("Close","red",90); close.clicked.connect(dlg.accept); lay.addWidget(close,0,Qt.AlignmentFlag.AlignRight); _fit_center(dlg,760,520); dlg.exec(); self.accept()


class DsdBinFilesDialog(QDialog):
    def __init__(self, viewer: Any) -> None:
        super().__init__(viewer); self.viewer=viewer; self.path=""; self.setWindowTitle("DSD Bin Files"); self.setStyleSheet(TOOL_STYLE)
        root=QVBoxLayout(self); top=QGridLayout(); root.addLayout(top); openb=_button("Open","blue",100); process=_button("Process","green",100); cancel=_button("Cancel","red",100); top.addWidget(openb,0,0); top.addWidget(process,0,1); top.addWidget(cancel,0,2)
        self.file_name=_field(width=150); self.current_filename=_field(width=360); self.samples=_field(width=110); self.samples2=_field(width=110); top.addWidget(QLabel("File Name"),0,3); top.addWidget(self.file_name,0,4); top.addWidget(self.current_filename,0,5); top.addWidget(QLabel("Samples"),1,3); top.addWidget(self.samples,1,4); top.addWidget(self.samples2,1,5)
        self.blocks=[]
        for name in ("Ref","BP","Mass","Force"):
            row=QHBoxLayout(); lab=QLabel(name); lab.setFixedWidth(45); row.addWidget(lab); box=QPlainTextEdit(); box.setMinimumHeight(90); row.addWidget(box,1); self.blocks.append((name,box)); root.addLayout(row)
        root.addWidget(QLabel("Time")); self.time_bar=QProgressBar(); root.addWidget(self.time_bar); openb.clicked.connect(self._open); process.clicked.connect(self._process); cancel.clicked.connect(self.reject); _fit_center(self,1040,680)
    def _open(self) -> None:
        path,_=QFileDialog.getOpenFileName(self,"Open DSD / Binary File",str(self.viewer.file_path.parent),"Binary files (*.bin *.dsd *.dat);;All files (*.*)")
        if path: self.path=path; self.file_name.setText(Path(path).name); self.current_filename.setText(path)
    def _process(self) -> None:
        if not self.path: self._open()
        if not self.path: return
        raw=Path(self.path).read_bytes(); self.samples.setText(str(len(raw))); self.samples2.setText(str(len(raw))); section=max(1,len(raw)//4)
        for i,(_name,box) in enumerate(self.blocks):
            chunk=raw[i*section:(i+1)*section][:512]; lines=[]
            for off in range(0,len(chunk),16):
                c=chunk[off:off+16]; hx=' '.join(f'{b:02X}' for b in c); asc=''.join(chr(b) if 32<=b<127 else '.' for b in c); lines.append(f"{off:06X}  {hx:<47}  {asc}")
            box.setPlainText('\n'.join(lines)); self.time_bar.setValue(int((i+1)/4*100)); QApplication.processEvents()



def radio_sims(viewer: Any) -> None:
    """Compact radio/QC flag summary retained as a functional SEG-D tool."""
    if getattr(viewer, "reader", None) is None:
        QMessageBox.information(viewer, "Radio Sims", "Open a SEG-D file first.")
        return
    categories = ["None", "Auxiliary", "Resistance", "Capacitance", "Leakage", "Tilt", "Multiple", "Other"]
    counts = {name: 0 for name in categories}
    rows = []
    for i in range(viewer.reader.get_trace_count()):
        ti = viewer.reader.get_trace_info(i)
        status = _status_from_trace_info(ti)
        if status not in counts:
            status = "Other"
        counts[status] += 1
        rows.append((i + 1, getattr(ti, "receiver_line", ""), getattr(ti, "receiver_point", ""), status))
    dlg = QDialog(viewer)
    dlg.setWindowTitle("Radio Sims / QC Flags")
    dlg.setStyleSheet(TOOL_STYLE)
    root = QVBoxLayout(dlg)
    plot = pg.PlotWidget()
    plot.setBackground("#FFFFFF")
    plot.showGrid(x=False, y=True, alpha=0.22)
    x = np.arange(len(categories))
    heights = [counts[c] for c in categories]
    plot.addItem(pg.BarGraphItem(x=x, height=heights, width=0.62, brush="#0A86C7"))
    plot.getAxis("bottom").setTicks([[(i, c) for i, c in enumerate(categories)]])
    root.addWidget(plot, 1)
    summary = QLabel("  |  ".join(f"{c}: {counts[c]}" for c in categories))
    summary.setWordWrap(True)
    root.addWidget(summary)
    close = _button("Close", "red", 90)
    close.clicked.connect(dlg.accept)
    root.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
    _fit_center(dlg, 760, 500)
    dlg.exec()


def multi_vib_sim(viewer: Any) -> None:
    data = getattr(viewer, "_raw_data", np.array([]))
    if not isinstance(data, np.ndarray) or data.size == 0:
        QMessageBox.information(viewer, "Multi Vib Sim", "Render traces first.")
        return
    n = min(48, data.shape[0])
    x = data[:n].astype(float)
    x -= np.mean(x, axis=1, keepdims=True)
    norm = np.linalg.norm(x, axis=1)
    norm[norm < 1e-12] = 1.0
    corr = (x @ x.T) / (norm[:, None] * norm[None, :])
    dlg = QDialog(viewer)
    dlg.setWindowTitle("Multi Vib Similarity")
    dlg.setStyleSheet(TOOL_STYLE)
    root = QVBoxLayout(dlg)
    plot = pg.PlotWidget()
    plot.setBackground("#FFFFFF")
    image = pg.ImageItem(corr)
    image.setLookupTable(_spectral_lut())
    image.setLevels([-1, 1])
    image.setRect(QRectF(1, 1, n, n))
    plot.addItem(image)
    plot.setLabel("bottom", "Trace Index")
    plot.setLabel("left", "Trace Index")
    root.addWidget(plot, 1)
    tri = np.abs(corr[np.triu_indices(n, 1)]) if n > 1 else np.array([0.0])
    root.addWidget(QLabel(f"Traces: {n}  |  Mean |Corr|: {np.mean(tri):.3f}  |  Pairs > 0.90: {np.count_nonzero(tri > 0.90)}"))
    close = _button("Close", "red", 90)
    close.clicked.connect(dlg.accept)
    root.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
    _fit_center(dlg, 760, 520)
    dlg.exec()

def spread_view(viewer: Any) -> None:
    if getattr(viewer, "reader", None) is None:
        QMessageBox.information(viewer, "Spread View", "Open a SEG-D file first."); return
    SpreadViewDialog(viewer).exec()


def split_proc_file(viewer: Any) -> None:
    FileSplitterDialog(viewer).exec()


def fix_radio_sim_file(viewer: Any) -> None:
    FixRadioSimDialog(viewer).exec()


def record_sum_diff(viewer: Any) -> None:
    RecordSumDiffDialog(viewer).exec()


def filters(viewer: Any) -> None:
    FiltersDialog(viewer).exec()


def panels(viewer: Any) -> None:
    FilterPanelsDialog(viewer).exec()


def trace_analysis(viewer: Any) -> None:
    TraceAnalysisOptionsDialog(viewer).exec()


def dsd_bin_files(viewer: Any) -> None:
    DsdBinFilesDialog(viewer).exec()
