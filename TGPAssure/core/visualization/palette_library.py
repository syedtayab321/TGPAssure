from __future__ import annotations

"""Application-wide color-palette library.

This module is deliberately Qt-free so QC engines, reports, NumPy rendering,
PyQtGraph, Matplotlib and headless tests can all share one authoritative color
table registry.  The palette catalog is the same catalog that originally
powered TraceWaveform FT Analysis.
"""

from functools import lru_cache

import numpy as np

DEFAULT_PALETTE = "Seismic"

COLOR_PALETTES: dict[str, list[str]] = {'Seismic': ['#122452', '#1260A0', '#13A6B9', '#FFD54F', '#DA3C2D'],
 'Seismic Blue-White-Red': ['#191970', '#1E90FF', '#F0F8FF', '#FF6347', '#8B0000'],
 'Viridis': ['#440154', '#31688E', '#35B779', '#FDE725'],
 'Grayscale': ['#000000', '#404040', '#808080', '#BFBFBF', '#FFFFFF'],
 'Blue Ice': ['#071A2F', '#0F4C81', '#1FA2FF', '#A7F3D0', '#FFFFFF'],
 'Copper Heat': ['#1C1210', '#7C2D12', '#EA580C', '#FDBA74', '#FFF7ED'],
 'Rainbow': ['#FF0000', '#FF7F00', '#FFFF00', '#00FF00', '#0000FF', '#8B00FF'],
 'Hot': ['#000000', '#7F0000', '#FF0000', '#FF7F00', '#FFFF00', '#FFFFFF'],
 'Cool': ['#0000FF', '#00FFFF', '#00FF00', '#FFFF00', '#FF0000'],
 'Jet': ['#00008F', '#0000FF', '#0080FF', '#00FFFF', '#80FF80', '#FFFF00', '#FF8000', '#FF0000', '#800000'],
 'Ocean': ['#000040', '#000080', '#0080C0', '#00C0FF', '#80E0FF', '#FFFFFF'],
 'Terrain': ['#004400', '#008000', '#90C090', '#C0C080', '#E0E080', '#FFFFFF'],
 'Spectral': ['#0000FF', '#0080FF', '#00FFFF', '#00FF80', '#80FF00', '#FFFF00', '#FF8000', '#FF0080', '#FF0000'],
 'NEO (Night Earth)': ['#000000',
                       '#001020',
                       '#004060',
                       '#0080A0',
                       '#00C0E0',
                       '#FFFFFF',
                       '#FFE080',
                       '#FFA040',
                       '#FF4000'],
 'Volumetric Picker': ['#000000',
                       '#000080',
                       '#0040C0',
                       '#0080FF',
                       '#80C0FF',
                       '#FFFFFF',
                       '#FFC080',
                       '#FF8000',
                       '#C04000',
                       '#800000'],
 'Seismic Dip Azimuth': ['#FF0000', '#FF8000', '#FFFF00', '#00FF00', '#00FFFF', '#0080FF', '#FF00FF', '#FF0080'],
 'SeismicRWB': ['#0000FF', '#0080FF', '#00FFFF', '#FFFFFF', '#FFFF00', '#FF8000', '#FF0000'],
 'Red Blue Green': ['#FF0000', '#FF80FF', '#FFFFFF', '#80FFFF', '#00FF00'],
 'Green Blue Red': ['#00FF00', '#80FFFF', '#FFFFFF', '#FF80FF', '#FF0000'],
 'Polarity': ['#0000FF', '#0080FF', '#FFFFFF', '#FF8000', '#FF0000'],
 'Semblance': ['#000000', '#004080', '#0080FF', '#00FFFF', '#00FF80', '#80FF00', '#FFFF00', '#FF8000', '#FF0000'],
 'Reflection Strength': ['#FFFFFF', '#80FF80', '#00FF00', '#008000', '#004000', '#000000'],
 'Variance': ['#000000', '#003F5C', '#7A5195', '#EF5675', '#FF7C43', '#F9A93D', '#FFD166'],
 'Local Flatness': ['#0000FF', '#0080FF', '#00FFFF', '#00FF80', '#80FF00', '#FFFF00', '#FF8000', '#FF0000'],
 'Structural Lows': ['#000000', '#001040', '#003080', '#0060C0', '#00A0FF', '#80D0FF', '#FFFFFF'],
 'Thickness': ['#FFFFFF', '#FFE0A0', '#FFC040', '#FF8000', '#A04000', '#400000'],
 'Uncertainty': ['#FFFFFF', '#C0E0FF', '#80C0FF', '#4080FF', '#0040FF', '#0000A0'],
 'Velocity': ['#000000',
              '#000040',
              '#000080',
              '#0040C0',
              '#0080FF',
              '#00FFFF',
              '#80FF80',
              '#FFFF00',
              '#FF8000',
              '#FF0000'],
 'Resistivity': ['#000000',
                 '#800000',
                 '#FF0000',
                 '#FF8000',
                 '#FFFF00',
                 '#80FF80',
                 '#00FFFF',
                 '#0080FF',
                 '#0000FF',
                 '#400080'],
 'Permeability': ['#FFFFFF', '#FFE0C0', '#FFA080', '#FF6040', '#D02000', '#800000'],
 'Water Saturation': ['#000000', '#000080', '#0040C0', '#0080FF', '#40C0FF', '#80E0FF', '#FFFFFF'],
 'Vitrinite Reflectance': ['#000000', '#003000', '#006000', '#00A000', '#40C040', '#80E080', '#FFFFFF'],
 'Gold': ['#000000', '#402000', '#804000', '#BF8000', '#FFBF00', '#FFFFFF'],
 'Gold White Blue': ['#000000', '#402000', '#804000', '#BF8000', '#FFBF00', '#FFFFFF', '#80C0FF', '#0080FF', '#004080'],
 'White Blue': ['#FFFFFF', '#80C0FF', '#0080FF', '#004080', '#000080'],
 'White Blue Green': ['#FFFFFF', '#80C0FF', '#0080FF', '#00A0A0', '#008000'],
 'White Grey Blue': ['#FFFFFF', '#C0C0C0', '#808080', '#4080C0', '#004080'],
 'White Red': ['#FFFFFF', '#FFC0C0', '#FF8080', '#FF4040', '#FF0000'],
 'White Yellow': ['#FFFFFF', '#FFFFC0', '#FFFF80', '#FFFF00', '#BF8000'],
 'Red Yellow Green': ['#FF0000', '#FF8000', '#FFFF00', '#80FF00', '#00FF00'],
 'Red White Blue': ['#FF0000', '#FF8080', '#FFFFFF', '#8080FF', '#0000FF'],
 'Red White Blue (Reverse)': ['#0000FF', '#8080FF', '#FFFFFF', '#FF8080', '#FF0000'],
 'Red White Blue (Blocky)': ['#FF0000',
                             '#FF4444',
                             '#FF8888',
                             '#FFCCCC',
                             '#FFFFFF',
                             '#CCCCFF',
                             '#8888FF',
                             '#4444FF',
                             '#0000FF'],
 'Blue White Red': ['#0000FF', '#8080FF', '#FFFFFF', '#FF8080', '#FF0000'],
 'Blue White Red (Blocky)': ['#0000FF',
                             '#4444FF',
                             '#8888FF',
                             '#CCCCFF',
                             '#FFFFFF',
                             '#FFCCCC',
                             '#FF8888',
                             '#FF4444',
                             '#FF0000'],
 'White Black Red': ['#FFFFFF', '#C0C0C0', '#808080', '#404040', '#800000', '#FF0000'],
 'White Black Red (Anti)': ['#FFFFFF', '#C0C0C0', '#808080', '#404040', '#800000', '#FF0000', '#FF8000'],
 'Red White Black': ['#FF0000', '#FF8080', '#FFFFFF', '#808080', '#000000'],
 'Green Yellow Red': ['#00FF00', '#80FF00', '#FFFF00', '#FF8000', '#FF0000'],
 'Green Blue Brown': ['#004000', '#008000', '#00C000', '#40A0A0', '#808080', '#A06040', '#804020'],
 'Purple Blue Green': ['#800080', '#4000C0', '#0080FF', '#00C0C0', '#00FF00'],
 'Purple Blue Green (Reverse)': ['#00FF00', '#00C0C0', '#0080FF', '#4000C0', '#800080'],
 'Purple Green Red': ['#800080', '#4000C0', '#00C0A0', '#80FF80', '#FFFF00', '#FF8000', '#FF0000'],
 'YellowFMS': ['#000000',
               '#004000',
               '#008000',
               '#00C000',
               '#C0C000',
               '#FFFF00',
               '#FFC000',
               '#FF8000',
               '#FF4000',
               '#FF0000'],
 'YellowFMS-GR': ['#000000',
                  '#004000',
                  '#008000',
                  '#00C000',
                  '#C0C000',
                  '#FFFF00',
                  '#FFC000',
                  '#FF8000',
                  '#FF4000',
                  '#FF0000',
                  '#FF0080',
                  '#FF00FF'],
 'YellowFMS-PEF': ['#FFFFFF', '#FFFF80', '#FFFF00', '#FFC000', '#FF8000', '#FF4000', '#FF0000', '#800000'],
 'YellowFMS-R': ['#FFFFFF', '#FFE0E0', '#FFC0C0', '#FF8080', '#FF4040', '#FF0000', '#800000'],
 'YellowFMS-T': ['#FFFFFF', '#FFE0C0', '#FFC080', '#FF8040', '#FF4000', '#800000'],
 'GrayLU': ['#000000', '#202020', '#404040', '#606060', '#808080', '#A0A0A0', '#C0C0C0', '#E0E0E0', '#FFFFFF'],
 'SunbowLU': ['#000000', '#0000FF', '#00FFFF', '#00FF00', '#FFFF00', '#FF0000', '#FFFFFF'],
 'RainbowLU': ['#0000FF', '#0080FF', '#00FFFF', '#00FF80', '#80FF00', '#FFFF00', '#FF8000', '#FF0000'],
 'Sunny Side Up': ['#000040',
                   '#000080',
                   '#0040C0',
                   '#0080FF',
                   '#40C0FF',
                   '#80FFFF',
                   '#FFFF80',
                   '#FFE080',
                   '#FFC040',
                   '#FF8000'],
 'Spectrum': ['#000000', '#0000FF', '#00FFFF', '#00FF00', '#FFFF00', '#FF8000', '#FF0000'],
 'Log Rainbow': ['#0000FF', '#0080FF', '#00FFFF', '#00FF80', '#80FF00', '#FFFF00', '#FF8000', '#FF0000'],
 'Log VDL': ['#000000', '#004000', '#008000', '#00C000', '#C0C000', '#FFFF00', '#FF8000', '#FF0000'],
 'Log Sand & Shale': ['#FFE0A0',
                      '#FFD080',
                      '#FFC060',
                      '#FFA040',
                      '#FF8020',
                      '#C06020',
                      '#804020',
                      '#402010',
                      '#000000'],
 'Log Seismic': ['#0000FF', '#0080FF', '#00FFFF', '#FFFFFF', '#FFFF00', '#FF8000', '#FF0000'],
 'Map Blocked': ['#0000FF', '#0080FF', '#00FFFF', '#00FF80', '#80FF00', '#FFFF00', '#FF8000', '#FF0000']}


def palette_names() -> tuple[str, ...]:
    return tuple(COLOR_PALETTES)


def _normalise_name(name: str | None) -> str:
    return str(name or DEFAULT_PALETTE) if str(name or DEFAULT_PALETTE) in COLOR_PALETTES else DEFAULT_PALETTE


@lru_cache(maxsize=256)
def _cached_rgb(name: str, samples: int) -> np.ndarray:
    name = _normalise_name(name)
    samples = max(2, int(samples))
    colors = COLOR_PALETTES[name]
    rgb = np.asarray([[int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)] for c in colors], dtype=np.float64)
    if len(rgb) == 1:
        return np.repeat(rgb.astype(np.uint8), samples, axis=0)
    positions = np.linspace(0.0, 1.0, len(rgb), dtype=np.float64)
    target = np.linspace(0.0, 1.0, samples, dtype=np.float64)
    result = np.column_stack([np.interp(target, positions, rgb[:, channel]) for channel in range(3)])
    return np.clip(np.rint(result), 0, 255).astype(np.uint8)


def palette_rgb_array(name: str = DEFAULT_PALETTE, samples: int = 256) -> np.ndarray:
    """Return a defensive RGB LUT copy for callers that may mutate the array."""
    return _cached_rgb(_normalise_name(name), max(2, int(samples))).copy()


def palette_rgba_array(values_01: np.ndarray, name: str = DEFAULT_PALETTE) -> np.ndarray:
    """Map normalized scalar values to an RGBA uint8 array using the global LUT."""
    values = np.clip(np.asarray(values_01, dtype=float), 0.0, 1.0)
    lut = _cached_rgb(_normalise_name(name), 256)
    indices = np.clip(np.rint(values * (len(lut) - 1)).astype(np.int64), 0, len(lut) - 1)
    rgb = lut[indices]
    alpha = np.full(values.shape + (1,), 255, dtype=np.uint8)
    return np.concatenate((rgb, alpha), axis=-1)


def palette_hex(name: str = DEFAULT_PALETTE, fraction: float = 0.5) -> str:
    """Return the interpolated color at *fraction* as #RRGGBB."""
    lut = _cached_rgb(_normalise_name(name), 256)
    idx = int(np.clip(round(float(fraction) * (len(lut) - 1)), 0, len(lut) - 1))
    r, g, b = (int(v) for v in lut[idx])
    return f"#{r:02X}{g:02X}{b:02X}"
