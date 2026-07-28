from __future__ import annotations

from typing import Any

import numpy as np

from core.domain.qc_engine import QCFinding, QCSeverity, QCStatus
from modules.magnetic.context import MagneticQcContext
from modules.magnetic.qc_stages.base import MagneticQCStage
from modules.magnetic.utils import finding, robust_sigma


class GridQC(MagneticQCStage):
    key = "grid"
    display_name = "Magnetic Grid"

    def evaluate(self, context: MagneticQcContext) -> tuple[dict[str, Any], list[QCFinding], str, QCStatus | None]:
        product = context.processing_products.get("grid")
        if not product:
            return self.skipped("No magnetic grid product is available.")
        grid = np.asarray(product.get("values"), dtype=float)
        if grid.ndim != 2 or grid.size == 0:
            item = finding("MAG.GRID.INVALID", QCSeverity.ERROR, "The magnetic grid product is empty or not two-dimensional.")
            return {"shape": list(grid.shape)}, [item], "Grid validation failed.", None
        finite = np.isfinite(grid)
        void_pct = 100.0 * np.count_nonzero(~finite) / grid.size
        edge = np.concatenate((grid[0, :], grid[-1, :], grid[:, 0], grid[:, -1]))
        interior = grid[1:-1, 1:-1] if min(grid.shape) > 2 else grid
        edge_sigma = robust_sigma(edge)
        interior_sigma = robust_sigma(interior.ravel())
        edge_ratio = edge_sigma / interior_sigma if np.isfinite(interior_sigma) and interior_sigma > 0 else 0.0
        extrapolated_pct = float(product.get("extrapolated_pct", 0.0))
        findings: list[QCFinding] = []
        if void_pct > float(self.threshold(context, "grid_void_max_pct")):
            findings.append(finding("MAG.GRID.VOIDS", QCSeverity.ERROR, f"Grid voids occupy {void_pct:.2f}% of cells."))
        if extrapolated_pct > float(self.threshold(context, "grid_extrapolation_max_pct")):
            findings.append(finding("MAG.GRID.EXTRAPOLATION", QCSeverity.WARNING, f"Grid extrapolation occupies {extrapolated_pct:.2f}% of cells.", suggested_action="Clip the grid to defensible survey coverage."))
        if edge_ratio > 3.0:
            findings.append(finding("MAG.GRID.EDGE", QCSeverity.WARNING, f"Grid-edge variability is {edge_ratio:.1f} times the interior variability.", suggested_action="Review search radius, cell size, extrapolation and boundary padding."))
        return {"shape": list(grid.shape), "cell_size": product.get("cell_size"), "void_pct": void_pct, "extrapolated_pct": extrapolated_pct, "minimum": float(np.nanmin(grid)) if np.any(finite) else None, "maximum": float(np.nanmax(grid)) if np.any(finite) else None, "edge_to_interior_noise_ratio": edge_ratio}, findings, "Grid completeness, range, extrapolation and edge behavior checked.", None
