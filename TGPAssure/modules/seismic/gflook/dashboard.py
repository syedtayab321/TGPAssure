from __future__ import annotations

import csv
import math
import os
import re
import struct
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
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


GF_EXTENSIONS = {".gf", ".gfc", ".txt", ".csv", ".dat", ".log"}
SIGNAL_NAMES = ("Ref", "Mass", "BP", "GF")


@dataclass
class GFRecord:
    path: Path
    record_number: str = ""
    record_date: str = ""
    record_time: str = ""
    vib_number: str = ""
    source_line: str = ""
    source_point: str = ""
    sample_rate_hz: float = 250.0
    dt: float = 0.004
    signals: dict[str, np.ndarray] = field(default_factory=dict)
    latitude: float | None = None
    longitude: float | None = None
    status: str = "Unchecked"
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)

    @property
    def sample_count(self) -> int:
        if not self.signals:
            return 0
        return max((len(v) for v in self.signals.values()), default=0)

    def signal(self, name: str) -> np.ndarray:
        arr = self.signals.get(name)
        if arr is None:
            return np.empty(0, dtype=float)
        return np.asarray(arr, dtype=float)


class GFFileReader:
    """Safe Sercel-VE464 GF style reader.

    Sercel GF binary layouts vary between recorder/export versions.  This reader
    therefore uses a two-stage approach: it first honours CSV/text exports with
    named Ref/Mass/BP/GF columns, then falls back to robust numeric extraction
    from mixed/binary files so the QC workspace never freezes on unknown files.
    """

    HEADER_KEYS = {
        "vib": "vib_number", "vibno": "vib_number", "vibnumber": "vib_number", "vib_number": "vib_number",
        "source_line": "source_line", "sourceline": "source_line", "line": "source_line", "sl": "source_line",
        "source_point": "source_point", "sourcepoint": "source_point", "sp": "source_point", "station": "source_point",
        "record": "record_number", "recordnumber": "record_number", "record_number": "record_number",
        "date": "record_date", "recorddate": "record_date", "time": "record_time", "recordtime": "record_time",
    }

    @staticmethod
    def read(path: str | Path) -> GFRecord:
        p = Path(path)
        raw = p.read_bytes()
        text = raw[:2_000_000].decode("utf-8", errors="ignore")
        record = GFRecord(path=p)
        GFFileReader._parse_text_metadata(record, text)
        if p.suffix.lower() in {".csv", ".txt", ".dat", ".log"}:
            try:
                GFFileReader._read_text_table(record, text)
            except Exception:
                pass
        if not record.signals:
            GFFileReader._read_numeric_fallback(record, raw, text)
        GFFileReader._normalise_record(record)
        return record

    @staticmethod
    def _key(text: str) -> str:
        return re.sub(r"[^a-z0-9]", "", text.strip().lower())

    @staticmethod
    def _parse_text_metadata(record: GFRecord, text: str) -> None:
        patterns = {
            "record_number": r"(?:record\s*(?:number|no\.?|#)?)[\s:=,]+([\w.-]+)",
            "vib_number": r"(?:vib\s*(?:number|no\.?|#)?)[\s:=,]+([\w.-]+)",
            "source_line": r"(?:source\s*line|line\s*no|line)[\s:=,]+([\w.-]+)",
            "source_point": r"(?:source\s*point|point|station|sp)[\s:=,]+([\w.-]+)",
            "record_date": r"(?:record\s*date|date)[\s:=,]+([0-9./-]+)",
            "record_time": r"(?:record\s*time|time)[\s:=,]+([0-9:.-]+)",
        }
        lowerish = text[:20000]
        for attr, pattern in patterns.items():
            m = re.search(pattern, lowerish, flags=re.I)
            if m:
                setattr(record, attr, m.group(1))
        for lat_key, attr in ((r"lat(?:itude)?", "latitude"), (r"lon(?:gitude)?", "longitude")):
            m = re.search(lat_key + r"[\s:=,]+(-?\d+(?:\.\d+)?)", lowerish, flags=re.I)
            if m:
                try:
                    setattr(record, attr, float(m.group(1)))
                except ValueError:
                    pass
        m = re.search(r"(?:sample\s*rate|samplerate|sr)[\s:=,]+(\d+(?:\.\d+)?)", lowerish, flags=re.I)
        if m:
            record.sample_rate_hz = max(float(m.group(1)), 1.0)
            record.dt = 1.0 / record.sample_rate_hz

    @staticmethod
    def _read_text_table(record: GFRecord, text: str) -> None:
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if not lines:
            return
        # Locate first line that looks like a table header or numeric table.
        header_index = 0
        delimiter = None
        for i, line in enumerate(lines[:300]):
            if "," in line:
                delimiter = ","
            elif "\t" in line:
                delimiter = "\t"
            else:
                delimiter = None
            parts = [p.strip() for p in (line.split(delimiter) if delimiter else re.split(r"\s+", line.strip()))]
            keys = [GFFileReader._key(p) for p in parts]
            if any(k in {"ref", "reference", "gf", "groundforce", "mass", "bp", "baseplate"} for k in keys):
                header_index = i
                break
            if sum(GFFileReader._is_float(p) for p in parts) >= 4:
                header_index = i
                break
        line = lines[header_index]
        delimiter = "," if "," in line else "\t" if "\t" in line else None
        first_parts = [p.strip() for p in (line.split(delimiter) if delimiter else re.split(r"\s+", line.strip()))]
        has_header = any(not GFFileReader._is_float(p) for p in first_parts)
        if has_header:
            headers = first_parts
            data_lines = lines[header_index + 1:]
        else:
            headers = []
            data_lines = lines[header_index:]
        columns: list[list[float]] = []
        for ln in data_lines:
            parts = [p.strip() for p in (ln.split(delimiter) if delimiter else re.split(r"\s+", ln.strip()))]
            nums = []
            for part in parts:
                try:
                    nums.append(float(part))
                except ValueError:
                    nums.append(math.nan)
            if len(nums) < 2:
                continue
            while len(columns) < len(nums):
                columns.append([])
            for i, value in enumerate(nums):
                columns[i].append(value)
        if not columns:
            return
        arrays = [np.asarray(col, dtype=float) for col in columns]
        arrays = [arr[np.isfinite(arr)] if np.isfinite(arr).sum() > max(8, len(arr) * 0.25) else arr for arr in arrays]
        key_to_idx = {GFFileReader._key(h): i for i, h in enumerate(headers)}
        def find(*names: str) -> int | None:
            for name in names:
                key = GFFileReader._key(name)
                for k, idx in key_to_idx.items():
                    if key == k or key in k or k in key:
                        return idx
            return None
        mapping = {
            "Ref": find("ref", "reference", "pilot"),
            "Mass": find("mass"),
            "BP": find("bp", "baseplate", "base plate"),
            "GF": find("gf", "groundforce", "ground force"),
        }
        used = set()
        for name, idx in mapping.items():
            if idx is not None and idx < len(arrays):
                record.signals[name] = arrays[idx]
                used.add(idx)
        if not record.signals:
            # Numeric export with no signal names.  Treat first four non-time columns as Ref/Mass/BP/GF.
            candidates = list(range(len(arrays)))
            if len(candidates) > 1 and GFFileReader._looks_like_time(arrays[0]):
                dt = float(np.nanmedian(np.diff(arrays[0]))) if len(arrays[0]) > 2 else 0.004
                if dt > 0:
                    record.dt = dt
                    record.sample_rate_hz = 1.0 / dt
                candidates = candidates[1:]
            for name, idx in zip(SIGNAL_NAMES, candidates[:4]):
                record.signals[name] = arrays[idx]

    @staticmethod
    def _read_numeric_fallback(record: GFRecord, raw: bytes, text: str) -> None:
        nums = [float(x) for x in re.findall(r"[-+]?\d*\.\d+(?:[eE][-+]?\d+)?|[-+]?\d+(?:[eE][-+]?\d+)?", text)]
        arr = np.asarray(nums, dtype=float)
        if arr.size < 64:
            # Binary fallback: interpret as little-endian int16 and float32, pick the cleaner sequence.
            int_count = len(raw) // 2
            f_count = len(raw) // 4
            candidates = []
            if int_count >= 64:
                candidates.append(np.frombuffer(raw[:int_count * 2], dtype="<i2").astype(float))
            if f_count >= 64:
                floats = np.frombuffer(raw[:f_count * 4], dtype="<f4").astype(float)
                floats = floats[np.isfinite(floats)]
                if floats.size >= 64:
                    candidates.append(floats)
            if candidates:
                arr = max(candidates, key=lambda a: min(a.size, np.isfinite(a).sum()))
        if arr.size < 64:
            record.warnings.append("No readable signal samples found.")
            return
        arr = arr[np.isfinite(arr)]
        # Split a single extracted vector into four equal traces. If too small, synthesize related traces.
        if arr.size >= 256:
            n = arr.size // 4
            for name, seg in zip(SIGNAL_NAMES, [arr[:n], arr[n:2*n], arr[2*n:3*n], arr[3*n:4*n]]):
                record.signals[name] = seg.copy()
        else:
            record.signals["Ref"] = arr.copy()
            record.signals["GF"] = arr.copy()

    @staticmethod
    def _normalise_record(record: GFRecord) -> None:
        n = record.sample_count
        if n <= 0:
            return
        for name in SIGNAL_NAMES:
            if name not in record.signals:
                if name == "GF" and "Ref" in record.signals:
                    record.signals[name] = record.signals["Ref"].copy()
                else:
                    record.signals[name] = np.zeros(n, dtype=float)
            record.signals[name] = GFFileReader._clean_signal(record.signals[name], n)
        if not record.record_number:
            digits = re.findall(r"\d+", record.path.stem)
            record.record_number = digits[-1] if digits else record.path.stem
        if not record.vib_number:
            m = re.search(r"vib[_ -]?(\d+)", record.path.stem, flags=re.I)
            record.vib_number = m.group(1) if m else ""

    @staticmethod
    def _clean_signal(signal: Sequence[float], n: int) -> np.ndarray:
        arr = np.asarray(signal, dtype=float)
        arr = arr[np.isfinite(arr)] if np.isfinite(arr).sum() >= max(8, arr.size // 4) else np.nan_to_num(arr)
        if arr.size == 0:
            arr = np.zeros(n, dtype=float)
        if arr.size < n:
            arr = np.pad(arr, (0, n - arr.size), mode="edge")
        elif arr.size > n:
            arr = arr[:n]
        return np.nan_to_num(arr.astype(float), nan=0.0, posinf=0.0, neginf=0.0)

    @staticmethod
    def _is_float(value: str) -> bool:
        try:
            float(value)
            return True
        except Exception:
            return False

    @staticmethod
    def _looks_like_time(arr: np.ndarray) -> bool:
        if arr.size < 8:
            return False
        d = np.diff(arr[:min(arr.size, 200)])
        return bool(np.nanmedian(d) > 0 and np.nanstd(d) < max(1e-9, abs(np.nanmedian(d)) * 0.2))


class GFAnalyzer:
    @staticmethod
    def analyse(record: GFRecord) -> GFRecord:
        ref = record.signal("Ref")
        gf = record.signal("GF")
        if ref.size < 8 or gf.size < 8:
            record.status = "Bad"
            record.warnings.append("Insufficient samples for GF analysis.")
            return record
        n = min(ref.size, gf.size)
        ref = GFAnalyzer._norm(ref[:n])
        gf = GFAnalyzer._norm(gf[:n])
        err = gf - ref
        corr = GFAnalyzer._safe_corr(ref, gf)
        rms_ref = float(np.sqrt(np.mean(ref ** 2)))
        rms_gf = float(np.sqrt(np.mean(gf ** 2)))
        rms_err = float(np.sqrt(np.mean(err ** 2)))
        distortion = float(100.0 * rms_err / max(rms_ref, 1e-9))
        phase_samples = GFAnalyzer._estimate_lag(ref, gf)
        phase_ms = float(phase_samples * record.dt * 1000.0)
        peak_gf = float(np.nanmax(np.abs(gf))) if gf.size else 0.0
        clip_ratio = float(np.mean(np.abs(gf) >= 0.995) * 100.0)
        dominant_hz = GFAnalyzer._dominant_frequency(gf, record.sample_rate_hz)
        record.metrics.update({
            "correlation": corr,
            "rms_ref": rms_ref,
            "rms_gf": rms_gf,
            "rms_error": rms_err,
            "distortion_pct": distortion,
            "phase_error_ms": phase_ms,
            "peak_gf": peak_gf,
            "clip_ratio_pct": clip_ratio,
            "dominant_hz": dominant_hz,
        })
        warnings = []
        if corr < 0.75:
            warnings.append("Low Ref/GF correlation")
        if abs(phase_ms) > 12.0:
            warnings.append("High phase error")
        if distortion > 35.0:
            warnings.append("High GF distortion")
        if clip_ratio > 2.0:
            warnings.append("Possible clipped GF signal")
        if peak_gf < 0.05:
            warnings.append("Low GF energy")
        record.warnings = list(dict.fromkeys(record.warnings + warnings))
        if not warnings:
            record.status = "Good"
        elif len(warnings) <= 2:
            record.status = "Warning"
        else:
            record.status = "Bad"
        return record

    @staticmethod
    def _norm(arr: np.ndarray) -> np.ndarray:
        arr = np.asarray(arr, dtype=float) - float(np.nanmean(arr))
        scale = float(np.nanpercentile(np.abs(arr), 99)) if arr.size else 1.0
        if not np.isfinite(scale) or scale <= 0:
            scale = float(np.nanmax(np.abs(arr)) or 1.0)
        return np.clip(arr / scale, -1.0, 1.0)

    @staticmethod
    def _safe_corr(a: np.ndarray, b: np.ndarray) -> float:
        if a.size < 2 or b.size < 2:
            return 0.0
        aa = a - np.mean(a); bb = b - np.mean(b)
        denom = float(np.sqrt(np.sum(aa ** 2) * np.sum(bb ** 2)))
        return float(np.sum(aa * bb) / denom) if denom > 0 else 0.0

    @staticmethod
    def _estimate_lag(a: np.ndarray, b: np.ndarray) -> int:
        n = min(a.size, b.size, 5000)
        aa = a[:n] - np.mean(a[:n]); bb = b[:n] - np.mean(b[:n])
        corr = np.correlate(bb, aa, mode="full")
        lag = int(np.argmax(corr) - (n - 1))
        return lag

    @staticmethod
    def _dominant_frequency(signal: np.ndarray, sample_rate: float) -> float:
        if signal.size < 16:
            return 0.0
        y = np.abs(np.fft.rfft(signal - np.mean(signal)))
        f = np.fft.rfftfreq(signal.size, d=1.0 / max(sample_rate, 1.0))
        if y.size <= 1:
            return 0.0
        idx = int(np.argmax(y[1:]) + 1)
        return float(f[idx])


class GFPlot(QWidget):
    PALETTES: dict[str, list[QColor]] = {
        "Mono / Classic": [QColor(14, 24, 39), QColor(14, 24, 39)],
        "Amplitude Blue-Gold": [QColor(30, 64, 175), QColor(14, 165, 233), QColor(34, 197, 94), QColor(250, 204, 21), QColor(220, 38, 38)],
        "Seismic Blue-White-Red": [QColor(30, 64, 175), QColor(147, 197, 253), QColor(255, 255, 255), QColor(252, 165, 165), QColor(185, 28, 28)],
        "Viridis Pro": [QColor(68, 1, 84), QColor(59, 82, 139), QColor(33, 145, 140), QColor(94, 201, 98), QColor(253, 231, 37)],
        "Thermal QC": [QColor(15, 23, 42), QColor(88, 28, 135), QColor(219, 39, 119), QColor(249, 115, 22), QColor(254, 240, 138)],
    }

    def __init__(self, title: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title = title
        self.x: np.ndarray | None = None
        self.y: np.ndarray | None = None
        self.y2: np.ndarray | None = None
        self.mode = "line"
        self.palette_name = "Amplitude Blue-Gold"
        self.colorize_by_value = True
        self.line_width = 0.9
        self._palette_rect = QRectF()
        self.setMinimumSize(170, 92)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setToolTip("Click Palette to change waveform colors")

    def set_series(self, y: Sequence[float] | np.ndarray, *, x: Sequence[float] | np.ndarray | None = None,
                   y2: Sequence[float] | np.ndarray | None = None, mode: str = "line") -> None:
        arr = np.asarray(y, dtype=float)
        self.y = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
        self.x = np.asarray(x, dtype=float) if x is not None else None
        self.y2 = np.asarray(y2, dtype=float) if y2 is not None else None
        self.mode = mode
        self.update()

    def clear(self) -> None:
        self.y = None; self.x = None; self.y2 = None; self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._palette_rect.contains(QPointF(event.position().x(), event.position().y())):
            self.open_palette_dialog()
            return
        super().mousePressEvent(event)

    def open_palette_dialog(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Waveform Color Palette - {self.title}")
        dlg.setMinimumWidth(340)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(8)
        title = QLabel("Color waveform by amplitude/value")
        title.setStyleSheet('font-family:"Segoe UI"; font-size:8pt; font-weight:700; color:#0F172A;')
        layout.addWidget(title)
        combo = QComboBox()
        combo.addItems(list(self.PALETTES.keys()))
        combo.setCurrentText(self.palette_name)
        combo.setStyleSheet('font-family:"Segoe UI"; font-size:8pt; min-height:24px;')
        layout.addWidget(combo)
        mode = QComboBox()
        mode.addItems(["Value-based color trace", "Single-color trace"])
        mode.setCurrentIndex(0 if self.colorize_by_value else 1)
        mode.setStyleSheet('font-family:"Segoe UI"; font-size:8pt; min-height:24px;')
        layout.addWidget(mode)
        preview = QLabel("Low amplitude/value  →  High amplitude/value")
        preview.setAlignment(Qt.AlignCenter)
        preview.setMinimumHeight(28)
        preview.setStyleSheet('font-family:"Segoe UI"; font-size:7.5pt; font-weight:600; color:#334155; border:1px solid #D6E1EA; border-radius:6px; background:#F8FAFC;')
        layout.addWidget(preview)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept); buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        if dlg.exec() == QDialog.Accepted:
            self.palette_name = combo.currentText()
            self.colorize_by_value = mode.currentIndex() == 0
            self.update()

    @classmethod
    def _interp_color(cls, stops: list[QColor], value: float) -> QColor:
        if not stops:
            return QColor(14, 24, 39)
        if len(stops) == 1:
            return QColor(stops[0])
        v = min(1.0, max(0.0, float(value)))
        pos = v * (len(stops) - 1)
        i = int(math.floor(pos))
        j = min(len(stops) - 1, i + 1)
        f = pos - i
        a, b = stops[i], stops[j]
        return QColor(
            int(a.red() + (b.red() - a.red()) * f),
            int(a.green() + (b.green() - a.green()) * f),
            int(a.blue() + (b.blue() - a.blue()) * f),
        )

    def _palette_color(self, norm_value: float) -> QColor:
        return self._interp_color(self.PALETTES.get(self.palette_name, self.PALETTES["Mono / Classic"]), norm_value)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(246, 249, 252))
        outer = QRectF(1, 1, max(20, self.width() - 2), max(20, self.height() - 2))
        painter.setPen(QPen(QColor(218, 226, 234), 1))
        painter.setBrush(QColor(255, 255, 255))
        painter.drawRoundedRect(outer, 7, 7)
        self._palette_rect = QRectF(self.width() - 58, 6, 50, 15)
        rect = QRectF(30, 22, max(20, self.width() - 42), max(20, self.height() - 36))
        painter.fillRect(rect, QColor(255, 255, 255))
        painter.setPen(QPen(QColor(203, 213, 225), 1))
        painter.drawRect(rect)
        painter.setFont(QFont("Segoe UI", 6, QFont.DemiBold))
        painter.setPen(QColor(15, 23, 42))
        painter.drawText(QRectF(8, 5, self.width() - 70, 15), Qt.AlignCenter, self.title)
        self._draw_palette_badge(painter)
        painter.setPen(QPen(QColor(226, 232, 240), 1, Qt.DotLine))
        for i in range(1, 5):
            x = rect.left() + rect.width() * i / 5
            y = rect.top() + rect.height() * i / 5
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        if self.y is None or self.y.size == 0:
            painter.setFont(QFont("Segoe UI", 7))
            painter.setPen(QColor(120, 130, 140))
            painter.drawText(rect, Qt.AlignCenter, "No data")
            return
        y = self.y.astype(float)
        if y.size > 2800:
            step = max(1, y.size // 2800)
            y = y[::step]
        x = np.linspace(0.0, 1.0, y.size) if self.x is None else np.asarray(self.x[:self.y.size], dtype=float)
        if x.size != self.y.size:
            x = np.linspace(0.0, 1.0, self.y.size)
        if x.size > y.size:
            x = x[::max(1, x.size // y.size)]
        if x.size != y.size:
            x = np.linspace(0.0, 1.0, y.size)
        ymin = float(np.nanpercentile(y, 1)); ymax = float(np.nanpercentile(y, 99))
        if self.y2 is not None and self.y2.size:
            yy = self.y2[::max(1, self.y2.size // max(1, y.size))]
            ymin = min(ymin, float(np.nanpercentile(yy, 1))); ymax = max(ymax, float(np.nanpercentile(yy, 99)))
        if not np.isfinite(ymin) or not np.isfinite(ymax) or abs(ymax - ymin) < 1e-12:
            ymin, ymax = -1.0, 1.0
        xmin, xmax = float(np.nanmin(x)), float(np.nanmax(x))
        if not np.isfinite(xmin) or not np.isfinite(xmax) or abs(xmax - xmin) < 1e-12:
            xmin, xmax = 0.0, 1.0
        def pt(i: int, yy: float) -> QPointF:
            px = rect.left() + (float(x[i]) - xmin) / (xmax - xmin) * rect.width()
            py = rect.bottom() - (float(yy) - ymin) / (ymax - ymin) * rect.height()
            return QPointF(px, py)
        def draw_line(vals: np.ndarray, color: QColor | None = None) -> None:
            vals = np.asarray(vals, dtype=float)
            if vals.size < 2:
                return
            if self.colorize_by_value and color is None:
                denom = ymax - ymin if abs(ymax - ymin) > 1e-12 else 1.0
                for i in range(1, vals.size):
                    nv = ((float(vals[i-1]) + float(vals[i])) * 0.5 - ymin) / denom
                    painter.setPen(QPen(self._palette_color(nv), self.line_width))
                    painter.drawLine(pt(i - 1, vals[i - 1]), pt(i, vals[i]))
            else:
                path = QPainterPath(); path.moveTo(pt(0, vals[0]))
                for i in range(1, vals.size):
                    path.lineTo(pt(i, vals[i]))
                painter.setPen(QPen(color or QColor(12, 24, 39), self.line_width))
                painter.drawPath(path)
        draw_line(y, None)
        if self.y2 is not None and self.y2.size:
            yy = np.asarray(self.y2, dtype=float)
            if yy.size > 2800:
                yy = yy[::max(1, yy.size // 2800)]
            if yy.size != y.size:
                idx = np.linspace(0, yy.size - 1, y.size).astype(int)
                yy = yy[idx]
            old = self.colorize_by_value
            self.colorize_by_value = False
            draw_line(yy, QColor(14, 165, 233))
            self.colorize_by_value = old
        self._draw_color_scale(painter, rect, ymin, ymax)
        painter.setFont(QFont("Segoe UI", 5))
        painter.setPen(QColor(100, 116, 139))
        painter.drawText(2, int(rect.center().y()), "Amp")
        painter.drawText(QRectF(rect.left(), rect.bottom() + 0, rect.width(), 10), Qt.AlignCenter, "Time / Frequency")

    def _draw_palette_badge(self, painter: QPainter) -> None:
        painter.save()
        painter.setPen(QPen(QColor(186, 200, 214), 1))
        painter.setBrush(QColor(241, 245, 249))
        painter.drawRoundedRect(self._palette_rect, 5, 5)
        painter.setFont(QFont("Segoe UI", 5, QFont.DemiBold))
        painter.setPen(QColor(51, 65, 85))
        painter.drawText(self._palette_rect, Qt.AlignCenter, "Palette")
        painter.restore()

    def _draw_color_scale(self, painter: QPainter, rect: QRectF, ymin: float, ymax: float) -> None:
        if not self.colorize_by_value:
            return
        bar = QRectF(rect.right() - 52, rect.top() + 5, 46, 5)
        stops = self.PALETTES.get(self.palette_name, self.PALETTES["Mono / Classic"])
        grad = QLinearGradient(bar.left(), bar.top(), bar.right(), bar.top())
        if len(stops) == 1:
            grad.setColorAt(0, stops[0]); grad.setColorAt(1, stops[0])
        else:
            for i, c in enumerate(stops):
                grad.setColorAt(i / (len(stops) - 1), c)
        painter.save()
        painter.setBrush(grad)
        painter.setPen(QPen(QColor(203, 213, 225), 0.6))
        painter.drawRoundedRect(bar, 2, 2)
        painter.setFont(QFont("Segoe UI", 4))
        painter.setPen(QColor(100, 116, 139))
        painter.drawText(QRectF(bar.left(), bar.bottom() + 1, bar.width(), 8), Qt.AlignCenter, "Value")
        painter.restore()


class GFMapCanvas(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.records: list[GFRecord] = []
        self.setMinimumSize(360, 280)

    def set_records(self, records: Sequence[GFRecord]) -> None:
        self.records = list(records)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        grad = QLinearGradient(0, 0, self.width(), self.height())
        grad.setColorAt(0, QColor(241, 245, 249)); grad.setColorAt(1, QColor(219, 234, 254))
        painter.fillRect(self.rect(), grad)
        painter.setPen(QPen(QColor(203, 213, 225), 1))
        for i in range(0, self.width(), 40):
            painter.drawLine(i, 0, i, self.height())
        for j in range(0, self.height(), 40):
            painter.drawLine(0, j, self.width(), j)
        coords = [(r.longitude, r.latitude, r) for r in self.records if r.longitude is not None and r.latitude is not None]
        if not coords:
            painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
            painter.setPen(QColor(70, 80, 85))
            painter.drawText(self.rect(), Qt.AlignCenter, "KMZ/Shapefile status map preview\nNo coordinates in selected GF files")
            return
        xs = [c[0] for c in coords]; ys = [c[1] for c in coords]
        xmin, xmax = min(xs), max(xs); ymin, ymax = min(ys), max(ys)
        if xmax == xmin: xmax += 1e-6
        if ymax == ymin: ymax += 1e-6
        for lon, lat, rec in coords:
            x = 18 + (lon - xmin) / (xmax - xmin) * (self.width() - 36)
            y = self.height() - 18 - (lat - ymin) / (ymax - ymin) * (self.height() - 36)
            color = {"Good": QColor(35, 142, 68), "Warning": QColor(220, 165, 0), "Bad": QColor(210, 55, 55)}.get(rec.status, QColor(90, 120, 180))
            painter.setBrush(color); painter.setPen(QPen(QColor(35, 35, 35), 1))
            painter.drawEllipse(QPointF(x, y), 5, 5)


class TGPGroundForceLookWidget(QWidget):
    """GFLook-style Sercel VE464 ground-force QC workspace for TGPAssure."""

    state_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.records: list[GFRecord] = []
        self.current_record: GFRecord | None = None
        self.folder: Path | None = None
        self._build_ui()
        self._apply_style()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(5, 5, 5, 4)
        root.setSpacing(4)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        left = QFrame()
        left.setObjectName("gfLeftPanel")
        left.setMinimumWidth(205)
        left.setMaximumWidth(285)
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(6, 6, 6, 6)
        left_l.setSpacing(5)

        row = QHBoxLayout()
        row.setSpacing(4)
        for text, slot in (("Folder", self.open_folder), ("File", self.open_file), ("Reload", self.reload_folder)):
            btn = QPushButton(text)
            btn.setObjectName("compactButton")
            btn.setFixedHeight(24)
            btn.clicked.connect(slot)
            row.addWidget(btn)
        left_l.addLayout(row)

        self.status_label = QLabel("Open a Sercel GF file or folder")
        self.status_label.setObjectName("gfStatus")
        self.status_label.setWordWrap(True)
        left_l.addWidget(self.status_label)

        self.file_list = QListWidget()
        self.file_list.setObjectName("gfFileList")
        self.file_list.currentRowChanged.connect(self._on_file_selected)
        left_l.addWidget(self.file_list, 1)

        self.summary_table = QTableWidget(0, 3)
        self.summary_table.setObjectName("gfSummary")
        self.summary_table.setHorizontalHeaderLabels(["Status", "Vib", "SP"])
        self.summary_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.summary_table.verticalHeader().setVisible(False)
        self.summary_table.setAlternatingRowColors(True)
        self.summary_table.setMaximumHeight(112)
        left_l.addWidget(self.summary_table)
        splitter.addWidget(left)

        right = QFrame()
        right.setObjectName("gfWorkArea")
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(0, 0, 0, 0)
        right_l.setSpacing(0)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._build_page1(), "Page 1")
        self.tabs.addTab(self._build_page2(), "Page 2")
        self.tabs.addTab(self._build_page3(), "Page 3")
        self.tabs.addTab(self._build_page4(), "GIS / QC")
        self.tabs.addTab(self._build_file_info(), "File Info")
        right_l.addWidget(self.tabs, 1)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([230, 1220])
        root.addWidget(splitter, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(4)
        for text, slot in (("Run QC", self.run_qc), ("QC Listing", self.export_qc_listing), ("KMZ", self.export_kmz), ("Shape File", self.export_shapefile), ("SEG-Y", self.convert_to_segy), ("Export Image", self.export_image)):
            b = QPushButton(text)
            b.setObjectName("footerButton")
            b.setFixedHeight(26)
            b.clicked.connect(slot)
            footer.addWidget(b)
        root.addLayout(footer)

    def _build_page1(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 4, 6, 6)
        layout.setSpacing(4)
        self.record_title = QLabel("")
        self.record_title.setObjectName("recordTitle")
        self.record_title.setFixedHeight(22)
        layout.addWidget(self.record_title)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        layout.addLayout(grid, 1)
        self.plots_p1 = {name: GFPlot(name) for name in ("Reference", "GF", "Mass", "BP")}
        for i, plot in enumerate(self.plots_p1.values()):
            grid.addWidget(plot, i // 2, i % 2)
        return page

    def _build_page2(self) -> QWidget:
        page = QWidget(); grid = QGridLayout(page); grid.setContentsMargins(6, 6, 6, 6); grid.setSpacing(4)
        self.plots_p2 = {
            "Ref Start": GFPlot("Ref Start"), "Ref End": GFPlot("Ref End"),
            "GF Start": GFPlot("GF Start"), "GF End": GFPlot("GF End"),
            "Ref + GF": GFPlot("Ref + GF Overlay"), "GF Error": GFPlot("GF Error"),
        }
        for i, plot in enumerate(self.plots_p2.values()):
            grid.addWidget(plot, i // 3, i % 3)
        return page

    def _build_page3(self) -> QWidget:
        page = QWidget(); grid = QGridLayout(page); grid.setContentsMargins(6, 6, 6, 6); grid.setSpacing(4)
        self.plots_p3 = {
            "Phase Error": GFPlot("Phase Error"), "FFT Ref": GFPlot("FFT Ref"),
            "FFT GF": GFPlot("FFT GF"), "GF Distortion": GFPlot("GF Distortion"),
            "Frequency vs Time": GFPlot("Frequency vs Time"), "Gather": GFPlot("Gather / Sweep Energy"),
        }
        for i, plot in enumerate(self.plots_p3.values()):
            grid.addWidget(plot, i // 3, i % 3)
        return page

    def _build_page4(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(6, 6, 6, 6); layout.setSpacing(5)
        self.map_canvas = GFMapCanvas(); layout.addWidget(self.map_canvas, 1)
        self.qc_text = QPlainTextEdit(); self.qc_text.setReadOnly(True); self.qc_text.setMaximumHeight(130); layout.addWidget(self.qc_text)
        return page

    def _build_file_info(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page)
        self.info_table = QTableWidget(0, 2); self.info_table.setHorizontalHeaderLabels(["Field", "Value"]); self.info_table.setAlternatingRowColors(True)
        self.info_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.info_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.info_table)
        return page

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            TGPGroundForceLookWidget, QWidget {
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 7pt;
                color: #0F172A;
                background: #EEF3F7;
            }
            QFrame#gfLeftPanel, QFrame#gfWorkArea {
                background: #FFFFFF;
                border: 1px solid #D7E1EA;
                border-radius: 7px;
            }
            QFrame#gfLeftPanel {
                background: #F8FBFD;
            }
            QLabel#gfStatus {
                background: #EAF5FF;
                color: #0F4C81;
                border: 1px solid #CFE7FA;
                border-radius: 7px;
                padding: 4px 6px;
                font-size: 7pt;
                font-weight: 600;
            }
            QLabel#recordTitle {
                background: #FFFFFF;
                border: 1px solid #DCE6EE;
                border-left: 4px solid #0EA5E9;
                border-radius: 6px;
                color: #0F172A;
                padding: 2px 7px;
                font-size: 7pt;
                font-weight: 700;
            }
            QTabWidget::pane {
                border: 0px;
                background: #FFFFFF;
                top: -1px;
            }
            QTabBar::tab {
                background: #E7EEF5;
                color: #334155;
                padding: 5px 10px;
                min-width: 68px;
                border: 1px solid #D6E1EA;
                border-bottom: 1px solid #CBD5E1;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-size: 7pt;
                font-weight: 700;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #0F6B7F;
                color: #FFFFFF;
                border-color: #0F6B7F;
            }
            QTabBar::tab:hover:!selected {
                background: #DDF3FA;
                color: #0F4C81;
            }
            QPushButton {
                background: #0F6B7F;
                color: white;
                border: 1px solid #0B5260;
                border-radius: 7px;
                padding: 4px 10px;
                font-size: 7pt;
                font-weight: 700;
            }
            QPushButton:hover { background: #128199; border-color: #0E7490; }
            QPushButton:pressed { background: #0B4B59; }
            QPushButton:disabled { background: #CBD5E1; color: #64748B; border-color: #CBD5E1; }
            QPushButton#compactButton {
                background: #0E7490;
                min-width: 52px;
            }
            QPushButton#footerButton {
                background: #0F172A;
                border-color: #1E293B;
                min-height: 22px;
                font-size: 7.3pt;
            }
            QPushButton#footerButton:hover { background: #1E3A5F; }
            QListWidget, QTableWidget, QPlainTextEdit {
                background: #FFFFFF;
                border: 1px solid #D7E1EA;
                border-radius: 7px;
                gridline-color: #E8EEF4;
                selection-background-color: #0EA5E9;
                selection-color: white;
                alternate-background-color: #F8FBFD;
                font-size: 7pt;
            }
            QListWidget::item {
                padding: 3px 5px;
                border-bottom: 1px solid #EEF2F6;
            }
            QListWidget::item:selected {
                background: #0EA5E9;
                color: white;
                border-radius: 4px;
            }
            QHeaderView::section {
                background: #E8EEF5;
                color: #243447;
                border: 0px;
                border-right: 1px solid #D7E1EA;
                border-bottom: 1px solid #D7E1EA;
                padding: 3px;
                font-size: 6.8pt;
                font-weight: 700;
            }
            QSplitter::handle { background: #DCE6EE; width: 4px; }
            QScrollBar:vertical, QScrollBar:horizontal { background: #EEF3F7; border: 0px; width: 9px; height: 9px; }
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal { background: #B7C5D3; border-radius: 4px; }
        """)

    def open_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Open Sercel VE464 GF Folder", str(self.folder or Path.home()))
        if folder:
            self.load_folder(folder)

    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open GF File", str(self.folder or Path.home()), "GF/Data Files (*.gf *.gfc *.csv *.txt *.dat *.log);;All Files (*.*)")
        if not path:
            return
        rec = GFAnalyzer.analyse(GFFileReader.read(path))
        self.records = [rec]
        self.folder = Path(path).parent
        self._populate_file_list()
        self.file_list.setCurrentRow(0)
        self.status_label.setText(f"Loaded {Path(path).name}")
        self.state_changed.emit()

    def load_folder(self, folder: str | Path) -> None:
        self.folder = Path(folder)
        files = [p for p in sorted(self.folder.iterdir()) if p.is_file() and (p.suffix.lower() in GF_EXTENSIONS or p.suffix == "")]
        records: list[GFRecord] = []
        errors: list[str] = []
        for path in files:
            try:
                records.append(GFAnalyzer.analyse(GFFileReader.read(path)))
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")
        self.records = records
        self._populate_file_list()
        if self.records:
            self.file_list.setCurrentRow(0)
        self.status_label.setText(f"{len(records)} GF files loaded" + (f" • {len(errors)} skipped" if errors else ""))
        if errors:
            self.qc_text.setPlainText("Skipped files:\n" + "\n".join(errors[:30]))
        self.state_changed.emit()

    def reload_folder(self) -> None:
        if self.folder:
            self.load_folder(self.folder)
        else:
            self.open_folder()

    def _populate_file_list(self) -> None:
        self.file_list.blockSignals(True); self.file_list.clear()
        for rec in self.records:
            item = QListWidgetItem(f"{rec.path.name}  |  Vib {rec.vib_number or '-'}  |  {rec.status}")
            item.setForeground({"Good": QColor(20, 120, 55), "Warning": QColor(185, 130, 0), "Bad": QColor(190, 45, 45)}.get(rec.status, QColor(60, 80, 110)))
            self.file_list.addItem(item)
        self.file_list.blockSignals(False)
        self._update_summary_table()

    def _update_summary_table(self) -> None:
        self.summary_table.setRowCount(len(self.records))
        for r, rec in enumerate(self.records):
            for c, val in enumerate((rec.status, rec.vib_number or "-", rec.source_point or "-")):
                item = QTableWidgetItem(str(val)); self.summary_table.setItem(r, c, item)

    def _on_file_selected(self, row: int) -> None:
        if row < 0 or row >= len(self.records):
            return
        self.current_record = self.records[row]
        self._display_record(self.current_record)

    def _display_record(self, rec: GFRecord) -> None:
        t = np.arange(rec.sample_count) * rec.dt
        self.record_title.setText(f"Record {rec.record_number or rec.path.stem}   •   Vib {rec.vib_number or '-'}   •   SL {rec.source_line or '-'}   •   SP {rec.source_point or '-'}   •   Samples {rec.sample_count}   •   Status {rec.status}")
        for label, sig_name in (("Reference", "Ref"), ("GF", "GF"), ("Mass", "Mass"), ("BP", "BP")):
            self.plots_p1[label].set_series(rec.signal(sig_name), x=t)
        n = rec.sample_count; k = max(16, min(n // 5, 800))
        self.plots_p2["Ref Start"].set_series(rec.signal("Ref")[:k])
        self.plots_p2["Ref End"].set_series(rec.signal("Ref")[-k:])
        self.plots_p2["GF Start"].set_series(rec.signal("GF")[:k])
        self.plots_p2["GF End"].set_series(rec.signal("GF")[-k:])
        self.plots_p2["Ref + GF"].set_series(rec.signal("Ref"), x=t, y2=rec.signal("GF"))
        self.plots_p2["GF Error"].set_series(GFAnalyzer._norm(rec.signal("GF")) - GFAnalyzer._norm(rec.signal("Ref")), x=t)
        ref = GFAnalyzer._norm(rec.signal("Ref")); gf = GFAnalyzer._norm(rec.signal("GF")); err = gf - ref
        phase = np.unwrap(np.angle(np.fft.ifft(np.fft.fft(gf[:min(gf.size, ref.size)]) * np.conj(np.fft.fft(ref[:min(gf.size, ref.size)]))))) if min(gf.size, ref.size) > 8 else np.zeros(8)
        self.plots_p3["Phase Error"].set_series(phase[:min(phase.size, 1200)])
        self.plots_p3["FFT Ref"].set_series(np.abs(np.fft.rfft(ref))[:1200])
        self.plots_p3["FFT GF"].set_series(np.abs(np.fft.rfft(gf))[:1200])
        window = max(16, min(256, err.size // 20 or 16)); dist = np.convolve(np.abs(err), np.ones(window)/window, mode="same") if err.size else err
        self.plots_p3["GF Distortion"].set_series(dist, x=t[:dist.size])
        freq = self._instantaneous_frequency(gf, rec.sample_rate_hz)
        self.plots_p3["Frequency vs Time"].set_series(freq)
        energy = np.convolve(gf ** 2, np.ones(window)/window, mode="same") if gf.size else gf
        self.plots_p3["Gather"].set_series(energy)
        self.map_canvas.set_records(self.records)
        self._update_file_info(rec)
        self._update_qc_text()

    @staticmethod
    def _instantaneous_frequency(y: np.ndarray, sr: float) -> np.ndarray:
        if y.size < 16:
            return np.zeros(0)
        # Zero-crossing based sweep-frequency trend; avoids scipy dependency.
        signs = np.signbit(y - np.mean(y)).astype(int)
        zc = np.flatnonzero(np.diff(signs))
        freq = np.zeros_like(y, dtype=float)
        if zc.size > 2:
            periods = np.diff(zc) / max(sr, 1.0) * 2.0
            vals = 1.0 / np.maximum(periods, 1e-6)
            centers = zc[1:]
            freq = np.interp(np.arange(y.size), centers, vals, left=vals[0], right=vals[-1])
        return freq

    def _update_file_info(self, rec: GFRecord) -> None:
        fields = [
            ("File", str(rec.path)), ("Record Number", rec.record_number), ("Record Date", rec.record_date),
            ("Record Time", rec.record_time), ("Vib Number", rec.vib_number), ("Source Line", rec.source_line),
            ("Source Point", rec.source_point), ("Total Samples", rec.sample_count), ("Sample Rate", f"{rec.sample_rate_hz:.3f} Hz"),
            ("Status", rec.status), ("Warnings", "; ".join(rec.warnings) or "None"),
        ] + [(k.replace("_", " ").title(), f"{v:.4g}") for k, v in sorted(rec.metrics.items())]
        self.info_table.setRowCount(len(fields))
        for r, (k, v) in enumerate(fields):
            self.info_table.setItem(r, 0, QTableWidgetItem(str(k)))
            self.info_table.setItem(r, 1, QTableWidgetItem(str(v)))

    def _update_qc_text(self) -> None:
        lines = ["TGPForceLook QC Listing", "=======================", ""]
        for rec in self.records:
            msg = "; ".join(rec.warnings) or "OK"
            lines.append(f"{rec.path.name:32s}  Vib={rec.vib_number or '-':>6s}  SL={rec.source_line or '-':>8s}  SP={rec.source_point or '-':>8s}  {rec.status:8s}  {msg}")
        self.qc_text.setPlainText("\n".join(lines))

    def run_qc(self) -> None:
        self.records = [GFAnalyzer.analyse(r) for r in self.records]
        self._populate_file_list()
        if self.current_record:
            self._display_record(self.current_record)
        self.state_changed.emit()
        QMessageBox.information(self, "TGPForceLook QC", f"QC completed for {len(self.records)} GF file(s).")

    def can_execute(self, action_id: str) -> bool:
        # Keep the ribbon fully usable. Commands that need loaded data show their
        # own clear message instead of staying greyed out, which also allows the
        # toolbar to remain consistent after loading files from inside the page.
        return True

    def handle_ribbon_action(self, action_id: str) -> None:
        actions = {
            "gflook_open_folder": self.open_folder, "gflook_open_file": self.open_file, "gflook_reload": self.reload_folder,
            "gflook_run_qc": self.run_qc, "gflook_page1": lambda: self.tabs.setCurrentIndex(0), "gflook_page2": lambda: self.tabs.setCurrentIndex(1),
            "gflook_page3": lambda: self.tabs.setCurrentIndex(2), "gflook_page4": lambda: self.tabs.setCurrentIndex(3),
            "gflook_file_info": lambda: self.tabs.setCurrentIndex(4), "gflook_export_kmz": self.export_kmz,
            "gflook_export_shp": self.export_shapefile, "gflook_convert_segy": self.convert_to_segy,
            "gflook_qc_listing": self.export_qc_listing, "gflook_export_image": self.export_image,
        }
        fn = actions.get(action_id)
        if callable(fn):
            fn()

    def export_qc_listing(self) -> None:
        if not self.records:
            QMessageBox.information(self, "QC Listing", "Load GF files first."); return
        path, _ = QFileDialog.getSaveFileName(self, "Export GF QC Listing", str((self.folder or Path.home()) / "gflook_qc_listing.csv"), "CSV (*.csv)")
        if not path: return
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["file", "record", "vib", "source_line", "source_point", "status", "warnings", "correlation", "phase_error_ms", "distortion_pct", "dominant_hz"])
            for r in self.records:
                w.writerow([r.path.name, r.record_number, r.vib_number, r.source_line, r.source_point, r.status, "; ".join(r.warnings), r.metrics.get("correlation", ""), r.metrics.get("phase_error_ms", ""), r.metrics.get("distortion_pct", ""), r.metrics.get("dominant_hz", "")])
        QMessageBox.information(self, "QC Listing", f"QC listing exported:\n{path}")

    def export_kmz(self) -> None:
        if not self.records:
            QMessageBox.information(self, "GIS Output", "Load GF files first."); return
        path, _ = QFileDialog.getSaveFileName(self, "Export GF Status KMZ", str((self.folder or Path.home()) / "gflook_status.kmz"), "KMZ (*.kmz)")
        if not path: return
        colors = {"Good": "ff238e44", "Warning": "ff00a5dc", "Bad": "ff3737d2", "Unchecked": "ff996633"}
        kml = ['<?xml version="1.0" encoding="UTF-8"?>','<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>TGPForceLook GF Status</name>']
        for status, color in colors.items():
            kml.append(f'<Style id="{status}"><IconStyle><color>{color}</color><scale>1.1</scale><Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon></IconStyle></Style>')
        for r in self.records:
            if r.longitude is None or r.latitude is None: continue
            desc = f"Vib: {r.vib_number}<br/>Source Line: {r.source_line}<br/>Source Point: {r.source_point}<br/>Warnings: {'; '.join(r.warnings) or 'None'}"
            kml.append(f'<Placemark><name>{r.path.name}</name><styleUrl>#{r.status}</styleUrl><description><![CDATA[{desc}]]></description><Point><coordinates>{r.longitude},{r.latitude},0</coordinates></Point></Placemark>')
        kml.append('</Document></kml>')
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("doc.kml", "\n".join(kml))
        QMessageBox.information(self, "GIS Output", f"KMZ exported:\n{path}")

    def export_shapefile(self) -> None:
        if not self.records:
            QMessageBox.information(self, "Shape File", "Load GF files first."); return
        base, _ = QFileDialog.getSaveFileName(self, "Export GF Status Shapefile", str((self.folder or Path.home()) / "gflook_status.shp"), "Shapefile (*.shp)")
        if not base: return
        try:
            import shapefile  # type: ignore
            w = shapefile.Writer(str(Path(base).with_suffix("")), shapeType=shapefile.POINT)
            w.field("FILE", "C", size=80); w.field("VIB", "C", size=20); w.field("SL", "C", size=20); w.field("SP", "C", size=20); w.field("STATUS", "C", size=12); w.field("WARN", "C", size=180)
            for r in self.records:
                if r.longitude is None or r.latitude is None: continue
                w.point(float(r.longitude), float(r.latitude)); w.record(r.path.name[:80], r.vib_number, r.source_line, r.source_point, r.status, ("; ".join(r.warnings))[:180])
            w.close()
            QMessageBox.information(self, "Shape File", f"Shapefile exported:\n{base}")
        except Exception as exc:
            QMessageBox.warning(self, "Shape File", f"Unable to export shapefile. Install pyshp if needed.\n\n{exc}")

    def convert_to_segy(self) -> None:
        rec = self.current_record or (self.records[0] if self.records else None)
        if rec is None:
            QMessageBox.information(self, "SEG-Y Output", "Load and select a GF file first."); return
        path, _ = QFileDialog.getSaveFileName(self, "Convert selected GF to SEG-Y", str((self.folder or Path.home()) / f"{rec.path.stem}_gf.segy"), "SEG-Y (*.sgy *.segy)")
        if not path: return
        self._write_simple_segy(Path(path), rec)
        QMessageBox.information(self, "SEG-Y Output", f"SEG-Y written:\n{path}")

    @staticmethod
    def _write_simple_segy(path: Path, rec: GFRecord) -> None:
        text = ("C 1 TGPForceLook SEG-Y export from Sercel VE464 GF file".ljust(80) * 40)[:3200].encode("ascii", errors="replace")
        ns = min(rec.sample_count, 32767); dt_us = int(round(rec.dt * 1_000_000))
        binhdr = bytearray(400); struct.pack_into(">hhh", binhdr, 16, dt_us, dt_us, ns); struct.pack_into(">h", binhdr, 24, 5)
        with path.open("wb") as fh:
            fh.write(text); fh.write(binhdr)
            for i, name in enumerate(SIGNAL_NAMES, start=1):
                data = rec.signal(name)[:ns].astype(">f4")
                th = bytearray(240); struct.pack_into(">i", th, 0, i); struct.pack_into(">i", th, 4, i); struct.pack_into(">h", th, 114, ns); struct.pack_into(">h", th, 116, dt_us)
                fh.write(th); fh.write(data.tobytes())

    def export_image(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Current GFLook Page Image", str((self.folder or Path.home()) / "gflook_page.png"), "PNG (*.png)")
        if not path: return
        pix = QPixmap(self.tabs.currentWidget().size())
        self.tabs.currentWidget().render(pix)
        pix.save(path, "PNG")
        QMessageBox.information(self, "Export Image", f"Image exported:\n{path}")
