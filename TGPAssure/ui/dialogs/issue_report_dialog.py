from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtWidgets import QComboBox,QDialog,QDialogButtonBox,QFileDialog,QFormLayout,QLineEdit,QMessageBox,QPlainTextEdit,QVBoxLayout


class IssueReportDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent); self.setWindowTitle("Report Issue"); self.setMinimumSize(600,500); root=QVBoxLayout(self); form=QFormLayout()
        self.category=QComboBox(self); self.category.addItems(["Bug","Data/QC issue","Performance","UI/Workflow","Other"])
        self.summary=QLineEdit(self); self.steps=QPlainTextEdit(self); self.expected=QPlainTextEdit(self)
        form.addRow("Category",self.category); form.addRow("Summary",self.summary); form.addRow("Steps / details",self.steps); form.addRow("Expected behavior",self.expected); root.addLayout(form)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel,self); buttons.accepted.connect(self._save); buttons.rejected.connect(self.reject); root.addWidget(buttons)
    def _save(self):
        if not self.summary.text().strip(): QMessageBox.warning(self,"Report Issue","Enter a short summary."); return
        path,_=QFileDialog.getSaveFileName(self,"Save Issue Report",f"TGPAssure_issue_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json","JSON (*.json)")
        if not path:return
        payload={"created_at":datetime.now(timezone.utc).isoformat(),"category":self.category.currentText(),"summary":self.summary.text().strip(),"details":self.steps.toPlainText().strip(),"expected":self.expected.toPlainText().strip()}
        Path(path).write_text(json.dumps(payload,indent=2),encoding="utf-8"); self.accept()
