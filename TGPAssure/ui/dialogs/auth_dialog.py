from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.auth import AuthError, LicenseService, NetworkUnavailable


@dataclass(frozen=True)
class _AuthRequest:
    mode: str
    name: str
    email: str
    password: str


class _AuthWorker(QObject):
    succeeded = Signal()
    failed = Signal(str, str)
    finished = Signal()

    def __init__(self, license_service: LicenseService, request: _AuthRequest) -> None:
        super().__init__()
        self._license_service = license_service
        self._request = request

    @Slot()
    def run(self) -> None:
        try:
            if self._request.mode == "login":
                self._license_service.login(self._request.email, self._request.password)
            else:
                self._license_service.register(
                    self._request.name,
                    self._request.email,
                    self._request.password,
                )
            self.succeeded.emit()
        except NetworkUnavailable as exc:
            self.failed.emit("network", str(exc))
        except AuthError as exc:
            self.failed.emit("auth", str(exc))
        except Exception as exc:
            self.failed.emit("unexpected", str(exc))
        finally:
            self.finished.emit()


class AuthDialog(QDialog):
    def __init__(self, license_service: LicenseService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.license_service = license_service
        self._auth_thread: QThread | None = None
        self._auth_worker: _AuthWorker | None = None
        self._busy = False
        self._loader_base_text = ""
        self._loader_ticks = 0
        self._loader_timer = QTimer(self)
        self._loader_timer.setInterval(360)
        self._loader_timer.timeout.connect(self._animate_loader_text)

        self.setWindowTitle("TGPAssure Account")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setMinimumHeight(470)
        self.resize(560, 520)
        self._apply_poppins_font()
        self._build_ui()

    def _apply_poppins_font(self) -> None:
        font = QFont("Poppins")
        font.setPointSize(10)
        self.setFont(font)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 18)
        root.setSpacing(14)

        header = QFrame()
        header.setObjectName("authHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(18, 16, 18, 16)
        header_layout.setSpacing(5)
        title = QLabel("TGPAssure Secure Login")
        title.setObjectName("authTitle")
        subtitle = QLabel("Use email and password. Account creation, payment and license activation require internet access.")
        subtitle.setWordWrap(True)
        subtitle.setObjectName("authSubtitle")
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        root.addWidget(header)

        toggle = QHBoxLayout()
        toggle.setSpacing(8)
        self.login_tab = QPushButton("Login")
        self.create_tab = QPushButton("Create Account")
        self.login_tab.setCheckable(True)
        self.create_tab.setCheckable(True)
        self.login_tab.setChecked(True)
        self.login_tab.clicked.connect(lambda: self._set_mode(0))
        self.create_tab.clicked.connect(lambda: self._set_mode(1))
        toggle.addWidget(self.login_tab)
        toggle.addWidget(self.create_tab)
        root.addLayout(toggle)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._login_page())
        self.stack.addWidget(self._create_page())
        root.addWidget(self.stack, 1)

        self.loader_card = QFrame()
        self.loader_card.setObjectName("authLoader")
        loader_layout = QHBoxLayout(self.loader_card)
        loader_layout.setContentsMargins(14, 12, 14, 12)
        loader_layout.setSpacing(12)
        self.loader_label = QLabel("Processing")
        self.loader_label.setObjectName("loaderLabel")
        self.loader_label.setMinimumWidth(185)
        self.loader_bar = QProgressBar()
        self.loader_bar.setRange(0, 0)
        self.loader_bar.setTextVisible(False)
        loader_layout.addWidget(self.loader_label)
        loader_layout.addWidget(self.loader_bar, 1)
        root.addWidget(self.loader_card)
        self.loader_card.setVisible(False)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setObjectName("authStatus")
        root.addWidget(self.status)
        self.status.setVisible(False)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.cancel_btn = QPushButton("Exit")
        self.cancel_btn.clicked.connect(self.reject)
        self.submit_btn = QPushButton("Login")
        self.submit_btn.setDefault(True)
        self.submit_btn.clicked.connect(self._submit)
        actions.addWidget(self.cancel_btn)
        actions.addWidget(self.submit_btn)
        root.addLayout(actions)

        self.setStyleSheet(
            """
            QDialog, QWidget {
                font-family: "Poppins", "Segoe UI", Arial, sans-serif;
                color: #1C2633;
            }
            QDialog { background: #F4F7FB; }
            QFrame#authHeader {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #073B5C,stop:1 #0D82B8);
                border-radius: 13px;
            }
            QLabel#authTitle {
                font-size: 22px;
                font-weight: 800;
                color: #FFFFFF;
                letter-spacing: 0.2px;
            }
            QLabel#authSubtitle {
                color: #E6F4FF;
                font-size: 12px;
                line-height: 16px;
            }
            QLabel#authStatus {
                color: #8A4A00;
                background: #FFF7E6;
                border: 1px solid #FFD58A;
                border-radius: 8px;
                padding: 9px 10px;
                font-weight: 500;
            }
            QFrame#authCard {
                background: #FFFFFF;
                border: 1px solid #D9E4EF;
                border-radius: 12px;
            }
            QFrame#authLoader {
                background: #EAF6FD;
                border: 1px solid #9ED4EF;
                border-radius: 10px;
            }
            QLabel#loaderLabel {
                color: #073B5C;
                font-weight: 700;
            }
            QLineEdit {
                min-height: 34px;
                border: 1px solid #C8D6E3;
                border-radius: 8px;
                padding: 4px 10px;
                background: #FFFFFF;
                selection-background-color: #0C7DB3;
            }
            QLineEdit:focus {
                border: 1px solid #0C7DB3;
                background: #FBFEFF;
            }
            QLineEdit:disabled {
                color: #6C7A87;
                background: #EEF3F7;
            }
            QPushButton {
                min-height: 33px;
                border-radius: 8px;
                padding: 5px 14px;
                border: 1px solid #B8C9D8;
                background: #FFFFFF;
                font-weight: 600;
            }
            QPushButton:hover { background: #EDF5FC; }
            QPushButton:checked {
                background: #0C7DB3;
                color: #FFFFFF;
                border-color: #0C7DB3;
                font-weight: 800;
            }
            QPushButton:default {
                background: #0C7DB3;
                color: #FFFFFF;
                border-color: #0C7DB3;
                font-weight: 800;
            }
            QPushButton:disabled {
                color: #7C8A96;
                background: #E5EBF0;
                border-color: #CDD8E2;
            }
            QProgressBar {
                min-height: 10px;
                max-height: 10px;
                border: 1px solid #B9DDEC;
                border-radius: 5px;
                background: #FFFFFF;
            }
            QProgressBar::chunk {
                border-radius: 5px;
                background: #0C7DB3;
            }
            """
        )
        self.login_email.setFocus(Qt.OtherFocusReason)

    def _login_page(self) -> QWidget:
        card = QFrame()
        card.setObjectName("authCard")
        layout = QFormLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(13)
        layout.setLabelAlignment(Qt.AlignLeft)
        self.login_email = QLineEdit()
        self.login_email.setPlaceholderText("name@company.com")
        self.login_password = QLineEdit()
        self.login_password.setEchoMode(QLineEdit.Password)
        self.login_password.setPlaceholderText("Password")
        self.login_password.returnPressed.connect(self._submit)
        layout.addRow("Email", self.login_email)
        layout.addRow("Password", self.login_password)
        return card

    def _create_page(self) -> QWidget:
        card = QFrame()
        card.setObjectName("authCard")
        layout = QFormLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(13)
        layout.setLabelAlignment(Qt.AlignLeft)
        self.create_name = QLineEdit()
        self.create_name.setPlaceholderText("Full name")
        self.create_email = QLineEdit()
        self.create_email.setPlaceholderText("name@company.com")
        self.create_password = QLineEdit()
        self.create_password.setEchoMode(QLineEdit.Password)
        self.create_password.setPlaceholderText("Minimum 6 characters")
        self.create_password.returnPressed.connect(self._submit)
        layout.addRow("Name", self.create_name)
        layout.addRow("Email", self.create_email)
        layout.addRow("Password", self.create_password)
        return card

    def _set_mode(self, index: int) -> None:
        if self._busy:
            return
        self.stack.setCurrentIndex(index)
        self.login_tab.setChecked(index == 0)
        self.create_tab.setChecked(index == 1)
        self.submit_btn.setText("Login" if index == 0 else "Create Account")
        self.status.setVisible(False)
        if index == 0:
            self.login_email.setFocus(Qt.OtherFocusReason)
        else:
            self.create_name.setFocus(Qt.OtherFocusReason)

    def _submit(self) -> None:
        if self._busy:
            return
        self.status.setVisible(False)
        request = self._build_request()
        if request is None:
            return
        self._start_auth(request)

    def _build_request(self) -> _AuthRequest | None:
        if self.stack.currentIndex() == 0:
            email = self.login_email.text().strip()
            password = self.login_password.text()
            if not email or not password:
                self._show_status("Enter email and password.")
                return None
            return _AuthRequest("login", "", email, password)

        name = self.create_name.text().strip()
        email = self.create_email.text().strip()
        password = self.create_password.text()
        if not name or not email or not password:
            self._show_status("Enter name, email and password.")
            return None
        if len(password) < 6:
            self._show_status("Password must be at least 6 characters.")
            return None
        return _AuthRequest("create", name, email, password)

    def _start_auth(self, request: _AuthRequest) -> None:
        self._set_loading(True, "Logging in" if request.mode == "login" else "Creating account")
        self._auth_thread = QThread(self)
        self._auth_worker = _AuthWorker(self.license_service, request)
        self._auth_worker.moveToThread(self._auth_thread)
        self._auth_thread.started.connect(self._auth_worker.run)
        self._auth_worker.succeeded.connect(self._on_auth_success)
        self._auth_worker.failed.connect(self._on_auth_failed)
        self._auth_worker.finished.connect(self._auth_thread.quit)
        self._auth_worker.finished.connect(self._auth_worker.deleteLater)
        self._auth_thread.finished.connect(self._on_auth_thread_finished)
        self._auth_thread.finished.connect(self._auth_thread.deleteLater)
        self._auth_thread.start()

    @Slot()
    def _on_auth_success(self) -> None:
        self._set_loading(False)
        self.accept()

    @Slot(str, str)
    def _on_auth_failed(self, category: str, message: str) -> None:
        self._set_loading(False)
        if category == "unexpected":
            QMessageBox.critical(self, "Login Error", message)
        else:
            self._show_status(message)

    @Slot()
    def _on_auth_thread_finished(self) -> None:
        self._auth_worker = None
        self._auth_thread = None

    def _set_loading(self, loading: bool, message: str = "") -> None:
        self._busy = loading
        self._loader_base_text = message
        self._loader_ticks = 0
        self.loader_label.setText(message if message else "Processing")
        self.loader_card.setVisible(loading)
        self.status.setVisible(False if loading else self.status.isVisible())
        if loading:
            self._loader_timer.start()
        else:
            self._loader_timer.stop()
        widgets = [
            self.login_tab,
            self.create_tab,
            self.login_email,
            self.login_password,
            self.create_name,
            self.create_email,
            self.create_password,
            self.cancel_btn,
            self.submit_btn,
        ]
        for widget in widgets:
            widget.setEnabled(not loading)
        self.submit_btn.setText("Please wait" if loading else ("Login" if self.stack.currentIndex() == 0 else "Create Account"))
        self.setCursor(Qt.WaitCursor if loading else Qt.ArrowCursor)

    def _animate_loader_text(self) -> None:
        if not self._busy:
            return
        self._loader_ticks = (self._loader_ticks + 1) % 4
        dots = "." * self._loader_ticks
        self.loader_label.setText(f"{self._loader_base_text}{dots}")

    def _show_status(self, message: str) -> None:
        self.status.setText(message)
        self.status.setVisible(True)

    def reject(self) -> None:
        if self._busy:
            self._show_status("Please wait until the current account request finishes.")
            return
        super().reject()
