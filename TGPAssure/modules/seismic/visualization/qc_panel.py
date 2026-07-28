from __future__ import annotations

from typing import Iterable

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from modules.seismic.visualization.models import QcTraceFlag, SectionData
from modules.seismic.visualization.processing import calculate_noise_metrics, calculate_spectrum


class SeismicQcPanel(QWidget):
    trace_selected = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._section: SectionData | None = None
        self._flags: list[QcTraceFlag] = []
        self._geometry: dict[str, np.ndarray] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.spectrum_plot = pg.PlotWidget(background="#08131D")
        self.spectrum_plot.setLabel("bottom", "Frequency", units="Hz")
        self.spectrum_plot.setLabel("left", "Amplitude")
        self.spectrum_plot.showGrid(x=True, y=True, alpha=0.2)
        self.spectrum_plot.addLegend(offset=(10, 10))
        self.tabs.addTab(self.spectrum_plot, "Amplitude Spectrum")

        self.noise_plot = pg.PlotWidget(background="#08131D")
        self.noise_plot.setLabel("bottom", "Trace index")
        self.noise_plot.setLabel("left", "Normalized metric")
        self.noise_plot.showGrid(x=True, y=True, alpha=0.2)
        self.noise_plot.addLegend(offset=(10, 10))
        self.tabs.addTab(self.noise_plot, "Noise Analysis")

        self.geometry_plot = pg.PlotWidget(background="#08131D")
        self.geometry_plot.setLabel("bottom", "X")
        self.geometry_plot.setLabel("left", "Y")
        self.geometry_plot.showGrid(x=True, y=True, alpha=0.2)
        self.geometry_plot.setAspectLocked(False)
        self.geometry_plot.addLegend(offset=(10, 10))
        self.tabs.addTab(self.geometry_plot, "Geometry QC")

        self.flags_table = QTableWidget(0, 5)
        self.flags_table.setHorizontalHeaderLabels(["Trace", "Severity", "Reason", "RMS", "Source"])
        self.flags_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.flags_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.flags_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.flags_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.flags_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.flags_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.flags_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.flags_table.cellDoubleClicked.connect(self._on_flag_double_clicked)
        self.tabs.addTab(self.flags_table, "Flagged Traces")

    def set_section(self, section: SectionData) -> None:
        self._section = section
        self._update_spectrum()
        self._update_noise()

    def set_flags(self, flags: Iterable[QcTraceFlag]) -> None:
        self._flags = list(flags)
        self._update_flag_table()
        self._update_geometry()

    def set_geometry(self, geometry: dict[str, np.ndarray]) -> None:
        self._geometry = geometry
        self._update_geometry()

    def _update_spectrum(self) -> None:
        self.spectrum_plot.clear()
        section = self._section
        if section is None or section.amplitudes.size == 0:
            return
        result = calculate_spectrum(section.amplitudes, section.sample_interval_ms)
        if result.frequency_hz.size == 0:
            return
        self.spectrum_plot.plot(
            result.frequency_hz,
            result.mean_amplitude,
            pen=pg.mkPen("#00B7D9", width=1.6),
            name="Mean",
        )
        self.spectrum_plot.plot(
            result.frequency_hz,
            result.median_amplitude,
            pen=pg.mkPen("#FFD54F", width=1.2),
            name="Median",
        )

    def _update_noise(self) -> None:
        self.noise_plot.clear()
        section = self._section
        if section is None or section.amplitudes.size == 0:
            return
        result = calculate_noise_metrics(
            section.amplitudes,
            section.trace_indices,
            section.sample_interval_ms,
        )
        if result.trace_indices.size == 0:
            return
        normalized_rms = result.rms / max(float(np.median(result.rms[result.rms > 0])) if np.any(result.rms > 0) else 1.0, 1e-12)
        self.noise_plot.plot(
            result.trace_indices,
            normalized_rms,
            pen=pg.mkPen("#00B7D9", width=1.4),
            name="RMS / median",
        )
        self.noise_plot.plot(
            result.trace_indices,
            result.high_frequency_ratio,
            pen=pg.mkPen("#FF9E64", width=1.3),
            name="High-frequency ratio",
        )
        self.noise_plot.plot(
            result.trace_indices,
            result.incoherence,
            pen=pg.mkPen("#D875FF", width=1.3),
            name="Incoherence",
        )

    def _update_geometry(self) -> None:
        self.geometry_plot.clear()
        if not self._geometry:
            return
        source_x = np.asarray(self._geometry.get("source_x", []), dtype=np.float64)
        source_y = np.asarray(self._geometry.get("source_y", []), dtype=np.float64)
        receiver_x = np.asarray(self._geometry.get("receiver_x", []), dtype=np.float64)
        receiver_y = np.asarray(self._geometry.get("receiver_y", []), dtype=np.float64)
        midpoint_x = np.asarray(self._geometry.get("midpoint_x", []), dtype=np.float64)
        midpoint_y = np.asarray(self._geometry.get("midpoint_y", []), dtype=np.float64)
        trace_indices = np.asarray(self._geometry.get("trace_indices", []), dtype=np.int64)
        if source_x.size:
            self.geometry_plot.plot(
                source_x,
                source_y,
                pen=None,
                symbol="t",
                symbolSize=4,
                symbolBrush="#FF9E64",
                symbolPen=None,
                name="Source",
            )
        if receiver_x.size:
            self.geometry_plot.plot(
                receiver_x,
                receiver_y,
                pen=None,
                symbol="o",
                symbolSize=3,
                symbolBrush="#00B7D9",
                symbolPen=None,
                name="Receiver",
            )
        if midpoint_x.size:
            self.geometry_plot.plot(
                midpoint_x,
                midpoint_y,
                pen=None,
                symbol="s",
                symbolSize=3,
                symbolBrush="#8BD450",
                symbolPen=None,
                name="Midpoint/CDP",
            )
        bad_trace_set = {int(flag.trace_index) for flag in self._flags}
        if bad_trace_set and trace_indices.size:
            mask = np.asarray([int(value) in bad_trace_set for value in trace_indices], dtype=bool)
            if np.any(mask):
                self.geometry_plot.plot(
                    midpoint_x[mask],
                    midpoint_y[mask],
                    pen=None,
                    symbol="x",
                    symbolSize=9,
                    symbolBrush="#FF4949",
                    symbolPen=pg.mkPen("#FF4949", width=2),
                    name="Bad trace",
                )

    def _update_flag_table(self) -> None:
        self.flags_table.setRowCount(len(self._flags))
        for row, flag in enumerate(self._flags):
            values = [
                str(flag.trace_index + 1),
                flag.severity,
                flag.reason,
                f"{flag.rms:.5g}",
                flag.source,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(256, flag.trace_index)
                self.flags_table.setItem(row, column, item)

    def _on_flag_double_clicked(self, row: int, _column: int) -> None:
        item = self.flags_table.item(row, 0)
        if item is not None:
            self.trace_selected.emit(int(item.data(256)))
