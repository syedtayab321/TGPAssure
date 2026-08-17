import hashlib
import sys
import json
from pathlib import Path
from PySide6.QtCore import QIODevice, QObject, Qt, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog
from PySide6.QtGui import QIcon

from core.data_access.db_engine import DatabaseEngine
from core.data_access.project_repository import ProjectRepository
from core.data_access.layout_store import LayoutStore
from core.data_access.file_manager import FileManager, FormatDescriptor
from core.infrastructure.service_container import ServiceContainer
from core.infrastructure.job_manager import JobManager
from core.infrastructure.crash_handler import CrashHandler
from core.infrastructure.logging_configurator import LoggingConfigurator
from core.infrastructure.settings_store import SettingsStore
from core.infrastructure.command_bus import CommandBus
from core.infrastructure.resource_paths import resource_path
from core.auth import AuthEnvironment, LicenseService
from modules.workspace.workspace_manager import WorkspaceManager
from ui.main_window import MainWindow
from ui.ribbon.segd_ribbon import SegdRibbonProvider
from ui.ribbon.home_ribbon import HomeRibbonProvider
from core.domain.processing_history import ProcessingHistoryManager
from core.infrastructure.task_scheduler import TaskScheduler
from modules.collaboration.collaboration_service import CollaborationService
from core.domain.data_quality_service import DataQualityService
from ui.launch import StartupSplash, TutorialDialog
from ui.dialogs.auth_dialog import AuthDialog
from ui.dialogs.subscription_dialog import SubscriptionDialog
from ui.spinbox_cursor_fix import install_spinbox_cursor_fix



class SingleInstanceController(QObject):
    file_received = Signal(str)
    activate_requested = Signal()

    def __init__(self, server_name: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.server_name = server_name
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._accept_connections)
        self._buffers: dict[QLocalSocket, bytearray] = {}
        self._owns_server = False

    def forward_to_existing(self, file_paths: list[Path]) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self.server_name, QIODevice.WriteOnly)
        if not socket.waitForConnected(350):
            socket.abort()
            return False
        payload = json.dumps(
            {
                "activate": True,
                "files": [str(path) for path in file_paths],
            }
        ).encode("utf-8")
        socket.write(payload)
        socket.flush()
        socket.waitForBytesWritten(750)
        socket.disconnectFromServer()
        return True

    def start(self) -> None:
        QLocalServer.removeServer(self.server_name)
        if not self.server.listen(self.server_name):
            raise RuntimeError(f"Unable to start the TGPAssure local server: {self.server.errorString()}")
        self._owns_server = True

    def close(self) -> None:
        if not self._owns_server:
            return
        self.server.close()
        QLocalServer.removeServer(self.server_name)
        self._owns_server = False

    def _accept_connections(self) -> None:
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            if socket is None:
                continue
            self._buffers[socket] = bytearray()
            socket.readyRead.connect(lambda current=socket: self._read_socket(current))
            socket.disconnected.connect(lambda current=socket: self._finish_socket(current))
            self._read_socket(socket)

    def _read_socket(self, socket: QLocalSocket) -> None:
        buffer = self._buffers.get(socket)
        if buffer is None:
            return
        buffer.extend(bytes(socket.readAll()))

    def _finish_socket(self, socket: QLocalSocket) -> None:
        self._read_socket(socket)
        payload = bytes(self._buffers.pop(socket, bytearray()))
        socket.deleteLater()
        if not payload:
            self.activate_requested.emit()
            return
        try:
            message = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.activate_requested.emit()
            return
        if bool(message.get("activate", True)):
            self.activate_requested.emit()
        files = message.get("files", [])
        if isinstance(files, list):
            for value in files:
                if isinstance(value, str) and value.strip():
                    self.file_received.emit(value)


def _startup_seismic_paths(arguments: list[str]) -> list[Path]:
    supported = {".sgy", ".segy", ".segd", ".sgd", ".d", ".dat"}
    paths: list[Path] = []
    for argument in arguments[1:]:
        try:
            path = Path(argument.strip('"')).expanduser().resolve()
        except (OSError, RuntimeError):
            continue
        if path.is_file() and path.suffix.lower() in supported:
            paths.append(path)
    return paths


def _single_instance_name() -> str:
    identity = str(Path.home().expanduser().resolve()).casefold().encode("utf-8", errors="ignore")
    digest = hashlib.sha1(identity).hexdigest()[:16]
    return f"TGPAssure_{digest}"

def setup_app_data_dir() -> Path:
    app_data_dir = Path.home() / ".tgpassure"
    app_data_dir.mkdir(parents=True, exist_ok=True)
    return app_data_dir


def setup_database(app_data_dir: Path) -> DatabaseEngine:
    db_path = app_data_dir / "tgpassure.db"
    return DatabaseEngine(db_path)


def initialize_database(db_engine: DatabaseEngine) -> None:
    conn = db_engine.get_write_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS project (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                project_uuid TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                description TEXT,
                module TEXT NOT NULL DEFAULT 'general',
                status TEXT NOT NULL DEFAULT 'active',
                root_path TEXT,
                database_path TEXT,
                schema_version INTEGER NOT NULL DEFAULT 0 CHECK (schema_version >= 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_opened_at TEXT
            )
        """)
        conn.execute("""
            INSERT OR IGNORE INTO project (id, project_uuid, name, schema_version)
            VALUES (1, '00000000-0000-0000-0000-000000000001', 'Default Project', 0)
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS project_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL DEFAULT 1,
                file_uuid TEXT NOT NULL UNIQUE,
                module TEXT NOT NULL,
                file_role TEXT NOT NULL,
                original_name TEXT NOT NULL,
                display_name TEXT NOT NULL,
                absolute_path TEXT,
                relative_path TEXT,
                extension TEXT,
                mime_type TEXT,
                size_bytes INTEGER NOT NULL DEFAULT 0 CHECK (size_bytes >= 0),
                sha256 TEXT,
                status TEXT NOT NULL DEFAULT 'available',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_verified_at TEXT,
                FOREIGN KEY (project_id) REFERENCES project(id) ON DELETE CASCADE,
                UNIQUE (project_id, absolute_path)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL DEFAULT 1,
                file_id INTEGER,
                job_uuid TEXT NOT NULL UNIQUE,
                job_type TEXT NOT NULL,
                module TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                priority INTEGER NOT NULL DEFAULT 0,
                progress REAL NOT NULL DEFAULT 0.0 CHECK (progress >= 0.0 AND progress <= 1.0),
                message TEXT,
                payload_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT,
                error_text TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                started_at TEXT,
                finished_at TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES project(id) ON DELETE CASCADE,
                FOREIGN KEY (file_id) REFERENCES project_files(id) ON DELETE SET NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS qc_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL DEFAULT 1,
                file_id INTEGER,
                job_id INTEGER,
                run_uuid TEXT NOT NULL UNIQUE,
                module TEXT NOT NULL,
                qc_profile TEXT NOT NULL,
                profile_version TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                overall_result TEXT NOT NULL DEFAULT 'pending',
                score REAL,
                assigned_to TEXT,
                assignment_history_json TEXT NOT NULL DEFAULT '[]',
                parameters_json TEXT NOT NULL DEFAULT '{}',
                summary_json TEXT NOT NULL DEFAULT '{}',
                started_at TEXT,
                completed_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES project(id) ON DELETE CASCADE,
                FOREIGN KEY (file_id) REFERENCES project_files(id) ON DELETE CASCADE,
                FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE SET NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS qc_stage_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                qc_run_id INTEGER NOT NULL,
                stage_key TEXT NOT NULL,
                stage_name TEXT NOT NULL,
                stage_order INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                result TEXT NOT NULL DEFAULT 'pending',
                score REAL,
                metrics_json TEXT NOT NULL DEFAULT '{}',
                message TEXT,
                started_at TEXT,
                completed_at TEXT,
                duration_ms INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0),
                FOREIGN KEY (qc_run_id) REFERENCES qc_runs(id) ON DELETE CASCADE,
                UNIQUE (qc_run_id, stage_key)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS qc_findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                qc_run_id INTEGER NOT NULL,
                stage_result_id INTEGER,
                file_id INTEGER,
                finding_code TEXT NOT NULL,
                severity TEXT NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                metric_name TEXT,
                observed_value REAL,
                expected_min REAL,
                expected_max REAL,
                unit TEXT,
                station_id TEXT,
                line_id TEXT,
                sample_index INTEGER,
                timestamp_utc TEXT,
                location_x REAL,
                location_y REAL,
                location_z REAL,
                crs TEXT,
                context_json TEXT NOT NULL DEFAULT '{}',
                is_resolved INTEGER NOT NULL DEFAULT 0 CHECK (is_resolved IN (0, 1)),
                resolution_note TEXT,
                resolved_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (qc_run_id) REFERENCES qc_runs(id) ON DELETE CASCADE,
                FOREIGN KEY (stage_result_id) REFERENCES qc_stage_results(id) ON DELETE SET NULL,
                FOREIGN KEY (file_id) REFERENCES project_files(id) ON DELETE SET NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS layout_store (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                layout_data BLOB,
                tabs_json TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            INSERT OR IGNORE INTO layout_store (id, layout_data, tabs_json)
            VALUES (1, NULL, '[]')
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS project_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL DEFAULT 1,
                setting_key TEXT NOT NULL,
                setting_value TEXT NOT NULL,
                value_type TEXT NOT NULL DEFAULT 'string',
                scope TEXT NOT NULL DEFAULT 'project',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES project(id) ON DELETE CASCADE,
                UNIQUE (project_id, setting_key, scope)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS recent_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_path TEXT NOT NULL UNIQUE,
                project_name TEXT NOT NULL,
                last_opened TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                open_count INTEGER NOT NULL DEFAULT 1
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL DEFAULT 1,
                qc_run_id INTEGER,
                processing_run_id INTEGER,
                report_uuid TEXT NOT NULL UNIQUE,
                report_type TEXT NOT NULL,
                title TEXT NOT NULL,
                format TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                file_path TEXT,
                sha256 TEXT,
                template_name TEXT,
                template_version TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                generated_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES project(id) ON DELETE CASCADE,
                FOREIGN KEY (qc_run_id) REFERENCES qc_runs(id) ON DELETE SET NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL DEFAULT 1,
                file_id INTEGER,
                module TEXT NOT NULL,
                bookmark_type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                target_json TEXT NOT NULL DEFAULT '{}',
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES project(id) ON DELETE CASCADE,
                FOREIGN KEY (file_id) REFERENCES project_files(id) ON DELETE SET NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS log_entries_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL DEFAULT 1,
                job_id INTEGER,
                qc_run_id INTEGER,
                processing_run_id INTEGER,
                level TEXT NOT NULL,
                logger_name TEXT NOT NULL,
                event_code TEXT,
                message TEXT NOT NULL,
                log_file_path TEXT,
                byte_offset INTEGER CHECK (byte_offset IS NULL OR byte_offset >= 0),
                byte_length INTEGER CHECK (byte_length IS NULL OR byte_length >= 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES project(id) ON DELETE CASCADE,
                FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE SET NULL,
                FOREIGN KEY (qc_run_id) REFERENCES qc_runs(id) ON DELETE SET NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                app_settings_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            INSERT OR IGNORE INTO settings (id, app_settings_json)
            VALUES (1, '{}')
        """)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_files_module ON project_files(module)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_qc_findings_severity ON qc_findings(severity)")

        conn.commit()
    finally:
        conn.close()


def setup_container(db_engine: DatabaseEngine, app_data_dir: Path, license_service: LicenseService | None = None) -> ServiceContainer:
    container = ServiceContainer()

    container.register(DatabaseEngine, db_engine)

    settings_store = SettingsStore(db_engine)
    container.register(SettingsStore, settings_store)

    layout_store = LayoutStore(db_engine)
    container.register(LayoutStore, layout_store)

    project_repo = ProjectRepository(db_engine)
    container.register(ProjectRepository, project_repo)

    file_manager = FileManager(project_repo)
    container.register(FileManager, file_manager)

    workspace_manager = WorkspaceManager(container)
    container.register(WorkspaceManager, workspace_manager)

    job_manager = JobManager(db_engine)
    container.register(JobManager, job_manager)

    # Processing history manager (records processing runs)
    processing_history = ProcessingHistoryManager(db_engine)
    container.register(ProcessingHistoryManager, processing_history)

    # Lightweight in-process task scheduler
    task_scheduler = TaskScheduler()
    container.register(TaskScheduler, task_scheduler)

    # attach scheduler to job manager so jobs can be scheduled
    try:
        job_manager.set_task_scheduler(task_scheduler)
    except Exception:
        pass

    # Collaboration helper (creates shared archives)
    collaboration = CollaborationService(app_data_dir)
    container.register(CollaborationService, collaboration)

    # Data quality service
    dq_service = DataQualityService(db_engine)
    container.register(DataQualityService, dq_service)

    command_bus = CommandBus()
    container.register(CommandBus, command_bus)

    if license_service is not None:
        container.register(LicenseService, license_service)

    return container



def main() -> int:
    app_data_dir = setup_app_data_dir()

    crash_handler = CrashHandler(app_data_dir / "logs")
    crash_handler.install()

    logging_configurator = LoggingConfigurator(app_data_dir / "logs")
    logging_configurator.configure()
    logger = logging_configurator.get_logger("tgpassure")

    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    install_spinbox_cursor_fix(app)
    app.setApplicationName("TGPAssure")
    app.setOrganizationName("TGP")
    app.setApplicationVersion("0.2.0")
    icon_path = resource_path("assets", "logo", "logo.ico")
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))

    startup_paths = _startup_seismic_paths(sys.argv)
    single_instance = SingleInstanceController(_single_instance_name(), app)
    if single_instance.forward_to_existing(startup_paths):
        return 0
    try:
        single_instance.start()
    except RuntimeError:
        if single_instance.forward_to_existing(startup_paths):
            return 0

    auth_env = AuthEnvironment.load(Path(__file__).resolve().parent, app_data_dir)
    license_service = LicenseService(app_data_dir, auth_env)
    show_subscription_after_login = False
    if not license_service.try_auto_login():
        auth_dialog = AuthDialog(license_service)
        if auth_dialog.exec() != AuthDialog.Accepted:
            single_instance.close()
            crash_handler.uninstall()
            logger.info("Application exited before login")
            return 0
        show_subscription_after_login = license_service.current_plan == "free"

    splash = StartupSplash()
    splash.show()
    splash.set_stage('Opening secure workspace…')
    app.processEvents()

    logger.info("Starting TGPAssure application")

    db_engine = setup_database(app_data_dir)
    splash.set_stage('Initializing project database…')
    app.processEvents()
    initialize_database(db_engine)
    container = setup_container(db_engine, app_data_dir, license_service)

    main_window = MainWindow(container)
    splash.set_stage('Loading quality-control tools…')
    app.processEvents()

    job_manager = container.resolve(JobManager)

    def handle_file_import(file_path: str) -> None:
        try:
            main_window.open_imported_file(file_path)
        except Exception as exc:
            logger.exception("Failed to open imported file")
            QMessageBox.critical(main_window, "Open Error", f"Failed to open file:\n{file_path}\n\n{exc}")

    main_window.file_imported.connect(handle_file_import)

    def open_file_from_explorer(file_uuid: str) -> None:
        managed_path = workspace_manager.resolve_project_file_path(file_uuid)
        if managed_path is not None:
            handle_file_import(str(managed_path))

    main_window.file_double_clicked.connect(open_file_from_explorer)

    def activate_main_window() -> None:
        if main_window.isMinimized():
            main_window.showNormal()
        main_window.show()
        main_window.raise_()
        main_window.activateWindow()

    single_instance.activate_requested.connect(activate_main_window)
    single_instance.file_received.connect(main_window.open_imported_file)

    main_window.show()
    splash.finish(main_window)

    for position, startup_path in enumerate(startup_paths):
        QTimer.singleShot(100 + position * 100, lambda path=startup_path: main_window.open_imported_file(path))

    settings_store = container.resolve(SettingsStore)
    restore_path: str | None = None
    if not startup_paths and settings_store.get("restore_last_project", False):
        recent_projects = workspace_manager.get_recent_projects()
        if recent_projects:
            candidate = Path(recent_projects[0]).expanduser()
            if candidate.is_file():
                restore_path = str(candidate)
                QTimer.singleShot(150, lambda path=restore_path: main_window.open_project_path(path, silent=True))

    if show_subscription_after_login:
        def show_initial_subscription() -> None:
            dialog = SubscriptionDialog(license_service, main_window, first_login=True)
            if dialog.exec() == SubscriptionDialog.Accepted:
                refresh = getattr(main_window, "refresh_license_ui", None)
                if callable(refresh):
                    refresh()
        QTimer.singleShot(250, show_initial_subscription)
    elif settings_store.get('show_tutorial', True) and not startup_paths and restore_path is None:
        def show_tutorial() -> None:
            tutorial = TutorialDialog(main_window)
            tutorial.exec()
            settings_store.set('show_tutorial', tutorial.show_again.isChecked())
        QTimer.singleShot(250, show_tutorial)

    job_manager.initialize(main_window)
    job_manager.job_started.connect(
        lambda job_id: main_window.begin_job_loader(
            job_id,
            cancel_callback=lambda active_job_id=job_id: job_manager.cancel(active_job_id),
        )
    )
    job_manager.job_progress.connect(main_window.update_job_progress)
    job_manager.job_progress.connect(main_window.update_job_loader)
    job_manager.job_completed.connect(lambda job_id, _result: main_window.end_job_loader(job_id))
    job_manager.job_failed.connect(lambda job_id, _error: main_window.end_job_loader(job_id))
    job_manager.job_cancelled.connect(main_window.end_job_loader)

    def update_memory() -> None:
        try:
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / (1024 * 1024)
            main_window.update_memory(memory_mb)
        except:
            pass

    memory_timer = QTimer()
    memory_timer.timeout.connect(update_memory)
    memory_timer.start(5000)

    logger.info("Application window shown")

    exit_code = app.exec()
    single_instance.close()
    crash_handler.uninstall()
    logger.info(f"Application exited with code {exit_code}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
