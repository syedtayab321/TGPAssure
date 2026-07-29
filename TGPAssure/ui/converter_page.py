from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QPushButton,
    QFileDialog,
    QListWidget,
    QListWidgetItem,
    QGroupBox,
    QDoubleSpinBox,
    QSpinBox,
    QCheckBox,
    QProgressBar,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QFrame,
    QGridLayout,
    QLineEdit,
    QButtonGroup,
    QStackedWidget,
)

from modules.seismic.converter import SegdConversionOptions, SegyToSegdConverter


class SegyToSegdConverterPage(QWidget):
    progress_signal = Signal(int, str)
    log_signal = Signal(str)
    finished_signal = Signal(object, object)  # reports, errors

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setProperty("module_id", "converter")
        self._files: list[Path] = []
        self._output_dir: Optional[Path] = None
        self._last_outputs: list[Path] = []
        self._stop_event: Optional[threading.Event] = None
        self._running = False
        self._converter = SegyToSegdConverter()
        self._build_ui()
        self.progress_signal.connect(self._on_progress)
        self.log_signal.connect(self._append_log)
        self.finished_signal.connect(self._on_finished)

    def _build_ui(self) -> None:
        self.setStyleSheet("""
            QWidget { font-family: Poppins, Segoe UI, Arial; font-size: 8pt; color: #13243a; }
            QLabel { background: transparent; }
            QFrame#HeroCard {
                border-radius: 9px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #14213d, stop:0.58 #0f6f9b, stop:1 #12a6c7);
            }
            QLabel#ConverterTitle { font-size: 14px; font-weight: 900; color: #ffffff; background: transparent; }
            QLabel#ConverterSubtitle { font-size: 7.5pt; color: #dceeff; background: transparent; }
            QFrame#MetricCard {
                background: #ffffff;
                border: 1px solid #d5e0ec;
                border-left: 4px solid #0a86c7;
                border-radius: 8px;
            }
            QLabel#MetricCaption { color: #5b6b7e; font-size: 7pt; font-weight: 900; background: transparent; }
            QLabel#MetricValue { color: #0b2a44; font-size: 11px; font-weight: 900; background: transparent; }
            QFrame#SideBar {
                background: #ffffff;
                border: 1px solid #d6e0ec;
                border-radius: 9px;
            }
            QLabel#SideTitle { color: #4f6176; background: #f1f5f9; border-radius: 5px; padding: 5px; font-size: 7.4pt; font-weight: 900; }
            QPushButton#NavButton {
                background: transparent;
                border: none;
                border-radius: 7px;
                color: #1e334d;
                text-align: left;
                padding: 7px 10px;
                font-weight: 850;
                min-height: 24px;
            }
            QPushButton#NavButton:hover { background: #eaf5fb; color: #086b99; }
            QPushButton#NavButton:checked { background: #0a86c7; color: #ffffff; }
            QFrame#Panel {
                background: #ffffff;
                border: 1px solid #d6e0ec;
                border-radius: 9px;
            }
            QLabel#PanelTitle { color: #0b2a44; font-size: 10px; font-weight: 900; background: transparent; }
            QLabel#HintBox { color: #4f6173; background: #eef7fc; border: 1px solid #cce6f3; border-radius: 7px; padding: 7px; }
            QGroupBox {
                background: #ffffff;
                border: 1px solid #d6e0ec;
                border-radius: 8px;
                margin-top: 9px;
                padding: 6px;
                font-weight: 850;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 9px;
                padding: 0 5px;
                color: #1f3658;
                background: #f7f9fc;
            }
            QPushButton {
                border: 1px solid #b8c7d8;
                border-radius: 7px;
                background: #f5f7fb;
                padding: 4px 10px;
                font-weight: 850;
                min-height: 23px;
            }
            QPushButton:hover { background: #eaf4fb; border-color: #1594c3; }
            QPushButton#PrimaryButton { background: #0782bd; color: white; border: 1px solid #0673a7; }
            QPushButton#PrimaryButton:hover { background: #076fa1; }
            QPushButton#SuccessButton { background: #139c60; color: white; border: 1px solid #0b7a49; }
            QPushButton#SuccessButton:hover { background: #0f814f; }
            QPushButton#OrangeButton { background: #d97706; color: white; border: 1px solid #b96105; }
            QPushButton#OrangeButton:hover { background: #b96105; }
            QPushButton#DangerButton { background: #edf2f7; color: #26384f; border: 1px solid #b7c5d6; }
            QPushButton#HeroButton {
                background: rgba(255,255,255,0.14);
                color: #ffffff;
                border: 1px solid rgba(255,255,255,0.34);
                padding: 5px 11px;
                min-width: 82px;
                min-height: 24px;
            }
            QPushButton#HeroButton:hover { background: rgba(255,255,255,0.24); }
            QLineEdit, QSpinBox, QDoubleSpinBox, QListWidget, QTableWidget, QPlainTextEdit {
                background: #ffffff;
                border: 1px solid #cbd6e3;
                border-radius: 6px;
                padding: 3px;
                selection-background-color: #0b88bd;
                selection-color: #ffffff;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox { min-height: 23px; }
            QListWidget::item { padding: 4px 6px; border-radius: 4px; }
            QListWidget::item:selected { background: #d9edf8; color: #0b2a44; }
            QHeaderView::section {
                background: #e8eef6;
                border: none;
                border-right: 1px solid #d1dbe8;
                padding: 4px 5px;
                font-weight: 900;
                color: #26384f;
            }
            QProgressBar {
                background: #edf2f7;
                border: 1px solid #d3deea;
                border-radius: 6px;
                text-align: center;
                height: 14px;
                font-weight: 800;
                color: #0b2a44;
            }
            QProgressBar::chunk { background: #0a8ec5; border-radius: 6px; }
            QCheckBox { spacing: 7px; }
            QCheckBox::indicator { width: 14px; height: 14px; border-radius: 4px; border: 1px solid #9db2c7; background: #ffffff; }
            QCheckBox::indicator:checked { background: #0a86c7; border-color: #086b99; }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(6)

        hero = QFrame()
        hero.setObjectName("HeroCard")
        hero.setMaximumHeight(70)
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(12, 7, 12, 7)
        hero_layout.setSpacing(8)
        hero_text = QVBoxLayout()
        hero_text.setSpacing(1)
        title = QLabel("SEG-Y → SEG-D Converter")
        title.setObjectName("ConverterTitle")
        subtitle = QLabel("Controlled conversion • source inspection • optional resampling • output validation • audit log")
        subtitle.setObjectName("ConverterSubtitle")
        subtitle.setWordWrap(True)
        hero_text.addWidget(title)
        hero_text.addWidget(subtitle)
        hero_layout.addLayout(hero_text, 1)
        for text, slot, name in (
            ("Add SEG-Y", self.add_files, "HeroButton"),
            ("Output Folder", self.choose_output_dir, "HeroButton"),
            ("Inspect", self.inspect_sources, "HeroButton"),
            ("Convert", self.start_conversion, "HeroButton"),
        ):
            btn = QPushButton(text)
            btn.setObjectName(name)
            btn.clicked.connect(slot)
            hero_layout.addWidget(btn)
        root.addWidget(hero)

        summary = QGridLayout()
        summary.setHorizontalSpacing(7)
        self.file_count_value = self._metric_card(summary, 0, "INPUT FILES", "0", "#0a86c7")
        self.output_dir_value = self._metric_card(summary, 1, "OUTPUT", "Not selected", "#15945c")
        self.state_value = self._metric_card(summary, 2, "STATUS", "Ready", "#7656a5")
        self.last_output_value = self._metric_card(summary, 3, "LAST SEG-D", "None", "#d97706")
        root.addLayout(summary)

        body = QHBoxLayout()
        body.setSpacing(7)
        sidebar = QFrame()
        sidebar.setObjectName("SideBar")
        sidebar.setFixedWidth(170)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(8, 8, 8, 8)
        side.setSpacing(5)
        side_title = QLabel("CONVERSION")
        side_title.setObjectName("SideTitle")
        side.addWidget(side_title)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: list[QPushButton] = []
        for idx, label in enumerate(("Overview", "Input Files", "Output Folder", "Settings / Run", "QA / Validation", "Log")):
            button = QPushButton(label)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.clicked.connect(lambda _=False, i=idx: self._set_page(i))
            self.nav_group.addButton(button, idx)
            self.nav_buttons.append(button)
            side.addWidget(button)
        side.addStretch(1)
        body.addWidget(sidebar)

        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)

        self._build_overview_page()
        self._build_input_page()
        self._build_output_page()
        self._build_settings_page()
        self._build_qa_page()
        self._build_log_page()
        self._set_page(0)

        bottom = QFrame()
        bottom.setObjectName("MetricCard")
        bottom.setMaximumHeight(52)
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(8, 5, 8, 5)
        bottom_layout.setSpacing(3)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        bottom_layout.addWidget(self.progress)
        self.status = QLabel("Ready")
        self.status.setStyleSheet("color: #33445f; font-weight: 750; background: transparent;")
        bottom_layout.addWidget(self.status)
        root.addWidget(bottom)

    def _metric_card(self, layout: QGridLayout, column: int, caption: str, value: str, color: str) -> QLabel:
        card = QFrame()
        card.setObjectName("MetricCard")
        card.setStyleSheet(f"QFrame#MetricCard {{ border-left:4px solid {color}; }}")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 6, 10, 6)
        card_layout.setSpacing(1)
        cap = QLabel(caption)
        cap.setObjectName("MetricCaption")
        val = QLabel(value)
        val.setObjectName("MetricValue")
        val.setWordWrap(False)
        card_layout.addWidget(cap)
        card_layout.addWidget(val)
        layout.addWidget(card, 0, column)
        return val

    @staticmethod
    def _panel(title: str) -> tuple[QFrame, QVBoxLayout]:
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)
        header = QLabel(title)
        header.setObjectName("PanelTitle")
        layout.addWidget(header)
        return panel, layout

    def _build_overview_page(self) -> None:
        page = QWidget()
        layout = QGridLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        readiness, ready_layout = self._panel("Workflow Readiness")
        self.input_ready_bar = self._bar_row(ready_layout, "Input queue")
        self.output_ready_bar = self._bar_row(ready_layout, "Output folder")
        self.inspect_ready_bar = self._bar_row(ready_layout, "Source inspection")
        self.convert_ready_bar = self._bar_row(ready_layout, "Conversion progress")
        hint = QLabel("Recommended sequence: Add SEG-Y → Choose output → Inspect headers → Convert → Validate SEG-D.")
        hint.setObjectName("HintBox")
        hint.setWordWrap(True)
        ready_layout.addWidget(hint)
        layout.addWidget(readiness, 0, 0)

        details, details_layout = self._panel("Current Job Summary")
        self.job_table = QTableWidget(0, 2)
        self.job_table.setHorizontalHeaderLabels(["Item", "Value"])
        self._prep_table(self.job_table)
        self.job_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.job_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        details_layout.addWidget(self.job_table)
        layout.addWidget(details, 0, 1)

        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        self.stack.addWidget(page)
        self._refresh_job_table()
        self._refresh_graphs()

    def _bar_row(self, layout: QVBoxLayout, label: str) -> QProgressBar:
        row = QHBoxLayout()
        caption = QLabel(label)
        caption.setMinimumWidth(132)
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        row.addWidget(caption)
        row.addWidget(bar, 1)
        layout.addLayout(row)
        return bar

    def _build_input_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        panel, box = self._panel("SEG-Y Input Queue")
        self.file_list = QListWidget()
        self.file_list.setAlternatingRowColors(True)
        box.addWidget(self.file_list, 1)
        btns = QHBoxLayout()
        add = QPushButton("Add SEG-Y Files")
        add.setObjectName("PrimaryButton")
        add.clicked.connect(lambda: self.add_files())
        btns.addWidget(add)
        remove = QPushButton("Remove Selected")
        remove.clicked.connect(self._remove_selected)
        btns.addWidget(remove)
        clear = QPushButton("Clear Queue")
        clear.setObjectName("DangerButton")
        clear.clicked.connect(self.clear_files)
        btns.addWidget(clear)
        btns.addStretch(1)
        box.addLayout(btns)
        layout.addWidget(panel, 1)
        self.stack.addWidget(page)

    def _build_output_page(self) -> None:
        page = QWidget()
        layout = QGridLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        panel, box = self._panel("Output Location")
        self.output_label = QLineEdit("Not selected")
        self.output_label.setReadOnly(True)
        box.addWidget(self.output_label)
        row = QHBoxLayout()
        browse = QPushButton("Browse Output Folder")
        browse.setObjectName("PrimaryButton")
        browse.clicked.connect(self.choose_output_dir)
        row.addWidget(browse)
        open_out = QPushButton("Open Last Output")
        open_out.clicked.connect(self.open_last_output)
        row.addWidget(open_out)
        validate = QPushButton("Validate Existing SEG-D")
        validate.clicked.connect(self.validate_output)
        row.addWidget(validate)
        row.addStretch(1)
        box.addLayout(row)
        layout.addWidget(panel, 0, 0)

        note_panel, note_layout = self._panel("Output Guidance")
        note = QLabel("Use a clean output folder with write permission. Converted files use the source file stem and a .segd extension. The QA page records source inspection and validation details.")
        note.setObjectName("HintBox")
        note.setWordWrap(True)
        note_layout.addWidget(note)
        note_layout.addStretch(1)
        layout.addWidget(note_panel, 0, 1)
        layout.setColumnStretch(0, 2)
        layout.setColumnStretch(1, 1)
        self.stack.addWidget(page)

    def _build_settings_page(self) -> None:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        options_box = QGroupBox("Conversion Parameters")
        options_form = QFormLayout(options_box)
        options_form.setLabelAlignment(Qt.AlignRight)
        options_form.setFormAlignment(Qt.AlignTop)
        options_form.setHorizontalSpacing(9)
        options_form.setVerticalSpacing(6)
        options_form.setContentsMargins(8, 12, 8, 8)

        self.rate_spin = QDoubleSpinBox()
        self.rate_spin.setRange(0.0, 100000.0)
        self.rate_spin.setDecimals(3)
        self.rate_spin.setSpecialValueText("Preserve source")
        self.rate_spin.setValue(0.0)
        self.rate_spin.setSuffix(" Hz")
        options_form.addRow("Output sample rate", self.rate_spin)

        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(-1e9, 1e9)
        self.scale_spin.setDecimals(6)
        self.scale_spin.setValue(1.0)
        options_form.addRow("Amplitude scale", self.scale_spin)

        self.file_number_spin = QSpinBox()
        self.file_number_spin.setRange(0, 16_777_215)
        self.file_number_spin.setSpecialValueText("Auto from SEG-Y")
        self.file_number_spin.setValue(0)
        options_form.addRow("SEG-D file number", self.file_number_spin)

        self.antialias_check = QCheckBox("Anti-alias filtering when resampling")
        self.antialias_check.setChecked(True)
        options_form.addRow("", self.antialias_check)
        self.validate_check = QCheckBox("Validate output after conversion")
        self.validate_check.setChecked(True)
        options_form.addRow("", self.validate_check)
        layout.addWidget(options_box, 1)

        workflow_panel, workflow = self._panel("Run Control")
        hint = QLabel("Run conversion after source inspection. Cancel is cooperative and stops between traces/files when possible.")
        hint.setObjectName("HintBox")
        hint.setWordWrap(True)
        workflow.addWidget(hint)
        self.inspect_btn = QPushButton("Inspect Source")
        self.inspect_btn.setObjectName("PrimaryButton")
        self.inspect_btn.clicked.connect(self.inspect_sources)
        workflow.addWidget(self.inspect_btn)
        self.run_btn = QPushButton("Start Conversion")
        self.run_btn.setObjectName("SuccessButton")
        self.run_btn.clicked.connect(self.start_conversion)
        workflow.addWidget(self.run_btn)
        self.cancel_btn = QPushButton("Cancel Conversion")
        self.cancel_btn.setObjectName("DangerButton")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_conversion)
        workflow.addWidget(self.cancel_btn)
        workflow.addStretch(1)
        layout.addWidget(workflow_panel, 1)
        self.stack.addWidget(page)

    def _build_qa_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        panel, box = self._panel("Source / Output QA Details")
        self.info_table = QTableWidget(0, 2)
        self.info_table.setHorizontalHeaderLabels(["Property", "Value"])
        self._prep_table(self.info_table)
        self.info_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.info_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        box.addWidget(self.info_table, 1)
        row = QHBoxLayout()
        inspect = QPushButton("Inspect Source")
        inspect.setObjectName("PrimaryButton")
        inspect.clicked.connect(self.inspect_sources)
        row.addWidget(inspect)
        validate = QPushButton("Validate Output")
        validate.clicked.connect(self.validate_output)
        row.addWidget(validate)
        open_out = QPushButton("Open Last Output")
        open_out.clicked.connect(self.open_last_output)
        row.addWidget(open_out)
        row.addStretch(1)
        box.addLayout(row)
        layout.addWidget(panel, 1)
        self.stack.addWidget(page)

    def _build_log_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        panel, box = self._panel("Conversion Log")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        box.addWidget(self.log, 1)
        layout.addWidget(panel, 1)
        self.stack.addWidget(page)

    @staticmethod
    def _prep_table(table: QTableWidget) -> None:
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(22)
        table.setSelectionBehavior(QTableWidget.SelectRows)

    def _set_page(self, index: int) -> None:
        index = max(0, min(index, self.stack.count() - 1))
        self.stack.setCurrentIndex(index)
        if index < len(self.nav_buttons):
            self.nav_buttons[index].setChecked(True)

    def _refresh_summary_cards(self) -> None:
        if hasattr(self, "file_count_value"):
            self.file_count_value.setText(str(len(self._files)))
        if hasattr(self, "output_dir_value"):
            if self._output_dir is None:
                self.output_dir_value.setText("Not selected")
            else:
                text = str(self._output_dir)
                self.output_dir_value.setText(text if len(text) <= 38 else "…" + text[-37:])
        if hasattr(self, "last_output_value"):
            if self._last_outputs:
                text = self._last_outputs[-1].name
                self.last_output_value.setText(text if len(text) <= 34 else text[:31] + "…")
            else:
                self.last_output_value.setText("None")
        self._refresh_job_table()
        self._refresh_graphs()

    def _refresh_job_table(self) -> None:
        if not hasattr(self, "job_table"):
            return
        rows = [
            ("Input files", f"{len(self._files):,}"),
            ("Output folder", str(self._output_dir) if self._output_dir else "Not selected"),
            ("Selected sample rate", "Preserve source" if not hasattr(self, "rate_spin") or self.rate_spin.value() <= 0 else f"{self.rate_spin.value():.3f} Hz"),
            ("Amplitude scale", f"{self.scale_spin.value():.6g}" if hasattr(self, "scale_spin") else "1"),
            ("Last output", str(self._last_outputs[-1]) if self._last_outputs else "None"),
            ("Status", self.state_value.text() if hasattr(self, "state_value") else "Ready"),
        ]
        self.job_table.setRowCount(0)
        for key, value in rows:
            row = self.job_table.rowCount()
            self.job_table.insertRow(row)
            self.job_table.setItem(row, 0, QTableWidgetItem(key))
            self.job_table.setItem(row, 1, QTableWidgetItem(str(value)))

    def _refresh_graphs(self) -> None:
        if not hasattr(self, "input_ready_bar"):
            return
        self.input_ready_bar.setValue(100 if self._files else 0)
        self.output_ready_bar.setValue(100 if self._output_dir else 0)
        self.inspect_ready_bar.setValue(100 if getattr(self, "info_table", None) is not None and self.info_table.rowCount() > 0 else 0)
        self.convert_ready_bar.setValue(self.progress.value() if hasattr(self, "progress") else 0)

    def add_files(self, paths: Optional[list[str]] = None) -> None:
        if paths is None:
            selected, _ = QFileDialog.getOpenFileNames(
                self, "Select SEG-Y files", str(Path.home()),
                "SEG-Y Files (*.sgy *.segy);;All Files (*.*)"
            )
            paths = selected
        for raw in paths or []:
            p = Path(raw).expanduser().resolve()
            if p not in self._files:
                self._files.append(p)
                self.file_list.addItem(QListWidgetItem(str(p)))
        if self._files and self._output_dir is None:
            self._output_dir = self._files[0].parent
            self.output_label.setText(str(self._output_dir))
        self._refresh_summary_cards()
        self._set_page(1)

    def open_single_file(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self, "Open SEG-Y", str(Path.home()), "SEG-Y Files (*.sgy *.segy);;All Files (*.*)"
        )
        if selected:
            self.clear_files()
            self.add_files([selected])
            self.inspect_sources()

    def _remove_selected(self) -> None:
        rows = sorted({i.row() for i in self.file_list.selectedIndexes()}, reverse=True)
        for row in rows:
            self._files.pop(row)
            self.file_list.takeItem(row)
        self._refresh_summary_cards()

    def clear_files(self) -> None:
        if self._running:
            return
        self._files.clear()
        self.file_list.clear()
        self.info_table.setRowCount(0)
        self._last_outputs.clear()
        self._refresh_summary_cards()

    def choose_output_dir(self) -> None:
        start = str(self._output_dir or (self._files[0].parent if self._files else Path.home()))
        selected = QFileDialog.getExistingDirectory(self, "Select SEG-D output directory", start)
        if selected:
            self._output_dir = Path(selected).resolve()
            self.output_label.setText(str(self._output_dir))
            self._refresh_summary_cards()
            self._set_page(2)

    def _set_info(self, items: dict) -> None:
        self.info_table.setRowCount(0)
        for key, value in items.items():
            row = self.info_table.rowCount()
            self.info_table.insertRow(row)
            self.info_table.setItem(row, 0, QTableWidgetItem(str(key).replace("_", " ").title()))
            if isinstance(value, (list, tuple)):
                value = ", ".join(map(str, value))
            self.info_table.setItem(row, 1, QTableWidgetItem(str(value)))
        self._refresh_graphs()

    def inspect_sources(self) -> None:
        if not self._files:
            QMessageBox.information(self, "SEG-Y Converter", "Add at least one SEG-Y file first.")
            return
        try:
            info = self._converter.inspect_source(self._files[0])
            self._set_info(info)
            self._append_log(f"Inspected: {self._files[0].name}")
            self._set_page(4)
        except Exception as exc:
            QMessageBox.critical(self, "SEG-Y Inspection Error", str(exc))

    def _options(self) -> SegdConversionOptions:
        rate = float(self.rate_spin.value())
        return SegdConversionOptions(
            destination_sample_rate_hz=rate if rate > 0 else None,
            amplitude_scale=float(self.scale_spin.value()),
            file_number=int(self.file_number_spin.value()) or None,
            antialias=self.antialias_check.isChecked(),
            validate_output=self.validate_check.isChecked(),
        )

    def start_conversion(self) -> None:
        if self._running:
            return
        if not self._files:
            QMessageBox.information(self, "SEG-Y Converter", "Add at least one SEG-Y file first.")
            return
        if self._output_dir is None:
            self.choose_output_dir()
            if self._output_dir is None:
                return

        self._running = True
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        if hasattr(self, "state_value"):
            self.state_value.setText("Running")
        self.progress.setValue(0)
        self._refresh_graphs()
        self._last_outputs = []
        stop_event = threading.Event()
        self._stop_event = stop_event
        files = list(self._files)
        output_dir = Path(self._output_dir)
        options = self._options()
        self._set_page(5)

        def worker() -> None:
            reports = []
            errors = []
            total = max(1, len(files))
            for file_no, src in enumerate(files):
                if stop_event.is_set():
                    break
                dst = output_dir / f"{src.stem}.segd"
                self.log_signal.emit(f"Starting {src.name} → {dst.name}")
                try:
                    def progress(frac: float, remaining: float, base=file_no, name=src.name) -> None:
                        overall = int(((base + frac) / total) * 100.0)
                        self.progress_signal.emit(overall, f"Converting {name} — {frac * 100:.1f}% — ETA {remaining:.1f}s")
                    report = self._converter.convert(
                        src, dst, options=options, progress_callback=progress, stop_event=stop_event
                    )
                    reports.append(report)
                    self.log_signal.emit(
                        f"Completed {src.name}: {report.trace_count:,} traces, "
                        f"{report.output_sample_interval_us} us, {report.elapsed_seconds:.2f}s"
                    )
                    for warning in report.warnings:
                        self.log_signal.emit(f"Warning: {warning}")
                except InterruptedError:
                    self.log_signal.emit("Conversion cancelled by user.")
                    break
                except Exception as exc:
                    errors.append((src, str(exc)))
                    self.log_signal.emit(f"ERROR {src.name}: {exc}")
            self.finished_signal.emit(reports, errors)

        threading.Thread(target=worker, daemon=True).start()

    def cancel_conversion(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
            self.status.setText("Cancellation requested…")
            if hasattr(self, "state_value"):
                self.state_value.setText("Cancelling")

    def validate_output(self) -> None:
        path = None
        if self._last_outputs:
            path = self._last_outputs[-1]
        else:
            selected, _ = QFileDialog.getOpenFileName(
                self, "Validate SEG-D", str(self._output_dir or Path.home()),
                "SEG-D Files (*.segd *.sgd *.d);;All Files (*.*)"
            )
            if selected:
                path = Path(selected)
        if path is None:
            return
        try:
            result = self._converter.validate_output(path)
            self._set_info({"file": str(path), **result})
            self._set_page(4)
            QMessageBox.information(self, "SEG-D Validation", "SEG-D structure and sample payload validation passed.")
        except Exception as exc:
            QMessageBox.critical(self, "SEG-D Validation Failed", str(exc))

    def open_last_output(self) -> None:
        if not self._last_outputs:
            QMessageBox.information(self, "SEG-Y Converter", "No converted output is available yet.")
            return
        window = self.window()
        opener = getattr(window, "_open_segd_path", None)
        if callable(opener):
            opener(str(self._last_outputs[-1]))
        else:
            QMessageBox.information(self, "Converted Output", str(self._last_outputs[-1]))

    def _on_progress(self, value: int, message: str) -> None:
        value = max(0, min(100, int(value)))
        self.progress.setValue(value)
        self.status.setText(message)
        if hasattr(self, "state_value"):
            self.state_value.setText(f"{value}%")
        self._refresh_graphs()

    def _append_log(self, text: str) -> None:
        self.log.appendPlainText(text)

    def _on_finished(self, reports, errors) -> None:
        self._running = False
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self._last_outputs = [Path(r.output_path) for r in reports]
        self._refresh_summary_cards()
        if reports:
            self.progress.setValue(100)
            last = reports[-1]
            self._set_info({
                "output": str(last.output_path),
                "trace_count": last.trace_count,
                "source_sample_intervals_us": last.source_sample_intervals_us,
                "output_sample_interval_us": last.output_sample_interval_us,
                "resampled_traces": last.resampled_trace_count,
                "minimum_samples": last.minimum_samples,
                "maximum_samples": last.maximum_samples,
                "nonfinite_samples_replaced": last.nonfinite_samples_replaced,
                "segd_file_number": last.file_number,
                "elapsed_seconds": f"{last.elapsed_seconds:.3f}",
            })
        if errors:
            self.status.setText(f"Completed with {len(errors)} error(s)")
            if hasattr(self, "state_value"):
                self.state_value.setText("Errors")
            QMessageBox.warning(self, "Conversion Complete", f"Converted {len(reports)} file(s); {len(errors)} failed. See the log.")
        elif reports:
            self.status.setText(f"Complete — {len(reports)} SEG-D file(s) created and validated")
            if hasattr(self, "state_value"):
                self.state_value.setText("Complete")
            QMessageBox.information(self, "Conversion Complete", f"Successfully converted {len(reports)} SEG-Y file(s) to SEG-D.")
        else:
            self.status.setText("Cancelled")
            if hasattr(self, "state_value"):
                self.state_value.setText("Cancelled")
        self._refresh_graphs()
