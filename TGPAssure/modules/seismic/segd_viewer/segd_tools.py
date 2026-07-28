from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PySide6.QtCore import Qt, QRectF
from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QMessageBox, QInputDialog,
    QPlainTextEdit, QPushButton, QSpinBox, QDoubleSpinBox, QCheckBox, QRadioButton,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont


def _show_text(parent: QWidget, title: str, text: str) -> None:
    dlg = QDialog(parent); dlg.setWindowTitle(title); dlg.resize(760, 520)
    lay = QVBoxLayout(dlg); edit = QPlainTextEdit(); edit.setReadOnly(True); edit.setPlainText(text); lay.addWidget(edit)
    close = QPushButton("Close"); close.clicked.connect(dlg.accept); lay.addWidget(close, 0, Qt.AlignRight); dlg.exec()


class _SpreadCanvas(QWidget):
    """428-style receiver-spread QC canvas based on decoded SEG-D trace extensions."""

    STATUS_COLORS = {
        "None": QColor("#00EE19"),
        "Leakage": QColor("#1010D8"),
        "Tilt": QColor("#ED19E8"),
        "Multiple": QColor("#FFF000"),
        "Capacitance": QColor("#050505"),
        "Resistance": QColor("#E00000"),
        "Other": QColor("#10D5D8"),
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(700, 420)
        self._rows: list[dict[str, Any]] = []
        self._mode = "Errors"
        self._slice_values: dict[int, float] = {}
        self._normalise_trace_peak = False

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.update()

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self._slice_values = {}
        self.update()

    def set_slice(self, mode: str, values: dict[int, float]) -> None:
        self._mode = mode
        self._slice_values = values
        self.update()

    def set_trace_peak_normalisation(self, enabled: bool) -> None:
        self._normalise_trace_peak = bool(enabled)
        self.update()

    @staticmethod
    def _finite(value: Any) -> bool:
        try:
            return bool(np.isfinite(float(value)))
        except Exception:
            return False

    @classmethod
    def _status(cls, row: dict[str, Any]) -> str:
        flags = [str(v).lower() for v in row.get("flags", ())]
        failures = []
        for label, value_key, low_key, high_key in (
            ("Resistance", "resistance", "resistance_low", "resistance_high"),
            ("Capacitance", "capacitance", "capacitance_low", "capacitance_high"),
        ):
            value, lo, hi = row.get(value_key), row.get(low_key), row.get(high_key)
            if cls._finite(value):
                if cls._finite(lo) and float(value) < float(lo): failures.append(label)
                if cls._finite(hi) and float(value) > float(hi): failures.append(label)
        for label, value_key, limit_key in (
            ("Leakage", "leakage", "leakage_limit"),
            ("Tilt", "tilt", "tilt_limit"),
        ):
            value, limit = row.get(value_key), row.get(limit_key)
            if cls._finite(value) and cls._finite(limit) and abs(float(value)) > abs(float(limit)):
                failures.append(label)
        for label in ("resistance", "capacitance", "leakage", "tilt"):
            if any(label in flag for flag in flags): failures.append(label.title())
        failures = list(dict.fromkeys(failures))
        if len(failures) > 1: return "Multiple"
        if failures: return failures[0]
        if flags: return "Other"
        return "None"

    def _metric_value(self, row: dict[str, Any]) -> tuple[float | None, bool]:
        mapping = {
            "Resistance": ("resistance", "resistance_low", "resistance_high"),
            "Capacitance": ("capacitance", "capacitance_low", "capacitance_high"),
            "Leakage": ("leakage", None, "leakage_limit"),
            "Tilt": ("tilt", None, "tilt_limit"),
        }
        if self._mode not in mapping:
            return None, False
        key, lo_key, hi_key = mapping[self._mode]
        value = row.get(key)
        if not self._finite(value): return None, False
        failed = False
        if lo_key and self._finite(row.get(lo_key)) and float(value) < float(row[lo_key]): failed = True
        if hi_key and self._finite(row.get(hi_key)) and abs(float(value)) > abs(float(row[hi_key])): failed = True
        return float(value), failed

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(self.rect(), QColor("white"))
        if not self._rows:
            painter.setPen(QColor("#777777")); painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No receiver spread data")
            return
        plot = QRectF(78, 45, max(200, self.width()-210), max(180, self.height()-105))
        painter.setPen(QPen(QColor("#A7ADB2"), 1)); painter.drawRect(plot)
        painter.setFont(QFont(painter.font().family(), 11, QFont.Weight.Bold))
        painter.setPen(QColor("#000000")); painter.drawText(QRectF(plot.left(), 8, plot.width(), 30), Qt.AlignmentFlag.AlignCenter, self._mode)

        lines = sorted({float(r["line"]) for r in self._rows})
        points = [float(r["point"]) for r in self._rows]
        pmin, pmax = min(points), max(points)
        if pmax <= pmin: pmax = pmin + 1.0
        line_y = {line: plot.top() + (i+0.5)*plot.height()/len(lines) for i,line in enumerate(lines)}
        for line, y in line_y.items():
            painter.setPen(QColor("#222222")); painter.drawText(8, int(y+4), f"{line:g}")

        # Draw records as contiguous colored segments; status colors reproduce the 428-style error overview.
        bin_w = max(2.0, plot.width()/max(1, min(500, len({round(p,6) for p in points}))))
        slice_abs = np.array([abs(v) for v in self._slice_values.values() if np.isfinite(v)], dtype=float)
        slice_scale = float(np.nanpercentile(slice_abs, 98)) if slice_abs.size else 1.0
        slice_scale = max(slice_scale, 1e-12)
        for row in self._rows:
            x = plot.left() + (float(row["point"])-pmin)/(pmax-pmin)*plot.width()
            y = line_y[float(row["line"])]
            if self._mode in {"TSlice", "FSlice"}:
                value = self._slice_values.get(int(row["index"]), np.nan)
                if not np.isfinite(value): color = QColor("#D5DADF")
                else:
                    frac = min(1.0, abs(float(value))/slice_scale)
                    # Blue -> cyan -> yellow -> red magnitude ramp without external colormap dependency.
                    color = QColor.fromHsv(int((1.0-frac)*220), 230, 245)
            elif self._mode == "Errors":
                color = self.STATUS_COLORS[self._status(row)]
            else:
                _, failed = self._metric_value(row)
                color = QColor("#E00000") if failed else QColor("#00EE19")
            painter.fillRect(QRectF(x-bin_w/2, y-11, bin_w+1, 22), QBrush(color))

        # X labels and legend
        painter.setFont(QFont(painter.font().family(), 8))
        painter.setPen(QColor("#333333"))
        for frac in np.linspace(0,1,7):
            x=plot.left()+frac*plot.width(); val=pmin+frac*(pmax-pmin)
            painter.save(); painter.translate(x, plot.bottom()+7); painter.rotate(-90); painter.drawText(0,0,f"{val:g}"); painter.restore()
        painter.drawText(QRectF(plot.left(), self.height()-24, plot.width(), 20), Qt.AlignmentFlag.AlignCenter, "Receiver Point / Position")
        if self._mode == "Errors":
            lx = plot.right()+20; ly = plot.bottom()-150
            for name,color in self.STATUS_COLORS.items():
                painter.fillRect(QRectF(lx,ly,22,18),QBrush(color)); painter.setPen(QColor("#222")); painter.drawText(int(lx+28),int(ly+14),name); ly+=20
        elif self._mode in {"TSlice","FSlice"}:
            painter.drawText(int(plot.right()+18), int(plot.top()+20), "Relative magnitude")
        else:
            painter.fillRect(QRectF(plot.right()+20,plot.top()+45,22,18),QBrush(QColor("#00EE19"))); painter.drawText(int(plot.right()+48),int(plot.top()+59),"Within limits")
            painter.fillRect(QRectF(plot.right()+20,plot.top()+70,22,18),QBrush(QColor("#E00000"))); painter.drawText(int(plot.right()+48),int(plot.top()+84),"Outside limits")


class _SpreadViewDialog(QDialog):
    def __init__(self, viewer: Any) -> None:
        super().__init__(viewer)
        self.viewer = viewer
        self.reader = viewer.reader
        self.setWindowTitle("Spread View")
        self.resize(1120, 760)
        self._rows = self._load_rows()
        self._build_ui()
        self._apply_range()

    def _load_rows(self) -> list[dict[str, Any]]:
        rows=[]
        for i in range(self.reader.get_trace_count()):
            ti=self.reader.get_trace_info(i)
            line=float(getattr(ti,"receiver_line",0.0) or 0.0)
            point=float(getattr(ti,"receiver_point",i+1) or (i+1))
            rows.append({
                "index":i,"line":line,"point":point,"flags":tuple(getattr(ti,"qc_flags",()) or ()),
                "resistance":getattr(ti,"resistance",None),"resistance_low":getattr(ti,"resistance_low_limit",None),"resistance_high":getattr(ti,"resistance_high_limit",None),
                "capacitance":getattr(ti,"capacitance",None),"capacitance_low":getattr(ti,"capacitance_low_limit",None),"capacitance_high":getattr(ti,"capacitance_high_limit",None),
                "leakage":getattr(ti,"leakage",None),"leakage_limit":getattr(ti,"leakage_limit",None),"tilt":getattr(ti,"tilt",None),"tilt_limit":getattr(ti,"tilt_limit",None),
            })
        return rows

    def _build_ui(self) -> None:
        root=QVBoxLayout(self); root.setContentsMargins(8,8,8,8); root.setSpacing(5)
        top=QHBoxLayout()
        bmp=QPushButton("BMP"); bmp.clicked.connect(self._export_bmp); top.addWidget(bmp)
        ts=QPushButton("TSlice"); ts.clicked.connect(self._time_slice); top.addWidget(ts)
        fs=QPushButton("FSlice"); fs.clicked.connect(self._frequency_slice); top.addWidget(fs)
        top.addSpacing(10); top.addWidget(QLabel("From")); self.from_spin=QDoubleSpinBox(); self.from_spin.setRange(-1e12,1e12); self.from_spin.setDecimals(3); top.addWidget(self.from_spin)
        top.addWidget(QLabel("To")); self.to_spin=QDoubleSpinBox(); self.to_spin.setRange(-1e12,1e12); self.to_spin.setDecimals(3); top.addWidget(self.to_spin)
        apply_btn=QPushButton("Apply Range"); apply_btn.clicked.connect(self._apply_range); top.addWidget(apply_btn)
        top.addSpacing(10); top.addWidget(QLabel("Normalisation")); self.spread_peak=QRadioButton("Spread Peak"); self.trace_peak=QRadioButton("Trace Peak"); self.spread_peak.setChecked(True); top.addWidget(self.spread_peak); top.addWidget(self.trace_peak)
        top.addStretch(1); close=QPushButton("Close"); close.clicked.connect(self.accept); top.addWidget(close); root.addLayout(top)
        if self._rows:
            pts=[r["point"] for r in self._rows]; self.from_spin.setValue(min(pts)); self.to_spin.setValue(max(pts))
        body=QHBoxLayout(); modes=QVBoxLayout(); self.mode_group=QButtonGroup(self)
        for mode in ("Resistance","Capacitance","Leakage","Tilt","Errors"):
            b=QPushButton(mode); b.setCheckable(True); self.mode_group.addButton(b); b.clicked.connect(lambda checked,m=mode:self._set_mode(m)); modes.addWidget(b)
            if mode=="Errors": b.setChecked(True)
        modes.addStretch(1); body.addLayout(modes)
        self.canvas=_SpreadCanvas(); body.addWidget(self.canvas,1); root.addLayout(body,1)
        self.status=QLabel(""); root.addWidget(self.status)
        self.trace_peak.toggled.connect(self.canvas.set_trace_peak_normalisation)

    def _selected_rows(self) -> list[dict[str,Any]]:
        lo=min(self.from_spin.value(),self.to_spin.value()); hi=max(self.from_spin.value(),self.to_spin.value())
        return [r for r in self._rows if lo<=r["point"]<=hi]

    def _apply_range(self) -> None:
        rows=self._selected_rows(); self.canvas.set_rows(rows); self.status.setText(f"Displaying {len(rows):,} of {len(self._rows):,} traces across {len({r['line'] for r in rows}):,} receiver lines.")

    def _set_mode(self, mode:str) -> None:
        self.canvas.set_mode(mode)

    def _time_slice(self) -> None:
        time_ms,ok=QInputDialog.getDouble(self,"Time Slice","Time (ms):",0.0,0.0,1e9,3)
        if not ok:return
        sample=int(round(time_ms/max(float(self.reader.get_sample_interval()),1e-12)))
        rows=self._selected_rows(); values={}
        for r in rows:
            d=self.reader.read_channel_data((r["index"],r["index"]+1),0,(sample,sample+1))
            if d.size: values[r["index"]]=float(d[0,0])
        self.canvas.set_slice("TSlice",values); self.status.setText(f"Time slice at {time_ms:.3f} ms (sample {sample}); {len(values):,} traces evaluated.")

    def _frequency_slice(self) -> None:
        freq_hz,ok=QInputDialog.getDouble(self,"Frequency Slice","Frequency (Hz):",10.0,0.0,100000.0,2)
        if not ok:return
        rows=self._selected_rows(); values={}; dt=max(float(self.reader.get_sample_interval()),1e-12)/1000.0
        for r in rows:
            d=self.reader.read_channel_data((r["index"],r["index"]+1),0,None)
            if not d.size:continue
            x=d[0].astype(float); x-=np.mean(x); win=np.hanning(x.size); spec=np.abs(np.fft.rfft(x*win)); f=np.fft.rfftfreq(x.size,d=dt); k=int(np.argmin(np.abs(f-freq_hz))); values[r["index"]]=float(spec[k]/max(np.sum(win),1e-12))
        self.canvas.set_slice("FSlice",values); self.status.setText(f"Frequency slice near {freq_hz:.2f} Hz; {len(values):,} traces evaluated with Hann-window FFT.")

    def _export_bmp(self) -> None:
        path,_=QFileDialog.getSaveFileName(self,"Export Spread View",str(self.viewer.file_path.with_name(self.viewer.file_path.stem+"_spread.bmp")),"Bitmap Image (*.bmp)")
        if path:self.canvas.grab().save(path)


def spread_view(viewer: Any) -> None:
    if viewer.reader is None:
        QMessageBox.information(viewer,"Spread View","Open a SEG-D file first.")
        return
    _SpreadViewDialog(viewer).exec()


def split_proc_file(viewer: Any) -> None:
    """Export the selected processing window without pretending to rewrite proprietary SEG-D headers."""
    if viewer.reader is None:return
    t0=min(viewer.trace_start_spin.value(),viewer.trace_end_spin.value())-1; t1=max(viewer.trace_start_spin.value(),viewer.trace_end_spin.value())
    s0=min(viewer.sample_start_spin.value(),viewer.sample_end_spin.value())-1; s1=max(viewer.sample_start_spin.value(),viewer.sample_end_spin.value())
    path,_=QFileDialog.getSaveFileName(viewer,"Split Processing File / Export Window",str(viewer.file_path.with_name(viewer.file_path.stem+"_subset.npz")),"TGPAssure processing subset (*.npz)")
    if not path:return
    data=viewer.reader.read_channel_data((t0,t1),0,(s0,s1)); meta={"source":str(viewer.file_path),"trace_range":[t0,t1],"sample_range":[s0,s1],"sample_interval_ms":float(viewer.reader.get_sample_interval()),"note":"Lossless processing subset; source SEG-D remains unchanged."}
    np.savez_compressed(path,data=data,metadata=json.dumps(meta)); QMessageBox.information(viewer,"Split Proc File",f"Exported {data.shape[0]} traces × {data.shape[1]} samples.\n\n{path}")


def fix_radio_sim_file(viewer: Any) -> None:
    src,_=QFileDialog.getOpenFileName(viewer,"Select Radio Simulation / Sidecar File",str(viewer.file_path.parent),"Text/data files (*.txt *.csv *.sim *.dat);;All files (*.*)")
    if not src:return
    raw=Path(src).read_bytes(); cleaned=raw.replace(b"\x00",b"").replace(b"\r\r\n",b"\r\n")
    try:
        text=cleaned.decode("utf-8-sig",errors="replace"); lines=[ln.rstrip() for ln in text.splitlines() if ln.strip()]; cleaned=("\n".join(lines)+"\n").encode("utf-8")
    except Exception: pass
    dst,_=QFileDialog.getSaveFileName(viewer,"Save Repaired Copy",str(Path(src).with_name(Path(src).stem+"_fixed"+Path(src).suffix)),"All files (*.*)")
    if not dst:return
    Path(dst).write_bytes(cleaned); QMessageBox.information(viewer,"Fix Radio Sim File",f"Created a cleaned copy without modifying the source.\nRemoved NUL bytes / malformed line endings where present.\n\n{dst}")


def record_sum_diff(viewer: Any) -> None:
    if viewer.reader is None:return
    data=viewer._raw_data
    if data.size==0: QMessageBox.information(viewer,"Record Sum/Diff","Render a trace window first."); return
    even=data[0::2]; odd=data[1::2]; n=min(len(even),len(odd))
    if n==0:return
    sums=even[:n]+odd[:n]; diffs=even[:n]-odd[:n]
    text=(f"Record Sum / Difference\nPairs: {n}\n\n"
          f"SUM RMS: {np.sqrt(np.mean(sums*sums)):.6g}\nSUM peak: {np.max(np.abs(sums)):.6g}\n"
          f"DIFF RMS: {np.sqrt(np.mean(diffs*diffs)):.6g}\nDIFF peak: {np.max(np.abs(diffs)):.6g}\n"
          f"Difference/Sum RMS ratio: {np.sqrt(np.mean(diffs*diffs))/max(np.sqrt(np.mean(sums*sums)),1e-12):.4f}\n\n"
          "Adjacent rendered traces are paired. Use this to compare repeat/paired records; source samples are unchanged.")
    _show_text(viewer,"Record Sum/Diff",text)


def multi_vib_sim(viewer: Any) -> None:
    data=viewer._raw_data
    if data.size==0: QMessageBox.information(viewer,"Multi Vib Sim","Render traces first."); return
    n=min(32,data.shape[0]); x=data[:n].astype(float); x-=x.mean(axis=1,keepdims=True); norm=np.linalg.norm(x,axis=1); norm[norm<1e-12]=1; corr=(x@x.T)/(norm[:,None]*norm[None,:]); tri=np.abs(corr[np.triu_indices(n,1)]) if n>1 else np.array([0.])
    _show_text(viewer,"Multi Vib Sim",f"Multi-vibrator / repeat-trace similarity\nTraces analysed: {n}\nMean |correlation|: {np.mean(tri):.3f}\nMaximum |correlation|: {np.max(tri):.3f}\nPairs > 0.90: {np.count_nonzero(tri>0.90)}\n\nHigh correlation may indicate strongly repeatable signatures or duplicated channels; interpret with acquisition geometry and vibrator records.")


def radio_sims(viewer: Any) -> None:
    if viewer.reader is None:return
    counts={k:0 for k in ("Normal","Auxiliary","Resistance","Capacitance","Leakage","Tilt","Multiple","Dead","Edited")}
    n=viewer.reader.get_trace_count()
    for i in range(n):
        ti=viewer.reader.get_trace_info(i); flags=list(getattr(ti,"qc_flags",()) or ())
        if len(flags)>1:counts["Multiple"]+=1
        elif flags and flags[0] in counts:counts[flags[0]]+=1
        elif getattr(ti,"channel_type",1)!=1:counts["Auxiliary"]+=1
        elif getattr(ti,"trace_edit",0)!=0:counts["Edited"]+=1
        else:counts["Normal"]+=1
    _show_text(viewer,"Radio Sims", "Radio / sensor simulation status summary\n\n"+"\n".join(f"{k}: {v:,}" for k,v in counts.items())+"\n\nClassification is derived from SEG-D channel/trace metadata and QC flags; no proprietary 428XL telemetry state is invented.")


def filters(viewer: Any) -> None:
    dlg=QDialog(viewer); dlg.setWindowTitle("SEG-D Display Filters"); lay=QVBoxLayout(dlg); form=QFormLayout()
    enabled=QCheckBox("Enable display filter"); enabled.setChecked(bool(viewer._filter_enabled)); low=QDoubleSpinBox(); high=QDoubleSpinBox(); low.setRange(0,10000); high.setRange(0,10000); low.setSuffix(" Hz"); high.setSuffix(" Hz"); low.setValue(viewer._filter_low_hz); high.setValue(viewer._filter_high_hz)
    form.addRow(enabled); form.addRow("Low cut / high-pass",low); form.addRow("High cut / low-pass",high); lay.addLayout(form)
    note=QLabel("Zero means disabled. When both are set, a 4th-order zero-phase Butterworth band-pass is applied to the display only. Raw SEG-D data are never overwritten."); note.setWordWrap(True); lay.addWidget(note)
    row=QHBoxLayout(); ok=QPushButton("Apply"); cancel=QPushButton("Cancel"); ok.clicked.connect(dlg.accept); cancel.clicked.connect(dlg.reject); row.addStretch(1); row.addWidget(ok); row.addWidget(cancel); lay.addLayout(row)
    if dlg.exec():
        viewer._filter_enabled=enabled.isChecked(); viewer._filter_low_hz=low.value(); viewer._filter_high_hz=high.value(); viewer.render_current_view()


def panels(viewer: Any) -> None:
    dlg=QDialog(viewer); dlg.setWindowTitle("Panels"); lay=QVBoxLayout(dlg); checks=[]
    for i in range(viewer.tab_widget.count()):
        c=QCheckBox(viewer.tab_widget.tabText(i)); c.setChecked(viewer.tab_widget.isTabVisible(i)); checks.append((i,c)); lay.addWidget(c)
    ok=QPushButton("Apply"); lay.addWidget(ok); ok.clicked.connect(dlg.accept)
    if dlg.exec():
        for i,c in checks: viewer.tab_widget.setTabVisible(i,c.isChecked())


def trace_analysis(viewer: Any) -> None:
    data=viewer._raw_data
    if data.size==0: QMessageBox.information(viewer,"Trace Analysis","Render traces first."); return
    rms=np.sqrt(np.mean(data.astype(float)**2,axis=1)); peak=np.max(np.abs(data),axis=1); zero=np.mean(np.abs(data)<=1e-20,axis=1)*100
    idx=int(np.argmax(rms)); tr=data[idx].astype(float); dt=max(float(viewer.reader.get_sample_interval()),1e-9)/1000.; spec=np.abs(np.fft.rfft(tr-tr.mean())); freq=np.fft.rfftfreq(tr.size,d=dt); dom=float(freq[np.argmax(spec[1:])+1]) if len(spec)>1 else 0
    _show_text(viewer,"Trace Analysis",f"Rendered window: {data.shape[0]} traces × {data.shape[1]} samples\nMean RMS: {np.mean(rms):.6g}\nMedian RMS: {np.median(rms):.6g}\nMax RMS trace: {viewer._trace_start+idx+1}\nGlobal peak: {np.max(peak):.6g}\nMean zero/dead sample fraction: {np.mean(zero):.3f}%\nDominant frequency of max-RMS trace: {dom:.2f} Hz")


def dsd_bin_files(viewer: Any) -> None:
    path,_=QFileDialog.getOpenFileName(viewer,"Open DSD / Binary File",str(viewer.file_path.parent),"Binary files (*.bin *.dsd *.dat);;All files (*.*)")
    if not path:return
    raw=Path(path).read_bytes(); head=raw[:512]
    hex_lines=[]
    for off in range(0,len(head),16):
        chunk=head[off:off+16]; hx=" ".join(f"{b:02X}" for b in chunk); asc="".join(chr(b) if 32<=b<127 else "." for b in chunk); hex_lines.append(f"{off:08X}  {hx:<47}  {asc}")
    _show_text(viewer,"DSD Bin Files",f"File: {path}\nSize: {len(raw):,} bytes\n\nFirst 512 bytes:\n"+"\n".join(hex_lines))
