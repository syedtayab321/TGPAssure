from __future__ import annotations

from pathlib import Path
from typing import List
import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget, QFileDialog,
    QProgressBar, QSpinBox, QDoubleSpinBox
)

from modules.seismic.converter.segy_to_segd import SegyToSegdConverter


class SegyToSegdDialog(QDialog):
    progress_signal = Signal(int)
    log_signal = Signal(str)
    finished_signal = Signal()
    running_signal = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Convert SEG-Y to SEG-D')
        self.resize(600, 400)
        self._files: List[Path] = []
        self._setup_ui()

        self.progress_signal.connect(self._update_progress)
        self.log_signal.connect(self._emit_parent_log)
        self.finished_signal.connect(self._on_finished)
        self.running_signal.connect(self._set_running)
        self._success_count = 0
        self._error_count = 0
        self._busy_task_id = f"segy-convert:{id(self)}"
        self._running = False

    def _emit_parent_log(self, text: str) -> None:
        parent = self.parent()
        if parent and hasattr(parent, 'log'):
            parent.log(text)

    def _set_running(self, running: bool) -> None:
        self._running = bool(running)
        self.run_btn.setEnabled(not running)
        self.cancel_btn.setEnabled(running)

    def _update_progress(self, value: int) -> None:
        self.progress.setValue(value)
        parent = self.parent()
        if parent and hasattr(parent, "update_busy_task"):
            parent.update_busy_task(
                self._busy_task_id,
                value,
                f"Converting SEG-Y to validated SEG-D 8058 — {value}%",
            )

    def _on_finished(self) -> None:
        self._set_running(False)
        parent = self.parent()
        if parent and hasattr(parent, "end_busy_task"):
            parent.end_busy_task(self._busy_task_id)
        from PySide6.QtWidgets import QMessageBox
        if self._error_count:
            QMessageBox.warning(
                self,
                "Conversion Complete",
                f"Completed: {self._success_count}\nFailed: {self._error_count}\n\nSee the application log for details.",
            )
        elif self._success_count:
            QMessageBox.information(
                self,
                "Conversion Complete",
                f"Successfully converted {self._success_count} SEG-Y file(s) to validated SEG-D 8058.",
            )

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel('Sample rate (Hz):'))
        self.sample_spin = QSpinBox()
        self.sample_spin.setRange(1, 20000)
        self.sample_spin.setValue(1000)
        top.addWidget(self.sample_spin)
        top.addWidget(QLabel('Scale:'))
        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(0.01, 100.0)
        self.scale_spin.setSingleStep(0.1)
        self.scale_spin.setValue(1.0)
        top.addWidget(self.scale_spin)
        layout.addLayout(top)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        btns = QHBoxLayout()
        add_btn = QPushButton('Add SEG-Y')
        add_btn.clicked.connect(self._add_files)
        btns.addWidget(add_btn)
        out_btn = QPushButton('Select Output Dir')
        out_btn.clicked.connect(self._choose_out_dir)
        btns.addWidget(out_btn)
        self.run_btn = QPushButton('Start Conversion')
        self.run_btn.clicked.connect(self._start)
        btns.addWidget(self.run_btn)
        self.cancel_btn = QPushButton('Cancel')
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        btns.addWidget(self.cancel_btn)
        layout.addLayout(btns)

        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        self._out_dir = None
        self._stop_event = None

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, 'Select SEG-Y files', str(Path.home()), 'SEG-Y Files (*.sgy *.segy);;All Files (*.*)')
        for f in files:
            p = Path(f)
            if p not in self._files:
                self._files.append(p)
                self.list_widget.addItem(str(p))

    def _choose_out_dir(self):
        d = QFileDialog.getExistingDirectory(self, 'Select output directory', str(Path.home()))
        if d:
            self._out_dir = Path(d)

    def _start(self):
        if not self._files:
            return
        if not self._out_dir:
            return
        self._success_count = 0
        self._error_count = 0
        files = list(self._files)
        output_dir = Path(self._out_dir)
        sample_rate = int(self.sample_spin.value())
        scale = float(self.scale_spin.value())
        stop_event = threading.Event()
        self._stop_event = stop_event
        self.running_signal.emit(True)
        parent = self.parent()
        if parent and hasattr(parent, "begin_busy_task"):
            parent.begin_busy_task(
                self._busy_task_id,
                "Converting SEG-Y to SEG-D",
                "Preparing conversion and validating output",
                0,
                cancel_callback=self._cancel,
            )

        def worker():
            conv = SegyToSegdConverter()
            total = len(files)
            completed = 0
            for p in files:
                current_name = p.name

                def progress_cb(frac, remaining, name=current_name, completed_local=completed):
                    overall = int((completed_local + frac) / total * 100)
                    self.progress_signal.emit(overall)
                    self.log_signal.emit(f'Converting {name}: {int(frac*100)}%')

                try:
                    self.log_signal.emit(f'Starting: {p.name}')
                    conv.convert(p, output_dir / (p.stem + '.segd'), sample_rate=sample_rate, scale=scale, progress_callback=progress_cb, stop_event=stop_event)
                    if stop_event.is_set():
                        self.log_signal.emit(f'Cancelled: {p.name}')
                        break
                    completed += 1
                    self._success_count += 1
                    self.progress_signal.emit(int(completed / total * 100))
                    self.log_signal.emit(f'Completed: {p.name} -> {output_dir / (p.stem + ".segd")}')
                except InterruptedError:
                    self.log_signal.emit(f'Cancelled: {p.name}')
                    break
                except Exception as e:
                    self._error_count += 1
                    self.log_signal.emit(f'Error converting {p.name}: {e}')

            self.finished_signal.emit()
        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def reject(self) -> None:
        if self._running:
            from PySide6.QtWidgets import QMessageBox
            answer = QMessageBox.question(
                self,
                "Conversion Running",
                "A conversion is still running. Cancel it and close this dialog?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
            if self._stop_event is not None:
                self._stop_event.set()
        super().reject()

    def _cancel(self):
        if not self._stop_event:
            return
        from PySide6.QtWidgets import QMessageBox
        resp = QMessageBox.question(self, 'Cancel Conversions', 'Are you sure you want to cancel running conversions?', QMessageBox.Yes | QMessageBox.No)
        if resp == QMessageBox.Yes:
            self._stop_event.set()
            self.log_signal.emit('Conversion cancellation requested')
