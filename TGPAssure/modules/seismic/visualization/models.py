from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np


DisplayMode = Literal["wiggle", "variable_density", "wiggle_density"]
InterpretationKind = Literal["horizon", "fault", "measurement", "well_path"]


@dataclass(slots=True)
class SectionRequest:
    trace_start: int = 0
    trace_count: int = 300
    sample_start: int = 0
    sample_count: int = 1500
    trace_decimation: int = 1
    sample_decimation: int = 1

    def normalized(self, total_traces: int, total_samples: int) -> "SectionRequest":
        trace_start = max(0, min(int(self.trace_start), max(0, total_traces - 1)))
        sample_start = max(0, min(int(self.sample_start), max(0, total_samples - 1)))
        trace_count = max(1, min(int(self.trace_count), max(1, total_traces - trace_start)))
        sample_count = max(1, min(int(self.sample_count), max(1, total_samples - sample_start)))
        return SectionRequest(
            trace_start=trace_start,
            trace_count=trace_count,
            sample_start=sample_start,
            sample_count=sample_count,
            trace_decimation=max(1, int(self.trace_decimation)),
            sample_decimation=max(1, int(self.sample_decimation)),
        )


@dataclass(slots=True)
class GainSettings:
    scalar: float = 1.0
    clip_percentile: float = 99.0
    agc_enabled: bool = False
    agc_window_ms: float = 500.0
    normalize_traces: bool = False


@dataclass(slots=True)
class SectionData:
    amplitudes: np.ndarray
    trace_indices: np.ndarray
    sample_indices: np.ndarray
    time_ms: np.ndarray
    labels: list[str]
    x_coordinates: np.ndarray
    y_coordinates: np.ndarray
    inline_values: np.ndarray
    crossline_values: np.ndarray
    cdp_values: np.ndarray
    shot_values: np.ndarray
    sample_interval_ms: float
    source_path: str

    @property
    def trace_count(self) -> int:
        return int(self.amplitudes.shape[1]) if self.amplitudes.ndim == 2 else 0

    @property
    def sample_count(self) -> int:
        return int(self.amplitudes.shape[0]) if self.amplitudes.ndim == 2 else 0


@dataclass(slots=True)
class VolumeData:
    amplitudes: np.ndarray
    inline_values: np.ndarray
    crossline_values: np.ndarray
    time_ms: np.ndarray
    sample_interval_ms: float
    source_path: str
    is_pseudo_volume: bool = False
    x_coordinates: np.ndarray | None = None
    y_coordinates: np.ndarray | None = None

    @property
    def shape(self) -> tuple[int, int, int]:
        return tuple(int(value) for value in self.amplitudes.shape)


@dataclass(slots=True)
class QcTraceFlag:
    trace_index: int
    severity: str
    reason: str
    rms: float
    peak: float
    zero_fraction: float
    clipping_fraction: float
    spike_score: float
    source: str = "visualization"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SpectrumResult:
    frequency_hz: np.ndarray
    mean_amplitude: np.ndarray
    median_amplitude: np.ndarray


@dataclass(slots=True)
class NoiseResult:
    trace_indices: np.ndarray
    rms: np.ndarray
    high_frequency_ratio: np.ndarray
    incoherence: np.ndarray


@dataclass(slots=True)
class InterpretationPoint:
    trace_index: int
    sample_index: int
    time_ms: float
    x: float | None = None
    y: float | None = None
    inline: int | None = None
    crossline: int | None = None
    amplitude: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "InterpretationPoint":
        return cls(
            trace_index=int(payload["trace_index"]),
            sample_index=int(payload["sample_index"]),
            time_ms=float(payload["time_ms"]),
            x=None if payload.get("x") is None else float(payload["x"]),
            y=None if payload.get("y") is None else float(payload["y"]),
            inline=None if payload.get("inline") is None else int(payload["inline"]),
            crossline=None if payload.get("crossline") is None else int(payload["crossline"]),
            amplitude=None if payload.get("amplitude") is None else float(payload["amplitude"]),
        )


@dataclass(slots=True)
class InterpretationObject:
    object_id: str
    name: str
    kind: InterpretationKind
    points: list[InterpretationPoint] = field(default_factory=list)
    visible: bool = True
    color: str = "#00E5FF"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_id": self.object_id,
            "name": self.name,
            "kind": self.kind,
            "points": [point.to_dict() for point in self.points],
            "visible": self.visible,
            "color": self.color,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "InterpretationObject":
        return cls(
            object_id=str(payload["object_id"]),
            name=str(payload["name"]),
            kind=str(payload["kind"]),
            points=[InterpretationPoint.from_dict(item) for item in payload.get("points", [])],
            visible=bool(payload.get("visible", True)),
            color=str(payload.get("color", "#00E5FF")),
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass(slots=True)
class WellPath:
    name: str
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    color: str = "#FFD54F"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "x": self.x.astype(float).tolist(),
            "y": self.y.astype(float).tolist(),
            "z": self.z.astype(float).tolist(),
            "color": self.color,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WellPath":
        return cls(
            name=str(payload["name"]),
            x=np.asarray(payload.get("x", []), dtype=np.float32),
            y=np.asarray(payload.get("y", []), dtype=np.float32),
            z=np.asarray(payload.get("z", []), dtype=np.float32),
            color=str(payload.get("color", "#FFD54F")),
        )


@dataclass(slots=True)
class VisualizationSession:
    session_version: int
    source_path: str
    source_size: int
    source_mtime_ns: int
    display_mode: DisplayMode
    section_request: SectionRequest
    gain_settings: GainSettings
    active_inline: int | None = None
    active_crossline: int | None = None
    active_time_index: int = 0
    opacity: float = 0.35
    interpretations: list[InterpretationObject] = field(default_factory=list)
    wells: list[WellPath] = field(default_factory=list)
    qc_flags: list[QcTraceFlag] = field(default_factory=list)
    ui_state: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_version": self.session_version,
            "source_path": self.source_path,
            "source_size": self.source_size,
            "source_mtime_ns": self.source_mtime_ns,
            "display_mode": self.display_mode,
            "section_request": asdict(self.section_request),
            "gain_settings": asdict(self.gain_settings),
            "active_inline": self.active_inline,
            "active_crossline": self.active_crossline,
            "active_time_index": self.active_time_index,
            "opacity": self.opacity,
            "interpretations": [item.to_dict() for item in self.interpretations],
            "wells": [item.to_dict() for item in self.wells],
            "qc_flags": [item.to_dict() for item in self.qc_flags],
            "ui_state": self.ui_state,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "VisualizationSession":
        return cls(
            session_version=int(payload.get("session_version", 1)),
            source_path=str(payload["source_path"]),
            source_size=int(payload.get("source_size", 0)),
            source_mtime_ns=int(payload.get("source_mtime_ns", 0)),
            display_mode=str(payload.get("display_mode", "wiggle_density")),
            section_request=SectionRequest(**payload.get("section_request", {})),
            gain_settings=GainSettings(**payload.get("gain_settings", {})),
            active_inline=payload.get("active_inline"),
            active_crossline=payload.get("active_crossline"),
            active_time_index=int(payload.get("active_time_index", 0)),
            opacity=float(payload.get("opacity", 0.35)),
            interpretations=[InterpretationObject.from_dict(item) for item in payload.get("interpretations", [])],
            wells=[WellPath.from_dict(item) for item in payload.get("wells", [])],
            qc_flags=[QcTraceFlag(**item) for item in payload.get("qc_flags", [])],
            ui_state=dict(payload.get("ui_state", {})),
        )

    def validate_source(self) -> None:
        path = Path(self.source_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Session source file not found: {path}")
        stat = path.stat()
        if self.source_size and stat.st_size != self.source_size:
            raise ValueError("The seismic source file size differs from the saved session")
