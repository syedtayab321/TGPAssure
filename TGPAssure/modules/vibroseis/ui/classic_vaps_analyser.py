from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules.vibroseis.vaps_reader import VapsReader, VapsRecord, VapsQcEngine


_VAPS_CLASSIC_QSS = """
QWidget#classicVapsAnalyser {
    background:#F3F3F3;
    color:#111111;
    font-family: Arial, Helvetica, sans-serif;
    font-size: 7.5pt;
}
QGroupBox {
    border:1px solid #9E9E9E;
    margin-top:5px;
    padding-top:7px;
    background:#F3F3F3;
    font-size:7.5pt;
    font-weight:600;
}
QGroupBox::title { subcontrol-origin: margin; left:7px; padding:0 3px; }
QPushButton {
    background:#ECECEC;
    border:1px outset #D0D0D0;
    min-height:22px;
    max-height:25px;
    padding:1px 6px;
    font-size:7.5pt;
}
QPushButton:pressed { border:1px inset #D0D0D0; background:#DCDCDC; }
QRadioButton, QCheckBox { background:transparent; font-size:7.4pt; spacing:2px; }
QLabel#vibTag {
    border:1px solid #6C6C6C;
    min-width:23px;
    max-width:23px;
    min-height:13px;
    max-height:13px;
    font-size:6.7pt;
    font-weight:bold;
}
QLabel#copyright { color:red; font-size:7.4pt; background:transparent; }
QLabel#classicStatus { color:#202020; background:transparent; font-size:7.5pt; }
QLabel#activeAttrLabel { color:#12324A; background:#FFFFFF; border:1px solid #C4CDD8; padding:4px 8px; font-weight:600; }
QGroupBox#vibSelectPanel { background:#F9FAFC; border:1px solid #BFC7D0; }
QWidget#vibCell { background:#FFFFFF; border:1px solid #E1E5EA; }
QLabel#dayChip { color:#001B44; font-weight:bold; background:#FFFFFF; border:1px solid #B7C5D8; padding:2px 6px; }
QComboBox { background:#FFFFFF; border:1px solid #9E9E9E; min-height:20px; font-size:7.5pt; }
QScrollArea { border:0; background:#F3F3F3; }
"""


DISPLAY_ATTRS: list[tuple[str, str]] = [
    ("drive_level_pct", "Drive Level"),
    ("peak_distortion_pct", "Peak Distortion"),
    ("avg_stiffness", "Average Stiffness"),
    ("force_overload", "Force Overload"),
    ("excitation_overload", "Excitation Overload"),
    ("avg_phase_deg", "Average Phase"),
    ("avg_force", "Average Force"),
    ("status_code", "Status Code"),
    ("pressure_overload", "Pressure Overload"),
    ("hdop", "Horizontal Accuracy"),
    ("peak_phase_deg", "Peak Phase"),
    ("peak_force", "Peak Force"),
    ("mass_warning", "Mass Warning"),
    ("mass_overload", "Mass Overload"),
    ("spare_1", "Spare"),
    ("avg_distortion_pct", "Average Distortion"),
    ("avg_viscosity", "Average Viscosity"),
    ("plate_warning", "Plate Warning"),
    ("valve_overload", "Valve Overload"),
    ("spare_2", "Spare"),
]

_TAG_COLOURS = [
    "#000000", "#1E2BFF", "#FF1C1C", "#27E23C", "#F6EA1A",
    "#000000", "#1E2BFF", "#FF1C1C", "#27E23C", "#F6EA1A",
    "#000000", "#1E2BFF", "#FF1C1C", "#27E23C", "#F6EA1A",
    "#000000", "#1E2BFF", "#FF1C1C", "#27E23C", "#F6EA1A",
]


class _VapsClassicPlot(QWidget):
    hover_text = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(560, 310)
        self.setMouseTracking(True)
        self.records: list[VapsRecord] = []
        self.attr = "drive_level_pct"
        self.label = "Drive Level"
        self.selected_vibs: set[str] = set()
        self.filtered = False
        self._points: list[tuple[float, float, VapsRecord, QColor]] = []
        self._cursor: Optional[QPointF] = None
        self.palette_name = "Classic"
        self.show_lines = False

    def set_records(self, records: list[VapsRecord]) -> None:
        self.records = list(records or [])
        self.update()

    def set_display(self, attr: str, label: str, selected_vibs: set[str], filtered: bool, palette_name: str = "Classic", show_lines: bool = False) -> None:
        self.attr = attr
        self.label = label
        self.selected_vibs = set(selected_vibs)
        self.filtered = filtered
        self.palette_name = palette_name or "Classic"
        self.show_lines = bool(show_lines)
        self.update()

    def _value(self, record: VapsRecord) -> float | None:
        if self.attr.startswith("spare"):
            return None
        value = getattr(record, self.attr, None)
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        if self.attr == "status_code":
            try:
                return float(str(value).strip()) if str(value).strip() else None
            except Exception:
                return None
        if value is None or value == "":
            return None
        try:
            return float(value)
        except Exception:
            return None

    @staticmethod
    def _norm_vib(vib: str) -> str:
        text = str(vib or "").strip().lower().replace("vib", "").replace("v", "").strip()
        digits = "".join(ch for ch in text if ch.isdigit())
        return digits or text or "?"

    def _visible_records(self) -> list[VapsRecord]:
        rows = []
        engine = VapsQcEngine()
        for record in self.records:
            vib = self._norm_vib(record.vib)
            if self.selected_vibs and vib not in self.selected_vibs:
                continue
            value = self._value(record)
            if self.filtered and value is None:
                continue
            if self.filtered:
                status, _findings = engine.evaluate_record(record)
                if status == "FAIL" and value is None:
                    continue
            rows.append(record)
        return rows

    def _plot_rect(self) -> QRectF:
        return QRectF(46, 18, max(1, self.width() - 64), max(1, self.height() - 48))


    def _x_value(self, record: VapsRecord, fallback: int) -> float:
        text = str(record.time or "").strip()
        m = __import__("re").search(r"(\d{1,2}):(\d{2})(?::(\d{2}(?:\.\d+)?))?", text)
        if m:
            h = int(m.group(1)); mn = int(m.group(2)); sec = float(m.group(3) or 0.0)
            return h + mn / 60.0 + sec / 3600.0
        return float(record.source_line or fallback)

    def _colour_for_vib(self, vib: str, value: float, ymin: float, ymax: float) -> QColor:
        if self.palette_name == "Thermal":
            t = 0.0 if ymax <= ymin else max(0.0, min(1.0, (value - ymin) / (ymax - ymin)))
            return QColor(int(40 + 215 * t), int(45 + 90 * (1.0 - abs(t - 0.5) * 2.0)), int(220 * (1.0 - t)))
        if self.palette_name == "Traffic":
            t = 0.0 if ymax <= ymin else max(0.0, min(1.0, (value - ymin) / (ymax - ymin)))
            if t > 0.75: return QColor("#D7191C")
            if t > 0.50: return QColor("#FDAE61")
            return QColor("#1A9641")
        return QColor(_TAG_COLOURS[(int(vib) - 1) % len(_TAG_COLOURS)] if vib.isdigit() and int(vib) > 0 else "#000000")

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(255, 255, 255))
        plot = self._plot_rect()
        painter.setPen(QPen(QColor(125, 125, 125), 1))
        painter.drawRect(plot)

        rows = self._visible_records()
        self._points = []
        if not rows:
            painter.setPen(QPen(QColor(60, 60, 60), 1))
            painter.drawText(plot, Qt.AlignmentFlag.AlignCenter, "Open a VAPS/H26 file, then select vibs and display attribute from the top ribbon.")
            painter.end()
            return

        values: list[float] = []
        xvals: list[float] = []
        for i, rec in enumerate(rows):
            value = self._value(rec)
            if value is None or not np.isfinite(value):
                continue
            values.append(float(value))
            xvals.append(self._x_value(rec, i + 1))
        if not values:
            painter.setPen(QPen(QColor(60, 60, 60), 1))
            painter.drawText(plot, Qt.AlignmentFlag.AlignCenter, f"No numeric values available for {self.label}.")
            painter.end()
            return

        xmin, xmax = min(xvals), max(xvals)
        ymin, ymax = min(values), max(values)
        if xmax <= xmin:
            xmax = xmin + 1.0
        if ymax <= ymin:
            ymax = ymin + 1.0
        pad_y = (ymax - ymin) * 0.08
        ymin -= pad_y
        ymax += pad_y

        painter.setPen(QPen(QColor(222, 222, 222), 1))
        for i in range(1, 6):
            y = plot.top() + i / 6 * plot.height()
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
        painter.setPen(QPen(QColor(80, 80, 80), 1))
        painter.drawText(QRectF(2, plot.top(), 42, 16), Qt.AlignmentFlag.AlignRight, f"{ymax:.3g}")
        painter.drawText(QRectF(2, plot.bottom()-16, 42, 16), Qt.AlignmentFlag.AlignRight, f"{ymin:.3g}")
        painter.drawText(QRectF(plot.left(), plot.bottom()+4, 80, 16), Qt.AlignmentFlag.AlignLeft, f"{xmin:.3g}")
        painter.drawText(QRectF(plot.right()-80, plot.bottom()+4, 80, 16), Qt.AlignmentFlag.AlignRight, f"{xmax:.3g}")

        by_vib: dict[str, list[tuple[float, float, VapsRecord]]] = {}
        for i, rec in enumerate(rows):
            value = self._value(rec)
            if value is None or not np.isfinite(value):
                continue
            vib = self._norm_vib(rec.vib)
            x = self._x_value(rec, i + 1)
            by_vib.setdefault(vib, []).append((x, float(value), rec))

        def sort_key(v: str):
            return (int(v) if v.isdigit() else 999, v)

        for vib in sorted(by_vib, key=sort_key):
            # Per-point colour is used for non-classic palettes; the classic palette stays by vibrator.
            color = QColor(_TAG_COLOURS[(int(vib) - 1) % len(_TAG_COLOURS)] if vib.isdigit() and int(vib) > 0 else "#000000")
            painter.setPen(QPen(color, 1.15))
            pts = sorted(by_vib[vib], key=lambda p: p[0])
            last: Optional[QPointF] = None
            for x, y, rec in pts:
                sx = plot.left() + (x - xmin) / max(1e-12, xmax - xmin) * plot.width()
                sy = plot.bottom() - (y - ymin) / max(1e-12, ymax - ymin) * plot.height()
                pt = QPointF(float(sx), float(sy))
                point_color = self._colour_for_vib(vib, y, ymin, ymax)
                painter.setPen(QPen(point_color, 1.15))
                if self.show_lines and last is not None:
                    painter.drawLine(last, pt)
                painter.setBrush(point_color)
                painter.drawEllipse(pt, 2.8, 2.8)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                self._points.append((float(sx), float(sy), rec, point_color))
                last = pt

        painter.setPen(QPen(QColor(60, 60, 60), 1))
        painter.drawText(QRectF(plot.left(), plot.top(), plot.width(), 16), Qt.AlignmentFlag.AlignCenter, f"{self.label} — {'Filtered' if self.filtered else 'Raw'}")
        if self._cursor is not None and plot.contains(self._cursor):
            painter.setPen(QPen(QColor(210, 0, 0), 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(plot.left(), self._cursor.y()), QPointF(plot.right(), self._cursor.y()))
            painter.drawLine(QPointF(self._cursor.x(), plot.top()), QPointF(self._cursor.x(), plot.bottom()))
        painter.end()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        p = event.position()
        self._cursor = p if self._plot_rect().contains(p) else None
        if self._points and self._cursor is not None:
            d2 = [(x - p.x()) ** 2 + (y - p.y()) ** 2 for x, y, _r, _c in self._points]
            idx = int(np.argmin(d2))
            if d2[idx] <= 18 * 18:
                rec = self._points[idx][2]
                value = self._value(rec)
                self.hover_text.emit(
                    f"Vib {rec.vib or '?'} | VP {rec.vp or '?'} | {self.label}: {'' if value is None else f'{value:.6g}'} | line {rec.source_line}"
                )
        self.update()
        super().mouseMoveEvent(event)


class ClassicVapsAnalyser(QWidget):
    """Compact classic VAPS analyser body.

    Ribbon-driven VAPS analyser body.

    The display attribute radio buttons, Raw/Filtered mode, palette and export
    controls live in the Vibroseis ribbon.  The workspace only keeps a compact
    responsive vibrator selector, the plot and the status strip.
    """

    records_loaded = Signal(list, object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("classicVapsAnalyser")
        self.setStyleSheet(_VAPS_CLASSIC_QSS)
        self.records: list[VapsRecord] = []
        self.path: Optional[Path] = None
        self.vib_checks: dict[str, QCheckBox] = {}
        self.attr_buttons: dict[str, QRadioButton] = {}
        self.attr_group = QButtonGroup(self)
        self.attr_group.setExclusive(True)
        self.filtered_radio = QRadioButton("Filtered", self)
        self.raw_radio = QRadioButton("Raw", self)
        self.lines_check = QCheckBox("Connect")
        self.palette_combo = QComboBox(self)
        self.palette_combo.addItems(["Classic", "Thermal", "Traffic"])
        self.raw_radio.setChecked(True)
        self.filtered_radio.toggled.connect(self._refresh_plot)
        self.raw_radio.toggled.connect(self._refresh_plot)
        self.lines_check.toggled.connect(self._refresh_plot)
        self.palette_combo.currentTextChanged.connect(self._refresh_plot)
        for attr, label in DISPLAY_ATTRS:
            rb = QRadioButton(label, self)
            rb.hide()
            self.attr_buttons[attr] = rb
            self.attr_group.addButton(rb)
            rb.toggled.connect(self._refresh_plot)
        self.attr_buttons["drive_level_pct"].setChecked(True)
        self._build_ui()
        self._refresh_plot()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(3, 3, 3, 3)
        root.setSpacing(2)

        # Ribbon-only controls.  Keep the radio buttons and mode widgets alive
        # as state holders, but do not show the large in-page radio panel.
        for rb in self.attr_buttons.values():
            rb.hide()
        self.raw_radio.hide()
        self.filtered_radio.hide()
        self.lines_check.hide()
        self.palette_combo.hide()

        top_status = QHBoxLayout()
        top_status.setSpacing(8)
        self.active_attr_label = QLabel("Display: Drive Level  |  Mode: Raw  |  Palette: Classic")
        self.active_attr_label.setObjectName("activeAttrLabel")
        self.day_chip = QLabel("Day 1")
        self.day_chip.setObjectName("dayChip")
        top_status.addWidget(self.active_attr_label, 1)
        top_status.addWidget(self.day_chip, 0, Qt.AlignmentFlag.AlignRight)
        root.addLayout(top_status, 0)

        body = QHBoxLayout()
        body.setSpacing(4)

        select = QGroupBox("Select Vibrators")
        select.setObjectName("vibSelectPanel")
        select.setMinimumWidth(154)
        select.setMaximumWidth(220)
        sl_outer = QVBoxLayout(select)
        sl_outer.setContentsMargins(6, 8, 6, 6)
        sl_outer.setSpacing(5)

        quick = QGridLayout()
        quick.setHorizontalSpacing(3)
        quick.setVerticalSpacing(3)
        all_btn = QPushButton("All")
        all_btn.clicked.connect(self.select_all_vibs)
        none_btn = QPushButton("None")
        none_btn.clicked.connect(self.select_no_vibs)
        rst_btn = QPushButton("Reset")
        rst_btn.clicked.connect(self.reset_to_loaded)
        quick.addWidget(all_btn, 0, 0)
        quick.addWidget(none_btn, 0, 1)
        quick.addWidget(rst_btn, 1, 0, 1, 2)
        sl_outer.addLayout(quick)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumHeight(230)
        vib_holder = QWidget()
        vib_grid = QGridLayout(vib_holder)
        vib_grid.setContentsMargins(0, 0, 0, 0)
        vib_grid.setHorizontalSpacing(4)
        vib_grid.setVerticalSpacing(2)
        for i in range(1, 21):
            cell = QWidget()
            cell.setObjectName("vibCell")
            row = QHBoxLayout(cell)
            row.setContentsMargins(1, 0, 1, 0)
            row.setSpacing(2)
            cb = QCheckBox(str(i))
            cb.setToolTip(f"Vibrator {i}")
            cb.toggled.connect(self._refresh_plot)
            self.vib_checks[str(i)] = cb
            tag = QLabel(f"V{i}")
            tag.setObjectName("vibTag")
            fg = "white" if _TAG_COLOURS[i - 1] == "#000000" else "black"
            tag.setStyleSheet(f"background:{_TAG_COLOURS[i - 1]};color:{fg};border:1px solid #606060;font-weight:bold;")
            row.addWidget(cb, 1)
            row.addWidget(tag, 0)
            vib_grid.addWidget(cell, (i - 1) // 2, (i - 1) % 2)
        scroll.setWidget(vib_holder)
        sl_outer.addWidget(scroll, 1)
        body.addWidget(select, 0)

        self.plot = _VapsClassicPlot(self)
        self.plot.hover_text.connect(self._set_status)
        body.addWidget(self.plot, 1)
        root.addLayout(body, 1)

        self.status = QLabel("No VAPS/H26 file loaded")
        self.status.setObjectName("classicStatus")
        root.addWidget(self.status)
        copyright_label = QLabel("(c) Copyright Ian Vincent June")
        copyright_label.setObjectName("copyright")
        copyright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(copyright_label)

    def selected_attr(self) -> tuple[str, str]:
        for attr, rb in self.attr_buttons.items():
            if rb.isChecked():
                return attr, rb.text()
        return "drive_level_pct", "Drive Level"

    def selected_vibs(self) -> set[str]:
        return {key for key, cb in self.vib_checks.items() if cb.isChecked()}

    def load_records(self, records: list[VapsRecord], path: Optional[Path] = None) -> None:
        self.records = list(records or [])
        self.path = path
        self.plot.set_records(self.records)
        self.reset_to_loaded()
        self.status.setText(f"{path.name if path else 'Loaded records'} — {len(self.records):,} VAPS records")

    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open VAPS / H26 file",
            str(Path.home()),
            "VAPS/H26/Text (*.vaps *.h26 *.csv *.txt *.dat *.log);;All Files (*.*)",
        )
        if not path:
            return
        try:
            records = VapsReader().read(path)
            self.load_records(records, Path(path))
            self.records_loaded.emit(self.records, self.path)
        except Exception as exc:
            QMessageBox.critical(self, "VAPS Open Error", str(exc))

    def clear_records(self) -> None:
        self.records = []
        self.path = None
        self.plot.set_records([])
        self.select_no_vibs()
        self.status.setText("VAPS analyser cleared")

    def select_all_vibs(self) -> None:
        self._set_all(True)

    def select_no_vibs(self) -> None:
        self._set_all(False)

    def _set_all(self, checked: bool) -> None:
        for cb in self.vib_checks.values():
            cb.blockSignals(True)
            cb.setChecked(checked)
            cb.blockSignals(False)
        self._refresh_plot()

    def reset_to_loaded(self) -> None:
        loaded = {_VapsClassicPlot._norm_vib(r.vib) for r in self.records if _VapsClassicPlot._norm_vib(r.vib).isdigit()}
        for key, cb in self.vib_checks.items():
            cb.blockSignals(True)
            cb.setChecked(key in loaded if loaded else False)
            cb.blockSignals(False)
        self._refresh_plot()

    def set_attribute(self, attr: str) -> None:
        rb = self.attr_buttons.get(attr)
        if rb is None:
            return
        rb.setChecked(True)
        self._refresh_plot()

    def set_mode(self, filtered: bool) -> None:
        self.filtered_radio.blockSignals(True)
        self.raw_radio.blockSignals(True)
        self.filtered_radio.setChecked(bool(filtered))
        self.raw_radio.setChecked(not bool(filtered))
        self.filtered_radio.blockSignals(False)
        self.raw_radio.blockSignals(False)
        self._refresh_plot()

    def set_raw_mode(self) -> None:
        self.set_mode(False)

    def set_filtered_mode(self) -> None:
        self.set_mode(True)

    def set_connect(self, connected: bool) -> None:
        self.lines_check.blockSignals(True)
        self.lines_check.setChecked(bool(connected))
        self.lines_check.blockSignals(False)
        self._refresh_plot()

    def toggle_connect(self) -> None:
        self.set_connect(not self.lines_check.isChecked())

    def set_palette(self, palette_name: str) -> None:
        name = str(palette_name or "Classic").strip().title()
        if name not in {"Classic", "Thermal", "Traffic"}:
            name = "Classic"
        self.palette_combo.blockSignals(True)
        self.palette_combo.setCurrentText(name)
        self.palette_combo.blockSignals(False)
        self._refresh_plot()

    def _refresh_plot(self, *_args) -> None:
        # During construction, hidden radio buttons may emit toggled() before
        # the plot widget exists.  Ignore those early signals; the constructor
        # calls this method again immediately after _build_ui().
        if not hasattr(self, "plot"):
            return
        attr, label = self.selected_attr()
        mode = "Filtered" if self.filtered_radio.isChecked() else "Raw"
        palette = self.palette_combo.currentText() if hasattr(self, "palette_combo") else "Classic"
        connected = self.lines_check.isChecked() if hasattr(self, "lines_check") else False
        if hasattr(self, "active_attr_label"):
            self.active_attr_label.setText(f"Display: {label}  |  Mode: {mode}  |  Palette: {palette}  |  {'Connected points' if connected else 'Scatter'}")
        self.plot.set_display(attr, label, self.selected_vibs(), self.filtered_radio.isChecked(), palette, connected)
        self.plot.set_records(self.records)

    def _set_status(self, text: str) -> None:
        self.status.setText(text)


    def show_statistics_dialog(self) -> None:
        if not self.records:
            QMessageBox.information(self, "VAPS Statistics", "Load a VAPS/H26 file first.")
            return
        attr, label = self.selected_attr()
        rows = self.plot._visible_records()
        by_vib: dict[str, list[float]] = {}
        for record in rows:
            value = self.plot._value(record)
            if value is None or not np.isfinite(value):
                continue
            vib = _VapsClassicPlot._norm_vib(record.vib)
            by_vib.setdefault(vib, []).append(float(value))
        dlg = QDialog(self)
        dlg.setWindowTitle(f"VAPS Statistics — {label}")
        layout = QVBoxLayout(dlg)
        table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels(["Vib", "Count", "Min", "Mean", "Max", "Std Dev"])
        for vib, values in sorted(by_vib.items(), key=lambda kv: (int(kv[0]) if kv[0].isdigit() else 999, kv[0])):
            arr = np.asarray(values, dtype=float)
            row = table.rowCount(); table.insertRow(row)
            out = [vib, str(arr.size), f"{np.nanmin(arr):.6g}", f"{np.nanmean(arr):.6g}", f"{np.nanmax(arr):.6g}", f"{np.nanstd(arr):.6g}"]
            for col, text in enumerate(out):
                table.setItem(row, col, QTableWidgetItem(text))
        layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        dlg.resize(620, 360)
        dlg.exec()

    def export_bmp(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export VAPS analyser bitmap", "vaps_analyser.bmp", "BMP (*.bmp);;PNG (*.png)")
        if not path:
            return
        pixmap = QPixmap(self.size())
        self.render(pixmap)
        pixmap.save(path)
        self.status.setText(f"BMP exported: {path}")

    def print_view(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Print VAPS analyser to image", "vaps_analyser_print.png", "PNG (*.png);;BMP (*.bmp)")
        if not path:
            return
        pixmap = QPixmap(self.size())
        self.render(pixmap)
        pixmap.save(path)
        self.status.setText(f"Print image created: {path}")
