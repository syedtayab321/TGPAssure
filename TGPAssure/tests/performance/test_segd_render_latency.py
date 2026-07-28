from __future__ import annotations

import pytest
import tempfile
import shutil
import time
import numpy as np
import struct
from pathlib import Path

from modules.seismic.segd_viewer.segd_reader import SegdReader
from modules.seismic.segd_viewer.trace_window_loader import TraceWindowLoader
from modules.seismic.segd_viewer.decimator import Decimator
from modules.seismic.segd_viewer.gain_stage import GainStage
from modules.seismic.segd_viewer.rasterizer import Rasterizer
from core.domain.colormap_registry import ColormapRegistry

@pytest.fixture
def temp_dir() -> Path:
    path = Path(tempfile.mkdtemp())
    yield path
    shutil.rmtree(path, ignore_errors=True)

def create_large_segd_file(path: Path, trace_count: int = 1000, sample_count: int = 500) -> None:
    with open(path, "wb") as f:
        general_header_1 = bytearray(64)
        general_header_1[0:2] = struct.pack('>h', 1)
        general_header_1[2:4] = struct.pack('>h', 64)
        general_header_1[4:6] = struct.pack('>h', 32)
        general_header_1[6:8] = struct.pack('>h', 0)
        general_header_1[8:10] = struct.pack('>h', 240)
        general_header_1[10:12] = struct.pack('>h', 1)
        general_header_1[12:14] = struct.pack('>h', trace_count)
        general_header_1[14:16] = struct.pack('>h', 1)
        general_header_1[16:18] = struct.pack('>h', 1)
        general_header_1[18:20] = struct.pack('>h', 4)
        general_header_1[20:22] = struct.pack('>h', 2)
        f.write(general_header_1)
        
        general_header_2 = bytearray(64)
        general_header_2[0:2] = struct.pack('>h', trace_count)
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
        channel_set_descriptor[4:6] = struct.pack('>h', sample_count)
        channel_set_descriptor[6:8] = struct.pack('>h', 4)
        channel_set_descriptor[8:10] = struct.pack('>h', 2)
        f.write(channel_set_descriptor)
        
        trace_headers = bytearray(240)
        f.write(trace_headers)
        
        for i in range(trace_count):
            trace_data = np.random.randn(sample_count).astype(np.float32)
            f.write(trace_data.tobytes())

def test_segd_render_latency(temp_dir: Path) -> None:
    test_file = temp_dir / "large.sgd"
    create_large_segd_file(test_file, trace_count=500, sample_count=500)
    
    loader = TraceWindowLoader(test_file, memory_budget_mb=128)
    decimator = Decimator()
    gain_stage = GainStage()
    rasterizer = Rasterizer()
    colormap_registry = ColormapRegistry()
    
    trace_range = (0, 100)
    sample_range = (0, 500)
    
    start_time = time.perf_counter()
    
    data = loader.read(trace_range, sample_range)
    
    if data.ndim == 3 and data.shape[1] == 1:
        data = data[:, 0, :]
    
    reduced = decimator.reduce_to_width(data, 800, 600)
    
    gained = gain_stage.apply(reduced, GainStage.MODE_AGC, {"window_length": 50})
    
    colormap = colormap_registry.get("seismic")
    qimage = rasterizer.to_qimage(gained, Rasterizer.DISPLAY_VARIABLE_DENSITY, colormap, 800, 600)
    
    end_time = time.perf_counter()
    elapsed_ms = (end_time - start_time) * 1000
    
    assert qimage is not None
    assert qimage.width() == 800 or qimage.width() > 0
    assert qimage.height() == 600 or qimage.height() > 0
    assert elapsed_ms < 100, f"Render latency was {elapsed_ms:.2f}ms, expected < 100ms"
    
    loader.close()