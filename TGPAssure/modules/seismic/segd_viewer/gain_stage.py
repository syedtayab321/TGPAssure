from __future__ import annotations

import numpy as np
from typing import Optional, Dict, Any, Union

class GainStage:
    MODE_NONE = "none"
    MODE_FIXED = "fixed"
    MODE_AGC = "agc"
    MODE_TRACE_BALANCE = "trace_balance"

    def __init__(self) -> None:
        pass

    def apply(self, array: np.ndarray, gain_mode: str, params: Optional[Dict[str, Any]] = None) -> np.ndarray:
        if array.size == 0:
            return array
        
        params = params or {}
        
        if gain_mode == self.MODE_NONE:
            return array
        elif gain_mode == self.MODE_FIXED:
            return self._apply_fixed_gain(array, params.get("db", 0.0))
        elif gain_mode == self.MODE_AGC:
            return self._apply_agc(array, params.get("window_length", 100))
        elif gain_mode == self.MODE_TRACE_BALANCE:
            return self._apply_trace_balance(array)
        else:
            return array

    def _apply_fixed_gain(self, array: np.ndarray, db: float) -> np.ndarray:
        gain = 10 ** (db / 20.0)
        return array * gain

    def _apply_agc(self, array: np.ndarray, window_length: int) -> np.ndarray:
        if window_length <= 1:
            return array
        
        if array.ndim == 1:
            return self._apply_agc_1d(array, window_length)
        elif array.ndim == 2:
            return self._apply_agc_2d(array, window_length)
        elif array.ndim == 3:
            return self._apply_agc_3d(array, window_length)
        else:
            return array

    def _apply_agc_1d(self, array: np.ndarray, window_length: int) -> np.ndarray:
        result = np.zeros_like(array)
        half_window = window_length // 2
        
        for i in range(len(array)):
            start = max(0, i - half_window)
            end = min(len(array), i + half_window + 1)
            window = array[start:end]
            rms = np.sqrt(np.mean(window ** 2))
            if rms > 0:
                result[i] = array[i] / rms
            else:
                result[i] = array[i]
        
        return result

    def _apply_agc_2d(self, array: np.ndarray, window_length: int) -> np.ndarray:
        result = np.zeros_like(array)
        half_window = window_length // 2
        
        for i in range(array.shape[0]):
            start = max(0, i - half_window)
            end = min(array.shape[0], i + half_window + 1)
            window = array[start:end, :]
            rms = np.sqrt(np.mean(window ** 2))
            if rms > 0:
                result[i, :] = array[i, :] / rms
            else:
                result[i, :] = array[i, :]
        
        return result

    def _apply_agc_3d(self, array: np.ndarray, window_length: int) -> np.ndarray:
        result = np.zeros_like(array)
        half_window = window_length // 2
        
        for i in range(array.shape[0]):
            start = max(0, i - half_window)
            end = min(array.shape[0], i + half_window + 1)
            window = array[start:end, :, :]
            rms = np.sqrt(np.mean(window ** 2))
            if rms > 0:
                result[i, :, :] = array[i, :, :] / rms
            else:
                result[i, :, :] = array[i, :, :]
        
        return result

    def _apply_trace_balance(self, array: np.ndarray) -> np.ndarray:
        if array.ndim == 1:
            rms = np.sqrt(np.mean(array ** 2))
            if rms > 0:
                return array / rms
            return array
        elif array.ndim == 2:
            result = np.zeros_like(array)
            for i in range(array.shape[0]):
                rms = np.sqrt(np.mean(array[i, :] ** 2))
                if rms > 0:
                    result[i, :] = array[i, :] / rms
                else:
                    result[i, :] = array[i, :]
            return result
        elif array.ndim == 3:
            result = np.zeros_like(array)
            for i in range(array.shape[0]):
                for j in range(array.shape[1]):
                    rms = np.sqrt(np.mean(array[i, j, :] ** 2))
                    if rms > 0:
                        result[i, j, :] = array[i, j, :] / rms
                    else:
                        result[i, j, :] = array[i, j, :]
            return result
        else:
            return array