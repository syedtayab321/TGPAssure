from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

from modules.seismic.converter.segy_to_segd import SegyToSegdConverter
from modules.seismic.segd_viewer.segd_reader import SegdReader


def _write_standard_segy(path: Path, trace_count: int = 3, sample_count: int = 128, dt_us: int = 2000) -> None:
    with path.open("wb") as stream:
        text = ("C01 TGPAssure synthetic converter regression".ljust(80) * 40).encode("ascii")[:3200]
        stream.write(text.ljust(3200, b" "))
        binary = bytearray(400)
        struct.pack_into(">H", binary, 16, dt_us)
        struct.pack_into(">H", binary, 20, sample_count)
        struct.pack_into(">H", binary, 24, 5)  # IEEE float32
        struct.pack_into(">H", binary, 300, 0x0100)
        struct.pack_into(">H", binary, 302, 1)
        stream.write(binary)
        for trace_index in range(trace_count):
            header = bytearray(240)
            struct.pack_into(">i", header, 0, trace_index + 1)
            struct.pack_into(">i", header, 8, trace_index + 1)
            struct.pack_into(">i", header, 20, 100 + trace_index)
            struct.pack_into(">H", header, 114, sample_count)
            struct.pack_into(">H", header, 116, dt_us)
            stream.write(header)
            samples = (np.sin(np.linspace(0, 6.0, sample_count)) + trace_index).astype(">f4")
            stream.write(samples.tobytes())


def test_preview_first_trace_exists(tmp_path: Path) -> None:
    test_segy = tmp_path / "source.sgy"
    _write_standard_segy(test_segy)
    data = SegyToSegdConverter().preview_first_trace(test_segy)
    assert data is not None
    assert isinstance(data, np.ndarray)
    assert data.size == 128
    assert np.any(np.abs(data) > 0)


def test_convert_creates_valid_readable_segd(tmp_path: Path) -> None:
    test_segy = tmp_path / "source.sgy"
    out_file = tmp_path / "out.segd"
    _write_standard_segy(test_segy)
    progress: list[float] = []
    SegyToSegdConverter().convert(
        test_segy, out_file, trace_indices=[0, 1], sample_rate=500, scale=1.0,
        progress_callback=lambda fraction, _eta: progress.append(fraction),
    )
    assert out_file.exists() and out_file.stat().st_size > 0
    reader = SegdReader(out_file)
    try:
        assert reader.get_trace_count() == 2
        first = reader.read_trace_window((0, 1))[0, 0]
        assert first.size == 128
        assert np.any(np.abs(first) > 0)
    finally:
        reader.close()
    assert progress and progress[-1] == 1.0
