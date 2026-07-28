from __future__ import annotations

import numpy as np
from typing import Tuple, Optional

class Decimator:
    def __init__(self) -> None:
        pass

    def reduce(self, array: np.ndarray, pixels_available: int) -> np.ndarray:
        if array.size == 0 or pixels_available <= 0:
            return array
        
        if array.ndim == 1:
            return self._reduce_1d(array, pixels_available)
        elif array.ndim == 2:
            return self._reduce_2d(array, pixels_available)
        elif array.ndim == 3:
            return self._reduce_3d(array, pixels_available)
        else:
            return array

    def _reduce_1d(self, array: np.ndarray, pixels_available: int) -> np.ndarray:
        n = len(array)
        if n <= pixels_available:
            return array
        
        chunk_size = n // pixels_available
        if chunk_size <= 1:
            return array
        
        result = np.zeros(pixels_available * 2, dtype=array.dtype)
        
        for i in range(pixels_available):
            start = i * chunk_size
            end = min(start + chunk_size, n)
            chunk = array[start:end]
            if len(chunk) > 0:
                result[i * 2] = np.min(chunk)
                result[i * 2 + 1] = np.max(chunk)
        
        return result

    def _reduce_2d(self, array: np.ndarray, pixels_available: int) -> np.ndarray:
        n, m = array.shape
        if n <= pixels_available:
            return array
        
        chunk_size = n // pixels_available
        if chunk_size <= 1:
            return array
        
        result = np.zeros((pixels_available * 2, m), dtype=array.dtype)
        
        for i in range(pixels_available):
            start = i * chunk_size
            end = min(start + chunk_size, n)
            chunk = array[start:end, :]
            if len(chunk) > 0:
                result[i * 2, :] = np.min(chunk, axis=0)
                result[i * 2 + 1, :] = np.max(chunk, axis=0)
        
        return result

    def _reduce_3d(self, array: np.ndarray, pixels_available: int) -> np.ndarray:
        n, channels, m = array.shape
        if n <= pixels_available:
            return array
        
        chunk_size = n // pixels_available
        if chunk_size <= 1:
            return array
        
        result = np.zeros((pixels_available * 2, channels, m), dtype=array.dtype)
        
        for i in range(pixels_available):
            start = i * chunk_size
            end = min(start + chunk_size, n)
            chunk = array[start:end, :, :]
            if len(chunk) > 0:
                result[i * 2, :, :] = np.min(chunk, axis=0)
                result[i * 2 + 1, :, :] = np.max(chunk, axis=0)
        
        return result

    def reduce_to_width(self, array: np.ndarray, width_pixels: int, height_pixels: Optional[int] = None) -> np.ndarray:
        if array.size == 0 or width_pixels <= 0:
            return array
        
        if height_pixels is None:
            height_pixels = width_pixels
        
        if array.ndim == 1:
            return self._reduce_1d_to_width(array, width_pixels)
        elif array.ndim == 2:
            return self._reduce_2d_to_dimensions(array, height_pixels, width_pixels)
        elif array.ndim == 3:
            return self._reduce_3d_to_dimensions(array, height_pixels, width_pixels)
        else:
            return array

    def _reduce_1d_to_width(self, array: np.ndarray, width_pixels: int) -> np.ndarray:
        n = len(array)
        if n <= width_pixels:
            return array
        
        chunk_size = n // width_pixels
        if chunk_size <= 1:
            return array
        
        result = np.zeros(width_pixels * 2, dtype=array.dtype)
        
        for i in range(width_pixels):
            start = i * chunk_size
            end = min(start + chunk_size, n)
            chunk = array[start:end]
            if len(chunk) > 0:
                result[i * 2] = np.min(chunk)
                result[i * 2 + 1] = np.max(chunk)
        
        return result

    def _reduce_2d_to_dimensions(self, array: np.ndarray, height_pixels: int, width_pixels: int) -> np.ndarray:
        n, m = array.shape
        
        if n <= height_pixels and m <= width_pixels:
            return array
        
        row_chunk = n // height_pixels if n > height_pixels else 1
        col_chunk = m // width_pixels if m > width_pixels else 1
        
        if row_chunk <= 1 and col_chunk <= 1:
            return array
        
        result_height = height_pixels * 2 if row_chunk > 1 else n
        result_width = width_pixels * 2 if col_chunk > 1 else m
        
        result = np.zeros((result_height, result_width), dtype=array.dtype)
        
        for i in range(height_pixels):
            row_start = i * row_chunk
            row_end = min(row_start + row_chunk, n)
            for j in range(width_pixels):
                col_start = j * col_chunk
                col_end = min(col_start + col_chunk, m)
                chunk = array[row_start:row_end, col_start:col_end]
                if chunk.size > 0:
                    result[i * 2, j * 2] = np.min(chunk)
                    result[i * 2 + 1, j * 2] = np.max(chunk)
        
        return result

    def _reduce_3d_to_dimensions(self, array: np.ndarray, height_pixels: int, width_pixels: int) -> np.ndarray:
        n, channels, m = array.shape
        
        if n <= height_pixels and m <= width_pixels:
            return array
        
        row_chunk = n // height_pixels if n > height_pixels else 1
        col_chunk = m // width_pixels if m > width_pixels else 1
        
        if row_chunk <= 1 and col_chunk <= 1:
            return array
        
        result_height = height_pixels * 2 if row_chunk > 1 else n
        result_width = width_pixels * 2 if col_chunk > 1 else m
        
        result = np.zeros((result_height, channels, result_width), dtype=array.dtype)
        
        for i in range(height_pixels):
            row_start = i * row_chunk
            row_end = min(row_start + row_chunk, n)
            for j in range(width_pixels):
                col_start = j * col_chunk
                col_end = min(col_start + col_chunk, m)
                chunk = array[row_start:row_end, :, col_start:col_end]
                if chunk.size > 0:
                    result[i * 2, :, j * 2] = np.min(chunk, axis=(0, 2))
                    result[i * 2 + 1, :, j * 2] = np.max(chunk, axis=(0, 2))
        
        return result