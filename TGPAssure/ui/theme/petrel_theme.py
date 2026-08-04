from __future__ import annotations

FONT_FAMILY = "Poppins"
FONT_SIZE_LARGE = 11
FONT_SIZE_NORMAL = 9
FONT_SIZE_SMALL = 8
FONT_SIZE_CAPTION = 7

STYLESHEET = r"""
* { font-family: "Poppins"; font-size: 9pt; color: #252525; }
QMainWindow { background: #dfe1e6; }
QWidget { background: #f6f7fa; }

#titleBar {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #4B5158,stop:1 #30353B);
    border-bottom: 1px solid #1E2328;
}
#titleBar QLabel { background: transparent; color: #FFFFFF; }
#titleBar > QLabel { font-size: 9pt; }
#appGlyph {
    background: #D7A514; color: #FFFFFF; border: 1px solid #F0C64B;
    border-radius: 3px; font-weight: 700; font-size: 10pt;
}
#quickAccessButton, #windowControl, #closeControl {
    background: transparent; color: #FFFFFF; border: 1px solid transparent; border-radius: 3px; padding: 0;
}
#quickAccessButton:hover, #windowControl:hover { background: rgba(255,255,255,42); border-color: rgba(255,255,255,76); }
#closeControl:hover { background: #E5484D; border-color: #F06A6E; }

#ribbonContainer {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #f1f2f5,stop:1 #e8e9ed);
    border-bottom: 1px solid #bdc1c8;
}
QTabBar#ribbonTabs {
    background: transparent;
    border: 0;
    qproperty-drawBase: false;
}
QTabBar#ribbonTabs::tab {
    background: transparent;
    color: #171717;
    border: 1px solid transparent;
    border-bottom: 0;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
    padding: 7px 13px 6px 13px;
    margin: 3px 1px 0 1px;
    min-height: 22px;
    font-size: 10pt;
    font-weight: 400;
}
QTabBar#ribbonTabs::tab:hover:!selected {
    background: rgba(255, 255, 255, 115);
    border-color: #d7d9de;
}
QTabBar#ribbonTabs::tab:selected {
    background: #ffffff;
    color: #151515;
    border-color: #d0d3d9;
    border-bottom-color: #ffffff;
    font-weight: 500;
}
QTabBar#ribbonTabs QToolButton {
    background: transparent;
    border: 0;
}
#ribbonGroupsBackground {
    background: transparent;
}
#ribbonGroupsContainer {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #ffffff,stop:1 #fbfbfc);
    border: 1px solid #d2d5da;
    border-radius: 7px;
}
QWidget#ribbonGroupContent,
QWidget#ribbonSmallColumn {
    background: transparent;
}
QFrame#ribbonGroup {
    background: transparent;
    border: 0;
    margin: 0;
}
QFrame#ribbonSeparator {
    background: #d4d6da;
    border: 0;
    min-width: 1px;
    max-width: 1px;
    margin: 7px 3px 18px 3px;
}
QToolButton#ribbonLargeAction,
QToolButton#ribbonSmallAction {
    background: transparent;
    color: #1f1f1f;
    border: 1px solid transparent;
    border-radius: 5px;
}
QToolButton#ribbonLargeAction {
    padding: 3px 3px 2px 3px;
    font-size: 8pt;
}
QToolButton#ribbonSmallAction {
    padding: 1px 5px 1px 4px;
    text-align: left;
    font-size: 8pt;
}
QToolButton#ribbonLargeAction:hover,
QToolButton#ribbonSmallAction:hover {
    background: #edf3f8;
    border-color: #bfd0df;
}
QToolButton#ribbonLargeAction:pressed,
QToolButton#ribbonSmallAction:pressed,
QToolButton#ribbonLargeAction:checked,
QToolButton#ribbonSmallAction:checked,
QToolButton#ribbonLargeAction[accent="true"],
QToolButton#ribbonSmallAction[accent="true"] {
    background: #dedfe3;
    border-color: #d1d3d8;
}
QToolButton#ribbonLargeAction:disabled,
QToolButton#ribbonSmallAction:disabled {
    color: #9b9da1;
}
QLabel#ribbonGroupLabel {
    background: transparent;
    color: #3d3f43;
    border: 0;
    padding: 0 5px 1px 5px;
    font-size: 7pt;
    font-weight: 400;
}
QLabel#featureBadge {
    background: #d77718;
    color: #ffffff;
    border: 1px solid #ffffff;
    border-radius: 7px;
    font-size: 6pt;
    font-weight: 700;
    padding: 1px 4px;
}

QDockWidget { background: white; border: 1px solid #b9bdc5; }
QWidget#dockTitleBar {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #f2f3f6,stop:1 #dfe2e7);
    border-top: 1px solid white; border-bottom: 1px solid #b8bcc4;
}
QLabel#dockTitleLabel { background: transparent; color: #202020; font-size: 9pt; font-weight: 500; }
QToolButton#dockTitleButton, QToolButton#dockCloseButton {
    background: transparent; border: 1px solid transparent; border-radius: 2px; padding: 0;
}
QToolButton#dockTitleButton:hover { background: #d8dde5; border-color: #b6bbc4; }
QToolButton#dockCloseButton:hover { background: #e81123; border-color: #e81123; }

QTreeWidget, QTreeView, QTableView, QListWidget, QListView {
    background: white; alternate-background-color: #fafafa; border: 1px solid #c8ccd3; outline: 0;
}
QTreeWidget::item, QTreeView::item, QListWidget::item, QListView::item { min-height: 20px; padding: 1px 2px; }
QTreeWidget::item:hover, QTreeView::item:hover, QListWidget::item:hover, QListView::item:hover { background: #edf3fa; }
QTreeWidget::item:selected, QTreeView::item:selected, QListWidget::item:selected, QListView::item:selected { background: #cfe4f8; color: #111; }
QHeaderView::section {
    background: #e7e9ed; color: #222; border: 0; border-right: 1px solid #c8ccd3;
    border-bottom: 1px solid #c8ccd3; padding: 3px 5px; font-size: 8pt;
}

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox {
    background: white; border: 1px solid #bfc4cc; border-radius: 2px; padding: 3px 5px;
    selection-background-color: #cfe4f8;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border-color: #6c9ec9; }
QPushButton {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #ffffff,stop:1 #e7e9ed);
    border: 1px solid #b9bdc5; border-radius: 3px; padding: 4px 10px;
}
QPushButton:hover { background: #e7eef7; border-color: #87a9ca; }
QPushButton:pressed { background: #d4e2f2; }
QGroupBox { border: 1px solid #c4c8cf; border-radius: 3px; margin-top: 10px; font-weight: 600; background: white; }
QGroupBox::title { subcontrol-origin: margin; left: 7px; padding: 0 4px; background: #f6f7fa; }

QTabWidget#documentTabs::pane { background: #e2e3e7; border: 1px solid #bdc1c8; top: -1px; }
QTabBar#documentTabBar { background: #e8eaee; border-bottom: 1px solid #bdc1c8; }
QTabBar#documentTabBar::tab {
    background: #eceef2; color: #222; border: 1px solid #c6c9cf; border-bottom: 0;
    padding: 5px 12px; margin-right: 1px; min-height: 22px; font-size: 8pt;
}
QTabBar#documentTabBar::tab:selected { background: white; border-top: 2px solid #c79a13; font-weight: 600; }
QTabBar#documentTabBar::tab:hover:!selected { background: #f6f7f9; }
QTabBar::close-button { width: 12px; height: 12px; margin-left: 4px; }

#homePage { background: #dedfe3; }
#homeBanner {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #d6d7da,stop:0.45 #ddd7c6,stop:1 #c9901d);
    border: 1px solid #b8b1a2; border-radius: 8px;
}
QLabel#homeHeading { background: transparent; font-size: 20pt; font-weight: 700; color: #2b2b2b; }
QLabel#homeSubheading { background: transparent; font-size: 12pt; color: #303030; }
QFrame#homeSection { background: #f7f7f9; border: 1px solid #c7cad1; border-radius: 7px; }
QLabel#homeSectionTitle { background: transparent; font-size: 10pt; font-weight: 700; }
QToolButton#homeQuickButton {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #fbfbfc,stop:1 #e4e5e9);
    border: 1px solid #c4c7ce; border-radius: 8px; padding: 8px;
}
QToolButton#homeQuickButton:hover { background: #edf3fa; border-color: #8daecc; }
QToolButton#recentProjectButton { background: transparent; border: 0; text-align: left; padding: 4px; }
QToolButton#recentProjectButton:hover { background: #e7eef7; }

#consoleHeader { background: #eceef2; border-bottom: 1px solid #c4c8cf; }
#consoleEditor { background: #fffdf6; border: 0; font-family: Consolas, monospace; font-size: 8pt; }
#consoleTabs::tab { background: transparent; border: 0; border-bottom: 2px solid transparent; padding: 4px 8px; font-size: 8pt; }
#consoleTabs::tab:selected { color: #1f5f96; border-bottom: 2px solid #2e75b6; }
QToolButton#consoleToolButton { background: transparent; border: 1px solid transparent; border-radius: 2px; padding: 2px; }
QToolButton#consoleToolButton:hover { background: #dce3eb; border-color: #b9c2cc; }

QStatusBar { background: #e4e6ea; border-top: 1px solid #bdc1c8; color: #202020; }
QStatusBar QLabel { background: transparent; color: #202020; padding: 0 5px; }
QStatusBar::item { border: 0; }
QProgressBar { background: #f4f5f7; border: 1px solid #b8bdc5; border-radius: 2px; text-align: center; font-size: 7pt; }
QProgressBar::chunk { background: #53b45e; }
QSplitter::handle { background: #c3c6cc; }
QSplitter::handle:hover { background: #9ca4ae; }

/* 2026 usability upgrade */
QTabBar#ribbonTabs::tab { border-top: 3px solid transparent; font-weight: 600; }
QTabBar#ribbonTabs::tab:selected { border-top: 3px solid #D39B24; background:#FFFFFF; }
QTabBar#ribbonTabs::tab:hover:!selected { background:#E8F1F8; border-top:3px solid #88AFC8; }
#homeBanner { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #0B526F,stop:0.55 #176D8A,stop:1 #B27A1F); min-height:105px; }
QLabel#homeHeading { color:#FFFFFF; font-size:24pt; }
QLabel#homeSubheading { color:#E8F5FB; font-size:10pt; }
QToolButton#homeBannerAction { background:rgba(255,255,255,32); color:#FFFFFF; border:1px solid rgba(255,255,255,100); border-radius:6px; padding:8px 12px; font-weight:700; }
QToolButton#homeBannerAction:hover { background:rgba(255,255,255,65); }
QToolButton#homeFeatureCard { background:#FFFFFF; border:1px solid #C5D2DC; border-radius:9px; padding:10px; text-align:center; font-weight:700; }
QToolButton#homeFeatureCard:hover { background:#EDF6FB; border-color:#5A9FC7; }
QFrame#homeWorkflowStrip { background:#163A50; border-radius:7px; }
QLabel#homeWorkflowStep { color:#FFFFFF; background:transparent; font-weight:600; padding:5px; }
QWidget#featureInspector { background:#F7FAFC; }
QLabel#featureInspectorTitle { color:#0B5D8A; font-size:14pt; font-weight:800; padding:4px 0 8px 0; }
QLabel#featureInspectorHeading { color:#8A6410; font-size:9pt; font-weight:800; }
QLabel#featureInspectorText { color:#263744; font-size:8pt; }
QFrame#geometryMapBar { background:#E8F0F5; border:1px solid #B8C9D4; border-radius:5px; }
QLabel#geometryMapStats { background:#102D40; color:#D9EDF8; border-radius:4px; padding:7px; font-family:Consolas; }
"""
# ---------------------------------------------------------------------------
# Workstation shell overrides — compact dark category strip + neutral canvas
# ---------------------------------------------------------------------------
STYLESHEET += r"""
QMainWindow { background:#6F6F6F; }
QWidget#centralWorkspaceHost, QWidget#centralWorkspaceStack { background:#6F6F6F; }
QWidget#emptyWorkspace { background:#6F6F6F; }
QLabel#workspaceWatermark { background:transparent; opacity:0.35; }
QLabel#workspaceWatermarkText {
    background:transparent; color:#9B9B9B; font-size:34pt; font-weight:700;
}

#titleBar {
    background:#F5F5F5;
    border-bottom:1px solid #B8B8B8;
}
#titleBar QLabel { color:#222222; }
#appGlyph { background:#D7A51A; border-color:#B98708; border-radius:2px; }

#ribbonContainer { background:#F1F1F1; border-bottom:1px solid #AFAFAF; }
#ribbonHeader { background:#333333; min-height:28px; max-height:34px; }
QToolButton#ribbonFileButton {
    background:#E9A91B; color:#171717; border:0; border-radius:0;
    padding:6px 17px; font-size:9pt; font-weight:500;
}
QToolButton#ribbonFileButton:hover { background:#F3BD3E; }
QToolButton#ribbonFileButton::menu-indicator { image:none; }
QTabBar#ribbonTabs { background:#333333; border:0; }
QTabBar#ribbonTabs::tab {
    background:#333333; color:#F2F2F2; border:0; border-radius:0;
    border-top:0; padding:6px 14px; margin:0; min-height:20px;
    font-size:8.5pt; font-weight:400;
}
QTabBar#ribbonTabs::tab:hover:!selected { background:#454545; color:#FFFFFF; border:0; }
QTabBar#ribbonTabs::tab:selected {
    background:#F4F4F4; color:#1F1F1F; border:0; font-weight:500;
}
#ribbonSubHeader { background:#E7E7E7; border-bottom:1px solid #C5C5C5; }
QTabBar#ribbonSubTabs { background:#E7E7E7; border:0; }
QTabBar#ribbonSubTabs::tab {
    background:#E7E7E7; color:#374151; border:0; border-bottom:3px solid transparent;
    padding:5px 13px 4px 13px; margin-right:1px; min-height:18px; font-size:8.5pt; font-weight:500;
}
QTabBar#ribbonSubTabs::tab:hover:!selected { background:#DCE7EF; color:#123C54; }
QTabBar#ribbonSubTabs::tab:selected {
    background:#F4F4F4; color:#0B5F8A; border-bottom:3px solid #D39B24; font-weight:700;
}
#ribbonGroupsBackground { background:#F4F4F4; }
#ribbonGroupsContainer {
    background:#F4F4F4; border:0; border-bottom:1px solid #BDBDBD; border-radius:0;
}
QFrame#ribbonSeparator { background:#C8C8C8; margin:6px 3px 19px 3px; }
QToolButton#ribbonLargeAction, QToolButton#ribbonSmallAction {
    color:#242424; border-radius:1px; background:transparent;
}
QToolButton#ribbonLargeAction:hover, QToolButton#ribbonSmallAction:hover {
    background:#E3E9EF; border-color:#AAB8C5;
}
QLabel#ribbonGroupLabel { color:#5C5C5C; font-size:7pt; }

QDockWidget { background:#FFFFFF; border:1px solid #8F8F8F; }
QWidget#dockTitleBar {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #F3C12F,stop:1 #D9A414);
    border-top:1px solid #FFE17A; border-bottom:1px solid #9B7710;
}
QLabel#dockTitleLabel { color:#202020; font-size:8.5pt; font-weight:700; }
QToolButton#dockTitleButton, QToolButton#dockCloseButton { border-radius:0; }
QToolButton#dockTitleButton:hover { background:#F6D969; border-color:#A98214; }
QToolButton#dockCloseButton:hover { background:#D9534F; border-color:#A5332F; }

QTreeWidget, QTreeView, QTableView, QListWidget, QListView {
    background:#FFFFFF; border:0; alternate-background-color:#FBFBFB;
}
QTreeWidget::item:selected, QTreeView::item:selected,
QListWidget::item:selected, QListView::item:selected { background:#D7E8F8; color:#111111; }

QTabWidget#documentTabs::pane { background:#6F6F6F; border:0; top:-1px; }
QTabBar#documentTabBar { background:#D8D8D8; border-bottom:1px solid #A0A0A0; }
QTabBar#documentTabBar::tab {
    background:#D8D8D8; color:#222; border:1px solid #AFAFAF; border-bottom:0;
    padding:4px 11px; min-height:20px; margin-right:1px; font-size:8pt;
}
QTabBar#documentTabBar::tab:selected { background:#F3F3F3; border-top:2px solid #D4A11B; }

QStatusBar { background:#E6E6E6; border-top:1px solid #AFAFAF; min-height:20px; }
QStatusBar QLabel { color:#252525; }
"""

# ---------------------------------------------------------------------------
# Global form-control visibility override
# Keep checked radio buttons visible on white/gray dialogs across the software.
# ---------------------------------------------------------------------------
STYLESHEET += r"""
QRadioButton {
    spacing: 6px;
    background: transparent;
    color: #252525;
}
QRadioButton::indicator {
    width: 14px;
    height: 14px;
    border-radius: 7px;
    border: 1px solid #4F5963;
    background: #FFFFFF;
}
QRadioButton::indicator:unchecked:hover {
    border: 1px solid #0B5F8A;
    background: #F3FAFF;
}
QRadioButton::indicator:checked {
    border: 2px solid #0B5F8A;
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.65, fx:0.5, fy:0.5,
                                stop:0 #0B5F8A, stop:0.43 #0B5F8A,
                                stop:0.46 #FFFFFF, stop:1 #FFFFFF);
}
QRadioButton::indicator:checked:hover {
    border: 2px solid #064F75;
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.65, fx:0.5, fy:0.5,
                                stop:0 #064F75, stop:0.43 #064F75,
                                stop:0.46 #FFFFFF, stop:1 #FFFFFF);
}
QRadioButton::indicator:disabled {
    border: 1px solid #A8AEB5;
    background: #E6E8EB;
}
QRadioButton::indicator:checked:disabled {
    border: 2px solid #8D99A3;
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.65, fx:0.5, fy:0.5,
                                stop:0 #8D99A3, stop:0.43 #8D99A3,
                                stop:0.46 #E6E8EB, stop:1 #E6E8EB);
}
"""
