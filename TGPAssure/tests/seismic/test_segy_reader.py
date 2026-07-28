from __future__ import annotations

import pytest
import tempfile
import shutil
import numpy as np
import psutil
import time
from pathlib import Path

from modules.seismic.segy_qc.segy_reader import SegyReader, UnsupportedSampleFormatError

@pytest.fixture
def temp_dir() -> Path:
    path = Path(tempfile.mkdtemp())
    yield path
    shutil.rmtree(path, ignore_errors=True)

def create_minimal_segy_file(path: Path, trace_count: int = 10, sample_count: int = 100) -> None:
    with open(path, "wb") as f:
        ebcdic_header = b" " * 3200
        f.write(ebcdic_header)
        
        binary_header = bytearray(400)
        binary_header[0:2] = (5).to_bytes(2, 'big')
        binary_header[2:4] = trace_count.to_bytes(2, 'big')
        binary_header[4:6] = sample_count.to_bytes(2, 'big')
        binary_header[6:8] = (2).to_bytes(2, 'big')
        f.write(binary_header)
        
        for _ in range(trace_count):
            trace_header = b" " * 240
            f.write(trace_header)
            
            trace_data = np.random.randn(sample_count).astype(np.float32)
            f.write(trace_data.tobytes())

def test_segy_reader_parses_binary_header(temp_dir: Path) -> None:
    test_file = temp_dir / "test.sgy"
    create_minimal_segy_file(test_file, trace_count=15, sample_count=200)
    
    reader = SegyReader(test_file)
    
    assert reader.binary_header.trace_count == 15
    assert reader.binary_header.sample_count_per_trace == 200
    assert reader.binary_header.sample_format_code == 5
    assert reader.binary_header.sample_interval_ms == 2

def test_segy_reader_parses_text_header(temp_dir: Path) -> None:
    test_file = temp_dir / "test.sgy"
    with open(test_file, "wb") as f:
        test_text = b"TEST HEADER " + b" " * (3200 - 12)
        f.write(test_text)
        
        binary_header = bytearray(400)
        binary_header[0:2] = (5).to_bytes(2, 'big')
        binary_header[2:4] = (1).to_bytes(2, 'big')
        binary_header[4:6] = (100).to_bytes(2, 'big')
        binary_header[6:8] = (2).to_bytes(2, 'big')
        f.write(binary_header)
        
        trace_header = b" " * 240
        f.write(trace_header)
        trace_data = np.random.randn(100).astype(np.float32)
        f.write(trace_data.tobytes())
    
    reader = SegyReader(test_file)
    assert reader.text_header is not None
    assert "TEST HEADER" in reader.text_header.decoded_text

def test_segy_reader_reads_trace_headers(temp_dir: Path) -> None:
    test_file = temp_dir / "test.sgy"
    create_minimal_segy_file(test_file, trace_count=20, sample_count=150)
    
    reader = SegyReader(test_file)
    headers = reader.read_trace_headers()
    
    assert len(headers) == 20
    assert 'cdp' in headers.dtype.names
    assert 'offset' in headers.dtype.names
    assert 'source_x' in headers.dtype.names

def test_segy_reader_reads_trace_window(temp_dir: Path) -> None:
    test_file = temp_dir / "test.sgy"
    create_minimal_segy_file(test_file, trace_count=20, sample_count=150)
    
    reader = SegyReader(test_file)
    data = reader.read_trace_window((0, 10), (0, 50))
    
    assert data.shape == (10, 50)
    assert data.dtype == np.float32

def test_segy_reader_memmap_does_not_spike_ram(temp_dir: Path) -> None:
    test_file = temp_dir / "large.sgy"
    
    trace_count = 500
    sample_count = 500
    
    with open(test_file, "wb") as f:
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
            trace_data = np.random.randn(sample_count).astype(np.float32)
            f.write(trace_data.tobytes())
    
    time.sleep(0.5)
    process = psutil.Process()
    initial_memory = process.memory_info().rss
    
    reader = SegyReader(test_file)
    data = reader.read_trace_window((0, 100), (0, 100))
    
    peak_memory = process.memory_info().rss
    memory_increase = (peak_memory - initial_memory) / (1024 * 1024)
    
    assert data.shape == (100, 100)
    assert memory_increase < 100, f"Memory increased by {memory_increase} MB"

def test_segy_reader_invalid_file_raises(temp_dir: Path) -> None:
    test_file = temp_dir / "invalid.sgy"
    test_file.write_text("This is not a valid SEG-Y file")
    
    with pytest.raises(ValueError):
        SegyReader(test_file)

def test_segy_reader_reads_all_formats(temp_dir: Path) -> None:
    test_file = temp_dir / "test.sgy"
    
    for format_code in [1, 2, 3, 5, 8, 9]:
        with open(test_file, "wb") as f:
            ebcdic_header = b" " * 3200
            f.write(ebcdic_header)
            
            binary_header = bytearray(400)
            binary_header[0:2] = format_code.to_bytes(2, 'big')
            binary_header[2:4] = (10).to_bytes(2, 'big')
            binary_header[4:6] = (100).to_bytes(2, 'big')
            binary_header[6:8] = (2).to_bytes(2, 'big')
            f.write(binary_header)
            
            for _ in range(10):
                trace_header = b" " * 240
                f.write(trace_header)
                trace_data = np.random.randn(100).astype(np.float32)
                f.write(trace_data.tobytes())
        
        reader = SegyReader(test_file)
        assert reader.binary_header.sample_format_code == format_code

def test_segy_reader_rejects_obsolete_format_4(temp_dir: Path) -> None:
    """Format 4 is obsolete fixed-point-with-gain and must not be silently misdecoded."""
    test_file = temp_dir / "format4.sgy"
    with test_file.open("wb") as f:
        f.write(b" " * 3200)
        binary_header = bytearray(400)
        binary_header[0:2] = (4).to_bytes(2, "big")
        binary_header[2:4] = (1).to_bytes(2, "big")
        binary_header[4:6] = (10).to_bytes(2, "big")
        binary_header[6:8] = (2).to_bytes(2, "big")
        f.write(binary_header)
        f.write(b" " * 240)
        f.write(b"\x00" * 40)
    with pytest.raises(UnsupportedSampleFormatError):
        SegyReader(test_file)
