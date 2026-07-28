from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from core.infrastructure.resource_paths import resource_path


class EmptyWorkspace(QWidget):
    """Neutral startup canvas shown when no document/viewer is open."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("emptyWorkspace")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.watermark = QLabel(self)
        self.watermark.setObjectName("workspaceWatermark")
        self.watermark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.watermark.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        logo_path = resource_path("assets", "logo", "logo.png")
        pixmap = QPixmap(str(logo_path))
        if not pixmap.isNull():
            self.watermark.setPixmap(
                pixmap.scaled(160, 160, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            )

        self.name_label = QLabel("TGPAssure", self)
        self.name_label.setObjectName("workspaceWatermarkText")
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        layout.addStretch(1)
        layout.addWidget(self.watermark, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.name_label, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)