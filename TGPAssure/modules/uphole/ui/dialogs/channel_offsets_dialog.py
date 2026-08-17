from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QButtonGroup, QDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QRadioButton, QSpinBox, QVBoxLayout

from .legacy_styles import LEGACY_DIALOG_QSS, CenteredDialog, button


class ChannelOffsetsDialog(CenteredDialog):
    """Legacy-style channel-offset entry dialog, max 24 receivers."""

    def __init__(self, offsets: list[float] | None = None, receiver_type: str = "Geophone", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Channel Offsets")
        self.setModal(True)
        self.setStyleSheet(LEGACY_DIALOG_QSS)
        self.resize(560, 570)
        self.offset_edits: list[QLineEdit] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        top = QHBoxLayout()
        top.addStretch(1)
        top.addWidget(QLabel("Number of Receivers (Max 24)"))
        self.receiver_count = QSpinBox()
        self.receiver_count.setRange(1, 24)
        self.receiver_count.setValue(min(max(len(offsets or [0] * 24), 1), 24))
        top.addWidget(self.receiver_count)
        set_btn = button("Set")
        top.addWidget(set_btn)
        top.addStretch(1)
        root.addLayout(top)

        title = QLabel("Channel offsets to be added to entered")
        title.setObjectName("sectionLabel")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(5)
        values = list(offsets or []) + [0] * 24
        for i in range(24):
            label = QLabel(f"Channel {i + 1}")
            edit = QLineEdit(str(values[i]))
            edit.setMaximumWidth(68)
            self.offset_edits.append(edit)
            row = i % 12
            col = 0 if i < 12 else 2
            grid.addWidget(label, row, col)
            grid.addWidget(edit, row, col + 1)
        root.addLayout(grid)

        radios = QHBoxLayout()
        self.type_group = QButtonGroup(self)
        self.type_radios: dict[str, QRadioButton] = {}
        for label in ("Hydrophone", "Geophone", "Other"):
            rb = QRadioButton(label)
            self.type_group.addButton(rb)
            self.type_radios[label] = rb
            radios.addWidget(rb)
        self.type_radios.get(receiver_type, self.type_radios["Geophone"]).setChecked(True)
        root.addLayout(radios)

        clear = button("Clear All")
        clear.setMinimumWidth(150)
        clear.clicked.connect(self.clear_all)
        root.addWidget(clear, alignment=Qt.AlignCenter)

        bottom = QHBoxLayout()
        cancel = button("Cancel", "cancelButton")
        save = button("Save")
        load = button("Load")
        ok = button("OK", "okButton")
        bottom.addWidget(cancel)
        bottom.addStretch(1)
        bottom.addWidget(save)
        bottom.addWidget(load)
        bottom.addStretch(1)
        bottom.addWidget(ok)
        root.addLayout(bottom)
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.accept)
        ok.clicked.connect(self.accept)
        load.clicked.connect(lambda: None)
        set_btn.clicked.connect(self._apply_receiver_count)
        self._apply_receiver_count()

    def _apply_receiver_count(self) -> None:
        n = self.receiver_count.value()
        for i, edit in enumerate(self.offset_edits):
            edit.setEnabled(i < n)

    def clear_all(self) -> None:
        for edit in self.offset_edits:
            edit.setText("0")

    def values(self) -> tuple[list[float], str]:
        out: list[float] = []
        for edit in self.offset_edits[: self.receiver_count.value()]:
            try:
                out.append(float(edit.text().strip() or "0"))
            except ValueError:
                out.append(0.0)
        rtype = "Geophone"
        for name, rb in self.type_radios.items():
            if rb.isChecked():
                rtype = name
                break
        return out, rtype
