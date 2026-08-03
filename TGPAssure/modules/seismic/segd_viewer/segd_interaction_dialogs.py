from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class _ActionDialog(QDialog):
    def _apply_base_style(self) -> None:
        self.setStyleSheet(
            "QDialog{background:#F3F7FA;color:#102A3D;}"
            "QFrame#header{background:#102A3D;border-radius:9px;}"
            "QLabel#title{color:white;font-size:14pt;font-weight:900;background:transparent;}"
            "QLabel#subtitle{color:#CFE7F5;background:transparent;}"
            "QFrame#card{background:white;border:1px solid #D4DEE8;border-radius:8px;}"
            "QLabel#caption{color:#607080;font-size:8pt;font-weight:800;background:transparent;}"
            "QLabel#value{color:#102A3D;font-size:10pt;font-weight:800;background:transparent;}"
            "QPushButton{background:#FFFFFF;border:1px solid #BFD0DC;border-radius:5px;padding:7px 10px;font-weight:800;}"
            "QPushButton:hover{background:#EFF8FC;border-color:#0A86C7;}"
            "QPushButton#primary{background:#0A86C7;color:white;border-color:#0A86C7;}"
        )

    def _header(self, title: str, subtitle: str) -> QFrame:
        frame = QFrame(self)
        frame.setObjectName("header")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 9, 12, 9)
        title_label = QLabel(title)
        title_label.setObjectName("title")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("subtitle")
        subtitle_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        return frame

    def _metric_grid(self, rows: list[tuple[str, str]]) -> QFrame:
        card = QFrame(self)
        card.setObjectName("card")
        grid = QGridLayout(card)
        grid.setContentsMargins(10, 9, 10, 9)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        for index, (caption, value) in enumerate(rows):
            cap = QLabel(caption)
            cap.setObjectName("caption")
            val = QLabel(value)
            val.setObjectName("value")
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            grid.addWidget(cap, index, 0)
            grid.addWidget(val, index, 1)
        return card


class SegdPickActionsDialog(_ActionDialog):
    def __init__(
        self,
        *,
        trace: int,
        sample: int,
        time_ms: float,
        amplitude: float,
        status: str,
        on_inspect: Callable[[], None],
        on_headers: Callable[[], None],
        on_copy: Callable[[], None],
        on_clear: Callable[[], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("SEG-D Pick Actions")
        self.setMinimumWidth(430)
        self._on_inspect = on_inspect
        self._on_headers = on_headers
        self._on_copy = on_copy
        self._on_clear = on_clear
        self._apply_base_style()

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(9)
        root.addWidget(self._header("Pick Created", "Choose what to do with the selected trace/sample point."))
        root.addWidget(self._metric_grid([
            ("Trace", f"{trace + 1}"),
            ("Sample", f"{sample + 1}"),
            ("Time", f"{time_ms:.3f} ms"),
            ("Amplitude", f"{amplitude:.6g}"),
            ("QC Status", status),
        ]))

        row = QHBoxLayout()
        inspect = QPushButton("Inspect Waveform")
        inspect.setObjectName("primary")
        headers = QPushButton("Show Headers")
        copy = QPushButton("Copy Details")
        clear = QPushButton("Clear Pick")
        close = QPushButton("Close")
        inspect.clicked.connect(self._inspect)
        headers.clicked.connect(self._headers)
        copy.clicked.connect(self._copy)
        clear.clicked.connect(self._clear)
        close.clicked.connect(self.accept)
        for button in (inspect, headers, copy, clear, close):
            row.addWidget(button)
        root.addLayout(row)

    def _inspect(self) -> None:
        self._on_inspect()

    def _headers(self) -> None:
        self._on_headers()

    def _copy(self) -> None:
        self._on_copy()

    def _clear(self) -> None:
        self._on_clear()
        self.accept()


class SegdMeasureActionsDialog(_ActionDialog):
    def __init__(
        self,
        *,
        trace_1: int,
        sample_1: int,
        trace_2: int,
        sample_2: int,
        delta_time_ms: float,
        on_copy: Callable[[], None],
        on_clear: Callable[[], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("SEG-D Measurement Actions")
        self.setMinimumWidth(440)
        self._on_copy = on_copy
        self._on_clear = on_clear
        self._apply_base_style()

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(9)
        root.addWidget(self._header("Measurement Complete", "Review the delta values, then copy or clear the measurement."))
        root.addWidget(self._metric_grid([
            ("Start", f"Trace {trace_1 + 1}, Sample {sample_1 + 1}"),
            ("End", f"Trace {trace_2 + 1}, Sample {sample_2 + 1}"),
            ("Δ Trace", f"{abs(trace_2 - trace_1)}"),
            ("Δ Sample", f"{abs(sample_2 - sample_1)}"),
            ("Δ Time", f"{delta_time_ms:.3f} ms"),
        ]))

        row = QHBoxLayout()
        copy = QPushButton("Copy Measurement")
        copy.setObjectName("primary")
        clear = QPushButton("Clear Measurement")
        close = QPushButton("Close")
        copy.clicked.connect(self._copy)
        clear.clicked.connect(self._clear)
        close.clicked.connect(self.accept)
        row.addWidget(copy)
        row.addWidget(clear)
        row.addWidget(close)
        root.addLayout(row)

    def _copy(self) -> None:
        self._on_copy()

    def _clear(self) -> None:
        self._on_clear()
        self.accept()
