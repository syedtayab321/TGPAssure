from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout,
)


@dataclass(frozen=True)
class ReportConfig:
    output_path: Path
    format: str
    title: str


class ReportDialog(QDialog):
    """Shared, fully-backed report destination/format dialog.

    Only options that all report renderers actually honour are exposed. This
    avoids presenting decorative checkboxes whose values are silently ignored.
    """

    def __init__(
        self,
        parent=None,
        *,
        default_format: str = "pdf",
        default_title: str = "QC Report",
        suggested_path: str | Path | None = None,
        allow_format_change: bool = True,
    ) -> None:
        super().__init__(parent)
        self._report_title = str(default_title or "QC Report")
        self.setWindowTitle("Generate Report")
        self.setMinimumWidth(570)

        root = QVBoxLayout(self)
        description = QLabel(self._report_title, self)
        description.setWordWrap(True)
        root.addWidget(description)

        form = QFormLayout()
        self.format_combo = QComboBox(self)
        self.format_combo.addItems(["PDF", "XLSX"])
        self.format_combo.setCurrentText(default_format.upper())
        self.format_combo.setEnabled(allow_format_change)

        self.path_edit = QLineEdit(str(suggested_path or ""), self)
        browse = QPushButton("Browse…", self)
        browse.clicked.connect(self._browse)
        path_row = QHBoxLayout()
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse)

        form.addRow("Format", self.format_combo)
        form.addRow("Output", path_row)
        root.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.format_combo.currentTextChanged.connect(self._sync_extension)

    def _browse(self) -> None:
        fmt = self.format_combo.currentText().lower()
        suffix = ".pdf" if fmt == "pdf" else ".xlsx"
        filter_text = "PDF (*.pdf)" if fmt == "pdf" else "Excel Workbook (*.xlsx)"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Report", self.path_edit.text() or f"report{suffix}", filter_text
        )
        if path:
            self.path_edit.setText(path)

    def _sync_extension(self) -> None:
        text = self.path_edit.text().strip()
        if not text:
            return
        desired = ".pdf" if self.format_combo.currentText().lower() == "pdf" else ".xlsx"
        self.path_edit.setText(str(Path(text).with_suffix(desired)))

    def _accept(self) -> None:
        path_text = self.path_edit.text().strip()
        if not path_text:
            QMessageBox.warning(self, "Report", "Choose an output file before continuing.")
            return
        path = Path(path_text).expanduser()
        desired = ".pdf" if self.format_combo.currentText().lower() == "pdf" else ".xlsx"
        if path.suffix.lower() != desired:
            path = path.with_suffix(desired)
            self.path_edit.setText(str(path))
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(self, "Report", f"Cannot create output folder:\n{exc}")
            return
        if path.exists():
            answer = QMessageBox.question(
                self, "Replace Report?", f"{path.name} already exists. Replace it?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        self.accept()

    def get_report_config(self) -> ReportConfig:
        return ReportConfig(
            Path(self.path_edit.text()).expanduser().resolve(),
            self.format_combo.currentText().lower(),
            self._report_title,
        )
