from __future__ import annotations

from typing import Optional, Dict, Any
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal, QSize, QPoint, QPropertyAnimation
from PySide6.QtGui import QColor, QAction, QKeySequence, QShortcut, QCloseEvent, QIcon, QGuiApplication, QResizeEvent
try:
    from shiboken6 import isValid as is_qobject_valid
except ImportError:
    def is_qobject_valid(obj: object) -> bool:
        return obj is not None

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QDockWidget, QStatusBar, QLabel, QProgressBar, QApplication,
    QPushButton, QFrame, QMessageBox, QFileDialog, QLineEdit, QMenu, QPlainTextEdit,
    QFormLayout, QScrollArea, QToolButton, QInputDialog, QTabBar, QSizePolicy, QStackedWidget
)

from core.infrastructure.service_container import ServiceContainer
from core.auth import LicenseService
from core.auth.plans import FEATURE_BY_KEY, FEATURES, MODULE_TITLES, feature_for_action, feature_for_provider
from ui.styles import apply_theme, Theme
from ui.icons import get_icon, icon_color
from ui.animations import fade_widget
from ui.docks.project_explorer import ProjectExplorer
from ui.ribbon.home_ribbon import HomeRibbonProvider
from ui.ribbon.segy_qc_ribbon import SegyQcRibbonProvider
from ui.ribbon.segy_viewer_ribbon import SegyViewerRibbonProvider
from ui.ribbon.segd_ribbon import SegdRibbonProvider
from ui.ribbon.module_ribbons import standard_providers
from ui.ribbon.workflow_ribbons import workflow_providers
from ui.ribbon.geodetic_ribbon import geodetic_providers
from ui.ribbon.seismic_ribbon import SeismicRibbonProvider
from ui.ribbon.seismic_visualization_ribbon import SeismicVisualizationRibbonProvider
from ui.ribbon.magnetic_ribbon import MagneticRibbonProvider
from ui.ribbon.gravity_ribbon import GravityRibbonProvider
from ui.ribbon.electrical_ribbon import ElectricalRibbonProvider
from ui.ribbon.converter_ribbon import ConverterRibbonProvider
from ui.ribbon.vibroseis_ribbon import VibroseisRibbonProvider
from ui.empty_workspace import EmptyWorkspace
from ui.widgets.full_page_loader import FullPageLoader
from ui.dialogs.subscription_dialog import SubscriptionDialog
from modules.workspace.workspace_manager import WorkspaceManager, WorkspaceTab
from core.data_access.layout_store import LayoutStore


class TitleBar(QWidget):
    quick_save_requested = Signal()
    quick_open_requested = Signal()
    subscription_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("titleBar")
        self.setFixedHeight(32)
        self._drag_position: QPoint | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 1, 3, 1)
        layout.setSpacing(4)

        self.icon = QLabel()
        self.icon.setObjectName("appGlyph")
        self.icon.setText("T")
        self.icon.setAlignment(Qt.AlignCenter)
        self.icon.setFixedSize(26, 26)
        layout.addWidget(self.icon)

        # Keep only quick-access commands that have real application actions.
        # The former Undo/Redo glyphs were decorative and therefore misleading.
        self.quick_save_btn = QToolButton(self)
        self.quick_save_btn.setObjectName("quickAccessButton")
        self.quick_save_btn.setIcon(get_icon("document-save", color=icon_color("document-save"), size=13))
        self.quick_save_btn.setIconSize(QSize(16, 16))
        self.quick_save_btn.setToolTip("Save Project")
        self.quick_save_btn.setAutoRaise(True)
        self.quick_save_btn.clicked.connect(self.quick_save_requested.emit)
        layout.addWidget(self.quick_save_btn)

        self.quick_open_btn = QToolButton(self)
        self.quick_open_btn.setObjectName("quickAccessButton")
        self.quick_open_btn.setIcon(get_icon("document-open", color=icon_color("document-open"), size=13))
        self.quick_open_btn.setIconSize(QSize(16, 16))
        self.quick_open_btn.setToolTip("Open Project")
        self.quick_open_btn.setAutoRaise(True)
        self.quick_open_btn.clicked.connect(self.quick_open_requested.emit)
        layout.addWidget(self.quick_open_btn)

        self.title = QLabel("TGPAssure E&P Software Platform ")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self.title, 1)

        self.account_btn = QToolButton(self)
        self.account_btn.setObjectName("windowControl")
        self.account_btn.setText("Account")
        self.account_btn.setToolTip("Subscription and module access")
        self.account_btn.setCursor(Qt.PointingHandCursor)
        self.account_btn.clicked.connect(self.subscription_requested.emit)
        layout.addWidget(self.account_btn)

        self.toggle_theme_btn = QToolButton()
        self.toggle_theme_btn.setObjectName("windowControl")
        self.toggle_theme_btn.setIcon(get_icon("color", color="#4A5568", size=13))
        self.toggle_theme_btn.setToolTip("Theme")
        self.min_btn = QToolButton()
        self.min_btn.setObjectName("windowControl")
        self.min_btn.setIcon(get_icon("window-minimize", color="#4A5568", size=13))
        self.min_btn.setIconSize(QSize(13, 13))
        self.max_btn = QToolButton()
        self.max_btn.setObjectName("windowControl")
        self.fit_btn = QToolButton()
        self.fit_btn.setObjectName("windowControl")
        self.fit_btn.setIcon(get_icon("zoom-fit-best", color="#4A5568", size=13))
        self.fit_btn.setIconSize(QSize(13, 13))
        self.fit_btn.setToolTip("Fit TGPAssure to this screen")
        self.max_btn.setIcon(get_icon("window-maximize", color="#4A5568", size=13))
        self.max_btn.setIconSize(QSize(13, 13))
        self.close_btn = QToolButton()
        self.close_btn.setObjectName("closeControl")
        self.close_btn.setIcon(get_icon("window-close", color="#4A5568", size=13))
        self.close_btn.setIconSize(QSize(13, 13))

        for button in (self.account_btn, self.toggle_theme_btn, self.fit_btn, self.min_btn, self.max_btn, self.close_btn):
            button.setFixedSize(34, 28)
            button.setAutoRaise(True)
            button.setCursor(Qt.PointingHandCursor)

        self.setStyleSheet("""
            QToolButton#quickAccessButton {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 3px;
                padding: 0;
            }
            QToolButton#quickAccessButton:hover {
                background: #E8EEF5;
                border-color: #D5DEE8;
            }
            QToolButton#windowControl,
            QToolButton#closeControl {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 3px;
                padding: 0;
                min-width: 0;
                min-height: 0;
            }
            QToolButton#windowControl:hover {
                background: #E8EEF5;
                border-color: #D5DEE8;
            }
            QToolButton#closeControl:hover {
                background: #E5484D;
                border-color: #E5484D;
            }
        """)

        layout.addWidget(self.toggle_theme_btn)
        layout.addWidget(self.fit_btn)
        layout.addWidget(self.min_btn)
        layout.addWidget(self.max_btn)
        layout.addWidget(self.close_btn)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_position = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_position is not None and event.buttons() & Qt.LeftButton and not self.window().isMaximized():
            self.window().move(event.globalPosition().toPoint() - self._drag_position)
        super().mouseMoveEvent(event)


class DockTitleBar(QWidget):
    def __init__(self, dock: QDockWidget, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent or dock)
        self._dock = dock
        self.setObjectName("dockTitleBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(28)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 4, 2)
        layout.setSpacing(4)

        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("dockTitleLabel")
        self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self.title_label, 1)

        self.float_btn = QToolButton(self)
        self.float_btn.setObjectName("dockTitleButton")
        self.float_btn.setFixedSize(26, 24)
        self.float_btn.setIconSize(QSize(13, 13))
        self.float_btn.setCursor(Qt.PointingHandCursor)
        self.float_btn.clicked.connect(self._toggle_floating)
        layout.addWidget(self.float_btn)

        self.close_btn = QToolButton(self)
        self.close_btn.setObjectName("dockCloseButton")
        self.close_btn.setFixedSize(26, 24)
        self.close_btn.setIcon(get_icon("window-close", color="#30343A", size=12))
        self.close_btn.setIconSize(QSize(13, 13))
        self.close_btn.setToolTip("Close")
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.clicked.connect(dock.close)
        layout.addWidget(self.close_btn)

        self.setStyleSheet("")

        dock.windowTitleChanged.connect(self.title_label.setText)
        dock.topLevelChanged.connect(self._sync_float_state)
        self._sync_float_state(dock.isFloating())

    def _toggle_floating(self) -> None:
        if self._dock.features() & QDockWidget.DockWidgetFloatable:
            self._dock.setFloating(not self._dock.isFloating())

    def _sync_float_state(self, floating: bool) -> None:
        icon_name = "window-restore" if floating else "window-maximize"
        self.float_btn.setIcon(get_icon(icon_name, color="#30343A", size=12))
        self.float_btn.setToolTip("Dock" if floating else "Float")
        self.float_btn.setVisible(bool(self._dock.features() & QDockWidget.DockWidgetFloatable))


class MainWindow(QMainWindow):
    file_imported = Signal(str)
    file_double_clicked = Signal(str)

    def __init__(self, container: ServiceContainer) -> None:
        super().__init__()
        self.container = container
        self._workspace_manager = container.resolve(WorkspaceManager)
        self._layout_store = container.resolve(LayoutStore)
        from core.infrastructure.settings_store import SettingsStore
        self._settings_store = container.resolve(SettingsStore) if container.has(SettingsStore) else None
        self._license_service = container.resolve(LicenseService) if container.has(LicenseService) else None
        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self._autosave_project)
        self._ribbon_workspace_timer = QTimer(self)
        self._ribbon_workspace_timer.setSingleShot(True)
        self._ribbon_workspace_timer.timeout.connect(self._run_pending_ribbon_workspace_activation)
        self._pending_ribbon_workspace_context: str | None = None
        self._ribbon_workspace_activation_in_progress = False
        self._workspace_loader_finish_tokens: dict[str, int] = {}
        self._workspace_loader_finish_token = 0
        self._current_project_name = None
        self._current_project_path = None
        self._active_module = "home"
        self._active_main_tab = "home"
        self._ribbon_providers = {}
        self._ribbon_tabs = {}
        self._ribbon_full_labels = {}
        self._ribbon_provider_to_main: dict[str, str] = {}
        self._last_subtab_by_main: dict[str, str] = {}
        self._ribbon_structure: dict[str, list[tuple[str, str]]] = {
            "home": [("home", "Home")],
            "seismic": [
                ("segd", "SEGD"),
                ("segd_scanner", "428 Header Scanner"),
                ("uphole", "Uphole"),
                ("receiver_qc", "Receiver QC"),
                ("segy_viewer", "SEGY"),
                ("converter", "Converter"),
                ("visualization", "2D/3D Viewer"),
            ],
            "magnetic": [
                ("magnetic_data", "Data"),
                ("magnetic_qc", "QC"),
                ("magnetic_processing", "Processing"),
                ("magnetic_viewer", "2D/3D & Satellite"),
                ("magnetic_reports", "Reports"),
            ],
            "electrical": [
                ("electrical_data", "Data & Methods"),
                ("electrical_qc", "QC"),
                ("electrical_processing", "Processing"),
                ("electrical_viewer", "2D/3D & Satellite"),
                ("electrical_reports", "Reports"),
            ],
            "gravity": [
                ("gravity_data", "Data"),
                ("gravity_qc", "QC"),
                ("gravity_processing", "Reduction"),
                ("gravity_viewer", "2D/3D & Satellite"),
                ("gravity_reports", "Reports"),
            ],
            "vibroseis": [
                ("vibroseis_data", "Data & Source Design"),
                ("vibroseis_qc", "QC"),
                ("vibroseis_viewer", "2D/3D & Satellite"),
                ("vibroseis_planning", "Planning & Export"),
            ],
            "geodetic": [
                ("geodetic_data", "DC Examiner"),
                ("geodetic_qc", "QC & Graphs"),
                ("geodetic_coordinates", "Coordinates & Datum"),
                ("geodetic_viewer", "2D/3D & Satellite"),
                ("geodetic_reports", "Reports & Export"),
            ],
        }
        self._responsive_mode = ""
        self._segy_qc_view = None
        self._segy_qc_tab_title = "SEG-Y QC"
        self._segy_qc_tab_icon = QIcon()
        self._data_quality_dashboard = None
        self._magnetic_dashboard = None
        self._gravity_dashboard = None
        self._electrical_dashboard = None
        self._converter_page = None
        self._vibroseis_dashboard = None
        self._geodetic_dashboard = None
        self._segd_scanner_dashboard = None
        self._receiver_qc_dashboard = None
        self._uphole_dashboard = None
        self._qc_history_page = None
        self._selected_project_path: Path | None = None
        self._busy_tasks: dict[str, dict[str, Any]] = {}
        self._busy_task_order: list[str] = []
        self._displayed_busy_task_id: str | None = None
        self._dashboard_fullscreen_active = False
        self._dashboard_fullscreen_state: dict[str, Any] = {}
        self._ribbon_label_sets = {
            "home": ("Home", "Home", "Home"),
            "seismic": ("Seismic", "Seismic", "Seismic"),
            "segd": ("SEG-D", "SEG-D", "SEG-D"),
            "segy_qc": ("SEG-Y QC", "SEG-Y QC", "QC"),
            "segy_viewer": ("SEG-Y Viewer", "SEG-Y View", "SEG-Y"),
            "visualization": ("2D/3D View", "2D/3D", "View"),
            "converter": ("Converter", "Converter", "Convert"),
            "vibroseis": ("Vibroseis", "Vibroseis", "Vibroseis"),
            "magnetic": ("Magnetic", "Magnetic", "Magnetic"),
            "gravity": ("Gravity", "Gravity", "Gravity"),
            "electrical": ("Electrical", "Electrical", "Electrical"),
            "geodetic": ("Geodetic", "Geodetic", "Geodetic"),
            "view": ("Layout", "Layout", "Layout"),
            "tools": ("Tools", "Tools", "Tools"),
            "help": ("Help", "Help", "Help"),
        }
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        
        self.setWindowTitle('TGPAssure E&P Software Platform')
        self.setMinimumSize(900, 540)
        self.resize(1280, 720)
        apply_theme(QApplication.instance(), Theme.LIGHT)
        
        self._create_central()
        self._create_docks()
        self._create_menu_bar()
        self._create_title_bar()
        self._create_ribbon()
        self._create_status_bar()
        self._create_shortcuts()
        self._apply_tab_styling()
        self._full_page_loader = FullPageLoader(self)
        self._full_page_loader.sync_geometry()
        
        self._register_ribbon_provider(HomeRibbonProvider())
        self._register_ribbon_provider(SegdRibbonProvider())
        self._register_ribbon_provider(SegyViewerRibbonProvider())
        self._register_ribbon_provider(ConverterRibbonProvider())
        self._register_ribbon_provider(SeismicVisualizationRibbonProvider())
        self._register_ribbon_provider(SegyQcRibbonProvider())
        for provider in workflow_providers():
            self._register_ribbon_provider(provider)
        for provider in geodetic_providers():
            self._register_ribbon_provider(provider)
        self._configure_ribbon_navigation()
        self.refresh_license_ui()
        self._set_active_module('home')
        self._apply_responsive_chrome(force=True)
        
        self._workspace_manager.tab_changed.connect(self._on_tab_changed)
        self._workspace_manager.project_state_changed.connect(self._update_ribbon)
        self._workspace_manager.file_imported.connect(lambda *_: self._update_ribbon())
        self._workspace_manager.tab_closed.connect(self._on_tab_closed)
        self._configure_autosave()

    def refresh_license_ui(self) -> None:
        self._refresh_license_top_tabs()
        if hasattr(self, "ribbon_sub_tab_bar"):
            self._populate_ribbon_subtabs(self._active_main_tab, self._active_module)
        if hasattr(self, "status_bar") and self._license_service is not None:
            user = self._license_service.user
            if user is not None:
                self.status_bar.showMessage(
                    f"Logged in: {user.email}",
                    3500,
                )
        if hasattr(self, "ribbon_groups_layout"):
            self._update_ribbon()

    def open_subscription_dialog(self) -> None:
        if self._license_service is None:
            QMessageBox.information(self, "Subscription", "Subscription service is not available in this build.")
            return
        dialog = SubscriptionDialog(self._license_service, self)
        dialog.license_changed.connect(self.refresh_license_ui)
        if dialog.exec() == SubscriptionDialog.Accepted:
            self.refresh_license_ui()

    def _logout_account(self) -> None:
        if self._license_service is None:
            return
        choice = QMessageBox.question(
            self,
            "Logout",
            "Logout from this TGPAssure account on this workstation? You will need internet to create a new account or buy modules again.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if choice != QMessageBox.Yes:
            return
        self._license_service.logout()
        QMessageBox.information(self, "Logged Out", "The local login session has been removed. TGPAssure will close now.")
        self.close()

    def _refresh_license_top_tabs(self) -> None:
        if not hasattr(self, "ribbon_tab_bar"):
            return
        mode = getattr(self, "_responsive_mode", "full")
        label_index = 2 if mode == "compact" else (1 if mode == "medium" else 0)
        for tab_id, index in self._ribbon_tabs.items():
            labels = self._ribbon_label_sets.get(tab_id)
            label = labels[label_index] if labels else self._ribbon_full_labels.get(tab_id, tab_id.title())
            if tab_id != "home" and not self._is_main_tab_licensed(tab_id):
                label = f"{label} 🔒"
            self.ribbon_tab_bar.setTabText(index, label)
            self.ribbon_tab_bar.setTabToolTip(index, "Locked — click to buy module access" if "🔒" in label else self._ribbon_full_labels.get(tab_id, label))

    def _is_main_tab_licensed(self, main_id: str | None) -> bool:
        module = str(main_id or "home")
        if module == "home":
            return True
        if self._license_service is None:
            return True
        return self._license_service.has_module(module)

    def _is_provider_licensed(self, provider_id: str | None) -> bool:
        provider = str(provider_id or "")
        if provider in {"", "home"}:
            return True
        if self._license_service is None:
            return True
        return self._license_service.has_provider(provider)

    def _is_action_licensed(self, action_id: str | None) -> bool:
        if self._license_service is None:
            return True
        return self._license_service.has_action(action_id)

    def _is_context_licensed(self, context_id: str | None) -> bool:
        context = str(context_id or "home")
        if context == "home":
            return True
        if context in {"seismic", "magnetic", "electrical", "gravity", "vibroseis", "geodetic"}:
            return self._is_main_tab_licensed(context)
        return self._is_provider_licensed(context)

    def _first_feature_for_module(self, module_id: str | None) -> str | None:
        module = str(module_id or "")
        for feature in FEATURES:
            if feature.module == module:
                return feature.key
        return None

    def _show_purchase_required(self, feature_key: str | None, module_id: str | None = None) -> None:
        if self._license_service is None:
            return
        feature = FEATURE_BY_KEY.get(feature_key or "")
        module_label = MODULE_TITLES.get(str(module_id or ""), str(module_id or "Module").title())
        target = feature.title if feature is not None else module_label
        QMessageBox.information(
            self,
            "Module Locked",
            f"{target} is locked for this account. Select the required module/submodule and complete payment to activate it.",
        )
        dialog = SubscriptionDialog(self._license_service, self, focus_feature=feature_key)
        dialog.license_changed.connect(self.refresh_license_ui)
        if dialog.exec() == SubscriptionDialog.Accepted:
            self.refresh_license_ui()

    def _restore_active_ribbon_selection(self) -> None:
        if not hasattr(self, "ribbon_tab_bar"):
            return
        main_index = self._ribbon_tabs.get(self._active_main_tab, self._ribbon_tabs.get("home", 0))
        if main_index is not None:
            self.ribbon_tab_bar.blockSignals(True)
            self.ribbon_tab_bar.setCurrentIndex(main_index)
            self.ribbon_tab_bar.blockSignals(False)
        self._populate_ribbon_subtabs(self._active_main_tab, self._active_module)
        self._refresh_license_top_tabs()

    def _apply_tab_styling(self):
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.tabBar().setMovable(True)

    def _create_title_bar(self):
        self.title_bar = TitleBar(self)
        self.title_bar.close_btn.clicked.connect(self.close)
        self.title_bar.min_btn.clicked.connect(lambda: self.showMinimized())
        self.title_bar.max_btn.clicked.connect(self._toggle_maximize)
        self.title_bar.fit_btn.clicked.connect(self._fit_to_screen)
        self.title_bar.quick_save_requested.connect(self._save_project)
        self.title_bar.quick_open_requested.connect(self._open_project)
        self.title_bar.subscription_requested.connect(self.open_subscription_dialog)
        self.setMenuWidget(self.title_bar)

    def _fit_to_screen(self):
        screen = QGuiApplication.screenAt(self.frameGeometry().center()) or QGuiApplication.primaryScreen()
        available = screen.availableGeometry()
        width = max(900, available.width() - 16)
        height = max(540, available.height() - 16)
        self.showNormal()
        self.resize(width, height)
        self.move(available.center() - self.rect().center())
        self._apply_responsive_chrome(force=True)

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _create_menu_bar(self):
        menu_bar = self.menuBar()
        
        file_menu = menu_bar.addMenu("&File")
        
        new_action = QAction("&New Project", self)
        new_action.setShortcut(QKeySequence("Ctrl+N"))
        new_action.triggered.connect(self._new_project)
        file_menu.addAction(new_action)
        
        open_action = QAction("&Open Project", self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self._open_project)
        file_menu.addAction(open_action)
        
        save_action = QAction("&Save", self)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.triggered.connect(self._save_project)
        file_menu.addAction(save_action)
        
        file_menu.addSeparator()
        
        import_action = QAction("&Import File", self)
        import_action.triggered.connect(self._import_file)
        file_menu.addAction(import_action)

        file_menu.addSeparator()
        subscription_action = QAction("&Subscription / Modules", self)
        subscription_action.triggered.connect(self.open_subscription_dialog)
        file_menu.addAction(subscription_action)
        logout_action = QAction("&Logout", self)
        logout_action.triggered.connect(self._logout_account)
        file_menu.addAction(logout_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        edit_menu = menu_bar.addMenu("&Edit")
        preferences_action = QAction("&Preferences", self)
        preferences_action.triggered.connect(self._open_preferences)
        edit_menu.addAction(preferences_action)
        
        view_menu = menu_bar.addMenu("&View")
        
        project_action = self.project_dock.toggleViewAction()
        project_action.setText("&Project Explorer")
        view_menu.addAction(project_action)
        
        properties_action = self.properties_dock.toggleViewAction()
        properties_action.setText("&Properties")
        view_menu.addAction(properties_action)
        
        output_action = self.output_dock.toggleViewAction()
        output_action.setText("&Output Console")
        view_menu.addAction(output_action)
        
        view_menu.addSeparator()
        
        reset_layout_action = QAction("&Reset Layout", self)
        reset_layout_action.triggered.connect(self._reset_layout)
        view_menu.addAction(reset_layout_action)

        view_menu.addSeparator()

        fullscreen_action = QAction("Full Screen View (F11)", self)
        fullscreen_action.setShortcut(QKeySequence("F11"))
        fullscreen_action.triggered.connect(self.enter_dashboard_fullscreen)
        view_menu.addAction(fullscreen_action)

        normal_screen_action = QAction("Back to Normal Screen (F5)", self)
        normal_screen_action.setShortcut(QKeySequence("F5"))
        normal_screen_action.triggered.connect(self.exit_dashboard_fullscreen)
        view_menu.addAction(normal_screen_action)

        self._view_fullscreen_action = fullscreen_action
        self._view_normal_screen_action = normal_screen_action
        
        help_menu = menu_bar.addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
        menu_bar.hide()

    def _create_ribbon(self):
        self.ribbon_container = QWidget()
        self.ribbon_container.setObjectName("ribbonContainer")
        ribbon_layout = QVBoxLayout(self.ribbon_container)
        ribbon_layout.setContentsMargins(0, 0, 0, 0)
        ribbon_layout.setSpacing(0)

        self.ribbon_header = QWidget()
        self.ribbon_header.setObjectName("ribbonHeader")
        header_layout = QHBoxLayout(self.ribbon_header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)

        self.file_button = QToolButton(self.ribbon_header)
        self.file_button.setObjectName("ribbonFileButton")
        self.file_button.setText("File")
        self.file_button.setPopupMode(QToolButton.InstantPopup)
        self.file_button.setCursor(Qt.PointingHandCursor)
        file_menu = QMenu(self.file_button)
        file_menu.addAction("New Project", self._new_project)
        file_menu.addAction("Open Project…", self._open_project)
        file_menu.addAction("Save Project", self._save_project)
        file_menu.addSeparator()
        file_menu.addAction("Import File…", self._import_file)
        file_menu.addSeparator()
        file_menu.addAction("Subscription / Modules…", self.open_subscription_dialog)
        file_menu.addAction("Logout", self._logout_account)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)
        self.file_button.setMenu(file_menu)
        header_layout.addWidget(self.file_button)

        self.ribbon_tab_bar = QTabBar(self.ribbon_header)
        self.ribbon_tab_bar.setObjectName("ribbonTabs")
        self.ribbon_tab_bar.setExpanding(False)
        self.ribbon_tab_bar.setUsesScrollButtons(True)
        self.ribbon_tab_bar.setElideMode(Qt.ElideNone)
        self.ribbon_tab_bar.setFixedHeight(35)
        self.ribbon_tab_bar.setDrawBase(False)
        self.ribbon_tab_bar.setDocumentMode(False)
        self.ribbon_tab_bar.currentChanged.connect(self._on_ribbon_tab_changed)
        try:
            self.ribbon_tab_bar.tabBarClicked.connect(self._on_ribbon_tab_clicked)
        except Exception:
            pass
        header_layout.addWidget(self.ribbon_tab_bar, 1)

        self.ribbon_sub_header = QWidget()
        self.ribbon_sub_header.setObjectName("ribbonSubHeader")
        sub_header_layout = QHBoxLayout(self.ribbon_sub_header)
        sub_header_layout.setContentsMargins(54, 0, 5, 0)
        sub_header_layout.setSpacing(0)
        self.ribbon_sub_tab_bar = QTabBar(self.ribbon_sub_header)
        self.ribbon_sub_tab_bar.setObjectName("ribbonSubTabs")
        self.ribbon_sub_tab_bar.setExpanding(False)
        self.ribbon_sub_tab_bar.setUsesScrollButtons(True)
        self.ribbon_sub_tab_bar.setElideMode(Qt.ElideNone)
        self.ribbon_sub_tab_bar.setFixedHeight(30)
        self.ribbon_sub_tab_bar.setDrawBase(False)
        self.ribbon_sub_tab_bar.currentChanged.connect(self._on_ribbon_sub_tab_changed)
        try:
            self.ribbon_sub_tab_bar.tabBarClicked.connect(self._on_ribbon_sub_tab_clicked)
        except Exception:
            pass
        sub_header_layout.addWidget(self.ribbon_sub_tab_bar, 1)
        self.ribbon_sub_header.setVisible(False)

        self.ribbon_groups_background = QWidget()
        self.ribbon_groups_background.setObjectName("ribbonGroupsBackground")
        background_layout = QVBoxLayout(self.ribbon_groups_background)
        background_layout.setContentsMargins(5, 0, 5, 5)
        background_layout.setSpacing(0)

        self.ribbon_groups_container = QWidget()
        self.ribbon_groups_container.setObjectName("ribbonGroupsContainer")
        self.ribbon_groups_layout = QHBoxLayout(self.ribbon_groups_container)
        self.ribbon_groups_layout.setContentsMargins(5, 1, 5, 0)
        self.ribbon_groups_layout.setSpacing(0)
        self.ribbon_groups_container.setFixedHeight(100)

        # Ribbon groups can legitimately exceed the available window width (the
        # seismic 2D/3D context is the densest example).  Do not let buttons
        # paint outside the ribbon or get clipped: use compact group layout first
        # and a thin horizontal-scroll fallback when the complete command set is
        # still wider than the viewport.
        self.ribbon_groups_scroll = QScrollArea(self.ribbon_groups_background)
        self.ribbon_groups_scroll.setObjectName("ribbonGroupsScroll")
        self.ribbon_groups_scroll.setFrameShape(QFrame.NoFrame)
        self.ribbon_groups_scroll.setWidgetResizable(False)
        self.ribbon_groups_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.ribbon_groups_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.ribbon_groups_scroll.setWidget(self.ribbon_groups_container)
        self.ribbon_groups_scroll.horizontalScrollBar().setFixedHeight(8)
        background_layout.addWidget(self.ribbon_groups_scroll)

        self.ribbon_groups_background.setFixedHeight(105)
        self.ribbon_groups_background.setVisible(False)

        ribbon_layout.addWidget(self.ribbon_header)
        ribbon_layout.addWidget(self.ribbon_sub_header)
        ribbon_layout.addWidget(self.ribbon_groups_background)

        self.ribbon_dock = QDockWidget("Ribbon")
        self.ribbon_dock.setObjectName("ribbonDock")
        self.ribbon_dock.setWidget(self.ribbon_container)
        self.ribbon_dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.ribbon_dock.setTitleBarWidget(QWidget())
        self.addDockWidget(Qt.TopDockWidgetArea, self.ribbon_dock)

    def _add_ribbon_tab(self, tab_id: str, label: str):
        index = self.ribbon_tab_bar.addTab(label)
        self.ribbon_tab_bar.setTabData(index, tab_id)
        self._ribbon_tabs[tab_id] = index
        self._ribbon_full_labels[tab_id] = label
        # Keep ribbon category text neutral; selection/hover colors are controlled
        # centrally by the workstation theme for a consistent dark ribbon strip.
        self.ribbon_tab_bar.setTabTextColor(index, QColor("#F2F2F2"))

    def _apply_responsive_chrome(self, force: bool = False) -> None:
        width = max(1, self.width())
        height = max(1, self.height())
        if width < 1100 or height < 650:
            mode = "compact"
            label_index = 2
            tab_font = 8
            tab_height = 30
            ribbon_height = 78
            ribbon_background_height = 83
            separator_height = 58
            status_font = 8
        elif width < 1450 or height < 780:
            mode = "medium"
            label_index = 1
            tab_font = 9
            tab_height = 32
            ribbon_height = 86
            ribbon_background_height = 91
            separator_height = 66
            status_font = 8
        else:
            mode = "full"
            label_index = 0
            tab_font = 10
            tab_height = 35
            ribbon_height = 92
            ribbon_background_height = 97
            separator_height = 72
            status_font = 9

        mode_changed = force or mode != self._responsive_mode
        self._responsive_mode = mode
        self.ribbon_tab_bar.setFixedHeight(tab_height)
        self.ribbon_groups_container.setFixedHeight(ribbon_height)
        if hasattr(self, "ribbon_groups_scroll"):
            self.ribbon_groups_scroll.setFixedHeight(ribbon_height)
        self.ribbon_groups_background.setFixedHeight(ribbon_background_height)
        self.ribbon_tab_bar.setExpanding(False)
        font = self.ribbon_tab_bar.font()
        font.setPointSize(tab_font)
        self.ribbon_tab_bar.setFont(font)

        for tab_id, tab_index in self._ribbon_tabs.items():
            labels = self._ribbon_label_sets.get(tab_id)
            if labels is None:
                label = self._ribbon_full_labels.get(tab_id, tab_id.replace("_", " ").title())
            else:
                label = labels[label_index]
            self.ribbon_tab_bar.setTabText(tab_index, label)
            full_label = self._ribbon_full_labels.get(tab_id, label)
            self.ribbon_tab_bar.setTabToolTip(tab_index, full_label)

        self._refresh_license_top_tabs()
        self.status_bar.setStyleSheet(
            f"QStatusBar{{font-size:{status_font}px;}} "
            f"QStatusBar QLabel{{font-size:{status_font}px;}} "
            f"QStatusBar QPushButton#statusFullScreenButton{{"
            f"font-size:{status_font}px; padding:2px 10px; min-height:19px; border-radius:4px;"
            f"border:1px solid #1E7AC2; background:#E2F1FF; color:#084B7A; font-weight:700;"
            f"}} "
            f"QStatusBar QPushButton#statusFullScreenButton:hover{{background:#FFFFFF; border-color:#0B5E9D;}} "
            f"QStatusBar QPushButton#statusNormalScreenButton{{"
            f"font-size:{status_font}px; padding:2px 10px; min-height:19px; border-radius:4px;"
            f"border:1px solid #D69E2E; background:#FFF1CC; color:#7A4D00; font-weight:700;"
            f"}} "
            f"QStatusBar QPushButton#statusNormalScreenButton:hover{{background:#FFFFFF; border-color:#B7791F;}}"
        )
        document_tab_font = self.tab_widget.tabBar().font()
        document_tab_font.setPointSize(8 if mode == "compact" else 9)
        self.tab_widget.tabBar().setFont(document_tab_font)
        self.title_bar.title.setVisible(width >= 760)
        self.title_bar.setFixedHeight(30 if mode == "compact" else 32)
        self.job_progress_bar.setFixedWidth(82 if mode == "compact" else 100)

        if mode_changed and self._active_module in self._ribbon_providers:
            self._update_ribbon()
            for i in range(self.ribbon_groups_layout.count()):
                item = self.ribbon_groups_layout.itemAt(i)
                widget = item.widget()
                if widget is not None and widget.objectName() == "ribbonSeparator":
                    widget.setFixedHeight(separator_height)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if hasattr(self, "ribbon_tab_bar"):
            self._apply_responsive_chrome()
        if hasattr(self, "ribbon_groups_scroll") and hasattr(self, "ribbon_groups_layout"):
            QTimer.singleShot(0, self._sync_ribbon_group_canvas)
        if hasattr(self, "_full_page_loader"):
            self._full_page_loader.sync_geometry()

    def begin_busy_task(
        self,
        task_id: str,
        title: str,
        message: str,
        progress: int | None = None,
        *,
        cancel_callback=None,
    ) -> None:
        """Register a long-running task with the application-wide loader.

        Multiple tasks may overlap. The most recently started task is presented,
        and when it finishes the loader automatically falls back to the previous
        active task instead of disappearing too early.
        """
        key = str(task_id or "foreground")
        self._busy_tasks[key] = {
            "title": str(title or "Processing"),
            "message": str(message or "Please wait"),
            "progress": progress,
            "cancel_callback": cancel_callback,
        }
        if key in self._busy_task_order:
            self._busy_task_order.remove(key)
        self._busy_task_order.append(key)
        self._render_busy_task(force_process_events=True)

    def update_busy_task(
        self,
        task_id: str,
        progress: int | None = None,
        message: str | None = None,
        *,
        title: str | None = None,
    ) -> None:
        key = str(task_id or "foreground")
        task = self._busy_tasks.get(key)
        if task is None:
            return
        if progress is not None:
            task["progress"] = max(0, min(100, int(progress)))
        if message is not None:
            task["message"] = str(message)
        if title is not None:
            task["title"] = str(title)
        if self._busy_task_order and self._busy_task_order[-1] == key:
            self._render_busy_task()

    def end_busy_task(self, task_id: str) -> None:
        key = str(task_id or "foreground")
        self._busy_tasks.pop(key, None)
        if key in self._busy_task_order:
            self._busy_task_order.remove(key)
        self._render_busy_task()

    def has_busy_task(self, task_id: str) -> bool:
        return str(task_id or "foreground") in self._busy_tasks

    def _render_busy_task(self, force_process_events: bool = False) -> None:
        if not hasattr(self, "_full_page_loader"):
            return
        while self._busy_task_order and self._busy_task_order[-1] not in self._busy_tasks:
            self._busy_task_order.pop()
        if not self._busy_task_order:
            self._displayed_busy_task_id = None
            self._full_page_loader.finish()
            return
        active_key = self._busy_task_order[-1]
        task = self._busy_tasks[active_key]
        cancel_callback = task.get("cancel_callback")
        if self._full_page_loader.isVisible() and self._displayed_busy_task_id == active_key:
            self._full_page_loader.update_loader(
                task.get("progress"),
                task.get("message"),
                title=task.get("title"),
                cancellable=cancel_callback is not None,
                cancel_callback=cancel_callback,
            )
        else:
            self._displayed_busy_task_id = active_key
            self._full_page_loader.show_loader(
                task.get("title", "Processing"),
                task.get("message", "Please wait"),
                task.get("progress"),
                cancellable=cancel_callback is not None,
                cancel_callback=cancel_callback,
            )
        if force_process_events:
            QApplication.processEvents()

    def _show_full_page_loader(self, title: str, message: str, progress: int | None = None) -> None:
        self.begin_busy_task("foreground", title, message, progress)

    def _update_full_page_loader(self, progress: int | None = None, message: str | None = None) -> None:
        self.update_busy_task("foreground", progress, message)

    def _hide_full_page_loader(self) -> None:
        self.end_busy_task("foreground")

    def begin_job_loader(self, job_id: int, cancel_callback=None) -> None:
        self.begin_busy_task(
            f"job:{job_id}",
            "Processing Geophysical Data",
            "Running background processing and quality-control tasks",
            0,
            cancel_callback=cancel_callback,
        )

    def update_job_loader(self, job_id: int, progress: float) -> None:
        value = float(progress)
        if 0.0 <= value <= 1.0:
            value *= 100.0
        self.update_busy_task(
            f"job:{job_id}",
            round(max(0.0, min(100.0, value))),
            "Processing data — the application remains responsive",
        )

    def end_job_loader(self, job_id: int) -> None:
        self.end_busy_task(f"job:{job_id}")


    def _on_ribbon_tab_clicked(self, index: int) -> None:
        """Open the selected workflow even when the active top ribbon tab is clicked again."""
        main_id = self.ribbon_tab_bar.tabData(index)
        if not main_id:
            return
        main_id = str(main_id)
        if main_id == "home":
            return
        if not self._is_main_tab_licensed(main_id):
            self._show_purchase_required(self._first_feature_for_module(main_id), main_id)
            if self._is_main_tab_licensed(main_id):
                self._set_active_module(main_id)
                self._schedule_ribbon_workspace_activation(self._active_module)
            else:
                self._restore_active_ribbon_selection()
            return
        self._set_active_module(main_id)
        self._schedule_ribbon_workspace_activation(self._active_module)

    def _on_ribbon_sub_tab_clicked(self, index: int) -> None:
        """Open the selected sub-workflow even when it is already selected."""
        provider_id = self.ribbon_sub_tab_bar.tabData(index)
        if not provider_id:
            return
        provider_id = str(provider_id)
        if not self._is_provider_licensed(provider_id):
            self._show_purchase_required(feature_for_provider(provider_id), self._active_main_tab)
            if not self._is_provider_licensed(provider_id):
                self._restore_active_ribbon_selection()
                return
        self._active_module = provider_id
        self._last_subtab_by_main[self._active_main_tab] = provider_id
        self._update_ribbon()
        self._schedule_ribbon_workspace_activation(provider_id)

    def _on_ribbon_tab_changed(self, index: int) -> None:
        main_id = self.ribbon_tab_bar.tabData(index)
        if main_id:
            main_id = str(main_id)
            if not self._is_main_tab_licensed(main_id):
                self._show_purchase_required(self._first_feature_for_module(main_id), main_id)
                if not self._is_main_tab_licensed(main_id):
                    self._restore_active_ribbon_selection()
                    return
            self._set_active_module(main_id)
            # Opening a module dashboard can be expensive. Debounce ribbon
            # navigation so rapid clicks do not queue several heavy dashboard
            # constructors and make the application appear to close/reopen or hang.
            self._schedule_ribbon_workspace_activation(self._active_module)

    def _on_ribbon_sub_tab_changed(self, index: int) -> None:
        provider_id = self.ribbon_sub_tab_bar.tabData(index)
        if not provider_id:
            return
        provider_id = str(provider_id)
        if not self._is_provider_licensed(provider_id):
            self._show_purchase_required(feature_for_provider(provider_id), self._active_main_tab)
            if not self._is_provider_licensed(provider_id):
                self._restore_active_ribbon_selection()
                return
        self._active_module = provider_id
        self._last_subtab_by_main[self._active_main_tab] = provider_id
        self._update_ribbon()
        self._schedule_ribbon_workspace_activation(provider_id)

    def _schedule_ribbon_workspace_activation(self, context_id: str | None) -> None:
        context = str(context_id or "").strip()
        task_id = "ribbon:workspace"
        if not context or context == "home":
            self.end_busy_task(task_id)
            return
        self._pending_ribbon_workspace_context = context

        # Start the full-screen loader immediately on ribbon tab/sub-tab click.
        # Dashboard construction is delayed by a short single-shot timer, so
        # waiting until the timer fires makes the UI feel unresponsive. Showing
        # the loader here gives instant feedback and keeps it visible until the
        # requested dashboard/view is actually activated or the file picker is
        # cancelled.
        self.begin_busy_task(
            task_id,
            "Opening Dashboard",
            f"Preparing {self._ribbon_context_label(context)} dashboard",
            5,
        )
        QApplication.processEvents()

        if self._ribbon_workspace_activation_in_progress:
            return
        # Keep the delay short only to allow the ribbon selection paint event to
        # complete before any heavier dashboard widget is built.
        self._ribbon_workspace_timer.start(40)

    def _run_pending_ribbon_workspace_activation(self) -> None:
        context = self._pending_ribbon_workspace_context
        self._pending_ribbon_workspace_context = None
        task_id = "ribbon:workspace"
        if not context or context == "home":
            self.end_busy_task(task_id)
            return
        if self._ribbon_workspace_activation_in_progress:
            self._pending_ribbon_workspace_context = context
            self._ribbon_workspace_timer.start(80)
            return
        # A newer click may have changed the selected provider while this request
        # was waiting. Drop stale requests instead of opening the wrong module.
        if context != self._active_module:
            self.end_busy_task(task_id)
            return

        self._ribbon_workspace_activation_in_progress = True
        target_widget = None
        finish_message = f"{self._ribbon_context_label(context)} dashboard is ready"
        try:
            if not self.has_busy_task(task_id):
                self.begin_busy_task(
                    task_id,
                    "Opening Dashboard",
                    f"Preparing {self._ribbon_context_label(context)} dashboard",
                    10,
                )
            else:
                self.update_busy_task(
                    task_id,
                    22,
                    f"Loading {self._ribbon_context_label(context)} dashboard",
                    title="Opening Dashboard",
                )
            QApplication.processEvents()

            self._activate_ribbon_workspace_context(context)
            target_widget = self.tab_widget.currentWidget() if hasattr(self, "tab_widget") else None
            self.update_busy_task(task_id, 82, "Finalising dashboard layout and graphs")
            QApplication.processEvents()
        except Exception as exc:
            self.log(f"Ribbon workspace activation failed for {context}: {exc}")
            finish_message = "Dashboard activation finished with errors"
        finally:
            self._ribbon_workspace_activation_in_progress = False
            if self.has_busy_task(task_id):
                # Do not hide the loader here.  Qt paints the newly-created
                # dashboard after this slot returns, so ending the loader in this
                # finally block makes it disappear while the lower workspace is
                # still blank.  Keep polling for a visible, painted tab and only
                # then fade the loader out.
                self._finish_busy_task_after_workspace_paint(
                    task_id,
                    context,
                    target_widget,
                    ready_message=finish_message,
                )
            if self._pending_ribbon_workspace_context and self._pending_ribbon_workspace_context != context:
                self._ribbon_workspace_timer.start(40)

    def _finish_busy_task_after_workspace_paint(
        self,
        task_id: str,
        context_id: str | None = None,
        target_widget: QWidget | None = None,
        *,
        ready_message: str = "Dashboard is ready",
        attempt: int = 0,
        stable_frames: int = 0,
    ) -> None:
        """Keep the full-screen loader visible until the workspace is actually painted.

        Ribbon clicks and file-open actions often finish their Python slot before
        Qt has laid out and painted the document tab underneath the loader.  This
        method waits for the requested widget to be the current tab, visible,
        sized, and stable for a few event-loop cycles.  It gives the user a
        smooth transition instead of a blank/lagging lower workspace.
        """
        key = str(task_id or "foreground")
        if attempt == 0:
            self._workspace_loader_finish_token += 1
            self._workspace_loader_finish_tokens[key] = self._workspace_loader_finish_token
        token = self._workspace_loader_finish_tokens.get(key)

        def _poll(next_attempt: int, next_stable: int) -> None:
            if self._workspace_loader_finish_tokens.get(key) != token:
                return
            if not self.has_busy_task(key):
                self._workspace_loader_finish_tokens.pop(key, None)
                return

            widget = target_widget
            if widget is None or not is_qobject_valid(widget):
                widget = self.tab_widget.currentWidget() if hasattr(self, "tab_widget") else None

            ready = self._workspace_widget_is_painted(widget)
            if ready:
                next_stable += 1
                self.update_busy_task(
                    key,
                    min(98, 88 + next_stable * 3),
                    ready_message if next_stable >= 2 else "Rendering dashboard on screen",
                )
                QApplication.processEvents()
                # Require multiple stable event-loop turns so graphs/tables get
                # one real paint behind the overlay before it disappears.
                if next_stable >= 3:
                    self.update_busy_task(key, 100, ready_message)
                    QApplication.processEvents()
                    self._workspace_loader_finish_tokens.pop(key, None)
                    self.end_busy_task(key)
                    return
            else:
                next_stable = 0
                progress = min(96, 82 + max(0, next_attempt // 2))
                self.update_busy_task(key, progress, "Waiting for dashboard to appear")

            # Safety valve: never leave the loader stuck forever if a dashboard
            # constructor opens a file dialog, is cancelled, or fails to create a
            # visible widget.  The delay is long enough for slow dashboard pages
            # but still recovers gracefully.
            if next_attempt >= 55:
                self._workspace_loader_finish_tokens.pop(key, None)
                self.end_busy_task(key)
                return
            QTimer.singleShot(70, lambda: _poll(next_attempt + 1, next_stable))

        QTimer.singleShot(90, lambda: _poll(attempt, stable_frames))

    def _workspace_widget_is_painted(self, widget: QWidget | None) -> bool:
        if widget is None or not is_qobject_valid(widget):
            return False
        if not hasattr(self, "tab_widget") or not is_qobject_valid(self.tab_widget):
            return bool(widget.isVisible() and widget.width() > 20 and widget.height() > 20)
        if self.tab_widget.currentWidget() is not widget:
            return False
        if self.tab_widget.indexOf(widget) < 0:
            return False
        if not self.tab_widget.isVisible() or not widget.isVisible():
            return False
        if widget.width() < 40 or widget.height() < 40:
            return False
        try:
            widget.ensurePolished()
            widget.update()
            self.tab_widget.update()
        except RuntimeError:
            return False
        return True

    def _ribbon_context_label(self, context_id: str) -> str:
        context = str(context_id or "workspace")
        for _main_id, items in self._ribbon_structure.items():
            for provider_id, label in items:
                if provider_id == context:
                    return label
        return context.replace("_", " ").title()

    def _dashboard_is_alive(self, attr_name: str) -> bool:
        dashboard = getattr(self, attr_name, None)
        return dashboard is not None and is_qobject_valid(dashboard)

    def _ribbon_context_needs_build(self, context_id: str) -> bool:
        # Kept for older call sites. Current ribbon navigation intentionally shows
        # the full-screen loader for every non-home tab click, even when a
        # dashboard already exists, so users always receive immediate feedback.
        context = str(context_id or "").strip()
        return bool(context and context != "home")

    def _activate_existing_workspace(self, module_id: str) -> QWidget | None:
        """Activate an already-open document for *module_id*, regardless of the current tab."""
        for index in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(index)
            if widget is not None and str(widget.property("module_id") or "") == module_id:
                self.tab_widget.setCurrentIndex(index)
                widget.show()
                widget.raise_()
                widget.setFocus(Qt.OtherFocusReason)
                return widget
        return None

    def _activate_ribbon_workspace_context(self, context_id: str) -> None:
        context = str(context_id or "home")
        try:
            if context == "home":
                return
            if not self._is_context_licensed(context):
                self._show_purchase_required(feature_for_provider(context), self._ribbon_provider_to_main.get(context, context))
                return

            # Each seismic subtab now owns its actual workspace.  Previously all
            # four contexts were routed to Data Quality, so clicking SEG-D, SEG-Y
            # Viewer or SEG-Y QC appeared to open the same pair of documents.
            if context in {"seismic", "segd"}:
                if self._activate_existing_workspace("segd") is None:
                    self._open_segd_viewer()
                return
            if context == "segy_viewer":
                if self._activate_existing_workspace("segy_viewer") is None:
                    self._open_segy_file()
                return
            if context == "segy_qc":
                if not self.activate_segy_qc_view():
                    self._warn_segy_qc_unavailable()
                return
            if context == "segd_scanner":
                self._open_segd_scanner_dashboard()
                return
            if context == "receiver_qc":
                self._open_receiver_qc_dashboard()
                return
            if context == "uphole":
                self._open_uphole_dashboard()
                return
            if context == "converter":
                self._open_converter_page()
                return
            if context == "visualization":
                if self._activate_existing_workspace("visualization") is None:
                    self._open_visualization()
                return

            if context.startswith("magnetic"):
                dashboard = self._open_magnetic_dashboard()
                tabs = getattr(dashboard, "tabs", None) if dashboard is not None else None
                if tabs is not None:
                    index_map = {
                        "magnetic_data": getattr(dashboard, "TAB_OVERVIEW", 0),
                        "magnetic_qc": getattr(dashboard, "TAB_QC", 2),
                        "magnetic_processing": getattr(dashboard, "TAB_PROCESSING", 4),
                        "magnetic_viewer": getattr(dashboard, "TAB_SPATIAL", 7),
                        "magnetic_reports": getattr(dashboard, "TAB_QC", 2),
                    }
                    if context in index_map:
                        tabs.setCurrentIndex(index_map[context])
                return

            if context.startswith("electrical"):
                dashboard = self._open_electrical_dashboard()
                if dashboard is not None:
                    widget_map = {
                        "electrical_data": getattr(dashboard, "overview_tab", None),
                        "electrical_qc": getattr(dashboard, "qc_tab", None),
                        "electrical_processing": getattr(dashboard, "plot_tab", None),
                        "electrical_viewer": getattr(dashboard, "spatial_tab", None),
                        "electrical_reports": getattr(dashboard, "guide_tab", None),
                    }
                    target = widget_map.get(context)
                    tabs = getattr(dashboard, "tabs", None)
                    if tabs is not None and target is not None:
                        tabs.setCurrentWidget(target)
                return

            if context.startswith("gravity"):
                dashboard = self._open_gravity_dashboard()
                tabs = getattr(dashboard, "tabs", None) if dashboard is not None else None
                if tabs is not None:
                    index_map = {
                        "gravity_data": getattr(dashboard, "TAB_OBSERVATIONS", getattr(dashboard, "TAB_OVERVIEW", 0)),
                        "gravity_qc": getattr(dashboard, "TAB_QC", 2),
                        "gravity_processing": getattr(dashboard, "TAB_PROCESSING", 3),
                        "gravity_viewer": getattr(dashboard, "TAB_SPATIAL", getattr(dashboard, "TAB_MAP", 4)),
                        "gravity_reports": getattr(dashboard, "TAB_REPORTS", getattr(dashboard, "TAB_QC", 2)),
                    }
                    if context in index_map:
                        tabs.setCurrentIndex(index_map[context])
                return

            if context.startswith("vibroseis"):
                dashboard = self._open_vibroseis_dashboard()
                if dashboard is not None:
                    # The main Vibroseis tab and the Data subtab both open the
                    # actual dashboard, not just the ribbon command strip.
                    if context in {"vibroseis", "vibroseis_data", "vibroseis_sweep"}:
                        dashboard.show_sweep()
                    elif context == "vibroseis_qc":
                        dashboard.show_signal_qc()
                    elif context == "vibroseis_viewer":
                        dashboard.show_geospatial_view("2d")
                    elif context == "vibroseis_planning":
                        dashboard.show_productivity()
                return

            if context.startswith("geodetic"):
                dashboard = self._open_geodetic_dashboard()
                if dashboard is not None:
                    page_map = {
                        "geodetic": getattr(dashboard, "TAB_OVERVIEW", 0),
                        "geodetic_data": getattr(dashboard, "TAB_EXAMINER", 1),
                        "geodetic_qc": getattr(dashboard, "TAB_QC", 2),
                        "geodetic_coordinates": getattr(dashboard, "TAB_COORDINATES", 3),
                        "geodetic_viewer": getattr(dashboard, "TAB_SPATIAL", 4),
                        "geodetic_reports": getattr(dashboard, "TAB_REPORT", 6),
                    }
                    target = page_map.get(context)
                    show_page = getattr(dashboard, "_show_page", None)
                    if target is not None and callable(show_page):
                        show_page(target)
                return
        except Exception as exc:
            self.log(f"Ribbon workspace activation failed for {context}: {exc}")

    def _register_ribbon_provider(self, provider: Any) -> None:
        """Register a content provider without creating another top-level tab."""
        self._ribbon_providers[provider.ribbon_tab_id()] = provider

    @staticmethod
    def _clear_tab_bar(tab_bar: QTabBar) -> None:
        """Remove every tab from a QTabBar in a PySide6-compatible way.

        QTabBar does not expose QTabWidget.clear(); removing tabs explicitly keeps
        this code compatible across supported Qt/PySide6 versions.
        """
        while tab_bar.count() > 0:
            tab_bar.removeTab(tab_bar.count() - 1)

    def _configure_ribbon_navigation(self) -> None:
        """Create the mandatory six-tab ribbon and map secondary contexts."""
        self.ribbon_tab_bar.blockSignals(True)
        self._clear_tab_bar(self.ribbon_tab_bar)
        self._ribbon_tabs.clear()
        self._ribbon_full_labels.clear()
        for tab_id, label in (
            ("home", "Home"),
            ("seismic", "Seismic"),
            ("magnetic", "Magnetic"),
            ("electrical", "Electrical"),
            ("gravity", "Gravity"),
            ("vibroseis", "Vibroseis"),
            ("geodetic", "Geodetic"),
        ):
            self._add_ribbon_tab(tab_id, label)
        self.ribbon_tab_bar.blockSignals(False)

        self._ribbon_provider_to_main.clear()
        for main_id, items in self._ribbon_structure.items():
            for provider_id, _label in items:
                self._ribbon_provider_to_main[provider_id] = main_id
        # Legacy/document module identifiers resolve to the correct modern context.
        self._ribbon_provider_to_main.update({
            "seismic": "seismic",
            "magnetic": "magnetic",
            "gravity": "gravity",
            "electrical": "electrical",
            "vibroseis": "vibroseis",
            "geodetic": "geodetic",
            "segy_qc": "seismic",
            "segy_viewer": "seismic",
            "segd": "seismic",
            "converter": "seismic",
            "visualization": "seismic",
            "segd_scanner": "seismic",
            "receiver_qc": "seismic",
            "uphole": "seismic",
        })

    def _default_provider_for_main(self, main_id: str) -> str:
        items = self._ribbon_structure.get(main_id, [])
        if not items:
            return "home"
        remembered = self._last_subtab_by_main.get(main_id)
        valid = {provider_id for provider_id, _ in items}
        if remembered in valid and self._is_provider_licensed(remembered):
            return remembered
        for provider_id, _label in items:
            if self._is_provider_licensed(provider_id):
                return provider_id
        return items[0][0]

    def _populate_ribbon_subtabs(self, main_id: str, selected_provider: str | None = None) -> None:
        items = self._ribbon_structure.get(main_id, [])
        self.ribbon_sub_tab_bar.blockSignals(True)
        self._clear_tab_bar(self.ribbon_sub_tab_bar)
        selected_index = 0
        for idx, (provider_id, label) in enumerate(items):
            display_label = f"{label} 🔒" if not self._is_provider_licensed(provider_id) else label
            tab_index = self.ribbon_sub_tab_bar.addTab(display_label)
            self.ribbon_sub_tab_bar.setTabData(tab_index, provider_id)
            if provider_id == selected_provider:
                selected_index = idx
        self.ribbon_sub_tab_bar.setCurrentIndex(selected_index if items else -1)
        self.ribbon_sub_tab_bar.blockSignals(False)
        # Home is intentionally flat; all technical modules use a secondary row.
        self.ribbon_sub_header.setVisible(len(items) > 1)

    def _set_active_module(self, module_id: str) -> None:
        requested = str(module_id or "home")
        if requested == "home":
            main_id, provider_id = "home", "home"
        elif requested == "segy_qc":
            # SEG-Y QC commands are now combined into the single SEG-Y ribbon tab.
            # The document can still carry module_id=segy_qc for workspace logic.
            main_id, provider_id = "seismic", "segy_viewer"
        elif requested in {"seismic", "magnetic", "electrical", "gravity", "vibroseis", "geodetic"}:
            main_id = requested
            provider_id = self._default_provider_for_main(main_id)
        else:
            main_id = self._ribbon_provider_to_main.get(requested, "home")
            provider_id = requested if requested in self._ribbon_providers else self._default_provider_for_main(main_id)

        self._active_main_tab = main_id
        self._active_module = provider_id
        self._last_subtab_by_main[main_id] = provider_id

        index = self._ribbon_tabs.get(main_id)
        if index is not None and self.ribbon_tab_bar.currentIndex() != index:
            self.ribbon_tab_bar.blockSignals(True)
            self.ribbon_tab_bar.setCurrentIndex(index)
            self.ribbon_tab_bar.blockSignals(False)

        self._populate_ribbon_subtabs(main_id, provider_id)
        self._update_ribbon()

    def _update_ribbon(self) -> None:
        # QTabWidget can emit currentChanged while the central workspace is being
        # constructed, before the ribbon widgets exist. Ignore those bootstrap
        # notifications and perform the normal refresh once ribbon creation ends.
        if not hasattr(self, "ribbon_groups_layout") or not hasattr(self, "ribbon_groups_background"):
            return
        self._clear_ribbon_groups()
        
        if self._active_module in self._ribbon_providers and self._ribbon_providers[self._active_module]:
            try:
                provider = self._ribbon_providers[self._active_module]
                groups = provider.build_ribbon_groups()
                action_count = sum(len(getattr(group, "actions", [])) for group in groups)
                # Dense contexts use the compact Office-style command geometry
                # even on wide monitors; this prevents the 2D/3D ribbon from
                # overflowing while preserving every command.
                dense = len(groups) >= 5 or action_count >= 18
                self.ribbon_groups_container._responsive_mode = "compact" if dense else self._responsive_mode
                
                for i, group in enumerate(groups):
                    if i > 0:
                        self._add_ribbon_separator()
                    self._add_ribbon_group(group)
                self.ribbon_groups_layout.addStretch(1)
                self._sync_ribbon_group_canvas()
                
                self.ribbon_groups_container.setVisible(True)
                self.ribbon_groups_background.setVisible(True)
                self._animate_ribbon()
            except Exception as e:
                self.log(f"Error building ribbon: {e}")
                self.ribbon_groups_container.setVisible(False)
                self.ribbon_groups_background.setVisible(False)
        else:
            self.ribbon_groups_container.setVisible(False)
            self.ribbon_groups_background.setVisible(False)

    def _clear_ribbon_groups(self) -> None:
        if not hasattr(self, "ribbon_groups_layout"):
            return
        self.ribbon_groups_container.setMinimumWidth(0)
        while self.ribbon_groups_layout.count():
            child = self.ribbon_groups_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _add_ribbon_separator(self) -> None:
        line = QFrame()
        line.setObjectName("ribbonSeparator")
        line.setFrameShape(QFrame.VLine)
        line.setFixedHeight(78)
        self.ribbon_groups_layout.addWidget(line)

    def _add_ribbon_group(self, group: Any) -> None:
        try:
            from ui.ribbon.ribbon_group_widget import RibbonGroupWidget
            widget = RibbonGroupWidget(group, self.ribbon_groups_container)
            widget.action_triggered.connect(self._on_ribbon_action)
            widget.details_requested.connect(self._update_feature_inspector)
            self.ribbon_groups_layout.addWidget(widget)
        except ImportError:
            self.log("RibbonGroupWidget not available")

    def _sync_ribbon_group_canvas(self) -> None:
        """Size the ribbon canvas to its command content without visual overflow."""
        if not hasattr(self, "ribbon_groups_container"):
            return
        self.ribbon_groups_layout.activate()
        hint = self.ribbon_groups_layout.sizeHint()
        viewport_width = 0
        if hasattr(self, "ribbon_groups_scroll"):
            viewport_width = max(0, self.ribbon_groups_scroll.viewport().width())
        width = max(viewport_width, hint.width() + 8)
        self.ribbon_groups_container.resize(width, self.ribbon_groups_container.height())
        self.ribbon_groups_container.setMinimumWidth(width)

    def _animate_ribbon(self) -> None:
        animation = QPropertyAnimation(self.ribbon_groups_container, b"windowOpacity", self)
        animation.setDuration(150)
        animation.setStartValue(0.65)
        animation.setEndValue(1.0)
        animation.start()
        self._ribbon_animation = animation

    def is_ribbon_action_enabled(self, action_id: str) -> bool:
        """Return whether an action's prerequisites are currently satisfied.

        Ribbon buttons query this every time a ribbon is rebuilt, so commands
        become available immediately after a file is loaded/QC finishes and are
        disabled again when their owning workspace closes.
        """
        if not self._is_action_licensed(action_id):
            return False
        always = {
            "new_project", "open_project", "about", "preferences", "shortcuts",
            "documentation", "report_issue", "reset_layout", "toggle_explorer",
            "subscription_modules", "logout_account",
            "toggle_properties", "toggle_console", "save_layout", "load_layout",
            "segd_open_file", "segd_open_viewer", "segd_open_2d3d", "segy_open_file", "segy_open_2d3d",
            "visualization_open",
            "magnetic_open", "magnetic_open_rover", "magnetic_open_base", "magnetic_open_boundary",
            "gravity_open", "gravity_open_observations", "gravity_open_base",
            "electrical_open", "electrical_open_data", "electrical_thresholds",
            "geodetic_open", "geodetic_examiner",
            "segd_scanner_open", "segd_scanner_folder", "receiver_open", "receiver_limits",
            "uphole_open", "uphole_open_folder", "vibroseis_load_vaps",
        }
        if action_id in always:
            return True

        project_open = self._workspace_manager.current_project_file is not None
        if action_id in {"save_project", "import_file", "export_data", "project_properties", "refresh_project", "qc_history"}:
            return project_open

        if action_id.startswith("segd_scanner_"):
            dashboard = self._segd_scanner_dashboard
            if dashboard is None:
                return action_id in {"segd_scanner_open", "segd_scanner_folder"}
            resolver = getattr(dashboard, "can_execute", None)
            return bool(resolver(action_id)) if callable(resolver) else True

        if action_id.startswith("receiver_"):
            dashboard = self._receiver_qc_dashboard
            if dashboard is None:
                return action_id in {"receiver_open", "receiver_limits"}
            resolver = getattr(dashboard, "can_execute", None)
            return bool(resolver(action_id)) if callable(resolver) else True

        if action_id.startswith("uphole_"):
            dashboard = self._uphole_dashboard
            if dashboard is None:
                return action_id in {"uphole_open", "uphole_open_folder"}
            resolver = getattr(dashboard, "can_execute", None)
            return bool(resolver(action_id)) if callable(resolver) else True

        if action_id.startswith("segd_"):
            return self._active_segd_viewer() is not None

        if action_id.startswith("segy_"):
            view = self._get_segy_qc_view()
            controller = getattr(view, "controller", None) if view is not None else None
            has_file = bool(getattr(controller, "file_path", None))
            has_run = bool(getattr(view, "current_run_uuid", None) or getattr(controller, "current_run_uuid", None))
            has_post = bool(getattr(view, "post_qc_file_path", None)) if view is not None else False
            if action_id in {"segy_select_base", "segy_view_raw", "segy_select_post_qc"}:
                return has_file
            if action_id in {"segy_view_post_qc", "segy_compare_pre_post"}:
                return has_file and has_post
            if action_id == "segy_run_qc":
                return has_file and getattr(controller, "current_job_id", None) is None
            if action_id == "segy_cancel_qc":
                return bool(controller and getattr(controller, "current_job_id", None) is not None)
            if action_id in {"segy_view_results", "segy_generate_pdf", "segy_generate_xlsx"} or action_id.startswith("segy_stage_"):
                return has_run
            return True

        if action_id.startswith("visualization_"):
            return self._active_visualization() is not None

        if action_id.startswith("magnetic_"):
            dashboard = self._magnetic_dashboard
            if dashboard is None:
                return False
            resolver = getattr(dashboard, "can_execute", None)
            if callable(resolver):
                return bool(resolver(action_id))
            has_data = getattr(dashboard, "rover", None) is not None
            has_qc = getattr(dashboard, "last_result", None) is not None or getattr(dashboard, "qc_result", None) is not None
            if action_id in {"magnetic_report_pdf", "magnetic_report_xlsx"}:
                return has_qc
            return has_data

        if action_id.startswith("gravity_"):
            dashboard = self._gravity_dashboard
            if dashboard is None:
                return False
            resolver = getattr(dashboard, "can_execute", None)
            return bool(resolver(action_id)) if callable(resolver) else getattr(dashboard, "observations", None) is not None

        if action_id.startswith("electrical_"):
            dashboard = self._electrical_dashboard
            if dashboard is None:
                return action_id.startswith("electrical_method_")
            resolver = getattr(dashboard, "can_execute", None)
            if callable(resolver):
                return bool(resolver(action_id))
            has_data = getattr(dashboard, "dataset", None) is not None
            has_qc = getattr(dashboard, "qc_result", None) is not None
            if action_id in {"electrical_report_pdf", "electrical_report_xlsx", "electrical_results"}:
                return has_qc
            if action_id.startswith("electrical_method_"):
                return True
            return has_data

        if action_id.startswith("vibroseis_"):
            dashboard = self._vibroseis_dashboard
            if dashboard is None:
                return action_id in {"vibroseis_open", "vibroseis_load", "vibroseis_sweep", "vibroseis_generate", "vibroseis_productivity", "vibroseis_load_vaps", "vibroseis_signal_qc", "vibroseis_ground_force", "vibroseis_vaps_qc"}
            resolver = getattr(dashboard, "can_execute", None)
            return bool(resolver(action_id)) if callable(resolver) else True

        if action_id.startswith("geodetic_"):
            dashboard = self._geodetic_dashboard
            if dashboard is None:
                return action_id in {"geodetic_open", "geodetic_examiner"}
            resolver = getattr(dashboard, "can_execute", None)
            return bool(resolver(action_id)) if callable(resolver) else True

        if action_id in {"cross_plot", "map", "histogram", "statistics", "view_headers"}:
            return bool(self._selected_project_path and self._selected_project_path.is_file())
        if action_id in {"batch_qc", "batch_export", "batch_process"}:
            return project_open
        return True

    def _show_feature_details(self, action_id: str = "workspace") -> None:
        from ui.feature_registry import get_feature_detail
        from ui.dialogs.feature_details_dialog import FeatureDetailsDialog
        FeatureDetailsDialog(get_feature_detail(action_id), self).exec()

    def _on_ribbon_action(self, action_id: str) -> None:
        if not self._is_action_licensed(action_id):
            self._show_purchase_required(feature_for_action(action_id), self._active_main_tab)
            return
        if not self.is_ribbon_action_enabled(action_id):
            self.status_bar.showMessage("This feature becomes available when its required data or QC result is ready.", 4000)
            return
        if action_id == "new_project":
            self._new_project()
        elif action_id == "open_project":
            self._open_project()
        elif action_id == "save_project":
            self._save_project()
        elif action_id == "import_file":
            self._import_file()
        elif action_id == "export_data":
            self._export_data()
        elif action_id == "subscription_modules":
            self.open_subscription_dialog()
        elif action_id == "logout_account":
            self._logout_account()
        elif action_id in {"segd_open_file", "segd_open_viewer"}:
            self._open_segd_viewer()
        elif action_id == "segd_open_2d3d":
            self._open_visualization()
        elif action_id == "segd_reload":
            self._apply_to_active_segd("reload_file")
        elif action_id == "segd_headers":
            self._apply_to_active_segd("toggle_headers")
        elif action_id == "segd_display_wiggle":
            self._apply_to_active_segd("set_display_mode", "wiggle")
        elif action_id == "segd_display_vd":
            self._apply_to_active_segd("set_display_mode", "variable_density")
        elif action_id == "segd_display_color":
            self._apply_to_active_segd("set_display_mode", "color_density")
        elif action_id == "segd_display_wiggle_color":
            self._apply_to_active_segd("set_display_mode", "wiggle_color")
        elif action_id == "segd_display_va":
            self._apply_to_active_segd("set_display_mode", "variable_area")
        elif action_id == "segd_gain_none":
            self._apply_to_active_segd("set_gain_mode", "none")
        elif action_id == "segd_gain_agc":
            self._apply_to_active_segd("set_gain_mode", "agc")
        elif action_id == "segd_gain_trace_balance":
            self._apply_to_active_segd("set_gain_mode", "trace_balance")
        elif action_id == "segd_gain_fixed":
            self._apply_to_active_segd("set_gain_mode", "fixed")
        elif action_id == "segd_pan":
            self._apply_to_active_segd("set_interaction_mode", "pan")
        elif action_id == "segd_pick":
            self._apply_to_active_segd("set_interaction_mode", "pick")
        elif action_id == "segd_measure":
            self._apply_to_active_segd("set_interaction_mode", "measure")
        elif action_id == "segd_zoom_fit":
            self._apply_to_active_segd("zoom_to_fit")
        elif action_id == "segd_run_qc":
            self._apply_to_active_segd("run_qc", "full")
        elif action_id == "segd_header_qc":
            self._apply_to_active_segd("run_qc", "header")
        elif action_id == "segd_trace_qc":
            self._apply_to_active_segd("run_qc", "trace")
        elif action_id == "segd_export_image":
            self._apply_to_active_segd("export_image")
        elif action_id.startswith("segy_viewer_"):
            viewer = self._active_segy_viewer()
            if viewer is None:
                self.status_bar.showMessage("Open a SEG-Y viewer first", 2500)
            elif action_id == "segy_viewer_export_image":
                viewer.export_image()
            elif action_id == "segy_viewer_fit":
                viewer.fit()
            elif action_id == "segy_viewer_wiggle":
                viewer.mode.setCurrentIndex(viewer.mode.findData("wiggle"))
            elif action_id == "segy_viewer_va":
                viewer.mode.setCurrentIndex(viewer.mode.findData("va"))
            elif action_id == "segy_viewer_vd":
                viewer.mode.setCurrentIndex(viewer.mode.findData("vd"))
            elif action_id == "segy_viewer_color":
                viewer.mode.setCurrentIndex(viewer.mode.findData("color"))
            elif action_id == "segy_viewer_headers":
                if hasattr(viewer, "show_headers_page"):
                    viewer.show_headers_page()
            elif action_id == "segy_viewer_trace_analysis":
                if hasattr(viewer, "show_trace_analysis_page"):
                    viewer.show_trace_analysis_page()
        elif action_id == "segy_open_2d3d":
            self._open_visualization()
        elif action_id == "segy_view_raw":
            self._view_segy_raw()
        elif action_id == "segy_select_post_qc":
            self._select_segy_post_qc()
        elif action_id == "segy_view_post_qc":
            self._view_segy_post_qc()
        elif action_id == "segy_compare_pre_post":
            self._compare_segy_pre_post()
        elif action_id == "segy_select_base":
            self._select_segy_repeatability_base()
        elif action_id.startswith("segy_stage_"):
            self._focus_segy_processing_stage(action_id.removeprefix("segy_stage_"))
        elif action_id == "segy_run_qc":
            self._run_segy_qc()
        elif action_id == "segy_cancel_qc":
            self._cancel_segy_qc()
        elif action_id == "segy_view_results":
            self._view_segy_results()
        elif action_id == "segy_edit_profile":
            self._edit_segy_qc_profile()
        elif action_id == "segy_open_dashboard":
            self._open_data_quality_dashboard()
        elif action_id == "segy_generate_pdf":
            self._generate_report("pdf")
        elif action_id == "segy_generate_xlsx":
            self._generate_report("xlsx")
        elif action_id == "segy_convert_to_segd":
            self._open_converter_page()
        elif action_id == "segd_scanner_open":
            self._open_segd_scanner_dashboard().scan_file()
        elif action_id == "segd_scanner_folder":
            self._open_segd_scanner_dashboard().scan_folder()
        elif action_id == "segd_scanner_export":
            self._open_segd_scanner_dashboard().export_csv()
        elif action_id == "segd_scanner_results":
            self._open_segd_scanner_dashboard().show_results()
        elif action_id == "segd_scanner_guide":
            self._open_segd_scanner_dashboard().show_guide()
        elif action_id == "receiver_open":
            self._open_receiver_qc_dashboard().open_file()
        elif action_id == "receiver_run_qc":
            self._open_receiver_qc_dashboard().run_qc()
        elif action_id == "receiver_export":
            self._open_receiver_qc_dashboard().export_results()
        elif action_id == "receiver_records":
            self._open_receiver_qc_dashboard().show_records()
        elif action_id == "receiver_failures":
            self._open_receiver_qc_dashboard().show_failures()
        elif action_id == "receiver_limits":
            self._open_receiver_qc_dashboard().show_limits()
        elif action_id == "receiver_statistics":
            self._open_receiver_qc_dashboard().show_statistics()
        elif action_id == "uphole_open":
            self._open_uphole_dashboard().open_file()
        elif action_id == "uphole_open_folder":
            self._open_uphole_dashboard().open_folder()
        elif action_id == "uphole_interpret":
            self._open_uphole_dashboard().interpret()
        elif action_id == "uphole_export":
            self._open_uphole_dashboard().export_csv()
        elif action_id == "uphole_assignments":
            self._open_uphole_dashboard().show_assignment()
        elif action_id == "uphole_time_depth":
            self._open_uphole_dashboard().show_time_depth()
        elif action_id == "uphole_layers":
            self._open_uphole_dashboard().show_layers()
        elif action_id == "uphole_guide":
            self._open_uphole_dashboard().show_guide()
        elif action_id == "converter_open":
            self._open_converter_page().open_single_file()
        elif action_id == "converter_add":
            self._open_converter_page().add_files()
        elif action_id == "converter_clear":
            self._open_converter_page().clear_files()
        elif action_id == "converter_run":
            self._open_converter_page().start_conversion()
        elif action_id == "converter_cancel":
            self._open_converter_page().cancel_conversion()
        elif action_id == "converter_inspect":
            self._open_converter_page().inspect_sources()
        elif action_id == "converter_validate":
            self._open_converter_page().validate_output()
        elif action_id == "converter_open_output":
            self._open_converter_page().open_last_output()
        elif action_id == "vibroseis_open":
            self._open_vibroseis_dashboard()
        elif action_id == "vibroseis_load":
            self._open_vibroseis_dashboard().open_telemetry()
        elif action_id == "vibroseis_load_vaps":
            dashboard = self._open_vibroseis_dashboard(); dashboard.show_vaps_qc(); dashboard.open_vaps()
        elif action_id == "vibroseis_vaps_qc":
            dashboard = self._open_vibroseis_dashboard(); dashboard.show_vaps_qc(); dashboard.run_vaps_qc()
        elif action_id == "vibroseis_sweep":
            self._open_vibroseis_dashboard().show_sweep()
        elif action_id == "vibroseis_generate":
            dashboard = self._open_vibroseis_dashboard(); dashboard.show_sweep(); dashboard.design_sweep()
        elif action_id == "vibroseis_export_pilot":
            self._open_vibroseis_dashboard().export_pilot()
        elif action_id == "vibroseis_signal_qc":
            dashboard = self._open_vibroseis_dashboard(); dashboard.show_signal_qc(); dashboard.run_signal_qc()
        elif action_id == "vibroseis_correlation":
            dashboard = self._open_vibroseis_dashboard(); dashboard.show_signal_qc(); dashboard.correlate_trace()
        elif action_id == "vibroseis_ground_force":
            dashboard = self._open_vibroseis_dashboard(); dashboard.show_ground_force(); dashboard.calculate_ground_force()
        elif action_id == "vibroseis_productivity":
            dashboard = self._open_vibroseis_dashboard(); dashboard.show_productivity(); dashboard.calculate_productivity()
        elif action_id == "vibroseis_view_2d":
            self._open_vibroseis_dashboard().show_geospatial_view("2d")
        elif action_id == "vibroseis_view_3d":
            self._open_vibroseis_dashboard().show_geospatial_view("3d")
        elif action_id == "vibroseis_satellite":
            self._open_vibroseis_dashboard().show_geospatial_view("2d")
        elif action_id == "geodetic_open":
            self._apply_to_geodetic("open_file")
        elif action_id == "geodetic_examiner":
            self._apply_to_geodetic("show_examiner")
        elif action_id == "geodetic_text_results":
            self._apply_to_geodetic("show_text_results")
        elif action_id == "geodetic_export_text":
            self._apply_to_geodetic("export_text")
        elif action_id == "geodetic_export_xlsx":
            self._apply_to_geodetic("export_xlsx")
        elif action_id == "geodetic_run_qc":
            self._apply_to_geodetic("run_qc")
        elif action_id == "geodetic_qc_results":
            self._apply_to_geodetic("show_qc")
        elif action_id == "geodetic_graph_prev":
            self._apply_to_geodetic("previous_graph_page")
        elif action_id == "geodetic_graph_next":
            self._apply_to_geodetic("next_graph_page")
        elif action_id == "geodetic_export_graphs":
            self._apply_to_geodetic("export_graphs")
        elif action_id == "geodetic_positions":
            self._apply_to_geodetic("show_positions")
        elif action_id == "geodetic_vectors":
            self._apply_to_geodetic("show_vectors")
        elif action_id == "geodetic_datum_crs":
            self._apply_to_geodetic("show_datum_crs")
        elif action_id == "geodetic_equipment":
            self._apply_to_geodetic("show_equipment")
        elif action_id == "geodetic_view_2d":
            self._apply_to_geodetic("show_native_view", "2d")
        elif action_id == "geodetic_view_3d":
            self._apply_to_geodetic("show_native_view", "3d")
        elif action_id == "geodetic_satellite":
            self._apply_to_geodetic("show_geospatial_view", "2d")
        elif action_id == "geodetic_terrain":
            self._apply_to_geodetic("show_geospatial_view", "3d")
        elif action_id == "geodetic_report_pdf":
            self._apply_to_geodetic("generate_report")
        elif action_id == "magnetic_open":
            self._open_magnetic_dashboard()
        elif action_id == "magnetic_open_rover":
            self._apply_to_magnetic("open_rover")
        elif action_id == "magnetic_open_base":
            self._apply_to_magnetic("open_base")
        elif action_id == "magnetic_open_boundary":
            self._apply_to_magnetic("open_boundary")
        elif action_id == "magnetic_view_2d":
            self._apply_to_magnetic("show_native_view", "2d")
        elif action_id == "magnetic_view_3d":
            self._apply_to_magnetic("show_native_view", "3d")
        elif action_id == "magnetic_satellite":
            self._apply_to_magnetic("show_geospatial_view", "2d")
        elif action_id == "magnetic_terrain":
            self._apply_to_magnetic("show_geospatial_view", "3d")
        elif action_id == "magnetic_run_full":
            self._apply_to_magnetic("run_full_qc")
        elif action_id == "magnetic_run_raw":
            self._apply_to_magnetic("run_raw_qc")
        elif action_id == "magnetic_run_processed":
            self._apply_to_magnetic("run_processed_qc")
        elif action_id == "magnetic_cancel":
            self._apply_to_magnetic("cancel_qc")
        elif action_id == "magnetic_despike":
            self._apply_to_magnetic("process_despike")
        elif action_id == "magnetic_diurnal":
            self._apply_to_magnetic("process_diurnal")
        elif action_id == "magnetic_level":
            self._apply_to_magnetic("process_leveling")
        elif action_id == "magnetic_microlevel":
            self._apply_to_magnetic("process_microlevel")
        elif action_id == "magnetic_grid":
            self._apply_to_magnetic("generate_grid")
        elif action_id == "magnetic_map":
            self._apply_to_magnetic("show_map")
        elif action_id == "magnetic_profile":
            self._apply_to_magnetic("show_profile")
        elif action_id == "magnetic_export_csv":
            self._apply_to_magnetic("export_csv")
        elif action_id == "magnetic_report_pdf":
            self._apply_to_magnetic("generate_report", "pdf")
        elif action_id == "magnetic_report_xlsx":
            self._apply_to_magnetic("generate_report", "xlsx")
        elif action_id == "gravity_open":
            self._open_gravity_dashboard()
        elif action_id == "gravity_open_observations":
            self._apply_to_gravity("open_observations")
        elif action_id == "gravity_open_base":
            self._apply_to_gravity("open_base")
        elif action_id == "gravity_view_2d":
            self._apply_to_gravity("show_native_view", "2d")
        elif action_id == "gravity_view_3d":
            self._apply_to_gravity("show_native_view", "3d")
        elif action_id == "gravity_satellite":
            self._apply_to_gravity("show_geospatial_view", "2d")
        elif action_id == "gravity_run_full":
            self._apply_to_gravity("run_full_qc")
        elif action_id == "gravity_run_field":
            self._apply_to_gravity("run_field_qc")
        elif action_id == "gravity_run_final":
            self._apply_to_gravity("run_final_qc")
        elif action_id == "gravity_cancel":
            self._apply_to_gravity("cancel_qc")
        elif action_id == "gravity_reduce":
            self._apply_to_gravity("process_standard")
        elif action_id == "gravity_grid":
            self._apply_to_gravity("generate_grid")
        elif action_id == "gravity_map":
            self._apply_to_gravity("show_map")
        elif action_id == "gravity_profile":
            self._apply_to_gravity("show_profile")
        elif action_id == "gravity_export_csv":
            self._apply_to_gravity("export_csv")
        elif action_id == "gravity_report_pdf":
            self._apply_to_gravity("generate_report", "pdf")
        elif action_id == "gravity_report_xlsx":
            self._apply_to_gravity("generate_report", "xlsx")
        elif action_id == "electrical_open":
            self._open_electrical_dashboard()
        elif action_id == "electrical_open_data":
            self._apply_to_electrical("open_data")
        elif action_id == "electrical_view_2d":
            self._apply_to_electrical("show_native_view", "2d")
        elif action_id == "electrical_view_3d":
            self._apply_to_electrical("show_native_view", "3d")
        elif action_id == "electrical_satellite":
            self._apply_to_electrical("show_geospatial_view", "2d")
        elif action_id == "electrical_terrain":
            self._apply_to_electrical("show_geospatial_view", "3d")
        elif action_id == "electrical_calculate":
            self._apply_to_electrical("calculate_fields")
        elif action_id == "electrical_method_ert":
            self._apply_to_electrical("set_method", "ert")
        elif action_id == "electrical_method_ves":
            self._apply_to_electrical("set_method", "ves")
        elif action_id == "electrical_method_profiling":
            self._apply_to_electrical("set_method", "profiling")
        elif action_id == "electrical_method_tdip":
            self._apply_to_electrical("set_method", "tdip")
        elif action_id == "electrical_method_fdip":
            self._apply_to_electrical("set_method", "fdip")
        elif action_id == "electrical_method_sip":
            self._apply_to_electrical("set_method", "sip")
        elif action_id == "electrical_method_sp":
            self._apply_to_electrical("set_method", "sp")
        elif action_id == "electrical_method_malm":
            self._apply_to_electrical("set_method", "malm")
        elif action_id == "electrical_method_equipotential":
            self._apply_to_electrical("set_method", "equipotential")
        elif action_id == "electrical_method_telluric":
            self._apply_to_electrical("set_method", "telluric")
        elif action_id == "electrical_run_qc":
            self._apply_to_electrical("run_full_qc")
        elif action_id == "electrical_thresholds":
            self._apply_to_electrical("configure_qc")
        elif action_id == "electrical_results":
            self._apply_to_electrical("show_qc_results")
        elif action_id == "electrical_sp_drift":
            self._apply_to_electrical("apply_sp_drift_correction")
        elif action_id == "electrical_despike":
            self._apply_to_electrical("despike_display_series")
        elif action_id == "electrical_pseudosection":
            self._apply_to_electrical("show_pseudosection")
        elif action_id == "electrical_profile":
            self._apply_to_electrical("show_profile")
        elif action_id == "electrical_export_csv":
            self._apply_to_electrical("export_csv")
        elif action_id == "electrical_report_pdf":
            self._apply_to_electrical("generate_report", "pdf")
        elif action_id == "electrical_report_xlsx":
            self._apply_to_electrical("generate_report", "xlsx")
        elif action_id == "visualization_open":
            self._open_visualization()
        elif action_id == "visualization_satellite":
            self._apply_to_active_visualization("show_geospatial_view", "2d")
        elif action_id == "visualization_terrain":
            self._apply_to_active_visualization("show_geospatial_view", "3d")
        elif action_id == "visualization_wiggle_density":
            self._apply_to_active_visualization("set_display_mode", "wiggle_density")
        elif action_id == "visualization_wiggle":
            self._apply_to_active_visualization("set_display_mode", "wiggle")
        elif action_id == "visualization_density":
            self._apply_to_active_visualization("set_display_mode", "variable_density")
        elif action_id == "visualization_fit":
            self._apply_to_active_visualization("zoom_to_fit")
        elif action_id == "visualization_gain_agc":
            self._apply_to_active_visualization("set_gain_mode", "agc")
        elif action_id == "visualization_gain_balance":
            self._apply_to_active_visualization("set_gain_mode", "trace_balance")
        elif action_id == "visualization_gain_none":
            self._apply_to_active_visualization("set_gain_mode", "none")
        elif action_id == "visualization_load_volume":
            self._apply_to_active_visualization("load_3d_volume")
        elif action_id == "visualization_show_volume":
            self._apply_to_active_visualization("show_volume")
        elif action_id == "visualization_inline":
            self._apply_to_active_visualization("show_inline_slice")
        elif action_id == "visualization_crossline":
            self._apply_to_active_visualization("show_crossline_slice")
        elif action_id == "visualization_time_slice":
            self._apply_to_active_visualization("show_time_slice")
        elif action_id == "visualization_pick_horizon":
            self._apply_to_active_visualization("begin_horizon_pick")
        elif action_id == "visualization_pick_fault":
            self._apply_to_active_visualization("begin_fault_pick")
        elif action_id == "visualization_measure":
            self._apply_to_active_visualization("begin_measurement")
        elif action_id == "visualization_undo_pick":
            self._apply_to_active_visualization("undo_pick")
        elif action_id == "visualization_stop_pick":
            self._apply_to_active_visualization("stop_picking")
        elif action_id == "visualization_bad_traces":
            self._apply_to_active_visualization("detect_bad_traces")
        elif action_id == "visualization_noise_overlay":
            self._apply_to_active_visualization("toggle_noise_overlay")
        elif action_id == "visualization_save_session":
            self._apply_to_active_visualization("save_session")
        elif action_id == "visualization_load_session":
            self._apply_to_active_visualization("load_session")
        elif action_id == "visualization_add_well":
            self._apply_to_active_visualization("add_well_path")
        elif action_id == "visualization_export_png":
            self._apply_to_active_visualization("export_png")
        elif action_id == "visualization_export_geotiff":
            self._apply_to_active_visualization("export_geotiff")
        elif action_id == "visualization_export_kml":
            self._apply_to_active_visualization("export_kml")
        elif action_id == "visualization_export_shapefile":
            self._apply_to_active_visualization("export_shapefile")
        elif action_id == "visualization_export_html":
            self._apply_to_active_visualization("export_html_report")
        elif action_id == "visualization_export_pdf":
            self._apply_to_active_visualization("export_pdf_report")
        elif action_id == "visualization_export_animation":
            self._apply_to_active_visualization("export_animation")
        elif action_id == "reset_layout":
            self._reset_layout()
        elif action_id == "toggle_explorer":
            self.project_dock.setVisible(not self.project_dock.isVisible())
        elif action_id == "toggle_properties":
            self.properties_dock.setVisible(not self.properties_dock.isVisible())
        elif action_id == "toggle_console":
            self.output_dock.setVisible(not self.output_dock.isVisible())
        elif action_id == "about":
            self._show_about()
        elif action_id == "project_properties":
            self._show_project_properties()
        elif action_id == "refresh_project":
            self._refresh_project()
        elif action_id == "qc_history":
            self._open_qc_history_page()
        elif action_id == "copy":
            self._copy_selection()
        elif action_id == "paste":
            self._paste_selection()
        elif action_id == "cut":
            self._cut_selection()
        elif action_id == "segy_open_file":
            self._open_segy_file()
        elif action_id == "seg2_open":
            self._open_seg2_file()
        elif action_id == "segb_open":
            self._open_segb_file()
        elif action_id == "ukooa_open":
            self._open_ukooa_file()
        elif action_id == "navigation_open":
            self._open_navigation_file()
        elif action_id == "seismic_validate":
            self._validate_seismic_data()
        elif action_id == "seismic_process":
            self._process_seismic_data()
        elif action_id == "save_layout":
            self._save_layout()
        elif action_id == "load_layout":
            self._load_layout()
        elif action_id == "view_headers":
            self._view_headers()
        elif action_id == "zoom_fit":
            self._zoom_to_fit()
        elif action_id == "zoom_in":
            self._zoom_in()
        elif action_id == "zoom_out":
            self._zoom_out()
        elif action_id == "zoom_100":
            self._zoom_100()
        elif action_id == "cross_plot":
            self._open_cross_plot()
        elif action_id == "map":
            self._open_map_view()
        elif action_id == "histogram":
            self._open_histogram()
        elif action_id == "statistics":
            self._open_statistics()
        elif action_id == "batch_qc":
            self._run_batch_qc()
        elif action_id == "batch_export":
            self._run_batch_export()
        elif action_id == "batch_process":
            self._run_batch_process()
        elif action_id == "preferences":
            self._open_preferences()
        elif action_id == "shortcuts":
            self._show_shortcuts()
        elif action_id == "documentation":
            self._open_documentation()
        elif action_id == "report_issue":
            self._report_issue()
        else:
            self.log(f"Action not implemented: {action_id}")

    def _export_data(self) -> None:
        project_file = self._workspace_manager.current_project_file
        if project_file is None:
            QMessageBox.warning(self, "Export Project Inventory", "Open a project first.")
            return
        output, selected_filter = QFileDialog.getSaveFileName(
            self, "Export Project Inventory", str(project_file.with_name(project_file.stem + "_inventory.csv")),
            "CSV (*.csv);;JSON (*.json)",
        )
        if not output:
            return
        import csv, json, sqlite3
        output_path = Path(output)
        as_json = "JSON" in selected_filter or output_path.suffix.lower() == ".json"
        output_path = output_path.with_suffix(".json" if as_json else ".csv")
        task_id = "project:export-inventory"
        self.begin_busy_task(task_id, "Exporting Project Inventory", "Reading registered files and checksums")
        try:
            conn = sqlite3.connect(str(project_file)); conn.row_factory = sqlite3.Row
            rows = [dict(row) for row in conn.execute(
                "SELECT file_uuid,module,file_role,original_name,display_name,absolute_path,relative_path,"
                "extension,mime_type,size_bytes,sha256,status,imported_at FROM project_files ORDER BY module, original_name"
            ).fetchall()]; conn.close()
            self.update_busy_task(task_id, 65, f"Writing {len(rows):,} inventory records")
            if as_json:
                output_path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
            else:
                fields = list(rows[0].keys()) if rows else ["file_uuid","module","file_role","original_name","relative_path","size_bytes","sha256","status"]
                with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
            self.update_busy_task(task_id, 100, "Project inventory exported")
            QMessageBox.information(self, "Export Project Inventory", f"Saved:\n{output_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Project Inventory", str(exc))
        finally:
            self.end_busy_task(task_id)

    def _show_project_properties(self) -> None:
        if not self._current_project_path:
            QMessageBox.information(self, "Project Properties", "No project is currently open.")
            return
        from ui.dialogs.project_properties_dialog import ProjectPropertiesDialog
        ProjectPropertiesDialog(
            self._current_project_name or self._current_project_path.name,
            Path(self._current_project_path),
            self._workspace_manager.current_project_file,
            self,
        ).exec()

    def _refresh_project(self) -> None:
        if self._current_project_path:
            task_id = "project:refresh"
            self.begin_busy_task(task_id, "Refreshing Project", "Reloading Project Explorer contents")
            try:
                self.log("Refreshing project...")
                self.project_explorer.clear()
                self.update_busy_task(task_id, 55, "Reading project folders and files")
                self.project_explorer.add_project(str(self._current_project_path))
                self.update_busy_task(task_id, 100, "Project refresh complete")
            finally:
                self.end_busy_task(task_id)
            QMessageBox.information(self, "Refresh", "Project refreshed successfully.")
        else:
            QMessageBox.warning(self, "Refresh", "No project is currently open.")

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        copy_action = menu.addAction("Copy")
        cut_action = menu.addAction("Cut")
        paste_action = menu.addAction("Paste")
        menu.addSeparator()
        select_all_action = menu.addAction("Select All")
        menu.addSeparator()
        details_action = menu.addAction("Details…")
        chosen = menu.exec(event.globalPos())
        if chosen is copy_action:
            self._copy_selection()
        elif chosen is cut_action:
            self._cut_selection()
        elif chosen is paste_action:
            self._paste_selection()
        elif chosen is select_all_action:
            self._select_all()
        elif chosen is details_action:
            current = self.tab_widget.currentWidget()
            module_id = current.property("module_id") if current is not None else self._active_module
            self._show_feature_details(str(module_id or "workspace"))
        event.accept()

    def _select_all(self) -> None:
        focus = QApplication.focusWidget()
        method = getattr(focus, "selectAll", None) if focus is not None else None
        if callable(method):
            method()
            return
        document = self.tab_widget.currentWidget() if hasattr(self, "tab_widget") else None
        for name in ("select_all", "selectAll"):
            method = getattr(document, name, None) if document is not None else None
            if callable(method):
                method()
                return
        self.status_bar.showMessage("The active view has no selectable content", 2500)

    def _copy_selection(self) -> None:
        focus = QApplication.focusWidget()
        if focus is not None:
            copy_method = getattr(focus, "copy", None)
            if callable(copy_method):
                copy_method()
                self.log("Copied selection to clipboard")
                return
            selected_text = getattr(focus, "selectedText", None)
            if callable(selected_text):
                text = str(selected_text() or "")
                if text:
                    QApplication.clipboard().setText(text)
                    self.log("Copied selection to clipboard")
                    return
            selection_model = getattr(focus, "selectionModel", None)
            model = getattr(focus, "model", None)
            if callable(selection_model) and callable(model):
                selection = selection_model()
                indexes = selection.selectedIndexes() if selection is not None else []
                if indexes:
                    rows: dict[int, list[tuple[int, str]]] = {}
                    data_model = model()
                    for index in indexes:
                        rows.setdefault(index.row(), []).append((index.column(), str(data_model.data(index) or "")))
                    lines = [
                        "\t".join(value for _, value in sorted(cells))
                        for _, cells in sorted(rows.items())
                    ]
                    QApplication.clipboard().setText("\n".join(lines))
                    self.log("Copied table selection to clipboard")
                    return
        document = self.tab_widget.currentWidget() if hasattr(self, "tab_widget") else None
        for name in ("copy_selection", "copy_current", "copy"):
            method = getattr(document, name, None) if document is not None else None
            if callable(method):
                method()
                self.log("Copied selection to clipboard")
                return
        self.status_bar.showMessage("Nothing selectable to copy", 2500)

    def _paste_selection(self) -> None:
        focus = QApplication.focusWidget()
        paste_method = getattr(focus, "paste", None) if focus is not None else None
        if callable(paste_method):
            paste_method()
            self.log("Pasted clipboard content")
            return
        document = self.tab_widget.currentWidget() if hasattr(self, "tab_widget") else None
        for name in ("paste_selection", "paste"):
            method = getattr(document, name, None) if document is not None else None
            if callable(method):
                method()
                self.log("Pasted clipboard content")
                return
        self.status_bar.showMessage("The active view does not accept pasted content", 2500)

    def _cut_selection(self) -> None:
        focus = QApplication.focusWidget()
        cut_method = getattr(focus, "cut", None) if focus is not None else None
        if callable(cut_method):
            cut_method()
            self.log("Cut selection to clipboard")
            return
        document = self.tab_widget.currentWidget() if hasattr(self, "tab_widget") else None
        for name in ("cut_selection", "cut"):
            method = getattr(document, name, None) if document is not None else None
            if callable(method):
                method()
                self.log("Cut selection to clipboard")
                return
        self.status_bar.showMessage("The active selection is read-only and cannot be cut", 2500)

    def _open_segy_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open SEG-Y File", str(Path.home()),
            "SEG-Y Files (*.sgy *.segy);;All Files (*.*)",
        )
        if not file_path:
            return
        resolved = str(Path(file_path).resolve())
        task_id = f"file-open:segy:{Path(resolved).name}"
        self.begin_busy_task(task_id, "Opening SEG-Y File", f"Preparing {Path(resolved).name}", 5)
        try:
            for index in range(self.tab_widget.count()):
                widget = self.tab_widget.widget(index)
                if widget is not None and widget.property("segy_viewer_file_path") == resolved:
                    self.update_busy_task(task_id, 45, "Activating existing SEG-Y viewer")
                    self.tab_widget.setCurrentIndex(index)
                    self._set_active_module("segy_viewer")
                    qc_view = self._get_segy_qc_view()
                    if qc_view is not None and getattr(qc_view, "current_file_path", None) != Path(resolved):
                        self.update_busy_task(task_id, 75, "Synchronizing SEG-Y QC workspace")
                        qc_view.set_file_path(resolved)
                    self.update_busy_task(task_id, 100, "SEG-Y viewer is ready")
                    return
            from modules.seismic.segy_viewer.segy_viewer_widget import SegyViewerWidget
            self.update_busy_task(task_id, 35, "Building SEG-Y trace viewer")
            QApplication.processEvents()
            viewer = SegyViewerWidget(resolved, self)
            viewer.setProperty("segy_viewer_file_path", resolved)
            self.update_busy_task(task_id, 60, "Opening SEG-Y document tab")
            index = self._add_document_tab(viewer, f"SEG-Y: {Path(resolved).name}", icon=get_icon("seg-y", color="#FFFFFF", size=15))
            self.tab_widget.setCurrentIndex(index)
            self._set_active_module("segy_viewer")
            # Keep the QC workspace synchronized so Run SEG-Y QC works immediately.
            qc_view = self._get_segy_qc_view()
            if qc_view is not None:
                self.update_busy_task(task_id, 82, "Synchronizing SEG-Y QC workspace")
                qc_view.set_file_path(resolved)
            self.update_busy_task(task_id, 100, "SEG-Y file is open")
            self.log(f"Opened SEG-Y viewer: {resolved}")
        except Exception as exc:
            QMessageBox.critical(self, "SEG-Y Open Error", str(exc))
        finally:
            if self.has_busy_task(task_id):
                self._finish_busy_task_after_workspace_paint(
                    task_id,
                    "segy_viewer",
                    self.tab_widget.currentWidget() if hasattr(self, "tab_widget") else None,
                    ready_message="SEG-Y file is ready",
                )

    def _open_seg2_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open SEG-2 File", str(Path.home()),
            "SEG-2 Files (*.seg2);;All Files (*.*)"
        )
        if file_path:
            self.log(f"Opening SEG-2 file: {file_path}")
            QMessageBox.information(self, "SEG-2", f"SEG-2 file loaded: {Path(file_path).name}")

    def _open_segb_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open SEG-B File", str(Path.home()),
            "SEG-B Files (*.segb);;All Files (*.*)"
        )
        if file_path:
            self.log(f"Opening SEG-B file: {file_path}")
            QMessageBox.information(self, "SEG-B", f"SEG-B file loaded: {Path(file_path).name}")

    def _open_ukooa_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open UKOOA File", str(Path.home()),
            "UKOOA Files (*.ukooa *.p190);;All Files (*.*)"
        )
        if file_path:
            self.log(f"Opening UKOOA file: {file_path}")
            QMessageBox.information(self, "UKOOA", f"UKOOA file loaded: {Path(file_path).name}")

    def _open_navigation_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Navigation File", str(Path.home()),
            "Navigation Files (*.nav *.txt);;All Files (*.*)"
        )
        if file_path:
            self.log(f"Opening navigation file: {file_path}")
            QMessageBox.information(self, "Navigation", f"Navigation file loaded: {Path(file_path).name}")

    def _validate_seismic_data(self) -> None:
        # Validation is the SEG-Y/SEG-D QC workflow; do not maintain a second,
        # misleading placeholder validation implementation.
        if self._active_segd_viewer() is not None:
            self._apply_to_active_segd("run_qc", "full")
        else:
            self._run_segy_qc()

    def _process_seismic_data(self) -> None:
        viewer = self._active_visualization()
        if viewer is None:
            QMessageBox.information(self, "Seismic Processing", "Open data in the 2D/3D viewer first. Processing/display controls are available in that module ribbon.")
            return
        self._set_active_module("visualization")

    def _save_layout(self) -> None:
        try:
            self._layout_store.save_layout(bytes(self.saveState()))
            self._layout_store.save_tabs(self._workspace_manager.get_tab_contexts())
            self.status_bar.showMessage("Window and dock layout saved.", 3500)
        except Exception as exc:
            QMessageBox.critical(self, "Save Layout", str(exc))

    def _load_layout(self) -> None:
        try:
            layout = self._layout_store.load_layout()
            if not layout:
                QMessageBox.information(self, "Load Layout", "No saved layout is available yet.")
                return
            if not self.restoreState(layout):
                raise RuntimeError("The saved layout is incompatible with this application version")
            self.status_bar.showMessage("Saved layout restored.", 3500)
        except Exception as exc:
            QMessageBox.critical(self, "Load Layout", str(exc))

    def _view_headers(self) -> None:
        self._apply_to_active_segd("toggle_headers")

    def _zoom_to_fit(self) -> None:
        viewer = self._active_visualization()
        if viewer is not None:
            self._apply_to_active_visualization("zoom_to_fit")
        elif self._active_segd_viewer() is not None:
            self._apply_to_active_segd("zoom_to_fit")
        else:
            self.status_bar.showMessage("Open a seismic view before using Fit.", 3000)

    def _zoom_in(self) -> None:
        self.status_bar.showMessage("Use the active viewer mouse-wheel/axis zoom controls.", 3000)

    def _zoom_out(self) -> None:
        self.status_bar.showMessage("Use the active viewer mouse-wheel/axis zoom controls.", 3000)

    def _zoom_100(self) -> None:
        self._zoom_to_fit()

    def _open_data_inspector(self, initial_tab: str) -> None:
        path = self._selected_project_path
        if path is None or not path.is_file():
            QMessageBox.information(self, initial_tab, "Select a tabular project file first.")
            return
        if path.suffix.lower() not in {".csv", ".tsv", ".txt", ".dat", ".xyz", ".xlsx", ".xlsm"}:
            QMessageBox.information(self, initial_tab, "The generic Data Inspector supports tabular files. Use the module-specific analysis tools for this file type.")
            return
        task_id = f"data-inspector:{path}"
        self.begin_busy_task(task_id, f"Opening {initial_tab}", f"Reading {path.name}")
        QApplication.processEvents()
        try:
            from ui.dialogs.data_inspector_dialog import DataInspectorDialog
            self.update_busy_task(task_id, 40, "Parsing tabular data and numeric columns")
            QApplication.processEvents()
            dialog = DataInspectorDialog(path, self, initial_tab=initial_tab)
            self.update_busy_task(task_id, 100, "Inspector ready")
            self.finish_busy_task(task_id)
            dialog.exec()
        except Exception as exc:
            self.finish_busy_task(task_id)
            QMessageBox.critical(self, "Data Inspector", str(exc))

    def _open_cross_plot(self) -> None:
        self._open_data_inspector("Cross Plot")

    def _open_map_view(self) -> None:
        if self._gravity_dashboard and getattr(self._gravity_dashboard, "observations", None) is not None:
            self._gravity_dashboard.show_map(); return
        if self._magnetic_dashboard and getattr(self._magnetic_dashboard, "rover", None) is not None:
            self._magnetic_dashboard.show_map(); return
        QMessageBox.information(self, "Map View", "Open a Magnetic or Gravity dataset to use the geophysical map view.")

    def _open_histogram(self) -> None:
        self._open_data_inspector("Histogram")

    def _open_statistics(self) -> None:
        self._open_data_inspector("Statistics")

    def _run_batch_qc(self) -> None:
        QMessageBox.information(self, "Batch QC", "Batch QC is intentionally not exposed in the ribbon until a validated multi-file scheduler is configured. Use module QC on each managed dataset.")

    def _run_batch_export(self) -> None:
        self._export_data()

    def _run_batch_process(self) -> None:
        QMessageBox.information(self, "Batch Process", "Batch processing is intentionally disabled until a reproducible processing recipe is selected for each dataset.")

    def _open_preferences(self) -> None:
        from ui.dialogs.preferences_dialog import PreferencesDialog
        if self._settings_store is None:
            QMessageBox.warning(self, "Preferences", "Application settings storage is unavailable in this session.")
            return
        try:
            dialog = PreferencesDialog(self._settings_store, self)
            if dialog.exec():
                self._configure_autosave()
        except Exception as exc:
            QMessageBox.critical(self, "Preferences", str(exc))

    def _configure_autosave(self) -> None:
        self._autosave_timer.stop()
        if self._settings_store is None:
            return
        try:
            minutes = max(0, int(self._settings_store.get("autosave_minutes", 10) or 0))
        except Exception:
            minutes = 10
        if minutes > 0:
            self._autosave_timer.start(minutes * 60 * 1000)

    def _autosave_project(self) -> None:
        if self._workspace_manager.current_project_file is None or not self._workspace_manager.is_dirty:
            return
        try:
            state_path = self._workspace_manager.save_project()
            self.status_bar.showMessage(f"Autosaved project state — {state_path.name}", 2500)
        except Exception as exc:
            self.log(f"Autosave failed: {exc}")

    def _show_shortcuts(self) -> None:
        shortcuts_text = (
            "Ctrl+N: New Project\n"
            "Ctrl+O: Open Project\n"
            "Ctrl+S: Save Project\n"
            "Ctrl+W: Close Active Tab\n"
            "Ctrl+Tab: Next Tab\n"
            "Ctrl+Shift+Tab: Previous Tab\n"
            "Ctrl+Q: Exit Application"
        )
        QMessageBox.information(self, "Keyboard Shortcuts", shortcuts_text)

    def _open_documentation(self) -> None:
        from ui.feature_registry import get_feature_detail
        from ui.dialogs.feature_details_dialog import FeatureDetailsDialog
        detail = get_feature_detail(self._active_module or "workspace")
        FeatureDetailsDialog(detail, self).exec()

    def _report_issue(self) -> None:
        from ui.dialogs.issue_report_dialog import IssueReportDialog
        IssueReportDialog(self).exec()

    def _active_visualization(self):
        widget = self.tab_widget.currentWidget()
        if widget is not None and widget.property("module_id") == "visualization":
            return widget
        return None

    def _apply_to_active_visualization(self, method_name: str, *args) -> None:
        viewer = self._active_visualization()
        if viewer is None:
            QMessageBox.information(self, "2D/3D Seismic", "Open a SEG-Y or SEG-D file in the 2D/3D viewer first.")
            return
        method = getattr(viewer, method_name, None)
        if method is None:
            QMessageBox.warning(self, "2D/3D Seismic", f"The active viewer does not support: {method_name}")
            return
        try:
            method(*args)
        except Exception as exc:
            QMessageBox.critical(self, "2D/3D Seismic Error", str(exc))

    def _open_converter_page(self):
        page = self._converter_page
        if page is None or not is_qobject_valid(page):
            from ui.converter_page import SegyToSegdConverterPage
            page = SegyToSegdConverterPage(self)
            self._converter_page = page
            page.destroyed.connect(lambda *_: setattr(self, "_converter_page", None))
            index = self._add_document_tab(
                page,
                "SEG-Y → SEG-D Converter",
                icon=get_icon("transform-move", color="#5B4FD6", size=16),
            )
        else:
            index = self.tab_widget.indexOf(page)
            if index < 0:
                index = self._add_document_tab(page, "SEG-Y → SEG-D Converter")
        self.tab_widget.setCurrentIndex(index)
        self._set_active_module("converter")
        return page

    def _open_segd_scanner_dashboard(self):
        dashboard = self._segd_scanner_dashboard
        if dashboard is None or not is_qobject_valid(dashboard):
            try:
                from modules.seismic.ui.segd_scanner_dashboard import SegdScannerDashboard
                dashboard = SegdScannerDashboard(self)
                self._segd_scanner_dashboard = dashboard
                dashboard.destroyed.connect(lambda *_: setattr(self, "_segd_scanner_dashboard", None))
                index = self._add_document_tab(
                    dashboard,
                    "SEG-D Header Scanner",
                    icon=get_icon("view-list-details", color="#0E7490", size=16),
                    closable=True,
                )
            except Exception as exc:
                QMessageBox.critical(self, "SEG-D Header Scanner", f"Unable to open the scanner:\n{exc}")
                return None
        else:
            index = self.tab_widget.indexOf(dashboard)
            if index < 0:
                index = self._add_document_tab(dashboard, "SEG-D Header Scanner", closable=True)
        self.tab_widget.setCurrentIndex(index)
        self._set_active_module("segd_scanner")
        dashboard.show(); dashboard.raise_(); dashboard.setFocus(Qt.OtherFocusReason)
        return dashboard

    def _open_receiver_qc_dashboard(self):
        dashboard = self._receiver_qc_dashboard
        if dashboard is None or not is_qobject_valid(dashboard):
            try:
                from modules.receiver.ui import ReceiverQcDashboard
                dashboard = ReceiverQcDashboard(self)
                self._receiver_qc_dashboard = dashboard
                dashboard.destroyed.connect(lambda *_: setattr(self, "_receiver_qc_dashboard", None))
                index = self._add_document_tab(
                    dashboard,
                    "Receiver SMT QC",
                    icon=get_icon("dialog-ok-apply", color="#0E7490", size=16),
                    closable=True,
                )
            except Exception as exc:
                QMessageBox.critical(self, "Receiver QC", f"Unable to open Receiver QC:\n{exc}")
                return None
        else:
            index = self.tab_widget.indexOf(dashboard)
            if index < 0:
                index = self._add_document_tab(dashboard, "Receiver SMT QC", closable=True)
        self.tab_widget.setCurrentIndex(index)
        self._set_active_module("receiver_qc")
        dashboard.show(); dashboard.raise_(); dashboard.setFocus(Qt.OtherFocusReason)
        return dashboard

    def _open_uphole_dashboard(self):
        dashboard = self._uphole_dashboard
        if dashboard is None or not is_qobject_valid(dashboard):
            try:
                from modules.uphole.ui import UpholeDashboard
                dashboard = UpholeDashboard(self)
                self._uphole_dashboard = dashboard
                dashboard.destroyed.connect(lambda *_: setattr(self, "_uphole_dashboard", None))
                index = self._add_document_tab(
                    dashboard,
                    "Uphole Interpretation",
                    icon=get_icon("seg-2", color="#0E7490", size=16),
                    closable=True,
                )
            except Exception as exc:
                QMessageBox.critical(self, "Uphole", f"Unable to open Uphole module:\n{exc}")
                return None
        else:
            index = self.tab_widget.indexOf(dashboard)
            if index < 0:
                index = self._add_document_tab(dashboard, "Uphole Interpretation", closable=True)
        self.tab_widget.setCurrentIndex(index)
        self._set_active_module("uphole")
        dashboard.show(); dashboard.raise_(); dashboard.setFocus(Qt.OtherFocusReason)
        return dashboard

    def _open_vibroseis_dashboard(self):
        """Open the integrated Vibroseis workspace as a document tab.

        Older builds silently logged constructor errors, so clicking the Vibroseis
        ribbon could appear to do nothing. This version always either opens the
        dashboard or shows the actual load error to the user.
        """
        dashboard = self._vibroseis_dashboard
        if dashboard is None or not is_qobject_valid(dashboard):
            try:
                from modules.vibroseis.ui import VibroseisDashboard
                dashboard = VibroseisDashboard(self)
            except Exception as exc:
                self.log(f"Vibroseis dashboard failed to open: {exc}")
                QMessageBox.critical(
                    self,
                    "Vibroseis Dashboard",
                    "Unable to open the Vibroseis Source QC dashboard.\n\n"
                    f"Reason: {exc}",
                )
                return None
            self._vibroseis_dashboard = dashboard
            dashboard.destroyed.connect(lambda *_: setattr(self, "_vibroseis_dashboard", None))
            index = self._add_document_tab(
                dashboard,
                "Vibroseis Source QC",
                icon=get_icon("media-playback-start", color="#0E7490", size=16),
                closable=True,
            )
        else:
            index = self.tab_widget.indexOf(dashboard)
            if index < 0:
                index = self._add_document_tab(
                    dashboard,
                    "Vibroseis Source QC",
                    icon=get_icon("media-playback-start", color="#0E7490", size=16),
                    closable=True,
                )
        self.tab_widget.setCurrentIndex(index)
        self._set_active_module("vibroseis")
        dashboard.show()
        dashboard.raise_()
        dashboard.setFocus(Qt.OtherFocusReason)
        return dashboard

    def _open_geodetic_dashboard(self):
        dashboard = self._geodetic_dashboard
        if dashboard is None or not is_qobject_valid(dashboard):
            try:
                from core.data_access.db_engine import DatabaseEngine
                from modules.geodetic.ui import GeodeticDashboard
                dashboard = GeodeticDashboard(self.container.resolve(DatabaseEngine), self)
                self._geodetic_dashboard = dashboard
                dashboard.destroyed.connect(lambda *_: setattr(self, "_geodetic_dashboard", None))
                dashboard.state_changed.connect(self._update_ribbon)
                dashboard.activity_started.connect(
                    lambda title, message: self.begin_busy_task(
                        "geodetic:dashboard", title, message
                    )
                )
                dashboard.activity_progress.connect(
                    lambda value, message: self.update_busy_task(
                        "geodetic:dashboard", value, message
                    )
                )
                dashboard.activity_finished.connect(
                    lambda: (self.end_busy_task("geodetic:dashboard"), self._update_ribbon())
                )
                dashboard.destroyed.connect(
                    lambda *_: self.end_busy_task("geodetic:dashboard")
                )
                index = self._add_document_tab(
                    dashboard,
                    "Geodetic Survey QC",
                    icon=get_icon("map", color="#0B6FA4", size=16),
                    closable=True,
                )
            except Exception as exc:
                QMessageBox.critical(self, "Geodetic", f"Unable to open the Geodetic module:\n{exc}")
                return None
        else:
            index = self.tab_widget.indexOf(dashboard)
            if index < 0:
                index = self._add_document_tab(dashboard, "Geodetic Survey QC", closable=True)
        self.tab_widget.setCurrentIndex(index)
        self._set_active_module("geodetic")
        dashboard.show(); dashboard.raise_(); dashboard.setFocus(Qt.OtherFocusReason)
        return dashboard

    def _apply_to_geodetic(self, method_name: str, *args) -> None:
        dashboard = self._open_geodetic_dashboard()
        if dashboard is None:
            return
        method = getattr(dashboard, method_name, None)
        if method is None:
            QMessageBox.warning(self, "Geodetic", f"The Geodetic module does not support: {method_name}")
            return
        try:
            method(*args)
        except Exception as exc:
            QMessageBox.critical(self, "Geodetic Error", str(exc))
        finally:
            self._update_ribbon()

    def _open_magnetic_dashboard(self):
        dashboard = self._magnetic_dashboard
        if dashboard is None:
            task_id = "magnetic:workspace"
            self.begin_busy_task(
                task_id,
                "Opening Magnetic QC",
                "Initializing magnetic readers, processing tools and dashboard",
            )
            try:
                from core.data_access.db_engine import DatabaseEngine
                from core.infrastructure.job_manager import JobManager
                from modules.magnetic.magnetic_controller import MagneticQcController
                from modules.magnetic.ui.magnetic_dashboard import MagneticDashboard

                self.update_busy_task(task_id, 45, "Creating Magnetic QC controller")
                controller = MagneticQcController(
                    self.container.resolve(DatabaseEngine),
                    self.container.resolve(JobManager),
                    self,
                )
                self.update_busy_task(task_id, 70, "Building Magnetic QC workspace")
                dashboard = MagneticDashboard(controller, self)
                dashboard.destroyed.connect(self._clear_magnetic_dashboard_reference)
                dashboard.dataset_changed.connect(lambda *_: self._update_ribbon())
                dashboard.activity_started.connect(
                    lambda title, message: self.begin_busy_task(
                        "magnetic:dashboard", title, message
                    )
                )
                dashboard.activity_progress.connect(
                    lambda value, message: self.update_busy_task(
                        "magnetic:dashboard", value, message
                    )
                )
                dashboard.activity_finished.connect(
                    lambda: (self.end_busy_task("magnetic:dashboard"), self._update_ribbon())
                )
                dashboard.destroyed.connect(
                    lambda *_: self.end_busy_task("magnetic:dashboard")
                )
                self._magnetic_dashboard = dashboard
                self.update_busy_task(task_id, 100, "Magnetic QC workspace is ready")
            except Exception as exc:
                self.end_busy_task(task_id)
                QMessageBox.critical(self, "Magnetic QC", f"Unable to open the Magnetic QC module:\n{exc}")
                return None
            self.end_busy_task(task_id)
        index = self.tab_widget.indexOf(dashboard)
        if index < 0:
            index = self._add_document_tab(
                dashboard,
                "Magnetic QC",
                icon=get_icon("office-chart-line", size=15),
                closable=True,
            )
        self.tab_widget.setCurrentIndex(index)
        self._set_active_module("magnetic")
        dashboard.show()
        dashboard.raise_()
        dashboard.setFocus(Qt.OtherFocusReason)
        return dashboard

    def _clear_magnetic_dashboard_reference(self, *_args) -> None:
        self._magnetic_dashboard = None
        self._update_ribbon()

    def _apply_to_magnetic(self, method_name: str, *args) -> None:
        dashboard = self._open_magnetic_dashboard()
        if dashboard is None:
            return
        method = getattr(dashboard, method_name, None)
        if method is None:
            QMessageBox.warning(self, "Magnetic QC", f"The Magnetic QC module does not support: {method_name}")
            return
        try:
            method(*args)
        except Exception as exc:
            QMessageBox.critical(self, "Magnetic QC Error", str(exc))
        finally:
            self._update_ribbon()

    def _open_gravity_dashboard(self):
        dashboard = self._gravity_dashboard
        if dashboard is None:
            task_id = "gravity:workspace"
            self.begin_busy_task(task_id, "Opening Gravity QC", "Initializing gravity readers, QC, reductions and visualization tools")
            try:
                from core.data_access.db_engine import DatabaseEngine
                from core.infrastructure.job_manager import JobManager
                from modules.gravity.gravity_controller import GravityQcController
                from modules.gravity.ui.gravity_dashboard import GravityDashboard

                self.update_busy_task(task_id, 40, "Creating Gravity QC controller")
                controller = GravityQcController(
                    self.container.resolve(DatabaseEngine),
                    self.container.resolve(JobManager),
                    self,
                )
                self.update_busy_task(task_id, 70, "Building Gravity QC workspace")
                dashboard = GravityDashboard(controller, self)
                dashboard.destroyed.connect(self._clear_gravity_dashboard_reference)
                dashboard.activity_started.connect(lambda title, message: self.begin_busy_task("gravity:dashboard", title, message))
                dashboard.activity_progress.connect(lambda value, message: self.update_busy_task("gravity:dashboard", value, message))
                dashboard.activity_finished.connect(lambda: (self.end_busy_task("gravity:dashboard"), self._update_ribbon()))
                dashboard.state_changed.connect(self._update_ribbon)
                dashboard.destroyed.connect(lambda *_: self.end_busy_task("gravity:dashboard"))
                self._gravity_dashboard = dashboard
                self.update_busy_task(task_id, 100, "Gravity QC workspace is ready")
            except Exception as exc:
                QMessageBox.critical(self, "Gravity QC", f"Unable to open the Gravity QC module:\n{exc}")
                return None
            finally:
                self.end_busy_task(task_id)
        index = self.tab_widget.indexOf(dashboard)
        if index < 0:
            index = self._add_document_tab(
                dashboard,
                "Gravity QC",
                icon=get_icon("view-statistics", size=15),
                closable=True,
            )
        self.tab_widget.setCurrentIndex(index)
        self._set_active_module("gravity")
        dashboard.show()
        dashboard.raise_()
        dashboard.setFocus(Qt.OtherFocusReason)
        return dashboard

    def _clear_gravity_dashboard_reference(self, *_args) -> None:
        self._gravity_dashboard = None
        self._update_ribbon()

    def _apply_to_gravity(self, method_name: str, *args) -> None:
        dashboard = self._open_gravity_dashboard()
        if dashboard is None:
            return
        method = getattr(dashboard, method_name, None)
        if method is None:
            QMessageBox.warning(self, "Gravity QC", f"The Gravity QC module does not support: {method_name}")
            return
        try:
            method(*args)
        except Exception as exc:
            QMessageBox.critical(self, "Gravity QC Error", str(exc))
        finally:
            self._update_ribbon()

    def _open_electrical_dashboard(self):
        dashboard = self._electrical_dashboard
        if dashboard is None:
            task_id = "electrical:workspace"
            self.begin_busy_task(
                task_id,
                "Opening Electrical QC",
                "Initializing electrical readers, QC engine, processing and visualization tools",
            )
            try:
                from core.data_access.db_engine import DatabaseEngine
                from modules.electrical.ui.electrical_dashboard import ElectricalDashboard

                self.update_busy_task(task_id, 45, "Creating Electrical Methods workspace")
                dashboard = ElectricalDashboard(self.container.resolve(DatabaseEngine), self)
                dashboard.destroyed.connect(self._clear_electrical_dashboard_reference)
                dashboard.activity_started.connect(
                    lambda title, message: self.begin_busy_task(
                        "electrical:dashboard", title, message
                    )
                )
                dashboard.activity_progress.connect(
                    lambda value, message: self.update_busy_task(
                        "electrical:dashboard", value, message
                    )
                )
                dashboard.activity_finished.connect(
                    lambda: (self.end_busy_task("electrical:dashboard"), self._update_ribbon())
                )
                dashboard.destroyed.connect(
                    lambda *_: self.end_busy_task("electrical:dashboard")
                )
                self._electrical_dashboard = dashboard
                self.update_busy_task(task_id, 100, "Electrical QC workspace is ready")
            except Exception as exc:
                self.end_busy_task(task_id)
                QMessageBox.critical(self, "Electrical QC", f"Unable to open the Electrical QC module:\n{exc}")
                return None
            self.end_busy_task(task_id)
        index = self.tab_widget.indexOf(dashboard)
        if index < 0:
            index = self._add_document_tab(
                dashboard,
                "Electrical QC",
                icon=get_icon("electrical", size=15),
                closable=True,
            )
        self.tab_widget.setCurrentIndex(index)
        self._set_active_module("electrical")
        dashboard.show()
        dashboard.raise_()
        dashboard.setFocus(Qt.OtherFocusReason)
        return dashboard

    def _clear_electrical_dashboard_reference(self, *_args) -> None:
        self._electrical_dashboard = None
        self._update_ribbon()

    def _apply_to_electrical(self, method_name: str, *args) -> None:
        dashboard = self._open_electrical_dashboard()
        if dashboard is None:
            return
        method = getattr(dashboard, method_name, None)
        if method is None:
            QMessageBox.warning(self, "Electrical QC", f"The Electrical QC module does not support: {method_name}")
            return
        try:
            method(*args)
        except Exception as exc:
            QMessageBox.critical(self, "Electrical QC Error", str(exc))
        finally:
            self._update_ribbon()

    def _open_qc_history_page(self):
        task_id = "qc-history:refresh"
        self.begin_busy_task(task_id, "Loading QC History", "Reading saved QC runs and findings")
        try:
            page = self._qc_history_page
            if page is None or not self._is_qobject_alive(page):
                try:
                    from core.data_access.db_engine import DatabaseEngine
                    from ui.qc_history_page import QcHistoryPage

                    self.update_busy_task(task_id, 25, "Initializing QC history workspace")
                    page = QcHistoryPage(self.container.resolve(DatabaseEngine), self)
                    page.file_open_requested.connect(self.open_imported_file)
                    page.activity_started.connect(
                        lambda title, message: self.begin_busy_task(
                            "qc-history:refresh", title, message
                        )
                    )
                    page.activity_progress.connect(
                        lambda value, message: self.update_busy_task(
                            "qc-history:refresh", value, message
                        )
                    )
                    page.activity_finished.connect(
                        lambda: self.end_busy_task("qc-history:refresh")
                    )
                    page.destroyed.connect(lambda *_: setattr(self, "_qc_history_page", None))
                    self._qc_history_page = page
                except Exception as exc:
                    QMessageBox.critical(self, "QC History", f"Unable to open QC Run History:\n{exc}")
                    return None
            try:
                self.update_busy_task(task_id, 65, "Refreshing run, stage and findings tables")
                page.refresh()
            except Exception as exc:
                self.log(f"QC history refresh failed: {exc}")
            index = self.tab_widget.indexOf(page)
            if index < 0:
                index = self._add_document_tab(
                    page, "QC Run History", icon=get_icon("view-history", size=15), closable=True
                )
            self.tab_widget.setCurrentIndex(index)
            self._set_active_module("home")
            self.update_busy_task(task_id, 100, "QC history is ready")
            return page
        finally:
            self.end_busy_task(task_id)

    def _open_home_module(self, module_id: str) -> None:
        handlers = {
            "segd": self._open_segd_viewer,
            "segy_viewer": self._open_segy_file,
            "converter": self._open_converter_page,
            "vibroseis": self._open_vibroseis_dashboard,
            "segd_scanner": self._open_segd_scanner_dashboard,
            "receiver_qc": self._open_receiver_qc_dashboard,
            "uphole": self._open_uphole_dashboard,
            "visualization": self._open_visualization,
            "magnetic": self._open_magnetic_dashboard,
            "gravity": self._open_gravity_dashboard,
            "electrical": self._open_electrical_dashboard,
        }
        handler = handlers.get(module_id)
        if handler is not None:
            handler()

    def _update_feature_inspector(self, action_id: str) -> None:
        from ui.feature_registry import get_feature_detail
        from ui.feature_inspector import FeatureInspector
        if not hasattr(self, "_feature_inspector_dock") or self._feature_inspector_dock is None:
            dock = QDockWidget("Feature Guide", self)
            dock.setObjectName("featureGuideDock")
            panel = FeatureInspector(dock)
            dock.setWidget(panel)
            dock.setMinimumWidth(320)
            dock.resize(360, 620)
            self.addDockWidget(Qt.RightDockWidgetArea, dock)
            self._feature_inspector_dock = dock
            self._feature_inspector_panel = panel
        self._feature_inspector_panel.set_detail(get_feature_detail(action_id))
        self._feature_inspector_dock.show()
        self._feature_inspector_dock.raise_()

    def _active_segy_viewer(self):
        widget = self.tab_widget.currentWidget() if hasattr(self, "tab_widget") else None
        return widget if widget is not None and widget.property("module_id") == "segy_viewer" else None

    def _active_segd_viewer(self):
        widget = self.tab_widget.currentWidget()
        if widget is not None and widget.property("module_id") == "segd":
            return widget
        return None

    def _apply_to_active_segd(self, method_name: str, *args) -> None:
        viewer = self._active_segd_viewer()
        if viewer is None:
            QMessageBox.information(self, "SEG-D", "Open a SEG-D file first from the SEG-D ribbon.")
            return
        method = getattr(viewer, method_name, None)
        if method is None:
            QMessageBox.warning(self, "SEG-D", f"The active SEG-D viewer does not support: {method_name}")
            return
        try:
            method(*args)
        except Exception as e:
            QMessageBox.critical(self, "SEG-D Error", str(e))

    def _create_central(self):
        central = QWidget()
        central.setObjectName("centralWorkspaceHost")
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.central_stack = QStackedWidget(central)
        self.central_stack.setObjectName("centralWorkspaceStack")

        self.empty_workspace = EmptyWorkspace(self.central_stack)
        self.central_stack.addWidget(self.empty_workspace)

        self.tab_widget = QTabWidget(self.central_stack)
        self.tab_widget.setObjectName("documentTabs")
        self.tab_widget.tabBar().setObjectName("documentTabBar")
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self._close_tab_by_index)
        self.tab_widget.tabBar().setExpanding(False)
        self.tab_widget.tabBar().setUsesScrollButtons(True)
        self.tab_widget.tabBar().setElideMode(Qt.ElideRight)
        self.tab_widget.currentChanged.connect(self._on_current_tab_changed)
        self.central_stack.addWidget(self.tab_widget)

        # Start exactly as a workstation shell: explorer + empty canvas, no Home document.
        self.home_page = None
        self.central_stack.setCurrentWidget(self.empty_workspace)
        layout.addWidget(self.central_stack)
        self.setCentralWidget(central)

    def _add_document_tab(
        self,
        widget: QWidget,
        title: str,
        icon: QIcon | None = None,
        closable: bool = True,
    ) -> int:
        if icon is not None:
            index = self.tab_widget.addTab(widget, icon, title)
        else:
            index = self.tab_widget.addTab(widget, title)

        if not closable:
            self.tab_widget.tabBar().setTabButton(
                index,
                QTabBar.RightSide,
                None
            )

        self._sync_document_workspace()
        return index

    def _sync_document_workspace(self) -> None:
        if not hasattr(self, "central_stack"):
            return
        if self.tab_widget.count() > 0:
            self.central_stack.setCurrentWidget(self.tab_widget)
        else:
            self.central_stack.setCurrentWidget(self.empty_workspace)


    def _install_dock_title_bar(self, dock: QDockWidget) -> None:
        dock.setTitleBarWidget(DockTitleBar(dock, dock.windowTitle(), dock))

    def _create_docks(self):
        self.project_dock = QDockWidget('Explorer')
        self.project_dock.setObjectName("projectDock")
        self.project_explorer = ProjectExplorer()
        self.project_explorer.file_selected.connect(self._on_project_item_selected)
        self.project_explorer.run_qc_requested.connect(lambda p: self.log(f'Run QC requested: {p}'))
        self.project_explorer.import_requested.connect(self._import_file)
        self.project_dock.setWidget(self.project_explorer)
        self.project_dock.setMinimumWidth(210)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.project_dock)
        self._install_dock_title_bar(self.project_dock)
        self.resizeDocks([self.project_dock], [275], Qt.Horizontal)
        
        self.properties_dock = QDockWidget('Properties')
        self.properties_dock.setObjectName("propertiesDock")
        try:
            from ui.docks.properties_panel import PropertiesPanel
            self.properties_panel = PropertiesPanel()
            self.properties_panel.run_qc.connect(lambda p: self.log(f'Run QC: {p}'))
            self.properties_panel.generate_report.connect(lambda p, t: self.log(f'Generate {t}: {p}'))
            self.properties_panel.view_in_explorer.connect(lambda p: self.log(f'Open Explorer: {p}'))
            self.properties_panel.delete_file.connect(lambda p: self.log(f'Delete: {p}'))
            self.properties_dock.setWidget(self.properties_panel)
        except ImportError:
            self.properties_dock.setWidget(QLabel("Properties panel not available"))
        self.addDockWidget(Qt.RightDockWidgetArea, self.properties_dock)
        self._install_dock_title_bar(self.properties_dock)
        self.properties_dock.setMinimumWidth(210)
        self.resizeDocks([self.properties_dock], [300], Qt.Horizontal)
        
        self.output_dock = QDockWidget('Output Console')
        self.output_dock.setObjectName("outputDock")
        try:
            from ui.docks.output_console import OutputConsole
            self.output_console = OutputConsole()
            self.output_dock.setWidget(self.output_console)
        except ImportError:
            self.output_console = QPlainTextEdit()
            self.output_console.setReadOnly(True)
            self.output_dock.setWidget(self.output_console)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.output_dock)
        self._install_dock_title_bar(self.output_dock)
        self.output_dock.setMinimumHeight(70)
        self.resizeDocks([self.output_dock], [155], Qt.Vertical)

        # Petrel-style startup shell: keep only the left Explorer visible initially.
        self.properties_dock.hide()
        self.output_dock.hide()

    def _create_status_bar(self):
        self.status_bar = QStatusBar()
        self.status_bar.setFixedHeight(28)
        self.setStatusBar(self.status_bar)
        
        self.project_label = QLabel('No Project')
        self.status_bar.addWidget(self.project_label)
        
        self.status_bar.addWidget(QLabel('Job Progress:'))
        self.job_progress_bar = QProgressBar()
        self.job_progress_bar.setFixedWidth(100)
        self.job_progress_bar.setRange(0, 100)
        self.job_progress_bar.setValue(0)
        self.status_bar.addWidget(self.job_progress_bar)

        self.fullscreen_view_btn = QPushButton('Full Screen View  F11')
        self.fullscreen_view_btn.setObjectName('statusFullScreenButton')
        self.fullscreen_view_btn.setToolTip('Show the active dashboard in full screen (F11)')
        self.fullscreen_view_btn.setCursor(Qt.PointingHandCursor)
        self.fullscreen_view_btn.clicked.connect(self.enter_dashboard_fullscreen)
        self.status_bar.addPermanentWidget(self.fullscreen_view_btn)

        self.normal_screen_btn = QPushButton('Back to Normal  F5')
        self.normal_screen_btn.setObjectName('statusNormalScreenButton')
        self.normal_screen_btn.setToolTip('Return from full screen to the normal dashboard layout (F5)')
        self.normal_screen_btn.setCursor(Qt.PointingHandCursor)
        self.normal_screen_btn.clicked.connect(self.exit_dashboard_fullscreen)
        self.normal_screen_btn.setEnabled(False)
        self.status_bar.addPermanentWidget(self.normal_screen_btn)

        self._sync_fullscreen_controls()
        
        self.coord_label = QLabel('X: 0  Y: 0')
        self.status_bar.addPermanentWidget(self.coord_label)
        
        self.zoom_label = QLabel('Zoom: 1.0x')
        self.status_bar.addPermanentWidget(self.zoom_label)
        
        self.memory_label = QLabel('Mem: 0 MB')
        self.status_bar.addPermanentWidget(self.memory_label)
        
        timer = QTimer(self)
        timer.timeout.connect(self._update_metrics)
        timer.start(1000)

    def _update_metrics(self):
        try:
            import psutil
            mem = psutil.Process().memory_info().rss / 1024 / 1024
            self.memory_label.setText(f'Mem: {int(mem)} MB')
        except Exception:
            pass

    def update_job_progress(self, job_id: int, progress: float) -> None:
        normalized_progress = float(progress)
        if 0.0 <= normalized_progress <= 1.0:
            normalized_progress *= 100.0
        value = max(0, min(100, round(normalized_progress)))
        self.job_progress_bar.setValue(value)
        self.status_bar.showMessage(f'Job {job_id}: {value}%')

    def update_memory(self, memory_mb: float) -> None:
        self.memory_label.setText(f'Mem: {round(float(memory_mb))} MB')

    def _create_shortcuts(self):
        self._shortcuts = []
        for sequence, handler in (
            ('Ctrl+N', self._new_project),
            ('Ctrl+O', self._open_project),
            ('Ctrl+S', self._save_project),
            ('Ctrl+W', self._close_active_tab),
            ('Ctrl+Tab', self._next_tab),
            ('Ctrl+Shift+Tab', self._prev_tab),
            ('F11', self.enter_dashboard_fullscreen),
            ('F5', self.exit_dashboard_fullscreen),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(handler)
            self._shortcuts.append(shortcut)

    def _sync_fullscreen_controls(self) -> None:
        """Keep the bottom full-screen controls correct on every dashboard."""
        active = bool(getattr(self, "_dashboard_fullscreen_active", False))
        if hasattr(self, "fullscreen_view_btn"):
            self.fullscreen_view_btn.setEnabled(not active)
            self.fullscreen_view_btn.setVisible(not active)
        if hasattr(self, "normal_screen_btn"):
            self.normal_screen_btn.setEnabled(active)
            self.normal_screen_btn.setVisible(True)
        if hasattr(self, "_view_fullscreen_action"):
            self._view_fullscreen_action.setEnabled(not active)
        if hasattr(self, "_view_normal_screen_action"):
            self._view_normal_screen_action.setEnabled(active)

    def enter_dashboard_fullscreen(self) -> None:
        """Show the active document/dashboard with minimum chrome.

        The feature is application-wide because every dashboard is hosted in the
        same central document tab area. F11 enters the full-screen dashboard view;
        F5 restores the normal workstation layout.
        """
        if getattr(self, "_dashboard_fullscreen_active", False):
            return

        state: dict[str, Any] = {
            "window_state": self.windowState(),
            "geometry": self.saveGeometry(),
            "title_bar_visible": self.title_bar.isVisible() if hasattr(self, "title_bar") else True,
            "ribbon_visible": self.ribbon_dock.isVisible() if hasattr(self, "ribbon_dock") else True,
            "project_dock_visible": self.project_dock.isVisible() if hasattr(self, "project_dock") else False,
            "properties_dock_visible": self.properties_dock.isVisible() if hasattr(self, "properties_dock") else False,
            "output_dock_visible": self.output_dock.isVisible() if hasattr(self, "output_dock") else False,
            "document_tabs_visible": self.tab_widget.tabBar().isVisible() if hasattr(self, "tab_widget") else True,
        }
        self._dashboard_fullscreen_state = state
        self._dashboard_fullscreen_active = True

        if hasattr(self, "title_bar"):
            self.title_bar.hide()
        if hasattr(self, "ribbon_dock"):
            self.ribbon_dock.hide()
        for dock_name in ("project_dock", "properties_dock", "output_dock"):
            dock = getattr(self, dock_name, None)
            if dock is not None:
                dock.hide()
        if hasattr(self, "tab_widget"):
            self.tab_widget.tabBar().hide()

        self.showFullScreen()
        self._sync_fullscreen_controls()
        if hasattr(self, "status_bar"):
            self.status_bar.showMessage("Full Screen View active — press F5 or click Back to Normal", 3500)

    def exit_dashboard_fullscreen(self) -> None:
        """Restore the normal workstation layout from full-screen dashboard view."""
        if not getattr(self, "_dashboard_fullscreen_active", False):
            return

        state = getattr(self, "_dashboard_fullscreen_state", {}) or {}
        self._dashboard_fullscreen_active = False

        if hasattr(self, "title_bar"):
            self.title_bar.setVisible(bool(state.get("title_bar_visible", True)))
        if hasattr(self, "ribbon_dock"):
            self.ribbon_dock.setVisible(bool(state.get("ribbon_visible", True)))
        for key, dock_name in (
            ("project_dock_visible", "project_dock"),
            ("properties_dock_visible", "properties_dock"),
            ("output_dock_visible", "output_dock"),
        ):
            dock = getattr(self, dock_name, None)
            if dock is not None:
                dock.setVisible(bool(state.get(key, False)))
        if hasattr(self, "tab_widget"):
            self.tab_widget.tabBar().setVisible(bool(state.get("document_tabs_visible", True)))

        saved_geometry = state.get("geometry")
        if saved_geometry is not None:
            self.restoreGeometry(saved_geometry)

        previous_state = state.get("window_state", Qt.WindowNoState)
        if previous_state & Qt.WindowMaximized:
            self.showMaximized()
        else:
            self.showNormal()
            self.setWindowState(Qt.WindowNoState)

        self._sync_fullscreen_controls()
        if hasattr(self, "status_bar"):
            self.status_bar.showMessage("Normal dashboard layout restored", 2500)


    def _new_project(self):
        from ui.dialogs.project_setup_dialog import ProjectSetupDialog
        dialog = ProjectSetupDialog(self)
        if not dialog.exec():
            return
        project_data = dialog.project_data()
        location = Path(project_data.pop('location'))
        task_id = "project:create"
        self.begin_busy_task(task_id, "Creating Project", f"Preparing workspace for {project_data.get('name', 'new project')}")
        error: Exception | None = None
        project = None
        try:
            self.update_busy_task(task_id, 35, "Creating project folders and database records")
            project = self._workspace_manager.create_project(project_data['name'], location, project_data)
            self._current_project_name = project.name
            self._current_project_path = location / project.name
            self.setWindowTitle(f"TGPAssure — {project.name}")
            self.project_label.setText(project.name)
            self.title_bar.title.setText(self.windowTitle())
            self.update_busy_task(task_id, 78, "Building Project Explorer")
            self.project_explorer.add_project(str(self._current_project_path))
            self.update_busy_task(task_id, 100, "Project is ready")
            self._update_ribbon()
        except Exception as exc:
            error = exc
        finally:
            self.end_busy_task(task_id)
        if error is not None:
            QMessageBox.critical(self, "Error", f"Failed to create project: {str(error)}")
        elif project is not None:
            QMessageBox.information(self, "Success", f"Project '{project.name}' created.")

    def _open_project(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", str(Path.home()),
            "TGP Project Files (*.tgp-project);;All Files (*.*)"
        )
        if file_path:
            self.open_project_path(file_path)

    def open_project_path(self, file_path: str | Path, *, silent: bool = False) -> bool:
        path = Path(file_path).expanduser().resolve()
        task_id = "project:open"
        self.begin_busy_task(task_id, "Opening Project", f"Loading {path.name}")
        try:
            project = self._workspace_manager.open_project(path)
            self._current_project_name = project.name
            self._current_project_path = path.parent
            self.setWindowTitle(f"TGPAssure — {project.name}")
            self.project_label.setText(project.name)
            self.title_bar.title.setText(self.windowTitle())
            self.update_busy_task(task_id, 65, "Restoring managed files and project workspace")
            self.project_explorer.clear()
            self.project_explorer.add_project(str(self._current_project_path))
            self.update_busy_task(task_id, 100, "Project ready")
            self._update_ribbon()
            if not silent:
                QMessageBox.information(self, "Project Opened", f"Project '{project.name}' opened successfully.")
            return True
        except Exception as exc:
            if not silent:
                QMessageBox.critical(self, "Open Project", f"Failed to open project:\n{exc}")
            else:
                self.log(f"Failed to restore project {path}: {exc}")
            return False
        finally:
            self.end_busy_task(task_id)

    def _save_project(self):
        if self._workspace_manager.current_project_file is None:
            QMessageBox.warning(self, "Save Project", "Open or create a project before saving.")
            return
        task_id = "project:save"
        self.begin_busy_task(task_id, "Saving Project", "Checkpointing database and workspace state")
        try:
            self.update_busy_task(task_id, 45, "Saving tabs and workspace state")
            state_path = self._workspace_manager.save_project()
            self.update_busy_task(task_id, 100, "Project saved")
            self.status_bar.showMessage(f"Project saved — {state_path.name}", 4000)
        except Exception as exc:
            QMessageBox.critical(self, "Save Project", f"Failed to save project:\n{exc}")
        finally:
            self.end_busy_task(task_id)
            self._update_ribbon()

    def _save_project_as(self):
        if self._workspace_manager.current_project_file is None:
            QMessageBox.warning(self, "Save Project Copy", "Open or create a project first.")
            return
        default = self._workspace_manager.current_project_file.with_name(self._workspace_manager.current_project_file.stem + "_copy.tgp-project")
        output, _ = QFileDialog.getSaveFileName(self, "Save Project Database Copy", str(default), "TGP Project (*.tgp-project)")
        if not output:
            return
        task_id = "project:backup"
        self.begin_busy_task(task_id, "Saving Project Copy", "Checkpointing and copying the project database")
        try:
            self._workspace_manager.save_project()
            source = self._workspace_manager.current_project_file
            import shutil
            target = Path(output).with_suffix(".tgp-project")
            shutil.copy2(source, target)
            self.update_busy_task(task_id, 100, "Project database copy saved")
            QMessageBox.information(self, "Save Project Copy", f"Saved database copy:\n{target}\n\nManaged raw/derived files remain in the original project folder.")
        except Exception as exc:
            QMessageBox.critical(self, "Save Project Copy", str(exc))
        finally:
            self.end_busy_task(task_id)

    def _import_file(self):
        if self._workspace_manager.current_project_file is None:
            QMessageBox.warning(self, "No Project", "Please open or create a project first!")
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import File", str(Path.home()),
            "Geophysical data (*.sgy *.segy *.segd *.sgd *.d *.csv *.tsv *.txt *.dat *.log *.xyz *.asc *.xlsx *.xlsm *.kml *.kmz);;SEG-Y Files (*.sgy *.segy);;SEG-D Files (*.segd *.sgd *.d);;Tabular data (*.csv *.tsv *.txt *.dat *.xyz *.xlsx *.xlsm);;All Files (*.*)"
        )
        if file_path:
            self.import_external_path(file_path)

    def import_external_path(self, file_path: str | Path) -> bool:
        if self._workspace_manager.current_project_file is None:
            QMessageBox.warning(self, "No Project", "Open or create a project before importing data.")
            return False
        source = Path(file_path).expanduser().resolve()
        task_id = f"project:import:{source.name}"
        self.begin_busy_task(task_id, "Importing File", f"Preparing {source.name}", 0)
        try:
            def report(percent: int, message: str) -> None:
                # Reserve the last 15% for database registration/UI refresh.
                self.update_busy_task(task_id, min(85, int(percent * 0.85)), message)
                QApplication.processEvents()

            record = self._workspace_manager.import_file(source, progress_callback=report)
            self.update_busy_task(task_id, 90, "Registering managed file in Project Explorer")
            self.project_explorer.add_file(str(record.managed_path))
            self.file_imported.emit(str(record.managed_path))
            self._selected_project_path = record.managed_path
            self.log(f"Imported file: {record.managed_path.name} [{record.sha256[:12]}…]")
            self.update_busy_task(task_id, 100, "Import complete")
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Import File", f"Failed to import file:\n{exc}")
            return False
        finally:
            self.end_busy_task(task_id)
            self._update_ribbon()

    def _on_project_item_selected(self, path: str) -> None:
        self._selected_project_path = Path(path).expanduser()
        self.log(f"Selected: {path}")
        self._update_ribbon()
        if hasattr(self, "properties_panel"):
            try:
                if hasattr(self.properties_panel, "load_path"):
                    self.properties_panel.load_path(path)
                elif hasattr(self.properties_panel, "set_file_path"):
                    self.properties_panel.set_file_path(path)
            except Exception as e:
                self.log(f"Error updating properties: {e}")
        suffix = Path(path).suffix.lower()
        if suffix in {".segd", ".sgd", ".d"}:
            self._set_active_module("segd")

    def _view_segy_raw(self) -> None:
        view = self._get_segy_qc_view()
        path = getattr(view, "current_file_path", None) if view is not None else None
        if path is None:
            self.status_bar.showMessage("Open a raw SEG-Y file in SEG-Y QC first", 3000)
            return
        self._open_visualization_path(str(path))

    def _select_segy_post_qc(self) -> None:
        view = self._get_segy_qc_view()
        if view is None:
            self._warn_segy_qc_unavailable()
            return
        if self.activate_segy_qc_view():
            view.select_post_qc_file()
            self._update_ribbon()

    def _view_segy_post_qc(self) -> None:
        view = self._get_segy_qc_view()
        path = getattr(view, "post_qc_file_path", None) if view is not None else None
        if path is None:
            self.status_bar.showMessage("Select a processed/post-QC SEG-Y file first", 3000)
            return
        self._open_visualization_path(str(path))

    def _compare_segy_pre_post(self) -> None:
        view = self._get_segy_qc_view()
        raw = getattr(view, "current_file_path", None) if view is not None else None
        post = getattr(view, "post_qc_file_path", None) if view is not None else None
        if raw is None or post is None:
            self.status_bar.showMessage("Raw and post-QC SEG-Y files are required for comparison", 3000)
            return
        self._open_segy_pre_post_comparison(str(raw), str(post))

    def _open_segy_pre_post_comparison(self, raw_path: str, post_path: str) -> None:
        raw = str(Path(raw_path).expanduser().resolve())
        post = str(Path(post_path).expanduser().resolve())
        comparison_key = f"{raw}|{post}"
        for index in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(index)
            if widget is not None and widget.property("segy_comparison_key") == comparison_key:
                self.tab_widget.setCurrentIndex(index)
                self._set_active_module("segy_qc")
                return
        try:
            from modules.seismic.segy_viewer.pre_post_comparison import SegyPrePostComparison

            comparison = SegyPrePostComparison(raw, post, self)
            comparison.setProperty("segy_comparison_key", comparison_key)
            comparison.setProperty("module_id", "segy_qc")
            index = self._add_document_tab(
                comparison,
                f"SEG-Y Compare: {Path(raw).stem} ↔ {Path(post).stem}",
                icon=get_icon("view-split-left-right", size=15),
            )
            self.tab_widget.setCurrentIndex(index)
            self._set_active_module("segy_qc")
            self.log(f"Opened SEG-Y raw/post-QC comparison: {raw} | {post}")
        except Exception as exc:
            QMessageBox.critical(self, "SEG-Y Comparison", f"Unable to open comparison:\n{exc}")

    def _select_segy_repeatability_base(self) -> None:
        view = self._get_segy_qc_view()
        if view is None:
            self._warn_segy_qc_unavailable()
            return
        if self.activate_segy_qc_view():
            view.select_repeatability_base_file()

    def _focus_segy_processing_stage(self, stage_key: str) -> None:
        view = self._get_segy_qc_view()
        if view is None:
            self._warn_segy_qc_unavailable()
            return
        if self.activate_segy_qc_view():
            view.focus_stage(stage_key)

    def _run_segy_qc(self) -> None:
        view = self._get_segy_qc_view()
        if view is None:
            self._warn_segy_qc_unavailable()
            return
        if self.activate_segy_qc_view():
            view.run_qc()

    def _cancel_segy_qc(self) -> None:
        view = self._get_segy_qc_view()
        if view is None:
            self._warn_segy_qc_unavailable()
            return
        if self.activate_segy_qc_view():
            view.cancel_qc()

    def _view_segy_results(self) -> None:
        view = self._get_segy_qc_view()
        if view is None:
            self._warn_segy_qc_unavailable()
            return
        if self.activate_segy_qc_view():
            view.show_results()

    def _edit_segy_qc_profile(self) -> None:
        view = self._get_segy_qc_view()
        if view is None:
            self._warn_segy_qc_unavailable()
            return
        if self.activate_segy_qc_view():
            view.edit_thresholds()

    def _open_data_quality_dashboard(self) -> None:
        self.activate_data_quality_dashboard()

    def attach_data_quality_dashboard(self, dashboard: QWidget, open_now: bool = False) -> None:
        if dashboard is None:
            return
        self._data_quality_dashboard = dashboard
        dashboard.setProperty("module_id", "segy_qc")
        dashboard.destroyed.connect(self._clear_data_quality_dashboard_reference)
        if open_now:
            self.activate_data_quality_dashboard()
        elif self.tab_widget.indexOf(dashboard) < 0:
            dashboard.hide()

    def _clear_data_quality_dashboard_reference(self, *_args) -> None:
        self._data_quality_dashboard = None
        self._update_ribbon()

    def activate_data_quality_dashboard(self) -> None:
        dashboard = self._data_quality_dashboard
        if dashboard is None:
            try:
                from core.domain.data_quality_service import DataQualityService
                from ui.docks.data_quality_dashboard import DataQualityDashboard

                service = self.container.resolve(DataQualityService)
                dashboard = DataQualityDashboard(service, self)
                self.attach_data_quality_dashboard(dashboard)
            except Exception as exc:
                QMessageBox.warning(
                    self,
                    "Data Quality Dashboard",
                    f"Unable to open the Data Quality dashboard:\n{exc}",
                )
                return

        index = self.tab_widget.indexOf(dashboard)
        if index < 0:
            index = self._add_document_tab(
                dashboard,
                "Data Quality",
                icon=get_icon("view-dashboard", size=15),
                closable=True,
            )

        self.tab_widget.setCurrentIndex(index)
        self._set_active_module("segy_qc")
        task_id = "data-quality:refresh"
        self.begin_busy_task(task_id, "Refreshing Data Quality", "Updating QC metrics, findings and summaries")
        try:
            if hasattr(dashboard, "show_overview"):
                dashboard.show_overview()
            elif hasattr(dashboard, "refresh"):
                dashboard.refresh()
            self.update_busy_task(task_id, 100, "Data Quality dashboard is ready")
        except Exception as exc:
            self.log(f"Data Quality dashboard refresh failed: {exc}")
        finally:
            self.end_busy_task(task_id)
        dashboard.show()
        dashboard.raise_()
        dashboard.setFocus(Qt.OtherFocusReason)

    def open_imported_file(self, file_path: str | Path) -> None:
        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            QMessageBox.warning(self, "File Not Found", f"The selected file does not exist:\n{path}")
            return
        suffix = path.suffix.lower()
        if suffix in {".sgy", ".segy", ".segd", ".sgd", ".d"}:
            self._open_visualization_path(str(path))
            return
        if suffix in {".csv", ".tsv", ".txt", ".dat", ".log", ".xyz", ".asc", ".xlsx", ".xlsm"}:
            # Generic ASCII extensions can represent gravity or magnetic data.
            # Keep the user informed while the gravity schema probe runs, then
            # hand magnetic imports to the dashboard's asynchronous loader.
            detection_task = f"file-detect:{path}"
            self.begin_busy_task(
                detection_task,
                "Inspecting Geophysical File",
                f"Checking data structure for {path.name}",
            )
            gravity_data = None
            try:
                self.update_busy_task(detection_task, 20, "Checking for gravity observation fields")
                from modules.gravity.reader import GravityReader
                gravity_data = GravityReader().read_observations(str(path))
            except Exception as exc:
                self.log(f"Gravity import did not match: {exc}")
            if gravity_data is not None:
                try:
                    self.update_busy_task(detection_task, 70, "Preparing gravity dashboard")
                    gravity_dashboard = self._open_gravity_dashboard()
                    if gravity_dashboard is not None:
                        gravity_dashboard._accept_observations(gravity_data)
                        self.update_busy_task(detection_task, 100, "Gravity dataset is ready")
                        return
                finally:
                    self.end_busy_task(detection_task)
            self.update_busy_task(detection_task, 55, "Checking for electrical survey fields")
            try:
                from modules.electrical.reader import ElectricalReader
                inspection = ElectricalReader().inspect(path)
                if inspection.get("is_electrical_candidate"):
                    self.update_busy_task(detection_task, 75, "Preparing Electrical QC dashboard")
                    dashboard = self._open_electrical_dashboard()
                    self.end_busy_task(detection_task)
                    if dashboard is not None:
                        dashboard.open_data_path(str(path))
                        return
            except Exception as exc:
                self.log(f"Electrical import did not match: {exc}")
            self.end_busy_task(detection_task)
            dashboard = self._open_magnetic_dashboard()
            if dashboard is not None:
                try:
                    dashboard.open_rover_path(str(path), show_import_dialog=False)
                    return
                except Exception as exc:
                    self.log(f"Magnetic import failed: {exc}")
        self.log(f"Imported file is not a supported seismic, magnetic, gravity or electrical file: {path}")
        QMessageBox.information(self, "File Imported", f"Imported file: {path.name}")

    def _open_visualization(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open SEG-Y or SEG-D for 2D/3D Visualization",
            str(Path.home()),
            "Seismic Files (*.sgy *.segy *.segd *.sgd *.d *.dat);;SEG-Y (*.sgy *.segy);;SEG-D (*.segd *.sgd *.d *.dat);;All Files (*.*)",
        )
        if file_path:
            self._open_visualization_path(file_path)

    def _open_visualization_path(self, file_path: str) -> None:
        resolved = str(Path(file_path).expanduser().resolve())
        for index in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(index)
            if widget is not None and widget.property("seismic_visualization_file_path") == resolved:
                self.tab_widget.setCurrentIndex(index)
                self._set_active_module("visualization")
                return
        setup_task = f"visualization:setup:{resolved}"
        self.begin_busy_task(
            setup_task,
            "Opening 2D/3D Seismic Viewer",
            f"Initializing visualization tools for {Path(resolved).name}",
        )
        try:
            from modules.seismic.visualization.dashboard import SeismicVisualizationDashboard

            self.update_busy_task(setup_task, 55, "Building seismic visualization workspace")
            viewer = SeismicVisualizationDashboard(self.container, resolved, self)
            viewer.setProperty("module_id", "visualization")
            viewer.setProperty("seismic_visualization_file_path", resolved)
            viewer.status_message.connect(self.log)
            activity_id = f"visualization:{id(viewer)}"
            viewer.activity_started.connect(
                lambda title, message, task_id=activity_id: self.begin_busy_task(
                    task_id, title, message
                )
            )
            viewer.activity_progress.connect(
                lambda value, message, task_id=activity_id: self.update_busy_task(
                    task_id, value, message
                )
            )
            viewer.activity_finished.connect(
                lambda task_id=activity_id: self.end_busy_task(task_id)
            )
            viewer.destroyed.connect(
                lambda *_, task_id=activity_id: self.end_busy_task(task_id)
            )
            index = self._add_document_tab(
                viewer,
                f"2D/3D: {Path(resolved).name}",
                icon=get_icon("view-3d", color="#FFFFFF", size=15),
            )
            self.tab_widget.setCurrentIndex(index)
            self._set_active_module("visualization")
            self.update_busy_task(setup_task, 100, "Visualization workspace is ready")
            self.log(f"Opened 2D/3D seismic viewer: {resolved}")
        except Exception as exc:
            self.log(f"Failed to open 2D/3D viewer: {exc}")
            QMessageBox.critical(self, "2D/3D Open Error", f"Failed to open seismic file:\n{resolved}\n\n{exc}")
        finally:
            self.end_busy_task(setup_task)

    def _open_segd_viewer(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open SEG-D File",
            str(Path.home()),
            "SEG-D Files (*.segd *.sgd *.d *.dat);;All Files (*.*)",
        )
        if not file_path:
            return
        self._open_segd_path(file_path)

    def _open_segd_path(self, file_path: str) -> None:
        resolved = str(Path(file_path).resolve())
        for index in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(index)
            if widget is not None and widget.property("segd_file_path") == resolved:
                self.tab_widget.setCurrentIndex(index)
                self._set_active_module("segd")
                return
        self._show_full_page_loader("Opening SEG-D", f"Preparing {Path(file_path).name}")
        try:
            from core.data_access.db_engine import DatabaseEngine
            from modules.seismic.segd_viewer.segd_viewer_widget import SegdViewerWidget

            viewer = SegdViewerWidget(
                file_path, self, db_engine=self.container.resolve(DatabaseEngine), auto_open=False
            )
            viewer.loading_started.connect(lambda title, message: self._show_full_page_loader(title, message))
            viewer.loading_progress.connect(
                lambda value, message: self._update_full_page_loader(value, message)
            )
            viewer.loading_finished.connect(self._hide_full_page_loader)
            viewer.setProperty("module_id", "segd")
            viewer.setProperty("segd_file_path", resolved)
            index = self._add_document_tab(
                viewer,
                f"SEG-D: {Path(file_path).name}",
                icon=get_icon("seg-d", color="#FFFFFF", size=15),
            )
            self.tab_widget.setCurrentIndex(index)
            self._set_active_module("segd")
            viewer.open_file(file_path)
            self.log(f"Opening SEG-D file asynchronously: {file_path}")
        except Exception as e:
            self._hide_full_page_loader()
            self.log(f"Failed to open SEG-D file: {e}")
            QMessageBox.critical(self, "SEG-D Open Error", f"Failed to open SEG-D file:\n{file_path}\n\n{e}")

    def _generate_report(self, format_type: str) -> None:
        view = self._get_segy_qc_view()
        if view is None:
            self._warn_segy_qc_unavailable()
            return
        if self.activate_segy_qc_view():
            view.request_report(format_type)

    @staticmethod
    def _is_qobject_alive(obj: object | None) -> bool:
        if obj is None:
            return False
        try:
            return bool(is_qobject_valid(obj))
        except RuntimeError:
            return False

    def _get_segy_qc_view(self) -> QWidget | None:
        view = self._segy_qc_view
        if not self._is_qobject_alive(view):
            self._segy_qc_view = None
            return None
        return view

    def _warn_segy_qc_unavailable(self) -> None:
        QMessageBox.warning(
            self,
            "SEG-Y QC",
            "The SEG-Y QC workspace is not available. Reopen the project or restart the application.",
        )

    def _clear_segy_qc_view_reference(self, *_args) -> None:
        self._segy_qc_view = None
        self._update_ribbon()

    def attach_segy_qc_view(self, view: QWidget) -> None:
        if not self._is_qobject_alive(view):
            self._segy_qc_view = None
            return

        self._segy_qc_view = view
        view.setProperty("module_id", "segy_qc")
        view.destroyed.connect(self._clear_segy_qc_view_reference)
        if hasattr(view, "view_file_requested"):
            view.view_file_requested.connect(self._open_visualization_path)
        if hasattr(view, "compare_files_requested"):
            view.compare_files_requested.connect(self._open_segy_pre_post_comparison)
        if hasattr(view, "review_targets_changed"):
            view.review_targets_changed.connect(self._update_ribbon)
        if hasattr(view, "activity_started"):
            view.activity_started.connect(
                lambda title, message: self.begin_busy_task("segy:file", title, message)
            )
            view.activity_progress.connect(
                lambda value, message: self.update_busy_task("segy:file", value, message)
            )
            view.activity_finished.connect(lambda: (self.end_busy_task("segy:file"), self._update_ribbon()))
            view.destroyed.connect(lambda *_: self.end_busy_task("segy:file"))
        controller = getattr(view, "controller", None)
        if controller is not None:
            for signal_name in ("file_loaded", "run_started", "run_completed", "run_failed", "run_cancelled", "run_loaded"):
                signal = getattr(controller, signal_name, None)
                if signal is not None:
                    try:
                        signal.connect(lambda *_: self._update_ribbon())
                    except Exception:
                        pass

        index = self.tab_widget.indexOf(view)
        if index >= 0:
            self._segy_qc_tab_title = self.tab_widget.tabText(index) or "SEG-Y QC"
            self._segy_qc_tab_icon = self.tab_widget.tabIcon(index)

    def activate_segy_qc_view(self) -> bool:
        view = self._get_segy_qc_view()
        if view is None:
            return False

        try:
            index = self.tab_widget.indexOf(view)
            if index < 0:
                index = self._add_document_tab(
                    view,
                    self._segy_qc_tab_title,
                    icon=self._segy_qc_tab_icon if not self._segy_qc_tab_icon.isNull() else get_icon(
                        "seismic",
                        color="#FFFFFF",
                        size=15,
                    ),
                    closable=True,
                )
            self.tab_widget.setCurrentIndex(index)
            view.show()
            view.raise_()
            view.setFocus(Qt.OtherFocusReason)
            self._set_active_module("segy_qc")
            return True
        except RuntimeError as exc:
            self.log(f"SEG-Y QC view is no longer valid: {exc}")
            self._clear_segy_qc_view_reference()
            return False

    def _show_about(self):
        QMessageBox.about(
            self,
            "About TGPAssure",
            "TGPAssure\nVersion 0.2.0\n\n"
            "Quality Control Application for Geophysical Data\n"
            "Built with PySide6, NumPy, and SQLite"
        )

    def _reset_layout(self):
        self.project_dock.setVisible(True)
        self.properties_dock.setVisible(True)
        self.output_dock.setVisible(True)
        self.tab_widget.setCurrentIndex(0)

    def _close_tab_by_index(self, index: int):
        widget = self.tab_widget.widget(index)
        if widget is None:
            return

        segy_view = self._get_segy_qc_view()
        if segy_view is not None and widget is segy_view:
            self._segy_qc_tab_title = self.tab_widget.tabText(index) or "SEG-Y QC"
            self._segy_qc_tab_icon = self.tab_widget.tabIcon(index)
            self.tab_widget.removeTab(index)
            widget.hide()
            self._sync_document_workspace()
            return

        if hasattr(widget, "close_file"):
            try:
                widget.close_file()
            except Exception:
                pass

        tab_id = widget.property("workspace_tab_id")
        if tab_id and tab_id in self._workspace_manager._tabs:
            self._workspace_manager.close_tab(tab_id)
        else:
            self.tab_widget.removeTab(index)
            widget.deleteLater()
            self._sync_document_workspace()

    def _close_active_tab(self):
        idx = self.tab_widget.currentIndex()
        if idx >= 0:
            self._close_tab_by_index(idx)

    def _next_tab(self):
        count = self.tab_widget.count()
        if count > 0:
            current = self.tab_widget.currentIndex()
            self.tab_widget.setCurrentIndex((current + 1) % count)

    def _prev_tab(self):
        count = self.tab_widget.count()
        if count > 0:
            current = self.tab_widget.currentIndex()
            self.tab_widget.setCurrentIndex((current - 1) % count)

    def _on_current_tab_changed(self, index: int):
        if index < 0:
            return
        widget = self.tab_widget.widget(index)
        if widget is None:
            return
        module_id = widget.property("module_id")
        if module_id:
            self._set_active_module(str(module_id))
        else:
            self._update_ribbon()

    def _on_tab_changed(self, tab: WorkspaceTab):
        tab.widget.setProperty('workspace_tab_id', tab.tab_id)
        for index in range(self.tab_widget.count()):
            if self.tab_widget.widget(index) is tab.widget:
                self.tab_widget.setCurrentIndex(index)
                return
        index = self._add_document_tab(tab.widget, tab.title)
        self.tab_widget.setCurrentIndex(index)

    def _on_tab_closed(self, tab_id: str):
        for index in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(index)
            if widget is None or widget.property('workspace_tab_id') != tab_id:
                continue

            segy_view = self._get_segy_qc_view()
            if segy_view is not None and widget is segy_view:
                self._segy_qc_tab_title = self.tab_widget.tabText(index) or "SEG-Y QC"
                self._segy_qc_tab_icon = self.tab_widget.tabIcon(index)
                self.tab_widget.removeTab(index)
                widget.hide()
                self._sync_document_workspace()
                return

            self.tab_widget.removeTab(index)
            widget.deleteLater()
            self._sync_document_workspace()
            return

    def closeEvent(self, event: QCloseEvent):
        if self._workspace_manager.current_project_file is not None and self._workspace_manager.is_dirty:
            confirm = True
            if self._settings_store is not None:
                confirm = bool(self._settings_store.get("confirm_close", True))
            if confirm:
                answer = QMessageBox.question(
                    self,
                    "Unsaved Project State",
                    "The project workspace has unsaved changes. Save before closing?",
                    QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                    QMessageBox.Save,
                )
                if answer == QMessageBox.Cancel:
                    event.ignore()
                    return
                if answer == QMessageBox.Save:
                    try:
                        self._workspace_manager.save_project()
                    except Exception as exc:
                        QMessageBox.critical(self, "Save Project", f"Could not save project before closing:\n{exc}")
                        event.ignore()
                        return
        try:
            self._layout_store.save_layout(self.saveState())
        except Exception as exc:
            self.log(f"Layout save failed during shutdown: {exc}")
        self._autosave_timer.stop()
        event.accept()

    def log(self, text: str):
        try:
            if hasattr(self, 'output_console'):
                if hasattr(self.output_console, 'log'):
                    self.output_console.log('INFO', text)
                else:
                    self.output_console.appendPlainText(f"[INFO] {text}")
        except Exception:
            print(f"[INFO] {text}")