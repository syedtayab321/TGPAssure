from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

from core.domain.qc_engine import QCFinding, QCStatus


class MagneticSurveyType(str, Enum):
    GROUND = "ground"
    AIRBORNE = "airborne"
    DRONE = "drone"
    MARINE = "marine"
    BASE_STATION = "base_station"


class MagneticLineType(str, Enum):
    TRAVERSE = "traverse"
    TIE = "tie"
    REPEAT = "repeat"
    CONTROL = "control"
    BASE = "base"
    UNKNOWN = "unknown"


class MagneticDataRole(str, Enum):
    ROVER = "rover"
    BASE = "base"
    PROCESSED = "processed"
    GRID = "grid"
    BOUNDARY = "boundary"
    CONTROL = "control"


@dataclass(frozen=True)
class ChannelProvenance:
    channel: str
    parent_channel: str | None
    operation: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def as_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "parent_channel": self.parent_channel,
            "operation": self.operation,
            "parameters": dict(self.parameters),
            "created_at": self.created_at,
        }


@dataclass
class MagneticDataset:
    source_path: Path
    role: MagneticDataRole
    survey_type: MagneticSurveyType
    timestamps: np.ndarray
    channels: dict[str, np.ndarray]
    x: np.ndarray | None = None
    y: np.ndarray | None = None
    elevation: np.ndarray | None = None
    line_id: np.ndarray | None = None
    station_id: np.ndarray | None = None
    line_type: np.ndarray | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    crs: str | None = None
    coordinate_units: str = "m"
    magnetic_units: str = "nT"
    provenance: list[ChannelProvenance] = field(default_factory=list)
    quality_flags: dict[str, np.ndarray] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.source_path = Path(self.source_path)
        self.timestamps = np.asarray(self.timestamps, dtype="datetime64[ms]")
        n = int(self.timestamps.size)
        if n == 0:
            raise ValueError("Magnetic dataset contains no records")
        self.channels = {name: np.asarray(values, dtype=float) for name, values in self.channels.items()}
        for name, values in self.channels.items():
            if values.ndim != 1 or values.size != n:
                raise ValueError(f"Channel '{name}' must contain exactly {n} one-dimensional values")
        self.x = self._normalise_optional(self.x, n, float, np.nan)
        self.y = self._normalise_optional(self.y, n, float, np.nan)
        self.elevation = self._normalise_optional(self.elevation, n, float, np.nan)
        self.line_id = self._normalise_optional(self.line_id, n, object, "")
        self.station_id = self._normalise_optional(self.station_id, n, object, "")
        self.line_type = self._normalise_optional(self.line_type, n, object, MagneticLineType.UNKNOWN.value)
        for key, mask in list(self.quality_flags.items()):
            values = np.asarray(mask, dtype=bool)
            if values.size != n:
                raise ValueError(f"Quality mask '{key}' must contain {n} values")
            self.quality_flags[key] = values

    @staticmethod
    def _normalise_optional(values: np.ndarray | Iterable[Any] | None, n: int, dtype: Any, fill: Any) -> np.ndarray:
        if values is None:
            return np.full(n, fill, dtype=dtype)
        array = np.asarray(values, dtype=dtype)
        if array.ndim != 1 or array.size != n:
            raise ValueError(f"Dataset column must contain exactly {n} one-dimensional values")
        return array

    @property
    def record_count(self) -> int:
        return int(self.timestamps.size)

    @property
    def channel_names(self) -> tuple[str, ...]:
        return tuple(self.channels.keys())

    @property
    def checksum(self) -> str:
        digest = hashlib.sha256()
        if self.source_path.exists():
            with self.source_path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            return digest.hexdigest()
        digest.update(self.timestamps.astype("int64").tobytes())
        for name in sorted(self.channels):
            digest.update(name.encode("utf-8"))
            digest.update(np.nan_to_num(self.channels[name], nan=0.0).tobytes())
        return digest.hexdigest()

    def channel(self, name: str) -> np.ndarray:
        try:
            return self.channels[name]
        except KeyError as exc:
            raise KeyError(f"Magnetic channel '{name}' is not available") from exc

    def first_available_channel(self, names: Iterable[str]) -> tuple[str, np.ndarray]:
        for name in names:
            if name in self.channels:
                return name, self.channels[name]
        raise KeyError(f"None of the requested magnetic channels are available: {', '.join(names)}")

    def add_derived_channel(
        self,
        name: str,
        values: np.ndarray | Iterable[float],
        *,
        parent_channel: str | None,
        operation: str,
        parameters: Mapping[str, Any] | None = None,
        overwrite: bool = False,
    ) -> None:
        if name in self.channels and not overwrite:
            raise ValueError(f"Channel '{name}' already exists")
        array = np.asarray(values, dtype=float)
        if array.ndim != 1 or array.size != self.record_count:
            raise ValueError(f"Derived channel '{name}' must contain {self.record_count} values")
        self.channels[name] = array.copy()
        self.provenance.append(
            ChannelProvenance(
                channel=name,
                parent_channel=parent_channel,
                operation=operation,
                parameters=dict(parameters or {}),
            )
        )

    def set_quality_flag(self, name: str, mask: np.ndarray | Iterable[bool]) -> None:
        values = np.asarray(mask, dtype=bool)
        if values.size != self.record_count:
            raise ValueError(f"Quality mask '{name}' must contain {self.record_count} values")
        self.quality_flags[name] = values

    def valid_coordinate_mask(self) -> np.ndarray:
        return np.isfinite(self.x) & np.isfinite(self.y)

    def valid_timestamp_mask(self) -> np.ndarray:
        return ~np.isnat(self.timestamps)

    def line_groups(self) -> dict[str, np.ndarray]:
        groups: dict[str, np.ndarray] = {}
        for line in np.unique(self.line_id.astype(str)):
            if line:
                groups[line] = np.flatnonzero(self.line_id.astype(str) == line)
        return groups

    def bounds(self) -> dict[str, float | None]:
        mask = self.valid_coordinate_mask()
        if not np.any(mask):
            return {"min_x": None, "max_x": None, "min_y": None, "max_y": None}
        return {
            "min_x": float(np.nanmin(self.x[mask])),
            "max_x": float(np.nanmax(self.x[mask])),
            "min_y": float(np.nanmin(self.y[mask])),
            "max_y": float(np.nanmax(self.y[mask])),
        }

    def time_bounds(self) -> tuple[str | None, str | None]:
        mask = self.valid_timestamp_mask()
        if not np.any(mask):
            return None, None
        values = self.timestamps[mask]
        return str(values.min()), str(values.max())

    def summary(self) -> dict[str, Any]:
        start, end = self.time_bounds()
        line_values = self.line_id.astype(str)
        return {
            "source_path": str(self.source_path),
            "role": self.role.value,
            "survey_type": self.survey_type.value,
            "record_count": self.record_count,
            "channels": list(self.channel_names),
            "line_count": int(len({v for v in line_values if v})),
            "crs": self.crs,
            "coordinate_units": self.coordinate_units,
            "magnetic_units": self.magnetic_units,
            "start_time": start,
            "end_time": end,
            "bounds": self.bounds(),
            "checksum": self.checksum,
            "metadata": self.metadata,
            "provenance": [entry.as_dict() for entry in self.provenance],
        }


@dataclass
class MagneticBoundary:
    vertices: np.ndarray
    crs: str | None = None
    name: str = "Survey Boundary"

    def __post_init__(self) -> None:
        self.vertices = np.asarray(self.vertices, dtype=float)
        if self.vertices.ndim != 2 or self.vertices.shape[1] != 2 or self.vertices.shape[0] < 3:
            raise ValueError("Boundary must contain at least three XY vertices")


@dataclass
class MagneticStageOutcome:
    stage_key: str
    display_name: str
    status: QCStatus
    metrics: dict[str, Any] = field(default_factory=dict)
    findings: list[QCFinding] = field(default_factory=list)
    message: str = ""
    duration_ms: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage_key": self.stage_key,
            "display_name": self.display_name,
            "status": self.status.value,
            "metrics": self.metrics,
            "findings": [
                {
                    "rule_id": finding.rule_id,
                    "severity": finding.severity.value,
                    "message": finding.message,
                    "location_ref": finding.location_ref,
                    "suggested_action": finding.suggested_action,
                    "metadata": json.loads(finding.metadata_json or "{}"),
                }
                for finding in self.findings
            ],
            "message": self.message,
            "duration_ms": self.duration_ms,
        }


@dataclass
class MagneticRunResult:
    run_uuid: str
    profile_name: str
    status: QCStatus
    score: float
    stage_outcomes: list[MagneticStageOutcome]
    summary: dict[str, Any]
    started_at: str
    completed_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_uuid": self.run_uuid,
            "profile_name": self.profile_name,
            "status": self.status.value,
            "score": self.score,
            "stage_outcomes": [stage.as_dict() for stage in self.stage_outcomes],
            "summary": self.summary,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }
