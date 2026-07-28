from __future__ import annotations

from collections import Counter
from statistics import median
from typing import Any


class InstrumentQC:
    GOOD = {"ok", "pass", "ready", "online", "healthy", "active"}
    def apply(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        output=[]; invalid=0; by_instrument=Counter()
        for row in records:
            instrument=str(row.get("instrument_id", "")).strip(); status=str(row.get("status", "")).strip().lower()
            valid=bool(instrument) and status in self.GOOD; invalid += int(not valid); by_instrument[instrument or "<missing>"] += 1
            output.append({**row,"instrument_valid":valid,"normalized_status":status})
        return {"records":output,"invalid_count":invalid,"instrument_counts":dict(by_instrument),"passed":bool(output) and invalid==0}


class TimingQC:
    def __init__(self, tolerance_seconds: float = 1.0, gap_multiplier: float = 3.0) -> None:
        self.tolerance_seconds=float(tolerance_seconds); self.gap_multiplier=float(gap_multiplier)
        if self.tolerance_seconds < 0 or self.gap_multiplier <= 1: raise ValueError("Invalid timing QC thresholds")
    def apply(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        ordered=sorted(records,key=lambda row:row["timestamp"])
        intervals=[(b["timestamp"]-a["timestamp"]).total_seconds() for a,b in zip(ordered,ordered[1:])]
        positive=[v for v in intervals if v>0]; expected=median(positive) if positive else 0.0
        output=[]; invalid=0; gaps=0; duplicates=0
        for index,row in enumerate(ordered):
            interval=None if index==0 else intervals[index-1]
            duplicate=interval is not None and interval<=0
            gap=bool(interval is not None and expected>0 and interval>expected*self.gap_multiplier)
            valid=interval is None or (not duplicate and abs(interval-expected)<=self.tolerance_seconds and not gap)
            invalid += int(not valid); gaps += int(gap); duplicates += int(duplicate)
            output.append({**row,"interval_seconds":interval,"timing_valid":valid,"timing_gap":gap,"duplicate_or_reversed_time":duplicate})
        return {"records":output,"expected_interval_seconds":expected,"invalid_count":invalid,"gap_count":gaps,"duplicate_or_reversed_count":duplicates,"passed":bool(output) and invalid==0}


class AcquisitionQcPipeline:
    def __init__(self, timing: TimingQC | None = None, instrument: InstrumentQC | None = None) -> None:
        self.timing=timing or TimingQC(); self.instrument=instrument or InstrumentQC()
    def run(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        if not records: raise ValueError("No acquisition records supplied")
        timing=self.timing.apply(records); instrument=self.instrument.apply(timing["records"])
        return {"records":instrument["records"],"timing":timing,"instrument":instrument,"passed":bool(timing["passed"] and instrument["passed"])}
