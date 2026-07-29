from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QApplication,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.auth import AuthError, LicenseService, NetworkUnavailable
from core.auth.plans import (
    ALL_FEATURE_KEYS,
    FEATURE_BY_KEY,
    FEATURES,
    MODULE_TITLES,
    PLAN_BY_KEY,
    PLANS,
    features_for_plan,
    monthly_total_for_features,
)


class SubscriptionDialog(QDialog):
    license_changed = Signal()

    def __init__(
        self,
        license_service: LicenseService,
        parent: QWidget | None = None,
        *,
        focus_feature: str | None = None,
        first_login: bool = False,
    ) -> None:
        super().__init__(parent)
        self.license_service = license_service
        self.focus_feature = focus_feature if focus_feature in FEATURE_BY_KEY else None
        self.first_login = first_login
        self.feature_checks: dict[str, QCheckBox] = {}
        self.module_tabs: dict[str, QWidget] = {}
        self.feature_rows: dict[str, QFrame] = {}
        self.setWindowTitle("TGPAssure Subscription")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, False)
        font = QFont("Poppins")
        font.setPointSize(9)
        self.setFont(font)
        self.setMinimumSize(520, 520)
        self.resize(680, 680)
        self.setMaximumSize(720, 720)
        self.setSizeGripEnabled(False)
        self.setWindowFlag(Qt.MSWindowsFixedSizeDialogHint, True)
        self._build_ui()
        self._load_current_state()
        self._select_focus_tab()
        self._recalculate()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._resize_and_center()
        QTimer.singleShot(0, self._resize_and_center)
        QTimer.singleShot(120, self._resize_and_center)

    def _resize_and_center(self) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return

        available = screen.availableGeometry()
        margin = 42
        max_side = min(
            700,
            int(available.width() - margin * 2),
            int(available.height() - margin * 2),
        )
        if max_side < 520:
            side = max(380, max_side)
        else:
            side = max(560, max_side)

        self.setMinimumSize(min(520, side), min(520, side))
        self.setMaximumSize(side, side)
        self.setFixedSize(side, side)

        frame = self.frameGeometry()
        frame.moveCenter(available.center())
        top_left = frame.topLeft()
        if top_left.x() < available.left() + margin:
            top_left.setX(available.left() + margin)
        if top_left.y() < available.top() + margin:
            top_left.setY(available.top() + margin)
        if top_left.x() + frame.width() > available.right() - margin:
            top_left.setX(available.right() - frame.width() - margin)
        if top_left.y() + frame.height() > available.bottom() - margin:
            top_left.setY(available.bottom() - frame.height() - margin)
        self.move(top_left)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 10)
        root.setSpacing(8)

        user = self.license_service.user
        account_text = f"{user.name}  •  {user.email}" if user else "Not signed in"

        header = QFrame()
        header.setObjectName("subHeader")
        header.setFixedHeight(86)
        header_layout = QGridLayout(header)
        header_layout.setContentsMargins(14, 9, 14, 8)
        header_layout.setHorizontalSpacing(12)
        header_layout.setVerticalSpacing(4)

        title = QLabel("Subscription & Module Access")
        title.setObjectName("subTitle")
        subtitle = QLabel(
            "Choose a plan or select only the required modules. Locked modules unlock after payment/license activation."
        )
        subtitle.setObjectName("subSubtitle")
        subtitle.setWordWrap(True)
        self.account_label = QLabel(account_text)
        self.account_label.setObjectName("accountLabel")
        internet_label = QLabel("Internet required for account creation, payment and Firebase license refresh.")
        internet_label.setObjectName("internetLabel")
        internet_label.setWordWrap(True)

        header_layout.addWidget(title, 0, 0, 1, 2)
        header_layout.addWidget(self.account_label, 0, 2, Qt.AlignRight | Qt.AlignVCenter)
        header_layout.addWidget(subtitle, 1, 0, 1, 3)
        header_layout.addWidget(internet_label, 2, 0, 1, 3)
        root.addWidget(header)

        plan_card = QFrame()
        plan_card.setObjectName("card")
        plan_card.setFixedHeight(78)
        plan_layout = QGridLayout(plan_card)
        plan_layout.setContentsMargins(12, 7, 12, 7)
        plan_layout.setHorizontalSpacing(10)
        plan_layout.setVerticalSpacing(4)

        plan_label = QLabel("Plan")
        plan_label.setObjectName("fieldLabel")
        self.plan_combo = QComboBox()
        self.plan_combo.setObjectName("planCombo")
        for plan in PLANS:
            self.plan_combo.addItem(
                f"{plan.title} — {self._money(plan.monthly_pkr)}/month" if plan.monthly_pkr else plan.title,
                plan.key,
            )
        self.plan_combo.currentIndexChanged.connect(self._on_plan_changed)

        self.plan_description = QLabel("")
        self.plan_description.setObjectName("planDescription")
        self.plan_description.setWordWrap(True)

        self.total_label = QLabel("Total: PKR 0 / month")
        self.total_label.setObjectName("totalLabel")
        self.selection_label = QLabel("0 selected")
        self.selection_label.setObjectName("selectionLabel")

        plan_layout.addWidget(plan_label, 0, 0)
        plan_layout.addWidget(self.plan_combo, 0, 1)
        plan_layout.addWidget(self.total_label, 0, 2, Qt.AlignRight | Qt.AlignVCenter)
        plan_layout.addWidget(self.plan_description, 1, 0, 1, 2)
        plan_layout.addWidget(self.selection_label, 1, 2, Qt.AlignRight | Qt.AlignVCenter)
        plan_layout.setColumnStretch(1, 1)
        plan_layout.setColumnStretch(2, 0)
        root.addWidget(plan_card)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("moduleTabs")
        self._build_feature_tabs()
        root.addWidget(self.tabs, 1)

        self.dev_box = QFrame()
        self.dev_box.setObjectName("devBox")
        self.dev_box.setFixedHeight(42)
        dev_layout = QHBoxLayout(self.dev_box)
        dev_layout.setContentsMargins(10, 6, 10, 6)
        dev_layout.setSpacing(10)
        dev_label = QLabel("Development mode: approve selected access without Stripe.")
        dev_label.setObjectName("devLabel")
        dev_label.setWordWrap(False)
        self.dev_approve_btn = QPushButton("Mark Payment Paid")
        self.dev_approve_btn.setObjectName("devButton")
        self.dev_approve_btn.clicked.connect(self._approve_development)
        dev_layout.addWidget(dev_label, 1)
        dev_layout.addWidget(self.dev_approve_btn)
        self.dev_box.setVisible(self.license_service.is_development)
        root.addWidget(self.dev_box)

        self.status = QLabel("")
        self.status.setObjectName("subStatus")
        self.status.setWordWrap(True)
        self.status.setVisible(False)
        root.addWidget(self.status)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.continue_free_btn = QPushButton("Continue Free")
        self.continue_free_btn.clicked.connect(self._continue_free)
        self.refresh_btn = QPushButton("Refresh License")
        self.refresh_btn.clicked.connect(self._refresh_license)
        self.checkout_btn = QPushButton("Pay with Stripe")
        self.checkout_btn.setObjectName("primaryButton")
        self.checkout_btn.setDefault(True)
        self.checkout_btn.clicked.connect(self._checkout)
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept if not self.first_login else self.reject)
        actions.addWidget(self.continue_free_btn)
        actions.addStretch(1)
        actions.addWidget(self.refresh_btn)
        actions.addWidget(self.checkout_btn)
        actions.addWidget(self.close_btn)
        root.addLayout(actions)

        self.setStyleSheet(
            """
            QDialog, QWidget {
                font-family: "Poppins", "Segoe UI", Arial, sans-serif;
                font-size: 8.5pt;
                color: #14283A;
            }
            QDialog { background: #F6F8FB; }
            QLabel { background: transparent; border: none; }
            QFrame#subHeader {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #072E44,stop:1 #0E7EAB);
                border-radius: 12px;
            }
            QLabel#subTitle {
                color: #FFFFFF;
                font-size: 13px;
                font-weight: 800;
                letter-spacing: 0.1px;
            }
            QLabel#subSubtitle { color: #E9F7FF; font-size: 8px; }
            QLabel#internetLabel { color: #BBDFF1; font-size: 8px; }
            QLabel#accountLabel {
                color: #FFFFFF;
                background: rgba(255,255,255,0.15);
                border: 1px solid rgba(255,255,255,0.30);
                border-radius: 10px;
                padding: 3px 9px;
                font-weight: 700;
                font-size: 8px;
            }
            QFrame#card {
                background: #FFFFFF;
                border: 1px solid #D9E4ED;
                border-radius: 10px;
            }
            QLabel#fieldLabel {
                color: #435A70;
                font-weight: 700;
                font-size: 8px;
            }
            QLabel#planDescription {
                color: #5E7183;
                font-size: 8px;
            }
            QLabel#totalLabel {
                color: #062F48;
                font-size: 13px;
                font-weight: 900;
            }
            QLabel#selectionLabel {
                color: #607385;
                font-size: 8px;
            }
            QComboBox#planCombo {
                min-height: 25px;
                border: 1px solid #B9CBD9;
                border-radius: 7px;
                padding: 1px 8px;
                background: #FFFFFF;
                color: #14283A;
            }
            QComboBox#planCombo:hover { border-color: #0E7EAB; }
            QTabWidget#moduleTabs::pane {
                border: 1px solid #D9E4ED;
                border-radius: 10px;
                background: #FFFFFF;
                top: -1px;
            }
            QTabBar::tab {
                background: #ECF3F8;
                color: #2F495F;
                border: 1px solid #D7E4EE;
                border-bottom: none;
                padding: 6px 10px;
                margin-right: 2px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-weight: 750;
                font-size: 8px;
            }
            QTabBar::tab:selected {
                background: #FFFFFF;
                color: #075D84;
                border-top: 3px solid #0E7EAB;
            }
            QTabBar::tab:hover { background: #F7FBFE; color: #064E71; }
            QFrame#featureRow {
                background: #FFFFFF;
                border: 1px solid #E0EAF2;
                border-radius: 10px;
            }
            QFrame#featureRow:hover { background: #F7FBFE; border-color: #B8D5E7; }
            QFrame#featureRow[selected="true"] {
                background: #EEF8FD;
                border: 1px solid #58B0D0;
            }
            QFrame#featureRow[focus="true"] {
                border: 2px solid #0E7EAB;
                background: #EDF9FF;
            }
            QFrame#featureRow[locked="true"] {
                background: #F8FAFC;
                border: 1px solid #E7EEF4;
            }
            QLabel#featureTitle { font-weight: 800; color: #12283B; font-size: 8.8px; }
            QLabel#featureDesc { color: #61778B; font-size: 8px; }
            QLabel#featurePrice { color: #075D84; font-weight: 900; font-size: 8px; }
            QLabel#moduleHint { color: #61758A; font-size: 8px; padding: 2px 2px; }
            QCheckBox#featureCheck { spacing: 0px; }
            QCheckBox#featureCheck::indicator {
                width: 17px;
                height: 17px;
                border-radius: 8px;
                border: 1px solid #AFC2D1;
                background: #FFFFFF;
            }
            QCheckBox#featureCheck::indicator:hover {
                border: 1px solid #0E7EAB;
                background: #F2FAFE;
            }
            QCheckBox#featureCheck::indicator:checked {
                border: 1px solid #0E7EAB;
                background: #0E7EAB;
            }
            QCheckBox#featureCheck::indicator:disabled {
                border: 1px solid #D7E1E9;
                background: #F1F4F7;
            }
            QFrame#devBox {
                background: #EFFAF2;
                border: 1px solid #A6DDB0;
                border-radius: 9px;
            }
            QLabel#devLabel { color: #245B2C; font-weight: 650; font-size: 8px; }
            QLabel#subStatus {
                color: #684900;
                background: #FFF7E6;
                border: 1px solid #FFD58A;
                border-radius: 8px;
                padding: 5px 8px;
                font-size: 8px;
            }
            QPushButton {
                min-height: 24px;
                border-radius: 7px;
                padding: 3px 9px;
                border: 1px solid #B8C9D8;
                background: #FFFFFF;
                font-weight: 650;
                color: #14283A;
            }
            QPushButton:hover { background: #EEF6FC; border-color: #0E7EAB; }
            QPushButton#primaryButton, QPushButton:default {
                background: #0E7EAB;
                color: #FFFFFF;
                border-color: #0E7EAB;
                font-weight: 850;
            }
            QPushButton#primaryButton:hover, QPushButton:default:hover { background: #086B96; }
            QPushButton#devButton { color: #245B2C; border-color: #8DCA99; }
            QScrollArea { background: #FFFFFF; border: none; }
            QScrollBar:vertical { width: 8px; background: #F1F5F8; }
            QScrollBar::handle:vertical { background: #BCD0DE; border-radius: 4px; min-height: 22px; }
            """
        )

    def _build_feature_tabs(self) -> None:
        grouped: dict[str, list] = defaultdict(list)
        for feature in FEATURES:
            grouped[feature.module].append(feature)

        for module_key, features in grouped.items():
            tab = QWidget()
            tab_layout = QVBoxLayout(tab)
            tab_layout.setContentsMargins(10, 9, 10, 9)
            tab_layout.setSpacing(7)

            hint = QLabel(
                "Select individual submodules for Modular Professional. Free and Enterprise plans are controlled automatically."
            )
            hint.setObjectName("moduleHint")
            hint.setWordWrap(True)
            tab_layout.addWidget(hint)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            content = QWidget()
            rows = QVBoxLayout(content)
            rows.setContentsMargins(0, 0, 0, 0)
            rows.setSpacing(5)

            for feature in features:
                row = QFrame()
                row.setObjectName("featureRow")
                row.setFixedHeight(46)
                row.setCursor(Qt.PointingHandCursor)
                row.setProperty("focus", feature.key == self.focus_feature)
                row_layout = QGridLayout(row)
                row_layout.setContentsMargins(8, 6, 8, 6)
                row_layout.setHorizontalSpacing(8)
                row_layout.setVerticalSpacing(2)

                check = QCheckBox()
                check.setObjectName("featureCheck")
                check.setToolTip(feature.description)
                check.stateChanged.connect(self._recalculate)
                self.feature_checks[feature.key] = check
                self.feature_rows[feature.key] = row

                title = QLabel(feature.title)
                title.setObjectName("featureTitle")
                desc = QLabel(feature.description)
                desc.setObjectName("featureDesc")
                desc.setWordWrap(True)
                price = QLabel(self._money(feature.monthly_pkr) + "/mo")
                price.setObjectName("featurePrice")

                row_layout.addWidget(check, 0, 0, 2, 1, Qt.AlignTop | Qt.AlignLeft)
                row_layout.addWidget(title, 0, 1)
                row_layout.addWidget(price, 0, 2, Qt.AlignRight | Qt.AlignVCenter)
                row_layout.addWidget(desc, 1, 1, 1, 2)
                row_layout.setColumnStretch(1, 1)
                row_layout.setColumnMinimumWidth(2, 86)
                row.mousePressEvent = lambda event, k=feature.key: self._toggle_feature(k)
                rows.addWidget(row)

            rows.addStretch(1)
            scroll.setWidget(content)
            tab_layout.addWidget(scroll, 1)
            self.module_tabs[module_key] = tab
            self.tabs.addTab(tab, MODULE_TITLES.get(module_key, module_key.title()))

    def _toggle_feature(self, key: str) -> None:
        check = self.feature_checks.get(key)
        if check is None or not check.isEnabled():
            return
        check.setChecked(not check.isChecked())

    def _refresh_row_styles(self) -> None:
        for key, row in self.feature_rows.items():
            check = self.feature_checks.get(key)
            selected = bool(check and check.isChecked())
            locked = bool(check and not check.isEnabled())
            row.setProperty("selected", selected)
            row.setProperty("locked", locked)
            row.style().unpolish(row)
            row.style().polish(row)
            row.update()

    def _select_focus_tab(self) -> None:
        if not self.focus_feature:
            return
        focus_module = FEATURE_BY_KEY[self.focus_feature].module
        tab = self.module_tabs.get(focus_module)
        if tab is None:
            return
        idx = self.tabs.indexOf(tab)
        if idx >= 0:
            self.tabs.setCurrentIndex(idx)

    def _load_current_state(self) -> None:
        plan = self.license_service.current_plan
        idx = max(0, self.plan_combo.findData(plan))
        self.plan_combo.setCurrentIndex(idx)
        active_features = self.license_service.entitlement_features
        if self.focus_feature:
            active_features.add(self.focus_feature)
            self.plan_combo.setCurrentIndex(max(0, self.plan_combo.findData("modular")))
        for key, check in self.feature_checks.items():
            check.setChecked(key in active_features)

    def _on_plan_changed(self) -> None:
        self.status.setVisible(False)
        plan_key = self._current_plan()
        plan = PLAN_BY_KEY.get(plan_key, PLAN_BY_KEY["free"])
        self.plan_description.setText(plan.description)
        if plan_key == "free":
            for key, check in self.feature_checks.items():
                check.blockSignals(True)
                check.setChecked(key in features_for_plan("free", []))
                check.setEnabled(False)
                check.blockSignals(False)
        elif plan_key == "enterprise_all":
            for check in self.feature_checks.values():
                check.blockSignals(True)
                check.setChecked(True)
                check.setEnabled(False)
                check.blockSignals(False)
        else:
            for check in self.feature_checks.values():
                check.setEnabled(True)
        self._recalculate()

    def _current_plan(self) -> str:
        return str(self.plan_combo.currentData() or "free")

    def _selected_features(self) -> list[str]:
        return sorted(key for key, check in self.feature_checks.items() if check.isChecked())

    def _recalculate(self) -> None:
        plan_key = self._current_plan()
        if plan_key == "enterprise_all":
            features = list(ALL_FEATURE_KEYS)
            total = PLAN_BY_KEY["enterprise_all"].monthly_pkr
        elif plan_key == "free":
            features = list(features_for_plan("free", []))
            total = 0
        else:
            features = self._selected_features()
            total = monthly_total_for_features(features)
        self.total_label.setText(f"Total: {self._money(total)} / month")
        self.selection_label.setText(f"{len(features)} selected")
        self._refresh_row_styles()
        self.checkout_btn.setText("Activate Free Plan" if total == 0 else "Pay with Stripe")
        self.checkout_btn.setEnabled(total == 0 or self.license_service.env.stripe_configured or self.license_service.is_development)

    def _continue_free(self) -> None:
        self.license_service.apply_license("free", features_for_plan("free", []), payment_status="free")
        self.license_changed.emit()
        self.accept()

    def _checkout(self) -> None:
        self.status.setVisible(False)
        plan_key = self._current_plan()
        selected = self._selected_features()
        if plan_key == "modular" and not selected:
            self._show_status("Select at least one module/submodule for the Modular Professional plan.")
            return
        try:
            checkout_url = self.license_service.create_checkout(plan_key, selected)
            self.license_changed.emit()
            if checkout_url:
                self._show_status("Stripe Checkout opened in your browser. After payment, click Refresh License.")
            else:
                QMessageBox.information(self, "Subscription Activated", "License updated successfully.")
                self.accept()
        except NetworkUnavailable as exc:
            self._show_status(str(exc))
        except AuthError as exc:
            self._show_status(str(exc))
        except Exception as exc:
            self._show_status(str(exc))

    def _approve_development(self) -> None:
        plan_key = self._current_plan()
        selected = self._selected_features()
        if plan_key == "modular" and not selected:
            self._show_status("Select at least one module/submodule for the development approval.")
            return
        amount = 0 if plan_key == "free" else (PLAN_BY_KEY["enterprise_all"].monthly_pkr if plan_key == "enterprise_all" else monthly_total_for_features(selected))
        self.license_service.approve_development_purchase(plan_key, selected, amount)
        self.license_changed.emit()
        QMessageBox.information(self, "Development Payment", "Development payment approved and stored locally. Firebase sync was attempted when configured.")
        self.accept()

    def _refresh_license(self) -> None:
        try:
            changed = self.license_service.sync_from_firebase(silent=False)
            self.license_changed.emit()
            self._show_status("Firebase license refreshed." if changed else "No Firebase license update was found.")
        except NetworkUnavailable as exc:
            self._show_status(str(exc))
        except AuthError as exc:
            self._show_status(str(exc))

    @staticmethod
    def _money(value: int) -> str:
        return f"PKR {int(value):,}"

    def _show_status(self, message: str) -> None:
        self.status.setText(message)
        self.status.setVisible(True)
