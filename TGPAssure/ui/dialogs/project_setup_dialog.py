from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLineEdit, QPushButton, QTextEdit, QVBoxLayout, QWidget


class ProjectSetupDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle('Create Project')
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText('e.g. Kirthar 2026 Seismic Survey')
        self.code_edit = QLineEdit()
        self.discipline_combo = QComboBox()
        self.discipline_combo.addItems(['Seismic 2D/3D', 'Seismic 4D / Time-Lapse', 'Ground Magnetic', 'Drone Magnetic', 'Airborne Magnetic', 'Marine Magnetic', 'Land Gravity', 'Microgravity', 'Integrated Seismic, Magnetic and Gravity'])
        self.client_edit = QLineEdit()
        self.area_edit = QLineEdit()
        self.coordinate_edit = QLineEdit()
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.classification_combo = QComboBox()
        self.classification_combo.addItems(['Confidential', 'Restricted', 'Internal', 'Public'])
        self.description_edit = QTextEdit()
        self.description_edit.setFixedHeight(86)
        self.location_edit = QLineEdit(str(Path.home()))
        browse = QPushButton('Browse…')
        browse.clicked.connect(self._select_location)
        location_row = QHBoxLayout()
        location_row.addWidget(self.location_edit)
        location_row.addWidget(browse)
        location_widget = QWidget()
        location_widget.setLayout(location_row)
        for label, widget in [('Project name *', self.name_edit), ('Project code', self.code_edit), ('Discipline *', self.discipline_combo), ('Client / operator', self.client_edit), ('Survey area', self.area_edit), ('Coordinate reference system', self.coordinate_edit), ('Survey start date', self.date_edit), ('Data classification', self.classification_combo), ('Description', self.description_edit), ('Project location *', location_widget)]:
            form.addRow(label, widget)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Ok).setText('Create Project')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _select_location(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, 'Select Project Location', self.location_edit.text())
        if folder:
            self.location_edit.setText(folder)

    def accept(self) -> None:
        if self.name_edit.text().strip() and self.location_edit.text().strip():
            super().accept()

    def project_data(self) -> dict[str, str]:
        return {'name': self.name_edit.text().strip(), 'code': self.code_edit.text().strip(), 'discipline': self.discipline_combo.currentText(), 'client': self.client_edit.text().strip(), 'survey_area': self.area_edit.text().strip(), 'crs': self.coordinate_edit.text().strip(), 'survey_start_date': self.date_edit.date().toString('yyyy-MM-dd'), 'classification': self.classification_combo.currentText(), 'description': self.description_edit.toPlainText().strip(), 'location': self.location_edit.text().strip()}
