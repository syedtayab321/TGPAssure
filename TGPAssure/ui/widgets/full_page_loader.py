from __future__ import annotations

from datetime import datetime
from math import cos, sin, pi
from typing import Callable, Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QConicalGradient, QFont, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class _GeoPulseSpinner(QWidget):
    """Small animated geophysical-themed spinner used inside the full page loader."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(118, 118)
        self._angle = 0
        self._pulse = 0
        self._timer = QTimer(self)
        self._timer.setInterval(38)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        self._angle = (self._angle + 5) % 360
        self._pulse = (self._pulse + 1) % 80
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(8, 8, -8, -8)
        cx, cy = rect.center().x(), rect.center().y()
        radius = min(rect.width(), rect.height()) / 2

        glow = QRadialGradient(cx, cy, radius)
        glow.setColorAt(0.0, QColor(39, 188, 226, 72))
        glow.setColorAt(0.55, QColor(16, 94, 124, 42))
        glow.setColorAt(1.0, QColor(5, 20, 34, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(rect)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(98, 150, 177, 110), 1.2))
        for scale in (0.42, 0.66, 0.90):
            r = radius * scale
            painter.drawEllipse(cx - r, cy - r, 2 * r, 2 * r)
        for step in range(0, 360, 45):
            a = step * pi / 180.0
            painter.drawLine(cx, cy, cx + cos(a) * radius * 0.90, cy + sin(a) * radius * 0.90)

        gradient = QConicalGradient(cx, cy, -self._angle)
        gradient.setColorAt(0.00, QColor(34, 211, 238, 20))
        gradient.setColorAt(0.28, QColor(34, 211, 238, 225))
        gradient.setColorAt(0.50, QColor(250, 204, 21, 180))
        gradient.setColorAt(1.00, QColor(34, 211, 238, 20))
        painter.setPen(QPen(gradient, 6.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(rect, int(-self._angle * 16), int(128 * 16))

        painter.setPen(QPen(QColor(255, 255, 255, 210), 2.0))
        sweep = self._angle * pi / 180.0
        painter.drawLine(cx, cy, cx + cos(sweep) * radius * 0.78, cy - sin(sweep) * radius * 0.78)

        pulse_radius = radius * (0.14 + 0.30 * (self._pulse / 79.0))
        painter.setPen(QPen(QColor(34, 211, 238, max(20, 155 - self._pulse * 2)), 2.0))
        painter.drawEllipse(cx - pulse_radius, cy - pulse_radius, 2 * pulse_radius, 2 * pulse_radius)

        painter.setPen(QColor("#E8F7FC"))
        font = QFont(painter.font())
        font.setBold(True)
        font.setPointSize(9)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "TGP")


class FullPageLoader(QFrame):
    """Blocking full-window activity overlay for foreground operations."""

    cancel_requested = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("fullPageLoader")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self._base_message = "Please wait"
        self._animation_step = 0
        self._started_at: datetime | None = None
        self._cancel_callback: Optional[Callable[[], None]] = None
        self._cancel_pending = False

        self.setStyleSheet(
            "QFrame#fullPageLoader{background:qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 rgba(2,15,27,232), stop:.55 rgba(5,43,60,225), stop:1 rgba(2,15,27,232));border:0;}"
            "QFrame#fullPageLoaderCard{background:rgba(9,31,48,248);border:1px solid rgba(118,205,236,165);border-radius:22px;}"
            "QLabel#fullPageLoaderEyebrow{color:#7DD3FC;background:transparent;font-size:9px;font-weight:900;letter-spacing:1.6px;}"
            "QLabel#fullPageLoaderTitle{color:#FFFFFF;background:transparent;font-size:22px;font-weight:900;}"
            "QLabel#fullPageLoaderMessage{color:#D7EDF7;background:transparent;font-size:12px;font-weight:700;}"
            "QLabel#fullPageLoaderElapsed{color:#98BACC;background:transparent;font-size:10px;font-weight:700;}"
            "QProgressBar{background:#102D41;border:1px solid #497D96;border-radius:8px;color:#E9F8FE;text-align:center;min-height:20px;font-weight:900;}"
            "QProgressBar::chunk{background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #0EA5E9, stop:.5 #22D3EE, stop:1 #FACC15);border-radius:7px;}"
            "QPushButton#fullPageLoaderCancel{background:#203F55;color:#FFFFFF;border:1px solid #6AA8C4;border-radius:8px;padding:6px 20px;font-size:10px;font-weight:900;}"
            "QPushButton#fullPageLoaderCancel:hover{background:#2B526D;}"
            "QPushButton#fullPageLoaderCancel:disabled{color:#8DA0AC;background:#263B4B;}"
        )

        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._fade = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade.setDuration(180)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.addStretch(1)

        row = QHBoxLayout()
        row.addStretch(1)
        card = QFrame(self)
        card.setObjectName("fullPageLoaderCard")
        card.setMinimumWidth(500)
        card.setMaximumWidth(680)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(38, 30, 38, 30)
        card_layout.setSpacing(13)

        self.spinner = _GeoPulseSpinner(card)
        eyebrow = QLabel("TGPASSURE • GEOPHYSICAL PROCESSING", card)
        eyebrow.setObjectName("fullPageLoaderEyebrow")
        eyebrow.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.title_label = QLabel("Loading", card)
        self.title_label.setObjectName("fullPageLoaderTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.message_label = QLabel("Please wait…", card)
        self.message_label.setObjectName("fullPageLoaderMessage")
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message_label.setWordWrap(True)
        self.message_label.setMinimumHeight(34)

        self.progress_bar = QProgressBar(card)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(True)

        self.elapsed_label = QLabel("", card)
        self.elapsed_label.setObjectName("fullPageLoaderElapsed")
        self.elapsed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.cancel_button = QPushButton("Cancel Task", card)
        self.cancel_button.setObjectName("fullPageLoaderCancel")
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self._request_cancel)

        card_layout.addWidget(self.spinner, 0, Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(eyebrow)
        card_layout.addWidget(self.title_label)
        card_layout.addWidget(self.message_label)
        card_layout.addWidget(self.progress_bar)
        card_layout.addWidget(self.elapsed_label)
        card_layout.addWidget(self.cancel_button, 0, Qt.AlignmentFlag.AlignCenter)
        row.addWidget(card)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)

        self._timer = QTimer(self)
        self._timer.setInterval(360)
        self._timer.timeout.connect(self._tick)
        self.hide()

    def show_loader(
        self,
        title: str = "Loading",
        message: str = "Please wait…",
        progress: Optional[int] = None,
        *,
        cancellable: bool = False,
        cancel_callback: Optional[Callable[[], None]] = None,
    ) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        self.title_label.setText(str(title))
        self._base_message = str(message or "Please wait")
        self._animation_step = 0
        self._started_at = datetime.now()
        self._cancel_pending = False
        self._cancel_callback = cancel_callback
        self.cancel_button.setText("Cancel Task")
        self.cancel_button.setEnabled(True)
        self.cancel_button.setVisible(bool(cancellable or cancel_callback is not None))
        self._set_progress(progress)
        self._refresh_message()
        self._refresh_elapsed()
        self._opacity.setOpacity(0.0)
        self.show()
        self.raise_()
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self.spinner.start()
        self._fade.stop()
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
        if not self._timer.isActive():
            self._timer.start()

    def update_loader(
        self,
        progress: Optional[int] = None,
        message: Optional[str] = None,
        *,
        title: Optional[str] = None,
        cancellable: Optional[bool] = None,
        cancel_callback: Optional[Callable[[], None]] = None,
    ) -> None:
        if title is not None:
            self.title_label.setText(str(title))
        if message is not None:
            self._base_message = str(message or "Working")
        if cancel_callback is not None:
            self._cancel_callback = cancel_callback
            self.cancel_button.setVisible(True)
        elif cancellable is False:
            self._cancel_callback = None
        if cancellable is not None:
            self.cancel_button.setVisible(bool(cancellable))
        self._set_progress(progress)
        self._refresh_message()
        if not self.isVisible():
            self.show()
        self.raise_()
        self.spinner.start()
        if not self._timer.isActive():
            self._timer.start()

    def finish(self) -> None:
        self._timer.stop()
        self.spinner.stop()
        self._cancel_callback = None
        self._cancel_pending = False
        self._started_at = None
        self.hide()
        parent = self.parentWidget()
        if parent is not None:
            parent.setFocus(Qt.FocusReason.OtherFocusReason)

    def sync_geometry(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
            if self.isVisible():
                self.raise_()

    def _set_progress(self, progress: Optional[int]) -> None:
        if progress is None:
            self.progress_bar.setRange(0, 0)
            self.progress_bar.setFormat("Processing")
            return
        value = max(0, min(100, int(progress)))
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(value)
        self.progress_bar.setFormat("%p%")

    def _tick(self) -> None:
        if not self.isVisible():
            return
        self._animation_step = (self._animation_step + 1) % 4
        self._refresh_message()
        self._refresh_elapsed()
        self.raise_()

    def _refresh_message(self) -> None:
        suffix = "•" * self._animation_step
        base = self._base_message.rstrip(". …•")
        self.message_label.setText(f"{base} {suffix}".rstrip())

    def _refresh_elapsed(self) -> None:
        if self._started_at is None:
            self.elapsed_label.clear()
            return
        seconds = max(0, int((datetime.now() - self._started_at).total_seconds()))
        minutes, seconds = divmod(seconds, 60)
        text = f"Elapsed {minutes:d}m {seconds:02d}s" if minutes else f"Elapsed {seconds:d}s"
        if self._cancel_pending:
            text += "  •  Cancellation requested"
        self.elapsed_label.setText(text)

    def _request_cancel(self) -> None:
        if self._cancel_pending:
            return
        self._cancel_pending = True
        self.cancel_button.setEnabled(False)
        self.cancel_button.setText("Cancelling…")
        self._base_message = "Requesting cancellation"
        self._refresh_message()
        self._refresh_elapsed()
        callback = self._cancel_callback
        if callback is not None:
            try:
                callback()
            except Exception:
                pass
        self.cancel_requested.emit()
