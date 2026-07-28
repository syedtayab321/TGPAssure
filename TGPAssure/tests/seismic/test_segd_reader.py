from __future__ import annotations

import pytest
import tempfile
import shutil
import numpy as np
import struct
from pathlib import Path

from modules.seismic.segd_viewer.segd_reader import SegdReader

@pytest.fixture
def temp_dir() -> Path:
    path = Path(tempfile.mkdtemp())
    yield path
    shutil.rmtree(path, ignore_errors=True)

def create_minimal_segd_file(path: Path) -> None:
    with open(path, "wb") as f:
        general_header_1 = bytearray(64)
        general_header_1[0:2] = struct.pack('>h', 1)
        general_header_1[2:4] = struct.pack('>h', 64)
        general_header_1[4:6] = struct.pack('>h', 32)
        general_header_1[6:8] = struct.pack('>h', 0)
        general_header_1[8:10] = struct.pack('>h', 240)
        general_header_1[10:12] = struct.pack('>h', 1)
        general_header_1[12:14] = struct.pack('>h', 10)
        general_header_1[14:16] = struct.pack('>h', 1)
        general_header_1[16:18] = struct.pack('>h', 1)
        general_header_1[18:20] = struct.pack('>h', 4)
        general_header_1[20:22] = struct.pack('>h', 2)
        f.write(general_header_1)
        
        general_header_2 = bytearray(64)
        general_header_2[0:2] = struct.pack('>h', 10)
        general_header_2[2:4] = struct.pack('>h', 1)
        general_header_2[4:6] = struct.pack('>h', 2026)
        general_header_2[6:8] = struct.pack('>h', 195)
        general_header_2[8:10] = struct.pack('>h', 8)
        general_header_2[10:12] = struct.pack('>h', 3)
        general_header_2[12:14] = struct.pack('>h', 5)
        general_header_2[14:16] = struct.pack('>h', 0)
        f.write(general_header_2)
        
        general_header_3 = bytearray(64)
        general_header_3[0:2] = struct.pack('>h', 0)
        general_header_3[2:4] = struct.pack('>h', 0)
        general_header_3[4:6] = struct.pack('>h', 32)
        general_header_3[6:8] = struct.pack('>h', 240)
        general_header_3[8:10] = struct.pack('>h', 0)
        f.write(general_header_3)
        
        channel_set_descriptor = bytearray(32)
        channel_set_descriptor[0:2] = struct.pack('>h', 1)
        channel_set_descriptor[2:4] = struct.pack('>h', 1)
        channel_set_descriptor[4:6] = struct.pack('>h', 100)
        channel_set_descriptor[6:8] = struct.pack('>h', 4)
        channel_set_descriptor[8:10] = struct.pack('>h', 2)
        f.write(channel_set_descriptor)
        
        trace_headers = bytearray(240)
        f.write(trace_headers)
        
        for i in range(10):
            trace_data = np.random.randn(100).astype(np.float32)
            f.write(trace_data.tobytes())

def test_segd_reader_parses_general_header_1(temp_dir: Path) -> None:
    test_file = temp_dir / "test.sgd"
    create_minimal_segd_file(test_file)
    
    reader = SegdReader(test_file)
    
    assert reader.general_header_1.file_number == 1
    assert reader.general_header_1.general_header_length == 64
    assert reader.general_header_1.channel_set_descriptor_length == 32
    assert reader.general_header_1.channel_set_count == 1
    assert reader.general_header_1.manufacturer_code == 1
    assert reader.general_header_1.version == 1

def test_segd_reader_parses_general_header_2(temp_dir: Path) -> None:
    test_file = temp_dir / "test.sgd"
    create_minimal_segd_file(test_file)
    
    reader = SegdReader(test_file)
    
    assert reader.general_header_2.maximum_traces == 10
    assert reader.general_header_2.channel_sets_count == 1
    assert reader.general_header_2.year == 2026
    assert reader.general_header_2.day == 195

def test_segd_reader_parses_channel_set_descriptors(temp_dir: Path) -> None:
    test_file = temp_dir / "test.sgd"
    create_minimal_segd_file(test_file)
    
    reader = SegdReader(test_file)
    
    assert len(reader.channel_set_descriptors) == 1
    descriptor = reader.channel_set_descriptors[0]
    assert descriptor.channel_set_id == 1
    assert descriptor.channel_count == 1
    assert descriptor.sample_count == 100
    assert descriptor.sample_format == 4

def test_segd_reader_reads_trace_window(temp_dir: Path) -> None:
    test_file = temp_dir / "test.sgd"
    create_minimal_segd_file(test_file)
    
    reader = SegdReader(test_file)
    data = reader.read_trace_window((0, 5), (0, 50))
    
    assert data.shape == (5, 1, 50)
    assert data.dtype == np.float32

def test_segd_reader_get_trace_count(temp_dir: Path) -> None:
    test_file = temp_dir / "test.sgd"
    create_minimal_segd_file(test_file)
    
    reader = SegdReader(test_file)
    assert reader.get_trace_count() == 10

def test_segd_reader_get_sample_count(temp_dir: Path) -> None:
    test_file = temp_dir / "test.sgd"
    create_minimal_segd_file(test_file)
    
    reader = SegdReader(test_file)
    assert reader.get_sample_count() == 100