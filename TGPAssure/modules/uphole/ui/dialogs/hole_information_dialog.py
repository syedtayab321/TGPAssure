from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QFormLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from .legacy_styles import LEGACY_DIALOG_QSS, CenteredDialog, button


class HoleInformationDialog(CenteredDialog):
    """Legacy-style Hole Information window used by UYH uphole workflow."""

    channel_offsets_requested = Signal()

    FIELDS = [
        "Hole Name", "Line", "Point", "Easting (X)", "Northing (Y)", "Elevation (Z)",
        "Drill Rig", "Hole Diameter", "Driller's Name", "Date Start Drilling", "Date End Drilling",
        "Total Depth Drilled", "Qty Bentonite", "Qty LCM Used", "Qty Bits Used", "Date Logged",
        "Recording system", "Observer name", "Total Depth",
    ]

    def __init__(self, data: dict[str, str] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Hole Information")
        self.setModal(True)
        self.setStyleSheet(LEGACY_DIALOG_QSS)
        self.resize(620, 640)
        self.edits: dict[str, QLineEdit] = {}
        data = data or {}

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        left = QWidget()
        form = QFormLayout(left)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(5)
        for name in self.FIELDS:
            edit = QLineEdit(str(data.get(name, "")))
            if name.startswith("Date"):
                edit.setPlaceholderText("DD/MM/YYYY")
            self.edits[name] = edit
            form.addRow(QLabel(name), edit)
        root.addWidget(left, 1)

        side = QVBoxLayout()
        side.addSpacing(10)
        ok = button("OK", "okButton")
        offsets = button("Channel Offsets")
        new_hole = button("New Hole (Clear All)")
        load = button("Load")
        save = button("Save")
        cancel = button("Cancel", "cancelButton")
        for btn in (ok, offsets, new_hole, load, save):
            btn.setMinimumWidth(135)
            side.addWidget(btn)
            side.addSpacing(14)
        side.addStretch(1)
        cancel.setMinimumWidth(135)
        side.addWidget(cancel)
        root.addLayout(side)

        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        new_hole.clicked.connect(self.clear_all)
        offsets.clicked.connect(self.channel_offsets_requested.emit)
        save.clicked.connect(self.accept)
        load.clicked.connect(lambda: None)

    def clear_all(self) -> None:
        for edit in self.edits.values():
            edit.clear()

    def values(self) -> dict[str, str]:
        return {key: edit.text().strip() for key, edit in self.edits.items()}
