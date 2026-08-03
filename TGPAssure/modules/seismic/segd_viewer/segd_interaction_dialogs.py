from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


def _center_dialog(dialog: QDialog, width: int = 520, height: int = 260) -> None:
    screen = QApplication.primaryScreen()
    parent = dialog.parentWidget()
    if parent is not None:
        try:
            screen = QApplication.screenAt(parent.mapToGlobal(parent.rect().center())) or screen
        except Exception:
            pass
    if screen is None:
        dialog.resize(width, height)
        return
    geom = screen.availableGeometry()
    w = min(width, max(420, geom.width() - 48))
    h = min(height, max(220, geom.height() - 48))
    dialog.resize(w, h)
    dialog.move(geom.x() + (geom.width() - w) // 2, geom.y() + (geom.height() - h) // 2)

def _tool_button(text: str, role: str = "gray") -> QPushButton:
    colors = {
        "blue": ("#DDEEFF", "#4B87C3", "#0E4F8C"),
        "green": ("#E2F7E8", "#65B47A", "#17682E"),
        "orange": ("#FFF0D2", "#CE9330", "#815300"),
        "red": ("#FBE4E4", "#D47C7C", "#8C1F1F"),
        "purple": ("#EFE5FF", "#9272CE", "#4F2F88"),
        "gray": ("#F3F3F3", "#8D8D8D", "#1B1B1B"),
    }
    bg, border, fg = colors.get(role, colors["gray"])
    button = QPushButton(text)
    button.setStyleSheet(
        f"QPushButton{{background:{bg};border:1px solid {border};color:{fg};font-weight:800;border-radius:5px;padding:6px 10px;}}"
        "QPushButton:hover{background:#FFFFFF;}"
    )
    return button


class _ActionDialog(QDialog):
    def _apply_base_style(self) -> None:
        self.setStyleSheet(
            "QDialog{background:#EAF0F5;color:#102A3D;font-family:Arial,Segoe UI,sans-serif;font-size:8.5pt;}"
            "QFrame#header{background:#102A3D;border-radius:7px;}"
            "QLabel#title{color:white;font-size:12pt;font-weight:900;background:transparent;}"
            "QLabel#subtitle{color:#CFE7F5;background:transparent;font-size:8.5pt;}"
            "QFrame#card{background:white;border:1px solid #C4D0DA;border-radius:6px;}"
            "QLabel#caption{color:#607080;font-size:8pt;font-weight:800;background:transparent;}"
            "QLabel#value{color:#102A3D;font-size:9pt;font-weight:800;background:transparent;}"
            "QPushButton{background:#FFFFFF;border:1px solid #BFD0DC;border-radius:5px;padding:5px 8px;font-weight:800;font-size:8.5pt;}"
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
        inspect = _tool_button("Inspect Waveform", "blue")
        inspect.setObjectName("primary")
        headers = _tool_button("Show Headers", "purple")
        copy = _tool_button("Copy Details", "green")
        clear = _tool_button("Clear Pick", "orange")
        close = _tool_button("Close", "red")
        inspect.clicked.connect(self._inspect)
        headers.clicked.connect(self._headers)
        copy.clicked.connect(self._copy)
        clear.clicked.connect(self._clear)
        close.clicked.connect(self.accept)
        for button in (inspect, headers, copy, clear, close):
            row.addWidget(button)
        root.addLayout(row)
        _center_dialog(self, 560, 265)
        QTimer.singleShot(0, lambda: _center_dialog(self, 560, 265))

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
        copy = _tool_button("Copy Measurement", "green")
        copy.setObjectName("primary")
        clear = _tool_button("Clear Measurement", "orange")
        close = _tool_button("Close", "red")
        copy.clicked.connect(self._copy)
        clear.clicked.connect(self._clear)
        close.clicked.connect(self.accept)
        row.addWidget(copy)
        row.addWidget(clear)
        row.addWidget(close)
        root.addLayout(row)
        _center_dialog(self, 560, 245)
        QTimer.singleShot(0, lambda: _center_dialog(self, 560, 245))

    def _copy(self) -> None:
        self._on_copy()

    def _clear(self) -> None:
        self._on_clear()
        self.accept()
