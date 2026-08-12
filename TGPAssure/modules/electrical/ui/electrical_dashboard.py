from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.data_access.db_engine import DatabaseEngine
from modules.electrical.processing import ElectricalProcessingEngine
from modules.electrical.reader import ElectricalReader
from modules.electrical.ui.prosys_qc_panel import ProsysQcPanel


_QSS = """
QWidget#electricalDashboard {
    background: #F4F6F8;
    color: #1B2733;
    font-size: 8.5pt;
}

QFrame#prosysToolbar {
    background: #FFFFFF;
    border: 0;
    border-bottom: 1px solid #DDE3E9;
}

QLabel#prosysToolbarTitle {
    color: #1B2733;
    font-size: 9.5pt;
    font-weight: 700;
}

QLabel#prosysToolbarStatus {
    color: #64707B;
    font-size: 8pt;
    font-weight: 500;
}

QFrame#prosysToolbarDivider {
    background: #E3E8EC;
    max-width: 1px;
    min-width: 1px;
}

QPushButton#prosysToolButton {
    background: #FFFFFF;
    color: #2B3846;
    border: 1px solid #CBD3DA;
    border-radius: 4px;
    padding: 5px 12px;
    font-weight: 600;
    font-size: 8.5pt;
}
QPushButton#prosysToolButton:hover {
    background: #F0F3F6;
    border-color: #AEB8C0;
}
QPushButton#prosysToolButton:pressed {
    background: #E4E9ED;
}

QPushButton#prosysToolButton[role="process"] {
    background: #1B6FA8;
    color: #FFFFFF;
    border-color: #175E8F;
}
QPushButton#prosysToolButton[role="process"]:hover {
    background: #1F7FC0;
}
QPushButton#prosysToolButton[role="process"]:pressed {
    background: #175E8F;
}

QPushButton#prosysToolButton[role="export"] {
    background: #FFFFFF;
    color: #1B6FA8;
    border-color: #A9C7DC;
}
QPushButton#prosysToolButton[role="export"]:hover {
    background: #EAF3FA;
}
"""


class ElectricalDashboard(QWidget):
    """Electrical module reduced to a Prosys-II style submodule only.

    The previous multi-method Electrical QC dashboard is intentionally removed
    from the visible workspace. This wrapper keeps the MainWindow integration
    stable while exposing only Prosys II data transfer, processing, plots,
    topography and export operations. The heavy banner header has been
    replaced with a slim, professional toolbar strip.
    """

    activity_started = Signal(str, str)
    activity_progress = Signal(int, str)
    activity_finished = Signal()

    def __init__(self, db: DatabaseEngine | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("electricalDashboard")
        self.setStyleSheet(_QSS)
        self.db = db
        self.reader = ElectricalReader()
        self.processing = ElectricalProcessingEngine()
        self.dataset = None
        self.qc_result = None
        self.source_path: Path | None = None
        self.tabs = None  # MainWindow compatibility; Prosys panel owns its internal tabs.
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_toolbar())

        body = QVBoxLayout()
        body.setContentsMargins(8, 8, 8, 8)
        body.setSpacing(6)
        self.prosys_panel = ProsysQcPanel(self, self)
        body.addWidget(self.prosys_panel, 1)

        body_container = QWidget()
        body_container.setLayout(body)
        root.addWidget(body_container, 1)

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("prosysToolbar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        title = QLabel("Prosys II Electrical / IP")
        title.setObjectName("prosysToolbarTitle")
        layout.addWidget(title)

        divider = QFrame()
        divider.setObjectName("prosysToolbarDivider")
        divider.setFrameShape(QFrame.VLine)
        layout.addWidget(divider)

        self.status_label = QLabel("No electrical/IP file loaded")
        self.status_label.setObjectName("prosysToolbarStatus")
        self.status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self.status_label, 1)

        open_btn = QPushButton("Open Data")
        open_btn.setObjectName("prosysToolButton")
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.clicked.connect(self.open_data)
        layout.addWidget(open_btn)

        process_btn = QPushButton("Process")
        process_btn.setObjectName("prosysToolButton")
        process_btn.setProperty("role", "process")
        process_btn.setCursor(Qt.PointingHandCursor)
        process_btn.clicked.connect(self.calculate_fields)
        layout.addWidget(process_btn)

        export_btn = QPushButton("Export TXT")
        export_btn.setObjectName("prosysToolButton")
        export_btn.setProperty("role", "export")
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.clicked.connect(self.export_txt)
        layout.addWidget(export_btn)

        return bar

    # ------------------------------------------------------------------
    # MainWindow / ribbon command compatibility
    # ------------------------------------------------------------------
    def can_execute(self, action_id: str) -> bool:
        if action_id in {"electrical_open", "electrical_open_data", "electrical_prosys"}:
            return True
        if action_id.startswith("electrical_"):
            return self.dataset is not None
        return True

    def show_prosys_workspace(self) -> None:
        self.raise_()
        self.setFocus(Qt.OtherFocusReason)
        self._refresh_all()

    def open_data(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Prosys II Electrical/IP Data",
            str(Path.home()),
            "Electrical/IP Data (*.csv *.txt *.dat *.xyz *.asc *.tsv *.xlsx *.xlsm);;All Files (*.*)",
        )
        if file_path:
            self.open_data_path(file_path)

    def open_data_path(self, file_path: str | Path) -> None:
        path = Path(file_path).expanduser().resolve()
        self.activity_started.emit("Opening Prosys II Data", f"Reading {path.name}")
        try:
            self.activity_progress.emit(25, "Parsing electrical/IP columns")
            dataset = self.reader.read(path)
            self.activity_progress.emit(55, "Calculating derived fields")
            dataset = self.processing.derive_standard_fields(dataset)
            self.dataset = dataset
            self.qc_result = None
            self.source_path = path
            self.status_label.setText(f"Loaded: {path.name}  •  {dataset.record_count:,} rows")
            self.activity_progress.emit(90, "Refreshing Prosys plots and tables")
            self._refresh_all()
        except Exception as exc:
            QMessageBox.critical(self, "Prosys II", f"Unable to open electrical/IP file:\n{exc}")
        finally:
            self.activity_finished.emit()

    def calculate_fields(self) -> None:
        if self.dataset is None:
            QMessageBox.information(self, "Prosys II", "Open an electrical/IP file first.")
            return
        self.dataset = self.processing.derive_standard_fields(self.dataset)
        self.status_label.setText(f"Processed: {self.dataset.record_count:,} rows  •  derived fields refreshed")
        self._refresh_all()

    # Prosys panel actions exposed to ribbon
    def apply_range_filter(self) -> None:
        self.prosys_panel.apply_range_filter()

    def reject_selected_rows(self) -> None:
        self.prosys_panel.reject_selected_rows()

    def apply_median_average(self) -> None:
        self.prosys_panel.apply_median_average()

    def apply_sliding_average(self) -> None:
        self.prosys_panel.apply_sliding_average()

    def import_topography(self) -> None:
        self.prosys_panel.import_topography()

    def apply_elevation_offset(self) -> None:
        self.prosys_panel.apply_elevation_offset()

    def export_txt(self) -> None:
        self.prosys_panel.export_txt()

    def export_csv(self) -> None:
        self.export_txt()

    def export_res2dinv(self) -> None:
        self.prosys_panel.export_res2dinv()

    def export_res3dinv(self) -> None:
        self.prosys_panel.export_res3dinv()

    # Old commands are intentionally routed to Prosys equivalents or disabled messages
    def run_full_qc(self) -> None:
        self.calculate_fields()

    def configure_qc(self) -> None:
        QMessageBox.information(
            self,
            "Prosys II",
            "Electrical QC has been replaced by the Prosys II submodule. "
            "Use the Processing Filters tab for limits and rejection.",
        )

    def show_qc_results(self) -> None:
        self.show_prosys_workspace()

    def set_method(self, *_args: Any) -> None:
        self.show_prosys_workspace()

    def show_native_view(self, *_args: Any) -> None:
        self.show_prosys_workspace()

    def show_geospatial_view(self, *_args: Any) -> None:
        self.show_prosys_workspace()

    def show_pseudosection(self) -> None:
        self.show_prosys_workspace()

    def show_profile(self) -> None:
        self.show_prosys_workspace()

    def generate_report(self, *_args: Any) -> None:
        QMessageBox.information(
            self, "Prosys II", "Use Export TXT / RES2DINV / RES3DINV from the Prosys II workspace."
        )

    def _refresh_all(self) -> None:
        if hasattr(self, "prosys_panel"):
            self.prosys_panel.refresh()