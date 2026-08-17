from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from .channel_offsets_dialog import ChannelOffsetsDialog
from .file_depth_assignment_dialog import FileDepthAssignmentDialog
from .hole_information_dialog import HoleInformationDialog
from .legacy_styles import LEGACY_DIALOG_QSS, CenteredDialog, button


class GeneralParametersDialog(CenteredDialog):
    """Modernized copy of the legacy Configure / General Parameters dialog."""

    def __init__(self, records, state: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("General Parameters")
        self.setModal(True)
        self.setStyleSheet(LEGACY_DIALOG_QSS)
        self.records = records
        self.state = state
        self.resize(600, 455)
        self.edits: dict[str, QLineEdit] = {}

        root = QHBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        left = QVBoxLayout()
        title = QLabel("General Project Parameters")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        left.addWidget(title)

        grid = QGridLayout()
        labels = ["Client", "Contractor", "Crew", "Country", "Area", "Block", "QC Contractor", "QC Name"]
        for row, label in enumerate(labels):
            rr = row if row < 6 else row + 2
            grid.addWidget(QLabel(label), rr, 0)
            edit = QLineEdit(str(state.get(label, "")))
            self.edits[label] = edit
            grid.addWidget(edit, rr, 1)
        left.addLayout(grid)
        left.addSpacing(12)
        line = QLabel("")
        line.setFixedHeight(1)
        line.setStyleSheet("background:#aaaaaa;")
        left.addWidget(line)
        self.auto_load = QCheckBox("Auto Load Picks if Exist")
        self.auto_write = QCheckBox("Auto Write SEGY on File Load")
        self.auto_load.setChecked(bool(state.get("Auto Load Picks if Exist", True)))
        self.auto_write.setChecked(bool(state.get("Auto Write SEGY on File Load", True)))
        left.addWidget(self.auto_load)
        left.addWidget(self.auto_write)

        bottom = QHBoxLayout()
        ok = button("OK", "okButton")
        cancel = button("Cancel", "cancelButton")
        ok.setMinimumWidth(115)
        cancel.setMinimumWidth(115)
        bottom.addWidget(ok)
        bottom.addWidget(cancel)
        left.addLayout(bottom)
        root.addLayout(left, 1)

        right = QVBoxLayout()
        for text in ("Client Logo", "Contractor", "QC Logo"):
            box = QLabel(text + "\n\n")
            box.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
            box.setMinimumSize(105, 74)
            box.setObjectName("logoBox")
            right.addWidget(box)
        right.addStretch(1)
        btn_row1 = QHBoxLayout()
        hole = button("Hole Information")
        load = button("Load")
        btn_row1.addWidget(hole)
        btn_row1.addWidget(load)
        right.addLayout(btn_row1)
        btn_row2 = QHBoxLayout()
        offsets = button("Channel Offsets")
        save = button("Save")
        btn_row2.addWidget(offsets)
        btn_row2.addWidget(save)
        right.addLayout(btn_row2)
        assignment = button("File Depth Assignments")
        right.addWidget(assignment)
        root.addLayout(right)

        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.accept)
        load.clicked.connect(lambda: None)
        hole.clicked.connect(self._show_hole)
        offsets.clicked.connect(self._show_offsets)
        assignment.clicked.connect(self._show_assignment)

    def _show_hole(self) -> None:
        dlg = HoleInformationDialog(self.state.get("hole_information", {}), self)
        dlg.channel_offsets_requested.connect(self._show_offsets)
        if dlg.exec() == QDialog.Accepted:
            self.state["hole_information"] = dlg.values()

    def _show_offsets(self) -> None:
        dlg = ChannelOffsetsDialog(self.state.get("channel_offsets", [0] * 24), self.state.get("receiver_type", "Geophone"), self)
        if dlg.exec() == QDialog.Accepted:
            offsets, receiver_type = dlg.values()
            self.state["channel_offsets"] = offsets
            self.state["receiver_type"] = receiver_type

    def _show_assignment(self) -> None:
        dlg = FileDepthAssignmentDialog(self.records, self.state.get("current_folder", ""), self)
        if dlg.exec() == QDialog.Accepted:
            dlg.apply_to_records()

    def values(self) -> dict:
        for key, edit in self.edits.items():
            self.state[key] = edit.text().strip()
        self.state["Auto Load Picks if Exist"] = self.auto_load.isChecked()
        self.state["Auto Write SEGY on File Load"] = self.auto_write.isChecked()
        return self.state
