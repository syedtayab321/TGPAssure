-- Create project table
CREATE TABLE project (
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
);

-- Insert default project with UUID
INSERT INTO project (
    id,
    project_uuid,
    name,
    schema_version
) VALUES (
    1,
    lower(hex(randomblob(16))),
    'Untitled Project',
    0
);

-- Create project_files table
CREATE TABLE project_files (
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
);

-- Create jobs table
CREATE TABLE jobs (
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
);

-- Create qc_runs table
CREATE TABLE qc_runs (
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
);

-- Create qc_stage_results table
CREATE TABLE qc_stage_results (
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
);

-- Create qc_findings table
CREATE TABLE qc_findings (
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
);

-- Create processing_runs table
CREATE TABLE processing_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL DEFAULT 1,
    source_file_id INTEGER NOT NULL,
    output_file_id INTEGER,
    job_id INTEGER,
    processing_uuid TEXT NOT NULL UNIQUE,
    module TEXT NOT NULL,
    process_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    algorithm_name TEXT NOT NULL,
    algorithm_version TEXT,
    parameters_json TEXT NOT NULL DEFAULT '{}',
    metrics_json TEXT NOT NULL DEFAULT '{}',
    output_path TEXT,
    error_text TEXT,
    started_at TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES project(id) ON DELETE CASCADE,
    FOREIGN KEY (source_file_id) REFERENCES project_files(id) ON DELETE CASCADE,
    FOREIGN KEY (output_file_id) REFERENCES project_files(id) ON DELETE SET NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE SET NULL
);

-- Create reports table
CREATE TABLE reports (
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
    FOREIGN KEY (qc_run_id) REFERENCES qc_runs(id) ON DELETE SET NULL,
    FOREIGN KEY (processing_run_id) REFERENCES processing_runs(id) ON DELETE SET NULL
);

-- Create bookmarks table
CREATE TABLE bookmarks (
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
);

-- Create recent_files table
CREATE TABLE recent_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL DEFAULT 1,
    absolute_path TEXT,
    display_name TEXT NOT NULL,
    module TEXT,
    last_opened_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    open_count INTEGER NOT NULL DEFAULT 1 CHECK (open_count >= 1),
    is_pinned INTEGER NOT NULL DEFAULT 0 CHECK (is_pinned IN (0, 1)),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (project_id) REFERENCES project(id) ON DELETE CASCADE,
    UNIQUE (project_id, absolute_path)
);

-- Create project_settings table
CREATE TABLE project_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL DEFAULT 1,
    setting_key TEXT NOT NULL,
    setting_value TEXT NOT NULL,
    value_type TEXT NOT NULL DEFAULT 'string',
    scope TEXT NOT NULL DEFAULT 'project',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES project(id) ON DELETE CASCADE,
    UNIQUE (project_id, setting_key, scope)
);

-- Create log_entries_index table
CREATE TABLE log_entries_index (
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
    FOREIGN KEY (qc_run_id) REFERENCES qc_runs(id) ON DELETE SET NULL,
    FOREIGN KEY (processing_run_id) REFERENCES processing_runs(id) ON DELETE SET NULL
);

-- Create indexes
CREATE INDEX idx_files_module ON project_files(module);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_qc_findings_severity ON qc_findings(severity);
CREATE INDEX idx_processing_runs_file ON processing_runs(source_file_id);