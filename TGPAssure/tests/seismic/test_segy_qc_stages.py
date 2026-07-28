from __future__ import annotations

import pytest
import tempfile
import shutil
import json
import numpy as np
from pathlib import Path

from core.data_access.db_engine import DatabaseEngine
from core.data_access.project_repository import ProjectRepository
from core.domain.qc_engine import QCStatus, QCSeverity

from modules.seismic.segy_qc.stages.validation import ValidationStage
from modules.seismic.segy_qc.stages.geometry_qc import GeometryQCStage
from modules.seismic.segy_qc.stages.trace_qc import TraceQCStage
from modules.seismic.segy_qc.stages.amplitude_qc import AmplitudeQCStage
from modules.seismic.segy_qc.stages.statics_qc import StaticsQCStage


@pytest.fixture
def temp_dir() -> Path:
    path = Path(tempfile.mkdtemp())
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def db_engine(temp_dir: Path) -> DatabaseEngine:
    db_path = temp_dir / "test.db"
    engine = DatabaseEngine(db_path)
    conn = engine.get_write_connection()
    try:
        conn.execute("""
            CREATE TABLE project (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                project_uuid TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("INSERT INTO project (id, project_uuid, name) VALUES (1, 'test', 'Test')")
        conn.execute("""
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
                size_bytes INTEGER NOT NULL DEFAULT 0,
                sha256 TEXT,
                status TEXT NOT NULL DEFAULT 'available',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_verified_at TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()
    return engine


@pytest.fixture
def project_repo(db_engine: DatabaseEngine) -> ProjectRepository:
    return ProjectRepository(db_engine)


def create_test_segy_data(trace_count: int = 10, sample_count: int = 100) -> tuple[Path, np.ndarray, np.ndarray]:
    temp_file = Path(tempfile.mktemp(suffix=".sgy"))
    
    with open(temp_file, "wb") as f:
        f.write(b" " * 3200)
        
        binary_header = bytearray(400)
        binary_header[0:2] = (5).to_bytes(2, 'big')
        binary_header[2:4] = trace_count.to_bytes(2, 'big')
        binary_header[4:6] = sample_count.to_bytes(2, 'big')
        binary_header[6:8] = (2).to_bytes(2, 'big')
        f.write(binary_header)
        
        headers = np.zeros(trace_count, dtype=[
            ('cdp', '>i4'), ('offset', '>i4'), ('source_x', '>i4'), ('source_y', '>i4'),
            ('receiver_group_x', '>i4'), ('receiver_group_y', '>i4'),
            ('trace_sequence_line', '>i4'), ('trace_sequence_file', '>i4'),
            ('total_static', '>i2'), ('source_to_receiver_static', '>i2'),
            ('coordinate_units', '>i2')
        ])
        
        for i in range(trace_count):
            headers[i]['cdp'] = i // 2
            headers[i]['offset'] = i * 10
            headers[i]['source_x'] = 100 + i * 5
            headers[i]['source_y'] = 200 + i * 5
            headers[i]['total_static'] = i * 10
            headers[i]['source_to_receiver_static'] = i * 5
            headers[i]['coordinate_units'] = 1
            
            f.write(headers[i].tobytes())
            
            trace_data = np.random.randn(sample_count).astype(np.float32)
            f.write(trace_data.tobytes())
    
    return temp_file, headers, np.random.randn(trace_count, sample_count)


def test_validation_stage_passes() -> None:
    temp_file, _, _ = create_test_segy_data()
    context = {"file_path": str(temp_file)}
    
    stage = ValidationStage()
    result = stage.run(context)
    
    assert result.status == QCStatus.PASS
    assert "format_code" in context
    assert "trace_count" in context
    assert context["trace_count"] == 10


def test_validation_stage_fails_on_invalid_file() -> None:
    temp_file = Path(tempfile.mktemp(suffix=".sgy"))
    temp_file.write_text("Invalid SEG-Y data")
    
    context = {"file_path": str(temp_file)}
    stage = ValidationStage()
    result = stage.run(context)
    
    assert result.status == QCStatus.FAIL


def test_geometry_qc_stage() -> None:
    headers = np.zeros(10, dtype=[
        ('cdp', '>i4'), ('offset', '>i4'), ('source_x', '>i4'), ('source_y', '>i4'),
        ('receiver_group_x', '>i4'), ('receiver_group_y', '>i4'),
        ('trace_sequence_line', '>i4'), ('trace_sequence_file', '>i4')
    ])
    
    for i in range(10):
        headers[i]['cdp'] = i // 2
    
    context = {"trace_headers": headers}
    stage = GeometryQCStage(expected_fold_min=1, expected_fold_max=10)
    result = stage.run(context)
    
    assert result.status == QCStatus.PASS
    assert "fold_stats" in context
    assert context["fold_stats"]["unique_cdps"] == 5


def test_trace_qc_stage_with_synthetic_data() -> None:
    temp_file, headers, data = create_test_segy_data()
    
    from modules.seismic.segy_qc.segy_reader import SegyReader
    reader = SegyReader(temp_file)
    context = {"reader": reader}
    
    stage = TraceQCStage(noise_floor_threshold=0.001)
    result = stage.run(context)
    
    assert result.status == QCStatus.PASS
    assert "rms_values" in context


def test_amplitude_qc_stage() -> None:
    temp_file, headers, data = create_test_segy_data()
    
    from modules.seismic.segy_qc.segy_reader import SegyReader
    reader = SegyReader(temp_file)
    context = {"reader": reader}
    
    stage = AmplitudeQCStage(dc_bias_threshold=0.1)
    result = stage.run(context)
    
    assert result.status == QCStatus.PASS
    assert "amplitude_stats" in context


def test_statics_qc_stage() -> None:
    headers = np.zeros(10, dtype=[
        ('total_static', '>i2'), ('source_to_receiver_static', '>i2'),
        ('cdp', '>i4'), ('offset', '>i4')
    ])
    
    for i in range(10):
        headers[i]['total_static'] = i * 50
        headers[i]['source_to_receiver_static'] = i * 25
    
    context = {"trace_headers": headers}
    stage = StaticsQCStage(max_static_magnitude=500.0)
    result = stage.run(context)
    
    assert result.status == QCStatus.PASS
    assert "static_stats" in context
    assert context["static_stats"]["max"] == 450.0


def test_geometry_qc_finds_low_fold() -> None:
    headers = np.zeros(20, dtype=[
        ('cdp', '>i4'), ('offset', '>i4'), ('source_x', '>i4'), ('source_y', '>i4'),
        ('receiver_group_x', '>i4'), ('receiver_group_y', '>i4'),
        ('trace_sequence_line', '>i4'), ('trace_sequence_file', '>i4')
    ])
    
    for i in range(20):
        headers[i]['cdp'] = i
    
    context = {"trace_headers": headers}
    stage = GeometryQCStage(expected_fold_min=2, expected_fold_max=10)
    result = stage.run(context)
    
    assert result.status == QCStatus.WARN
    assert len(result.findings) > 0
    assert result.findings[0].rule_id == "geometry_low_fold"


def test_trace_qc_detects_dead_traces() -> None:
    temp_file = Path(tempfile.mktemp(suffix=".sgy"))
    
    trace_count = 10
    sample_count = 100
    
    with open(temp_file, "wb") as f:
        f.write(b" " * 3200)
        
        binary_header = bytearray(400)
        binary_header[0:2] = (5).to_bytes(2, 'big')
        binary_header[2:4] = trace_count.to_bytes(2, 'big')
        binary_header[4:6] = sample_count.to_bytes(2, 'big')
        binary_header[6:8] = (2).to_bytes(2, 'big')
        f.write(binary_header)
        
        for i in range(trace_count):
            f.write(b" " * 240)
            
            if i % 3 == 0:
                trace_data = np.zeros(sample_count, dtype=np.float32)
            else:
                trace_data = np.random.randn(sample_count).astype(np.float32)
            f.write(trace_data.tobytes())
    
    from modules.seismic.segy_qc.segy_reader import SegyReader
    reader = SegyReader(temp_file)
    context = {"reader": reader}
    
    stage = TraceQCStage(noise_floor_threshold=0.001)
    result = stage.run(context)
    
    assert result.status == QCStatus.WARN
    assert len(result.findings) > 0
    assert result.findings[0].rule_id == "trace_dead_traces"


def test_validation_detects_invalid_format_code() -> None:
    temp_file = Path(tempfile.mktemp(suffix=".sgy"))
    
    with open(temp_file, "wb") as f:
        f.write(b" " * 3200)
        
        binary_header = bytearray(400)
        binary_header[0:2] = (99).to_bytes(2, 'big')
        binary_header[2:4] = (10).to_bytes(2, 'big')
        binary_header[4:6] = (100).to_bytes(2, 'big')
        binary_header[6:8] = (2).to_bytes(2, 'big')
        f.write(binary_header)
        
        for _ in range(10):
            f.write(b" " * 240)
            trace_data = np.random.randn(100).astype(np.float32)
            f.write(trace_data.tobytes())
    
    context = {"file_path": str(temp_file)}
    stage = ValidationStage()
    result = stage.run(context)
    
    assert result.status == QCStatus.FAIL
    assert len(result.findings) > 0
    assert result.findings[0].rule_id == "validation_invalid_format_code"