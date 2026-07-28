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


class GravitySurveyType(str, Enum):
    LAND = "land"
    MARINE = "marine"
    AIRBORNE = "airborne"
    BASE_STATION = "base_station"


class GravityDataRole(str, Enum):
    OBSERVATIONS = "observations"
    BASE = "base"
    PROCESSED = "processed"
    GRID = "grid"


@dataclass(frozen=True)
class GravityChannelProvenance:
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
class GravityDataset:
    source_path: Path
    role: GravityDataRole
    survey_type: GravitySurveyType
    timestamps: np.ndarray
    channels: dict[str, np.ndarray]
    latitude: np.ndarray | None = None
    longitude: np.ndarray | None = None
    elevation: np.ndarray | None = None
    x: np.ndarray | None = None
    y: np.ndarray | None = None
    station_id: np.ndarray | None = None
    line_id: np.ndarray | None = None
    is_base: np.ndarray | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    crs: str | None = "EPSG:4326"
    gravity_units: str = "mGal"
    elevation_units: str = "m"
    provenance: list[GravityChannelProvenance] = field(default_factory=list)
    quality_flags: dict[str, np.ndarray] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.source_path = Path(self.source_path)
        self.timestamps = np.asarray(self.timestamps, dtype="datetime64[ms]")
        n = int(self.timestamps.size)
        if n == 0:
            raise ValueError("Gravity dataset contains no records")
        normalized: dict[str, np.ndarray] = {}
        for name, values in self.channels.items():
            arr = np.asarray(values, dtype=float)
            if arr.ndim != 1 or arr.size != n:
                raise ValueError(f"Channel '{name}' must contain exactly {n} one-dimensional values")
            normalized[name] = arr
        self.channels = normalized
        self.latitude = self._optional(self.latitude, n, float, np.nan)
        self.longitude = self._optional(self.longitude, n, float, np.nan)
        self.elevation = self._optional(self.elevation, n, float, np.nan)
        self.x = self._optional(self.x, n, float, np.nan)
        self.y = self._optional(self.y, n, float, np.nan)
        self.station_id = self._optional(self.station_id, n, object, "")
        self.line_id = self._optional(self.line_id, n, object, "")
        self.is_base = self._optional(self.is_base, n, bool, self.role == GravityDataRole.BASE)
        for key, mask in list(self.quality_flags.items()):
            values = np.asarray(mask, dtype=bool)
            if values.size != n:
                raise ValueError(f"Quality mask '{key}' must contain {n} values")
            self.quality_flags[key] = values

    @staticmethod
    def _optional(values: Iterable[Any] | np.ndarray | None, n: int, dtype: Any, fill: Any) -> np.ndarray:
        if values is None:
            return np.full(n, fill, dtype=dtype)
        arr = np.asarray(values, dtype=dtype)
        if arr.ndim != 1 or arr.size != n:
            raise ValueError(f"Dataset column must contain exactly {n} one-dimensional values")
        return arr

    @property
    def record_count(self) -> int:
        return int(self.timestamps.size)

    @property
    def station_count(self) -> int:
        values = {str(v).strip() for v in self.station_id if str(v).strip()}
        return len(values) if values else self.record_count

    @property
    def line_count(self) -> int:
        return len({str(v).strip() for v in self.line_id if str(v).strip()})

    @property
    def channel_names(self) -> tuple[str, ...]:
        return tuple(self.channels.keys())

    @property
    def checksum(self) -> str:
        digest = hashlib.sha256()
        if self.source_path.exists() and self.source_path.is_file():
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
        if name not in self.channels:
            raise KeyError(f"Gravity channel '{name}' is not available")
        return self.channels[name]

    def add_derived_channel(
        self,
        name: str,
        values: Iterable[float] | np.ndarray,
        *,
        parent_channel: str | None,
        operation: str,
        parameters: Mapping[str, Any] | None = None,
        overwrite: bool = False,
    ) -> None:
        if name in self.channels and not overwrite:
            raise ValueError(f"Channel '{name}' already exists")
        arr = np.asarray(values, dtype=float)
        if arr.ndim != 1 or arr.size != self.record_count:
            raise ValueError(f"Derived channel '{name}' must contain {self.record_count} values")
        self.channels[name] = arr.copy()
        self.provenance.append(
            GravityChannelProvenance(name, parent_channel, operation, dict(parameters or {}))
        )

    def set_quality_flag(self, name: str, values: Iterable[bool] | np.ndarray) -> None:
        mask = np.asarray(values, dtype=bool)
        if mask.size != self.record_count:
            raise ValueError(f"Quality mask '{name}' must contain {self.record_count} values")
        self.quality_flags[name] = mask

    def valid_coordinate_mask(self) -> np.ndarray:
        geog = np.isfinite(self.latitude) & np.isfinite(self.longitude)
        projected = np.isfinite(self.x) & np.isfinite(self.y)
        return geog | projected

    def time_bounds(self) -> tuple[str | None, str | None]:
        mask = ~np.isnat(self.timestamps)
        if not np.any(mask):
            return None, None
        vals = self.timestamps[mask]
        return str(vals.min()), str(vals.max())

    def summary(self) -> dict[str, Any]:
        start, end = self.time_bounds()
        return {
            "source_path": str(self.source_path),
            "role": self.role.value,
            "data_role": self.role.value,
            "survey_type": self.survey_type.value,
            "record_count": self.record_count,
            "station_count": self.station_count,
            "line_count": self.line_count,
            "channels": list(self.channel_names),
            "crs": self.crs,
            "gravity_units": self.gravity_units,
            "elevation_units": self.elevation_units,
            "start_time": start,
            "end_time": end,
            "checksum": self.checksum,
            "metadata": dict(self.metadata),
            "provenance": [p.as_dict() for p in self.provenance],
        }

    def copy(self) -> "GravityDataset":
        return GravityDataset(
            self.source_path,
            self.role,
            self.survey_type,
            self.timestamps.copy(),
            {k: v.copy() for k, v in self.channels.items()},
            latitude=self.latitude.copy(),
            longitude=self.longitude.copy(),
            elevation=self.elevation.copy(),
            x=self.x.copy(),
            y=self.y.copy(),
            station_id=self.station_id.copy(),
            line_id=self.line_id.copy(),
            is_base=self.is_base.copy(),
            metadata=dict(self.metadata),
            crs=self.crs,
            gravity_units=self.gravity_units,
            elevation_units=self.elevation_units,
            provenance=list(self.provenance),
            quality_flags={k: v.copy() for k, v in self.quality_flags.items()},
        )


@dataclass
class GravityStageOutcome:
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
                    "rule_id": f.rule_id,
                    "severity": f.severity.value,
                    "message": f.message,
                    "location_ref": f.location_ref,
                    "suggested_action": f.suggested_action,
                    "metadata": json.loads(f.metadata_json or "{}"),
                }
                for f in self.findings
            ],
            "message": self.message,
            "duration_ms": self.duration_ms,
        }


@dataclass
class GravityRunResult:
    run_uuid: str
    profile_name: str
    status: QCStatus
    score: float
    stage_outcomes: list[GravityStageOutcome]
    summary: dict[str, Any]
    started_at: str
    completed_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_uuid": self.run_uuid,
            "profile_name": self.profile_name,
            "status": self.status.value,
            "score": float(self.score),
            "stage_outcomes": [s.as_dict() for s in self.stage_outcomes],
            "summary": self.summary,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }
