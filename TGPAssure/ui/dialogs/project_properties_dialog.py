from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QPlainTextEdit, QVBoxLayout


class ProjectPropertiesDialog(QDialog):
    def __init__(self, project_name: str, project_root: Path, project_file: Path | None = None, parent=None) -> None:
        super().__init__(parent); self.setWindowTitle("Project Properties"); self.setMinimumSize(620, 500)
        root = QVBoxLayout(self); form = QFormLayout()
        project_root = Path(project_root); project_file = Path(project_file) if project_file else next(iter(project_root.glob("*.tgp-project")), None)
        values = {"Name": project_name or project_root.name, "Project folder": str(project_root), "Database": str(project_file or "Not found")}
        file_count = 0; qc_count = 0; schema = "Unknown"
        if project_file and project_file.is_file():
            try:
                conn = sqlite3.connect(str(project_file)); file_count = conn.execute("SELECT COUNT(*) FROM project_files").fetchone()[0]; qc_count = conn.execute("SELECT COUNT(*) FROM qc_runs").fetchone()[0]; row=conn.execute("SELECT schema_version FROM project WHERE id=1").fetchone(); schema=str(row[0]) if row else "Unknown"; conn.close()
            except sqlite3.Error: pass
        values.update({"Registered files": str(file_count), "QC runs": str(qc_count), "Schema version": schema})
        for key, value in values.items():
            label=QLabel(value); label.setTextInteractionFlags(label.textInteractionFlags()); label.setWordWrap(True); form.addRow(key, label)
        root.addLayout(form)
        metadata = QPlainTextEdit(self); metadata.setReadOnly(True); metadata_path=project_root / "project_metadata.json"
        if metadata_path.is_file():
            try: metadata.setPlainText(json.dumps(json.loads(metadata_path.read_text(encoding="utf-8")), indent=2))
            except Exception: metadata.setPlainText(metadata_path.read_text(encoding="utf-8", errors="replace"))
        else: metadata.setPlainText("No additional project metadata has been saved.")
        root.addWidget(metadata, 1)
        buttons=QDialogButtonBox(QDialogButtonBox.Close,self); buttons.rejected.connect(self.reject); buttons.accepted.connect(self.accept); root.addWidget(buttons)
