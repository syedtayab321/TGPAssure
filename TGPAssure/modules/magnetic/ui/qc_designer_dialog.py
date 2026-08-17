from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from core.domain.automated_qc_pipeline import QCPipelineDesign, QCStageDescriptor
from modules.magnetic.magnetic_engine import PROCESSED_STAGE_KEYS, RAW_STAGE_KEYS
from modules.magnetic.magnetic_profiles import MAGNETIC_THRESHOLD_LABELS, PROFILES, get_profile


_STYLE = """
QDialog { background:#F3F6FA; color:#17212B; font-family:"Segoe UI"; font-size:8.5pt; }
QFrame#designerHeader { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #243B53,stop:1 #3F6E8C); border-radius:8px; }
QLabel#designerTitle { color:white; font-size:15pt; font-weight:800; }
QLabel#designerSubtitle { color:#D9EAF5; font-size:8.5pt; }
QLabel#sectionTitle { color:#173B57; font-weight:800; font-size:9.5pt; }
QTableWidget { background:white; border:1px solid #D3DDE7; border-radius:6px; gridline-color:#E8EDF3; alternate-background-color:#F8FAFC; }
QHeaderView::section { background:#E9F0F6; color:#243746; padding:5px; border:0; border-right:1px solid #D1DAE4; font-weight:700; }
QPushButton { background:#FFFFFF; border:1px solid #BFCBD7; border-radius:6px; padding:5px 10px; font-weight:700; }
QPushButton:hover { background:#EDF5FB; border-color:#79A7C7; }
QPushButton#primary { background:#2F6FA7; color:white; border-color:#245A88; }
QPushButton#primary:hover { background:#245F91; }
QComboBox,QLineEdit { background:white; border:1px solid #BFCBD7; border-radius:5px; padding:4px 7px; min-height:23px; }
QTabWidget::pane { border:1px solid #D3DDE7; border-radius:6px; background:white; }
QTabBar::tab { background:#E8EEF5; border:1px solid #C8D3DE; padding:6px 12px; }
QTabBar::tab:selected { background:white; color:#174A7C; font-weight:800; }
"""


class MagneticQcDesignerDialog(QDialog):
    """Professional non-destructive designer for the existing Magnetic QC engine."""

    def __init__(
        self,
        stages: tuple[QCStageDescriptor, ...],
        design: QCPipelineDesign | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Magnetic QC Designer & Automated Pipeline")
        self.resize(1020, 720)
        self.setMinimumSize(880, 620)
        self.setStyleSheet(_STYLE)
        self._stages = stages
        self._design = design or QCPipelineDesign(
            module_id="magnetic",
            name="Magnetic Automated QC",
            profile_name="standard",
            stage_keys=[stage.key for stage in stages],
        )
        self._build_ui()
        self._load_design(self._design)

    @property
    def design(self) -> QCPipelineDesign:
        return self._collect_design()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self); root.setContentsMargins(12, 12, 12, 12); root.setSpacing(10)
        header = QFrame(); header.setObjectName("designerHeader")
        hl = QVBoxLayout(header); hl.setContentsMargins(18, 12, 18, 12); hl.setSpacing(2)
        title = QLabel("Magnetic QC Designer"); title.setObjectName("designerTitle")
        subtitle = QLabel("Build repeatable QC pipelines from the existing TGPAssure scientific stages. Raw data is never overwritten."); subtitle.setObjectName("designerSubtitle")
        hl.addWidget(title); hl.addWidget(subtitle); root.addWidget(header)

        config = QHBoxLayout(); config.setSpacing(8)
        config.addWidget(QLabel("Pipeline name:")); self.name_edit = QLineEdit(); self.name_edit.setMinimumWidth(240); config.addWidget(self.name_edit)
        config.addWidget(QLabel("QC profile:")); self.profile_combo = QComboBox()
        for key, profile in PROFILES.items(): self.profile_combo.addItem(profile.display_name, key)
        self.profile_combo.currentIndexChanged.connect(self._profile_changed)
        config.addWidget(self.profile_combo)
        self.stop_on_failure = QCheckBox("Stop after failed stage")
        config.addWidget(self.stop_on_failure); config.addStretch(1)
        load_btn = QPushButton("Load Design"); load_btn.clicked.connect(self._load_from_file)
        save_btn = QPushButton("Save Design"); save_btn.clicked.connect(self._save_to_file)
        config.addWidget(load_btn); config.addWidget(save_btn); root.addLayout(config)

        self.tabs = QTabWidget(); root.addWidget(self.tabs, 1)
        self.tabs.addTab(self._stage_tab(), "QC Stages")
        self.tabs.addTab(self._threshold_tab(), "Thresholds")
        self.tabs.addTab(self._automation_tab(), "Automation")

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.run_button = QPushButton("Run Automated QC"); self.run_button.setObjectName("primary")
        self.run_button.clicked.connect(self.accept); buttons.addButton(self.run_button, QDialogButtonBox.AcceptRole)
        buttons.rejected.connect(self.reject); root.addWidget(buttons)

    def _stage_tab(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(8, 8, 8, 8); layout.setSpacing(7)
        row = QHBoxLayout(); row.addWidget(QLabel("Stage selection controls the scientific checks executed by the background pipeline.")); row.addStretch(1)
        for text, slot in (("Full QC", self._select_all), ("Raw QC", lambda: self._select_keys(RAW_STAGE_KEYS)), ("Processed QC", lambda: self._select_keys(PROCESSED_STAGE_KEYS)), ("Clear", self._clear_optional)):
            btn = QPushButton(text); btn.clicked.connect(slot); row.addWidget(btn)
        layout.addLayout(row)
        self.stage_table = QTableWidget(len(self._stages), 4)
        self.stage_table.setHorizontalHeaderLabels(["Run", "Category", "QC Stage", "Purpose"])
        self.stage_table.setAlternatingRowColors(True); self.stage_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.stage_table.verticalHeader().setVisible(False); self.stage_table.verticalHeader().setDefaultSectionSize(25)
        self.stage_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.stage_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.stage_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.stage_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        for row_idx, stage in enumerate(self._stages):
            check = QTableWidgetItem(); check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable); check.setCheckState(Qt.CheckState.Checked); check.setData(Qt.ItemDataRole.UserRole, stage.key)
            if stage.required: check.setFlags(Qt.ItemFlag.ItemIsEnabled); check.setCheckState(Qt.CheckState.Checked)
            self.stage_table.setItem(row_idx, 0, check)
            self.stage_table.setItem(row_idx, 1, QTableWidgetItem(stage.category))
            name = QTableWidgetItem(stage.display_name + ("  (required)" if stage.required else "")); name.setData(Qt.ItemDataRole.UserRole, stage.key); self.stage_table.setItem(row_idx, 2, name)
            self.stage_table.setItem(row_idx, 3, QTableWidgetItem(stage.description))
        layout.addWidget(self.stage_table, 1); return page

    def _threshold_tab(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(8, 8, 8, 8); layout.setSpacing(7)
        top = QHBoxLayout(); top.addWidget(QLabel("Override only values that differ from the selected QC profile.")); top.addStretch(1)
        reset = QPushButton("Reset Overrides"); reset.clicked.connect(self._reset_thresholds); top.addWidget(reset); layout.addLayout(top)
        self.threshold_table = QTableWidget(0, 4); self.threshold_table.setHorizontalHeaderLabels(["Override", "Threshold", "Profile value", "Effective value"])
        self.threshold_table.setAlternatingRowColors(True); self.threshold_table.verticalHeader().setVisible(False)
        self.threshold_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.threshold_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.threshold_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.threshold_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        layout.addWidget(self.threshold_table, 1); return page

    def _automation_tab(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(12, 12, 12, 12); layout.setSpacing(8)
        label = QLabel("Reusable pipeline architecture"); label.setObjectName("sectionTitle"); layout.addWidget(label)
        text = QTextEdit(); text.setReadOnly(True); text.setPlainText(
            "This designer stores a module-neutral QCPipelineDesign (stage IDs, profile, overrides and automation options).\n\n"
            "Magnetic is the first registered adapter. The same core registry accepts adapters for Seismic/Uphole/Seismetics, Gravity, Geodetic and Electrical without changing this design format.\n\n"
            "Execution remains inside each scientific module, so module-specific algorithms and QC rules are not duplicated or weakened. Cancellation is cooperative and checked between pipeline stages."
        ); layout.addWidget(text, 1); return page

    def _selected_stage_keys(self) -> list[str]:
        keys = []
        required = {stage.key for stage in self._stages if stage.required}
        for row in range(self.stage_table.rowCount()):
            item = self.stage_table.item(row, 0); key = str(item.data(Qt.ItemDataRole.UserRole) or "")
            if item.checkState() == Qt.CheckState.Checked or key in required: keys.append(key)
        return keys

    def _select_keys(self, keys) -> None:
        selected = set(keys) | {stage.key for stage in self._stages if stage.required}
        for row in range(self.stage_table.rowCount()):
            item = self.stage_table.item(row, 0); item.setCheckState(Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole) in selected else Qt.CheckState.Unchecked)

    def _select_all(self) -> None: self._select_keys(stage.key for stage in self._stages)
    def _clear_optional(self) -> None: self._select_keys(())

    def _profile_changed(self, *_args) -> None:
        self._populate_thresholds(self._collect_overrides())

    def _populate_thresholds(self, overrides: dict[str, Any]) -> None:
        key = str(self.profile_combo.currentData() or "standard")
        profile = get_profile(key)
        self.threshold_table.setRowCount(len(profile.thresholds))
        for row, (name, base_value) in enumerate(profile.thresholds.items()):
            override = QTableWidgetItem(); override.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable); override.setCheckState(Qt.CheckState.Checked if name in overrides else Qt.CheckState.Unchecked); override.setData(Qt.ItemDataRole.UserRole, name)
            self.threshold_table.setItem(row, 0, override)
            label = QTableWidgetItem(MAGNETIC_THRESHOLD_LABELS.get(name, name)); label.setToolTip(name); self.threshold_table.setItem(row, 1, label)
            self.threshold_table.setItem(row, 2, QTableWidgetItem("" if base_value is None else str(base_value)))
            effective = overrides.get(name, base_value); item = QTableWidgetItem("" if effective is None else str(effective)); self.threshold_table.setItem(row, 3, item)

    def _collect_overrides(self) -> dict[str, Any]:
        if not hasattr(self, "threshold_table"): return dict(self._design.threshold_overrides)
        out: dict[str, Any] = {}
        for row in range(self.threshold_table.rowCount()):
            flag = self.threshold_table.item(row, 0)
            if flag is None or flag.checkState() != Qt.CheckState.Checked: continue
            key = str(flag.data(Qt.ItemDataRole.UserRole)); text = self.threshold_table.item(row, 3).text().strip()
            if text.lower() in {"", "none", "null"}: value = None
            else:
                try: value = float(text)
                except ValueError: value = text
            out[key] = value
        return out

    def _reset_thresholds(self) -> None: self._populate_thresholds({})

    def _collect_design(self) -> QCPipelineDesign:
        return QCPipelineDesign(
            module_id="magnetic",
            name=self.name_edit.text().strip() or "Magnetic Automated QC",
            profile_name=str(self.profile_combo.currentData() or "standard"),
            stage_keys=self._selected_stage_keys(),
            threshold_overrides=self._collect_overrides(),
            stop_on_failure=self.stop_on_failure.isChecked(),
            metadata={"designer": "TGPAssure Magnetic QC Designer"},
        ).normalized()

    def _load_design(self, design: QCPipelineDesign) -> None:
        self._design = design
        self.name_edit.setText(design.name)
        idx = self.profile_combo.findData(design.profile_name); self.profile_combo.setCurrentIndex(max(0, idx))
        self.stop_on_failure.setChecked(bool(design.stop_on_failure)); self._select_keys(design.stage_keys)
        self._populate_thresholds(dict(design.threshold_overrides))

    def _save_to_file(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save QC Pipeline Design", "magnetic_qc_pipeline.json", "QC Pipeline (*.json)")
        if path:
            try: self._collect_design().save(path)
            except Exception as exc: QMessageBox.critical(self, "QC Designer", str(exc))

    def _load_from_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load QC Pipeline Design", str(Path.home()), "QC Pipeline (*.json)")
        if not path: return
        try:
            design = QCPipelineDesign.load(path)
            if design.module_id != "magnetic": raise ValueError(f"Pipeline is for module '{design.module_id}', not Magnetic")
            self._load_design(design)
        except Exception as exc:
            QMessageBox.critical(self, "QC Designer", f"Unable to load pipeline:\n{exc}")
