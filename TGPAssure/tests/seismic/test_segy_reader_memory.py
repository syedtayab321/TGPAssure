from __future__ import annotations

import pytest
import tempfile
import shutil
import numpy as np
import psutil
import time
from pathlib import Path

from modules.seismic.segy_qc.segy_reader import SegyReader

@pytest.fixture
def temp_dir() -> Path:
    path = Path(tempfile.mkdtemp())
    yield path
    shutil.rmtree(path, ignore_errors=True)

def create_large_segy_file(path: Path, trace_count: int, sample_count: int) -> None:
    with open(path, "wb") as f:
        ebcdic_header = b" " * 3200
        f.write(ebcdic_header)
        
        binary_header = bytearray(400)
        binary_header[0:2] = (5).to_bytes(2, 'big')
        binary_header[2:4] = trace_count.to_bytes(2, 'big')
        binary_header[4:6] = sample_count.to_bytes(2, 'big')
        binary_header[6:8] = (2).to_bytes(2, 'big')
        f.write(binary_header)
        
        for i in range(trace_count):
            trace_header = b" " * 240
            f.write(trace_header)
            chunk_size = sample_count * 4
            chunk = np.random.randn(sample_count).astype(np.float32).tobytes()
            f.write(chunk)

def test_segy_reader_memory_efficient_large_file(temp_dir: Path) -> None:
    trace_count = 1000
    sample_count = 1000
    
    test_file = temp_dir / "large.sgy"
    create_large_segy_file(test_file, trace_count, sample_count)
    
    time.sleep(0.5)
    process = psutil.Process()
    initial_memory = process.memory_info().rss
    
    reader = SegyReader(test_file)
    
    headers = reader.read_trace_headers((0, 100))
    data = reader.read_trace_window((0, 50), (0, 200))
    
    peak_memory = process.memory_info().rss
    memory_increase = (peak_memory - initial_memory) / (1024 * 1024)
    
    assert len(headers) == 100
    assert data.shape == (50, 200)
    assert memory_increase < 200, f"Memory increased by {memory_increase} MB"

def test_segy_reader_reads_all_traces_memory_efficient(temp_dir: Path) -> None:
    trace_count = 500
    sample_count = 500
    
    test_file = temp_dir / "medium.sgy"
    create_large_segy_file(test_file, trace_count, sample_count)
    
    time.sleep(0.5)
    process = psutil.Process()
    initial_memory = process.memory_info().rss
    
    reader = SegyReader(test_file)
    
    headers = reader.read_trace_headers()
    data = reader.read_trace_window((0, trace_count), (0, sample_count))
    
    peak_memory = process.memory_info().rss
    memory_increase = (peak_memory - initial_memory) / (1024 * 1024)
    
    assert len(headers) == trace_count
    assert data.shape == (trace_count, sample_count)
    assert memory_increase < 150, f"Memory increased by {memory_increase} MB"

def test_segy_reader_multiple_reads_no_memory_leak(temp_dir: Path) -> None:
    trace_count = 200
    sample_count = 200
    
    test_file = temp_dir / "multi.sgy"
    create_large_segy_file(test_file, trace_count, sample_count)
    
    reader = SegyReader(test_file)
    
    process = psutil.Process()
    initial_memory = process.memory_info().rss
    
    for i in range(5):
        start_trace = i * 20
        end_trace = start_trace + 20
        data = reader.read_trace_window((start_trace, end_trace), (0, 50))
        assert data.shape == (20, 50)
    
    peak_memory = process.memory_info().rss
    memory_increase = (peak_memory - initial_memory) / (1024 * 1024)
    
    assert memory_increase < 50, f"Memory increased by {memory_increase} MB"