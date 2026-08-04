from __future__ import annotations

from typing import Any

import numpy as np

from core.domain.qc_engine import QCFinding, QCSeverity, QCStatus
from modules.magnetic.context import MagneticQcContext
from modules.magnetic.qc_stages.base import MagneticQCStage
from modules.magnetic.utils import finding, percentile


class TimestampQC(MagneticQCStage):
    key = "timestamp"
    display_name = "Timestamp and Clock"

    def evaluate(self, context: MagneticQcContext) -> tuple[dict[str, Any], list[QCFinding], str, QCStatus | None]:
        timestamps = context.rover_dataset.timestamps
        valid = ~np.isnat(timestamps)
        findings: list[QCFinding] = []
        if str(context.rover_dataset.metadata.get("timestamp_source") or "").lower() == "missing":
            return self.skipped(
                "No timestamp/date+time columns were mapped; coordinate, channel and schema QC can still run.",
                {"invalid_timestamp_pct": 100.0},
            )
        missing_pct = 100.0 * float(np.count_nonzero(~valid)) / timestamps.size
        if not np.any(valid):
            findings.append(finding("MAG.TIME.ALL_INVALID", QCSeverity.CRITICAL, "No valid rover timestamps are available."))
            return {"invalid_timestamp_pct": 100.0}, findings, "Timestamp validation failed.", None
        integer_time = timestamps[valid].astype("datetime64[ms]").astype(np.int64)
        differences_s = np.diff(integer_time) / 1000.0
        duplicate_pct = 100.0 * float(np.count_nonzero(differences_s == 0)) / max(differences_s.size, 1)
        nonmonotonic_pct = 100.0 * float(np.count_nonzero(differences_s < 0)) / max(differences_s.size, 1)
        positive = differences_s[differences_s > 0]
        median_interval = float(np.median(positive)) if positive.size else 0.0
        maximum_gap = float(np.max(positive)) if positive.size else 0.0
        if duplicate_pct > float(self.threshold(context, "duplicate_timestamp_max_pct")):
            findings.append(finding("MAG.TIME.DUPLICATE", QCSeverity.WARNING, f"Duplicate timestamps affect {duplicate_pct:.2f}% of intervals.", suggested_action="Remove duplicate records or confirm multiple sensors share timestamps."))
        if nonmonotonic_pct > float(self.threshold(context, "timestamp_nonmonotonic_max_pct")):
            findings.append(finding("MAG.TIME.NONMONOTONIC", QCSeverity.ERROR, f"Non-monotonic timestamps affect {nonmonotonic_pct:.2f}% of intervals.", suggested_action="Correct clock resets and sort acquisition records by verified time."))
        if maximum_gap > float(self.threshold(context, "timestamp_gap_max_s")):
            findings.append(finding("MAG.TIME.GAP", QCSeverity.WARNING, f"Maximum rover time gap is {maximum_gap:.2f} s.", suggested_action="Review acquisition interruptions and missing records."))
        if context.base_dataset is not None:
            base_valid = ~np.isnat(context.base_dataset.timestamps)
            if np.any(base_valid):
                rover_start, rover_end = integer_time.min(), integer_time.max()
                base_time = context.base_dataset.timestamps[base_valid].astype("datetime64[ms]").astype(np.int64)
                uncovered_before = max(0.0, (base_time.min() - rover_start) / 1000.0)
                uncovered_after = max(0.0, (rover_end - base_time.max()) / 1000.0)
                if uncovered_before > 0 or uncovered_after > 0:
                    findings.append(finding("MAG.TIME.BASE_COVERAGE", QCSeverity.ERROR, "Base-station recording does not cover the complete rover acquisition period.", suggested_action="Load the complete base session or exclude uncovered rover periods.", metadata={"uncovered_before_s": uncovered_before, "uncovered_after_s": uncovered_after}))
        metrics = {
            "invalid_timestamp_pct": missing_pct,
            "duplicate_timestamp_pct": duplicate_pct,
            "nonmonotonic_timestamp_pct": nonmonotonic_pct,
            "median_sampling_interval_s": median_interval,
            "p95_sampling_interval_s": percentile(positive, 95, 0.0),
            "maximum_gap_s": maximum_gap,
        }
        return metrics, findings, "Timestamp continuity, order and rover/base coverage checked.", None
