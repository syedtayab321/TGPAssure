from __future__ import annotations

from typing import Any

import numpy as np

from core.domain.qc_engine import QCFinding, QCSeverity, QCStatus
from modules.magnetic.constants import BASE_TOTAL_FIELD, RAW_TOTAL_FIELD
from modules.magnetic.context import MagneticQcContext
from modules.magnetic.qc_stages.base import MagneticQCStage
from modules.magnetic.utils import finding, robust_sigma


class BaseStationQC(MagneticQCStage):
    key = "base_station"
    display_name = "Base Station / Static Stability"

    def evaluate(self, context: MagneticQcContext) -> tuple[dict[str, Any], list[QCFinding], str, QCStatus | None]:
        standalone_static = False
        if context.base_dataset is not None:
            dataset = context.base_dataset
            values = dataset.channel(BASE_TOTAL_FIELD)
            source_label = "separate base-station dataset"
        else:
            classification = str(context.rover_dataset.metadata.get("acquisition_classification", "moving")).lower()
            if classification != "stationary":
                return self.skipped("No separate base-station dataset is loaded and the primary dataset is not classified as stationary.")
            dataset = context.rover_dataset
            values = dataset.channel(RAW_TOTAL_FIELD)
            source_label = "primary stationary/static dataset"
            standalone_static = True

        valid = np.isfinite(values) & ~np.isnat(dataset.timestamps)
        if np.count_nonzero(valid) < 2:
            finding_item = finding("MAG.BASE.INSUFFICIENT", QCSeverity.ERROR, "The stability dataset has fewer than two valid time-field records.")
            return {"valid_records": int(np.count_nonzero(valid))}, [finding_item], "Base/static stability QC failed.", None

        time_ms = dataset.timestamps[valid].astype("datetime64[ms]").astype(np.int64)
        field = values[valid]
        order = np.argsort(time_ms)
        time_ms, field = time_ms[order], field[order]
        dt_s = np.diff(time_ms) / 1000.0
        df = np.diff(field)
        rate_nt_min = np.divide(np.abs(df) * 60.0, dt_s, out=np.full_like(df, np.nan), where=dt_s > 0)
        field_range = float(np.max(field) - np.min(field))
        median_interval = float(np.median(dt_s[dt_s > 0])) if np.any(dt_s > 0) else 0.0
        max_gap = float(np.max(dt_s)) if dt_s.size else 0.0
        noise = robust_sigma(np.diff(field)) / np.sqrt(2.0)
        max_rate = float(np.nanmax(rate_nt_min)) if np.any(np.isfinite(rate_nt_min)) else 0.0

        # A robust linear trend is useful for distinguishing slow drift from
        # short-period magnetic activity. The range threshold remains the
        # configured acceptance criterion because it is instrument/project
        # dependent, while the slope is reported for diagnosis.
        elapsed_h = (time_ms - time_ms[0]) / 3_600_000.0
        if elapsed_h.size >= 2 and float(elapsed_h[-1]) > 0:
            slope_nt_h, intercept = np.polyfit(elapsed_h, field, 1)
            trend = intercept + slope_nt_h * elapsed_h
            detrended_noise = robust_sigma(field - trend)
        else:
            slope_nt_h = 0.0
            detrended_noise = 0.0

        findings: list[QCFinding] = []
        if standalone_static:
            findings.append(
                finding(
                    "MAG.BASE.STANDALONE_STATIC",
                    QCSeverity.INFO,
                    "No separate base file is loaded. The primary dataset appears stationary, so TGPAssure used it for static/base stability QC only.",
                    suggested_action="Load a separate simultaneous base station file before applying diurnal correction to a moving rover survey.",
                )
            )
        if median_interval > float(self.threshold(context, "base_sampling_interval_max_s")):
            findings.append(finding("MAG.BASE.SAMPLING", QCSeverity.WARNING, f"Median base/static sampling interval is {median_interval:.2f} s."))
        if max_gap > float(self.threshold(context, "base_gap_max_s")):
            findings.append(
                finding(
                    "MAG.BASE.GAP",
                    QCSeverity.ERROR,
                    f"Maximum base/static time gap is {max_gap:.1f} s.",
                    suggested_action="Review acquisition interruptions and missing records.",
                )
            )
        if field_range > float(self.threshold(context, "base_drift_max_nt")):
            findings.append(
                finding(
                    "MAG.BASE.DRIFT",
                    QCSeverity.WARNING if standalone_static else QCSeverity.ERROR,
                    f"Base/static field range is {field_range:.1f} nT.",
                    suggested_action="Review magnetic activity, nearby cultural interference and instrument stability.",
                )
            )
        if max_rate > float(self.threshold(context, "base_rate_max_nt_min")):
            findings.append(
                finding(
                    "MAG.BASE.RATE",
                    QCSeverity.WARNING if standalone_static else QCSeverity.ERROR,
                    f"Maximum field rate is {max_rate:.2f} nT/min.",
                    suggested_action="Identify magnetic storm intervals, spikes or local instrument disturbances.",
                )
            )
        if noise > float(self.threshold(context, "base_noise_rms_max_nt")):
            findings.append(finding("MAG.BASE.NOISE", QCSeverity.WARNING, f"Robust base/static high-frequency noise is {noise:.2f} nT RMS."))

        context.base_statistics.update(
            {
                "source": source_label,
                "standalone_static_mode": standalone_static,
                "record_count": int(field.size),
                "median_interval_s": median_interval,
                "maximum_gap_s": max_gap,
                "field_range_nt": field_range,
                "linear_trend_nt_per_hour": float(slope_nt_h),
                "detrended_robust_sigma_nt": float(detrended_noise),
                "maximum_rate_nt_min": max_rate,
                "noise_rms_nt": noise,
            }
        )
        return dict(context.base_statistics), findings, "Base/static sampling, stability, drift trend, field rate and noise checked.", None
