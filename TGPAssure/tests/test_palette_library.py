from __future__ import annotations

import numpy as np

from core.visualization.palette_library import (
    COLOR_PALETTES,
    DEFAULT_PALETTE,
    palette_hex,
    palette_names,
    palette_rgb_array,
    palette_rgba_array,
)


def test_tracewaveform_palette_catalog_is_global_and_complete():
    assert DEFAULT_PALETTE in COLOR_PALETTES
    assert len(COLOR_PALETTES) == 68
    assert set(palette_names()) == set(COLOR_PALETTES)
    for required in ("Seismic", "Spectral", "Resistivity", "Velocity", "Jet", "Viridis"):
        assert required in COLOR_PALETTES


def test_palette_rgb_lut_is_interpolated_and_defensive():
    lut = palette_rgb_array("Seismic", 257)
    assert lut.shape == (257, 3)
    assert lut.dtype == np.uint8
    assert tuple(lut[0]) == (18, 36, 82)
    assert tuple(lut[-1]) == (218, 60, 45)

    # Callers are allowed to mutate their LUT without poisoning the cached source.
    lut[0] = 0
    fresh = palette_rgb_array("Seismic", 257)
    assert tuple(fresh[0]) == (18, 36, 82)


def test_palette_rgba_maps_scalar_values_and_unknown_name_falls_back():
    values = np.array([0.0, 0.5, 1.0], dtype=float)
    rgba = palette_rgba_array(values, "Viridis")
    assert rgba.shape == (3, 4)
    assert rgba.dtype == np.uint8
    assert np.all(rgba[:, 3] == 255)

    fallback = palette_rgb_array("not-a-real-palette", 11)
    default = palette_rgb_array(DEFAULT_PALETTE, 11)
    assert np.array_equal(fallback, default)
    assert palette_hex("not-a-real-palette", 0.25) == palette_hex(DEFAULT_PALETTE, 0.25)
