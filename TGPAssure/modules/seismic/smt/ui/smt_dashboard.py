from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from modules.seismic.smt import SmtProjectDatabase
from modules.seismic.smt.ui.dialogs import (
    ConfigurationDialog,
    ImportRecordsDialog,
    MaintenanceDialog,
    PendingRetestsDialog,
    ProjectSelectionDialog,
    RecordsDialog,
    ResultsDialog,
    SingleStringDialog,
    StatisticsDialog,
    TimeAnalysisDialog,
    UnseenStringsDialog,
    UtilitiesDialog,
)


# Compact SMTAN2-inspired desktop theme.  Every text-bearing widget receives an
# explicit foreground/background so TGPAssure's application-wide stylesheet
# cannot produce white-on-white labels or oversized inherited typography.
_COMPACT_DASHBOARD_QSS = """
QWidget#smtDashboard {
    background:#EEF3F6;
    color:#142536;
    font-family: Arial, Helvetica, sans-serif;
    font-size:8pt;
}
QWidget#smtDashboard QLabel { background:transparent; color:#142536; }
QFrame#classicWindow {
    background:#F5F8FA;
    border:1px solid #B4C3CD;
    border-radius:7px;
}
QFrame#classicTitleBar {
    min-height:30px;
    max-height:34px;
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #082B45, stop:0.55 #0D7190, stop:1 #1E9CB4);
    border:0;
    border-radius:6px;
}
QLabel#classicTitle {
    background:transparent;
    color:#FFFFFF;
    font-size:10pt;
    font-weight:900;
}
QFrame#launcherPanel {
    background:#E7EEF3;
    border:1px solid #BCD0DB;
    border-radius:6px;
}
QPushButton#launcherButton {
    min-height:44px;
    max-height:46px;
    padding:3px 8px;
    border:1px solid #B4C5CF;
    border-radius:5px;
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #FFFFFF, stop:1 #E1EBF1);
    color:#172A39;
    font-size:8pt;
    font-weight:750;
    text-align:left;
}
QPushButton#launcherButton:hover { background:#E7F7FC; border-color:#5CA8C4; }
QPushButton#launcherButton:pressed { background:#CCE3EE; border-color:#2F7F9B; }
QPushButton#launcherButton:disabled { background:#E2E8EC; border-color:#C5CFD6; color:#7B8790; }
QPushButton#exitButton {
    min-height:44px;
    max-height:46px;
    padding:3px 8px;
    border:1px solid #C8A9A9;
    border-radius:5px;
    background:#FFF0F0;
    color:#8B2222;
    font-size:8pt;
    font-weight:800;
    text-align:left;
}
QPushButton#exitButton:hover { background:#F8DDDD; border-color:#B56A6A; }
QFrame#displayPanel {
    background:#FFFFFF;
    border:1px solid #BCD0DB;
    border-radius:6px;
}
QLabel#projectName {
    min-height:30px;
    max-height:34px;
    background:#E7F4FB;
    color:#0A4A6C;
    border:1px solid #9BC2D6;
    border-radius:5px;
    padding:2px 8px;
    font-size:11pt;
    font-weight:850;
}
QLabel#moduleHeading {
    min-height:28px;
    max-height:32px;
    background:#EDF8F0;
    color:#246B39;
    border:1px solid #B2D1BA;
    border-radius:5px;
    padding:1px 6px;
    font-size:12pt;
    font-weight:850;
}
QFrame#metricCard {
    background:#FFFFFF;
    border:1px solid #D2DDE5;
    border-radius:6px;
}
QFrame#metricCard[tone="blue"] { border-left:5px solid #1785B3; background:#F3FAFE; }
QFrame#metricCard[tone="purple"] { border-left:5px solid #7156B8; background:#F8F5FE; }
QFrame#metricCard[tone="green"] { border-left:5px solid #2B9961; background:#F2FBF6; }
QFrame#metricCard[tone="red"] { border-left:5px solid #C64A55; background:#FFF5F6; }
QLabel#metricCaption { color:#536777; font-size:7.5pt; font-weight:750; }
QLabel#metricValue { color:#123D5A; font-size:16pt; font-weight:900; }
QLabel#metricSubValue { color:#6B3A3F; font-size:7pt; font-weight:650; }
QFrame#infoCard {
    background:#EFF7FB;
    border:1px solid #BED4E0;
    border-radius:6px;
}
QLabel#infoTitle { color:#0E547B; font-size:9.3pt; font-weight:850; }
QLabel#infoText { color:#344956; font-size:7.7pt; }
QFrame#readyPanel {
    background:#EDF8F0;
    border:1px solid #B2D1BA;
    border-radius:6px;
}
QLabel#ready { color:#28713C; font-size:13pt; font-weight:900; }
QLabel#buildLabel { color:#667581; font-size:7pt; }
QLabel#statusLine {
    min-height:22px;
    max-height:25px;
    background:#E3ECF2;
    color:#263743;
    border:1px solid #B7C5CE;
    border-radius:4px;
    padding:1px 7px;
    font-size:7.7pt;
    font-weight:650;
}
QToolTip { background:#FFFBE6; color:#16212A; border:1px solid #9A8F56; padding:3px; }
"""


class SmtDashboard(QWidget):
    """Compact SMTAN2-style launcher integrated into the Seismic workspace."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("smtDashboard")
        self.setStyleSheet(_COMPACT_DASHBOARD_QSS)
        self.database: SmtProjectDatabase | None = None
        self._build_ui()
        self._update_state()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(3, 3, 3, 3)
        root.setSpacing(0)

        window = QFrame()
        window.setObjectName("classicWindow")
        window_layout = QVBoxLayout(window)
        window_layout.setContentsMargins(3, 3, 3, 3)
        window_layout.setSpacing(3)

        title_bar = QFrame()
        title_bar.setObjectName("classicTitleBar")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(7, 1, 7, 1)
        title = QLabel("SMTAN2 — SMT Results Database")
        title.setObjectName("classicTitle")
        title.setStyleSheet("background: transparent; color: #FFFFFF; font-weight: 900;")
        title_layout.addWidget(title)
        title_layout.addStretch(1)
        window_layout.addWidget(title_bar)

        body = QHBoxLayout()
        body.setSpacing(5)
        body.addWidget(self._build_launcher_panel())
        body.addWidget(self._build_display_panel(), 1)
        window_layout.addLayout(body, 1)

        self.status_line = QLabel("Ready")
        self.status_line.setObjectName("statusLine")
        self.status_line.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        window_layout.addWidget(self.status_line)
        root.addWidget(window, 1)

    def _launcher_button(
        self,
        text: str,
        icon: QStyle.StandardPixmap,
        callback,
        *,
        tooltip: str,
    ) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("launcherButton")
        button.setIcon(self.style().standardIcon(icon))
        button.setIconSize(QSize(24, 24))
        button.setToolTip(tooltip)
        button.clicked.connect(callback)
        return button

    def _build_launcher_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("launcherPanel")
        panel.setFixedWidth(208)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(3)

        self.project_button = self._launcher_button(
            "New/Select Project",
            QStyle.StandardPixmap.SP_DriveHDIcon,
            self.new_select_project,
            tooltip="Create a new SMT database or open an existing project.",
        )
        self.import_button = self._launcher_button(
            "Add Records",
            QStyle.StandardPixmap.SP_FileDialogNewFolder,
            self.add_records,
            tooltip="Import SMT200, SMT300, SMT400 or SGT-II result exports.",
        )
        self.config_button = self._launcher_button(
            "Configure Limits",
            QStyle.StandardPixmap.SP_DirIcon,
            self.configure,
            tooltip="Set test limits, project details, colours and date handling.",
        )
        self.results_button = self._launcher_button(
            "Show Results",
            QStyle.StandardPixmap.SP_FileDialogContentsView,
            self.show_results,
            tooltip="Query records and display histograms, scatter plots and cross plots.",
        )
        self.utilities_button = self._launcher_button(
            "Utilities",
            QStyle.StandardPixmap.SP_ComputerIcon,
            self.show_utilities,
            tooltip="Open statistics, time analysis, maintenance, unseen strings and retests.",
        )
        self.exit_button = self._launcher_button(
            "Exit / Close SMT",
            QStyle.StandardPixmap.SP_DialogCloseButton,
            self.close,
            tooltip="Close the SMT Results Database tab.",
        )
        self.exit_button.setObjectName("exitButton")

        for button in (
            self.project_button,
            self.import_button,
            self.config_button,
            self.results_button,
            self.utilities_button,
            self.exit_button,
        ):
            layout.addWidget(button)
        layout.addStretch(1)
        return panel

    def _metric_card(self, caption: str, tone: str) -> tuple[QFrame, QLabel, QLabel]:
        frame = QFrame()
        frame.setObjectName("metricCard")
        frame.setProperty("tone", tone)
        frame.setMinimumHeight(60)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(7, 4, 6, 4)
        layout.setSpacing(0)

        caption_label = QLabel(caption)
        caption_label.setObjectName("metricCaption")
        value_label = QLabel("0")
        value_label.setObjectName("metricValue")
        value_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        sub_label = QLabel("")
        sub_label.setObjectName("metricSubValue")
        sub_label.setMinimumHeight(11)

        layout.addWidget(caption_label)
        layout.addWidget(value_label, 1)
        layout.addWidget(sub_label)
        return frame, value_label, sub_label

    def _build_display_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("displayPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(5)

        self.project_name = QLabel("No SMT Project Selected")
        self.project_name.setObjectName("projectName")
        self.project_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.project_name)

        self.logo_label = QLabel()
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo_label.setMaximumHeight(38)
        self.logo_label.setVisible(False)
        layout.addWidget(self.logo_label)

        heading = QLabel("SMT200  /  SMT300  /  SMT400  /  SGT-II")
        heading.setObjectName("moduleHeading")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(heading)

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(5)
        metrics.setVerticalSpacing(5)

        record_card, self.record_count, record_sub = self._metric_card("Database Records", "blue")
        unique_card, self.unique_value, unique_sub = self._metric_card("Unique Strings", "purple")
        pass_card, self.pass_value, pass_sub = self._metric_card("Passed", "green")
        fail_card, self.fail_value, self.pending_value = self._metric_card("Failed", "red")
        record_sub.setText("All imported tests")
        unique_sub.setText("Distinct string numbers")
        pass_sub.setText("Within configured limits")
        self.pending_value.setText("Pending retests: 0")

        metrics.addWidget(record_card, 0, 0)
        metrics.addWidget(unique_card, 0, 1)
        metrics.addWidget(pass_card, 0, 2)
        metrics.addWidget(fail_card, 0, 3)
        for column in range(4):
            metrics.setColumnStretch(column, 1)
        layout.addLayout(metrics)

        info_card = QFrame()
        info_card.setObjectName("infoCard")
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(9, 5, 9, 5)
        info_layout.setSpacing(3)
        info_title = QLabel("True Database Storage and Display for SMT Results")
        info_title.setObjectName("infoTitle")
        info_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_layout.addWidget(info_title)
        info = QLabel(
            "SQLite project storage • result imports • histograms • scatter plots • cross plots • "
            "statistics • single-string analysis • time analysis • unseen strings • pending retests"
        )
        info.setObjectName("infoText")
        info.setWordWrap(True)
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_layout.addWidget(info)
        layout.addWidget(info_card)
        layout.addStretch(1)

        ready_panel = QFrame()
        ready_panel.setObjectName("readyPanel")
        ready_layout = QHBoxLayout(ready_panel)
        ready_layout.setContentsMargins(8, 2, 8, 2)
        self.ready_label = QLabel("Ready")
        self.ready_label.setObjectName("ready")
        self.ready_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ready_layout.addStretch(1)
        ready_layout.addWidget(self.ready_label)
        ready_layout.addStretch(1)
        layout.addWidget(ready_panel)

        self.build_label = QLabel("TGPAssure SMT module — SMTAN2-compatible workflow")
        self.build_label.setObjectName("buildLabel")
        self.build_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.build_label)
        return panel

    def _require_database(self) -> SmtProjectDatabase | None:
        if self.database is None:
            QMessageBox.information(self, "SMTAN2", "Create or select an SMT project first.")
            return None
        return self.database

    def new_select_project(self) -> None:
        dialog = ProjectSelectionDialog(self)
        if dialog.exec() != ProjectSelectionDialog.DialogCode.Accepted or dialog.selected_path is None:
            return
        self._open_database(dialog.selected_path)

    def _open_database(self, path: Path) -> None:
        if self.database is not None:
            try:
                self.database.close()
            except Exception:
                pass
        self.database = SmtProjectDatabase(path)
        self.status_line.setText(f"Project opened: {path}")
        self._apply_branding()
        self._update_state()

    def add_records(self) -> None:
        database = self._require_database()
        if database is None:
            return
        self.ready_label.setText("Working…")
        dialog = ImportRecordsDialog(database, self)
        dialog.exec()
        self.ready_label.setText("Ready")
        self._update_state()

    def configure(self) -> None:
        database = self._require_database()
        if database is None:
            return
        if ConfigurationDialog(database, self).exec() == ConfigurationDialog.DialogCode.Accepted:
            self.status_line.setText("SMT limits and parameters saved; result statuses recalculated.")
            self._apply_branding()
            self._update_state()

    def show_records(self) -> None:
        database = self._require_database()
        if database is not None:
            RecordsDialog(database, self).exec()
            self._update_state()

    def show_results(self) -> None:
        database = self._require_database()
        if database is not None:
            ResultsDialog(database, self).exec()

    def show_statistics(self) -> None:
        database = self._require_database()
        if database is not None:
            StatisticsDialog(database, self).exec()

    def show_pending_retests(self) -> None:
        database = self._require_database()
        if database is not None:
            PendingRetestsDialog(database, self).exec()
            self._update_state()

    def show_utilities(self) -> None:
        database = self._require_database()
        if database is not None:
            UtilitiesDialog(database, self).exec()
            self._update_state()

    def show_single_string(self) -> None:
        database = self._require_database()
        if database is not None:
            SingleStringDialog(database, self).exec()

    def show_time_analysis(self) -> None:
        database = self._require_database()
        if database is not None:
            TimeAnalysisDialog(database, self).exec()

    def show_maintenance(self) -> None:
        database = self._require_database()
        if database is not None:
            MaintenanceDialog(database, self).exec()
            self._update_state()

    def show_unseen_strings(self) -> None:
        database = self._require_database()
        if database is not None:
            UnseenStringsDialog(database, self).exec()

    def open_pending_dialog(self) -> None:
        self.show_pending_retests()

    def export_records(self) -> None:
        database = self._require_database()
        if database is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export SMT Database Records",
            str(database.path.with_name(database.path.stem + "_records.csv")),
            "CSV (*.csv)",
        )
        if not path:
            return
        try:
            output = database.export_records_csv(path)
            self.status_line.setText(f"Records exported: {output}")
            QMessageBox.information(self, "SMTAN2", f"Records exported:\n{output}")
        except Exception as exc:
            QMessageBox.critical(self, "SMTAN2", f"Unable to export records:\n{exc}")

    def _apply_branding(self) -> None:
        self.logo_label.clear()
        self.logo_label.setVisible(False)
        if self.database is None:
            return
        config = self.database.load_configuration()
        path = Path(config.logo_path).expanduser() if config.logo_path else None
        if config.show_logo and path is not None and path.is_file():
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                self.logo_label.setPixmap(
                    pixmap.scaled(
                        300,
                        36,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                self.logo_label.setVisible(True)

    def _update_state(self) -> None:
        enabled = self.database is not None
        for button in (self.import_button, self.config_button, self.results_button, self.utilities_button):
            button.setEnabled(enabled)
        if self.database is None:
            self.project_name.setText("No SMT Project Selected")
            self.record_count.setText("0")
            self.unique_value.setText("0")
            self.pass_value.setText("0")
            self.fail_value.setText("0")
            self.pending_value.setText("Pending retests: 0")
            self.ready_label.setText("Ready")
            self.status_line.setText("Ready — select or create an SMT project")
            return
        stats = self.database.statistics()
        pending = len(self.database.pending_retests())
        self.project_name.setText(self.database.project_name)
        self.record_count.setText(f"{stats['total_records']:,}")
        self.unique_value.setText(f"{stats['total_unique_strings']:,}")
        self.pass_value.setText(f"{stats['total_good']:,}")
        self.fail_value.setText(f"{stats['total_failures']:,}")
        self.pending_value.setText(f"Pending retests: {pending:,}")
        self.ready_label.setText("Ready")
        self._apply_branding()

    def can_execute(self, action_id: str) -> bool:
        if action_id in {"smt_project", "smt_open_project"}:
            return True
        if self.database is None:
            return False
        if action_id in {
            "smt_results",
            "smt_statistics",
            "smt_pending",
            "smt_export_records",
            "smt_single_string",
            "smt_time_analysis",
            "smt_records",
            "smt_unseen",
        }:
            return self.database.record_count() > 0
        return True

    def closeEvent(self, event) -> None:
        if self.database is not None:
            try:
                self.database.close()
            except Exception:
                pass
            self.database = None
        super().closeEvent(event)
