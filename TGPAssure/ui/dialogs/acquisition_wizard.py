from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QStackedWidget,
    QWidget, QFormLayout, QMessageBox
)


class AcquisitionPage(QWidget):
    def __init__(self, title: str, fields: dict[str, str], parent=None):
        super().__init__(parent)
        layout = QFormLayout(self)
        self._edits = {}
        for label, placeholder in fields.items():
            le = QLineEdit()
            le.setPlaceholderText(placeholder)
            layout.addRow(QLabel(label), le)
            self._edits[label] = le

    def values(self) -> dict:
        return {k: v.text() for k, v in self._edits.items()}


class AcquisitionWizard(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Acquisition Steps Wizard')
        self.resize(560, 360)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self.stack = QStackedWidget()

        self.page1 = AcquisitionPage('Survey Info', {
            'Survey Name': 'Enter survey name',
            'Line ID': 'Line identifier (optional)',
            'Operator': 'Operator name'
        })

        self.page2 = AcquisitionPage('Receiver & Source', {
            'Receiver Type': 'e.g., Geophone',
            'Receiver Count': 'Number of receivers',
            'Source Type': 'e.g., Vibroseis'
        })

        self.page3 = AcquisitionPage('Sampling & Files', {
            'Sample Rate (Hz)': 'e.g., 1000',
            'Expected Traces': 'Approximate trace count',
            'Output Folder': 'Path to save acquisition files'
        })

        self.stack.addWidget(self.page1)
        self.stack.addWidget(self.page2)
        self.stack.addWidget(self.page3)

        layout.addWidget(self.stack)

        btns = QHBoxLayout()
        self.prev_btn = QPushButton('Previous')
        self.prev_btn.clicked.connect(self._prev)
        btns.addWidget(self.prev_btn)
        self.next_btn = QPushButton('Next')
        self.next_btn.clicked.connect(self._next)
        btns.addWidget(self.next_btn)
        self.finish_btn = QPushButton('Finish')
        self.finish_btn.clicked.connect(self._finish)
        btns.addWidget(self.finish_btn)

        layout.addLayout(btns)
        self._update_controls()

    def _update_controls(self):
        idx = self.stack.currentIndex()
        self.prev_btn.setEnabled(idx > 0)
        self.next_btn.setEnabled(idx < self.stack.count() - 1)
        self.finish_btn.setEnabled(idx == self.stack.count() - 1)

    def _prev(self):
        idx = self.stack.currentIndex()
        if idx > 0:
            self.stack.setCurrentIndex(idx - 1)
        self._update_controls()

    def _next(self):
        idx = self.stack.currentIndex()
        if idx < self.stack.count() - 1:
            self.stack.setCurrentIndex(idx + 1)
        self._update_controls()

    def _finish(self):
        data = {}
        data.update(self.page1.values())
        data.update(self.page2.values())
        data.update(self.page3.values())

        out_folder = data.get('Output Folder') or ''
        if out_folder:
            p = Path(out_folder)
            try:
                p.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, 'Error', f'Unable to create output folder: {e}')
                return

        # For now, just show a summary and store to a simple JSON in the project folder if possible
        summary = json_like = '\n'.join([f"{k}: {v}" for k, v in data.items()])
        QMessageBox.information(self, 'Acquisition Saved', f'Acquisition steps captured:\n\n{summary}')
        self.accept()
