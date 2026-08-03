from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping

import numpy as np
import pyqtgraph as pg
from scipy import signal
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QFileDialog,
    QFrame,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QComboBox,
    QTabWidget,
    QWidget,
    QMessageBox,
)


_DIALOG_QSS = """
QDialog#vibResultsDialog {
    background:#F3F7FA;
    color:#102A3D;
    font-size:8pt;
}
QFrame#vibDialogHeader {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #07263A, stop:.55 #0B5673, stop:1 #1096B5);
    border:0;
    border-radius:8px;
}
QLabel#vibDialogTitle {
    color:#FFFFFF;
    font-size:13pt;
    font-weight:900;
}
QLabel#vibDialogSubtitle {
    color:#D6F2FA;
    font-size:8pt;
    font-weight:700;
}
QFrame#vibMetricCard {
    background:#FFFFFF;
    border:1px solid #D2DEE8;
    border-radius:8px;
}
QLabel#vibMetricTitle {
    color:#557084;
    font-size:7.2pt;
    font-weight:900;
}
QLabel#vibMetricValue {
    color:#06243A;
    font-size:12pt;
    font-weight:900;
}
QTableWidget {
    background:#FFFFFF;
    alternate-background-color:#F7FAFC;
    border:1px solid #D7E2EB;
    gridline-color:#E7EDF2;
    selection-background-color:#D7EBF8;
    selection-color:#092C40;
    font-size:7.8pt;
}
QHeaderView::section {
    background:#E7F0F6;
    color:#29495E;
    border:0;
    border-right:1px solid #D7E2EB;
    border-bottom:1px solid #CAD8E3;
    padding:4px;
    font-weight:900;
}
QPushButton {
    min-height:26px;
    padding:3px 12px;
    border:1px solid #B8C7D3;
    border-radius:6px;
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #FFFFFF, stop:1 #EDF3F8);
    color:#102A3D;
    font-weight:800;
}
QPushButton:hover { border-color:#0A86C7; background:#F2F9FD; }
QPushButton#vibPrimary {
    background:#0A86C7;
    border-color:#0873AB;
    color:#FFFFFF;
    font-weight:900;
}
QPushButton#vibGreen {
    background:#15945C;
    border-color:#117849;
    color:#FFFFFF;
    font-weight:900;
}
QTabWidget::pane { border:1px solid #D2DFE9; background:#FFFFFF; }
QTabWidget QTabBar::tab {
    background:#E9F1F6;
    color:#2E5368;
    border:1px solid #D2DFE9;
    padding:5px 12px;
    min-height:20px;
    font-weight:800;
}
QTabWidget QTabBar::tab:selected {
    background:#FFFFFF;
    color:#0879A8;
    border-top:2px solid #0A92C4;
    border-bottom-color:#FFFFFF;
    font-weight:900;
}
"""


class _BaseVibroseisResultsDialog(QDialog):
    def __init__(self, title: str, subtitle: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("vibResultsDialog")
        self.setStyleSheet(_DIALOG_QSS)
        self.setWindowTitle(title)
        self.resize(1120, 720)
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        header = QFrame(self)
        header.setObjectName("vibDialogHeader")
        h = QVBoxLayout(header)
        h.setContentsMargins(14, 8, 14, 8)
        h.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("vibDialogTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("vibDialogSubtitle")
        subtitle_label.setWordWrap(True)
        h.addWidget(title_label)
        h.addWidget(subtitle_label)
        root.addWidget(header)

        self.metric_grid = QGridLayout()
        self.metric_grid.setSpacing(8)
        root.addLayout(self.metric_grid)

        self.tabs = QTabWidget(self)
        root.addWidget(self.tabs, 1)

        footer = QHBoxLayout()
        palette_label = QLabel("Colour palette")
        palette_label.setStyleSheet("color:#17384F;font-weight:900;background:transparent;")
        self.palette_combo = QComboBox()
        self.palette_combo.addItem("TGP Blue / Amber", ["#0A6EA8", "#D98919", "#15945C", "#AA3377", "#D7191C", "#7B61FF"])
        self.palette_combo.addItem("High Contrast", ["#003F5C", "#FFA600", "#2F4B7C", "#D45087", "#665191", "#F95D6A"])
        self.palette_combo.addItem("Geophysical Field", ["#074F57", "#18A999", "#F2C14E", "#F78154", "#4D9078", "#7B2CBF"])
        self.palette_combo.addItem("Warm Presentation", ["#7A1F1F", "#C65D21", "#E0A100", "#4F772D", "#315C99", "#8A4FFF"])
        self.palette_combo.setMinimumWidth(185)
        self.palette_combo.currentIndexChanged.connect(self._apply_palette_to_plots)
        footer.addWidget(palette_label)
        footer.addWidget(self.palette_combo)
        footer.addStretch(1)
        self.export_btn = QPushButton("Export CSV")
        self.export_btn.setObjectName("vibGreen")
        self.export_btn.clicked.connect(self._export_csv)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        footer.addWidget(self.export_btn)
        footer.addWidget(close)
        root.addLayout(footer)
        self._export_rows: list[list[object]] = []


    def _palette_colors(self) -> list[str]:
        colors = self.palette_combo.currentData() if hasattr(self, "palette_combo") else None
        if isinstance(colors, list) and colors:
            return [str(c) for c in colors]
        return ["#0A6EA8", "#D98919", "#15945C", "#AA3377", "#D7191C", "#7B61FF"]

    def _palette_pen(self, index: int = 0, width: float = 1.25):
        colors = self._palette_colors()
        return pg.mkPen(colors[index % len(colors)], width=width)

    def _apply_palette_to_plots(self) -> None:
        colors = self._palette_colors()
        color_index = 0
        for plot in self.findChildren(pg.PlotWidget):
            for item in plot.listDataItems():
                try:
                    item.setPen(pg.mkPen(colors[color_index % len(colors)], width=1.25))
                    color_index += 1
                except Exception:
                    pass
            plot.repaint()

    @staticmethod
    def _style_plot(plot: pg.PlotWidget, title: str, left: str = "", bottom: str = "") -> None:
        plot.setBackground("w")
        plot.showGrid(x=True, y=True, alpha=0.22)
        plot.setTitle(title, color="#15384F", size="9pt")
        if left:
            plot.setLabel("left", left)
        if bottom:
            plot.setLabel("bottom", bottom)
        try:
            plot.getAxis("left").setWidth(58)
            plot.getAxis("left").setStyle(tickFont=QFont("Arial", 8))
            plot.getAxis("bottom").setStyle(tickFont=QFont("Arial", 8))
        except Exception:
            pass

    def _add_metric(self, title: str, value: object, row: int, col: int) -> None:
        card = QFrame(self)
        card.setObjectName("vibMetricCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(2)
        t = QLabel(str(title).upper())
        t.setObjectName("vibMetricTitle")
        v = QLabel(str(value))
        v.setObjectName("vibMetricValue")
        v.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(t)
        lay.addWidget(v)
        self.metric_grid.addWidget(card, row, col)

    @staticmethod
    def _table(headers: list[str], rows: Iterable[Iterable[object]]) -> QTableWidget:
        rows = list(rows)
        table = QTableWidget(len(rows), len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.verticalHeader().setVisible(False)
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                table.setItem(r, c, QTableWidgetItem("" if value is None else str(value)))
        table.horizontalHeader().setStretchLastSection(True)
        table.resizeRowsToContents()
        return table

    def _export_csv(self) -> None:
        if not self._export_rows:
            QMessageBox.information(self, "Export", "No result rows are available for export.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Vibroseis results", str(Path.home() / "vibroseis_results.csv"), "CSV (*.csv)")
        if not path:
            return
        output = Path(path).with_suffix(".csv")
        try:
            import csv
            with open(output, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerows(self._export_rows)
            QMessageBox.information(self, "Export Complete", f"Results exported:\n{output}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))


class SweepResultsDialog(_BaseVibroseisResultsDialog):
    def __init__(self, result, sample_rate_hz: float, parent=None) -> None:
        super().__init__(
            "Vibroseis Sweep Design Results",
            "Generated pilot sweep, normalized spectrum and Klauder wavelet. Use these outputs for pilot-file export and source planning review.",
            parent,
        )
        peak = float(np.nanmax(np.abs(result.samples))) if result.samples.size else 0.0
        rms = float(np.sqrt(np.nanmean(result.samples ** 2))) if result.samples.size else 0.0
        dom = float(result.frequency_hz[int(np.nanargmax(result.amplitude_spectrum))]) if result.amplitude_spectrum.size else 0.0
        self._add_metric("Samples", f"{result.samples.size:,}", 0, 0)
        self._add_metric("Peak amplitude", f"{peak:.6g}", 0, 1)
        self._add_metric("RMS", f"{rms:.6g}", 0, 2)
        self._add_metric("Dominant freq", f"{dom:.3f} Hz", 0, 3)

        p1 = pg.PlotWidget(); self._style_plot(p1, "Pilot Sweep", "Amplitude", "Time (s)")
        p1.plot(result.time_s, result.samples, pen=self._palette_pen(0, 1.3))
        self.tabs.addTab(p1, "Pilot")

        p2 = pg.PlotWidget(); self._style_plot(p2, "Normalized Sweep Spectrum", "Normalized amplitude", "Frequency (Hz)")
        p2.plot(result.frequency_hz, result.amplitude_spectrum, pen=self._palette_pen(2, 1.5))
        self.tabs.addTab(p2, "Spectrum")

        p3 = pg.PlotWidget(); self._style_plot(p3, "Klauder Wavelet / Autocorrelation", "Correlation", "Lag (s)")
        p3.plot(result.autocorrelation_lag_s, result.klauder_wavelet, pen=self._palette_pen(1, 1.2))
        self.tabs.addTab(p3, "Klauder")

        self._export_rows = [["time_s", "pilot_amplitude", "instantaneous_frequency_hz"]]
        self._export_rows += [[float(t), float(a), float(f)] for t, a, f in zip(result.time_s, result.samples, result.instantaneous_frequency_hz)]


class SignalQcResultsDialog(_BaseVibroseisResultsDialog):
    def __init__(self, qc_result, reference: np.ndarray, measured: np.ndarray, sample_rate_hz: float, parent=None) -> None:
        super().__init__(
            "Vibroseis Source Signal QC Results",
            "Reference and measured source signals compared by lag, RMS, amplitude ratio, band energy, coherence and phase error.",
            parent,
        )
        n = min(reference.size, measured.size)
        reference = np.nan_to_num(reference[:n].astype(float, copy=False))
        measured = np.nan_to_num(measured[:n].astype(float, copy=False))
        time_s = np.arange(n, dtype=float) / max(float(sample_rate_hz), 1.0)
        lags, corr = self._correlate(reference, measured, sample_rate_hz)
        freq, ref_spec = self._spectrum(reference, sample_rate_hz)
        _, mea_spec = self._spectrum(measured, sample_rate_hz)

        self._add_metric("Correlation", f"{qc_result.normalized_correlation:.5f}", 0, 0)
        self._add_metric("Lag", f"{qc_result.lag_ms:.3f} ms", 0, 1)
        self._add_metric("Amp ratio", f"{qc_result.amplitude_ratio_db:.3f} dB", 0, 2)
        self._add_metric("Dominant freq", f"{qc_result.dominant_frequency_hz:.3f} Hz", 0, 3)
        self._add_metric("Coherence", f"{qc_result.spectral_coherence_mean:.5f}", 1, 0)
        self._add_metric("Phase RMS", f"{qc_result.phase_error_rms_deg:.3f}°", 1, 1)
        self._add_metric("Band energy", f"{100 * qc_result.in_band_energy_fraction:.2f}%", 1, 2)
        self._add_metric("Crest factor", f"{qc_result.crest_factor:.4f}", 1, 3)

        p1 = pg.PlotWidget(); self._style_plot(p1, "Reference vs Measured Signal", "Amplitude", "Time (s)")
        p1.plot(time_s, reference, pen=self._palette_pen(0, 1.1), name="Reference")
        p1.plot(time_s, measured, pen=self._palette_pen(1, 1.1), name="Measured")
        self.tabs.addTab(p1, "Time Overlay")

        p2 = pg.PlotWidget(); self._style_plot(p2, "Normalized Cross-Correlation", "Correlation", "Lag (s)")
        p2.plot(lags, corr, pen=self._palette_pen(2, 1.3))
        p2.addLine(x=qc_result.lag_samples / max(float(sample_rate_hz), 1.0), pen=pg.mkPen("#D7191C", width=1.0, style=Qt.DashLine))
        self.tabs.addTab(p2, "Correlation")

        p3 = pg.PlotWidget(); self._style_plot(p3, "Amplitude Spectrum", "Normalized amplitude", "Frequency (Hz)")
        p3.plot(freq, ref_spec, pen=self._palette_pen(0, 1.2))
        p3.plot(freq, mea_spec, pen=self._palette_pen(3, 1.2))
        self.tabs.addTab(p3, "Spectrum")

        rows = [
            ["Normalized correlation", f"{qc_result.normalized_correlation:.5f}"],
            ["Estimated lag", f"{qc_result.lag_samples} samples / {qc_result.lag_ms:.3f} ms"],
            ["Reference RMS", f"{qc_result.rms_reference:.6g}"],
            ["Measured RMS", f"{qc_result.rms_measured:.6g}"],
            ["Amplitude ratio", f"{qc_result.amplitude_ratio_db:.3f} dB"],
            ["RMS spectral phase error", f"{qc_result.phase_error_rms_deg:.3f}°"],
            ["Mean magnitude-squared coherence", f"{qc_result.spectral_coherence_mean:.5f}"],
            ["Energy inside QC band", f"{100 * qc_result.in_band_energy_fraction:.2f}%"],
            ["Dominant frequency", f"{qc_result.dominant_frequency_hz:.3f} Hz"],
            ["Crest factor", f"{qc_result.crest_factor:.4f}"],
        ]
        self.tabs.addTab(self._table(["Metric", "Value"], rows), "Metrics")
        self._export_rows = [["metric", "value"], *rows]

    @staticmethod
    def _correlate(reference: np.ndarray, measured: np.ndarray, sample_rate_hz: float) -> tuple[np.ndarray, np.ndarray]:
        ref = reference - np.nanmean(reference)
        mea = measured - np.nanmean(measured)
        corr = signal.correlate(mea, ref, mode="full", method="fft")
        energy = np.sqrt(float(np.dot(ref, ref)) * float(np.dot(mea, mea)))
        if energy > 0:
            corr = corr / energy
        lags = signal.correlation_lags(mea.size, ref.size, mode="full") / max(float(sample_rate_hz), 1.0)
        return lags, corr

    @staticmethod
    def _spectrum(values: np.ndarray, sample_rate_hz: float) -> tuple[np.ndarray, np.ndarray]:
        values = np.nan_to_num(values - np.nanmean(values))
        if values.size < 2:
            return np.asarray([0.0]), np.asarray([0.0])
        win = np.hanning(values.size)
        spec = np.abs(np.fft.rfft(values * win))
        if spec.size and spec.max() > 0:
            spec = spec / spec.max()
        freq = np.fft.rfftfreq(values.size, d=1.0 / max(float(sample_rate_hz), 1.0))
        return freq, spec


class CorrelationResultsDialog(_BaseVibroseisResultsDialog):
    def __init__(self, lag: np.ndarray, corr: np.ndarray, parent=None) -> None:
        super().__init__(
            "Trace × Pilot Correlation Results",
            "Normalized trace-to-pilot cross-correlation with peak lag marker and exportable correlation samples.",
            parent,
        )
        peak_i = int(np.nanargmax(np.abs(corr))) if corr.size else 0
        peak_lag = float(lag[peak_i]) if lag.size else 0.0
        peak_corr = float(corr[peak_i]) if corr.size else 0.0
        self._add_metric("Peak corr", f"{peak_corr:.5f}", 0, 0)
        self._add_metric("Peak lag", f"{1000 * peak_lag:.3f} ms", 0, 1)
        self._add_metric("Samples", f"{corr.size:,}", 0, 2)
        p = pg.PlotWidget(); self._style_plot(p, "Normalized Trace × Pilot Cross-Correlation", "Correlation", "Lag (s)")
        p.plot(lag, corr, pen=self._palette_pen(2, 1.3))
        p.addLine(x=peak_lag, pen=pg.mkPen("#D7191C", width=1.0, style=Qt.DashLine))
        self.tabs.addTab(p, "Correlation")
        rows = [[float(l), float(c)] for l, c in zip(lag, corr)]
        self.tabs.addTab(self._table(["Lag (s)", "Correlation"], rows[:5000]), "Samples")
        self._export_rows = [["lag_s", "correlation"], *rows]


class GroundForceResultsDialog(_BaseVibroseisResultsDialog):
    def __init__(self, result, parent=None) -> None:
        super().__init__(
            "Vibroseis Ground Force Results",
            "Estimated ground force from reaction-mass and baseplate acceleration channels using selected masses and polarity conventions.",
            parent,
        )
        force = np.nan_to_num(np.asarray(result.ground_force_n, dtype=float))
        self._add_metric("Peak |force|", f"{result.peak_force_n:,.2f} N", 0, 0)
        self._add_metric("RMS force", f"{result.rms_force_n:,.2f} N", 0, 1)
        self._add_metric("Impulse", f"{result.impulse_ns:,.3f} N·s", 0, 2)
        self._add_metric("Samples", f"{force.size:,}", 0, 3)

        p1 = pg.PlotWidget(); self._style_plot(p1, "Estimated Ground Force", "Force (N)", "Time (s)")
        p1.plot(result.time_s, force, pen=self._palette_pen(0, 1.2))
        p1.addLine(y=0, pen=pg.mkPen("#687B88", width=1.0, style=Qt.DashLine))
        self.tabs.addTab(p1, "Force Curve")

        if force.size:
            hist, edges = np.histogram(force, bins=min(60, max(10, int(np.sqrt(force.size)))))
            centers = (edges[:-1] + edges[1:]) / 2.0
        else:
            hist = np.asarray([0]); centers = np.asarray([0.0])
        p2 = pg.PlotWidget(); self._style_plot(p2, "Force Distribution", "Count", "Force (N)")
        p2.plot(centers, hist, pen=self._palette_pen(1, 1.3), fillLevel=0, brush="#DDEFF8")
        self.tabs.addTab(p2, "Distribution")

        rows = [
            ["Peak |ground force|", f"{result.peak_force_n:,.2f} N"],
            ["RMS ground force", f"{result.rms_force_n:,.2f} N"],
            ["Signed force impulse", f"{result.impulse_ns:,.3f} N·s"],
            ["Minimum force", f"{float(np.nanmin(force)) if force.size else 0:,.2f} N"],
            ["Maximum force", f"{float(np.nanmax(force)) if force.size else 0:,.2f} N"],
        ]
        self.tabs.addTab(self._table(["Metric", "Value"], rows), "Metrics")
        self._export_rows = [["time_s", "ground_force_n"], *[[float(t), float(f)] for t, f in zip(result.time_s, force)]]


class ProductivityResultsDialog(_BaseVibroseisResultsDialog):
    def __init__(self, result, parent=None) -> None:
        super().__init__(
            "Vibroseis Productivity Results",
            "Nominal vibrator cycle calculation for VP/hour planning and active sweep-time review.",
            parent,
        )
        self._add_metric("Cycle / VP", f"{result.cycle_time_per_vp_s:.2f} s", 0, 0)
        self._add_metric("VP / hour", f"{result.theoretical_vp_per_hour:.2f}", 0, 1)
        self._add_metric("Sweeps / hour", f"{result.theoretical_sweeps_per_hour:.2f}", 0, 2)
        self._add_metric("Active sweep", f"{100 * result.active_sweep_fraction:.2f}%", 0, 3)
        p = pg.PlotWidget(); self._style_plot(p, "Productivity Summary", "Value", "Metric")
        x = np.arange(3, dtype=float)
        y = np.asarray([result.cycle_time_per_vp_s, result.theoretical_vp_per_hour, result.theoretical_sweeps_per_hour], dtype=float)
        bg = pg.BarGraphItem(x=x, height=y, width=0.55, brush="#0A86C7")
        p.addItem(bg)
        axis = p.getAxis("bottom")
        axis.setTicks([[(0, "Cycle s/VP"), (1, "VP/h"), (2, "Sweeps/h")]])
        self.tabs.addTab(p, "Graph")
        rows = [
            ["Nominal cycle time / VP", f"{result.cycle_time_per_vp_s:.2f} s"],
            ["Theoretical VP / hour", f"{result.theoretical_vp_per_hour:.2f}"],
            ["Theoretical sweeps / hour", f"{result.theoretical_sweeps_per_hour:.2f}"],
            ["Active sweep fraction", f"{100 * result.active_sweep_fraction:.2f}%"],
        ]
        self.tabs.addTab(self._table(["Metric", "Value"], rows), "Metrics")
        self._export_rows = [["metric", "value"], *rows]


class VapsQcResultsDialog(_BaseVibroseisResultsDialog):
    def __init__(self, summary: Mapping[str, object], records: list[object], attr: str, label: str, metric_getter, parent=None) -> None:
        super().__init__(
            "VAPS / H26 Field Vib QC Results",
            "Vibrator attribute QC with fleet summary, selected attribute display, warning categories and exportable record-level findings.",
            parent,
        )
        records_n = int(summary.get("records", 0) or 0)
        vibs_n = int(summary.get("vibs", 0) or 0)
        pass_n = int(summary.get("pass", 0) or 0)
        fail_n = int(summary.get("fail", 0) or 0)
        self._add_metric("Records", f"{records_n:,}", 0, 0)
        self._add_metric("Vibrators", f"{vibs_n:,}", 0, 1)
        self._add_metric("Pass", f"{pass_n:,}", 0, 2)
        self._add_metric("Fail", f"{fail_n:,}", 0, 3)

        p1 = pg.PlotWidget(); self._style_plot(p1, f"Selected Attribute — {label}", label, "Record / Source Line")
        pens = ["#111111", "#0A6EA8", "#D7191C", "#15945C", "#E6C200", "#7B61FF", "#AA3377", "#EE7733", "#009988", "#33BBEE"]
        by_vib: dict[str, list[tuple[float, float]]] = {}
        for i, rec in enumerate(records):
            value = metric_getter(rec, attr)
            if value is None:
                continue
            vib = str(getattr(rec, "vib", "?") or "?").strip() or "?"
            x_val = getattr(rec, "source_line", None)
            try:
                x = float(x_val) if x_val not in (None, "") else float(i + 1)
            except Exception:
                x = float(i + 1)
            by_vib.setdefault(vib, []).append((x, float(value)))
        for idx, (vib, pairs) in enumerate(sorted(by_vib.items())):
            pairs.sort(key=lambda p: p[0])
            if not pairs:
                continue
            x = np.asarray([p[0] for p in pairs], dtype=float)
            y = np.asarray([p[1] for p in pairs], dtype=float)
            p1.plot(x, y, pen=pg.mkPen(pens[idx % len(pens)], width=1.25), symbol="o", symbolSize=4, name=f"Vib {vib}")
        self.tabs.addTab(p1, "Attribute Graph")

        warnings = dict(summary.get("warnings", {}) or {})
        p2 = pg.PlotWidget(); self._style_plot(p2, "Warning Category Counts", "Count", "Category")
        if warnings:
            keys = list(warnings.keys())
            vals = np.asarray([float(warnings[k]) for k in keys], dtype=float)
            x = np.arange(len(keys), dtype=float)
            p2.addItem(pg.BarGraphItem(x=x, height=vals, width=0.55, brush="#D98919"))
            p2.getAxis("bottom").setTicks([[ (i, str(k)[:18]) for i, k in enumerate(keys) ]])
        self.tabs.addTab(p2, "Warnings Graph")

        warn_rows = [[k, v] for k, v in sorted(warnings.items())]
        if not warn_rows:
            warn_rows = [["No warning category", 0]]
        self.tabs.addTab(self._table(["Warning / QC category", "Count"], warn_rows), "Warnings")

        record_rows = []
        for rec in records[:5000]:
            record_rows.append([
                getattr(rec, "vib", ""), getattr(rec, "vp", ""), getattr(rec, "drive_level_pct", ""),
                getattr(rec, "avg_phase_deg", ""), getattr(rec, "peak_phase_deg", ""), getattr(rec, "avg_distortion_pct", ""),
                getattr(rec, "peak_distortion_pct", ""), getattr(rec, "avg_force", ""), getattr(rec, "peak_force", ""),
                getattr(rec, "status_code", ""), getattr(rec, "source_line", ""),
            ])
        self.tabs.addTab(self._table(["Vib", "VP", "Drive %", "Avg Phase", "Peak Phase", "Avg Dist", "Peak Dist", "Avg Force", "Peak Force", "Status", "Line"], record_rows), "Records")
        self._export_rows = [["vib", "vp", "drive_pct", "avg_phase", "peak_phase", "avg_dist", "peak_dist", "avg_force", "peak_force", "status", "line"], *record_rows]
