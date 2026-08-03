from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


DIALOG_STYLE = """
    QDialog { background:#EEF4F8; }
    QFrame#headerCard, QFrame#metricCard, QFrame#plotCard { background:#FFFFFF; border:1px solid #D5E1EA; border-radius:8px; }
    QLabel { background:transparent; }
    QLabel#titleLabel { color:#102A3D; font-size:14px; font-weight:900; }
    QLabel#subtleLabel { color:#607486; font-size:10px; }
    QLabel#metricTitle { color:#607486; font-size:10px; font-weight:800; }
    QLabel#metricValue { color:#102A3D; font-size:15px; font-weight:900; }
    QPushButton { min-height:27px; padding:4px 12px; border-radius:6px; border:1px solid #9FB2C3; background:#FFFFFF; font-weight:700; color:#173B53; }
    QPushButton:hover { background:#E2F0FA; border-color:#3A8BC2; }
    QPushButton#primaryButton { background:#E7F3FF; color:#0B5D8A; border-color:#7DB3D8; }
    QPushButton#exportButton { background:#EAF8EF; color:#216A3A; border-color:#82C79B; }
    QPushButton#dangerButton { background:#FDEBEC; color:#A12D34; border-color:#E5A0A5; }
    QPushButton#modeButton { text-align:left; padding-left:10px; background:#FFFFFF; border-left:4px solid #0A86C7; }
    QPushButton#modeButton:checked { background:#DCEFFA; color:#0A5E8D; border-color:#76B7DC; border-left:4px solid #D58B00; }
    QSpinBox,QDoubleSpinBox { background:#FFFFFF; border:1px solid #A9BAC8; border-radius:5px; padding:3px; min-height:25px; }
    QTableWidget { background:#FFFFFF; alternate-background-color:#F4F8FB; border:1px solid #D5E1EA; gridline-color:#E4ECF2; }
    QHeaderView::section { background:#173B53; color:white; padding:5px; border:0; font-weight:800; }
"""


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


def _metric_card(title: str, value: str, accent: str = "#0A86C7") -> QFrame:
    card = QFrame()
    card.setObjectName("metricCard")
    card.setStyleSheet(f"QFrame#metricCard{{border-left:5px solid {accent};}}")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(10, 7, 10, 7)
    layout.setSpacing(1)
    t = QLabel(title)
    t.setObjectName("metricTitle")
    v = QLabel(value)
    v.setObjectName("metricValue")
    layout.addWidget(t)
    layout.addWidget(v)
    return card


def _spectral_lut() -> np.ndarray:
    stops = np.array(
        [[18, 36, 82], [18, 96, 160], [19, 166, 185], [255, 213, 79], [218, 60, 45]],
        dtype=float,
    )
    positions = np.linspace(0.0, 1.0, len(stops))
    x = np.linspace(0.0, 1.0, 256)
    lut = np.vstack([np.interp(x, positions, stops[:, c]) for c in range(3)]).T
    return np.clip(lut, 0, 255).astype(np.ubyte)


def _build_table(headers: list[str], rows: list[list[Any]], max_height: int | None = None) -> QTableWidget:
    table = QTableWidget(len(rows), len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            item = QTableWidgetItem(str(value))
            if isinstance(value, (int, float, np.integer, np.floating)):
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(r, c, item)
    if max_height is not None:
        table.setMaximumHeight(max_height)
    return table


def _show_text(parent: QWidget, title: str, text: str) -> None:
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.resize(760, 500)
    dlg.setStyleSheet(DIALOG_STYLE)
    lay = QVBoxLayout(dlg)
    edit = QPlainTextEdit()
    edit.setReadOnly(True)
    edit.setPlainText(text)
    edit.setStyleSheet("background:#FFFFFF;border:1px solid #D5E1EA;border-radius:6px;font-family:Consolas,monospace;")
    lay.addWidget(edit)
    close = QPushButton("Close")
    close.setObjectName("dangerButton")
    close.clicked.connect(dlg.accept)
    lay.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
    dlg.exec()


class _SpreadCanvas(QWidget):
    """428-style receiver-spread QC canvas based on decoded SEG-D trace extensions."""

    STATUS_COLORS = {
        "None": QColor("#00B050"),
        "Leakage": QColor("#1C4FD7"),
        "Tilt": QColor("#D719E8"),
        "Multiple": QColor("#F1D302"),
        "Capacitance": QColor("#111111"),
        "Resistance": QColor("#E01E1E"),
        "Other": QColor("#16C7CA"),
        "Missing": QColor("#9AA7B2"),
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(680, 360)
        self._rows: list[dict[str, Any]] = []
        self._mode = "Errors"
        self._slice_values: dict[int, float] = {}
        self._normalise_trace_peak = False

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.update()

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self._slice_values = {}
        self.update()

    def set_slice(self, mode: str, values: dict[int, float]) -> None:
        self._mode = mode
        self._slice_values = values
        self.update()

    def set_trace_peak_normalisation(self, enabled: bool) -> None:
        self._normalise_trace_peak = bool(enabled)
        self.update()

    @staticmethod
    def _finite(value: Any) -> bool:
        try:
            return bool(np.isfinite(float(value)))
        except Exception:
            return False

    @classmethod
    def _status(cls, row: dict[str, Any]) -> str:
        flags = [str(v).lower() for v in row.get("flags", ())]
        failures = []
        for label, value_key, low_key, high_key in (
            ("Resistance", "resistance", "resistance_low", "resistance_high"),
            ("Capacitance", "capacitance", "capacitance_low", "capacitance_high"),
        ):
            value, lo, hi = row.get(value_key), row.get(low_key), row.get(high_key)
            if cls._finite(value):
                if cls._finite(lo) and float(value) < float(lo):
                    failures.append(label)
                if cls._finite(hi) and float(value) > float(hi):
                    failures.append(label)
        for label, value_key, limit_key in (
            ("Leakage", "leakage", "leakage_limit"),
            ("Tilt", "tilt", "tilt_limit"),
        ):
            value, limit = row.get(value_key), row.get(limit_key)
            if cls._finite(value) and cls._finite(limit) and abs(float(value)) > abs(float(limit)):
                failures.append(label)
        for label in ("resistance", "capacitance", "leakage", "tilt"):
            if any(label in flag for flag in flags):
                failures.append(label.title())
        failures = list(dict.fromkeys(failures))
        if len(failures) > 1:
            return "Multiple"
        if failures:
            return failures[0]
        if flags:
            return "Other"
        return "None"

    def _metric_state(self, row: dict[str, Any]) -> tuple[float | None, str]:
        mapping = {
            "Resistance": ("resistance", "resistance_low", "resistance_high"),
            "Capacitance": ("capacitance", "capacitance_low", "capacitance_high"),
            "Leakage": ("leakage", None, "leakage_limit"),
            "Tilt": ("tilt", None, "tilt_limit"),
        }
        if self._mode not in mapping:
            return None, "missing"
        key, lo_key, hi_key = mapping[self._mode]
        value = row.get(key)
        if not self._finite(value):
            return None, "missing"
        failed = False
        has_limit = False
        if lo_key and self._finite(row.get(lo_key)):
            has_limit = True
            if float(value) < float(row[lo_key]):
                failed = True
        if hi_key and self._finite(row.get(hi_key)):
            has_limit = True
            if abs(float(value)) > abs(float(row[hi_key])):
                failed = True
        if failed:
            return float(value), "failed"
        if not has_limit:
            return float(value), "value_only"
        return float(value), "ok"

    @staticmethod
    def _slice_color(value: float, scale: float) -> QColor:
        frac = min(1.0, abs(float(value)) / max(scale, 1e-12))
        if frac < 0.33:
            return QColor.fromHsv(205, int(160 + frac * 180), 230)
        if frac < 0.70:
            return QColor.fromHsv(120 - int((frac - 0.33) * 150), 230, 245)
        return QColor.fromHsv(max(0, 42 - int((frac - 0.70) * 140)), 240, 245)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(self.rect(), QColor("#F7FAFC"))
        if not self._rows:
            painter.setPen(QColor("#777777"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No receiver spread data")
            return

        plot = QRectF(58, 38, max(220, self.width() - 168), max(180, self.height() - 88))
        painter.setPen(QPen(QColor("#A7B3BE"), 1))
        painter.fillRect(plot, QColor("#FFFFFF"))
        painter.drawRect(plot)
        painter.setFont(QFont(painter.font().family(), 11, QFont.Weight.Bold))
        painter.setPen(QColor("#102A3D"))
        painter.drawText(QRectF(plot.left(), 6, plot.width(), 26), Qt.AlignmentFlag.AlignCenter, self._mode)

        lines = sorted({float(r["line"]) for r in self._rows})
        points = [float(r["point"]) for r in self._rows]
        pmin, pmax = min(points), max(points)
        if pmax <= pmin:
            pmax = pmin + 1.0
        line_y = {line: plot.top() + (i + 0.5) * plot.height() / max(1, len(lines)) for i, line in enumerate(lines)}

        painter.setFont(QFont(painter.font().family(), 8, QFont.Weight.Bold))
        painter.setPen(QColor("#173B53"))
        for line, y in line_y.items():
            painter.drawText(QRectF(4, y - 10, 50, 20), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{line:g}")
            painter.setPen(QPen(QColor("#ECF1F5"), 1))
            painter.drawLine(plot.left(), y, plot.right(), y)
            painter.setPen(QColor("#173B53"))

        unique_points = len({round(p, 6) for p in points})
        bin_w = max(3.0, min(26.0, plot.width() / max(1, min(420, unique_points))))
        slice_abs = np.array([abs(v) for v in self._slice_values.values() if np.isfinite(v)], dtype=float)
        slice_scale = float(np.nanpercentile(slice_abs, 98)) if slice_abs.size else 1.0
        slice_scale = max(slice_scale, 1e-12)
        for row in self._rows:
            x = plot.left() + (float(row["point"]) - pmin) / (pmax - pmin) * plot.width()
            y = line_y[float(row["line"])]
            if self._mode in {"TSlice", "FSlice"}:
                value = self._slice_values.get(int(row["index"]), np.nan)
                color = QColor("#CCD6DF") if not np.isfinite(value) else self._slice_color(value, slice_scale)
            elif self._mode == "Errors":
                color = self.STATUS_COLORS[self._status(row)]
            else:
                _, state = self._metric_state(row)
                color = {
                    "ok": QColor("#00B050"),
                    "failed": QColor("#E01E1E"),
                    "value_only": QColor("#0A86C7"),
                    "missing": QColor("#9AA7B2"),
                }[state]
            painter.fillRect(QRectF(x - bin_w / 2, y - 8, bin_w + 1, 16), QBrush(color))

        painter.setFont(QFont(painter.font().family(), 8))
        painter.setPen(QColor("#3F5363"))
        for frac in np.linspace(0, 1, 6):
            x = plot.left() + frac * plot.width()
            val = pmin + frac * (pmax - pmin)
            painter.drawLine(x, plot.bottom(), x, plot.bottom() + 4)
            painter.drawText(QRectF(x - 38, plot.bottom() + 7, 76, 18), Qt.AlignmentFlag.AlignCenter, f"{val:g}")
        painter.drawText(QRectF(plot.left(), self.height() - 22, plot.width(), 18), Qt.AlignmentFlag.AlignCenter, "Receiver Point / Position")

        lx = plot.right() + 12
        ly = plot.top() + 10
        painter.setFont(QFont(painter.font().family(), 8, QFont.Weight.Bold))
        if self._mode == "Errors":
            legend_items = [(k, v) for k, v in self.STATUS_COLORS.items() if k != "Missing"]
            for idx, (name, color) in enumerate(legend_items):
                col = idx % 2
                row = idx // 2
                xx = lx + col * 68
                yy = ly + row * 22
                painter.fillRect(QRectF(xx, yy, 14, 14), QBrush(color))
                painter.setPen(QColor("#22313C"))
                painter.drawText(int(xx + 18), int(yy + 12), name[:8])
        elif self._mode in {"TSlice", "FSlice"}:
            painter.setPen(QColor("#22313C"))
            painter.drawText(int(lx), int(ly + 12), "Relative")
            painter.drawText(int(lx), int(ly + 28), "magnitude")
        else:
            for idx, (name, color) in enumerate((
                ("OK", QColor("#00B050")),
                ("Fail", QColor("#E01E1E")),
                ("Value", QColor("#0A86C7")),
                ("Missing", QColor("#9AA7B2")),
            )):
                yy = ly + idx * 22
                painter.fillRect(QRectF(lx, yy, 14, 14), QBrush(color))
                painter.setPen(QColor("#22313C"))
                painter.drawText(int(lx + 18), int(yy + 12), name)


class _SpreadViewDialog(QDialog):
    def __init__(self, viewer: Any) -> None:
        super().__init__(viewer)
        self.viewer = viewer
        self.reader = viewer.reader
        self.setWindowTitle("Spread View")
        self.resize(1020, 620)
        self.setMinimumSize(860, 500)
        self.setStyleSheet(DIALOG_STYLE)
        self._rows = self._load_rows()
        self._last_slice: tuple[str, float] | None = None
        self._build_ui()
        self._apply_range()

    def _load_rows(self) -> list[dict[str, Any]]:
        rows = []
        for i in range(self.reader.get_trace_count()):
            ti = self.reader.get_trace_info(i)
            line = float(getattr(ti, "receiver_line", 0.0) or 0.0)
            point = float(getattr(ti, "receiver_point", i + 1) or (i + 1))
            rows.append(
                {
                    "index": i,
                    "line": line,
                    "point": point,
                    "channel_set": getattr(ti, "channel_set", ""),
                    "channel_type": getattr(ti, "channel_type", ""),
                    "trace_edit": getattr(ti, "trace_edit", 0),
                    "flags": tuple(getattr(ti, "qc_flags", ()) or ()),
                    "resistance": getattr(ti, "resistance", None),
                    "resistance_low": getattr(ti, "resistance_low_limit", None),
                    "resistance_high": getattr(ti, "resistance_high_limit", None),
                    "capacitance": getattr(ti, "capacitance", None),
                    "capacitance_low": getattr(ti, "capacitance_low_limit", None),
                    "capacitance_high": getattr(ti, "capacitance_high_limit", None),
                    "leakage": getattr(ti, "leakage", None),
                    "leakage_limit": getattr(ti, "leakage_limit", None),
                    "tilt": getattr(ti, "tilt", None),
                    "tilt_limit": getattr(ti, "tilt_limit", None),
                }
            )
        return rows

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)
        top_card = QFrame(self)
        top_card.setObjectName("headerCard")
        top = QHBoxLayout(top_card)
        top.setContentsMargins(8, 5, 8, 5)
        top.setSpacing(6)
        bmp = QPushButton("BMP")
        bmp.setObjectName("exportButton")
        bmp.clicked.connect(self._export_bmp)
        top.addWidget(bmp)
        ts = QPushButton("T Slice")
        ts.setObjectName("primaryButton")
        ts.clicked.connect(self._time_slice)
        top.addWidget(ts)
        fs = QPushButton("F Slice")
        fs.setObjectName("primaryButton")
        fs.clicked.connect(self._frequency_slice)
        top.addWidget(fs)
        top.addSpacing(8)
        top.addWidget(QLabel("From"))
        self.from_spin = QDoubleSpinBox()
        self.from_spin.setRange(-1e12, 1e12)
        self.from_spin.setDecimals(3)
        top.addWidget(self.from_spin)
        top.addWidget(QLabel("To"))
        self.to_spin = QDoubleSpinBox()
        self.to_spin.setRange(-1e12, 1e12)
        self.to_spin.setDecimals(3)
        top.addWidget(self.to_spin)
        apply_btn = QPushButton("Apply Range")
        apply_btn.setObjectName("primaryButton")
        apply_btn.clicked.connect(self._apply_range)
        top.addWidget(apply_btn)
        top.addSpacing(8)
        top.addWidget(QLabel("Normalisation"))
        self.spread_peak = QRadioButton("Spread Peak")
        self.trace_peak = QRadioButton("Trace Peak")
        self.spread_peak.setChecked(True)
        top.addWidget(self.spread_peak)
        top.addWidget(self.trace_peak)
        top.addStretch(1)
        close = QPushButton("Close")
        close.setObjectName("dangerButton")
        close.clicked.connect(self.accept)
        top.addWidget(close)
        root.addWidget(top_card)
        if self._rows:
            pts = [r["point"] for r in self._rows]
            self.from_spin.setValue(min(pts))
            self.to_spin.setValue(max(pts))

        body = QHBoxLayout()
        body.setSpacing(6)
        modes_frame = QFrame(self)
        modes_frame.setObjectName("headerCard")
        modes = QVBoxLayout(modes_frame)
        modes.setContentsMargins(6, 6, 6, 6)
        modes.setSpacing(5)
        self.mode_group = QButtonGroup(self)
        for mode in ("Resistance", "Capacitance", "Leakage", "Tilt", "Errors"):
            b = QPushButton(mode)
            b.setObjectName("modeButton")
            b.setCheckable(True)
            self.mode_group.addButton(b)
            b.clicked.connect(lambda checked, m=mode: self._set_mode(m))
            modes.addWidget(b)
            if mode == "Errors":
                b.setChecked(True)
        modes.addStretch(1)
        body.addWidget(modes_frame)
        self.canvas = _SpreadCanvas()
        body.addWidget(self.canvas, 1)
        root.addLayout(body, 1)
        bottom = QFrame(self)
        bottom.setObjectName("headerCard")
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(8, 4, 8, 4)
        self.status = QLabel("")
        self.status.setObjectName("subtleLabel")
        self.summary = QLabel("")
        self.summary.setObjectName("subtleLabel")
        bottom_layout.addWidget(self.status, 1)
        bottom_layout.addWidget(self.summary)
        root.addWidget(bottom)
        self.trace_peak.toggled.connect(self._on_normalisation_changed)

    def _selected_rows(self) -> list[dict[str, Any]]:
        lo = min(self.from_spin.value(), self.to_spin.value())
        hi = max(self.from_spin.value(), self.to_spin.value())
        return [r for r in self._rows if lo <= r["point"] <= hi]

    def _status_counts(self, rows: list[dict[str, Any]]) -> dict[str, int]:
        counts = {name: 0 for name in _SpreadCanvas.STATUS_COLORS if name != "Missing"}
        for row in rows:
            counts[_SpreadCanvas._status(row)] = counts.get(_SpreadCanvas._status(row), 0) + 1
        return counts

    def _apply_range(self) -> None:
        rows = self._selected_rows()
        self.canvas.set_rows(rows)
        line_count = len({r["line"] for r in rows})
        counts = self._status_counts(rows)
        fail_count = sum(v for k, v in counts.items() if k != "None")
        self.status.setText(f"Displaying {len(rows):,} of {len(self._rows):,} traces across {line_count:,} receiver lines.")
        self.summary.setText(f"Errors/flags: {fail_count:,}  |  Clean: {counts.get('None', 0):,}")
        if self._last_slice:
            self._refresh_current_slice()

    def _set_mode(self, mode: str) -> None:
        self._last_slice = None
        self.canvas.set_mode(mode)

    def _on_normalisation_changed(self, checked: bool) -> None:
        self.canvas.set_trace_peak_normalisation(checked)
        if self._last_slice:
            self._refresh_current_slice()

    def _refresh_current_slice(self) -> None:
        if not self._last_slice:
            return
        mode, value = self._last_slice
        if mode == "TSlice":
            self._calculate_time_slice(value, prompt=False)
        elif mode == "FSlice":
            self._calculate_frequency_slice(value, prompt=False)

    def _time_slice(self) -> None:
        time_ms, ok = QInputDialog.getDouble(self, "Time Slice", "Time (ms):", 0.0, 0.0, 1e9, 3)
        if not ok:
            return
        self._calculate_time_slice(time_ms, prompt=True)

    def _calculate_time_slice(self, time_ms: float, prompt: bool = False) -> None:
        sample = int(round(time_ms / max(float(self.reader.get_sample_interval()), 1e-12)))
        rows = self._selected_rows()
        values: dict[int, float] = {}
        trace_norm = self.trace_peak.isChecked()
        for row in rows:
            try:
                if trace_norm:
                    data = self.reader.read_channel_data((row["index"], row["index"] + 1), 0, None)
                    if data.size:
                        trace = data[0].astype(float)
                        denom = max(float(np.nanmax(np.abs(trace))), 1e-12)
                        if 0 <= sample < trace.size:
                            values[row["index"]] = float(trace[sample] / denom)
                else:
                    data = self.reader.read_channel_data((row["index"], row["index"] + 1), 0, (sample, sample + 1))
                    if data.size:
                        values[row["index"]] = float(data[0, 0])
            except Exception:
                continue
        self._last_slice = ("TSlice", float(time_ms))
        self.canvas.set_slice("TSlice", values)
        norm_text = "trace-peak normalised" if trace_norm else "spread-peak scaled"
        self.status.setText(f"Time slice at {time_ms:.3f} ms (sample {sample}); {len(values):,} traces evaluated, {norm_text}.")

    def _frequency_slice(self) -> None:
        freq_hz, ok = QInputDialog.getDouble(self, "Frequency Slice", "Frequency (Hz):", 10.0, 0.0, 100000.0, 2)
        if not ok:
            return
        self._calculate_frequency_slice(freq_hz, prompt=True)

    def _calculate_frequency_slice(self, freq_hz: float, prompt: bool = False) -> None:
        rows = self._selected_rows()
        values: dict[int, float] = {}
        dt = max(float(self.reader.get_sample_interval()), 1e-12) / 1000.0
        trace_norm = self.trace_peak.isChecked()
        for row in rows:
            try:
                data = self.reader.read_channel_data((row["index"], row["index"] + 1), 0, None)
                if not data.size:
                    continue
                x = data[0].astype(float)
                x -= np.mean(x)
                win = np.hanning(x.size)
                spec = np.abs(np.fft.rfft(x * win))
                f = np.fft.rfftfreq(x.size, d=dt)
                if not spec.size or not f.size:
                    continue
                k = int(np.argmin(np.abs(f - freq_hz)))
                value = float(spec[k] / max(np.sum(win), 1e-12))
                if trace_norm:
                    value /= max(float(np.nanmax(spec)), 1e-12)
                values[row["index"]] = value
            except Exception:
                continue
        self._last_slice = ("FSlice", float(freq_hz))
        self.canvas.set_slice("FSlice", values)
        norm_text = "trace-spectrum normalised" if trace_norm else "spread-peak scaled"
        self.status.setText(f"Frequency slice near {freq_hz:.2f} Hz; {len(values):,} traces evaluated with Hann-window FFT, {norm_text}.")

    def _export_bmp(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Spread View",
            str(self.viewer.file_path.with_name(self.viewer.file_path.stem + "_spread.bmp")),
            "Bitmap Image (*.bmp)",
        )
        if path:
            self.canvas.grab().save(path)


def spread_view(viewer: Any) -> None:
    if viewer.reader is None:
        QMessageBox.information(viewer, "Spread View", "Open a SEG-D file first.")
        return
    _SpreadViewDialog(viewer).exec()


def split_proc_file(viewer: Any) -> None:
    """Export the selected processing window without pretending to rewrite proprietary SEG-D headers."""
    if viewer.reader is None:
        return
    t0 = min(viewer.trace_start_spin.value(), viewer.trace_end_spin.value()) - 1
    t1 = max(viewer.trace_start_spin.value(), viewer.trace_end_spin.value())
    s0 = min(viewer.sample_start_spin.value(), viewer.sample_end_spin.value()) - 1
    s1 = max(viewer.sample_start_spin.value(), viewer.sample_end_spin.value())
    path, _ = QFileDialog.getSaveFileName(
        viewer,
        "Split Processing File / Export Window",
        str(viewer.file_path.with_name(viewer.file_path.stem + "_subset.npz")),
        "TGPAssure processing subset (*.npz)",
    )
    if not path:
        return
    data = viewer.reader.read_channel_data((t0, t1), 0, (s0, s1))
    meta = {
        "source": str(viewer.file_path),
        "trace_range": [t0, t1],
        "sample_range": [s0, s1],
        "sample_interval_ms": float(viewer.reader.get_sample_interval()),
        "note": "Lossless processing subset; source SEG-D remains unchanged.",
    }
    np.savez_compressed(path, data=data, metadata=json.dumps(meta))
    QMessageBox.information(viewer, "Split Proc File", f"Exported {data.shape[0]} traces × {data.shape[1]} samples.\n\n{path}")


def fix_radio_sim_file(viewer: Any) -> None:
    src, _ = QFileDialog.getOpenFileName(
        viewer,
        "Select Radio Simulation / Sidecar File",
        str(viewer.file_path.parent),
        "Text/data files (*.txt *.csv *.sim *.dat);;All files (*.*)",
    )
    if not src:
        return
    raw = Path(src).read_bytes()
    cleaned = raw.replace(b"\x00", b"").replace(b"\r\r\n", b"\r\n")
    try:
        text = cleaned.decode("utf-8-sig", errors="replace")
        lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
        cleaned = ("\n".join(lines) + "\n").encode("utf-8")
    except Exception:
        pass
    dst, _ = QFileDialog.getSaveFileName(
        viewer,
        "Save Repaired Copy",
        str(Path(src).with_name(Path(src).stem + "_fixed" + Path(src).suffix)),
        "All files (*.*)",
    )
    if not dst:
        return
    Path(dst).write_bytes(cleaned)
    QMessageBox.information(
        viewer,
        "Fix Radio Sim File",
        f"Created a cleaned copy without modifying the source.\nRemoved NUL bytes / malformed line endings where present.\n\n{dst}",
    )


def _open_stats_dialog(parent: QWidget, title: str, cards: list[tuple[str, str, str]], table_rows: list[list[Any]], plot_widget: QWidget | None = None, headers: list[str] | None = None, export_rows: list[dict[str, Any]] | None = None) -> None:
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.resize(860, 560)
    dlg.setMinimumSize(760, 460)
    dlg.setStyleSheet(DIALOG_STYLE)
    root = QVBoxLayout(dlg)
    root.setContentsMargins(10, 10, 10, 10)
    grid = QGridLayout()
    for idx, (name, value, accent) in enumerate(cards):
        grid.addWidget(_metric_card(name, value, accent), idx // 3, idx % 3)
    root.addLayout(grid)
    if plot_widget is not None:
        root.addWidget(plot_widget, 1)
    table = _build_table(headers or ["Metric", "Value"], table_rows, max_height=190)
    root.addWidget(table)
    buttons = QHBoxLayout()
    buttons.addStretch(1)
    if export_rows:
        export_btn = QPushButton("Export CSV")
        export_btn.setObjectName("exportButton")

        def _export() -> None:
            safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", title.strip().lower()).strip("_") or "segd_export"
            path, _ = QFileDialog.getSaveFileName(parent, f"Export {title}", f"{safe_name}.csv", "CSV (*.csv)")
            if not path:
                return
            with open(path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(export_rows[0].keys()))
                writer.writeheader()
                writer.writerows(export_rows)
            QMessageBox.information(parent, title, f"Exported CSV:\n{path}")

        export_btn.clicked.connect(_export)
        buttons.addWidget(export_btn)
    close = QPushButton("Close")
    close.setObjectName("dangerButton")
    close.clicked.connect(dlg.accept)
    buttons.addWidget(close)
    root.addLayout(buttons)
    dlg.exec()


def record_sum_diff(viewer: Any) -> None:
    if viewer.reader is None:
        return
    data = viewer._raw_data
    if data.size == 0:
        QMessageBox.information(viewer, "Record Sum/Diff", "Render a trace window first.")
        return
    even = data[0::2].astype(float)
    odd = data[1::2].astype(float)
    n = min(len(even), len(odd))
    if n == 0:
        return
    sums = even[:n] + odd[:n]
    diffs = even[:n] - odd[:n]
    sum_rms = np.sqrt(np.mean(sums * sums, axis=1))
    diff_rms = np.sqrt(np.mean(diffs * diffs, axis=1))
    ratio = float(np.sqrt(np.mean(diffs * diffs)) / max(np.sqrt(np.mean(sums * sums)), 1e-12))
    plot = pg.PlotWidget()
    plot.setBackground("#FFFFFF")
    plot.setLabel("bottom", "Pair Number")
    plot.setLabel("left", "RMS")
    plot.showGrid(x=True, y=True, alpha=0.22)
    x = np.arange(1, n + 1)
    plot.plot(x, sum_rms, pen=pg.mkPen("#0B6FA4", width=2), name="Sum RMS")
    plot.plot(x, diff_rms, pen=pg.mkPen("#D96C2C", width=2), name="Diff RMS")
    plot.addLegend()
    cards = [
        ("Pairs", f"{n:,}", "#0A86C7"),
        ("Mean Sum RMS", _format_number(np.mean(sum_rms), 5), "#14A3A8"),
        ("Diff/Sum Ratio", f"{ratio:.4f}", "#D58B00"),
    ]
    rows = [
        ["SUM RMS mean", _format_number(np.mean(sum_rms), 6)],
        ["SUM RMS peak", _format_number(np.max(sum_rms), 6)],
        ["DIFF RMS mean", _format_number(np.mean(diff_rms), 6)],
        ["DIFF RMS peak", _format_number(np.max(diff_rms), 6)],
        ["Difference/Sum RMS ratio", f"{ratio:.4f}"],
    ]
    export_rows = [{"pair": int(i), "sum_rms": float(s), "diff_rms": float(d)} for i, s, d in zip(x, sum_rms, diff_rms)]
    _open_stats_dialog(viewer, "Record Sum / Difference", cards, rows, plot, export_rows=export_rows)


def multi_vib_sim(viewer: Any) -> None:
    data = viewer._raw_data
    if data.size == 0:
        QMessageBox.information(viewer, "Multi Vib Sim", "Render traces first.")
        return
    n = min(48, data.shape[0])
    x = data[:n].astype(float)
    x -= x.mean(axis=1, keepdims=True)
    norm = np.linalg.norm(x, axis=1)
    norm[norm < 1e-12] = 1.0
    corr = (x @ x.T) / (norm[:, None] * norm[None, :])
    tri = np.abs(corr[np.triu_indices(n, 1)]) if n > 1 else np.array([0.0])
    plot = pg.PlotWidget()
    plot.setBackground("#FFFFFF")
    plot.setLabel("bottom", "Trace Index")
    plot.setLabel("left", "Trace Index")
    image = pg.ImageItem(corr)
    image.setLookupTable(_spectral_lut())
    image.setLevels([-1.0, 1.0])
    image.setRect(QRectF(1, 1, n, n))
    plot.addItem(image)
    cards = [
        ("Traces Analysed", f"{n:,}", "#0A86C7"),
        ("Mean |Corr|", f"{np.mean(tri):.3f}", "#14A3A8"),
        ("Pairs > 0.90", f"{np.count_nonzero(tri > 0.90):,}", "#D58B00"),
    ]
    rows = [
        ["Maximum |correlation|", f"{np.max(tri):.3f}"],
        ["Median |correlation|", f"{np.median(tri):.3f}"],
        ["Pairs > 0.70", f"{np.count_nonzero(tri > 0.70):,}"],
        ["Pairs > 0.90", f"{np.count_nonzero(tri > 0.90):,}"],
        ["Interpretation", "High values may indicate repeatable signatures or duplicated/strongly similar channels."],
    ]
    _open_stats_dialog(viewer, "Multi Vib Similarity", cards, rows, plot)


def radio_sims(viewer: Any) -> None:
    if viewer.reader is None:
        return
    categories = ["Normal", "Auxiliary", "Resistance", "Capacitance", "Leakage", "Tilt", "Multiple", "Dead", "Edited"]
    counts = {k: 0 for k in categories}
    rows: list[dict[str, Any]] = []
    n = viewer.reader.get_trace_count()
    for i in range(n):
        ti = viewer.reader.get_trace_info(i)
        flags = list(getattr(ti, "qc_flags", ()) or ())
        if len(flags) > 1:
            status = "Multiple"
        elif flags and flags[0] in counts:
            status = flags[0]
        elif getattr(ti, "channel_type", 1) != 1:
            status = "Auxiliary"
        elif getattr(ti, "trace_edit", 0) != 0:
            status = "Edited"
        else:
            status = "Normal"
        counts[status] = counts.get(status, 0) + 1
        rows.append(
            {
                "trace": i + 1,
                "line": getattr(ti, "receiver_line", ""),
                "point": getattr(ti, "receiver_point", ""),
                "channel_set": getattr(ti, "channel_set", ""),
                "status": status,
                "flags": ";".join(map(str, flags)),
            }
        )
    plot = pg.PlotWidget()
    plot.setBackground("#FFFFFF")
    plot.setLabel("bottom", "Radio / QC Category")
    plot.setLabel("left", "Trace Count")
    plot.showGrid(x=False, y=True, alpha=0.22)
    heights = [counts[k] for k in categories]
    x = np.arange(len(categories))
    bar = pg.BarGraphItem(x=x, height=heights, width=0.68, brush="#0A86C7")
    plot.addItem(bar)
    plot.getAxis("bottom").setTicks([[(i, name) for i, name in enumerate(categories)]])
    fail_count = sum(v for k, v in counts.items() if k != "Normal")
    cards = [
        ("Total Traces", f"{n:,}", "#0A86C7"),
        ("Normal", f"{counts.get('Normal', 0):,}", "#00B050"),
        ("Flagged / Auxiliary", f"{fail_count:,}", "#D58B00"),
    ]
    table_rows = [[name, f"{counts[name]:,}", f"{(counts[name] / max(n, 1) * 100):.2f}%"] for name in categories]
    _open_stats_dialog(
        viewer,
        "Radio Sims / QC Flags",
        cards,
        table_rows,
        plot,
        headers=["Category", "Trace Count", "Percent"],
        export_rows=rows,
    )


def filters(viewer: Any) -> None:
    dlg = QDialog(viewer)
    dlg.setWindowTitle("SEG-D Display Filters")
    dlg.resize(420, 230)
    dlg.setStyleSheet(DIALOG_STYLE)
    lay = QVBoxLayout(dlg)
    form = QFormLayout()
    enabled = QCheckBox("Enable display filter")
    enabled.setChecked(bool(viewer._filter_enabled))
    low = QDoubleSpinBox()
    high = QDoubleSpinBox()
    low.setRange(0, 10000)
    high.setRange(0, 10000)
    low.setSuffix(" Hz")
    high.setSuffix(" Hz")
    low.setValue(viewer._filter_low_hz)
    high.setValue(viewer._filter_high_hz)
    form.addRow(enabled)
    form.addRow("Low cut / high-pass", low)
    form.addRow("High cut / low-pass", high)
    lay.addLayout(form)
    note = QLabel("Zero means disabled. When both values are set, a 4th-order zero-phase Butterworth band-pass is applied to display only. Raw SEG-D data are never overwritten.")
    note.setObjectName("subtleLabel")
    note.setWordWrap(True)
    lay.addWidget(note)
    row = QHBoxLayout()
    ok = QPushButton("Apply")
    ok.setObjectName("primaryButton")
    cancel = QPushButton("Cancel")
    cancel.setObjectName("dangerButton")
    ok.clicked.connect(dlg.accept)
    cancel.clicked.connect(dlg.reject)
    row.addStretch(1)
    row.addWidget(ok)
    row.addWidget(cancel)
    lay.addLayout(row)
    if dlg.exec():
        viewer._filter_enabled = enabled.isChecked()
        viewer._filter_low_hz = low.value()
        viewer._filter_high_hz = high.value()
        viewer.render_current_view()


def panels(viewer: Any) -> None:
    """Receiver/channel-set panel summary. Does not require a viewer.tab_widget attribute."""
    if viewer.reader is None:
        QMessageBox.information(viewer, "Panels", "Open a SEG-D file first.")
        return
    groups: dict[tuple[float, int], dict[str, Any]] = {}
    for i in range(viewer.reader.get_trace_count()):
        ti = viewer.reader.get_trace_info(i)
        key = (float(getattr(ti, "receiver_line", 0.0) or 0.0), int(getattr(ti, "channel_set", 0) or 0))
        g = groups.setdefault(
            key,
            {
                "line": key[0],
                "channel_set": key[1],
                "traces": 0,
                "first_trace": i + 1,
                "last_trace": i + 1,
                "point_min": float(getattr(ti, "receiver_point", i + 1) or (i + 1)),
                "point_max": float(getattr(ti, "receiver_point", i + 1) or (i + 1)),
                "auxiliary": 0,
                "edited": 0,
                "flagged": 0,
            },
        )
        point = float(getattr(ti, "receiver_point", i + 1) or (i + 1))
        g["traces"] += 1
        g["last_trace"] = i + 1
        g["point_min"] = min(g["point_min"], point)
        g["point_max"] = max(g["point_max"], point)
        if getattr(ti, "channel_type", 1) != 1:
            g["auxiliary"] += 1
        if getattr(ti, "trace_edit", 0) != 0:
            g["edited"] += 1
        if getattr(ti, "qc_flags", ()):
            g["flagged"] += 1
    ordered = sorted(groups.values(), key=lambda row: (row["line"], row["channel_set"]))
    plot = pg.PlotWidget()
    plot.setBackground("#FFFFFF")
    plot.setLabel("bottom", "Panel")
    plot.setLabel("left", "Trace Count")
    plot.showGrid(x=False, y=True, alpha=0.22)
    top = ordered[:30]
    x = np.arange(len(top))
    y = [row["traces"] for row in top]
    plot.addItem(pg.BarGraphItem(x=x, height=y, width=0.68, brush="#0A86C7"))
    plot.getAxis("bottom").setTicks([[(i, f"L{row['line']:g}/S{row['channel_set']}") for i, row in enumerate(top)]])
    table_rows = [
        [
            f"{row['line']:g}",
            row["channel_set"],
            f"{row['point_min']:g}–{row['point_max']:g}",
            row["first_trace"],
            row["last_trace"],
            row["traces"],
            row["flagged"],
            row["auxiliary"],
            row["edited"],
        ]
        for row in ordered
    ]
    cards = [
        ("Panels", f"{len(ordered):,}", "#0A86C7"),
        ("Receiver Lines", f"{len({row['line'] for row in ordered}):,}", "#14A3A8"),
        ("Total Traces", f"{viewer.reader.get_trace_count():,}", "#D58B00"),
    ]
    export_rows = [
        {
            "line": row["line"],
            "channel_set": row["channel_set"],
            "point_min": row["point_min"],
            "point_max": row["point_max"],
            "first_trace": row["first_trace"],
            "last_trace": row["last_trace"],
            "traces": row["traces"],
            "flagged": row["flagged"],
            "auxiliary": row["auxiliary"],
            "edited": row["edited"],
        }
        for row in ordered
    ]
    _open_stats_dialog(
        viewer,
        "Receiver / Channel Panels",
        cards,
        table_rows,
        plot,
        headers=["Line", "Set", "Point Range", "First", "Last", "Traces", "Flagged", "Aux", "Edited"],
        export_rows=export_rows,
    )


def trace_analysis(viewer: Any) -> None:
    data = viewer._raw_data
    if data.size == 0:
        QMessageBox.information(viewer, "Trace Analysis", "Render traces first.")
        return
    data64 = data.astype(float)
    rms = np.sqrt(np.mean(data64 ** 2, axis=1))
    peak = np.max(np.abs(data64), axis=1)
    zero = np.mean(np.abs(data64) <= 1e-20, axis=1) * 100.0
    idx = int(np.argmax(rms))
    trace = data64[idx]
    dt = max(float(viewer.reader.get_sample_interval()), 1e-9) / 1000.0
    spec = np.abs(np.fft.rfft(trace - trace.mean()))
    freq = np.fft.rfftfreq(trace.size, d=dt)
    dom = float(freq[np.argmax(spec[1:]) + 1]) if len(spec) > 1 else 0.0
    plot = pg.PlotWidget()
    plot.setBackground("#FFFFFF")
    plot.setLabel("bottom", "Rendered Trace Number")
    plot.setLabel("left", "Amplitude Statistic")
    plot.showGrid(x=True, y=True, alpha=0.22)
    x = np.arange(viewer._trace_start + 1, viewer._trace_start + len(rms) + 1)
    plot.plot(x, rms, pen=pg.mkPen("#0B6FA4", width=2), name="RMS")
    plot.plot(x, peak, pen=pg.mkPen("#D96C2C", width=2), name="Peak")
    plot.addLegend()
    cards = [
        ("Rendered Window", f"{data.shape[0]:,} × {data.shape[1]:,}", "#0A86C7"),
        ("Mean RMS", _format_number(np.mean(rms), 5), "#14A3A8"),
        ("Dominant Frequency", f"{dom:.2f} Hz", "#D58B00"),
    ]
    table_rows = [
        ["Median RMS", _format_number(np.median(rms), 6)],
        ["Max RMS trace", f"{viewer._trace_start + idx + 1:,}"],
        ["Global peak", _format_number(np.max(peak), 6)],
        ["Mean zero/dead sample fraction", f"{np.mean(zero):.3f}%"],
        ["Dominant frequency of max-RMS trace", f"{dom:.2f} Hz"],
    ]
    export_rows = [
        {"trace": int(t), "rms": float(r), "peak": float(p), "zero_dead_percent": float(z)}
        for t, r, p, z in zip(x, rms, peak, zero)
    ]
    _open_stats_dialog(viewer, "Trace Analysis", cards, table_rows, plot, export_rows=export_rows)


def dsd_bin_files(viewer: Any) -> None:
    path, _ = QFileDialog.getOpenFileName(
        viewer,
        "Open DSD / Binary File",
        str(viewer.file_path.parent),
        "Binary files (*.bin *.dsd *.dat);;All files (*.*)",
    )
    if not path:
        return
    raw = Path(path).read_bytes()
    head = raw[:512]
    hex_lines = []
    for off in range(0, len(head), 16):
        chunk = head[off:off + 16]
        hx = " ".join(f"{b:02X}" for b in chunk)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        hex_lines.append(f"{off:08X}  {hx:<47}  {asc}")
    _show_text(viewer, "DSD Bin Files", f"File: {path}\nSize: {len(raw):,} bytes\n\nFirst 512 bytes:\n" + "\n".join(hex_lines))
