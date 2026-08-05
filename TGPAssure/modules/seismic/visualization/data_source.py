from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING, Any, Hashable

import numpy as np

from core.data_access.db_engine import DatabaseEngine
from modules.seismic.segy_reader import SegyReader, SegyTraceIndex
from modules.seismic.segy_viewer.segy_display import (
    DisplayGrid,
    align_traces_to_time_grid,
    build_time_grid,
)
from modules.seismic.visualization.models import QcTraceFlag, SectionData, SectionRequest, VolumeData

if TYPE_CHECKING:
    from modules.seismic.segd_viewer.segd_reader import SegdReader


class _ArrayCache:
    def __init__(self, maximum_items: int = 8) -> None:
        self.maximum_items = max(1, int(maximum_items))
        self._items: OrderedDict[Hashable, Any] = OrderedDict()
        self._lock = threading.RLock()

    def get(self, key: Hashable) -> Any | None:
        with self._lock:
            value = self._items.get(key)
            if value is not None:
                self._items.move_to_end(key)
            return value

    def put(self, key: Hashable, value: Any) -> Any:
        with self._lock:
            self._items[key] = value
            self._items.move_to_end(key)
            while len(self._items) > self.maximum_items:
                self._items.popitem(last=False)
        return value

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


class UnifiedSeismicDataSource:
    SEG_Y_EXTENSIONS = {".sgy", ".segy"}
    SEG_D_EXTENSIONS = {".segd", ".sgd", ".d", ".dat"}

    def __init__(self, file_path: str | Path, database_engine: DatabaseEngine | None = None) -> None:
        self.file_path = Path(file_path).expanduser().resolve()
        if not self.file_path.exists():
            raise FileNotFoundError(f"Seismic file not found: {self.file_path}")
        suffix = self.file_path.suffix.lower()
        if suffix in self.SEG_Y_EXTENSIONS:
            self.format_name = "SEG-Y"
            self._reader: Any = SegyReader(self.file_path)
            self._segy_index: SegyTraceIndex | None = None
            self._segy_display_grid: DisplayGrid | None = None
        elif suffix in self.SEG_D_EXTENSIONS:
            from modules.seismic.segd_viewer.segd_reader import SegdReader

            self.format_name = "SEG-D"
            self._reader = SegdReader(self.file_path)
            self._segy_index = None
            self._segy_display_grid = None
        else:
            raise ValueError(f"Unsupported seismic format: {suffix or self.file_path.name}")
        self.database_engine = database_engine
        self._cache = _ArrayCache(10)
        self._lock = threading.RLock()

    @property
    def is_segy(self) -> bool:
        return isinstance(self._reader, SegyReader)

    @property
    def is_segd(self) -> bool:
        return self.format_name == "SEG-D"

    @property
    def total_traces(self) -> int:
        if self.is_segy:
            return self._index().trace_count
        return int(self._reader.get_trace_count())

    @property
    def total_samples(self) -> int:
        if self.is_segy:
            return int(self._time_grid().sample_count)
        return int(self._reader.get_sample_count())

    @property
    def sample_interval_ms(self) -> float:
        if self.is_segy:
            return float(self._time_grid().interval_ms)
        return float(self._reader.get_sample_interval())

    def _time_grid(self) -> DisplayGrid:
        if not self.is_segy:
            raise TypeError("Physical SEG-Y time grid is only available for SEG-Y data")
        with self._lock:
            if self._segy_display_grid is None:
                index = self._index()
                self._segy_display_grid = build_time_grid(
                    index.sample_counts,
                    index.sample_intervals_us,
                    index.delay_time_ms,
                )
            return self._segy_display_grid

    @property
    def has_3d_geometry(self) -> bool:
        if not self.is_segy:
            return False
        index = self._index()
        valid = (index.inline_3d != 0) & (index.crossline_3d != 0)
        return bool(np.count_nonzero(valid) >= 4 and np.unique(index.inline_3d[valid]).size > 1)

    def _index(self) -> SegyTraceIndex:
        if not self.is_segy:
            raise TypeError("Trace index is only available for SEG-Y")
        with self._lock:
            if self._segy_index is None:
                self._segy_index = self._reader.scan_trace_headers()
            return self._segy_index

    def metadata(self) -> dict[str, Any]:
        if self.is_segy:
            index = self._index()
            return {
                **self._reader.file_info(),
                "format": self.format_name,
                "trace_count": index.trace_count,
                "sample_count": self.total_samples,
                "nominal_samples_per_trace": int(self._reader.binary_header.samples_per_trace),
                "sample_interval_ms": self.sample_interval_ms,
                "time_start_ms": float(self._time_grid().start_ms),
                "time_end_ms": float(self._time_grid().end_ms),
                "has_3d_geometry": self.has_3d_geometry,
                "inline_count": int(np.unique(index.inline_3d[index.inline_3d != 0]).size),
                "crossline_count": int(np.unique(index.crossline_3d[index.crossline_3d != 0]).size),
            }
        return {
            **self._reader.metadata_summary(),
            "format": self.format_name,
            "has_3d_geometry": False,
        }

    def read_section(self, request: SectionRequest) -> SectionData:
        normalized = request.normalized(self.total_traces, self.total_samples)
        key = (
            "section",
            normalized.trace_start,
            normalized.trace_count,
            normalized.sample_start,
            normalized.sample_count,
            normalized.trace_decimation,
            normalized.sample_decimation,
        )
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        trace_stop = min(self.total_traces, normalized.trace_start + normalized.trace_count)
        trace_indices = np.arange(
            normalized.trace_start,
            trace_stop,
            normalized.trace_decimation,
            dtype=np.int64,
        )
        sample_stop = min(self.total_samples, normalized.sample_start + normalized.sample_count)
        sample_indices = np.arange(
            normalized.sample_start,
            sample_stop,
            normalized.sample_decimation,
            dtype=np.int64,
        )
        if self.is_segy:
            section = self._read_segy_section(trace_indices, sample_indices)
        else:
            section = self._read_segd_section(trace_indices, sample_indices)
        return self._cache.put(key, section)

    def _read_segy_section(self, trace_indices: np.ndarray, sample_indices: np.ndarray) -> SectionData:
        """Read a SEG-Y section on a physically correct common time grid.

        Trace-header delay time, variable sample interval and variable trace
        length are honoured. Missing coverage is represented by NaN rather
        than zero, preventing false flat events at trace ends.
        """
        index = self._index()
        if trace_indices.size == 0 or sample_indices.size == 0:
            data = np.empty((sample_indices.size, trace_indices.size), dtype=np.float32)
            time_ms = np.empty(sample_indices.size, dtype=np.float64)
        else:
            counts = index.sample_counts[trace_indices]
            intervals_us = index.sample_intervals_us[trace_indices]
            delays_ms = index.delay_time_ms[trace_indices]
            grid = self._time_grid()
            traces = [self._reader.read_trace(int(trace_index), index) for trace_index in trace_indices]
            first_sample = int(sample_indices[0])
            sample_step = int(sample_indices[1] - sample_indices[0]) if sample_indices.size > 1 else 1
            requested_stop = min(grid.sample_count, int(sample_indices[-1]) + 1)
            if first_sample >= grid.sample_count or requested_stop <= first_sample:
                data = np.full((sample_indices.size, trace_indices.size), np.nan, dtype=np.float32)
                time_ms = grid.start_ms + sample_indices.astype(np.float64) * grid.interval_ms
            else:
                aligned = align_traces_to_time_grid(
                    traces,
                    intervals_us,
                    delays_ms,
                    grid,
                    start_sample=first_sample,
                    end_sample=requested_stop,
                )
                selected = aligned[:, ::sample_step]
                data = selected.T.astype(np.float32, copy=False)
                actual_indices = first_sample + np.arange(data.shape[0], dtype=np.int64) * sample_step
                time_ms = grid.start_ms + actual_indices.astype(np.float64) * grid.interval_ms
                # Preserve the requested array shape when a window extends beyond
                # the available common time grid. This keeps UI range controls stable.
                if data.shape[0] < sample_indices.size:
                    padded = np.full((sample_indices.size, trace_indices.size), np.nan, dtype=np.float32)
                    padded[: data.shape[0], :] = data
                    data = padded
                    time_ms = grid.start_ms + sample_indices.astype(np.float64) * grid.interval_ms
        cdp = index.cdp[trace_indices].astype(np.int64)
        shot = np.where(index.shotpoint[trace_indices] != 0, index.shotpoint[trace_indices], index.field_record[trace_indices]).astype(np.int64)
        inline_values = index.inline_3d[trace_indices].astype(np.int64)
        crossline_values = index.crossline_3d[trace_indices].astype(np.int64)
        cdp_x = index.cdp_x[trace_indices].astype(np.float64)
        cdp_y = index.cdp_y[trace_indices].astype(np.float64)
        midpoint_x = 0.5 * (index.source_x[trace_indices] + index.receiver_x[trace_indices])
        midpoint_y = 0.5 * (index.source_y[trace_indices] + index.receiver_y[trace_indices])
        x = np.where(np.isfinite(cdp_x) & (cdp_x != 0), cdp_x, midpoint_x)
        y = np.where(np.isfinite(cdp_y) & (cdp_y != 0), cdp_y, midpoint_y)
        labels = self._labels(cdp, shot, inline_values, crossline_values, trace_indices)
        return SectionData(
            amplitudes=data,
            trace_indices=trace_indices,
            sample_indices=sample_indices,
            time_ms=time_ms,
            labels=labels,
            x_coordinates=x.astype(np.float64),
            y_coordinates=y.astype(np.float64),
            inline_values=inline_values,
            crossline_values=crossline_values,
            cdp_values=cdp,
            shot_values=shot,
            sample_interval_ms=(float(np.median(np.diff(time_ms))) if time_ms.size > 1 else self.sample_interval_ms),
            source_path=str(self.file_path),
        )

    def _read_segd_section(self, trace_indices: np.ndarray, sample_indices: np.ndarray) -> SectionData:
        if trace_indices.size == 0 or sample_indices.size == 0:
            data = np.empty((sample_indices.size, trace_indices.size), dtype=np.float32)
            headers = np.empty(0)
        else:
            trace_start = int(trace_indices[0])
            trace_stop = int(trace_indices[-1]) + 1
            sample_start = int(sample_indices[0])
            sample_stop = int(sample_indices[-1]) + 1
            raw = self._reader.read_channel_data((trace_start, trace_stop), 0, (sample_start, sample_stop))
            trace_step = int(trace_indices[1] - trace_indices[0]) if trace_indices.size > 1 else 1
            sample_step = int(sample_indices[1] - sample_indices[0]) if sample_indices.size > 1 else 1
            data = raw[::trace_step, ::sample_step].T.astype(np.float32, copy=False)
            headers = self._reader.read_trace_headers((trace_start, trace_stop))[::trace_step]
        if headers.size:
            receiver_line = headers["receiver_line"].astype(np.int64)
            receiver_point = headers["receiver_point"].astype(np.int64)
            shot = headers["file_number"].astype(np.int64)
            labels = [
                f"RL {int(line)} / RP {int(point)}" if int(point) else f"Trace {int(trace) + 1}"
                for trace, line, point in zip(trace_indices, receiver_line, receiver_point)
            ]
            x = receiver_point.astype(np.float64)
            y = receiver_line.astype(np.float64)
        else:
            receiver_line = np.zeros(trace_indices.size, dtype=np.int64)
            receiver_point = np.zeros(trace_indices.size, dtype=np.int64)
            shot = np.zeros(trace_indices.size, dtype=np.int64)
            labels = [f"Trace {int(value) + 1}" for value in trace_indices]
            x = trace_indices.astype(np.float64)
            y = np.zeros(trace_indices.size, dtype=np.float64)
        return SectionData(
            amplitudes=data,
            trace_indices=trace_indices,
            sample_indices=sample_indices,
            time_ms=sample_indices.astype(np.float64) * self.sample_interval_ms,
            labels=labels,
            x_coordinates=x,
            y_coordinates=y,
            inline_values=receiver_line,
            crossline_values=receiver_point,
            cdp_values=np.zeros(trace_indices.size, dtype=np.int64),
            shot_values=shot,
            sample_interval_ms=(
                self.sample_interval_ms * (int(sample_indices[1] - sample_indices[0]) if sample_indices.size > 1 else 1)
            ),
            source_path=str(self.file_path),
        )

    @staticmethod
    def _labels(
        cdp: np.ndarray,
        shot: np.ndarray,
        inline_values: np.ndarray,
        crossline_values: np.ndarray,
        trace_indices: np.ndarray,
    ) -> list[str]:
        labels: list[str] = []
        for column, trace_index in enumerate(trace_indices):
            if inline_values[column] and crossline_values[column]:
                labels.append(f"IL {int(inline_values[column])} / XL {int(crossline_values[column])}")
            elif cdp[column]:
                labels.append(f"CDP {int(cdp[column])}")
            elif shot[column]:
                labels.append(f"Shot {int(shot[column])}")
            else:
                labels.append(f"Trace {int(trace_index) + 1}")
        return labels

    def geometry(self, maximum_points: int = 100_000) -> dict[str, np.ndarray]:
        key = ("geometry", int(maximum_points))
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        stride = max(1, int(np.ceil(self.total_traces / max(1, maximum_points))))
        trace_indices = np.arange(0, self.total_traces, stride, dtype=np.int64)
        if self.is_segy:
            index = self._index()
            cdp_x = index.cdp_x[trace_indices].astype(np.float64)
            cdp_y = index.cdp_y[trace_indices].astype(np.float64)
            midpoint_x = 0.5 * (index.source_x[trace_indices] + index.receiver_x[trace_indices])
            midpoint_y = 0.5 * (index.source_y[trace_indices] + index.receiver_y[trace_indices])
            result = {
                "trace_indices": trace_indices,
                "source_x": index.source_x[trace_indices].astype(np.float64),
                "source_y": index.source_y[trace_indices].astype(np.float64),
                "receiver_x": index.receiver_x[trace_indices].astype(np.float64),
                "receiver_y": index.receiver_y[trace_indices].astype(np.float64),
                "midpoint_x": np.where(cdp_x != 0, cdp_x, midpoint_x),
                "midpoint_y": np.where(cdp_y != 0, cdp_y, midpoint_y),
                "inline": index.inline_3d[trace_indices].astype(np.int64),
                "crossline": index.crossline_3d[trace_indices].astype(np.int64),
                "cdp": index.cdp[trace_indices].astype(np.int64),
                "shot": index.shotpoint[trace_indices].astype(np.int64),
                "offset": index.offsets[trace_indices].astype(np.float64),
                "coordinate_units": index.coordinate_units[trace_indices].astype(np.int32),
            }
        else:
            headers = self._reader.read_trace_headers((0, self.total_traces))[::stride]
            point = headers["receiver_point"].astype(np.float64)
            line = headers["receiver_line"].astype(np.float64)
            result = {
                "trace_indices": trace_indices,
                "source_x": np.zeros(trace_indices.size),
                "source_y": np.zeros(trace_indices.size),
                "receiver_x": point,
                "receiver_y": line,
                "midpoint_x": point,
                "midpoint_y": line,
                "inline": line.astype(np.int64),
                "crossline": point.astype(np.int64),
                "cdp": np.zeros(trace_indices.size, dtype=np.int64),
                "shot": headers["file_number"].astype(np.int64),
                "offset": np.zeros(trace_indices.size),
                "coordinate_units": np.zeros(trace_indices.size, dtype=np.int32),
            }
        return self._cache.put(key, result)

    def load_volume(
        self,
        max_inlines: int = 96,
        max_crosslines: int = 128,
        max_samples: int = 512,
    ) -> VolumeData:
        key = ("volume", int(max_inlines), int(max_crosslines), int(max_samples))
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        if self.has_3d_geometry:
            volume = self._load_true_volume(max_inlines, max_crosslines, max_samples)
        else:
            volume = self._load_pseudo_volume(max_crosslines, max_samples)
        return self._cache.put(key, volume)

    def _load_true_volume(self, max_inlines: int, max_crosslines: int, max_samples: int) -> VolumeData:
        index = self._index()
        valid = (index.inline_3d != 0) & (index.crossline_3d != 0)
        all_inlines = np.unique(index.inline_3d[valid]).astype(np.int64)
        all_crosslines = np.unique(index.crossline_3d[valid]).astype(np.int64)
        inline_step = max(1, int(np.ceil(all_inlines.size / max(1, max_inlines))))
        crossline_step = max(1, int(np.ceil(all_crosslines.size / max(1, max_crosslines))))
        inline_values = all_inlines[::inline_step]
        crossline_values = all_crosslines[::crossline_step]
        inline_lookup = {int(value): position for position, value in enumerate(inline_values)}
        crossline_lookup = {int(value): position for position, value in enumerate(crossline_values)}
        selected_trace_indices = np.flatnonzero(
            valid
            & np.isin(index.inline_3d, inline_values)
            & np.isin(index.crossline_3d, crossline_values)
        )
        if selected_trace_indices.size == 0:
            raise ValueError("No traces remain after 3D inline/crossline decimation")

        # Establish a common physical time axis from each trace's delay time,
        # sample interval and sample count before any volume decimation.
        full_grid = self._time_grid()
        sample_step = max(1, int(np.ceil(full_grid.sample_count / max(1, max_samples))))
        grid_interval = full_grid.interval_ms * sample_step
        grid_count = max(1, int(np.ceil((full_grid.sample_count - 1) / sample_step)) + 1)
        grid = DisplayGrid(
            start_ms=full_grid.start_ms,
            end_ms=full_grid.start_ms + (grid_count - 1) * grid_interval,
            interval_ms=grid_interval,
            sample_count=grid_count,
        )
        volume = np.full(
            (inline_values.size, crossline_values.size, grid.sample_count),
            np.nan,
            dtype=np.float32,
        )
        x_grid = np.full((inline_values.size, crossline_values.size), np.nan, dtype=np.float64)
        y_grid = np.full((inline_values.size, crossline_values.size), np.nan, dtype=np.float64)
        occupied = np.zeros((inline_values.size, crossline_values.size), dtype=bool)

        for trace_index in selected_trace_indices:
            inline = int(index.inline_3d[trace_index])
            crossline = int(index.crossline_3d[trace_index])
            inline_position = inline_lookup[inline]
            crossline_position = crossline_lookup[crossline]
            # Never perform an implicit stack when duplicate IL/XL bins exist.
            # The first indexed trace remains the deterministic display source;
            # duplicate-bin resolution is an explicit QC/processing decision.
            if occupied[inline_position, crossline_position]:
                continue
            trace = self._reader.read_trace(int(trace_index), index)
            volume[inline_position, crossline_position, :] = align_traces_to_time_grid(
                [trace],
                [int(index.sample_intervals_us[trace_index])],
                [int(index.delay_time_ms[trace_index])],
                grid,
            )[0]
            occupied[inline_position, crossline_position] = True
            cdp_x = float(index.cdp_x[trace_index])
            cdp_y = float(index.cdp_y[trace_index])
            if not np.isfinite(cdp_x) or not np.isfinite(cdp_y) or (cdp_x == 0.0 and cdp_y == 0.0):
                cdp_x = 0.5 * (float(index.source_x[trace_index]) + float(index.receiver_x[trace_index]))
                cdp_y = 0.5 * (float(index.source_y[trace_index]) + float(index.receiver_y[trace_index]))
            x_grid[inline_position, crossline_position] = cdp_x
            y_grid[inline_position, crossline_position] = cdp_y

        time_ms = grid.start_ms + np.arange(grid.sample_count, dtype=np.float64) * grid.interval_ms
        return VolumeData(
            amplitudes=volume,
            inline_values=inline_values,
            crossline_values=crossline_values,
            time_ms=time_ms,
            sample_interval_ms=grid.interval_ms,
            source_path=str(self.file_path),
            is_pseudo_volume=False,
            x_coordinates=x_grid,
            y_coordinates=y_grid,
        )

    def _load_pseudo_volume(self, max_traces: int, max_samples: int) -> VolumeData:
        trace_step = max(1, int(np.ceil(self.total_traces / max(2, max_traces))))
        sample_step = max(1, int(np.ceil(self.total_samples / max(2, max_samples))))
        request = SectionRequest(
            trace_start=0,
            trace_count=self.total_traces,
            sample_start=0,
            sample_count=self.total_samples,
            trace_decimation=trace_step,
            sample_decimation=sample_step,
        )
        section = self.read_section(request)
        curtain = section.amplitudes.T.astype(np.float32, copy=False)
        thickness = 10
        weights = 1.0 - 0.08 * np.abs(np.linspace(-1.0, 1.0, thickness, dtype=np.float32))
        volume = curtain[None, :, :] * weights[:, None, None]
        x_grid = np.repeat(section.x_coordinates[None, :], thickness, axis=0)
        y_grid = np.repeat(section.y_coordinates[None, :], thickness, axis=0)
        return VolumeData(
            amplitudes=volume.astype(np.float32, copy=False),
            inline_values=np.arange(thickness, dtype=np.int64),
            crossline_values=section.trace_indices.astype(np.int64),
            time_ms=section.time_ms,
            sample_interval_ms=section.sample_interval_ms,
            source_path=str(self.file_path),
            is_pseudo_volume=True,
            x_coordinates=x_grid,
            y_coordinates=y_grid,
        )

    def extract_inline(self, volume: VolumeData, inline_position: int) -> np.ndarray:
        position = max(0, min(int(inline_position), volume.amplitudes.shape[0] - 1))
        return volume.amplitudes[position, :, :].T

    def extract_crossline(self, volume: VolumeData, crossline_position: int) -> np.ndarray:
        position = max(0, min(int(crossline_position), volume.amplitudes.shape[1] - 1))
        return volume.amplitudes[:, position, :].T

    def extract_time_slice(self, volume: VolumeData, sample_position: int) -> np.ndarray:
        position = max(0, min(int(sample_position), volume.amplitudes.shape[2] - 1))
        return volume.amplitudes[:, :, position]

    def load_existing_qc_flags(self) -> list[QcTraceFlag]:
        """Manual viewer build: old automated repository integration removed."""
        return []

    def close(self) -> None:
        self._cache.clear()
        close = getattr(self._reader, "close", None)
        if callable(close):
            close()
