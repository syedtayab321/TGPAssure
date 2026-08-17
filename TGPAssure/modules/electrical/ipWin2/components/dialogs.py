from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .models import VesRow, complete_row, display_value, parse_float

_IPI_COMPONENT_QSS = """
QDialog {
    background:#ECEFF3;
    color:#1C2430;
    font-family:"Segoe UI", Arial, sans-serif;
    font-size:6.4pt;
}
QGroupBox {
    border:1px solid #AEB8C4;
    border-radius:2px;
    margin-top:8px;
    padding-top:8px;
    font-size:6.5pt;
    font-weight:800;
}
QGroupBox::title { subcontrol-origin: margin; left:8px; padding:0 3px; }
QPushButton {
    min-height:16px;
    padding:1px 6px;
    border:1px solid #B7C1CC;
    border-radius:3px;
    background:#FFFFFF;
    color:#263241;
    font-size:6.4pt;
    font-weight:700;
}
QPushButton:hover { background:#EAF4FF; border-color:#75A4D3; }
QPushButton#primaryButton { background:#DFF3E5; color:#0C6534; border-color:#83BD95; }
QPushButton#dangerButton { background:#FFE8E8; color:#A52828; border-color:#CC8B8B; }
QPushButton#warningButton { background:#FFF1D5; color:#875400; border-color:#D1A04C; }
QTableWidget {
    background:#FFFFFF;
    alternate-background-color:#F7F9FC;
    gridline-color:#CFD6DF;
    border:1px solid #BFC8D2;
    font-size:6.3pt;
    selection-background-color:#0B7DD7;
    selection-color:#FFFFFF;
}
QHeaderView::section {
    background:#E4E9EF;
    border:0;
    border-right:1px solid #C7D1DD;
    border-bottom:1px solid #C7D1DD;
    padding:1px 2px;
    font-size:6.3pt;
    font-weight:800;
}
QComboBox, QLineEdit, QDoubleSpinBox, QTextEdit {
    min-height:16px;
    border:1px solid #B8C2CC;
    border-radius:2px;
    background:#FFFFFF;
    padding:1px 4px;
    font-size:6.4pt;
}
QTabWidget::pane { border:1px solid #B8C2CC; background:#F8FAFC; }
QTabBar::tab { padding:3px 10px; font-size:6.4pt; }
"""

_ARRAY_TYPES = ["Schlumberger", "Pole-dipole", "Wenner", "Express (AB=2AOmax)"]


class VesPointEntryDialog(QDialog):
    """IPI-style New/Edit VES point dialog with editable table and live curve."""

    def __init__(self, rows: list[VesRow], array_type: str = "Schlumberger", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New VES point")
        self.resize(920, 430)
        self.setStyleSheet(_IPI_COMPONENT_QSS)
        self.rows: list[VesRow] = []
        self.array_type = array_type if array_type in _ARRAY_TYPES else "Schlumberger"
        self._building = True
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        top = QHBoxLayout()
        for icon_text, tip in [("📋", "Copy"), ("📂", "Open TXT"), ("💾", "Save TXT")]:
            tool = QPushButton(icon_text)
            tool.setToolTip(tip)
            tool.setFixedWidth(26)
            top.addWidget(tool)
            if "Open" in tip:
                tool.clicked.connect(self.open_txt)
            elif "Save" in tip:
                tool.clicked.connect(self.save_txt)
        self.array_combo = QComboBox()
        self.array_combo.addItems(_ARRAY_TYPES)
        self.array_combo.setCurrentText(self.array_type)
        self.array_combo.currentTextChanged.connect(lambda *_: self._recalculate_all())
        top.addWidget(QLabel("Array type:"))
        top.addWidget(self.array_combo)
        self.show_numbers = QCheckBox("Show numbers")
        self.show_numbers.stateChanged.connect(lambda *_: self._refresh_plot())
        top.addWidget(self.show_numbers)
        top.addStretch(1)
        root.addLayout(top)

        body = QHBoxLayout()
        self.table = QTableWidget(21, 8)
        self.table.setAlternatingRowColors(True)
        self.table.setHorizontalHeaderLabels(["N", "AB/2", "MN", "SP", "V", "I", "K", "Ro_a"])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(18)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        for c, w in enumerate([30, 58, 54, 54, 54, 54, 68, 72]):
            self.table.setColumnWidth(c, w)
        self.table.itemChanged.connect(self._on_table_changed)
        body.addWidget(self.table, 0)

        self.plot = pg.PlotWidget(background="#FFFFFF")
        self.plot.setLogMode(x=True, y=True)
        self.plot.showGrid(x=True, y=True, alpha=0.28)
        self.plot.setLabel("left", "Apparent resistivity")
        self.plot.setLabel("bottom", "Spacing")
        body.addWidget(self.plot, 1)
        root.addLayout(body, 1)

        buttons = QHBoxLayout()
        for text, obj, slot in [
            ("Open TXT", "warningButton", self.open_txt),
            ("Save TXT", "", self.save_txt),
            ("Recalc", "", self._recalculate_all),
        ]:
            btn = QPushButton(text)
            if obj:
                btn.setObjectName(obj)
            btn.clicked.connect(slot)
            buttons.addWidget(btn)
        buttons.addStretch(1)
        ok_btn = QPushButton("OK")
        ok_btn.setObjectName("primaryButton")
        ok_btn.clicked.connect(self.accept)
        add_btn = QPushButton("Add")
        add_btn.setEnabled(False)
        add_btn.setToolTip("Enabled after a valid edited row is available")
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("dangerButton")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(ok_btn)
        buttons.addWidget(add_btn)
        buttons.addWidget(cancel_btn)
        root.addLayout(buttons)

        self._fill(rows)
        self._building = False
        self._refresh_plot()

    def _fill(self, rows: list[VesRow]) -> None:
        self.table.clearContents()
        for i in range(self.table.rowCount()):
            item = QTableWidgetItem(str(i + 1))
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 0, item)
        for row, record in enumerate(rows[: self.table.rowCount()]):
            for col, value in enumerate([record.ab2, record.mn, record.sp, record.voltage, record.current, record.k, record.rhoa], start=1):
                self.table.setItem(row, col, QTableWidgetItem(display_value(value)))

    def _row_from_table(self, r: int) -> VesRow | None:
        vals = [parse_float(self.table.item(r, c).text()) if self.table.item(r, c) else math.nan for c in range(1, 8)]
        if not np.isfinite(vals[0]) and not np.isfinite(vals[-1]):
            return None
        return complete_row(VesRow(vals[0], vals[1], vals[2], vals[3], vals[4], vals[5], vals[6]), self.array_combo.currentText())

    def _on_table_changed(self, item: QTableWidgetItem) -> None:
        if self._building or item.column() == 0:
            return
        row = self._row_from_table(item.row())
        if row is not None:
            self._building = True
            self.table.setItem(item.row(), 6, QTableWidgetItem(display_value(row.k)))
            self.table.setItem(item.row(), 7, QTableWidgetItem(display_value(row.rhoa)))
            self._building = False
        self._refresh_plot()

    def _recalculate_all(self) -> None:
        self._building = True
        for r in range(self.table.rowCount()):
            row = self._row_from_table(r)
            if row is None:
                continue
            self.table.setItem(r, 6, QTableWidgetItem(display_value(row.k)))
            self.table.setItem(r, 7, QTableWidgetItem(display_value(row.rhoa)))
        self._building = False
        self._refresh_plot()

    def _refresh_plot(self) -> None:
        self.plot.clear()
        rows = [row for row in (self._row_from_table(i) for i in range(self.table.rowCount())) if row is not None]
        x = np.asarray([r.ab2 for r in rows], dtype=float)
        y = np.asarray([r.rhoa for r in rows], dtype=float)
        valid = np.isfinite(x) & np.isfinite(y) & (x > 0) & (y > 0)
        if np.any(valid):
            order = np.argsort(x[valid])
            xx, yy = x[valid][order], y[valid][order]
            self.plot.plot(xx, yy, pen=pg.mkPen("#111111", width=1.0), symbol="s", symbolSize=4, symbolPen="#333333", symbolBrush="#FFFFFF")
            if self.show_numbers.isChecked():
                for n, (a, b) in enumerate(zip(xx, yy), start=1):
                    label = pg.TextItem(str(n), color="#174A7C", anchor=(0, 1))
                    label.setPos(float(a), float(b))
                    self.plot.addItem(label)

    def accept(self) -> None:
        self.rows = [row for row in (self._row_from_table(i) for i in range(self.table.rowCount())) if row is not None]
        self.array_type = self.array_combo.currentText()
        super().accept()

    def open_txt(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open VES TXT", str(Path.home()), "Text files (*.txt *.dat *.csv);;All Files (*.*)")
        if not path:
            return
        rows = []
        for line in Path(path).read_text(errors="ignore").splitlines():
            vals = [parse_float(tok) for tok in line.replace(",", " ").replace(";", " ").split()]
            vals = [v for v in vals if np.isfinite(v)]
            if len(vals) >= 2:
                padded = vals + [math.nan] * 7
                rows.append(VesRow(padded[0], padded[1], padded[2], padded[3], padded[4], padded[5], padded[6]))
        self._building = True
        self._fill(rows)
        self._building = False
        self._refresh_plot()

    def save_txt(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save VES TXT", str(Path.home() / "ves_point.txt"), "Text files (*.txt *.dat);;All Files (*.*)")
        if not path:
            return
        rows = [row for row in (self._row_from_table(i) for i in range(self.table.rowCount())) if row is not None]
        with Path(path).open("w") as fh:
            fh.write("AB/2\tMN\tSP\tV\tI\tK\tRo_a\n")
            for row in rows:
                fh.write("\t".join(display_value(v) for v in (row.ab2, row.mn, row.sp, row.voltage, row.current, row.k, row.rhoa)) + "\n")


class ProfileInformationDialog(QDialog):
    """IPI-style Information/Profile comments + array coordinates dialog."""

    def __init__(self, comments: str, array_type: str, coordinates: Iterable[tuple[float, float]] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Information")
        self.resize(560, 405)
        self.setStyleSheet(_IPI_COMPONENT_QSS)
        self.comments = comments
        self.array_type = array_type if array_type in _ARRAY_TYPES else "Schlumberger"
        root = QHBoxLayout(self)
        left = QVBoxLayout()
        left.addWidget(QLabel("Profile comments"))
        self.comments_edit = QTextEdit()
        self.comments_edit.setPlainText(comments)
        self.comments_edit.setMaximumHeight(70)
        left.addWidget(self.comments_edit)
        self.count_label = QLabel("Number of points - 0")
        left.addWidget(self.count_label)
        row = QHBoxLayout()
        row.addWidget(QLabel("Array type"))
        self.array_combo = QComboBox()
        self.array_combo.addItems(_ARRAY_TYPES)
        self.array_combo.setCurrentText(self.array_type)
        row.addWidget(self.array_combo, 1)
        left.addLayout(row)
        group = QGroupBox("Coordinates' table")
        grid = QVBoxLayout(group)
        self.coord_table = QTableWidget(8, 3)
        self.coord_table.setHorizontalHeaderLabels(["X", "Y", "Z"])
        self.coord_table.verticalHeader().setVisible(False)
        self.coord_table.verticalHeader().setDefaultSectionSize(19)
        self.coord_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for r, xy in enumerate(list(coordinates or [])[:8]):
            vals = list(xy) + [math.nan]
            for c in range(3):
                self.coord_table.setItem(r, c, QTableWidgetItem(display_value(vals[c])))
        grid.addWidget(self.coord_table)
        left.addWidget(group, 1)
        root.addLayout(left, 1)
        side = QVBoxLayout()
        for text, obj, slot in [
            ("OK", "primaryButton", self.accept),
            ("New", "warningButton", self._clear),
            ("Cancel", "dangerButton", self.reject),
            ("Help", "", self._help),
        ]:
            btn = QPushButton(text)
            if obj:
                btn.setObjectName(obj)
            btn.clicked.connect(slot)
            side.addWidget(btn)
        side.addSpacing(10)
        for text in ["Line", "Join", "Delete", "Restore", "Copy", "Paste"]:
            side.addWidget(QPushButton(text))
        side.addStretch(1)
        root.addLayout(side)

    def _clear(self) -> None:
        self.comments_edit.clear()
        self.coord_table.clearContents()

    def _help(self) -> None:
        QMessageBox.information(self, "Information", "Enter profile comments, select array type and optionally store coordinate rows for the VES profile.")

    def accept(self) -> None:
        self.comments = self.comments_edit.toPlainText().strip()
        self.array_type = self.array_combo.currentText()
        super().accept()


class IpiOptionsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Options")
        self.resize(360, 190)
        self.setStyleSheet(_IPI_COMPONENT_QSS)
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        autosave_page = QWidget()
        grid = QGridLayout(autosave_page)
        self.autosave = QCheckBox("Autosaving")
        self.autosave.setChecked(True)
        self.autosave_every = QCheckBox("Autosave every")
        self.interval = QDoubleSpinBox()
        self.interval.setRange(0, 120)
        self.interval.setDecimals(0)
        self.interval.setSuffix(" min.")
        grid.addWidget(self.autosave, 0, 0)
        grid.addWidget(self.autosave_every, 1, 0)
        grid.addWidget(self.interval, 1, 1)
        grid.addWidget(QCheckBox("Confirmation for exit"), 2, 0)
        grid.addWidget(QCheckBox("Wrap lines in DAT file"), 3, 0)
        tabs.addTab(autosave_page, "Autosave")
        model_page = QWidget()
        mgrid = QGridLayout(model_page)
        mgrid.addWidget(QLabel("Default layers"), 0, 0)
        layers = QDoubleSpinBox(); layers.setDecimals(0); layers.setRange(2, 12); layers.setValue(4)
        mgrid.addWidget(layers, 0, 1)
        mgrid.addWidget(QCheckBox("Create new model after loading curve"), 1, 0, 1, 2)
        tabs.addTab(model_page, "New model")
        root.addWidget(tabs)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Help)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.helpRequested.connect(lambda: QMessageBox.information(self, "Options", "Configure autosave and default model behavior."))
        root.addWidget(buttons)


class IpiSectionOptionsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Section options")
        self.setStyleSheet(_IPI_COMPONENT_QSS)
        root = QVBoxLayout(self)
        group = QGroupBox("Section display")
        grid = QGridLayout(group)
        self.show_pseudo = QCheckBox("Pseudo-section")
        self.show_model = QCheckBox("Resistivity section")
        self.show_pseudo.setChecked(True)
        self.show_model.setChecked(True)
        grid.addWidget(self.show_pseudo, 0, 0)
        grid.addWidget(self.show_model, 1, 0)
        grid.addWidget(QLabel("Depth multiplier"), 2, 0)
        self.depth_multiplier = QDoubleSpinBox(); self.depth_multiplier.setRange(0.25, 10.0); self.depth_multiplier.setValue(1.0); self.depth_multiplier.setSingleStep(0.25)
        grid.addWidget(self.depth_multiplier, 2, 1)
        grid.addWidget(QCheckBox("Horizontal mirror"), 3, 0)
        grid.addWidget(QCheckBox("Logarithmic color scale"), 4, 0)
        root.addWidget(group)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        root.addWidget(buttons)


class IpiInversionOptionsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Inversion option")
        self.setStyleSheet(_IPI_COMPONENT_QSS)
        root = QVBoxLayout(self)
        group = QGroupBox("Inversion control")
        grid = QGridLayout(group)
        self.iterations = QDoubleSpinBox(); self.iterations.setDecimals(0); self.iterations.setRange(1, 50); self.iterations.setValue(8)
        self.damping = QDoubleSpinBox(); self.damping.setRange(0.0, 1.0); self.damping.setSingleStep(0.05); self.damping.setValue(0.2)
        grid.addWidget(QLabel("Iterations"), 0, 0); grid.addWidget(self.iterations, 0, 1)
        grid.addWidget(QLabel("Damping"), 1, 0); grid.addWidget(self.damping, 1, 1)
        grid.addWidget(QCheckBox("Respect fixed H layers"), 2, 0, 1, 2)
        grid.addWidget(QCheckBox("Smooth model"), 3, 0, 1, 2)
        root.addWidget(group)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        root.addWidget(buttons)


class IpiAxesLimitsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Axes' limits")
        self.setStyleSheet(_IPI_COMPONENT_QSS)
        root = QGridLayout(self)
        self.xmin = QDoubleSpinBox(); self.xmin.setRange(0, 1e9); self.xmin.setValue(1)
        self.xmax = QDoubleSpinBox(); self.xmax.setRange(0, 1e9); self.xmax.setValue(1000)
        self.ymin = QDoubleSpinBox(); self.ymin.setRange(0, 1e9); self.ymin.setValue(1)
        self.ymax = QDoubleSpinBox(); self.ymax.setRange(0, 1e9); self.ymax.setValue(1000)
        for row, (label, widget) in enumerate([("X min", self.xmin), ("X max", self.xmax), ("Y min", self.ymin), ("Y max", self.ymax)]):
            root.addWidget(QLabel(label), row, 0); root.addWidget(widget, row, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        root.addWidget(buttons, 4, 0, 1, 2)


class IpiLayerConstraintDialog(QDialog):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setStyleSheet(_IPI_COMPONENT_QSS)
        root = QVBoxLayout(self)
        group = QGroupBox(title)
        grid = QGridLayout(group)
        self.rho = QDoubleSpinBox(); self.rho.setRange(0.001, 1e9); self.rho.setValue(10)
        self.h = QDoubleSpinBox(); self.h.setRange(0.001, 1e6); self.h.setValue(1)
        grid.addWidget(QLabel("ρ"), 0, 0); grid.addWidget(self.rho, 0, 1)
        grid.addWidget(QLabel("h"), 1, 0); grid.addWidget(self.h, 1, 1)
        root.addWidget(group)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        root.addWidget(buttons)


class IpiChoiceDialog(QDialog):
    def __init__(self, title: str, label: str, options: list[str], current: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setStyleSheet(_IPI_COMPONENT_QSS)
        root = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        self.combo = QComboBox(); self.combo.addItems(options); self.combo.setCurrentIndex(current)
        row.addWidget(self.combo)
        root.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    @staticmethod
    def get_choice(parent: QWidget, title: str, label: str, options: list[str], current: int = 0) -> tuple[str, bool]:
        dlg = IpiChoiceDialog(title, label, options, current, parent)
        ok = dlg.exec() == QDialog.Accepted
        return dlg.combo.currentText(), ok
