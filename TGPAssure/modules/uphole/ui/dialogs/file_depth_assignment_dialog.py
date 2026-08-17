from __future__ import annotations

import csv
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout

from modules.uphole import UpholeShot
from .legacy_styles import LEGACY_DIALOG_QSS, CenteredDialog, button


class FileDepthAssignmentDialog(CenteredDialog):
    """Legacy File - Depth Assignment table for Load a Hole workflow."""

    def __init__(self, records: list[UpholeShot], folder: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("File - Depth Assignment")
        self.setModal(True)
        self.setStyleSheet(LEGACY_DIALOG_QSS)
        self.records = records
        self.folder = folder or ""
        self.resize(555, 610)

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        side = QVBoxLayout()
        self.folder_label = QLabel(self.folder.upper() if self.folder else "")
        self.folder_label.setWordWrap(True)
        self.folder_label.setStyleSheet("color:#9a9800; font-weight:800;")
        side.addWidget(self.folder_label)
        select_folder = button("Select Folder")
        save_assignment = button("Save Assignment", "saveAssignment")
        load_assignment = button("Load Assignment")
        save_default = button("Save as Default")
        load_default = button("Load Default")
        invert_depths = button("Invert Depths")
        invert_offsets = button("Invert Offsets")
        clear = button("Clear")
        close = button("Close", "closeButton")
        for btn in (select_folder, save_assignment, load_assignment, save_default, load_default, invert_depths, invert_offsets, clear):
            btn.setMinimumWidth(135)
            side.addWidget(btn)
            side.addSpacing(7)
        side.addStretch(1)
        close.setMinimumWidth(135)
        side.addWidget(close)
        root.addLayout(side)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["File", "Depth", "Offset"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, 1)

        self._populate()
        close.clicked.connect(self.accept)
        clear.clicked.connect(self._clear)
        invert_depths.clicked.connect(lambda: self._invert_column(1))
        invert_offsets.clicked.connect(lambda: self._invert_column(2))
        save_assignment.clicked.connect(self._save_assignment)
        load_assignment.clicked.connect(self._load_assignment)
        save_default.clicked.connect(self._save_assignment)
        load_default.clicked.connect(self._load_assignment)
        select_folder.clicked.connect(self._select_folder)

    def _populate(self) -> None:
        self.table.setRowCount(0)
        for rec in self.records:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(rec.file_name))
            self.table.setItem(row, 1, QTableWidgetItem("" if rec.depth_m is None else str(rec.depth_m)))
            self.table.setItem(row, 2, QTableWidgetItem("" if rec.offset_m is None else str(rec.offset_m)))

    def apply_to_records(self) -> None:
        for row, rec in enumerate(self.records):
            rec.file_name = self.table.item(row, 0).text().strip() if self.table.item(row, 0) else rec.file_name
            rec.depth_m = self._float_cell(row, 1)
            rec.offset_m = self._float_cell(row, 2)

    def _float_cell(self, row: int, col: int) -> float | None:
        item = self.table.item(row, col)
        if not item or not item.text().strip():
            return None
        try:
            return float(item.text().strip())
        except ValueError:
            return None

    def _clear(self) -> None:
        for row in range(self.table.rowCount()):
            self.table.setItem(row, 1, QTableWidgetItem("0"))
            self.table.setItem(row, 2, QTableWidgetItem("0"))

    def _invert_column(self, col: int) -> None:
        vals = []
        for row in range(self.table.rowCount()):
            vals.append(self.table.item(row, col).text() if self.table.item(row, col) else "")
        vals.reverse()
        for row, val in enumerate(vals):
            self.table.setItem(row, col, QTableWidgetItem(val))

    def _save_assignment(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save Assignment", "uphole_depth_assignment.fda", "Assignment (*.fda *.csv);;CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["file_name", "depth_m", "offset_m"])
            for row in range(self.table.rowCount()):
                writer.writerow([
                    self.table.item(row, 0).text() if self.table.item(row, 0) else "",
                    self.table.item(row, 1).text() if self.table.item(row, 1) else "",
                    self.table.item(row, 2).text() if self.table.item(row, 2) else "",
                ])

    def _load_assignment(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load Assignment", "", "Assignment (*.fda *.csv);;All files (*.*)")
        if not path:
            return
        with open(path, newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
        by_file = {str(r.get("file_name", "")).strip(): r for r in rows}
        for row in range(self.table.rowCount()):
            fname = self.table.item(row, 0).text() if self.table.item(row, 0) else ""
            src = by_file.get(fname)
            if src:
                self.table.setItem(row, 1, QTableWidgetItem(str(src.get("depth_m", ""))))
                self.table.setItem(row, 2, QTableWidgetItem(str(src.get("offset_m", ""))))

    def _select_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Uphole Folder")
        if folder:
            self.folder = folder
            self.folder_label.setText(folder.upper())
