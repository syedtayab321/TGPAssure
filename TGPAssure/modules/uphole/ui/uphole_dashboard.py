from __future__ import annotations

import csv
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from modules.uphole import UpholeReader, UpholeShot
from modules.uphole.ui.dialogs import FileDepthAssignmentDialog, GeneralParametersDialog, PickBreaksPanel
from modules.uphole.ui.legacy_uphole_plot import LegacyUpholePlot

_QSS = """
QWidget#upholeDashboard {
    background:#f5f7fb;
    color:#182033;
    font-family:Segoe UI, Arial, sans-serif;
    font-size:8pt;
}
QWidget#upholeRibbon {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #ffffff,stop:1 #edf3fb);
    border-bottom:1px solid #cbd7e6;
}
QFrame#ribbonGroup {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #ffffff,stop:1 #f4f8ff);
    border:1px solid #b8c8dc;
    border-radius:10px;
}
QFrame#ribbonGroup:hover {
    border-color:#78a9df;
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #ffffff,stop:1 #edf6ff);
}
QLabel#groupTitle {
    color:#1d4ed8;
    font-size:7.2pt;
    font-weight:800;
    padding:0 4px;
    letter-spacing:.2px;
}
QLabel#displayTitle {
    color:#0f172a;
    font-size:7.8pt;
    font-weight:800;
    padding-right:4px;
}
QPushButton#ribbonButton {
    background:#ffffff;
    color:#1f2937;
    border:1px solid #b9c7d8;
    border-radius:8px;
    padding:4px 8px;
    min-height:24px;
    font-size:8pt;
    font-weight:700;
}
QPushButton#ribbonButton:hover { background:#dbeafe; border-color:#60a5fa; color:#0f172a; }
QPushButton#ribbonBlue {
    background:#eaf3ff; color:#0b5cab; border:1px solid #b9d8fb; border-radius:7px;
    padding:4px 9px; min-height:24px; font-size:8pt; font-weight:700;
}
QPushButton#ribbonGreen {
    background:#e9fbea; color:#176b33; border:1px solid #b9edc2; border-radius:7px;
    padding:4px 9px; min-height:24px; font-size:8pt; font-weight:700;
}
QPushButton#ribbonAmber {
    background:#fff4e6; color:#9a4b00; border:1px solid #ffd49d; border-radius:7px;
    padding:4px 9px; min-height:24px; font-size:8pt; font-weight:700;
}
QPushButton#ribbonRed {
    background:#fff0f1; color:#991b1b; border:1px solid #fecaca; border-radius:7px;
    padding:4px 9px; min-height:24px; font-size:8pt; font-weight:700;
}
QPushButton#ribbonButton:pressed, QPushButton#ribbonBlue:pressed, QPushButton#ribbonGreen:pressed,
QPushButton#ribbonAmber:pressed, QPushButton#ribbonRed:pressed { padding-top:5px; padding-bottom:3px; }
QPushButton#clearButton {
    background:#fff7ed;
    color:#9a3412;
    border:1px solid #fdba74;
    border-radius:7px;
    padding:4px 8px;
    min-height:24px;
    font-size:8pt;
    font-weight:650;
}
QToolButton#navButton {
    background:#ffffff;
    border:1px solid #cbd5e1;
    border-radius:7px;
    color:#1677d2;
    font-weight:900;
    font-size:11pt;
    min-width:26px;
    min-height:24px;
}
QToolButton#navButton:hover { background:#eaf2ff; border-color:#93c5fd; }
QRadioButton, QCheckBox {
    color:#1f2937;
    spacing:2px;
    font-size:7.8pt;
    font-weight:520;
}
QPushButton#swatch {
    border:1px solid #94a3b8;
    border-radius:4px;
    min-width:22px;
    max-width:22px;
    min-height:16px;
    max-height:16px;
    padding:0;
}
"""


class UpholeDashboard(QWidget):
    """Modern ribbon-based Uphole Interpretation module with legacy UYH workflow behavior."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("upholeDashboard")
        self.setProperty("module_id", "uphole")
        self.setStyleSheet(_QSS)
        self.reader = UpholeReader()
        self.plot: LegacyUpholePlot | None = None
        self.records: list[UpholeShot] = []
        self.current_path: str = ""
        self.current_folder: str = ""
        self.params: dict = {
            "Client": "The Client",
            "Contractor": "Anyone But WG",
            "Crew": "Crew",
            "Country": "Sum Kuntry",
            "Area": "An Area",
            "Block": "A Block",
            "QC Contractor": "Rent-a-Rat",
            "QC Name": "Noddy Nonuts",
            "Auto Load Picks if Exist": True,
            "Auto Write SEGY on File Load": True,
            "channel_offsets": [0.0] * 24,
            "receiver_type": "Geophone",
        }
        self._build_ui()
        self._refresh_state()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_ribbon())

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)

        self.pick_panel = PickBreaksPanel()
        self.pick_panel.hide()
        self.pick_panel.clear_requested.connect(self.clear_picks)
        self.pick_panel.save_requested.connect(self.save_picks)
        self.pick_panel.print_requested.connect(lambda: QMessageBox.information(self, "Print", "Print command sent from pick-break panel."))
        self.pick_panel.close_requested.connect(self._close_pick_panel)
        content.addWidget(self.pick_panel)

        self.plot = LegacyUpholePlot()
        self.plot.pick_made.connect(self._on_pick_made)
        content.addWidget(self.plot, 1)
        root.addLayout(content, 1)

        self.mode_radios["va_plus"].setChecked(True)
        self._set_display_mode("va_plus")

    def _build_ribbon(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("upholeRibbon")
        bar.setFixedHeight(76)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(7)

        file_group = self._group("File")
        file_row = QHBoxLayout()
        file_row.setSpacing(4)
        file_row.addWidget(self._ribbon_button("📂 Open", self.open_file, "ribbonBlue"))
        file_row.addWidget(self._ribbon_button("🗂 Load Hole", self.load_hole, "ribbonGreen"))
        file_row.addWidget(self._ribbon_button("💾 Save Img", self.save_image))
        file_group.layout().addLayout(file_row)
        layout.addWidget(file_group)

        work_group = self._group("Workflow")
        work_row = QHBoxLayout()
        work_row.setSpacing(4)
        work_row.addWidget(self._ribbon_button("✚ Pick Breaks", self.pick_breaks, "ribbonAmber"))
        work_row.addWidget(self._ribbon_button("📈 Uphole", self.run_uphole, "ribbonGreen"))
        work_row.addWidget(self._ribbon_button("⚙ Configure", self.configure, "ribbonBlue"))
        work_group.layout().addLayout(work_row)
        layout.addWidget(work_group)

        output_group = self._group("Output")
        out_row = QHBoxLayout()
        out_row.setSpacing(4)
        out_row.addWidget(self._ribbon_button("☰ Headers", self.headers))
        out_row.addWidget(self._ribbon_button("⇢ SEGY", self.write_segy))
        clear = QPushButton("Clear Results")
        clear.setObjectName("clearButton")
        clear.clicked.connect(self.clear_results)
        out_row.addWidget(clear)
        output_group.layout().addLayout(out_row)
        layout.addWidget(output_group)

        display_group = self._group("Display")
        display_row = QHBoxLayout()
        display_row.setSpacing(5)
        display_row.addWidget(QLabel("Mode"))
        self.mode_group = QButtonGroup(self)
        self.mode_radios: dict[str, QRadioButton] = {}
        for mode, label in (("wig", "Wig"), ("va_plus", "VA+"), ("va_minus", "VA-"), ("va_both", "VA+/-")):
            rb = QRadioButton(label)
            self.mode_group.addButton(rb)
            self.mode_radios[mode] = rb
            rb.toggled.connect(lambda checked, m=mode: self._set_display_mode(m) if checked else None)
            display_row.addWidget(rb)
        self.grad_fill = QCheckBox("Gradient")
        self.grad_fill.toggled.connect(lambda checked: self._set_grad_fill(checked))
        display_row.addWidget(self.grad_fill)
        self.black_swatch = QPushButton("")
        self.black_swatch.setObjectName("swatch")
        self.black_swatch.setStyleSheet("QPushButton#swatch{background:#000000;border:1px solid #777;}")
        self.red_swatch = QPushButton("")
        self.red_swatch.setObjectName("swatch")
        self.red_swatch.setStyleSheet("QPushButton#swatch{background:#ef4444;border:1px solid #777;}")
        display_row.addWidget(self.black_swatch)
        display_row.addWidget(self.red_swatch)
        display_group.layout().addLayout(display_row)
        layout.addWidget(display_group, 1)

        nav_group = self._group("Scale")
        nav_row = QHBoxLayout()
        nav_row.setSpacing(4)
        for text, tip, handler in (
            ("≪", "Reduce horizontal stretch", lambda: self.plot.zoom_horizontal(0.80)),
            ("≫", "Increase horizontal stretch", lambda: self.plot.zoom_horizontal(1.25)),
            ("⌃", "Compress vertical time spacing", lambda: self.plot.zoom_vertical(1.25)),
            ("⌄", "Expand vertical time spacing", lambda: self.plot.zoom_vertical(0.80)),
        ):
            btn = QToolButton()
            btn.setObjectName("navButton")
            btn.setText(text)
            btn.setToolTip(tip)
            btn.clicked.connect(handler)
            nav_row.addWidget(btn)
        nav_group.layout().addLayout(nav_row)
        layout.addWidget(nav_group)

        layout.addWidget(self._ribbon_button("Exit", self.close_dashboard, "ribbonRed"))
        return bar

    def _group(self, title: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("ribbonGroup")
        v = QVBoxLayout(frame)
        v.setContentsMargins(7, 4, 7, 4)
        v.setSpacing(3)
        lbl = QLabel(title)
        lbl.setObjectName("groupTitle")
        lbl.setAlignment(Qt.AlignCenter)
        v.addWidget(lbl)
        return frame

    def _ribbon_button(self, text: str, handler, object_name: str = "ribbonButton") -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName(object_name)
        btn.clicked.connect(handler)
        return btn

    def _set_display_mode(self, mode: str) -> None:
        if self.plot is None:
            return
        self.plot.display_mode = mode
        self.plot.update()

    def _set_grad_fill(self, checked: bool) -> None:
        if self.plot is None:
            return
        self.plot.grad_fill = checked
        self.plot.update()

    def _refresh_state(self) -> None:
        if self.records and self.plot is not None:
            rec = self.records[self.plot.current_index]
            path = self.current_path or rec.file_name
            self.window().setWindowTitle(f"Uphole ---> Current File : {path}")
        if self.plot is not None:
            self.plot.set_records(self.records, self.current_path)
        self._refresh_pick_label()

    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Uphole File", "", "Uphole Files (*.seg2 *.sg2 *.oyo *.gen *.csv *.txt *.dat);;All files (*.*)")
        if not path:
            return
        self._load_path(path)

    def load_hole(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Load a Hole")
        if not folder:
            return
        self.current_folder = folder
        self.params["current_folder"] = folder
        self._load_path(folder)
        if self.records:
            dlg = FileDepthAssignmentDialog(self.records, folder, self)
            if dlg.exec():
                dlg.apply_to_records()
                self._refresh_state()

    def _load_path(self, path: str) -> None:
        try:
            records = self.reader.read(path)
        except Exception as exc:
            QMessageBox.warning(self, "Uphole", str(exc))
            return
        self.records = records
        self.current_path = path
        if self.plot is not None:
            self.plot.current_index = 0
        self._refresh_state()

    def configure(self) -> None:
        dlg = GeneralParametersDialog(self.records, self.params, self)
        if dlg.exec():
            self.params = dlg.values()
            self._refresh_state()

    def pick_breaks(self) -> None:
        if not self.records:
            QMessageBox.information(self, "Pick Breaks", "Open a SEG2/OYO file or load a hole first.")
            return
        self.pick_panel.show()
        if self.plot is not None:
            self.plot.pick_mode = True
            self.plot.update()
        self._refresh_pick_label()

    def _close_pick_panel(self) -> None:
        self.pick_panel.hide()
        if self.plot is not None:
            self.plot.pick_mode = False
            self.plot.update()

    def _on_pick_made(self, pick_ms: float) -> None:
        self._refresh_pick_label()

    def _refresh_pick_label(self) -> None:
        if self.plot is None:
            return
        rec = self.plot.current_record()
        if rec is None:
            self.pick_panel.set_pick(None, None)
        else:
            self.pick_panel.set_pick(rec.channel, rec.pick_ms)

    def clear_picks(self) -> None:
        for rec in self.records:
            rec.pick_ms = None
            rec.corrected_ms = None
        self._refresh_state()

    def save_picks(self) -> None:
        if not self.records:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Picks", "uphole_picks.csv", "CSV (*.csv)")
        if not path:
            return
        self._write_records_csv(path)
        QMessageBox.information(self, "Save", f"Saved:\n{path}")

    def clear_results(self) -> None:
        for rec in self.records:
            rec.corrected_ms = None
        if self.plot is not None:
            self.plot.update()

    def run_uphole(self) -> None:
        if not self.records:
            QMessageBox.information(self, "Uphole", "Load records first.")
            return
        for rec in self.records:
            if rec.pick_ms is not None and rec.corrected_ms is None:
                rec.corrected_ms = rec.pick_ms
        if self.plot is not None:
            self.plot.update()
        QMessageBox.information(self, "Uphole", "Uphole picks/results updated.")

    def headers(self) -> None:
        if not self.records or self.plot is None:
            QMessageBox.information(self, "Headers", "No file loaded.")
            return
        rec = self.plot.current_record()
        if rec is None:
            return
        info = (
            f"File: {rec.file_name}\n"
            f"Shot: {rec.shot_id}\n"
            f"Depth: {rec.depth_m}\n"
            f"Offset: {rec.offset_m}\n"
            f"Pick: {rec.pick_ms}\n"
            f"Sample interval: {rec.sample_interval_ms} ms\n"
            f"Samples: {rec.samples}\n"
            f"Traces: {rec.trace_count}\n"
            f"Note: {rec.note}"
        )
        QMessageBox.information(self, "Headers", info)

    def write_segy(self) -> None:
        if not self.records:
            QMessageBox.information(self, "Write SEGY", "No file loaded.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Write SEGY Sidecar", "uphole_segy_sidecar.csv", "CSV (*.csv)")
        if path:
            self._write_records_csv(path)
            QMessageBox.information(self, "Write SEGY", f"SEG-Y sidecar written:\n{path}")

    def save_image(self) -> None:
        if self.plot is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Image", "uphole_display.png", "PNG (*.png)")
        if not path:
            return
        pix = self.plot.grab()
        if not pix.save(path, "PNG"):
            QMessageBox.warning(self, "Save Image", "Could not save image.")

    def _write_records_csv(self, path: str) -> None:
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["file_name", "shot_id", "depth_m", "offset_m", "pick_ms", "corrected_ms", "channel", "sample_interval_ms", "samples", "trace_count", "note"])
            for rec in self.records:
                writer.writerow([rec.file_name, rec.shot_id, rec.depth_m, rec.offset_m, rec.pick_ms, rec.corrected_ms, rec.channel, rec.sample_interval_ms, rec.samples, rec.trace_count, rec.note])

    def interpret(self) -> None:
        """Compatibility entry point used by the main TGPAssure ribbon."""
        self.run_uphole()

    def refresh(self) -> None:
        """Compatibility refresh hook for host windows."""
        self._refresh_state()

    def close_dashboard(self) -> None:
        parent = self.parentWidget()
        while parent is not None:
            if hasattr(parent, "indexOf") and hasattr(parent, "removeTab"):
                index = parent.indexOf(self)
                if index >= 0:
                    parent.removeTab(index)
                    self.deleteLater()
                    return
            parent = parent.parentWidget()
        self.close()
