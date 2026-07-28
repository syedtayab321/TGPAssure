from __future__ import annotations

from pathlib import Path
from datetime import datetime
import hashlib

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFormLayout, QLineEdit, QTextEdit, QPushButton,
    QHBoxLayout, QGroupBox, QSizePolicy, QToolButton
)


class PropertiesPanel(QWidget):
    run_qc = Signal(str)
    generate_report = Signal(str, str)
    view_in_explorer = Signal(str)
    delete_file = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('propertiesPanel')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.setStyleSheet("""
            QWidget#propertiesPanel {
                background-color: #FFFFFF;
                color: #1F1F1F;
            }
            QWidget#propertiesPanel QGroupBox {
                background-color: #FFFFFF;
                color: #1F1F1F;
            }
            QWidget#propertiesPanel QLabel {
                background-color: transparent;
                color: #1F1F1F;
            }
            QWidget#propertiesPanel QLineEdit,
            QWidget#propertiesPanel QTextEdit {
                background-color: #FFFFFF;
                color: #1F1F1F;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        self.info_group = QGroupBox('General')
        info_layout = QFormLayout()
        self.name_label = QLabel('')
        self.type_label = QLabel('')
        self.size_label = QLabel('')
        self.import_date_label = QLabel('')
        self.sha_label = QLabel('')
        self.qc_status_label = QLabel('')
        info_layout.addRow('Name', self.name_label)
        info_layout.addRow('Type', self.type_label)
        info_layout.addRow('Size', self.size_label)
        info_layout.addRow('Import Date', self.import_date_label)
        info_layout.addRow('SHA-256', self.sha_label)
        info_layout.addRow('QC Status', self.qc_status_label)
        self.info_group.setLayout(info_layout)
        layout.addWidget(self.info_group)

        self.meta_group = QGroupBox('Details')
        meta_layout = QFormLayout()
        self.survey_edit = QLineEdit()
        self.client_edit = QLineEdit()
        self.operator_edit = QLineEdit()
        self.acq_date_edit = QLineEdit()
        self.notes_edit = QTextEdit()
        meta_layout.addRow('Survey Name', self.survey_edit)
        meta_layout.addRow('Client', self.client_edit)
        meta_layout.addRow('Operator', self.operator_edit)
        meta_layout.addRow('Acquisition Date', self.acq_date_edit)
        meta_layout.addRow('Processing Notes', self.notes_edit)
        self.meta_group.setLayout(meta_layout)
        layout.addWidget(self.meta_group)

        actions = QHBoxLayout()
        self.run_qc_btn = QPushButton('Run QC')
        self.report_btn = QPushButton('Generate Report')
        self.view_btn = QPushButton('View in Explorer')
        self.delete_btn = QPushButton('Delete')
        actions.addWidget(self.run_qc_btn)
        actions.addWidget(self.report_btn)
        actions.addWidget(self.view_btn)
        actions.addWidget(self.delete_btn)
        layout.addLayout(actions)

        self.run_qc_btn.clicked.connect(self._on_run_qc)
        self.report_btn.clicked.connect(self._on_generate_report)
        self.view_btn.clicked.connect(self._on_view)
        self.delete_btn.clicked.connect(self._on_delete)

        layout.addStretch()
        self._current_path = None

    def load_path(self, path: str):
        p = Path(path)
        self._current_path = path
        self.name_label.setText(p.name)
        self.type_label.setText(p.suffix.lstrip('.') or 'folder')
        try:
            sz = p.stat().st_size
            self.size_label.setText(f'{sz} bytes')
            mtime = datetime.fromtimestamp(p.stat().st_mtime)
            self.import_date_label.setText(mtime.isoformat(sep=' ', timespec='seconds'))
            self.sha_label.setText(self._compute_sha(p) if p.is_file() else '')
        except Exception:
            self.size_label.setText('')
            self.import_date_label.setText('')
            self.sha_label.setText('')
        self.qc_status_label.setText('Not Run')

    def _compute_sha(self, p: Path) -> str:
        try:
            h = hashlib.sha256()
            with p.open('rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return ''

    def _on_run_qc(self):
        if self._current_path:
            self.run_qc.emit(self._current_path)

    def _on_generate_report(self):
        if self._current_path:
            self.generate_report.emit(self._current_path, 'pdf')

    def _on_view(self):
        if self._current_path:
            self.view_in_explorer.emit(self._current_path)

    def _on_delete(self):
        if self._current_path:
            self.delete_file.emit(self._current_path)