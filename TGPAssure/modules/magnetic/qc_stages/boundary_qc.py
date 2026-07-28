from __future__ import annotations

from typing import Any

import numpy as np

from core.domain.qc_engine import QCFinding, QCSeverity, QCStatus
from modules.magnetic.context import MagneticQcContext
from modules.magnetic.qc_stages.base import MagneticQCStage
from modules.magnetic.utils import finding, point_in_polygon


class BoundaryQC(MagneticQCStage):
    key = "boundary"
    display_name = "Survey Boundary"

    def evaluate(self, context: MagneticQcContext) -> tuple[dict[str, Any], list[QCFinding], str, QCStatus | None]:
        if context.survey_boundary is None:
            return self.skipped("No survey boundary is loaded.")
        dataset = context.rover_dataset
        boundary = context.survey_boundary
        if dataset.crs and boundary.crs and dataset.crs.casefold() != boundary.crs.casefold():
            finding_item = finding("MAG.BOUNDARY.CRS", QCSeverity.ERROR, f"Boundary CRS ({boundary.crs}) does not match the rover CRS ({dataset.crs}).", suggested_action="Transform the boundary to the rover dataset CRS before boundary QC.")
            return {"dataset_crs": dataset.crs, "boundary_crs": boundary.crs}, [finding_item], "Boundary CRS mismatch.", None
        valid = dataset.valid_coordinate_mask()
        inside = np.zeros(dataset.record_count, dtype=bool)
        inside[valid] = point_in_polygon(dataset.x[valid], dataset.y[valid], boundary.vertices)
        outside = valid & ~inside
        outside_pct = 100.0 * float(np.count_nonzero(outside)) / max(np.count_nonzero(valid), 1)
        findings: list[QCFinding] = []
        if outside_pct > float(self.threshold(context, "outside_boundary_max_pct")):
            findings.append(finding("MAG.BOUNDARY.OUTSIDE", QCSeverity.ERROR, f"{outside_pct:.2f}% of valid stations are outside the survey boundary.", suggested_action="Confirm boundary version, coordinate system and station exclusions.", metadata={"outside_count": int(np.count_nonzero(outside))}))
        context.qc_masks["outside_boundary"] = outside
        return {"outside_boundary_count": int(np.count_nonzero(outside)), "outside_boundary_pct": outside_pct, "boundary_name": boundary.name}, findings, "Survey coverage against the loaded boundary checked.", None
