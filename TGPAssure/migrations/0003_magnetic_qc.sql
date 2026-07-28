-- Magnetic QC module schema
CREATE TABLE IF NOT EXISTS magnetic_datasets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_uuid TEXT NOT NULL UNIQUE,
    file_id INTEGER,
    source_path TEXT NOT NULL,
    role TEXT NOT NULL,
    survey_type TEXT NOT NULL,
    instrument_make TEXT,
    instrument_model TEXT,
    sensor_serial_number TEXT,
    crs TEXT,
    coordinate_units TEXT,
    magnetic_units TEXT,
    record_count INTEGER NOT NULL,
    line_count INTEGER NOT NULL DEFAULT 0,
    start_time TEXT,
    end_time TEXT,
    min_x REAL,
    max_x REAL,
    min_y REAL,
    max_y REAL,
    checksum TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    column_mapping_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(file_id) REFERENCES project_files(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS magnetic_line_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id INTEGER NOT NULL,
    line_id TEXT NOT NULL,
    line_type TEXT,
    station_count INTEGER,
    length_m REAL,
    azimuth_deg REAL,
    mean_spacing_m REAL,
    maximum_spacing_m REAL,
    mean_field_nt REAL,
    field_std_nt REAL,
    noise_rms_nt REAL,
    qc_status TEXT,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(dataset_id) REFERENCES magnetic_datasets(id) ON DELETE CASCADE,
    UNIQUE(dataset_id, line_id)
);

CREATE TABLE IF NOT EXISTS magnetic_base_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id INTEGER NOT NULL,
    station_name TEXT,
    start_time TEXT,
    end_time TEXT,
    sampling_interval_s REAL,
    mean_field_nt REAL,
    field_range_nt REAL,
    noise_rms_nt REAL,
    maximum_rate_nt_min REAL,
    qc_status TEXT,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(dataset_id) REFERENCES magnetic_datasets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS magnetic_processing_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_uuid TEXT NOT NULL UNIQUE,
    dataset_id INTEGER,
    processing_run_id INTEGER,
    product_type TEXT NOT NULL,
    channel_name TEXT,
    file_path TEXT,
    parent_product_id INTEGER,
    crs TEXT,
    units TEXT,
    cell_size REAL,
    statistics_json TEXT NOT NULL DEFAULT '{}',
    parameters_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(dataset_id) REFERENCES magnetic_datasets(id) ON DELETE SET NULL,
    FOREIGN KEY(processing_run_id) REFERENCES processing_runs(id) ON DELETE SET NULL,
    FOREIGN KEY(parent_product_id) REFERENCES magnetic_processing_products(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS magnetic_qc_masks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id INTEGER NOT NULL,
    qc_run_id INTEGER,
    mask_name TEXT NOT NULL,
    mask_path TEXT,
    true_count INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(dataset_id) REFERENCES magnetic_datasets(id) ON DELETE CASCADE,
    FOREIGN KEY(qc_run_id) REFERENCES qc_runs(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_magnetic_datasets_checksum ON magnetic_datasets(checksum);
CREATE INDEX IF NOT EXISTS idx_magnetic_lines_dataset ON magnetic_line_summaries(dataset_id);
CREATE INDEX IF NOT EXISTS idx_magnetic_products_dataset ON magnetic_processing_products(dataset_id);
CREATE INDEX IF NOT EXISTS idx_magnetic_masks_run ON magnetic_qc_masks(qc_run_id);
