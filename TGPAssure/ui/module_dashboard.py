from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget


class ModuleDashboard(QWidget):
    def __init__(self, module: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.module = module
        self.records: list[dict[str, Any]] = []
        self.setObjectName('moduleDashboard')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        heading = QLabel(f'{module.title()} Quality Assurance')
        heading.setStyleSheet('font-size:20px;font-weight:700;color:#102A43;')
        description = QLabel(f'Import {module.title()} survey data, review validation results, and run the available correction and QC workflow.')
        description.setWordWrap(True)
        self.status = QLabel('No dataset loaded')
        self.status.setObjectName('moduleStatus')
        buttons = QHBoxLayout()
        upload = QPushButton('Upload CSV Data')
        upload.setProperty('variant', 'primary')
        upload.clicked.connect(self._upload)
        run = QPushButton('Run QC')
        run.clicked.connect(self._run_qc)
        buttons.addWidget(upload)
        buttons.addWidget(run)
        buttons.addStretch()
        self.results = QPlainTextEdit()
        self.results.setReadOnly(True)
        self.results.setPlaceholderText('Module results will appear here.')
        layout.addWidget(heading)
        layout.addWidget(description)
        layout.addSpacing(8)
        layout.addWidget(self.status)
        layout.addLayout(buttons)
        layout.addWidget(self.results, 1)

    def _upload(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, f'Upload {self.module.title()} Data', str(Path.home()), 'CSV files (*.csv)')
        if not path:
            return
        readers = {
            'gravity': ('modules.gravity.reader', 'GravityReader'),
            'em': ('modules.em.reader', 'EmReader'),
            'acquisition': ('modules.acquisition.reader', 'AcquisitionReader'),
        }
        if self.module not in readers:
            self.status.setText('Dedicated module required')
            self.results.setPlainText(f"{self.module.title()} uses its dedicated quality-control dashboard.")
            return
        module_name, class_name = readers[self.module]
        reader = getattr(__import__(module_name, fromlist=[class_name]), class_name)()
        try:
            self.records = reader.read(path)
            self.status.setText(f'Loaded {len(self.records):,} records from {Path(path).name}')
            self.results.setPlainText('Dataset loaded. Select Run QC to process it.')
        except Exception as error:
            self.status.setText('Import failed')
            self.results.setPlainText(str(error))

    def _run_qc(self) -> None:
        if not self.records:
            self.results.setPlainText('Upload a CSV dataset before running QC.')
            return
        try:
            if self.module == 'gravity':
                from modules.gravity.qc import BouguerCorrectionQC, FreeAirCorrectionQC, TidalCorrectionQC
                outcome = BouguerCorrectionQC().apply(FreeAirCorrectionQC().apply(TidalCorrectionQC().apply(self.records)['records'])['records'])
            elif self.module == 'em':
                from modules.em.qc import ImpedanceQC, PhaseQC
                outcome = PhaseQC().apply(ImpedanceQC().apply(self.records)['records'])
            else:
                from modules.acquisition.qc import InstrumentQC, TimingQC
                outcome = TimingQC().apply(InstrumentQC().apply(self.records)['records'])
            self.status.setText(f'QC complete: {"Passed" if outcome["passed"] else "Review findings"}')
            self.results.setPlainText('\n'.join([f'QC status: {"Passed" if outcome["passed"] else "Review required"}', f'Records processed: {len(outcome["records"]):,}', '', 'First processed record:', str(outcome['records'][0])]))
        except Exception as error:
            self.status.setText('QC failed')
            self.results.setPlainText(str(error))
