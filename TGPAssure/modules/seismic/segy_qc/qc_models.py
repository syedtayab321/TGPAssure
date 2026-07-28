from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SegyFinding:
    code: str
    severity: str
    category: str
    title: str
    description: str
    metric_name: Optional[str] = None
    observed_value: Optional[float] = None
    expected_min: Optional[float] = None
    expected_max: Optional[float] = None
    unit: Optional[str] = None
    trace_index: Optional[int] = None
    line_id: Optional[str] = None
    station_id: Optional[str] = None
    location_x: Optional[float] = None
    location_y: Optional[float] = None
    suggested_action: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SegyStageOutcome:
    key: str
    name: str
    status: str
    score: float
    metrics: Dict[str, Any] = field(default_factory=dict)
    findings: List[SegyFinding] = field(default_factory=list)
    message: str = ""
    duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["findings"] = [finding.to_dict() for finding in self.findings]
        return data


@dataclass
class SegyRunSummary:
    run_uuid: str
    file_path: str
    file_name: str
    profile_key: str
    profile_name: str
    status: str
    overall_result: str
    score: float
    trace_count: int
    sample_count: int
    sample_interval_us: float
    stage_count: int
    finding_count: int
    severity_counts: Dict[str, int]
    started_at: str
    completed_at: str
    duration_ms: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
