from __future__ import annotations

from typing import Optional
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSplitter, QPushButton, QFrame
)

from modules.seismic.segd_viewer.segd_canvas import SegdCanvas
from modules.seismic.segd_viewer.configuration_panel import ConfigurationPanel
from modules.seismic.segd_viewer.header_viewer import HeaderViewer


class SegdViewerEnhanced(QWidget):
    def __init__(self, container, file_path: Optional[Path] = None):
        super().__init__()
        self._container = container
        self._file_path = file_path
        self.setup_ui()

    def setup_ui(self):
        self.setObjectName('segdViewerEnhanced')
        self.setStyleSheet('''
            QWidget#segdViewerEnhanced { background:#EDF4F8; }
            QFrame#segdHeader { background:#123B5D; }
            QFrame#segdHeader QLabel { color:white; font-size:12px; font-weight:600; }
            QFrame#segdHeader QPushButton { background:#1C527C; color:white; border:1px solid #39749B; border-radius:3px; padding:4px 10px; }
            QGraphicsView { background:#101820; border:1px solid #284A63; }
        ''')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QFrame()
        header.setObjectName('segdHeader')
        top = QHBoxLayout(header)
        title = QLabel('SEG-D Viewer')
        title.setStyleSheet('padding:4px')
        top.addWidget(title)
        top.addStretch()
        open_btn = QPushButton('Open File')
        open_btn.clicked.connect(self._open_file)
        top.addWidget(open_btn)
        layout.addWidget(header)

        splitter = QSplitter(Qt.Horizontal)
        self.canvas = SegdCanvas()
        splitter.addWidget(self.canvas)

        right_panel = QFrame()
        right_layout = QVBoxLayout(right_panel)
        self.config = ConfigurationPanel()
        self.header = HeaderViewer()
        right_layout.addWidget(self.config)
        right_layout.addWidget(self.header)
        splitter.addWidget(right_panel)

        layout.addWidget(splitter)

    def _open_file(self):
        from PySide6.QtWidgets import QFileDialog
        file, _ = QFileDialog.getOpenFileName(self, 'Open SEG-D File', str(Path.home()), 'SEG-D Files (*.segd);;All Files (*.*)')
        if file:
            try:
                reader = None
                loader = None
                from modules.seismic.segd_viewer.segd_reader import SegdReader
                from modules.seismic.segd_viewer.trace_window_loader import TraceWindowLoader
                from core.infrastructure.job_manager import JobManager
                from core.data_access.db_engine import DatabaseEngine
                jm = self._container.resolve(JobManager)
                db = self._container.resolve(DatabaseEngine)
                reader = SegdReader(Path(file))
                loader = TraceWindowLoader(Path(file), memory_budget_mb=256)
                self.canvas.initialize(loader, jm)
                self.header.set_reader(reader)
            except Exception as e:
                print('Failed to open file', e)
