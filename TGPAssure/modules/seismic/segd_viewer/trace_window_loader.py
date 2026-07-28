from __future__ import annotations

from typing import Optional, Tuple, Dict, Any, List
from collections import OrderedDict
import numpy as np
from pathlib import Path

from modules.seismic.segd_viewer.segd_reader import SegdReader


class LRUCache:
    def __init__(self, max_size: int) -> None:
        self.max_size = max_size
        self.cache = OrderedDict()
        self.current_size = 0

    def get(self, key: Tuple[int, int, int, int]) -> Optional[np.ndarray]:
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        return None

    def put(self, key: Tuple[int, int, int, int], value: np.ndarray) -> None:
        value_size = value.nbytes
        while self.current_size + value_size > self.max_size and len(self.cache) > 0:
            old_key, old_value = self.cache.popitem(last=False)
            self.current_size -= old_value.nbytes
        
        self.cache[key] = value
        self.cache.move_to_end(key)
        self.current_size += value_size

    def clear(self) -> None:
        self.cache.clear()
        self.current_size = 0


class TraceWindowLoader:
    def __init__(self, file_path: Path, memory_budget_mb: int = 512) -> None:
        self.file_path = file_path
        self.memory_budget = memory_budget_mb * 1024 * 1024
        self.reader = SegdReader(file_path)
        self.cache = LRUCache(self.memory_budget)
        self._trace_count = self.reader.get_trace_count()
        self._sample_count = self.reader.get_sample_count()
        self._channel_count = self.reader.get_channel_count()

    def read(self, trace_range: Tuple[int, int], sample_range: Optional[Tuple[int, int]] = None, channel: Optional[int] = None) -> np.ndarray:
        if sample_range is None:
            sample_range = (0, self._sample_count)
        
        cache_key = (trace_range[0], trace_range[1], sample_range[0], sample_range[1], channel if channel is not None else -1)
        
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        
        if channel is not None:
            data = self.reader.read_channel_data(trace_range, channel, sample_range)
        else:
            data = self.reader.read_trace_window(trace_range, sample_range)
        
        self.cache.put(cache_key, data)
        return data

    def get_trace_count(self) -> int:
        return self._trace_count

    def get_sample_count(self) -> int:
        return self._sample_count

    def get_channel_count(self) -> int:
        return self._channel_count

    def get_sample_interval(self) -> int:
        return self.reader.get_sample_interval()

    def clear_cache(self) -> None:
        self.cache.clear()

    def close(self) -> None:
        self.reader.close()
        self.cache.clear()