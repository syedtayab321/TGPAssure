from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage, QColor
from typing import Optional, Dict, Any

class Rasterizer:
    DISPLAY_WIGGLE = "wiggle"
    DISPLAY_VARIABLE_DENSITY = "variable_density"
    DISPLAY_VARIABLE_AREA = "variable_area"

    def __init__(self) -> None:
        pass

    def to_qimage(self, array: np.ndarray, display_mode: str, colormap: np.ndarray, 
                  width: Optional[int] = None, height: Optional[int] = None) -> QImage:
        if array.size == 0:
            return QImage()
        
        if display_mode == self.DISPLAY_WIGGLE:
            return self._to_wiggle_qimage(array, width, height)
        elif display_mode == self.DISPLAY_VARIABLE_DENSITY:
            return self._to_variable_density_qimage(array, colormap, width, height)
        elif display_mode == self.DISPLAY_VARIABLE_AREA:
            return self._to_variable_area_qimage(array, width, height)
        else:
            return self._to_variable_density_qimage(array, colormap, width, height)

    def _to_variable_density_qimage(self, array: np.ndarray, colormap: np.ndarray, 
                                     width: Optional[int] = None, height: Optional[int] = None) -> QImage:
        if array.ndim == 1:
            img_array = self._normalize_array(array)
            if height is None:
                height = len(img_array)
            if width is None:
                width = 1
            img_array = img_array.reshape(1, -1)
        elif array.ndim == 2:
            img_array = self._normalize_array(array)
            if height is None:
                height = img_array.shape[0]
            if width is None:
                width = img_array.shape[1]
        else:
            img_array = self._normalize_array(array)
            if height is None:
                height = img_array.shape[0]
            if width is None:
                width = img_array.shape[1]
            if array.ndim == 3 and array.shape[1] == 1:
                img_array = img_array[:, 0, :]
        
        img_array = self._resize_array(img_array, height, width)
        
        img_array = np.clip(img_array, 0, 1)
        img_array = (img_array * 255).astype(np.uint8)
        
        indices = img_array.astype(np.int16)
        indices = np.clip(indices, 0, len(colormap) - 1)
        
        colored = colormap[indices]
        
        if colored.ndim == 2:
            colored = colored.reshape(height, width, 3)
        
        colored = colored.astype(np.uint8)
        
        if colored.shape[2] == 3:
            rgb_array = np.zeros((height, width, 4), dtype=np.uint8)
            rgb_array[:, :, 0] = colored[:, :, 0]
            rgb_array[:, :, 1] = colored[:, :, 1]
            rgb_array[:, :, 2] = colored[:, :, 2]
            rgb_array[:, :, 3] = 255
            colored = rgb_array
        
        qimage = QImage(colored.data, width, height, width * 4, QImage.Format_RGBA8888)
        return qimage.copy()

    def _to_wiggle_qimage(self, array: np.ndarray, width: Optional[int] = None, height: Optional[int] = None) -> QImage:
        if array.ndim == 1:
            return QImage()
        
        if height is None:
            height = array.shape[0]
        if width is None:
            width = array.shape[1] if array.ndim == 2 else array.shape[2]
        
        if array.ndim == 3 and array.shape[1] == 1:
            data = array[:, 0, :]
        else:
            data = array
        
        qimage = QImage(width, height, QImage.Format_RGB32)
        
        for y in range(height):
            for x in range(width):
                val = data[y, x] if y < data.shape[0] and x < data.shape[1] else 0
                intensity = int((np.clip(val, -1, 1) + 1) * 127)
                color = QColor(intensity, intensity, intensity)
                qimage.setPixel(x, y, color.rgb())
        
        return qimage

    def _to_variable_area_qimage(self, array: np.ndarray, width: Optional[int] = None, height: Optional[int] = None) -> QImage:
        if array.ndim == 1:
            return QImage()
        
        if height is None:
            height = array.shape[0]
        if width is None:
            width = array.shape[1] if array.ndim == 2 else array.shape[2]
        
        if array.ndim == 3 and array.shape[1] == 1:
            data = array[:, 0, :]
        else:
            data = array
        
        qimage = QImage(width, height, QImage.Format_RGB32)
        
        for y in range(height):
            for x in range(width):
                val = data[y, x] if y < data.shape[0] and x < data.shape[1] else 0
                if val > 0:
                    intensity = int(np.clip(val * 127, 0, 255))
                    color = QColor(intensity, intensity, intensity)
                else:
                    color = QColor(255, 255, 255)
                qimage.setPixel(x, y, color.rgb())
        
        return qimage

    def _normalize_array(self, array: np.ndarray) -> np.ndarray:
        if array.size == 0:
            return array
        
        min_val = np.min(array)
        max_val = np.max(array)
        
        if max_val - min_val > 0:
            return (array - min_val) / (max_val - min_val)
        return array

    def _resize_array(self, array: np.ndarray, target_height: int, target_width: int) -> np.ndarray:
        """Resize a display array without Python pixel loops.

        Seismic decimation happens before rasterization, so deterministic nearest
        index mapping is appropriate here and avoids the previous per-pixel mean
        loop that dominated 800x600 render latency.
        """
        if array.ndim == 1:
            return array
        if target_height <= 0 or target_width <= 0:
            return np.empty((0, 0), dtype=array.dtype)
        current_height, current_width = array.shape[:2]
        if current_height == target_height and current_width == target_width:
            return array
        if current_height == 0 or current_width == 0:
            return np.empty((target_height, target_width), dtype=array.dtype)

        row_index = np.minimum(
            (np.arange(target_height, dtype=np.float64) * current_height / target_height).astype(np.intp),
            current_height - 1,
        )
        col_index = np.minimum(
            (np.arange(target_width, dtype=np.float64) * current_width / target_width).astype(np.intp),
            current_width - 1,
        )
        return np.ascontiguousarray(array[np.ix_(row_index, col_index)])
