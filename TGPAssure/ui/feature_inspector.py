from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget

from ui.feature_registry import FeatureDetail


class FeatureInspector(QWidget):
    """Persistent, non-modal explanation panel for the last selected ribbon command."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("featureInspector")
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        self.title = QLabel("Feature Guide")
        self.title.setObjectName("featureInspectorTitle")
        root.addWidget(self.title)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.body = QWidget(self.scroll)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(2, 2, 6, 2)
        self.body_layout.setSpacing(10)
        self.scroll.setWidget(self.body)
        root.addWidget(self.scroll, 1)
        self.set_detail(FeatureDetail(
            "Feature Guide",
            "Select any ribbon command to see what it does, why it is used, its inputs, calculation logic and outputs.",
            "No prerequisite.",
            "The panel updates automatically when a ribbon command is selected.",
            "A concise, auditable explanation of the selected feature.",
            method="",
            use_case="Use this as the in-application operating guide.",
        ))

    def set_detail(self, detail: FeatureDetail) -> None:
        self.title.setText(detail.title)
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        rows = [
            ("Purpose", detail.summary),
            ("When to use it", detail.use_case),
            ("Requirements", detail.prerequisites),
            ("How it works", detail.workflow),
            ("Calculation / method", detail.method),
            ("Result", detail.output),
        ]
        for heading, text in rows:
            if not text:
                continue
            h = QLabel(heading)
            h.setObjectName("featureInspectorHeading")
            t = QLabel(text)
            t.setObjectName("featureInspectorText")
            t.setWordWrap(True)
            t.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.body_layout.addWidget(h)
            self.body_layout.addWidget(t)
        self.body_layout.addStretch(1)
