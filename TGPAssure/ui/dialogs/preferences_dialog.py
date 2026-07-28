from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QSpinBox, QVBoxLayout
)


class PreferencesDialog(QDialog):
    """Preferences whose controls are backed by implemented application behavior."""

    def __init__(self, settings_store, parent=None) -> None:
        super().__init__(parent)
        self._store = settings_store
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(480)

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.autosave = QSpinBox(self)
        self.autosave.setRange(0, 120)
        self.autosave.setSuffix(" min")
        self.autosave.setSpecialValueText("Disabled")
        self.autosave.setValue(int(settings_store.get("autosave_minutes", 10) or 0))

        self.confirm = QCheckBox("Confirm before closing unsaved project state", self)
        self.confirm.setChecked(bool(settings_store.get("confirm_close", True)))

        self.open_last = QCheckBox("Restore last project on startup", self)
        self.open_last.setChecked(bool(settings_store.get("restore_last_project", False)))

        self.google_maps_key = QLineEdit(self)
        self.google_maps_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.google_maps_key.setPlaceholderText("Google Maps Platform API key")
        self.google_maps_key.setText(str(settings_store.get("google_maps_api_key", "") or ""))
        self.google_maps_key.setToolTip(
            "Used by the shared satellite and 3D terrain viewer. 2D satellite also has a no-key "
            "fallback. Google mode requires Maps JavaScript API activation, billing, and compatible "
            "key restrictions."
        )
        maps_note = QLabel(
            "2D satellite works in Auto/Free 2D mode without a Google key using no-key imagery. "
            "Google 2D/3D requires Maps JavaScript API to be enabled on the selected Google Cloud "
            "project, billing to be active, and key restrictions to allow the desktop WebEngine origin. "
            "The key is stored only in the local TGPAssure settings database; alternatively set "
            "TGPASSURE_GOOGLE_MAPS_API_KEY in the environment."
        )
        maps_note.setWordWrap(True)
        maps_note.setStyleSheet("color:#667085;font-size:9pt;")

        form.addRow("Autosave interval", self.autosave)
        form.addRow("", self.confirm)
        form.addRow("", self.open_last)
        form.addRow("Google Maps Platform", self.google_maps_key)
        form.addRow("", maps_note)
        root.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _save(self) -> None:
        self._store.set("autosave_minutes", self.autosave.value())
        self._store.set("confirm_close", self.confirm.isChecked())
        self._store.set("restore_last_project", self.open_last.isChecked())
        self._store.set("google_maps_api_key", self.google_maps_key.text().strip())
        self.accept()
