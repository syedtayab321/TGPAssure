from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QScrollArea, QVBoxLayout, QWidget

from ui.feature_registry import FeatureDetail


class FeatureDetailsDialog(QDialog):
    def __init__(self, detail: FeatureDetail, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Feature Details — {detail.title}")
        self.setMinimumSize(560, 430)
        root = QVBoxLayout(self)
        title = QLabel(detail.title)
        title.setObjectName("dialogTitle")
        font = title.font(); font.setPointSize(max(font.pointSize(), 14)); font.setBold(True); title.setFont(font)
        root.addWidget(title)

        scroll = QScrollArea(self); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame)
        body = QWidget(scroll); layout = QVBoxLayout(body); layout.setSpacing(14)
        for heading, text in (
            ("Purpose", detail.summary),
            ("When to use it", detail.use_case),
            ("Requirements", detail.prerequisites),
            ("How it works", detail.workflow),
            ("Calculation / method", detail.method),
            ("Result", detail.output),
        ):
            if not text:
                continue
            h = QLabel(heading); f = h.font(); f.setBold(True); h.setFont(f)
            h.setStyleSheet("color:#0B5D8A;font-size:10pt;")
            p = QLabel(text); p.setWordWrap(True); p.setTextInteractionFlags(Qt.TextSelectableByMouse)
            layout.addWidget(h); layout.addWidget(p)
        layout.addStretch(1); scroll.setWidget(body); root.addWidget(scroll, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close, parent=self); buttons.rejected.connect(self.reject); buttons.accepted.connect(self.accept)
        root.addWidget(buttons)
        self.setStyleSheet("QDialog{background:#F4F8FC;} QLabel{background:transparent;} QPushButton{min-width:90px;}")
