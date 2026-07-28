from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np

from core.domain.qc_engine import QCFinding, QCSeverity, QCStatus
from modules.magnetic.constants import DIURNAL_CORRECTED_FIELD, RAW_TOTAL_FIELD
from modules.magnetic.context import MagneticQcContext
from modules.magnetic.qc_stages.base import MagneticQCStage
from modules.magnetic.utils import finding


class RepeatStationQC(MagneticQCStage):
    key = "repeat_station"
    display_name = "Repeat Stations"

    def evaluate(self, context: MagneticQcContext) -> tuple[dict[str, Any], list[QCFinding], str, QCStatus | None]:
        dataset = context.rover_dataset
        _, values = dataset.first_available_channel((DIURNAL_CORRECTED_FIELD, RAW_TOTAL_FIELD))
        groups: dict[str, list[int]] = defaultdict(list)
        for index, station in enumerate(dataset.station_id.astype(str)):
            if station:
                groups[station].append(index)
        repeated = {station: indices for station, indices in groups.items() if len(indices) > 1}
        if not repeated:
            repeat_lines = np.flatnonzero(dataset.line_type.astype(str) == "repeat")
            if repeat_lines.size == 0:
                return self.skipped("No repeated station identifiers or repeat lines are present.")
            return self.skipped("Repeat lines are present but station identifiers are required for point repeatability statistics.", {"repeat_line_records": int(repeat_lines.size)})
        differences: list[float] = []
        station_metrics: dict[str, float] = {}
        for station, indices in repeated.items():
            station_values = values[np.asarray(indices)]
            station_values = station_values[np.isfinite(station_values)]
            if station_values.size < 2:
                continue
            difference = float(np.max(station_values) - np.min(station_values))
            differences.append(difference)
            station_metrics[station] = difference
        if not differences:
            return self.skipped("Repeated stations contain insufficient valid total-field values.")
        array = np.asarray(differences)
        rms = float(np.sqrt(np.mean(array ** 2)))
        maximum = float(np.max(array))
        findings: list[QCFinding] = []
        if maximum > float(self.threshold(context, "repeat_station_difference_max_nt")):
            findings.append(finding("MAG.REPEAT.MAX", QCSeverity.ERROR, f"Maximum repeat-station field range is {maximum:.2f} nT.", suggested_action="Review diurnal correction, station position and nearby cultural sources."))
        if rms > float(self.threshold(context, "repeat_station_rms_max_nt")):
            findings.append(finding("MAG.REPEAT.RMS", QCSeverity.WARNING, f"Repeat-station RMS difference is {rms:.2f} nT."))
        return {"repeat_station_count": len(station_metrics), "maximum_difference_nt": maximum, "rms_difference_nt": rms, "station_differences_nt": station_metrics}, findings, "Repeat-station field agreement checked.", None
