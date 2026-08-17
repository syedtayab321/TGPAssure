from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class PickBreaksPanel(QWidget):
    """Compact side panel shown while first-break picking is active."""

    clear_requested = Signal()
    save_requested = Signal()
    print_requested = Signal()
    close_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedWidth(132)
        self.setStyleSheet(
            "QWidget{background:#f1f5f9;border-right:1px solid #cbd5e1;font-family:Segoe UI,Arial;font-size:8pt;}"
            "QLabel#title{font-weight:800;color:#0f172a;}"
            "QLabel#pick{color:#475569;background:#ffffff;border:1px solid #d8e2ee;border-radius:7px;padding:6px;}"
            "QPushButton{border:1px solid #cbd5e1;border-radius:8px;padding:5px;background:#ffffff;min-height:24px;font-weight:650;}"
            "QPushButton:hover{background:#e8f2ff;border-color:#93c5fd;}"
            "QPushButton#clear{background:#fee2e2;color:#991b1b;border-color:#fca5a5;}"
            "QPushButton#save{background:#dcfce7;color:#166534;border-color:#86efac;}"
            "QPushButton#print{background:#dbeafe;color:#1d4ed8;border-color:#93c5fd;}"
            "QPushButton#close{background:#fff7ed;color:#9a3412;border-color:#fdba74;}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(7)
        clear = QPushButton("Clear All")
        clear.setObjectName("clear")
        layout.addWidget(clear)
        title = QLabel("Pick Times (mS)")
        title.setObjectName("title")
        layout.addWidget(title)
        self.pick_label = QLabel("")
        self.pick_label.setObjectName("pick")
        self.pick_label.setWordWrap(True)
        layout.addWidget(self.pick_label)
        layout.addStretch(1)
        print_btn = QPushButton("Print")
        print_btn.setObjectName("print")
        save_btn = QPushButton("Save")
        save_btn.setObjectName("save")
        close_btn = QPushButton("Close")
        close_btn.setObjectName("close")
        layout.addWidget(print_btn)
        layout.addWidget(save_btn)
        layout.addWidget(close_btn)
        clear.clicked.connect(self.clear_requested.emit)
        save_btn.clicked.connect(self.save_requested.emit)
        print_btn.clicked.connect(self.print_requested.emit)
        close_btn.clicked.connect(self.close_requested.emit)

    def set_pick(self, channel: int | None, pick_ms: float | None) -> None:
        if pick_ms is None:
            self.pick_label.setText("No pick")
            return
        ch = channel if channel is not None else 1
        self.pick_label.setText(f"Ch {ch:02d}\n{pick_ms:.2f} mS")
