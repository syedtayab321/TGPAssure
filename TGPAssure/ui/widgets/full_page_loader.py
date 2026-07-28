from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class FullPageLoader(QFrame):
    """Blocking full-window activity overlay used for long foreground operations.

    The loader supports determinate and indeterminate progress, an optional cancel
    action, an elapsed-time indicator, and a lightweight animated status label.
    It intentionally lives directly under the main window so it can cover the
    ribbon, workspace, docks, and status bar while a blocking task is active.
    """

    cancel_requested = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("fullPageLoader")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self._base_message = "Please wait"
        self._animation_step = 0
        self._started_at: datetime | None = None
        self._cancel_callback: Optional[Callable[[], None]] = None
        self._cancel_pending = False

        self.setStyleSheet(
            "QFrame#fullPageLoader{background:rgba(7,19,30,205);border:0;}"
            "QFrame#fullPageLoaderCard{background:rgba(18,42,59,250);"
            "border:1px solid rgba(151,187,211,190);border-radius:12px;}"
            "QLabel#fullPageLoaderEyebrow{color:#8FCBE8;background:transparent;"
            "font-size:8px;font-weight:700;letter-spacing:1px;}"
            "QLabel#fullPageLoaderTitle{color:#FFFFFF;background:transparent;"
            "font-size:16px;font-weight:700;}"
            "QLabel#fullPageLoaderMessage{color:#DDEAF2;background:transparent;"
            "font-size:10px;}"
            "QLabel#fullPageLoaderElapsed{color:#9EB4C2;background:transparent;"
            "font-size:8px;}"
            "QProgressBar{background:#263B4B;border:1px solid #67869B;"
            "border-radius:5px;color:#FFFFFF;text-align:center;min-height:18px;}"
            "QProgressBar::chunk{background:#25A8D6;border-radius:4px;}"
            "QPushButton#fullPageLoaderCancel{background:#314B5C;color:#FFFFFF;"
            "border:1px solid #67869B;border-radius:5px;padding:5px 18px;"
            "font-size:9px;font-weight:600;}"
            "QPushButton#fullPageLoaderCancel:hover{background:#3C5B70;}"
            "QPushButton#fullPageLoaderCancel:disabled{color:#8DA0AC;background:#263B4B;}"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addStretch(1)

        row = QHBoxLayout()
        row.addStretch(1)
        card = QFrame(self)
        card.setObjectName("fullPageLoaderCard")
        card.setMinimumWidth(410)
        card.setMaximumWidth(590)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 24, 32, 24)
        card_layout.setSpacing(10)

        eyebrow = QLabel("TGPASSURE • PROCESSING", card)
        eyebrow.setObjectName("fullPageLoaderEyebrow")
        eyebrow.setAlignment(Qt.AlignCenter)

        self.title_label = QLabel("Loading", card)
        self.title_label.setObjectName("fullPageLoaderTitle")
        self.title_label.setAlignment(Qt.AlignCenter)

        self.message_label = QLabel("Please wait…", card)
        self.message_label.setObjectName("fullPageLoaderMessage")
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setWordWrap(True)
        self.message_label.setMinimumHeight(34)

        self.progress_bar = QProgressBar(card)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(True)

        self.elapsed_label = QLabel("", card)
        self.elapsed_label.setObjectName("fullPageLoaderElapsed")
        self.elapsed_label.setAlignment(Qt.AlignCenter)

        self.cancel_button = QPushButton("Cancel Task", card)
        self.cancel_button.setObjectName("fullPageLoaderCancel")
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self._request_cancel)

        card_layout.addWidget(eyebrow)
        card_layout.addWidget(self.title_label)
        card_layout.addWidget(self.message_label)
        card_layout.addWidget(self.progress_bar)
        card_layout.addWidget(self.elapsed_label)
        card_layout.addWidget(self.cancel_button, 0, Qt.AlignCenter)
        row.addWidget(card)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)

        self._timer = QTimer(self)
        self._timer.setInterval(400)
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
        self.show()
        self.raise_()
        self.setFocus(Qt.OtherFocusReason)
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
        if not self._timer.isActive():
            self._timer.start()

    def finish(self) -> None:
        self._timer.stop()
        self._cancel_callback = None
        self._cancel_pending = False
        self._started_at = None
        self.hide()
        parent = self.parentWidget()
        if parent is not None:
            parent.setFocus(Qt.OtherFocusReason)

    def sync_geometry(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
            if self.isVisible():
                self.raise_()

    def _set_progress(self, progress: Optional[int]) -> None:
        if progress is None:
            self.progress_bar.setRange(0, 0)
            self.progress_bar.setFormat("Working…")
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
        suffix = "." * self._animation_step
        base = self._base_message.rstrip(". …")
        self.message_label.setText(f"{base}{suffix}")

    def _refresh_elapsed(self) -> None:
        if self._started_at is None:
            self.elapsed_label.clear()
            return
        seconds = max(0, int((datetime.now() - self._started_at).total_seconds()))
        minutes, seconds = divmod(seconds, 60)
        if minutes:
            text = f"Elapsed {minutes:d}m {seconds:02d}s"
        else:
            text = f"Elapsed {seconds:d}s"
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
