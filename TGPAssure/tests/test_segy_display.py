import importlib.util
import pathlib
import sys

import numpy as np

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "modules" / "seismic" / "segy_viewer" / "segy_display.py"
SPEC = importlib.util.spec_from_file_location("tgp_segy_display_testmodule", MODULE_PATH)
DISPLAY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = DISPLAY
SPEC.loader.exec_module(DISPLAY)


def test_modal_interval_is_used_for_display_grid():
    assert DISPLAY.choose_display_interval_ms([2000, 2000, 4000]) == 2.0


def test_time_grid_respects_delay_and_variable_trace_length():
    grid = DISPLAY.build_time_grid([3, 4], [2000, 1000], [100, 98])
    assert grid.start_ms == 98.0
    assert grid.interval_ms == 1.0
    assert grid.end_ms == 104.0
    assert grid.sample_count == 7


def test_alignment_uses_true_trace_delay_and_does_not_zero_fill_missing_samples():
    grid = DISPLAY.build_time_grid([3, 3], [1000, 1000], [0, 2])
    out = DISPLAY.align_traces_to_time_grid(
        [np.array([1.0, 2.0, 3.0]), np.array([10.0, 20.0, 30.0])],
        [1000, 1000],
        [0, 2],
        grid,
    )
    assert np.allclose(out[0, :3], [1, 2, 3], equal_nan=True)
    assert np.isnan(out[0, 3:]).all()
    assert np.isnan(out[1, :2]).all()
    assert np.allclose(out[1, 2:], [10, 20, 30], equal_nan=True)


def test_trace_balance_ignores_nan_padding():
    data = np.array([[3.0, 4.0, np.nan]], dtype=np.float32)
    out = DISPLAY.apply_display_gain(data, "balance", 1.0)
    expected_rms = np.sqrt((9 + 16) / 2)
    assert np.allclose(out[0, :2], np.array([3.0, 4.0]) / expected_rms)
    assert np.isnan(out[0, 2])
