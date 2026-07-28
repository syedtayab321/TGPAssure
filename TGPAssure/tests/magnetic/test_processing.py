from __future__ import annotations

import numpy as np

from modules.magnetic.constants import (
    DESPIKED_TOTAL_FIELD,
    DIURNAL_CORRECTED_FIELD,
    DIURNAL_CORRECTION,
    LEVELED_FIELD,
    RAW_TOTAL_FIELD,
)
from modules.magnetic.magnetic_processing_engine import MagneticProcessingEngine


def test_processing_preserves_raw_and_creates_provenance(magnetic_datasets):
    rover, base = magnetic_datasets
    original = rover.channel(RAW_TOTAL_FIELD).copy()
    rover.channels[RAW_TOTAL_FIELD][25] += 100.0
    engine = MagneticProcessingEngine()

    mask = engine.despike(rover)
    engine.apply_diurnal_correction(rover, base)
    corrections = engine.level_lines(rover)

    assert mask[25]
    assert DESPIKED_TOTAL_FIELD in rover.channels
    assert DIURNAL_CORRECTION in rover.channels
    assert DIURNAL_CORRECTED_FIELD in rover.channels
    assert LEVELED_FIELD in rover.channels
    assert set(corrections) == {"L001", "L002"}
    assert len(rover.provenance) >= 4
    # The processing engine never replaces the raw channel object with a derived result.
    assert rover.channel(RAW_TOTAL_FIELD)[0] == original[0]


def test_gridding_returns_georeferenced_arrays(magnetic_datasets):
    rover, base = magnetic_datasets
    engine = MagneticProcessingEngine()
    engine.apply_diurnal_correction(rover, base)
    grid = engine.grid(rover, cell_size=25.0)

    assert grid["values"].ndim == 2
    assert grid["values"].shape == (grid["y"].size, grid["x"].size)
    assert grid["cell_size"] == 25.0
    assert grid["crs"] == "EPSG:32643"
    assert np.any(np.isfinite(grid["values"]))
