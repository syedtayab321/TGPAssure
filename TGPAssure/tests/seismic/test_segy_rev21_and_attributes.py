from __future__ import annotations

import importlib.util
import struct
import sys
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[2]


def _load_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


reader_module = _load_module("tgpassure_test_segy_reader", "modules/seismic/segy_reader.py")
attributes_module = _load_module("tgpassure_test_seismic_attributes", "modules/seismic/visualization/seismic_attributes.py")
SegyReader = reader_module.SegyReader


def _pack_into(buffer: bytearray, offset: int, fmt: str, value, endian: str = ">") -> None:
    struct.pack_into(endian + fmt, buffer, offset, value)


def _rev21_trace(trace_no: int, samples: np.ndarray, *, endian: str = ">") -> bytes:
    header = bytearray(240)
    _pack_into(header, 0, "i", trace_no, endian)
    _pack_into(header, 4, "i", trace_no, endian)
    _pack_into(header, 8, "i", 77, endian)
    _pack_into(header, 12, "i", trace_no, endian)
    _pack_into(header, 20, "i", 1000 + trace_no, endian)
    _pack_into(header, 36, "i", 125 + trace_no, endian)
    _pack_into(header, 70, "h", -100, endian)
    _pack_into(header, 72, "i", 1234567, endian)
    _pack_into(header, 76, "i", 2345678, endian)
    _pack_into(header, 80, "i", 1234667, endian)
    _pack_into(header, 84, "i", 2345778, endian)
    _pack_into(header, 108, "h", 12 + trace_no, endian)
    _pack_into(header, 114, "H", len(samples), endian)
    _pack_into(header, 116, "H", 2000, endian)

    ext = bytearray(240)
    _pack_into(ext, 0, "Q", 5_000_000_000 + trace_no, endian)
    _pack_into(ext, 8, "Q", 6_000_000_000 + trace_no, endian)
    _pack_into(ext, 16, "q", 7_000_000_000 + trace_no, endian)
    _pack_into(ext, 24, "q", 9_000_000_000 + trace_no, endian)
    _pack_into(ext, 96, "d", 500_000.125 + trace_no, endian)
    _pack_into(ext, 104, "d", 3_200_000.25 + trace_no, endian)
    _pack_into(ext, 112, "d", 500_025.5 + trace_no, endian)
    _pack_into(ext, 120, "d", 3_200_030.75 + trace_no, endian)
    _pack_into(ext, 128, "d", 33.125 + trace_no, endian)
    _pack_into(ext, 136, "I", len(samples), endian)
    _pack_into(ext, 144, "d", 2000.0, endian)
    _pack_into(ext, 156, "H", 1, endian)
    _pack_into(ext, 160, "d", 500_012.8125 + trace_no, endian)
    _pack_into(ext, 168, "d", 3_200_015.5 + trace_no, endian)
    ext[232:240] = b"SEG00001"

    sample_bytes = np.asarray(samples, dtype=(">f4" if endian == ">" else "<f4")).tobytes()
    return bytes(header) + bytes(ext) + sample_bytes


def _write_rev21(path: Path, *, endian: str = ">", first_trace_offset: int = 3600) -> None:
    text = bytearray(b" " * 3200)
    text[:80] = b"C01 TGPASSURE SEG-Y REV 2.1 VALIDATION DATASET".ljust(80, b" ")
    binary = bytearray(400)
    _pack_into(binary, 16, "H", 2000, endian)
    _pack_into(binary, 18, "H", 2000, endian)
    _pack_into(binary, 20, "H", 8, endian)
    _pack_into(binary, 22, "H", 8, endian)
    _pack_into(binary, 24, "H", 5, endian)  # IEEE float32
    _pack_into(binary, 54, "h", 1, endian)  # metres
    binary[96:100] = b"\x01\x02\x03\x04" if endian == ">" else b"\x04\x03\x02\x01"
    _pack_into(binary, 300, "H", 0x0201, endian)
    _pack_into(binary, 302, "H", 0, endian)
    _pack_into(binary, 304, "h", 0, endian)
    _pack_into(binary, 306, "H", 1, endian)
    _pack_into(binary, 308, "h", 1, endian)
    _pack_into(binary, 310, "h", 4, endian)
    _pack_into(binary, 312, "Q", 2, endian)
    _pack_into(binary, 320, "Q", first_trace_offset, endian)

    padding = b"\x00" * max(0, first_trace_offset - 3600)
    first = _rev21_trace(1, np.linspace(-1.0, 1.0, 8, dtype=np.float32), endian=endian)
    second = _rev21_trace(2, np.linspace(1.0, -1.0, 8, dtype=np.float32), endian=endian)
    path.write_bytes(bytes(text) + bytes(binary) + padding + first + second)


@pytest.mark.parametrize("endian,detection", [(">", "rev2-sentinel-big-endian"), ("<", "rev2-sentinel-little-endian")])
def test_rev21_reader_uses_endian_sentinel_and_extension1(tmp_path: Path, endian: str, detection: str) -> None:
    file_path = tmp_path / f"rev21_{'be' if endian == '>' else 'le'}.sgy"
    _write_rev21(file_path, endian=endian)

    reader = SegyReader(file_path)
    index = reader.scan_trace_headers()

    assert reader.binary_header.revision == "2.1"
    assert reader.binary_header.endian == endian
    assert reader.binary_header.byte_order_detection == detection
    assert reader.binary_header.declared_trace_count == 2
    assert reader.binary_header.maximum_additional_trace_headers == 1
    assert reader.trace_data_start == 3600
    np.testing.assert_array_equal(index.header_sizes, np.array([480, 480]))
    np.testing.assert_array_equal(index.trace_extension_counts, np.array([1, 1]))
    assert bool(np.all(index.trace_extension_1_present))
    assert int(index.cdp[0]) == 9_000_000_001
    structured = reader.read_trace_headers((0, 1))
    assert int(structured["trace_sequence_line"][0]) == 5_000_000_001
    assert int(structured["trace_sequence_file"][0]) == 6_000_000_001
    assert int(structured["field_record"][0]) == 7_000_000_001
    assert int(structured["cdp"][0]) == 9_000_000_001
    assert float(index.source_x[0]) == pytest.approx(500_001.125)
    assert float(index.cdp_x[1]) == pytest.approx(500_014.8125)
    np.testing.assert_allclose(reader.read_trace(0, index), np.linspace(-1.0, 1.0, 8), rtol=1e-6)



def test_rev21_extended_binary_overrides_preserve_large_counts_and_fractional_interval(tmp_path: Path) -> None:
    file_path = tmp_path / "rev21_extended_binary.sgy"
    text = bytearray(b" " * 3200)
    binary = bytearray(400)
    _pack_into(binary, 16, "H", 0, ">")
    _pack_into(binary, 20, "H", 0, ">")
    _pack_into(binary, 24, "H", 5, ">")
    binary[96:100] = b"\x01\x02\x03\x04"
    _pack_into(binary, 68, "I", 70000, ">")
    _pack_into(binary, 72, "d", 500.25, ">")
    _pack_into(binary, 88, "I", 71000, ">")
    _pack_into(binary, 92, "I", 80000, ">")
    _pack_into(binary, 300, "H", 0x0201, ">")
    _pack_into(binary, 302, "H", 1, ">")
    _pack_into(binary, 312, "Q", 0, ">")

    # No trace payload is needed to validate effective binary-header overrides.
    file_path.write_bytes(bytes(text) + bytes(binary))
    reader = SegyReader(file_path)

    assert reader.binary_header.samples_per_trace == 70000
    assert reader.binary_header.original_samples_per_trace == 71000
    assert reader.binary_header.sample_interval_us == pytest.approx(500.25)
    assert reader.binary_header.ensemble_fold == 80000


def test_trace_extension1_preserves_fractional_sample_interval_and_offset(tmp_path: Path) -> None:
    file_path = tmp_path / "rev21_fractional_trace_values.sgy"
    _write_rev21(file_path)
    raw = bytearray(file_path.read_bytes())
    ext_start = 3600 + 240
    _pack_into(raw, ext_start + 128, "d", 33.125, ">")
    _pack_into(raw, ext_start + 144, "d", 1999.75, ">")
    file_path.write_bytes(bytes(raw))

    reader = SegyReader(file_path)
    index = reader.scan_trace_headers()
    assert float(index.offsets[0]) == pytest.approx(33.125)
    assert float(index.sample_intervals_us[0]) == pytest.approx(1999.75)
    header = reader.read_trace_header(0, index)
    assert header.offset == pytest.approx(33.125)
    assert header.sample_interval_us == pytest.approx(1999.75)

def test_invalid_rev2_first_trace_offset_falls_back_safely_for_qc(tmp_path: Path) -> None:
    file_path = tmp_path / "bad_first_trace_offset.sgy"
    _write_rev21(file_path, first_trace_offset=3200)
    reader = SegyReader(file_path)

    assert reader.binary_header.first_trace_offset == 3200
    assert reader.trace_data_start == 3600
    assert reader.trace_data_start_source == "invalid-binary-header-override-fallback"
    assert reader.scan_trace_headers().trace_count == 2


def test_instantaneous_attributes_and_semblance_are_numerically_consistent() -> None:
    dt_ms = 2.0
    time_s = np.arange(2000, dtype=np.float64) * dt_ms / 1000.0
    signal = np.sin(2.0 * np.pi * 25.0 * time_s)
    section = np.repeat(signal[:, None], 5, axis=1).astype(np.float32)

    envelope = attributes_module.envelope(section)
    frequency = attributes_module.instantaneous_frequency(section, dt_ms)
    semblance = attributes_module.local_semblance(section, dt_ms, window_ms=40.0, trace_radius=2)
    rms = attributes_module.rms_amplitude(section, dt_ms, window_ms=40.0)

    core = slice(100, -100)
    assert float(np.nanmedian(envelope[core])) == pytest.approx(1.0, rel=2e-3)
    assert float(np.nanmedian(frequency[core])) == pytest.approx(25.0, rel=2e-3)
    assert float(np.nanmedian(semblance[core])) == pytest.approx(1.0, rel=1e-5)
    assert float(np.nanmedian(rms[core])) == pytest.approx(1.0 / np.sqrt(2.0), rel=2e-2)


def test_attributes_preserve_missing_samples() -> None:
    data = np.ones((64, 4), dtype=np.float32)
    data[10:20, 2] = np.nan
    for key in attributes_module.ATTRIBUTE_NAMES:
        out = attributes_module.compute_attribute(data, 2.0, key)
        assert out.shape == data.shape
        assert np.all(np.isnan(out[10:20, 2]))


def test_volume_semblance_uses_true_spatial_aperture_and_preserves_missing_bins() -> None:
    dt_ms = 2.0
    time_s = np.arange(256, dtype=np.float64) * dt_ms / 1000.0
    trace = np.sin(2.0 * np.pi * 20.0 * time_s).astype(np.float32)
    volume = np.broadcast_to(trace, (5, 7, trace.size)).copy()
    volume[2, 3, :] = np.nan

    coherence = attributes_module.volume_semblance(volume, dt_ms, window_ms=32.0, spatial_radius=1)
    assert coherence.shape == volume.shape
    assert float(np.nanmedian(coherence[1:4, 1:6, 40:-40])) == pytest.approx(1.0, rel=1e-5)
    assert np.all(np.isnan(coherence[2, 3, :]))

    envelope = attributes_module.compute_volume_attribute(volume, dt_ms, "envelope")
    assert envelope.shape == volume.shape
    assert np.all(np.isnan(envelope[2, 3, :]))


def test_unified_segy_sections_keep_one_global_physical_time_axis(tmp_path: Path) -> None:
    from modules.seismic.visualization.data_source import UnifiedSeismicDataSource
    from modules.seismic.visualization.models import SectionRequest

    file_path = tmp_path / "global_time_grid.sgy"
    _write_rev21(file_path)
    source = UnifiedSeismicDataSource(file_path)
    try:
        first = source.read_section(SectionRequest(trace_start=0, trace_count=1, sample_start=0, sample_count=source.total_samples))
        second = source.read_section(SectionRequest(trace_start=1, trace_count=1, sample_start=0, sample_count=source.total_samples))
        np.testing.assert_allclose(first.time_ms, second.time_ms)
        assert first.time_ms[0] == pytest.approx(13.0)
        assert np.isfinite(first.amplitudes[0, 0])
        assert np.isnan(second.amplitudes[0, 0])
    finally:
        source.close()


def test_volume_rgba_keeps_missing_voxels_fully_transparent() -> None:
    from modules.seismic.visualization.processing import normalized_rgba_volume

    volume = np.ones((3, 4, 5), dtype=np.float32)
    volume[1, 2, 3] = np.nan
    rgba = normalized_rgba_volume(volume, opacity=0.5)
    assert rgba.shape == (3, 4, 5, 4)
    assert int(rgba[1, 2, 3, 3]) == 0
    assert int(np.max(rgba[..., 3])) > 0
