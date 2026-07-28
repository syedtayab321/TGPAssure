from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Tuple

import numpy as np

from core.domain.qc_engine import QCFinding, QCSeverity, QCStage, QCStageResult
from modules.seismic.segy_qc.stages._processing_qc_utils import (
    error_result,
    get_reader_and_index,
    make_finding,
    stage_result,
    threshold,
    trace_pair_metrics,
)


class RepeatabilityQCStage(QCStage):
    """Evaluate 4D base/monitor repeatability using NRMS, predictability and shifts."""

    STAGE_NAME = "RepeatabilityQC"

    @staticmethod
    def _geometry_keys(index: Any) -> List[Tuple[int, ...]]:
        count = int(index.trace_count)
        cdp = np.asarray(index.cdp, dtype=np.int64)
        offsets = np.asarray(index.offsets, dtype=np.float64)
        inline = np.asarray(index.inline_3d, dtype=np.int64)
        crossline = np.asarray(index.crossline_3d, dtype=np.int64)
        if np.count_nonzero((inline != 0) | (crossline != 0)) >= max(3, count // 4):
            return [
                (int(inline[i]), int(crossline[i]), int(round(offsets[i] / 10.0) * 10))
                for i in range(count)
            ]
        if np.count_nonzero(cdp) >= max(3, count // 4):
            return [(int(cdp[i]), int(round(offsets[i] / 10.0) * 10)) for i in range(count)]
        field = np.asarray(index.field_record, dtype=np.int64)
        trace_number = np.asarray(index.trace_number, dtype=np.int64)
        return [(int(field[i]), int(trace_number[i])) for i in range(count)]

    @staticmethod
    def _match_two_surveys(base_index: Any, monitor_index: Any, maximum_pairs: int = 400) -> List[Tuple[int, int, str]]:
        base_keys = RepeatabilityQCStage._geometry_keys(base_index)
        monitor_keys = RepeatabilityQCStage._geometry_keys(monitor_index)
        base_map: Dict[Tuple[int, ...], List[int]] = defaultdict(list)
        monitor_map: Dict[Tuple[int, ...], List[int]] = defaultdict(list)
        for trace_index, key in enumerate(base_keys):
            base_map[key].append(trace_index)
        for trace_index, key in enumerate(monitor_keys):
            monitor_map[key].append(trace_index)
        common = sorted(set(base_map).intersection(monitor_map))
        pairs: List[Tuple[int, int, str]] = []
        for key in common:
            base_values = base_map[key]
            monitor_values = monitor_map[key]
            pair_count = min(len(base_values), len(monitor_values))
            for ordinal in range(pair_count):
                pairs.append((base_values[ordinal], monitor_values[ordinal], ":".join(str(item) for item in key)))
        if len(pairs) > maximum_pairs:
            selected = np.linspace(0, len(pairs) - 1, maximum_pairs, dtype=int)
            pairs = [pairs[int(index)] for index in selected]
        return pairs

    @staticmethod
    def _common_sampling(
        base_trace: np.ndarray,
        monitor_trace: np.ndarray,
        base_dt_ms: float,
        monitor_dt_ms: float,
    ) -> tuple[np.ndarray, np.ndarray, float]:
        common_dt = max(float(base_dt_ms), float(monitor_dt_ms), np.finfo(float).eps)
        duration_ms = min(
            (base_trace.size - 1) * float(base_dt_ms),
            (monitor_trace.size - 1) * float(monitor_dt_ms),
        )
        sample_count = int(duration_ms / common_dt) + 1
        if sample_count < 8:
            return base_trace[:sample_count], monitor_trace[:sample_count], common_dt
        common_times = np.arange(sample_count, dtype=np.float64) * common_dt
        base = np.interp(common_times, np.arange(base_trace.size) * float(base_dt_ms), base_trace)
        monitor = np.interp(common_times, np.arange(monitor_trace.size) * float(monitor_dt_ms), monitor_trace)
        return base, monitor, common_dt

    def run(self, context: Dict[str, Any]) -> QCStageResult:
        findings: List[QCFinding] = []
        try:
            monitor_reader, monitor_index = get_reader_and_index(context)
            nrms_max = threshold(context, "nrms_max", 60.0)
            predictability_min = threshold(context, "predictability_min", 0.70)
            time_shift_max_ms = threshold(context, "time_shift_max_ms", 8.0)
            amplitude_deviation = threshold(context, "amplitude_ratio_min_max", 0.25)
            amplitude_min = max(0.0, 1.0 - amplitude_deviation)
            amplitude_max = 1.0 + amplitude_deviation

            base_reader = context.get("base_reader")
            base_error = context.get("base_reader_error")
            comparison_mode = "external_base_monitor"
            if base_reader is None:
                detail = f" The selected base SEG-Y could not be opened: {base_error}" if base_error else ""
                findings.append(
                    make_finding(
                        "REPEATABILITY_BASE_SURVEY_REQUIRED",
                        QCSeverity.WARNING,
                        "4D repeatability requires a separate base-survey SEG-Y; no valid base survey is available in the QC context." + detail,
                        category="repeatability",
                        title="Base survey required for 4D QC",
                        suggested_action="Use Select 4D Base in the SEG-Y QC ribbon, then choose the matching base survey before rerunning QC.",
                        context={"comparison_mode": comparison_mode, "base_reader_error": base_error},
                    )
                )
                metrics = {
                    "comparison_mode": comparison_mode,
                    "matched_trace_pair_count": 0,
                    "nrms_median_pct": 0.0,
                    "predictability_median": 0.0,
                    "time_shift_p95_abs_ms": 0.0,
                    "amplitude_ratio_median": 0.0,
                }
                context["repeatability_qc"] = {"available": False, "metrics": metrics}
                return stage_result(self.STAGE_NAME, metrics, findings)

            base_index = context.get("base_index")
            if base_index is None:
                base_index = base_reader.scan_trace_headers()
                context["base_index"] = base_index
            pairs = self._match_two_surveys(base_index, monitor_index)

            if not pairs:
                findings.append(
                    make_finding(
                        "REPEATABILITY_REFERENCE_UNAVAILABLE",
                        QCSeverity.WARNING,
                        "No matching base/monitor traces were found using inline/crossline/offset, CDP/offset, or field-record/trace geometry keys.",
                        category="repeatability",
                        title="No matching 4D trace pairs",
                        suggested_action="Verify geometry headers, coordinate/scalar consistency, trace sorting and offset sign conventions in both surveys before rerunning 4D QC.",
                        context={"comparison_mode": comparison_mode},
                    )
                )
                metrics = {
                    "comparison_mode": comparison_mode,
                    "matched_trace_pair_count": 0,
                    "nrms_median_pct": 0.0,
                    "predictability_median": 0.0,
                    "time_shift_p95_abs_ms": 0.0,
                    "amplitude_ratio_median": 0.0,
                }
                context["repeatability_qc"] = {"available": False, "metrics": metrics}
                return stage_result(self.STAGE_NAME, metrics, findings)

            pair_results: List[Dict[str, Any]] = []
            search_lag_ms = max(4.0 * time_shift_max_ms, 40.0)
            for base_trace_index, monitor_trace_index, geometry_key in pairs:
                base_trace = np.asarray(base_reader.read_trace(base_trace_index, index=base_index), dtype=np.float64)
                monitor_trace = np.asarray(monitor_reader.read_trace(monitor_trace_index, index=monitor_index), dtype=np.float64)
                base_dt_ms = float(base_index.sample_intervals_us[base_trace_index]) / 1000.0
                monitor_dt_ms = float(monitor_index.sample_intervals_us[monitor_trace_index]) / 1000.0
                base_aligned, monitor_aligned, common_dt = self._common_sampling(
                    base_trace,
                    monitor_trace,
                    base_dt_ms,
                    monitor_dt_ms,
                )
                if base_aligned.size < 8 or monitor_aligned.size < 8:
                    continue
                metrics = trace_pair_metrics(base_aligned, monitor_aligned, common_dt, search_lag_ms)
                pair_results.append(
                    {
                        "geometry_key": geometry_key,
                        "base_trace_index": int(base_trace_index) + 1,
                        "monitor_trace_index": int(monitor_trace_index) + 1,
                        **metrics,
                    }
                )

            if not pair_results:
                raise ValueError("Matched repeatability traces did not contain enough common samples")

            nrms = np.asarray([item["nrms_pct"] for item in pair_results], dtype=np.float64)
            predictability = np.asarray([item["predictability"] for item in pair_results], dtype=np.float64)
            shifts = np.asarray([item["time_shift_ms"] for item in pair_results], dtype=np.float64)
            amplitude_ratio = np.asarray([item["amplitude_ratio"] for item in pair_results], dtype=np.float64)

            nrms_median = float(np.median(nrms))
            nrms_p90 = float(np.percentile(nrms, 90))
            predictability_median = float(np.median(predictability))
            shift_p95 = float(np.percentile(np.abs(shifts), 95))
            amplitude_median = float(np.median(amplitude_ratio))
            nrms_bad = int(np.count_nonzero(nrms > nrms_max))
            predictability_bad = int(np.count_nonzero(predictability < predictability_min))
            shift_bad = int(np.count_nonzero(np.abs(shifts) > time_shift_max_ms))
            amplitude_bad = int(np.count_nonzero((amplitude_ratio < amplitude_min) | (amplitude_ratio > amplitude_max)))

            if nrms_median > nrms_max:
                findings.append(
                    make_finding(
                        "REPEATABILITY_HIGH_NRMS",
                        QCSeverity.ERROR,
                        f"Median base/monitor NRMS is {nrms_median:.1f}%, exceeding {nrms_max:.1f}%.",
                        category="repeatability",
                        title="4D NRMS exceeds tolerance",
                        metric_name="nrms_median_pct",
                        observed_value=nrms_median,
                        expected_max=nrms_max,
                        unit="%",
                        suggested_action="Review survey matching, statics, phase, amplitude balancing, positioning, source/receiver repeatability and cross-equalization.",
                        context={"failing_pair_count": nrms_bad},
                    )
                )
            elif nrms_bad:
                findings.append(
                    make_finding(
                        "REPEATABILITY_LOCAL_NRMS",
                        QCSeverity.WARNING,
                        f"{nrms_bad} matched trace pairs exceed the NRMS limit although the median passes.",
                        category="repeatability",
                        title="Localized 4D NRMS failures",
                        metric_name="nrms_failing_pair_count",
                        observed_value=float(nrms_bad),
                        expected_max=0.0,
                        unit="pairs",
                        suggested_action="Map the failing pairs spatially and inspect local acquisition/processing differences before interpretation.",
                    )
                )

            if predictability_median < predictability_min:
                findings.append(
                    make_finding(
                        "REPEATABILITY_LOW_PREDICTABILITY",
                        QCSeverity.ERROR,
                        f"Median predictability is {predictability_median:.3f}, below {predictability_min:.3f}.",
                        category="repeatability",
                        title="Low base/monitor predictability",
                        metric_name="predictability_median",
                        observed_value=predictability_median,
                        expected_min=predictability_min,
                        unit="ratio",
                        suggested_action="Apply phase/time alignment and cross-equalization, then reassess predictability in stable non-reservoir windows.",
                        context={"failing_pair_count": predictability_bad},
                    )
                )

            if shift_p95 > time_shift_max_ms:
                findings.append(
                    make_finding(
                        "REPEATABILITY_TIME_SHIFT",
                        QCSeverity.ERROR,
                        f"The 95th-percentile absolute base/monitor time shift is {shift_p95:.2f} ms, exceeding {time_shift_max_ms:.2f} ms.",
                        category="repeatability",
                        title="4D time shifts exceed tolerance",
                        metric_name="time_shift_p95_abs_ms",
                        observed_value=shift_p95,
                        expected_max=time_shift_max_ms,
                        unit="ms",
                        suggested_action="Review residual statics, datum consistency, clock/sample timing and time-shift cross-equalization.",
                        context={"failing_pair_count": shift_bad},
                    )
                )

            if amplitude_median < amplitude_min or amplitude_median > amplitude_max:
                findings.append(
                    make_finding(
                        "REPEATABILITY_AMPLITUDE_RATIO",
                        QCSeverity.ERROR,
                        f"Median monitor/base RMS amplitude ratio is {amplitude_median:.3f}; the accepted range is {amplitude_min:.3f}-{amplitude_max:.3f}.",
                        category="repeatability",
                        title="4D amplitude mismatch",
                        metric_name="amplitude_ratio_median",
                        observed_value=amplitude_median,
                        expected_min=amplitude_min,
                        expected_max=amplitude_max,
                        unit="ratio",
                        suggested_action="Review source strength, receiver coupling, gain recovery, scaling and amplitude cross-equalization while preserving true 4D differences.",
                        context={"failing_pair_count": amplitude_bad},
                    )
                )
            elif amplitude_bad:
                findings.append(
                    make_finding(
                        "REPEATABILITY_LOCAL_AMPLITUDE_RATIO",
                        QCSeverity.WARNING,
                        f"{amplitude_bad} matched pairs fall outside the accepted amplitude-ratio range.",
                        category="repeatability",
                        title="Localized 4D amplitude mismatch",
                        metric_name="amplitude_failing_pair_count",
                        observed_value=float(amplitude_bad),
                        expected_max=0.0,
                        unit="pairs",
                        suggested_action="Map amplitude-ratio outliers and compare acquisition footprint, fold and processing scalars.",
                    )
                )

            metrics = {
                "comparison_mode": comparison_mode,
                "matched_trace_pair_count": len(pair_results),
                "nrms_min_pct": float(np.min(nrms)),
                "nrms_max_pct": float(np.max(nrms)),
                "nrms_median_pct": nrms_median,
                "nrms_p90_pct": nrms_p90,
                "nrms_failing_pair_count": nrms_bad,
                "predictability_min": float(np.min(predictability)),
                "predictability_median": predictability_median,
                "predictability_failing_pair_count": predictability_bad,
                "time_shift_median_ms": float(np.median(shifts)),
                "time_shift_p95_abs_ms": shift_p95,
                "time_shift_failing_pair_count": shift_bad,
                "amplitude_ratio_min": float(np.min(amplitude_ratio)),
                "amplitude_ratio_max": float(np.max(amplitude_ratio)),
                "amplitude_ratio_median": amplitude_median,
                "amplitude_ratio_failing_pair_count": amplitude_bad,
                "pair_results": pair_results[:200],
            }
            context["repeatability_qc"] = {
                "available": True,
                "metrics": metrics,
                "pair_results": pair_results,
            }
            return stage_result(self.STAGE_NAME, metrics, findings)
        except InterruptedError:
            raise
        except Exception as exc:
            return error_result(self.STAGE_NAME, "REPEATABILITY_QC_EXCEPTION", exc)
