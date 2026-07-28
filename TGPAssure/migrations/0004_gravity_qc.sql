CREATE TABLE IF NOT EXISTS gravity_datasets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_uuid TEXT NOT NULL UNIQUE,
    file_id INTEGER,
    source_path TEXT NOT NULL,
    role TEXT NOT NULL,
    survey_type TEXT NOT NULL,
    instrument_make TEXT,
    instrument_model TEXT,
    instrument_serial TEXT,
    crs TEXT,
    gravity_units TEXT,
    elevation_units TEXT,
    record_count INTEGER NOT NULL,
    station_count INTEGER NOT NULL DEFAULT 0,
    line_count INTEGER NOT NULL DEFAULT 0,
    start_time TEXT,
    end_time TEXT,
    checksum TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(file_id) REFERENCES project_files(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_gravity_dataset_checksum ON gravity_datasets(checksum);

CREATE TABLE IF NOT EXISTS gravity_base_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id INTEGER NOT NULL,
    record_count INTEGER,
    drift_rate_mgal_hr REAL,
    residual_std_mgal REAL,
    max_gap_min REAL,
    range_mgal REAL,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(dataset_id) REFERENCES gravity_datasets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS gravity_repeat_statistics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    qc_run_id INTEGER,
    dataset_id INTEGER NOT NULL,
    repeat_group TEXT NOT NULL,
    sample_count INTEGER,
    mean_mgal REAL,
    std_mgal REAL,
    rms_mgal REAL,
    range_mgal REAL,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(qc_run_id) REFERENCES qc_runs(id) ON DELETE CASCADE,
    FOREIGN KEY(dataset_id) REFERENCES gravity_datasets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS gravity_loop_closures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    qc_run_id INTEGER,
    dataset_id INTEGER NOT NULL,
    loop_id TEXT NOT NULL,
    closure_mgal REAL,
    duration_hr REAL,
    closure_rate_mgal_hr REAL,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(qc_run_id) REFERENCES qc_runs(id) ON DELETE CASCADE,
    FOREIGN KEY(dataset_id) REFERENCES gravity_datasets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS gravity_crossovers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    qc_run_id INTEGER,
    dataset_id INTEGER NOT NULL,
    line_a TEXT,
    line_b TEXT,
    station_a TEXT,
    station_b TEXT,
    distance_m REAL,
    error_mgal REAL,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(qc_run_id) REFERENCES qc_runs(id) ON DELETE CASCADE,
    FOREIGN KEY(dataset_id) REFERENCES gravity_datasets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS gravity_processing_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_uuid TEXT NOT NULL UNIQUE,
    dataset_id INTEGER,
    processing_run_id INTEGER,
    product_type TEXT NOT NULL,
    channel_name TEXT,
    file_path TEXT,
    crs TEXT,
    units TEXT,
    statistics_json TEXT NOT NULL DEFAULT '{}',
    parameters_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(dataset_id) REFERENCES gravity_datasets(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS gravity_qc_masks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id INTEGER NOT NULL,
    qc_run_id INTEGER,
    mask_name TEXT NOT NULL,
    true_count INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(dataset_id) REFERENCES gravity_datasets(id) ON DELETE CASCADE,
    FOREIGN KEY(qc_run_id) REFERENCES qc_runs(id) ON DELETE SET NULL
);
