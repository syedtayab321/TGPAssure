from __future__ import annotations
from dataclasses import dataclass
from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QProgressBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

@dataclass
class ProcessStage:
    name: str
    state: str = "Queued"
    duration: str = "-"

class ProcessWindow(QDialog):
    cancelled = Signal()
    paused = Signal(bool)
    states = {"Completed": ("o", "#107C10"), "Running": ("o", "#0078D4"), "Queued": ("o", "#8A8A8A"), "Warning": ("o", "#CA5010"), "Failed": ("x", "#D13438")}
    def __init__(self, title: str = "Processing", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(560, 380)
        self._paused = False
        layout = QVBoxLayout(self)
        self.progress_label = QLabel("Overall Progress: 0%")
        layout.addWidget(self.progress_label)
        self.progress = QProgressBar(self)
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)
        self.eta_label = QLabel("Estimated time remaining: calculating...")
        layout.addWidget(self.eta_label)
        self.stages = QTreeWidget(self)
        self.stages.setHeaderLabels(["Stage", "Duration", "Status"])
        layout.addWidget(self.stages, 1)
        self.operation_label = QLabel("Current operation: waiting")
        self.details_label = QLabel("")
        self.details_label.setWordWrap(True)
        layout.addWidget(self.operation_label)
        layout.addWidget(self.details_label)
        controls = QHBoxLayout()
        self.cancel_button = QPushButton("Cancel", self)
        self.pause_button = QPushButton("Pause", self)
        self.details_button = QPushButton("Hide Details", self)
        self.cancel_button.clicked.connect(self.cancelled)
        self.pause_button.clicked.connect(self._toggle_pause)
        self.details_button.clicked.connect(self._toggle_details)
        controls.addWidget(self.cancel_button)
        controls.addWidget(self.pause_button)
        controls.addStretch()
        controls.addWidget(self.details_button)
        layout.addLayout(controls)
    def set_stages(self, stages: list[ProcessStage]) -> None:
        self.stages.clear()
        for stage in stages:
            item = QTreeWidgetItem([stage.name, stage.duration, stage.state])
            symbol, colour = self.states.get(stage.state, self.states["Queued"])
            item.setText(0, f"{symbol}  {stage.name}")
            item.setForeground(0, QBrush(QColor(colour)))
            item.setToolTip(0, stage.state)
            self.stages.addTopLevelItem(item)
    def update_progress(self, value: int, operation: str, details: str = "", eta: str = "calculating...") -> None:
        value = max(0, min(100, int(value)))
        self.progress.setValue(value)
        self.progress_label.setText(f"Overall Progress: {value}%")
        self.operation_label.setText(f"Current operation: {operation}")
        self.details_label.setText(details)
        self.eta_label.setText(f"Estimated time remaining: {eta}")
    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        self.pause_button.setText("Resume" if self._paused else "Pause")
        self.paused.emit(self._paused)
    def _toggle_details(self) -> None:
        visible = not self.details_label.isVisible()
        self.details_label.setVisible(visible)
        self.details_button.setText("Hide Details" if visible else "Show Details")
