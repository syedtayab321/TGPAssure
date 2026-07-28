from __future__ import annotations

import numpy as np
from typing import Dict, Any, Optional

class ColormapRegistry:
    def __init__(self) -> None:
        self._colormaps: Dict[str, np.ndarray] = {}
        self._register_builtin_colormaps()

    def _register_builtin_colormaps(self) -> None:
        self._colormaps["grayscale"] = self._create_grayscale()
        self._colormaps["seismic"] = self._create_seismic()
        self._colormaps["seismic_reversed"] = self._create_seismic_reversed()
        self._colormaps["rainbow"] = self._create_rainbow()
        self._colormaps["viridis"] = self._create_viridis()
        self._colormaps["hot"] = self._create_hot()
        self._colormaps["cool"] = self._create_cool()

    def _create_grayscale(self) -> np.ndarray:
        colormap = np.zeros((256, 3), dtype=np.uint8)
        for i in range(256):
            colormap[i, :] = i
        return colormap

    def _create_seismic(self) -> np.ndarray:
        colormap = np.zeros((256, 3), dtype=np.uint8)
        for i in range(256):
            t = i / 255.0
            if t < 0.5:
                r = int((0.5 - t) * 2 * 255)
                g = int((0.5 - t) * 2 * 50)
                b = int(255 - t * 255)
            else:
                r = int(t * 255)
                g = int((t - 0.5) * 2 * 50)
                b = int((1 - t) * 2 * 255)
            colormap[i, 0] = np.clip(r, 0, 255)
            colormap[i, 1] = np.clip(g, 0, 255)
            colormap[i, 2] = np.clip(b, 0, 255)
        return colormap

    def _create_seismic_reversed(self) -> np.ndarray:
        colormap = self._create_seismic()
        return colormap[::-1]

    def _create_rainbow(self) -> np.ndarray:
        colormap = np.zeros((256, 3), dtype=np.uint8)
        for i in range(256):
            t = i / 255.0
            r = int(np.sin(t * 2 * np.pi + 0) * 127 + 128)
            g = int(np.sin(t * 2 * np.pi + 2 * np.pi / 3) * 127 + 128)
            b = int(np.sin(t * 2 * np.pi + 4 * np.pi / 3) * 127 + 128)
            colormap[i, 0] = np.clip(r, 0, 255)
            colormap[i, 1] = np.clip(g, 0, 255)
            colormap[i, 2] = np.clip(b, 0, 255)
        return colormap

    def _create_viridis(self) -> np.ndarray:
        colormap = np.zeros((256, 3), dtype=np.uint8)
        viridis_colors = [
            (68, 1, 84), (71, 18, 122), (69, 40, 149), (64, 62, 166),
            (55, 84, 176), (46, 104, 180), (38, 124, 178), (33, 144, 171),
            (33, 163, 158), (44, 180, 139), (66, 195, 116), (98, 208, 89),
            (138, 219, 61), (182, 226, 38), (226, 231, 35), (253, 231, 37)
        ]
        for i in range(256):
            idx = int(i / 255.0 * 15)
            color = viridis_colors[idx]
            colormap[i, 0] = color[0]
            colormap[i, 1] = color[1]
            colormap[i, 2] = color[2]
        return colormap

    def _create_hot(self) -> np.ndarray:
        colormap = np.zeros((256, 3), dtype=np.uint8)
        for i in range(256):
            t = i / 255.0
            if t < 0.33:
                r = int(t / 0.33 * 255)
                g = 0
                b = 0
            elif t < 0.66:
                r = 255
                g = int((t - 0.33) / 0.33 * 255)
                b = 0
            else:
                r = 255
                g = 255
                b = int((t - 0.66) / 0.34 * 255)
            colormap[i, 0] = np.clip(r, 0, 255)
            colormap[i, 1] = np.clip(g, 0, 255)
            colormap[i, 2] = np.clip(b, 0, 255)
        return colormap

    def _create_cool(self) -> np.ndarray:
        colormap = np.zeros((256, 3), dtype=np.uint8)
        for i in range(256):
            t = i / 255.0
            r = int(t * 255)
            g = int((1 - t) * 255)
            b = int(255)
            colormap[i, 0] = np.clip(r, 0, 255)
            colormap[i, 1] = np.clip(g, 0, 255)
            colormap[i, 2] = np.clip(b, 0, 255)
        return colormap

    def register(self, name: str, colormap: np.ndarray) -> None:
        self._colormaps[name] = colormap

    def get(self, name: str) -> Optional[np.ndarray]:
        return self._colormaps.get(name)

    def list(self) -> list[str]:
        return list(self._colormaps.keys())

    def get_default(self) -> np.ndarray:
        return self._colormaps["seismic"]