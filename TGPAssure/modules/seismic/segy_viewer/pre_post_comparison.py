from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from modules.seismic.segy_viewer.segy_viewer_widget import SegyViewerWidget


class SegyPrePostComparison(QWidget):
    """Side-by-side raw/post-QC SEG-Y review with synchronized navigation.

    The comparison deliberately uses the production SEG-Y viewer on both sides so
    sample timing, variable trace lengths, endian handling and display behavior
    remain identical to single-file review. No samples are resampled merely for
    the sake of visual comparison; each viewer retains its own physical time grid.
    """

    def __init__(
        self,
        raw_path: str | Path,
        post_path: str | Path,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("module_id", "segy_qc")
        self.raw_path = Path(raw_path).expanduser().resolve()
        self.post_path = Path(post_path).expanduser().resolve()
        self._sync_guard = False
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame(self)
        header.setObjectName("segyComparisonHeader")
        header.setStyleSheet(
            "QFrame#segyComparisonHeader{background:#f5f7fa;border-bottom:1px solid #d8e0e7;}"
        )
        row = QHBoxLayout(header)
        row.setContentsMargins(10, 6, 10, 6)
        title = QLabel("SEG-Y QC — Raw vs Post-QC Comparison")
        title.setStyleSheet("font-size:14px;font-weight:800;color:#18384f;")
        self.sync_navigation = QCheckBox("Synchronize navigation")
        self.sync_navigation.setChecked(True)
        fit_both = QPushButton("Fit Both")
        fit_both.clicked.connect(self.fit_both)
        row.addWidget(title)
        row.addStretch(1)
        row.addWidget(self.sync_navigation)
        row.addWidget(fit_both)
        root.addWidget(header)

        labels = QFrame(self)
        labels_row = QHBoxLayout(labels)
        labels_row.setContentsMargins(8, 4, 8, 4)
        raw_label = QLabel(f"RAW / PRE-QC  —  {self.raw_path.name}")
        post_label = QLabel(f"PROCESSED / POST-QC  —  {self.post_path.name}")
        raw_label.setStyleSheet("font-weight:700;color:#334155;")
        post_label.setStyleSheet("font-weight:700;color:#334155;")
        labels_row.addWidget(raw_label, 1)
        labels_row.addWidget(post_label, 1)
        root.addWidget(labels)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.raw_viewer = SegyViewerWidget(self.raw_path, splitter)
        self.post_viewer = SegyViewerWidget(self.post_path, splitter)
        splitter.addWidget(self.raw_viewer)
        splitter.addWidget(self.post_viewer)
        splitter.setSizes([1, 1])
        root.addWidget(splitter, 1)

        self.raw_viewer.canvas.window_changed.connect(self._sync_from_raw)
        self.post_viewer.canvas.window_changed.connect(self._sync_from_post)

    def _sync_from_raw(self, t0: int, t1: int, s0: int, s1: int) -> None:
        if not self.sync_navigation.isChecked() or self._sync_guard:
            return
        self._sync_guard = True
        try:
            self._set_equivalent_window(self.raw_viewer, self.post_viewer, t0, t1, s0, s1)
        finally:
            self._sync_guard = False

    def _sync_from_post(self, t0: int, t1: int, s0: int, s1: int) -> None:
        if not self.sync_navigation.isChecked() or self._sync_guard:
            return
        self._sync_guard = True
        try:
            self._set_equivalent_window(self.post_viewer, self.raw_viewer, t0, t1, s0, s1)
        finally:
            self._sync_guard = False

    @staticmethod
    def _set_equivalent_window(
        source: SegyViewerWidget,
        target: SegyViewerWidget,
        t0: int,
        t1: int,
        s0: int,
        s1: int,
    ) -> None:
        """Synchronize by physical time rather than blindly copying sample indices."""
        source_grid = source.time_grid
        target_grid = target.time_grid
        if source_grid is None or target_grid is None:
            target.set_window(t0, t1, s0, s1)
            return
        start_ms = source_grid.start_ms + int(s0) * source_grid.interval_ms
        end_ms = source_grid.start_ms + int(s1) * source_grid.interval_ms
        target_s0 = int(round((start_ms - target_grid.start_ms) / target_grid.interval_ms))
        target_s1 = int(round((end_ms - target_grid.start_ms) / target_grid.interval_ms))
        target.set_window(t0, t1, target_s0, target_s1)

    def fit_both(self) -> None:
        self.raw_viewer.fit()
        self.post_viewer.fit()
