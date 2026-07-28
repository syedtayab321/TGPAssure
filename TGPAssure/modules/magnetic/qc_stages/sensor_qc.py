from __future__ import annotations

from typing import Any

import numpy as np

from core.domain.qc_engine import QCFinding, QCSeverity, QCStatus
from modules.magnetic.constants import RAW_TOTAL_FIELD
from modules.magnetic.context import MagneticQcContext
from modules.magnetic.qc_stages.base import MagneticQCStage
from modules.magnetic.utils import finding, robust_sigma


class SensorQC(MagneticQCStage):
    key = "sensor"
    display_name = "Sensor Health"

    def evaluate(self, context: MagneticQcContext) -> tuple[dict[str, Any], list[QCFinding], str, QCStatus | None]:
        dataset = context.rover_dataset
        values = dataset.channel(RAW_TOTAL_FIELD)
        findings: list[QCFinding] = []
        finite = np.isfinite(values)
        missing_pct = 100.0 * np.count_nonzero(~finite) / values.size
        minimum = float(self.threshold(context, "sensor_range_min_nt"))
        maximum = float(self.threshold(context, "sensor_range_max_nt"))
        out_of_range = finite & ((values < minimum) | (values > maximum))
        if np.any(out_of_range):
            findings.append(
                finding(
                    "MAG.SENSOR.RANGE",
                    QCSeverity.ERROR,
                    f"{np.count_nonzero(out_of_range)} total-field values fall outside {minimum:.0f}–{maximum:.0f} nT.",
                    suggested_action="Check instrument lock, units and corrupted records.",
                )
            )
        if missing_pct > float(self.threshold(context, "missing_value_max_pct")):
            findings.append(finding("MAG.SENSOR.MISSING", QCSeverity.ERROR, f"Missing total-field values affect {missing_pct:.2f}% of records."))

        constant_count = 0
        maximum_run = 1
        if values.size > 1:
            equal = np.isfinite(values[1:]) & np.isfinite(values[:-1]) & (values[1:] == values[:-1])
            run = 1
            for is_equal in equal:
                run = run + 1 if is_equal else 1
                maximum_run = max(maximum_run, run)
            constant_count = int(np.count_nonzero(equal))
        run_limit = int(self.threshold(context, "frozen_sequence_max_samples"))
        if maximum_run > run_limit:
            findings.append(
                finding(
                    "MAG.SENSOR.FROZEN",
                    QCSeverity.ERROR,
                    f"A repeated-value sequence reaches {maximum_run} samples.",
                    suggested_action="Inspect sensor lock, communication and logger status.",
                )
            )

        validation_bad_pct = 0.0
        if "sensor_validation_bad" in dataset.quality_flags:
            validation_bad = np.asarray(dataset.quality_flags["sensor_validation_bad"], dtype=bool)
            validation_bad_pct = 100.0 * float(np.count_nonzero(validation_bad)) / max(validation_bad.size, 1)
            limit = float(self.threshold(context, "sensor_validation_bad_max_pct", 0.1))
            if validation_bad_pct > limit:
                findings.append(
                    finding(
                        "MAG.SENSOR.VALIDATION",
                        QCSeverity.ERROR,
                        f"Instrument validation flags mark {validation_bad_pct:.3f}% of sensor samples as bad.",
                        suggested_action="Review the instrument validation marker and exclude invalid samples before processing.",
                        metadata={"bad_samples": int(np.count_nonzero(validation_bad)), "limit_pct": limit},
                    )
                )

        sensitivity_min = sensitivity_max = None
        if "sensor_sensitivity" in dataset.channels:
            sensitivity = dataset.channel("sensor_sensitivity")
            valid_sensitivity = sensitivity[np.isfinite(sensitivity)]
            if valid_sensitivity.size:
                sensitivity_min = float(np.min(valid_sensitivity))
                sensitivity_max = float(np.max(valid_sensitivity))
                expected_min = dataset.metadata.get("source_header", {}).get("sensor_scalar_sensitivity_expected_min")
                try:
                    expected_min_value = float(expected_min) if expected_min is not None else None
                except (TypeError, ValueError):
                    expected_min_value = None
                if expected_min_value is not None and np.any(valid_sensitivity < expected_min_value):
                    count = int(np.count_nonzero(valid_sensitivity < expected_min_value))
                    findings.append(
                        finding(
                            "MAG.SENSOR.SENSITIVITY",
                            QCSeverity.WARNING,
                            f"{count} sensor-sensitivity values are below the logger-declared expected minimum of {expected_min_value:.0f}.",
                            suggested_action="Review sensor operating state and instrument diagnostics around the affected records.",
                        )
                    )

        disagreement = None
        if "sensor_1_raw" in dataset.channels and "sensor_2_raw" in dataset.channels:
            delta = dataset.channel("sensor_1_raw") - dataset.channel("sensor_2_raw")
            disagreement = float(np.nanpercentile(np.abs(delta), 95))
            if disagreement > float(self.threshold(context, "sensor_disagreement_max_nt")):
                findings.append(
                    finding(
                        "MAG.SENSOR.DISAGREEMENT",
                        QCSeverity.ERROR,
                        f"Dual-sensor P95 disagreement is {disagreement:.2f} nT.",
                        suggested_action="Verify sensor separation, calibration, orientation and cable integrity.",
                    )
                )

        context.qc_masks["sensor_out_of_range"] = out_of_range
        return {
            "missing_total_field_pct": missing_pct,
            "minimum_total_field_nt": float(np.nanmin(values)) if np.any(finite) else None,
            "maximum_total_field_nt": float(np.nanmax(values)) if np.any(finite) else None,
            "robust_field_sigma_nt": robust_sigma(values),
            "out_of_range_count": int(np.count_nonzero(out_of_range)),
            "repeated_adjacent_values": constant_count,
            "maximum_frozen_run_samples": maximum_run,
            "sensor_validation_bad_pct": validation_bad_pct,
            "sensor_sensitivity_min": sensitivity_min,
            "sensor_sensitivity_max": sensitivity_max,
            "dual_sensor_p95_difference_nt": disagreement,
        }, findings, "Sensor range, logger validation, sensitivity, missing values and frozen readings checked.", None
