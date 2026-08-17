from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QPushButton, QApplication

LEGACY_DIALOG_QSS = """
QDialog {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #f7fbff,stop:.50 #eef7ff,stop:1 #eaf2fb);
    color: #0f172a;
    font-family: Segoe UI, Arial, sans-serif;
    font-size: 8.2pt;
}
QLabel#titleLabel {
    font-size: 10.5pt;
    font-weight: 900;
    color:#0b4f8a;
}
QLabel#sectionLabel {
    font-size: 8.5pt;
    font-weight: 800;
    color:#1e3a8a;
}
QLabel#logoBox {
    background:#ffffff;
    border:1px solid #cbd5e1;
    border-radius:9px;
    color:#64748b;
    font-weight:700;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QTableWidget {
    background: #ffffff;
    color:#111827;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    min-height: 20px;
    padding: 1px 5px;
    selection-background-color:#bfdbfe;
    font-size:8pt;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #2563eb;
    background:#f8fbff;
}
QHeaderView::section {
    background:#dbeafe;
    color:#0f172a;
    border:1px solid #c7d2fe;
    padding:3px;
    font-weight:700;
    font-size:8pt;
}
QCheckBox, QRadioButton {
    color:#1f2937;
    spacing:4px;
    font-size:8pt;
}
QPushButton {
    background: #ffffff;
    color:#1f2937;
    border: 1px solid #b7c7da;
    border-radius: 8px;
    padding: 5px 10px;
    min-height: 24px;
    font-size:8pt;
    font-weight:650;
}
QPushButton:hover { background: #dbeafe; border-color:#60a5fa; color:#0f172a; }
QPushButton#okButton, QPushButton#saveGreen, QPushButton#saveAssignment {
    background: #dcfce7;
    color:#166534;
    border:1px solid #86efac;
}
QPushButton#okButton:hover, QPushButton#saveGreen:hover, QPushButton#saveAssignment:hover {
    background: #bbf7d0;
}
QPushButton#cancelButton, QPushButton#clearButton, QPushButton#closeButton {
    background: #fee2e2;
    color:#991b1b;
    border:1px solid #fca5a5;
}
QPushButton#cancelButton:hover, QPushButton#clearButton:hover, QPushButton#closeButton:hover {
    background: #fecaca;
}
QPushButton#blueButton {
    background:#dbeafe;
    color:#1d4ed8;
    border:1px solid #93c5fd;
}
QPushButton#amberButton {
    background:#ffedd5;
    color:#9a3412;
    border:1px solid #fdba74;
}
"""


class CenteredDialog(QDialog):
    """QDialog that always opens centered over its parent or active screen."""

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        QTimer.singleShot(0, self.center_on_parent)

    def center_on_parent(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            parent_frame = parent.window().frameGeometry()
            target = parent_frame.center()
        else:
            screen = QApplication.primaryScreen()
            if screen is None:
                return
            target = screen.availableGeometry().center()
        geo = self.frameGeometry()
        geo.moveCenter(target)
        self.move(geo.topLeft())


def button(text: str, object_name: str | None = None):
    btn = QPushButton(text)
    if object_name:
        btn.setObjectName(object_name)
    return btn
