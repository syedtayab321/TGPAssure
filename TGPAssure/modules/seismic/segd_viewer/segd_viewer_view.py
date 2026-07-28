from __future__ import annotations

from typing import Optional, Dict, Any
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QPushButton, QLabel

from core.infrastructure.service_container import ServiceContainer
from core.infrastructure.job_manager import JobManager
from core.data_access.db_engine import DatabaseEngine
from modules.seismic.segd_viewer.segd_reader import SegdReader
from modules.seismic.segd_viewer.trace_window_loader import TraceWindowLoader
from modules.seismic.segd_viewer.segd_canvas import SegdCanvas
from modules.seismic.segd_viewer.configuration_panel import ConfigurationPanel
from modules.seismic.segd_viewer.header_viewer import HeaderViewer
from modules.seismic.segd_viewer.picking_tool import PickingTool


class SegdViewerView(QWidget):
    def __init__(self, container: ServiceContainer, file_path: Optional[Path] = None) -> None:
        super().__init__()
        self._container = container
        self._job_manager = container.resolve(JobManager)
        self._db_engine = container.resolve(DatabaseEngine)
        self._file_path = file_path
        self._loader: Optional[TraceWindowLoader] = None
        self._reader: Optional[SegdReader] = None
        self._picking_tool = PickingTool(self._db_engine)

        self.setup_ui()

        if file_path:
            self.load_file(file_path)

    def setup_ui(self) -> None:
        self.setObjectName("segdViewer")
        self.setStyleSheet("""
            QWidget#segdViewer { background:#EDF4F8; }
            QWidget#segdToolbar { background:#123B5D; border-bottom:1px solid #0C2B43; }
            QWidget#segdToolbar QLabel { color:#EAF4FC; font-size:10px; }
            QWidget#segdToolbar QPushButton { background:#1C527C; color:white; border:1px solid #39749B; border-radius:3px; padding:4px 9px; font-size:9px; }
            QWidget#segdToolbar QPushButton:hover { background:#28709F; }
            QGraphicsView { background:#101820; border:1px solid #284A63; }
        """)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        toolbar_frame = QWidget()
        toolbar_frame.setObjectName("segdToolbar")
        toolbar = QHBoxLayout(toolbar_frame)
        toolbar.setContentsMargins(8, 4, 8, 4)

        self.mode_combo = QPushButton("Pan")
        self.mode_combo.setCheckable(True)
        self.mode_combo.setChecked(True)
        self.mode_combo.clicked.connect(lambda: self._set_mode(SegdCanvas.MODE_PAN))
        toolbar.addWidget(self.mode_combo)

        select_btn = QPushButton("Select")
        select_btn.clicked.connect(lambda: self._set_mode(SegdCanvas.MODE_SELECT))
        toolbar.addWidget(select_btn)

        pick_btn = QPushButton("Pick")
        pick_btn.clicked.connect(lambda: self._set_mode(SegdCanvas.MODE_PICK))
        toolbar.addWidget(pick_btn)

        measure_btn = QPushButton("Measure")
        measure_btn.clicked.connect(lambda: self._set_mode(SegdCanvas.MODE_MEASURE))
        toolbar.addWidget(measure_btn)

        toolbar.addStretch()

        fit_btn = QPushButton("Fit to View")
        fit_btn.clicked.connect(self._zoom_to_fit)
        toolbar.addWidget(fit_btn)

        self.status_label = QLabel("Ready")
        toolbar.addWidget(self.status_label)

        main_layout.addWidget(toolbar_frame)

        splitter = QSplitter(Qt.Horizontal)

        left_splitter = QSplitter(Qt.Vertical)

        self.canvas = SegdCanvas()
        self.canvas.pick_created.connect(self._on_pick_created)
        self.canvas.measurement_updated.connect(self._on_measurement_updated)
        left_splitter.addWidget(self.canvas)

        self.header_viewer = HeaderViewer()
        left_splitter.addWidget(self.header_viewer)
        left_splitter.setSizes([600, 200])

        splitter.addWidget(left_splitter)

        self.config_panel = ConfigurationPanel()
        self.config_panel.config_changed.connect(self._on_config_changed)
        splitter.addWidget(self.config_panel)

        splitter.setSizes([800, 300])

        main_layout.addWidget(splitter)

    def load_file(self, file_path: Path) -> None:
        self._file_path = file_path
        self._reader = SegdReader(file_path)
        self._loader = TraceWindowLoader(file_path, memory_budget_mb=512)
        self.canvas.initialize(self._loader, self._job_manager)
        self.header_viewer.set_reader(self._reader)
        self.config_panel.set_channel_count(self._loader.get_channel_count())
        self._zoom_to_fit()

    def _set_mode(self, mode: str) -> None:
        self.canvas.set_mode(mode)
        self.mode_combo.setText(mode.capitalize())

    def _zoom_to_fit(self) -> None:
        self.canvas.zoom_to_fit()

    def _on_pick_created(self, pick_data: Dict[str, Any]) -> None:
        pick_id = self._picking_tool.create_pick(pick_data)
        self.status_label.setText(f"Pick created: {pick_id[:8]}")

    def _on_measurement_updated(self, time_delta: float, amplitude_delta: float) -> None:
        self.status_label.setText(f"dt: {abs(time_delta):.2f} ms, da: {abs(amplitude_delta):.2f}")

    def _on_config_changed(self) -> None:
        config = self.config_panel.get_config()
        self.canvas.set_colormap(config["colormap"])
        self.canvas.set_display_mode(config["display_mode"])
        self.canvas.set_gain_mode(config["gain_mode"], config["gain_params"])
        self.canvas.set_clip_percentile(config["clip_percentile"])
        self.canvas.set_selected_channels(config["channels"])
