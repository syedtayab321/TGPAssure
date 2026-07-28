from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QFileDialog, QListWidget, QListWidgetItem, QGroupBox, QDoubleSpinBox,
    QSpinBox, QCheckBox, QProgressBar, QPlainTextEdit, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QSplitter, QTabWidget,
    QFrame, QGridLayout, QLineEdit, QScrollArea
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
            QWidget { font-size: 8pt; color: #172033; }
            QLabel { background: transparent; }
            QLabel#ConverterTitle { font-size: 14px; font-weight: 800; color: #ffffff; background: transparent; }
            QLabel#ConverterSubtitle { font-size: 7.6pt; color: #dceeff; background: transparent; }
            QFrame#HeroCard {
                border-radius: 9px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #14213d, stop:0.58 #0f6f9b, stop:1 #12a6c7);
            }
            QFrame#MetricCard {
                background: #ffffff;
                border: 1px solid #d5e0ec;
                border-radius: 8px;
            }
            QLabel#MetricCaption { color: #5f6d80; font-size: 7.2pt; font-weight: 800; letter-spacing: 0.2px; background: transparent; }
            QLabel#MetricValue { color: #10203a; font-size: 9.4pt; font-weight: 800; background: transparent; }
            QGroupBox {
                background: #ffffff;
                border: 1px solid #d6e0ec;
                border-radius: 8px;
                margin-top: 9px;
                padding: 6px;
                font-size: 8pt;
                font-weight: 750;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 9px;
                padding: 0 5px;
                color: #1f3658;
                background: #f7f9fc;
            }
            QTabWidget::pane {
                border: 1px solid #d6e0ec;
                border-radius: 8px;
                background: #f7f9fc;
                top: -1px;
            }
            QTabBar::tab {
                background: #edf3f9;
                border: 1px solid #d4deeb;
                border-bottom: none;
                padding: 4px 10px;
                margin-right: 2px;
                border-top-left-radius: 7px;
                border-top-right-radius: 7px;
                font-size: 8pt;
                font-weight: 750;
                color: #314257;
                min-height: 22px;
            }
            QTabBar::tab:selected { background: #ffffff; color: #0676a8; }
            QPushButton {
                border: 1px solid #b8c7d8;
                border-radius: 6px;
                background: #f5f7fb;
                padding: 4px 9px;
                font-size: 8pt;
                font-weight: 750;
                min-height: 21px;
            }
            QPushButton:hover { background: #eaf4fb; border-color: #1594c3; }
            QPushButton#PrimaryButton {
                background: #0782bd;
                color: white;
                border: 1px solid #0673a7;
            }
            QPushButton#SuccessButton {
                background: #139c60;
                color: white;
                border: 1px solid #0b7a49;
            }
            QPushButton#DangerButton {
                background: #edf2f7;
                color: #26384f;
                border: 1px solid #b7c5d6;
            }
            QPushButton#HeroButton {
                background: rgba(255,255,255,0.14);
                color: #ffffff;
                border: 1px solid rgba(255,255,255,0.34);
                padding: 5px 10px;
                min-width: 80px;
                min-height: 24px;
            }
            QPushButton#HeroButton:hover { background: rgba(255,255,255,0.24); }
            QLineEdit, QSpinBox, QDoubleSpinBox, QListWidget, QTableWidget, QPlainTextEdit {
                background: #ffffff;
                border: 1px solid #cbd6e3;
                border-radius: 6px;
                padding: 3px;
                font-size: 8pt;
                selection-background-color: #0b88bd;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox { min-height: 21px; }
            QListWidget::item { padding: 3px 5px; }
            QHeaderView::section {
                background: #e8eef6;
                border: none;
                border-right: 1px solid #d1dbe8;
                padding: 4px 5px;
                font-size: 8pt;
                font-weight: 800;
                color: #26384f;
            }
            QProgressBar {
                background: #edf2f7;
                border: 1px solid #d3deea;
                border-radius: 6px;
                text-align: center;
                height: 13px;
                font-size: 7.8pt;
                font-weight: 700;
            }
            QProgressBar::chunk { background: #0a8ec5; border-radius: 6px; }
            QScrollArea { border: none; background: #f7f9fc; }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(5)

        hero = QFrame()
        hero.setObjectName("HeroCard")
        hero.setMaximumHeight(74)
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(12, 7, 12, 7)
        hero_layout.setSpacing(8)
        hero_text = QVBoxLayout()
        hero_text.setContentsMargins(0, 0, 0, 0)
        hero_text.setSpacing(1)
        title = QLabel("SEG-Y → SEG-D Converter")
        title.setObjectName("ConverterTitle")
        title.setAttribute(Qt.WA_TranslucentBackground)
        subtitle = QLabel("Rev 2.1 / 8058 conversion • source inspection • optional resampling • output validation")
        subtitle.setObjectName("ConverterSubtitle")
        subtitle.setAttribute(Qt.WA_TranslucentBackground)
        subtitle.setWordWrap(True)
        hero_text.addWidget(title)
        hero_text.addWidget(subtitle)
        hero_layout.addLayout(hero_text, 1)

        add_top = QPushButton("Add SEG-Y")
        add_top.setObjectName("HeroButton")
        add_top.clicked.connect(lambda: self.add_files())
        hero_layout.addWidget(add_top)
        choose_top = QPushButton("Output Folder")
        choose_top.setObjectName("HeroButton")
        choose_top.clicked.connect(self.choose_output_dir)
        hero_layout.addWidget(choose_top)
        inspect_top = QPushButton("Inspect")
        inspect_top.setObjectName("HeroButton")
        inspect_top.clicked.connect(self.inspect_sources)
        hero_layout.addWidget(inspect_top)
        convert_top = QPushButton("Convert")
        convert_top.setObjectName("HeroButton")
        convert_top.clicked.connect(self.start_conversion)
        hero_layout.addWidget(convert_top)
        root.addWidget(hero)

        summary = QHBoxLayout()
        summary.setSpacing(6)
        self.file_count_value = self._metric_card(summary, "INPUT FILES", "0")
        self.output_dir_value = self._metric_card(summary, "OUTPUT", "Not selected")
        self.state_value = self._metric_card(summary, "STATUS", "Ready")
        self.last_output_value = self._metric_card(summary, "LAST SEG-D", "None")
        root.addLayout(summary)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.setMinimumHeight(330)
        root.addWidget(tabs, 1)

        def make_scroll(content: QWidget) -> QScrollArea:
            sc = QScrollArea()
            sc.setWidgetResizable(True)
            sc.setWidget(content)
            return sc

        # Tab 1: input files only, so the SEG-Y queue has enough vertical room.
        input_tab = QWidget()
        input_layout = QVBoxLayout(input_tab)
        input_layout.setContentsMargins(10, 10, 10, 10)
        input_layout.setSpacing(7)
        input_box = QGroupBox("SEG-Y Input Queue")
        input_box_layout = QVBoxLayout(input_box)
        input_box_layout.setContentsMargins(8, 11, 8, 8)
        input_box_layout.setSpacing(6)
        self.file_list = QListWidget()
        self.file_list.setMinimumHeight(210)
        self.file_list.setAlternatingRowColors(True)
        input_box_layout.addWidget(self.file_list, 1)
        file_row = QHBoxLayout()
        file_row.setSpacing(6)
        add = QPushButton("Add SEG-Y Files")
        add.setObjectName("PrimaryButton")
        add.clicked.connect(lambda: self.add_files())
        file_row.addWidget(add)
        remove = QPushButton("Remove Selected")
        remove.clicked.connect(self._remove_selected)
        file_row.addWidget(remove)
        clear = QPushButton("Clear Queue")
        clear.setObjectName("DangerButton")
        clear.clicked.connect(self.clear_files)
        file_row.addWidget(clear)
        input_box_layout.addLayout(file_row)
        input_layout.addWidget(input_box, 1)
        tabs.addTab(make_scroll(input_tab), "1  Input Files")

        # Tab 2: output folder only, separated from the input queue to avoid clipped fields.
        output_tab = QWidget()
        output_layout_page = QVBoxLayout(output_tab)
        output_layout_page.setContentsMargins(10, 10, 10, 10)
        output_layout_page.setSpacing(7)
        output_box = QGroupBox("SEG-D Output Directory")
        output_layout = QHBoxLayout(output_box)
        output_layout.setContentsMargins(8, 11, 8, 8)
        output_layout.setSpacing(6)
        self.output_label = QLineEdit("No output directory selected")
        self.output_label.setReadOnly(True)
        output_layout.addWidget(self.output_label, 1)
        choose = QPushButton("Browse")
        choose.clicked.connect(self.choose_output_dir)
        output_layout.addWidget(choose)
        output_layout_page.addWidget(output_box)

        output_actions_box = QGroupBox("Output Actions")
        output_actions = QHBoxLayout(output_actions_box)
        output_actions.setContentsMargins(8, 11, 8, 8)
        output_actions.setSpacing(6)
        open_out = QPushButton("Open Last Output")
        open_out.clicked.connect(self.open_last_output)
        output_actions.addWidget(open_out)
        validate_now_out = QPushButton("Validate Existing SEG-D")
        validate_now_out.clicked.connect(self.validate_output)
        output_actions.addWidget(validate_now_out)
        output_actions.addStretch(1)
        output_layout_page.addWidget(output_actions_box)

        readiness_box = QGroupBox("Readiness")
        readiness_layout = QVBoxLayout(readiness_box)
        readiness_layout.setContentsMargins(8, 11, 8, 8)
        readiness = QLabel("Workflow: add source SEG-Y files, choose a clean output folder, inspect headers, then run conversion. The converter preserves source traces unless resampling or scaling is selected.")
        readiness.setWordWrap(True)
        readiness.setStyleSheet("color: #536275; background: #eef7fc; border: 1px solid #cce6f3; border-radius: 7px; padding: 6px;")
        readiness_layout.addWidget(readiness)
        output_layout_page.addWidget(readiness_box)
        output_layout_page.addStretch(1)
        tabs.addTab(make_scroll(output_tab), "2  Output Folder")

        # Tab 3: settings and run controls.
        settings_tab = QWidget()
        settings_layout = QHBoxLayout(settings_tab)
        settings_layout.setContentsMargins(10, 10, 10, 10)
        settings_layout.setSpacing(8)

        options_box = QGroupBox("Conversion Parameters")
        options_form = QFormLayout(options_box)
        options_form.setLabelAlignment(Qt.AlignRight)
        options_form.setFormAlignment(Qt.AlignTop)
        options_form.setHorizontalSpacing(9)
        options_form.setVerticalSpacing(5)
        options_form.setContentsMargins(8, 12, 8, 8)

        self.rate_spin = QDoubleSpinBox()
        self.rate_spin.setRange(0.0, 100000.0)
        self.rate_spin.setDecimals(3)
        self.rate_spin.setSpecialValueText("Preserve source")
        self.rate_spin.setValue(0.0)
        self.rate_spin.setSuffix(" Hz")
        self.rate_spin.setMinimumWidth(150)
        options_form.addRow("Output sample rate", self.rate_spin)

        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(-1e9, 1e9)
        self.scale_spin.setDecimals(6)
        self.scale_spin.setValue(1.0)
        self.scale_spin.setMinimumWidth(150)
        options_form.addRow("Amplitude scale", self.scale_spin)

        self.file_number_spin = QSpinBox()
        self.file_number_spin.setRange(0, 16_777_215)
        self.file_number_spin.setSpecialValueText("Auto from SEG-Y")
        self.file_number_spin.setValue(0)
        self.file_number_spin.setMinimumWidth(150)
        options_form.addRow("SEG-D file number", self.file_number_spin)

        self.antialias_check = QCheckBox("Anti-alias filtering when resampling")
        self.antialias_check.setChecked(True)
        options_form.addRow("", self.antialias_check)
        self.validate_check = QCheckBox("Validate output after conversion")
        self.validate_check.setChecked(True)
        options_form.addRow("", self.validate_check)
        settings_layout.addWidget(options_box, 1)

        workflow_box = QGroupBox("Workflow Controls")
        workflow_layout = QVBoxLayout(workflow_box)
        workflow_layout.setContentsMargins(8, 12, 8, 8)
        workflow_layout.setSpacing(7)
        hint = QLabel("Recommended sequence: Input Files → Output Folder → Inspect Source → Start Conversion → Validate Output.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #536275; background: #eef7fc; border: 1px solid #cce6f3; border-radius: 7px; padding: 6px;")
        workflow_layout.addWidget(hint)
        self.run_btn = QPushButton("Start Conversion")
        self.run_btn.setObjectName("SuccessButton")
        self.run_btn.clicked.connect(self.start_conversion)
        workflow_layout.addWidget(self.run_btn)
        self.cancel_btn = QPushButton("Cancel Conversion")
        self.cancel_btn.setObjectName("DangerButton")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_conversion)
        workflow_layout.addWidget(self.cancel_btn)
        workflow_layout.addStretch(1)
        settings_layout.addWidget(workflow_box, 1)
        tabs.addTab(make_scroll(settings_tab), "3  Settings / Run")

        # Tab 4: QA and source validation table. Separated from input/output to remove crowding.
        qa_tab = QWidget()
        qa_layout = QVBoxLayout(qa_tab)
        qa_layout.setContentsMargins(10, 10, 10, 10)
        qa_layout.setSpacing(7)
        preview_box = QGroupBox("Source / Validation Details")
        preview_layout = QVBoxLayout(preview_box)
        preview_layout.setContentsMargins(8, 11, 8, 8)
        preview_layout.setSpacing(6)
        self.info_table = QTableWidget(0, 2)
        self.info_table.setMinimumHeight(220)
        self.info_table.setHorizontalHeaderLabels(["Property", "Value"])
        self.info_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.info_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.info_table.verticalHeader().setVisible(False)
        self.info_table.verticalHeader().setDefaultSectionSize(21)
        self.info_table.setAlternatingRowColors(True)
        preview_layout.addWidget(self.info_table, 1)
        preview_btns = QHBoxLayout()
        preview_btns.setSpacing(6)
        self.inspect_btn = QPushButton("Inspect Source")
        self.inspect_btn.setObjectName("PrimaryButton")
        self.inspect_btn.clicked.connect(self.inspect_sources)
        preview_btns.addWidget(self.inspect_btn)
        validate_now = QPushButton("Validate Output")
        validate_now.clicked.connect(self.validate_output)
        preview_btns.addWidget(validate_now)
        open_out_qa = QPushButton("Open Last Output")
        open_out_qa.clicked.connect(self.open_last_output)
        preview_btns.addWidget(open_out_qa)
        preview_layout.addLayout(preview_btns)
        qa_layout.addWidget(preview_box, 1)
        tabs.addTab(make_scroll(qa_tab), "4  QA / Validation")

        # Tab 5: log, full-width and not squeezed under the input pane.
        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)
        log_layout.setContentsMargins(10, 10, 10, 10)
        log_layout.setSpacing(7)
        log_box = QGroupBox("Conversion Log")
        log_box_layout = QVBoxLayout(log_box)
        log_box_layout.setContentsMargins(8, 11, 8, 8)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(230)
        log_box_layout.addWidget(self.log)
        log_layout.addWidget(log_box, 1)
        tabs.addTab(make_scroll(log_tab), "5  Log")

        bottom = QFrame()
        bottom.setObjectName("MetricCard")
        bottom.setMaximumHeight(54)
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(8, 5, 8, 5)
        bottom_layout.setSpacing(3)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        bottom_layout.addWidget(self.progress)
        self.status = QLabel("Ready")
        self.status.setStyleSheet("color: #33445f; font-size: 8pt; font-weight: 700; background: transparent;")
        bottom_layout.addWidget(self.status)
        root.addWidget(bottom)

    def _metric_card(self, parent_layout: QHBoxLayout, caption: str, value: str) -> QLabel:
        card = QFrame()
        card.setObjectName("MetricCard")
        card.setMaximumHeight(52)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(1)
        cap = QLabel(caption)
        cap.setObjectName("MetricCaption")
        val = QLabel(value)
        val.setObjectName("MetricValue")
        val.setWordWrap(False)
        layout.addWidget(cap)
        layout.addWidget(val)
        parent_layout.addWidget(card, 1)
        return val

    def _refresh_summary_cards(self) -> None:
        if hasattr(self, "file_count_value"):
            self.file_count_value.setText(str(len(self._files)))
        if hasattr(self, "output_dir_value"):
            if self._output_dir is None:
                self.output_dir_value.setText("Not selected")
            else:
                text = str(self._output_dir)
                self.output_dir_value.setText(text if len(text) <= 34 else "…" + text[-33:])
        if hasattr(self, "last_output_value"):
            if self._last_outputs:
                text = self._last_outputs[-1].name
                self.last_output_value.setText(text if len(text) <= 32 else text[:29] + "…")
            else:
                self.last_output_value.setText("None")

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

    def _set_info(self, items: dict) -> None:
        self.info_table.setRowCount(0)
        for key, value in items.items():
            row = self.info_table.rowCount()
            self.info_table.insertRow(row)
            self.info_table.setItem(row, 0, QTableWidgetItem(str(key).replace("_", " ").title()))
            if isinstance(value, (list, tuple)):
                value = ", ".join(map(str, value))
            self.info_table.setItem(row, 1, QTableWidgetItem(str(value)))

    def inspect_sources(self) -> None:
        if not self._files:
            QMessageBox.information(self, "SEG-Y Converter", "Add at least one SEG-Y file first.")
            return
        try:
            info = self._converter.inspect_source(self._files[0])
            self._set_info(info)
            self._append_log(f"Inspected: {self._files[0].name}")
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
        self._last_outputs = []
        stop_event = threading.Event()
        self._stop_event = stop_event
        files = list(self._files)
        output_dir = Path(self._output_dir)
        options = self._options()

        def worker() -> None:
            reports = []
            errors = []
            total = len(files)
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
        self.progress.setValue(max(0, min(100, int(value))))
        self.status.setText(message)
        if hasattr(self, "state_value"):
            self.state_value.setText(f"{max(0, min(100, int(value)))}%")

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
