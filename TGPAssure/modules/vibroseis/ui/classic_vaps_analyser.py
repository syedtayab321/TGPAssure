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
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
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

    def set_records(self, records: list[VapsRecord]) -> None:
        self.records = list(records or [])
        self.update()

    def set_display(self, attr: str, label: str, selected_vibs: set[str], filtered: bool) -> None:
        self.attr = attr
        self.label = label
        self.selected_vibs = set(selected_vibs)
        self.filtered = filtered
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
        return QRectF(36, 12, max(1, self.width() - 46), max(1, self.height() - 24))

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
            xvals.append(float(rec.source_line or i + 1))
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

        by_vib: dict[str, list[tuple[float, float, VapsRecord]]] = {}
        for i, rec in enumerate(rows):
            value = self._value(rec)
            if value is None or not np.isfinite(value):
                continue
            vib = self._norm_vib(rec.vib)
            x = float(rec.source_line or i + 1)
            by_vib.setdefault(vib, []).append((x, float(value), rec))

        def sort_key(v: str):
            return (int(v) if v.isdigit() else 999, v)

        for vib in sorted(by_vib, key=sort_key):
            color = QColor(_TAG_COLOURS[(int(vib) - 1) % len(_TAG_COLOURS)] if vib.isdigit() and int(vib) > 0 else "#000000")
            painter.setPen(QPen(color, 1.15))
            pts = sorted(by_vib[vib], key=lambda p: p[0])
            last: Optional[QPointF] = None
            for x, y, rec in pts:
                sx = plot.left() + (x - xmin) / max(1e-12, xmax - xmin) * plot.width()
                sy = plot.bottom() - (y - ymin) / max(1e-12, ymax - ymin) * plot.height()
                pt = QPointF(float(sx), float(sy))
                if last is not None:
                    painter.drawLine(last, pt)
                painter.setBrush(color)
                painter.drawEllipse(pt, 2.8, 2.8)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                self._points.append((float(sx), float(sy), rec, color))
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

    The old Open/Print/BMP/Display/432-mode controls are intentionally exposed
    through the top ribbon.  This widget now keeps only the data display area,
    left vibrator selector and status line so the workspace is not crowded.
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
        self.raw_radio.setChecked(True)
        self.filtered_radio.toggled.connect(self._refresh_plot)
        self.raw_radio.toggled.connect(self._refresh_plot)
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

        body = QHBoxLayout()
        body.setSpacing(4)

        select = QGroupBox("Select Vibs")
        select.setMaximumWidth(122)
        select.setMinimumWidth(106)
        sl_outer = QVBoxLayout(select)
        sl_outer.setContentsMargins(4, 7, 4, 4)
        sl_outer.setSpacing(2)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        vib_holder = QWidget()
        vib_layout = QVBoxLayout(vib_holder)
        vib_layout.setContentsMargins(0, 0, 0, 0)
        vib_layout.setSpacing(1)
        for i in range(1, 21):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(2)
            cb = QCheckBox(f"Vib {i}")
            cb.toggled.connect(self._refresh_plot)
            self.vib_checks[str(i)] = cb
            tag = QLabel(f"V{i}")
            tag.setObjectName("vibTag")
            fg = "white" if _TAG_COLOURS[i - 1] == "#000000" else "black"
            tag.setStyleSheet(f"background:{_TAG_COLOURS[i - 1]};color:{fg};border:1px solid #606060;font-weight:bold;")
            row.addWidget(cb, 1)
            row.addWidget(tag)
            vib_layout.addLayout(row)
        vib_layout.addStretch(1)
        scroll.setWidget(vib_holder)
        sl_outer.addWidget(scroll, 1)

        btnrow = QHBoxLayout()
        btnrow.setSpacing(2)
        all_btn = QPushButton("All")
        all_btn.clicked.connect(self.select_all_vibs)
        none_btn = QPushButton("None")
        none_btn.clicked.connect(self.select_no_vibs)
        rst_btn = QPushButton("Rst")
        rst_btn.clicked.connect(self.reset_to_loaded)
        btnrow.addWidget(all_btn)
        btnrow.addWidget(none_btn)
        btnrow.addWidget(rst_btn)
        sl_outer.addLayout(btnrow)
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

    def _refresh_plot(self) -> None:
        # During construction, hidden radio buttons may emit toggled() before
        # the plot widget exists.  Ignore those early signals; the constructor
        # calls this method again immediately after _build_ui().
        if not hasattr(self, "plot"):
            return
        attr, label = self.selected_attr()
        self.plot.set_display(attr, label, self.selected_vibs(), self.filtered_radio.isChecked())
        self.plot.set_records(self.records)

    def _set_status(self, text: str) -> None:
        self.status.setText(text)

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
