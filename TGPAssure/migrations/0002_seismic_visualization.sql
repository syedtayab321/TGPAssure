CREATE TABLE IF NOT EXISTS seismic_visualization_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_uuid TEXT NOT NULL UNIQUE,
    source_file_path TEXT NOT NULL,
    session_name TEXT NOT NULL,
    session_path TEXT,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_visualization_sessions_source
ON seismic_visualization_sessions(source_file_path, updated_at DESC);
