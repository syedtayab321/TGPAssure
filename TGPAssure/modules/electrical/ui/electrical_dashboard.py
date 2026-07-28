from __future__ import annotations

import csv
import traceback
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.data_access.db_engine import DatabaseEngine
from core.domain.geospatial import CoordinateTransformError, to_wgs84
from core.domain.spatial_visualization import geographic_to_local_xy
from ui.widgets.geospatial_view import GeoTrack, GoogleGeospatialView
from ui.widgets.scientific_spatial_view import ScientificSpatialView
from modules.electrical.constants import DEFAULT_QC_THRESHOLDS, ElectricalMethod, METHOD_LABELS, SUPPORTED_EXTENSIONS
from modules.electrical.history import save_electrical_qc_run
from modules.electrical.models import ElectricalDataset, ElectricalQcResult
from modules.electrical.processing import ElectricalProcessingEngine
from modules.electrical.qc_engine import ElectricalQcEngine
from modules.electrical.reader import ElectricalReader
from modules.electrical.reporting import ElectricalReportBuilder


_QSS = """
QWidget#electricalDashboard {
    background: #F3F6FA;
    color: #0F2638;
    font-size: 8.5pt;
}
QWidget#electricalDashboard QLabel { background: transparent; }
QFrame#elecTopBand {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #09273D, stop:0.56 #0F4868, stop:1 #126C92);
    border: 0;
    border-radius: 7px;
}
QFrame#elecTopBand QLabel { background: transparent; }
QLabel#elecTitle {
    color: #FFFFFF;
    background: transparent;
    font-size: 13px;
    font-weight: 900;
}
QLabel#elecTopSubtitle {
    color: #C8E5F5;
    background: transparent;
    font-size: 8px;
}
QLabel#elecHeaderLabel {
    color: #D8ECF6;
    background: transparent;
    font-size: 8px;
    font-weight: 800;
}
QLabel#elecBadge {
    background: #E8F7EF;
    color: #0F6C43;
    border: 1px solid #B8DEC9;
    border-radius: 8px;
    padding: 4px 10px;
    font-size: 8px;
    font-weight: 900;
}
QLabel#elecStatusBadge {
    background: rgba(255,255,255,0.14);
    color: #FFFFFF;
    border: 1px solid rgba(255,255,255,0.24);
    border-radius: 8px;
    padding: 4px 10px;
    font-size: 8px;
    font-weight: 800;
}
QFrame#elecSideNav {
    background: #FFFFFF;
    border: 1px solid #D3DFE8;
    border-radius: 7px;
}
QLabel#elecNavTitle {
    color: #587287;
    font-size: 8px;
    font-weight: 900;
    letter-spacing: 0.5px;
    padding: 3px 4px 4px 5px;
}
QPushButton#elecNavButton {
    text-align: left;
    min-height: 28px;
    max-height: 30px;
    padding: 3px 8px;
    border: 1px solid transparent;
    border-radius: 5px;
    background: transparent;
    color: #24465D;
    font-weight: 700;
}
QPushButton#elecNavButton:hover {
    background: #EDF5FB;
    border-color: #D2E6F1;
    color: #0A6EA8;
}
QPushButton#elecNavButton:checked {
    background: #0A6EA8;
    border-color: #075C8C;
    color: #FFFFFF;
}
QFrame#elecCard, QFrame#elecPanel, QFrame#elecControlBand, QFrame#elecQcBanner, QFrame#elecSummaryTile {
    background: #FFFFFF;
    border: 1px solid #D4DEE8;
    border-radius: 7px;
}
QFrame#elecMetricCard {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #FFFFFF, stop:1 #F5F8FB);
    border: 1px solid #D6E2EA;
    border-left: 3px solid #0A86C7;
    border-radius: 7px;
}
QLabel#elecMetricTitle {
    color: #607587;
    font-size: 7.8px;
    font-weight: 900;
    letter-spacing: .4px;
}
QLabel#elecMetricValue {
    color: #0F3149;
    font-size: 15px;
    font-weight: 900;
}
QLabel#elecMetricHint {
    color: #778897;
    font-size: 7.8px;
}
QLabel#elecSectionTitle {
    color: #123047;
    font-size: 10px;
    font-weight: 900;
}
QLabel#elecMicroTitle {
    color: #496171;
    font-size: 8px;
    font-weight: 900;
}
QLabel#elecSubtitle {
    color: #5D7080;
    font-size: 8px;
}
QLabel#elecQcScore {
    color: #0D2B45;
    font-size: 19px;
    font-weight: 900;
}
QLabel#elecPass {
    background: #E7F6EF;
    color: #156B41;
    border: 1px solid #CBEBD9;
    border-radius: 8px;
    padding: 3px 8px;
    font-size: 8px;
    font-weight: 900;
}
QLabel#elecWarn {
    background: #FFF6E3;
    color: #8A5A00;
    border: 1px solid #F1DCAB;
    border-radius: 8px;
    padding: 3px 8px;
    font-size: 8px;
    font-weight: 900;
}
QLabel#elecFail {
    background: #FCEDED;
    color: #A43B3B;
    border: 1px solid #F0C9C9;
    border-radius: 8px;
    padding: 3px 8px;
    font-size: 8px;
    font-weight: 900;
}
QLabel#elecInfo {
    background: #E9F4FB;
    color: #176B93;
    border: 1px solid #C8E4F2;
    border-radius: 8px;
    padding: 3px 8px;
    font-size: 8px;
    font-weight: 900;
}
QTableWidget {
    background: #FFFFFF;
    alternate-background-color: #F7FAFC;
    border: 1px solid #DCE5EC;
    gridline-color: #E7EDF2;
    selection-background-color: #D6EBF7;
    selection-color: #0E2E44;
    font-size: 8.2pt;
}
QHeaderView::section {
    background: #E8F0F6;
    color: #29495E;
    border: 0;
    border-bottom: 1px solid #D3DFE8;
    border-right: 1px solid #E1E8EF;
    padding: 3px 4px;
    font-weight: 900;
    font-size: 8.1pt;
}
QPushButton {
    min-height: 23px;
    max-height: 28px;
    padding: 2px 9px;
    border: 1px solid #B8C7D3;
    border-radius: 5px;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #FFFFFF, stop:1 #EDF3F8);
    color: #102A3D;
}
QPushButton:hover { background:#E7F2FA; border-color:#75AFCF; }
QPushButton#elecPrimaryButton {
    background: #0A82BE;
    color: #FFFFFF;
    border: 1px solid #086A9B;
    font-weight: 900;
}
QPushButton#elecPrimaryButton:hover { background:#0792D8; }
QComboBox {
    min-height: 24px;
    border: 1px solid #BCCBD6;
    border-radius: 5px;
    background: #FFFFFF;
    color: #102A3D;
    padding: 1px 7px;
}
QProgressBar {
    border: 1px solid #CBD8E2;
    border-radius: 6px;
    background: #EEF3F7;
    text-align: center;
    height: 10px;
    font-size: 7.5px;
}
QProgressBar::chunk { border-radius: 5px; background: #0A86C7; }
QSplitter::handle { background: #CCD7E0; }
QSplitter::handle:horizontal { width: 4px; }
QSplitter::handle:vertical { height: 4px; }

QWidget#electricalDashboard QPushButton#elecNavButton {
    text-align: left;
    min-height: 28px;
    max-height: 30px;
    padding: 3px 8px;
    border: 1px solid transparent;
    border-radius: 5px;
    background: transparent;
    color: #24465D;
    font-weight: 700;
}
QWidget#electricalDashboard QPushButton#elecNavButton:hover {
    background: #EDF5FB;
    border-color: #D2E6F1;
    color: #0A6EA8;
}
QWidget#electricalDashboard QPushButton#elecNavButton:checked {
    background: #0A6EA8;
    border-color: #075C8C;
    color: #FFFFFF;
}

"""


class _WorkerSignals(QObject):
    finished = Signal(object)
    error = Signal(str)
    progress = Signal(int, str)


class _Runnable(QRunnable):
    def __init__(self, fn: Callable[..., Any]) -> None:
        super().__init__()
        self.fn = fn
        self.signals = _WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.fn(self.signals.progress.emit)
            self.signals.finished.emit(result)
        except Exception:
            self.signals.error.emit(traceback.format_exc())


class _NoOpTabBar:
    def setExpanding(self, *_args: Any, **_kwargs: Any) -> None:
        return None


class _NavigationStack(QWidget):
    """Compact left navigation used instead of a tall horizontal tab strip."""

    _SHORT_TITLES = {
        "Overview": "Overview",
        "Measurements": "Measurements",
        "QC Results": "QC Results",
        "Pseudosection / Plots": "Plots",
        "2D / 3D Data": "2D / 3D",
        "Satellite / Terrain": "Satellite",
        "Method Guide": "Guide",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._widgets: list[QWidget] = []
        self._buttons: list[QPushButton] = []
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(5)

        self.nav_panel = QFrame(self)
        self.nav_panel.setObjectName("elecSideNav")
        self.nav_panel.setFixedWidth(142)
        nav = QVBoxLayout(self.nav_panel)
        nav.setContentsMargins(5, 6, 5, 6)
        nav.setSpacing(4)
        nav_title = QLabel("ELECTRICAL")
        nav_title.setObjectName("elecNavTitle")
        nav.addWidget(nav_title)
        self._nav_layout = nav

        self.stack = QStackedWidget(self)
        root.addWidget(self.nav_panel)
        root.addWidget(self.stack, 1)
        self.stack.currentChanged.connect(self._sync_buttons)

    def addTab(self, widget: QWidget, title: str) -> int:
        index = self.stack.addWidget(widget)
        self._widgets.append(widget)
        button = QPushButton(self._SHORT_TITLES.get(title, title))
        button.setObjectName("elecNavButton")
        button.setCheckable(True)
        button.setToolTip(title)
        button.clicked.connect(lambda _checked=False, target=widget: self.setCurrentWidget(target))
        self._buttons.append(button)
        self._nav_layout.addWidget(button)
        if index == 0:
            button.setChecked(True)
        return index

    def finalize(self) -> None:
        self._nav_layout.addStretch(1)

    def setCurrentWidget(self, widget: QWidget) -> None:
        self.stack.setCurrentWidget(widget)
        self._sync_buttons(self.stack.currentIndex())

    def currentWidget(self) -> QWidget | None:
        return self.stack.currentWidget()

    def setDocumentMode(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def setUsesScrollButtons(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def setElideMode(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def tabBar(self) -> _NoOpTabBar:
        return _NoOpTabBar()

    def _sync_buttons(self, index: int) -> None:
        for i, button in enumerate(self._buttons):
            button.blockSignals(True)
            button.setChecked(i == index)
            button.blockSignals(False)



class ElectricalDashboard(QWidget):
    activity_started = Signal(str, str)
    activity_progress = Signal(int, str)
    activity_finished = Signal()

    def __init__(self, db_engine: DatabaseEngine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("electricalDashboard")
        self.setProperty("module_id", "electrical")
        self.setStyleSheet(_QSS)
        self.db_engine = db_engine
        self.reader = ElectricalReader()
        self.processing = ElectricalProcessingEngine()
        self.report_builder = ElectricalReportBuilder()
        self.thresholds = dict(DEFAULT_QC_THRESHOLDS)
        self.dataset: ElectricalDataset | None = None
        self.qc_result: ElectricalQcResult | None = None
        self._thread_pool = QThreadPool(self)
        self._active_workers: set[_Runnable] = set()
        self._build_ui()
        self._refresh_all()

    # ------------------------------------------------------------------
    # Public ribbon actions
    # ------------------------------------------------------------------
    def open_data(self) -> None:
        extensions = " ".join(f"*{ext}" for ext in sorted(SUPPORTED_EXTENSIONS))
        path, _ = QFileDialog.getOpenFileName(self, "Open Electrical Survey Data", "", f"Electrical exports ({extensions});;All files (*.*)")
        if path:
            self.open_data_path(path)

    def open_data_path(self, path: str | Path, method: str | ElectricalMethod | None = None) -> None:
        source = str(Path(path).expanduser().resolve())
        selected_method = ElectricalMethod(method) if method is not None and not isinstance(method, ElectricalMethod) else method
        if selected_method is None:
            selected_method = self._selected_method()

        def work(progress):
            progress(10, "Inspecting electrical file and mapping columns")
            inspection = self.reader.inspect(source)
            if not inspection.get("is_electrical_candidate"):
                raise ValueError("The selected table does not contain recognizable electrical measurement fields.")
            progress(35, f"Detected {len(inspection['mapped_fields'])} recognized electrical fields")
            dataset = self.reader.read(source, selected_method)
            progress(70, "Calculating standard resistance, geometry, array and reciprocal diagnostics")
            dataset = self.processing.derive_standard_fields(dataset)
            progress(100, "Electrical dataset ready")
            return dataset

        self._run_background("Opening Electrical Data", "Reading and preparing electrical measurements", work, self._on_dataset_loaded)

    def set_method(self, method: str) -> None:
        target = ElectricalMethod(method)
        for index in range(self.method_combo.count()):
            if self.method_combo.itemData(index) == target.value:
                self.method_combo.setCurrentIndex(index)
                break
        if self.dataset is not None:
            self.dataset.method = target
            self.qc_result = None
            self._refresh_all()

    def run_full_qc(self) -> None:
        if self.dataset is None:
            self.open_data()
            return
        dataset = self.dataset.copy()
        dataset.method = self._selected_method(resolve_auto=True)
        engine = ElectricalQcEngine(self.thresholds)

        def work(progress):
            return engine.run(dataset, progress=progress)

        self._run_background("Running Electrical QC", f"Executing {dataset.method_label} acquisition and method-specific QC", work, self._on_qc_complete)

    def configure_qc(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Electrical QC Thresholds")
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        controls: dict[str, QDoubleSpinBox] = {}
        labels = {
            "contact_resistance_warn_ohm": "Contact resistance warning (Ω)",
            "stack_std_warn_pct": "Stacking deviation warning (%)",
            "reciprocal_warn_pct": "Reciprocal warning (%)",
            "reciprocal_fail_pct": "Reciprocal fail (%)",
            "min_current_ma": "Minimum injected current (mA)",
            "min_abs_voltage_mv": "Minimum |receiver voltage| (mV)",
            "repeat_warn_pct": "Repeat spread warning (%)",
            "outlier_mad_z": "Robust outlier MAD-z threshold",
            "sp_drift_warn_mv": "SP base closure warning (mV)",
            "tdip_extreme_warn_mv_v": "TDIP |chargeability| screening (mV/V)",
            "sip_abs_phase_warn_mrad": "SIP |phase| screening (mrad)",
        }
        for key, label in labels.items():
            box = QDoubleSpinBox(dialog)
            box.setDecimals(4)
            box.setRange(0.0, 1_000_000_000.0)
            box.setValue(float(self.thresholds[key]))
            controls[key] = box
            form.addRow(label, box)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        reset = QPushButton("Reset Defaults")
        cancel = QPushButton("Cancel")
        apply = QPushButton("Apply")
        buttons.addWidget(reset)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(apply)
        layout.addLayout(buttons)
        reset.clicked.connect(lambda: [controls[key].setValue(float(DEFAULT_QC_THRESHOLDS[key])) for key in controls])
        cancel.clicked.connect(dialog.reject)
        apply.clicked.connect(dialog.accept)
        if dialog.exec() == QDialog.Accepted:
            for key, box in controls.items():
                self.thresholds[key] = float(box.value())
            self.qc_result = None
            self.status_label.setText("QC thresholds updated — rerun QC")

    def calculate_fields(self) -> None:
        if not self._require_dataset():
            return
        try:
            self.dataset = self.processing.derive_standard_fields(self.dataset)
            self.qc_result = None
            self._refresh_all()
            self.status_label.setText("Standard electrical fields recalculated")
        except Exception as exc:
            QMessageBox.critical(self, "Electrical Processing", str(exc))

    def apply_sp_drift_correction(self) -> None:
        if not self._require_dataset():
            return
        try:
            self.dataset = self.processing.sp_drift_correct(self.dataset)
            self.qc_result = None
            self._refresh_all()
            self.tabs.setCurrentWidget(self.plot_tab)
            QMessageBox.information(self, "Self-Potential", "Linear base/reference drift correction was applied to a copy of the imported SP values. Original sp_mv is preserved; corrected values are stored in sp_corrected_mv.")
        except Exception as exc:
            QMessageBox.warning(self, "Self-Potential Drift Correction", str(exc))

    def despike_display_series(self) -> None:
        if not self._require_dataset():
            return
        target = self._primary_measurement_name()
        if not target:
            QMessageBox.information(self, "Electrical Processing", "No suitable numeric measurement series is available for despiking.")
            return
        self.dataset.columns[f"{target}_despiked"] = self.processing.despike(self.dataset.numeric(target), self.thresholds["outlier_mad_z"])
        self.dataset.metadata["despiked_display_field"] = f"{target}_despiked"
        self.qc_result = None
        self._refresh_all()
        self.status_label.setText(f"Created auditable despiked series: {target}_despiked (original preserved)")

    def show_pseudosection(self) -> None:
        self.tabs.setCurrentWidget(self.plot_tab)
        self._refresh_plot(force_mode="pseudosection")

    def show_profile(self) -> None:
        self.tabs.setCurrentWidget(self.plot_tab)
        self._refresh_plot(force_mode="profile")

    def show_native_view(self, mode: str = "2d") -> None:
        if not self._require_dataset():
            return
        self.tabs.setCurrentWidget(self.spatial_tab)
        self._refresh_native_spatial()
        self.native_spatial_view.set_mode("3d" if str(mode).lower().startswith("3") else "2d")

    def show_geospatial_view(self, mode: str = "2d") -> None:
        if not self._require_dataset():
            return
        self.tabs.setCurrentWidget(self.geo_tab)
        self._refresh_geospatial()
        self.geospatial_view.set_mode("3d" if str(mode).lower().startswith("3") else "2d")

    def show_qc_results(self) -> None:
        self.tabs.setCurrentWidget(self.qc_tab)

    def export_csv(self) -> None:
        if not self._require_dataset():
            return
        suggested = self.dataset.source_path.with_name(self.dataset.source_path.stem + "_electrical_qc_export.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Export Electrical CSV", str(suggested), "CSV (*.csv)")
        if not path:
            return
        dataset = self.dataset.copy()

        def work(progress):
            progress(15, "Preparing electrical export columns")
            headers, rows = self.processing.export_rows(dataset)
            progress(45, f"Writing {len(rows):,} electrical records")
            with Path(path).open("w", newline="", encoding="utf-8-sig") as stream:
                writer = csv.writer(stream)
                writer.writerow(headers)
                writer.writerows(rows)
            progress(100, "Electrical CSV export complete")
            return Path(path)

        self._run_background("Exporting Electrical Data", "Writing processed/QC-ready tabular data", work,
                             lambda output: QMessageBox.information(self, "Electrical Export", f"Saved:\n{output}"))

    def generate_report(self, fmt: str) -> None:
        if self.qc_result is None:
            QMessageBox.information(self, "Electrical Report", "Run Electrical QC first so the report contains stage results, findings and graphs.")
            return
        suffix = ".pdf" if fmt.lower() == "pdf" else ".xlsx"
        suggested = self.qc_result.dataset.source_path.with_name(self.qc_result.dataset.source_path.stem + f"_electrical_qc{suffix}")
        from ui.dialogs.report_dialog import ReportDialog
        dialog = ReportDialog(
            self, default_format=fmt, default_title="Electrical Geophysics Quality-Control Report",
            suggested_path=suggested, allow_format_change=False,
        )
        if not dialog.exec():
            return
        config = dialog.get_report_config()
        path = str(config.output_path)
        result = self.qc_result

        def work(progress):
            progress(15, "Building electrical QC report model")
            progress(35, "Rendering tables, findings and QC graphs")
            output = self.report_builder.render(result, path, fmt)
            progress(100, "Electrical QC report complete")
            return output

        self._run_background("Generating Electrical QC Report", f"Creating {fmt.upper()} report with QC graphs", work,
                             lambda output: QMessageBox.information(self, "Electrical Report", f"Saved:\n{output}"))

    def can_execute(self, action_id: str) -> bool:
        has_data = self.dataset is not None
        has_result = self.qc_result is not None
        if action_id in {"electrical_open", "electrical_open_data", "electrical_thresholds"} or action_id.startswith("electrical_method_"):
            return True
        if action_id in {"electrical_results", "electrical_report_pdf", "electrical_report_xlsx"}:
            return has_result
        if action_id in {
            "electrical_calculate", "electrical_run_qc", "electrical_sp_drift",
            "electrical_despike", "electrical_pseudosection", "electrical_profile",
            "electrical_view_2d", "electrical_view_3d", "electrical_satellite", "electrical_terrain", "electrical_export_csv",
        }:
            return has_data
        return True

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        top = QFrame(self)
        top.setObjectName("elecTopBand")
        top.setMaximumHeight(68)
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(9, 6, 9, 6)
        top_layout.setSpacing(8)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(0)
        title = QLabel("Electrical Geophysics QC")
        title.setObjectName("elecTitle")
        title.setStyleSheet("background:transparent;color:#FFFFFF;font-size:13px;font-weight:900;")
        subtitle = QLabel("ERT • VES • Profiling • IP • SP • MALM • Telluric")
        subtitle.setObjectName("elecTopSubtitle")
        subtitle.setStyleSheet("background:transparent;color:#C8E5F5;font-size:8px;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        top_layout.addLayout(title_box, 1)

        method_label = QLabel("METHOD")
        method_label.setObjectName("elecHeaderLabel")
        method_label.setStyleSheet("background:transparent;color:#D8ECF6;font-size:8px;font-weight:800;")
        top_layout.addWidget(method_label)
        self.method_combo = QComboBox()
        for method, label in METHOD_LABELS.items():
            self.method_combo.addItem(label, method.value)
        self.method_combo.setMinimumWidth(255)
        self.method_combo.setMaximumWidth(380)
        self.method_combo.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.method_combo.currentIndexChanged.connect(self._method_changed)
        top_layout.addWidget(self.method_combo, 0)

        open_button = QPushButton("Open")
        open_button.clicked.connect(self.open_data)
        qc_button = QPushButton("Run QC")
        qc_button.setObjectName("elecPrimaryButton")
        qc_button.clicked.connect(self.run_full_qc)
        thresholds_button = QPushButton("Thresholds")
        thresholds_button.clicked.connect(self.configure_qc)
        for button in (open_button, qc_button, thresholds_button):
            button.setMaximumHeight(26)
            top_layout.addWidget(button)

        self.dataset_badge = QLabel("NO DATA")
        self.dataset_badge.setObjectName("elecBadge")
        self.dataset_badge.setMinimumWidth(118)
        self.dataset_badge.setMaximumWidth(260)
        self.dataset_badge.setAlignment(Qt.AlignCenter)
        top_layout.addWidget(self.dataset_badge)

        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("elecStatusBadge")
        self.status_label.setMinimumWidth(130)
        self.status_label.setMaximumWidth(280)
        self.status_label.setAlignment(Qt.AlignCenter)
        top_layout.addWidget(self.status_label)
        root.addWidget(top)

        self.tabs = _NavigationStack(self)
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setElideMode(Qt.ElideRight)
        try:
            self.tabs.tabBar().setExpanding(False)
        except Exception:
            pass
        self.overview_tab = QWidget()
        self.data_tab = QWidget()
        self.qc_tab = QWidget()
        self.plot_tab = QWidget()
        self.spatial_tab = QWidget()
        self.geo_tab = QWidget()
        self.guide_tab = QWidget()
        self.tabs.addTab(self.overview_tab, "Overview")
        self.tabs.addTab(self.data_tab, "Measurements")
        self.tabs.addTab(self.qc_tab, "QC Results")
        self.tabs.addTab(self.plot_tab, "Pseudosection / Plots")
        self.tabs.addTab(self.spatial_tab, "2D / 3D Data")
        self.tabs.addTab(self.geo_tab, "Satellite / Terrain")
        self.tabs.addTab(self.guide_tab, "Method Guide")
        self.tabs.finalize()
        root.addWidget(self.tabs, 1)

        self._build_overview_tab()
        self._build_data_tab()
        self._build_qc_tab()
        self._build_plot_tab()
        self._build_native_spatial_tab()
        self._build_geospatial_tab()
        self._build_guide_tab()

    def _metric_card(self, title: str, value: str, hint: str):
        frame = QFrame(self)
        frame.setObjectName("elecMetricCard")
        frame.setMinimumHeight(46)
        frame.setMaximumHeight(58)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(1)
        title_label = QLabel(title)
        title_label.setObjectName("elecMetricTitle")
        value_label = QLabel(value)
        value_label.setObjectName("elecMetricValue")
        hint_label = QLabel(hint)
        hint_label.setObjectName("elecMetricHint")
        hint_label.setWordWrap(False)
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addWidget(hint_label)
        return frame, value_label, hint_label

    def _build_overview_tab(self) -> None:
        layout = QVBoxLayout(self.overview_tab)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(7)
        self.metric_records = self._metric_card("RECORDS", "0", "Imported measurements")
        self.metric_method = self._metric_card("METHOD", "—", "Selected workflow")
        self.metric_score = self._metric_card("QC SCORE", "—", "Run full QC")
        self.metric_findings = self._metric_card("FINDINGS", "0", "Automated issues")
        for card in (self.metric_records[0], self.metric_method[0], self.metric_score[0], self.metric_findings[0]):
            kpi_row.addWidget(card, 1)
        layout.addLayout(kpi_row)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        left = QFrame()
        left.setObjectName("elecPanel")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(10, 8, 10, 10)
        title = QLabel("Dataset & Acquisition Summary")
        title.setObjectName("elecSectionTitle")
        left_layout.addWidget(title)
        self.overview_table = self._new_table(["Parameter", "Value"])
        left_layout.addWidget(self.overview_table, 1)

        right = QFrame()
        right.setObjectName("elecPanel")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(10, 8, 10, 10)
        title2 = QLabel("Workflow & Inversion Readiness")
        title2.setObjectName("elecSectionTitle")
        right_layout.addWidget(title2)
        self.workflow_table = self._new_table(["Step", "Status", "Purpose"])
        right_layout.addWidget(self.workflow_table, 1)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([520, 720])
        layout.addWidget(splitter, 1)

    def _build_data_tab(self) -> None:
        layout = QVBoxLayout(self.data_tab)
        layout.setContentsMargins(5, 5, 5, 5)
        self.data_table = self._new_table([])
        layout.addWidget(self.data_table)

    def _build_qc_tab(self) -> None:
        layout = QVBoxLayout(self.qc_tab)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        banner = QFrame()
        banner.setObjectName("elecQcBanner")
        banner.setMaximumHeight(76)
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(9, 6, 9, 6)
        banner_layout.setSpacing(8)

        score_tile = QFrame()
        score_tile.setObjectName("elecSummaryTile")
        score_tile.setMaximumHeight(58)
        score_box = QVBoxLayout(score_tile)
        score_box.setContentsMargins(8, 4, 8, 4)
        score_box.setSpacing(1)
        score_title = QLabel("OVERALL SCORE")
        score_title.setObjectName("elecMetricTitle")
        self.qc_score_label = QLabel("—")
        self.qc_score_label.setObjectName("elecQcScore")
        self.qc_score_bar = QProgressBar()
        self.qc_score_bar.setRange(0, 100)
        self.qc_score_bar.setValue(0)
        self.qc_score_bar.setTextVisible(False)
        score_box.addWidget(score_title)
        score_box.addWidget(self.qc_score_label)
        score_box.addWidget(self.qc_score_bar)
        banner_layout.addWidget(score_tile, 0)

        status_tile = QFrame()
        status_tile.setObjectName("elecSummaryTile")
        status_tile.setMaximumHeight(58)
        status_box = QVBoxLayout(status_tile)
        status_box.setContentsMargins(8, 4, 8, 4)
        status_box.setSpacing(2)
        status_title = QLabel("STATUS")
        status_title.setObjectName("elecMetricTitle")
        self.qc_status_badge = QLabel("NOT RUN")
        self.qc_status_badge.setObjectName("elecInfo")
        self.qc_status_badge.setAlignment(Qt.AlignCenter)
        self.qc_status_badge.setMaximumHeight(23)
        self.qc_result_hint = QLabel("Run QC to produce stage scorecard and recommended actions.")
        self.qc_result_hint.setObjectName("elecSubtitle")
        self.qc_result_hint.setWordWrap(False)
        status_box.addWidget(status_title)
        status_box.addWidget(self.qc_status_badge)
        status_box.addWidget(self.qc_result_hint)
        banner_layout.addWidget(status_tile, 1)

        severity_tile = QFrame()
        severity_tile.setObjectName("elecSummaryTile")
        severity_tile.setMaximumHeight(58)
        severity_layout = QHBoxLayout(severity_tile)
        severity_layout.setContentsMargins(8, 5, 8, 5)
        severity_layout.setSpacing(5)
        self.qc_error_badge = QLabel("ERROR 0")
        self.qc_error_badge.setObjectName("elecFail")
        self.qc_warning_badge = QLabel("WARNING 0")
        self.qc_warning_badge.setObjectName("elecWarn")
        self.qc_info_badge = QLabel("INFO 0")
        self.qc_info_badge.setObjectName("elecInfo")
        for label in (self.qc_error_badge, self.qc_warning_badge, self.qc_info_badge):
            label.setAlignment(Qt.AlignCenter)
            label.setMinimumWidth(82)
            label.setMaximumHeight(28)
            severity_layout.addWidget(label)
        banner_layout.addWidget(severity_tile, 0)
        layout.addWidget(banner)

        # Keep each QC product on its own page.  The previous vertical splitter
        # squeezed both tables into the same viewport and made long findings hard
        # to review on normal laptop displays.
        self.qc_result_tabs = QTabWidget(self.qc_tab)
        self.qc_result_tabs.setDocumentMode(True)
        self.qc_result_tabs.setUsesScrollButtons(True)

        scorecard_page = QWidget()
        scorecard_layout = QVBoxLayout(scorecard_page)
        scorecard_layout.setContentsMargins(4, 4, 4, 4)
        self.stage_table = self._new_table(["Stage", "Status", "Score", "Findings", "Key metrics", "Summary"])
        self.stage_table.setMinimumHeight(320)
        scorecard_layout.addWidget(self.stage_table, 1)
        self.qc_result_tabs.addTab(scorecard_page, "Stage Scorecard")

        findings_page = QWidget()
        findings_layout = QVBoxLayout(findings_page)
        findings_layout.setContentsMargins(4, 4, 4, 4)
        self.finding_table = self._new_table(["Severity", "Stage", "Code", "Finding", "Observed", "Recommended action"])
        self.finding_table.setMinimumHeight(320)
        findings_layout.addWidget(self.finding_table, 1)
        self.qc_result_tabs.addTab(findings_page, "Findings & Actions")

        charts_page = QWidget()
        charts_layout = QVBoxLayout(charts_page)
        charts_layout.setContentsMargins(4, 4, 4, 4)
        charts_layout.setSpacing(5)
        chart_tabs = QTabWidget(charts_page)
        chart_tabs.setDocumentMode(True)

        self.qc_stage_plot = pg.PlotWidget(background="w")
        self.qc_stage_plot.showGrid(x=False, y=True, alpha=0.18)
        self.qc_stage_plot.setLabel("left", "QC score (%)")
        self.qc_stage_plot.setYRange(0, 105, padding=0)
        chart_tabs.addTab(self.qc_stage_plot, "Stage Scores")

        self.qc_severity_plot = pg.PlotWidget(background="w")
        self.qc_severity_plot.showGrid(x=False, y=True, alpha=0.18)
        self.qc_severity_plot.setLabel("left", "Finding count")
        chart_tabs.addTab(self.qc_severity_plot, "Finding Severity")

        self.qc_finding_stage_plot = pg.PlotWidget(background="w")
        self.qc_finding_stage_plot.showGrid(x=False, y=True, alpha=0.18)
        self.qc_finding_stage_plot.setLabel("left", "Findings")
        chart_tabs.addTab(self.qc_finding_stage_plot, "Findings by Stage")

        charts_layout.addWidget(chart_tabs, 1)
        self.qc_result_tabs.addTab(charts_page, "QC Charts")
        layout.addWidget(self.qc_result_tabs, 1)

    def _build_plot_tab(self) -> None:
        layout = QVBoxLayout(self.plot_tab)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)
        toolbar_frame = QFrame()
        toolbar_frame.setObjectName("elecPanel")
        toolbar = QHBoxLayout(toolbar_frame)
        toolbar.setContentsMargins(8, 4, 8, 4)
        toolbar.setSpacing(6)
        label = QLabel("Display:")
        label.setObjectName("elecMicroTitle")
        toolbar.addWidget(label)
        self.plot_mode = QComboBox()
        self.plot_mode.addItem("Auto for Method", "auto")
        self.plot_mode.addItem("Apparent Pseudosection", "pseudosection")
        self.plot_mode.addItem("Profile / Curve", "profile")
        self.plot_mode.addItem("QC Distribution", "qc")
        self.plot_mode.setMaximumWidth(220)
        self.plot_mode.currentIndexChanged.connect(lambda *_: self._refresh_plot())
        toolbar.addWidget(self.plot_mode)
        toolbar.addStretch(1)
        self.plot_note = QLabel("Apparent-data display for QC; inversion-ready export still needs error model/topography review.")
        self.plot_note.setObjectName("elecSubtitle")
        self.plot_note.setWordWrap(False)
        toolbar.addWidget(self.plot_note, 1)
        layout.addWidget(toolbar_frame)
        self.plot_widget = pg.PlotWidget(background="w")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.18)
        try:
            self.plot_widget.getPlotItem().layout.setContentsMargins(8, 8, 8, 8)
        except Exception:
            pass
        layout.addWidget(self.plot_widget, 1)

    def _build_native_spatial_tab(self) -> None:
        layout = QVBoxLayout(self.spatial_tab)
        layout.setContentsMargins(6, 6, 6, 6)
        self.native_spatial_view = ScientificSpatialView(self.spatial_tab, title="Electrical Native 2D / 3D")
        layout.addWidget(self.native_spatial_view, 1)

    def _build_geospatial_tab(self) -> None:
        layout = QVBoxLayout(self.geo_tab)
        layout.setContentsMargins(6, 6, 6, 6)
        self.geospatial_view = GoogleGeospatialView(self.geo_tab, title="Electrical Survey — Satellite & 3D Terrain")
        layout.addWidget(self.geospatial_view, 1)

    def _build_guide_tab(self) -> None:
        layout = QVBoxLayout(self.guide_tab)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        guide = [
            ("Electrical Resistivity Tomography (ERT)", "Multi-electrode DC apparent-resistivity acquisition for 2D/3D imaging. QC priority: geometry, contact resistance, signal/stacking, reciprocal error, outliers, topography and inversion error model."),
            ("Vertical Electrical Sounding (VES)", "Expanding electrode spacing to investigate vertical resistivity variation, commonly Schlumberger/Wenner style. QC priority: AB/2 and MN/2 geometry, overlap checks, stacking/noise, curve continuity and repeat readings."),
            ("DC Resistivity Profiling", "Fixed/controlled array moved along a traverse to emphasize lateral changes. QC priority: station spacing, geometry consistency, current/voltage, contact, repeats and cultural noise."),
            ("Time-Domain IP (TDIP)", "Measures post-current shutoff voltage decay/chargeability. QC adds chargeability sign/range, decay-window shape, timing, SP cancellation, coupling and repeatability."),
            ("Frequency-Domain IP (FDIP)", "Measures frequency-dependent amplitude/phase response at selected frequencies. QC adds frequency validity, phase convention, repeatability and coupling checks."),
            ("Spectral IP / Complex Resistivity (SIP)", "Extends FDIP over multiple frequencies to characterize dispersion. QC emphasizes spectral coverage, phase/magnitude coherence, frequency metadata, repeats and instrument synchronization."),
            ("Self-Potential (SP)", "Passive natural voltage mapping with non-polarizing electrodes. QC emphasizes stable base/reference electrode, drift/closure, repeats, electrode polarization, wire/contact integrity and cultural/temporal noise."),
            ("Mise-à-la-Masse (MALM)", "Energizes a conductive body/source and maps surface potential distribution. QC emphasizes stable source/return geometry, source IDs, reference consistency, coordinates, repeats and leakage/cultural effects."),
            ("Equipotential / Potential Mapping", "Maps electric potential at surface stations, commonly around an injected-current source. QC emphasizes coordinate integrity, stable reference/source conditions, repeated control points, potential continuity and cultural leakage/noise."),
            ("Telluric Electric-Field Method", "Measures naturally varying electric fields/potential differences through time. QC emphasizes timestamps, synchronized/reference channels or stations, electrode stability, temporal drift/noise and repeat/reference consistency."),
        ]
        for heading, text in guide:
            frame = QFrame()
            frame.setObjectName("elecPanel")
            box = QVBoxLayout(frame)
            h = QLabel(heading)
            h.setObjectName("elecSectionTitle")
            body = QLabel(text)
            body.setWordWrap(True)
            body.setObjectName("elecSubtitle")
            box.addWidget(h)
            box.addWidget(body)
            content_layout.addWidget(frame)
        note = QLabel("Scope note: MT, CSAMT, VLF, FDEM and TDEM are electromagnetic methods and belong in the EM module. This Electrical suite focuses on galvanic/potential and passive electric-field workflows and their acquisition QC.")
        note.setWordWrap(True)
        note.setObjectName("elecSubtitle")
        content_layout.addWidget(note)
        content_layout.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll)

    def _new_table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        if headers:
            table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(22)
        table.setWordWrap(False)
        table.setShowGrid(True)
        table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        table.horizontalHeader().setMinimumSectionSize(48)
        font = table.font()
        font.setPointSizeF(8.2)
        table.setFont(font)
        return table

    def _refresh_all(self) -> None:
        self._refresh_metrics()
        self._refresh_overview()
        self._refresh_data_table()
        self._refresh_qc_tables()
        self._refresh_plot()
        self._refresh_native_spatial()
        self._refresh_geospatial()

    @staticmethod
    def _finite_span(values: np.ndarray) -> float:
        finite = values[np.isfinite(values)]
        if finite.size < 2:
            return 0.0
        return float(np.nanmax(finite) - np.nanmin(finite))

    def _line_axis(self, dataset) -> np.ndarray:
        """Return a compact numeric Y/line axis for electrical 2D/3D previews."""
        n = dataset.record_count
        if dataset.has("line_id"):
            labels = dataset.text("line_id")
            mapping = {name: idx for idx, name in enumerate(dict.fromkeys(str(v) for v in labels))}
            return np.asarray([float(mapping.get(str(v), 0)) for v in labels], dtype=float)
        if dataset.has("line"):
            raw = dataset.numeric("line")
            if self._finite_span(raw) > 0:
                unique = {value: idx for idx, value in enumerate(sorted(set(float(v) for v in raw[np.isfinite(raw)])))}
                return np.asarray([float(unique.get(float(v), 0.0)) if np.isfinite(v) else 0.0 for v in raw], dtype=float)
        return np.zeros(n, dtype=float)

    def _refresh_native_spatial(self) -> None:
        if not hasattr(self, "native_spatial_view"):
            return
        dataset = self.dataset
        if dataset is None or dataset.record_count == 0:
            self.native_spatial_view.clear("Load electrical data to enable the native 2D/3D view.")
            return
        value_name = self._primary_measurement_name()
        if not value_name or not dataset.has(value_name):
            self.native_spatial_view.clear("No plottable electrical measurement field is available.")
            return
        values = dataset.numeric(value_name)
        depth = dataset.numeric("pseudo_depth") if dataset.has("pseudo_depth") else np.zeros(dataset.record_count)
        elevation = dataset.numeric("elevation") if dataset.has("elevation") else np.zeros(dataset.record_count)

        # Electrical 3D should not be driven by repeated GPS site coordinates when
        # an ERT/IP pseudosection geometry is available. ABMN-derived pseudo_x and
        # pseudo_depth give a much better native 2D/3D QC view for ERT/TDIP/FDIP/SIP.
        has_pseudo = dataset.has("pseudo_x") and dataset.has("pseudo_depth")
        pseudo_x = dataset.numeric("pseudo_x") if dataset.has("pseudo_x") else np.arange(dataset.record_count, dtype=float)
        pseudo_depth = depth
        pseudo_x_span = self._finite_span(pseudo_x)
        pseudo_depth_span = self._finite_span(pseudo_depth)
        method_name = str(getattr(dataset.method, "value", dataset.method)).lower()
        prefers_pseudosection = any(key in method_name for key in ("ert", "dip", "ip", "resistivity"))

        if has_pseudo and (prefers_pseudosection or pseudo_x_span > 0 or pseudo_depth_span > 0):
            x = pseudo_x
            y = self._line_axis(dataset)
            if np.any(np.isfinite(elevation)) and self._finite_span(elevation) > 0:
                z = elevation - np.where(np.isfinite(pseudo_depth), pseudo_depth, 0.0)
                z_text = "elevation minus electrical pseudodepth"
            else:
                z = -np.where(np.isfinite(pseudo_depth), pseudo_depth, 0.0)
                z_text = "negative electrical pseudodepth"
            coordinate_label = f"Electrical pseudosection / 3D array coordinates; Z = {z_text}"
            allow_surface = bool(self._finite_span(y) > 0 and pseudo_x_span > 0 and pseudo_depth_span > 0)
        elif dataset.has("easting") and dataset.has("northing"):
            x = dataset.numeric("easting")
            y = dataset.numeric("northing")
            z = elevation - np.where(np.isfinite(depth), depth, 0.0)
            coordinate_label = str(dataset.metadata.get("crs") or dataset.metadata.get("coordinate_system") or "Projected survey coordinates")
            allow_surface = True
        elif dataset.has("longitude") and dataset.has("latitude"):
            x, y, lon0, lat0 = geographic_to_local_xy(dataset.numeric("longitude"), dataset.numeric("latitude"))
            z = elevation - np.where(np.isfinite(depth), depth, 0.0)
            coordinate_label = f"Local metric display about {lat0:.6f}°, {lon0:.6f}° (source WGS84)"
            allow_surface = True
        else:
            x = pseudo_x if dataset.has("pseudo_x") else np.arange(dataset.record_count, dtype=float)
            y = self._line_axis(dataset)
            z = -np.where(np.isfinite(depth), depth, 0.0)
            coordinate_label = "Profile/pseudosection coordinates; Z is negative pseudodepth, not inversion depth"
            allow_surface = bool(self._finite_span(y) > 0)

        self.native_spatial_view.set_data(
            x, y, values, z=z,
            title=dataset.method_label,
            value_label=value_name.replace("_", " "),
            value_units="ohm·m" if "resistivity" in value_name else ("mV/V" if "chargeability" in value_name else ""),
            coordinate_label=coordinate_label,
            allow_surface=allow_surface,
        )

    def _refresh_geospatial(self) -> None:
        if not hasattr(self, "geospatial_view"):
            return
        dataset = self.dataset
        if dataset is None or dataset.record_count == 0:
            self.geospatial_view.clear_tracks()
            return

        lon = dataset.numeric("longitude") if dataset.has("longitude") else None
        lat = dataset.numeric("latitude") if dataset.has("latitude") else None
        if lon is None and dataset.has("lon"):
            lon = dataset.numeric("lon")
        if lat is None and dataset.has("lat"):
            lat = dataset.numeric("lat")
        altitude = dataset.numeric("elevation") if dataset.has("elevation") else None
        crs = dataset.metadata.get("crs") or dataset.metadata.get("epsg") or dataset.metadata.get("coordinate_system")

        try:
            if lon is not None and lat is not None:
                coords = to_wgs84(lon, lat, crs="EPSG:4326", altitude_m=altitude, allow_lonlat_inference=True)
            elif dataset.has("easting") and dataset.has("northing"):
                coords = to_wgs84(
                    dataset.numeric("easting"), dataset.numeric("northing"), crs=crs,
                    altitude_m=altitude, allow_lonlat_inference=True,
                )
            else:
                self.geospatial_view.clear_tracks()
                self.geospatial_view.set_status_message("Satellite/3D view requires longitude/latitude or easting/northing coordinates.")
                return
        except CoordinateTransformError as exc:
            self.geospatial_view.clear_tracks()
            self.geospatial_view.set_status_message(str(exc))
            return

        valid = coords.valid_mask
        if not np.any(valid):
            self.geospatial_view.clear_tracks()
            self.geospatial_view.set_status_message("No valid geographic coordinates are available for satellite/3D display.")
            return
        tracks: list[GeoTrack] = []
        if dataset.has("line_id"):
            lines = dataset.text("line_id")
            for name in dict.fromkeys(str(v).strip() for v in lines if str(v).strip()):
                idx = np.flatnonzero((lines.astype(str) == name) & valid)
                if idx.size:
                    tracks.append(GeoTrack(name, coords.longitude[idx], coords.latitude[idx], coords.altitude_m[idx]))
        if not tracks:
            idx = np.flatnonzero(valid)
            tracks.append(GeoTrack(dataset.method_label, coords.longitude[idx], coords.latitude[idx], coords.altitude_m[idx]))
        self.geospatial_view.set_tracks(tracks, render=self.tabs.currentWidget() is self.geo_tab)

    def _refresh_metrics(self) -> None:
        dataset = self.dataset
        result = self.qc_result
        self.metric_records[1].setText(f"{dataset.record_count:,}" if dataset else "0")
        self.metric_method[1].setText(dataset.method.value.upper() if dataset else "—")
        self.metric_score[1].setText(f"{result.score:.1f}" if result else "—")
        self.metric_findings[1].setText(str(len(result.findings)) if result else "0")
        self.dataset_badge.setText(dataset.source_path.name if dataset else "NO DATASET")
        self.dataset_badge.setToolTip(str(dataset.source_path) if dataset else "")

        if hasattr(self, "qc_score_label"):
            if result is None:
                self.qc_score_label.setText("—")
                self.qc_score_bar.setValue(0)
                self.qc_status_badge.setText("NOT RUN")
                _set_badge_kind(self.qc_status_badge, "info")
                self.qc_error_badge.setText("ERROR 0")
                self.qc_warning_badge.setText("WARNING 0")
                self.qc_info_badge.setText("INFO 0")
                self.qc_result_hint.setText("Run Full QC to produce stage scores, severity counts and recommended actions.")
            else:
                summary = result.summary()
                severity = {str(k).lower(): int(v) for k, v in summary.get("severity_counts", {}).items()}
                score = max(0, min(100, int(round(result.score))))
                self.qc_score_label.setText(f"{result.score:.1f}/100")
                self.qc_score_bar.setValue(score)
                self.qc_status_badge.setText(result.status.upper())
                _set_badge_kind(self.qc_status_badge, "pass" if result.status.lower() in {"pass", "passed", "ok"} else ("fail" if result.status.lower() in {"fail", "failed", "error"} else "warn"))
                self.qc_error_badge.setText(f"ERROR {severity.get('error', 0)}")
                self.qc_warning_badge.setText(f"WARNING {severity.get('warning', 0)}")
                self.qc_info_badge.setText(f"INFO {severity.get('info', 0)}")
                self.qc_result_hint.setText(
                    f"{len(result.stages)} stages • {result.duration_ms:,} ms • {result.profile_name}. "
                    "Resolve severe findings before export."
                )

    def _refresh_overview(self) -> None:
        rows: list[tuple[str, Any]] = []
        if self.dataset:
            summary = self.dataset.summary()
            keys = [
                "source_file", "method_label", "record_count", "source_format", "line_count",
                "apparent_resistivity_ohm_m_median", "apparent_resistivity_ohm_m_min", "apparent_resistivity_ohm_m_max",
                "chargeability_mv_v_median", "sp_mv_median", "frequency_hz_min", "frequency_hz_max",
                "reciprocal_pair_count",
            ]
            rows = [(key.replace("_", " ").title(), summary[key]) for key in keys if key in summary]
            fields = sorted(self.dataset.columns)
            preview = ", ".join(fields[:14]) + (f" … +{len(fields) - 14} more" if len(fields) > 14 else "")
            rows.append(("Recognized Fields", f"{len(fields)} fields: {preview}"))
            if self.dataset.has("longitude") and self.dataset.has("latitude"):
                rows.append(("Spatial Context", "WGS84 geographic coordinates available for satellite/terrain display"))
            elif self.dataset.has("easting") and self.dataset.has("northing"):
                rows.append(("Spatial Context", "Projected coordinates available; CRS must be correct for satellite display"))
            else:
                rows.append(("Spatial Context", "No geographic coordinates; native 2D/3D uses profile/pseudo coordinates"))
        self._fill_table(self.overview_table, rows)

        workflow = [
            ("1. Import", "READY" if self.dataset else "WAITING", "Load field/controller export and map recognized electrical columns."),
            ("2. Geometry / derive", "READY" if self.dataset else "WAITING", "Calculate resistance, geometric factor, apparent resistivity and pseudo coordinates where possible."),
            ("3. Acquisition QC", "DONE" if self.qc_result else "PENDING", "Check signal, contact resistance, stacking noise, repeats and reciprocal error."),
            ("4. Method QC", "DONE" if self.qc_result else "PENDING", "Apply ERT/VES/IP/SIP/SP/MALM/equipotential/telluric-specific screening."),
            ("5. Review plots", "DONE" if self.qc_result else "PENDING", "Inspect pseudosection/profile/QC distributions and field context."),
            ("6. Inversion export", "READY" if self.dataset else "WAITING", "Export auditable data; inversion still needs explicit error model/topography/sensitivity review."),
            ("7. Report / history", "DONE" if self.qc_result else "PENDING", "Generate PDF/XLSX report and save QC run to centralized project history."),
        ]
        self.workflow_table.setRowCount(len(workflow))
        self.workflow_table.setColumnCount(3)
        self.workflow_table.setHorizontalHeaderLabels(["Step", "Status", "Purpose"])
        for row_index, row in enumerate(workflow):
            for column, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                if column == 1:
                    _apply_status_style(item, str(value))
                self.workflow_table.setItem(row_index, column, item)
        self.workflow_table.setColumnWidth(0, 165)
        self.workflow_table.setColumnWidth(1, 84)
        self.workflow_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)

    def _refresh_data_table(self) -> None:
        table = self.data_table
        table.clear()
        if self.dataset is None:
            table.setRowCount(0)
            table.setColumnCount(0)
            return
        preferred = [
            "line_id", "station", "a", "b", "m", "n", "ab2_m", "mn2_m", "current_ma", "voltage_mv",
            "apparent_resistivity_ohm_m", "chargeability_mv_v", "sp_mv", "frequency_hz", "phase_mrad",
            "contact_resistance_ohm", "stack_std_pct", "reciprocal_error_pct",
        ]
        headers = [name for name in preferred if self.dataset.has(name)]
        headers.extend(name for name in sorted(self.dataset.columns) if name not in headers)
        headers = headers[:20]
        count = min(self.dataset.record_count, 500)
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels([name.replace("_", " ").title() for name in headers])
        table.setRowCount(count)
        for row in range(count):
            for column, name in enumerate(headers):
                value = self.dataset.columns[name][row]
                text = _display(value)
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                table.setItem(row, column, item)
        for column in range(len(headers)):
            table.setColumnWidth(column, 105)
        if headers:
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.status_label.setText(f"Showing {count:,} of {self.dataset.record_count:,} records")

    def _refresh_qc_tables(self) -> None:
        self.stage_table.clearSpans()
        self.finding_table.clearSpans()
        self.stage_table.setRowCount(0)
        self.finding_table.setRowCount(0)
        if self.qc_result is None:
            self.stage_table.setRowCount(1)
            placeholder = QTableWidgetItem("Run Full QC to populate stage scorecard and method-specific checks.")
            placeholder.setForeground(QColor("#607587"))
            self.stage_table.setItem(0, 0, placeholder)
            self.stage_table.setSpan(0, 0, 1, max(1, self.stage_table.columnCount()))
            self._refresh_qc_charts()
            return
        result = self.qc_result
        self.stage_table.setRowCount(len(result.stages))
        for row, stage in enumerate(result.stages):
            values = [
                stage.stage_name,
                stage.status.upper(),
                f"{stage.score:.1f}",
                len(stage.findings),
                _metrics_preview(stage.metrics),
                stage.message,
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                if col == 1:
                    _apply_status_style(item, str(value))
                elif col == 2:
                    _apply_score_style(item, stage.score)
                self.stage_table.setItem(row, col, item)
        self.stage_table.setColumnWidth(0, 190)
        self.stage_table.setColumnWidth(1, 70)
        self.stage_table.setColumnWidth(2, 62)
        self.stage_table.setColumnWidth(3, 62)
        self.stage_table.setColumnWidth(4, 260)
        self.stage_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)

        findings = result.findings
        if not findings:
            self.finding_table.setRowCount(1)
            ok = QTableWidgetItem("No automated QC findings. Still review the field context, electrode layout, topography and inversion error model before final interpretation.")
            ok.setForeground(QColor("#166A42"))
            self.finding_table.setItem(0, 0, ok)
            self.finding_table.setSpan(0, 0, 1, max(1, self.finding_table.columnCount()))
        else:
            self.finding_table.setRowCount(len(findings))
            for row, finding in enumerate(findings):
                observed = _finding_observed(finding)
                finding_text = f"{finding.title}: {finding.message}" if finding.title else finding.message
                values = [finding.severity.upper(), finding.stage_key, finding.code, finding_text, observed, finding.suggested_action]
                for col, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    item.setToolTip(str(value))
                    if col == 0:
                        _apply_severity_style(item, str(finding.severity))
                    self.finding_table.setItem(row, col, item)
        self.finding_table.setColumnWidth(0, 72)
        self.finding_table.setColumnWidth(1, 86)
        self.finding_table.setColumnWidth(2, 132)
        self.finding_table.setColumnWidth(3, 390)
        self.finding_table.setColumnWidth(4, 100)
        self.finding_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self._refresh_qc_charts()

    def _refresh_qc_charts(self) -> None:
        """Render compact QC graphics without hiding the underlying tabular evidence."""
        for name in ("qc_stage_plot", "qc_severity_plot", "qc_finding_stage_plot"):
            plot = getattr(self, name, None)
            if plot is not None:
                plot.clear()
        result = self.qc_result
        if result is None:
            for plot in (self.qc_stage_plot, self.qc_severity_plot, self.qc_finding_stage_plot):
                plot.setTitle("Run Full QC to populate this chart")
            return

        stages = list(result.stages)
        x = np.arange(len(stages), dtype=float)
        scores = np.asarray([float(stage.score) for stage in stages], dtype=float)
        brushes = []
        for stage in stages:
            status = str(stage.status).lower()
            if status in {"fail", "failed", "error"}:
                brushes.append(pg.mkBrush("#D9534F"))
            elif status in {"warning", "warn", "review"}:
                brushes.append(pg.mkBrush("#E5A11B"))
            else:
                brushes.append(pg.mkBrush("#2E9B63"))
        if stages:
            self.qc_stage_plot.addItem(pg.BarGraphItem(x=x, height=scores, width=0.68, brushes=brushes, pen=pg.mkPen("#FFFFFF")))
            self.qc_stage_plot.addItem(pg.InfiniteLine(pos=80.0, angle=0, pen=pg.mkPen("#C87B00", width=1, style=Qt.DashLine)))
            labels = [(float(i), _short_stage_label(stage.stage_name)) for i, stage in enumerate(stages)]
            self.qc_stage_plot.getAxis("bottom").setTicks([labels])
            self.qc_stage_plot.setXRange(-0.8, max(0.8, len(stages) - 0.2), padding=0)
            self.qc_stage_plot.setYRange(0, 105, padding=0)
            self.qc_stage_plot.setTitle("QC stage scorecard — green pass, amber review, red fail")

        severity_order = ["error", "warning", "info"]
        counts = {key: 0 for key in severity_order}
        for finding in result.findings:
            key = str(finding.severity).lower()
            if key in {"critical", "fail", "failed"}:
                key = "error"
            elif key in {"warn", "review"}:
                key = "warning"
            if key in counts:
                counts[key] += 1
        sev_x = np.arange(3, dtype=float)
        sev_values = np.asarray([counts[key] for key in severity_order], dtype=float)
        sev_brushes = [pg.mkBrush("#D9534F"), pg.mkBrush("#E5A11B"), pg.mkBrush("#2B8FBF")]
        self.qc_severity_plot.addItem(pg.BarGraphItem(x=sev_x, height=sev_values, width=0.62, brushes=sev_brushes, pen=pg.mkPen("#FFFFFF")))
        self.qc_severity_plot.getAxis("bottom").setTicks([[(0.0, "Error"), (1.0, "Warning"), (2.0, "Info")]])
        self.qc_severity_plot.setXRange(-0.8, 2.8, padding=0)
        self.qc_severity_plot.setYRange(0, max(1.0, float(np.max(sev_values)) * 1.18), padding=0)
        self.qc_severity_plot.setTitle(f"Automated findings — {len(result.findings)} total")

        finding_counts = np.asarray([len(stage.findings) for stage in stages], dtype=float)
        if stages:
            stage_brushes = [pg.mkBrush("#347FA8") for _ in stages]
            self.qc_finding_stage_plot.addItem(pg.BarGraphItem(x=x, height=finding_counts, width=0.68, brushes=stage_brushes, pen=pg.mkPen("#FFFFFF")))
            self.qc_finding_stage_plot.getAxis("bottom").setTicks([[(float(i), _short_stage_label(stage.stage_name)) for i, stage in enumerate(stages)]])
            self.qc_finding_stage_plot.setXRange(-0.8, max(0.8, len(stages) - 0.2), padding=0)
            self.qc_finding_stage_plot.setYRange(0, max(1.0, float(np.max(finding_counts)) * 1.18), padding=0)
            self.qc_finding_stage_plot.setTitle("Finding concentration by QC stage")

    def _refresh_plot(self, force_mode: str | None = None) -> None:
        self.plot_widget.clear()
        if self.dataset is None or self.dataset.record_count == 0:
            self.plot_widget.setTitle("Open an electrical dataset to visualize measurements")
            return
        if force_mode:
            for i in range(self.plot_mode.count()):
                if self.plot_mode.itemData(i) == force_mode:
                    self.plot_mode.blockSignals(True)
                    self.plot_mode.setCurrentIndex(i)
                    self.plot_mode.blockSignals(False)
                    break
        mode = str(self.plot_mode.currentData() or "auto")
        if mode == "auto":
            if self.dataset.method in {ElectricalMethod.ERT, ElectricalMethod.TDIP} and self.dataset.has("pseudo_depth"):
                mode = "pseudosection"
            else:
                mode = "profile"
        if mode == "pseudosection":
            self._plot_pseudosection()
        elif mode == "qc":
            self._plot_qc_distribution()
        else:
            self._plot_profile()

    def _plot_pseudosection(self) -> None:
        dataset = self.dataset
        assert dataset is not None
        if not (dataset.has("pseudo_x") and dataset.has("pseudo_depth")):
            self.plot_widget.setTitle("Pseudosection requires A/B/M/N or AB/2 geometry")
            return
        value_name = "chargeability_mv_v" if dataset.method == ElectricalMethod.TDIP and dataset.has("chargeability_mv_v") else "apparent_resistivity_ohm_m"
        if not dataset.has(value_name):
            self.plot_widget.setTitle("No apparent resistivity/chargeability values available")
            return
        x = dataset.numeric("pseudo_x")
        depth = dataset.numeric("pseudo_depth")
        values = dataset.numeric(value_name)
        valid = np.isfinite(x) & np.isfinite(depth) & np.isfinite(values)
        if value_name == "apparent_resistivity_ohm_m":
            valid &= values > 0
        if not np.any(valid):
            self.plot_widget.setTitle("No valid pseudosection points")
            return
        plot_values = np.log10(values[valid]) if value_name == "apparent_resistivity_ohm_m" else values[valid]
        low, high = np.nanpercentile(plot_values, [2, 98]) if len(plot_values) > 2 else (np.nanmin(plot_values), np.nanmax(plot_values))
        if not np.isfinite(high - low) or high == low:
            high = low + 1.0
        normalized = np.clip((plot_values - low) / (high - low), 0.0, 1.0)
        try:
            cmap = pg.colormap.get("CET-D1")
        except Exception:
            cmap = pg.colormap.get("viridis")
        colors = cmap.map(normalized, mode="qcolor")
        spots = [{"pos": (float(px), float(-pz)), "brush": color, "pen": None, "size": 8} for px, pz, color in zip(x[valid], depth[valid], colors)]
        scatter = pg.ScatterPlotItem(spots=spots)
        self.plot_widget.addItem(scatter)
        self.plot_widget.setLabel("bottom", "Profile position / pseudo X")
        self.plot_widget.setLabel("left", "Pseudo-depth (display only)")
        label = "log10 apparent resistivity (ohm·m)" if value_name.startswith("apparent") else "chargeability (mV/V)"
        self.plot_widget.setTitle(f"Apparent-data pseudosection colored by {label}")
        self.plot_note.setText("Apparent pseudosection: QC/visualization aid only — not an inverted resistivity model.")

    def _plot_profile(self) -> None:
        dataset = self.dataset
        assert dataset is not None
        self.plot_widget.setLogMode(False, False)
        if dataset.method == ElectricalMethod.VES and dataset.has("ab2_m") and dataset.has("apparent_resistivity_ohm_m"):
            x = dataset.numeric("ab2_m")
            y = dataset.numeric("apparent_resistivity_ohm_m")
            valid = np.isfinite(x) & (x > 0) & np.isfinite(y) & (y > 0)
            order = np.argsort(x[valid])
            self.plot_widget.setLogMode(True, True)
            self.plot_widget.plot(x[valid][order], y[valid][order], pen=pg.mkPen(width=2), symbol="o", symbolSize=6)
            self.plot_widget.setLabel("bottom", "AB/2", units="m")
            self.plot_widget.setLabel("left", "Apparent resistivity", units="ohm m")
            self.plot_widget.setTitle("VES apparent-resistivity sounding curve")
            return
        if dataset.method in {ElectricalMethod.FDIP, ElectricalMethod.SIP} and dataset.has("frequency_hz"):
            y_name = "phase_mrad" if dataset.has("phase_mrad") else self._primary_measurement_name()
            if y_name:
                x = dataset.numeric("frequency_hz")
                y = dataset.numeric(y_name)
                valid = np.isfinite(x) & (x > 0) & np.isfinite(y)
                order = np.argsort(x[valid])
                self.plot_widget.setLogMode(True, False)
                self.plot_widget.plot(x[valid][order], y[valid][order], pen=pg.mkPen(width=2), symbol="o", symbolSize=6)
                self.plot_widget.setLabel("bottom", "Frequency", units="Hz")
                self.plot_widget.setLabel("left", y_name.replace("_", " "))
                self.plot_widget.setTitle("Frequency-domain / spectral electrical response")
                return
        self.plot_widget.setLogMode(False, False)
        y_name = self._primary_measurement_name()
        if not y_name:
            self.plot_widget.setTitle("No plottable measurement field")
            return
        y = self.dataset.numeric(y_name)
        if self.dataset.has("station"):
            x = self.dataset.numeric("station")
            x_label = "Station / chainage"
        elif self.dataset.has("easting"):
            x = self.dataset.numeric("easting")
            x_label = "Easting"
        else:
            x = np.arange(self.dataset.record_count, dtype=float)
            x_label = "Reading index"
        valid = np.isfinite(x) & np.isfinite(y)
        self.plot_widget.plot(x[valid], y[valid], pen=pg.mkPen(width=1.5), symbol="o" if np.count_nonzero(valid) < 300 else None, symbolSize=4)
        self.plot_widget.setLabel("bottom", x_label)
        self.plot_widget.setLabel("left", y_name.replace("_", " "))
        self.plot_widget.setTitle(f"{self.dataset.method_label} measurement profile")

    def _plot_qc_distribution(self) -> None:
        target = self._primary_measurement_name()
        if not target or self.dataset is None:
            return
        values = self.dataset.numeric(target)
        values = values[np.isfinite(values)]
        if values.size < 2:
            return
        hist, edges = np.histogram(values, bins=min(40, max(10, int(np.sqrt(values.size)))))
        curve = pg.PlotCurveItem(edges, np.r_[hist, hist[-1]], stepMode=True, fillLevel=0, brush=(100, 140, 180, 80))
        self.plot_widget.addItem(curve)
        self.plot_widget.setLabel("bottom", target.replace("_", " "))
        self.plot_widget.setLabel("left", "Count")
        self.plot_widget.setTitle("Measurement distribution for QC review")

    # ------------------------------------------------------------------
    # State / workers
    # ------------------------------------------------------------------
    def _on_dataset_loaded(self, dataset: ElectricalDataset) -> None:
        self.dataset = dataset
        self.qc_result = None
        if self.method_combo.currentData() == ElectricalMethod.AUTO.value:
            for i in range(self.method_combo.count()):
                if self.method_combo.itemData(i) == dataset.method.value:
                    self.method_combo.blockSignals(True)
                    self.method_combo.setCurrentIndex(i)
                    self.method_combo.blockSignals(False)
                    break
        self._refresh_all()
        self.status_label.setText(f"Loaded {dataset.record_count:,} records — {dataset.method_label}")

    def _on_qc_complete(self, result: ElectricalQcResult) -> None:
        self.dataset = result.dataset
        self.qc_result = result
        try:
            run_uuid = save_electrical_qc_run(self.db_engine, result)
            self.dataset.metadata["last_qc_run_uuid"] = run_uuid
        except Exception as exc:
            self.dataset.metadata["qc_history_error"] = str(exc)
        self._refresh_all()
        self.tabs.setCurrentWidget(self.qc_tab)
        self.status_label.setText(f"Electrical QC: {result.status.upper()} — score {result.score:.1f}/100")
        QMessageBox.information(self, "Electrical QC Complete", f"Method: {result.dataset.method_label}\nStatus: {result.status.upper()}\nScore: {result.score:.1f}/100\nFindings: {len(result.findings)}")

    def _run_background(self, title: str, message: str, fn: Callable[[Callable[[int, str], None]], Any], on_success: Callable[[Any], None]) -> None:
        self.activity_started.emit(title, message)
        worker = _Runnable(fn)
        self._active_workers.add(worker)
        worker.signals.progress.connect(self.activity_progress.emit)

        def finish(result: Any) -> None:
            self._active_workers.discard(worker)
            self.activity_finished.emit()
            on_success(result)

        def fail(details: str) -> None:
            self._active_workers.discard(worker)
            self.activity_finished.emit()
            short = details.strip().splitlines()[-1] if details.strip() else "Unknown error"
            QMessageBox.critical(self, title, short)

        worker.signals.finished.connect(finish)
        worker.signals.error.connect(fail)
        self._thread_pool.start(worker)

    def _selected_method(self, resolve_auto: bool = False) -> ElectricalMethod:
        method = ElectricalMethod(str(self.method_combo.currentData() or ElectricalMethod.AUTO.value))
        if resolve_auto and method == ElectricalMethod.AUTO:
            if self.dataset is not None:
                return self.dataset.method if self.dataset.method != ElectricalMethod.AUTO else ElectricalMethod.PROFILING
            return ElectricalMethod.PROFILING
        return method

    def _method_changed(self) -> None:
        if self.dataset is None:
            return
        selected = self._selected_method()
        if selected != ElectricalMethod.AUTO:
            self.dataset.method = selected
            self.qc_result = None
            self._refresh_all()

    def _primary_measurement_name(self) -> str | None:
        if self.dataset is None:
            return None
        if self.dataset.method == ElectricalMethod.SP:
            for name in ("sp_corrected_mv", "sp_mv", "voltage_mv"):
                if self.dataset.has(name):
                    return name
        if self.dataset.method in {ElectricalMethod.TDIP, ElectricalMethod.FDIP} and self.dataset.has("chargeability_mv_v"):
            return "chargeability_mv_v"
        if self.dataset.method == ElectricalMethod.SIP and self.dataset.has("phase_mrad"):
            return "phase_mrad"
        if self.dataset.method in {ElectricalMethod.MALM, ElectricalMethod.EQUIPOTENTIAL}:
            for name in ("voltage_mv", "sp_mv"):
                if self.dataset.has(name):
                    return name
        if self.dataset.method == ElectricalMethod.TELLURIC:
            for name in ("electric_field_mv_km", "electric_field_x_mv_km", "electric_field_y_mv_km", "voltage_mv", "sp_mv"):
                if self.dataset.has(name):
                    return name
        for name in ("apparent_resistivity_ohm_m", "resistance_ohm", "voltage_mv"):
            if self.dataset.has(name):
                return name
        return None

    def _require_dataset(self) -> bool:
        if self.dataset is not None:
            return True
        QMessageBox.information(self, "Electrical Methods", "Open an electrical survey dataset first.")
        return False

    @staticmethod
    def _fill_table(table: QTableWidget, rows: list[tuple[str, Any]]) -> None:
        table.setRowCount(len(rows))
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Parameter", "Value"])
        for row, (name, value) in enumerate(rows):
            for col, text in enumerate((name, _display(value))):
                item = QTableWidgetItem(str(text))
                item.setToolTip(str(text))
                table.setItem(row, col, item)
        table.setColumnWidth(0, 190)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)



def _short_stage_label(value: str, maximum: int = 18) -> str:
    text = str(value or "").replace(" / ", "/").strip()
    return text if len(text) <= maximum else text[: maximum - 1] + "…"

def _display(value: Any) -> str:
    if isinstance(value, (np.floating, float)):
        if not np.isfinite(float(value)):
            return "—"
        return f"{float(value):.6g}"
    if isinstance(value, (np.integer, int)):
        return str(int(value))
    return "—" if value is None else str(value)


def _metrics_preview(metrics: dict[str, Any], limit: int = 4) -> str:
    if not metrics:
        return "—"
    parts: list[str] = []
    for key, value in metrics.items():
        label = str(key).replace("_", " ")
        if isinstance(value, (np.floating, float)):
            rendered = "—" if not np.isfinite(float(value)) else f"{float(value):.4g}"
        elif isinstance(value, (np.integer, int)):
            rendered = f"{int(value):,}"
        else:
            rendered = str(value)
        parts.append(f"{label}: {rendered}")
        if len(parts) >= limit:
            break
    return " • ".join(parts)


def _finding_observed(finding: Any) -> str:
    parts: list[str] = []
    if getattr(finding, "row_index", None) is not None:
        parts.append(f"row {int(finding.row_index) + 1}")
    observed = getattr(finding, "observed_value", None)
    if observed is not None:
        parts.append(_display(observed))
    unit = getattr(finding, "unit", None)
    if unit and parts:
        parts[-1] = f"{parts[-1]} {unit}"
    return " • ".join(parts) if parts else "—"


def _set_badge_kind(label: QLabel, kind: str) -> None:
    kind = kind.lower()
    if kind in {"pass", "ok", "ready", "done"}:
        label.setObjectName("elecPass")
    elif kind in {"fail", "error"}:
        label.setObjectName("elecFail")
    elif kind in {"warn", "warning", "pending"}:
        label.setObjectName("elecWarn")
    else:
        label.setObjectName("elecInfo")
    label.style().unpolish(label)
    label.style().polish(label)


def _apply_status_style(item: QTableWidgetItem, status: str) -> None:
    value = status.lower()
    if any(token in value for token in ("done", "ready", "pass", "ok", "completed")):
        item.setForeground(QColor("#166A42"))
        item.setBackground(QColor("#E9F7EF"))
    elif any(token in value for token in ("fail", "error")):
        item.setForeground(QColor("#A43B3B"))
        item.setBackground(QColor("#FCEEEE"))
    elif any(token in value for token in ("pending", "warning", "warn")):
        item.setForeground(QColor("#8A5A00"))
        item.setBackground(QColor("#FFF7E5"))
    else:
        item.setForeground(QColor("#176B93"))
        item.setBackground(QColor("#EAF4FB"))


def _apply_score_style(item: QTableWidgetItem, score: float) -> None:
    if score >= 85:
        item.setForeground(QColor("#166A42"))
    elif score >= 70:
        item.setForeground(QColor("#8A5A00"))
    else:
        item.setForeground(QColor("#A43B3B"))


def _apply_severity_style(item: QTableWidgetItem, severity: str) -> None:
    value = severity.lower()
    if value == "error":
        item.setForeground(QColor("#A43B3B"))
        item.setBackground(QColor("#FCEEEE"))
    elif value == "warning":
        item.setForeground(QColor("#8A5A00"))
        item.setBackground(QColor("#FFF7E5"))
    elif value == "info":
        item.setForeground(QColor("#176B93"))
        item.setBackground(QColor("#EAF4FB"))
    else:
        item.setForeground(QColor("#166A42"))
        item.setBackground(QColor("#E9F7EF"))
