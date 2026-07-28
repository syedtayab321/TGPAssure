from __future__ import annotations

from modules.magnetic.context import MagneticQcContext
from modules.magnetic.magnetic_engine import MagneticQcPipeline
from modules.magnetic.magnetic_processing_engine import MagneticProcessingEngine
from modules.magnetic.magnetic_profiles import get_profile
from modules.magnetic.models import MagneticDataset


class MagneticQC:
    """Compatibility facade for direct, synchronous magnetic QC."""

    def run(
        self,
        rover: MagneticDataset,
        *,
        base: MagneticDataset | None = None,
        profile_name: str = "standard",
    ) -> dict:
        profile = get_profile(profile_name)
        context = MagneticQcContext(rover_dataset=rover, base_dataset=base, profile_name=profile.name, thresholds=profile.thresholds)
        return MagneticQcPipeline().run(context).as_dict()


class DiurnalCorrectionQC:
    """Traceable diurnal correction with compatibility for simple record lists."""

    def apply(self, rover, base=None) -> dict:
        # Lightweight callers historically supplied rows containing both rover
        # and coincident base values. Preserve that API while keeping the full
        # MagneticDataset processing path authoritative for production use.
        if isinstance(rover, list) and base is None:
            if not rover:
                return {"records": [], "passed": False}
            try:
                reference = float(rover[0]["base_field"])
                output = []
                for row in rover:
                    base_value = float(row["base_field"])
                    total = float(row["total_field"])
                    output.append({**row, "corrected_total_field": total - (base_value - reference)})
                return {"records": output, "passed": True}
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Invalid coincident rover/base record: {exc}") from exc
        if not isinstance(rover, MagneticDataset) or not isinstance(base, MagneticDataset):
            raise TypeError("Diurnal correction requires MagneticDataset rover/base inputs or coincident record rows")
        MagneticProcessingEngine().apply_diurnal_correction(rover, base)
        result = MagneticQC().run(rover, base=base, profile_name="processing")
        return {"dataset": rover, "qc_result": result, "passed": result["status"] == "pass"}
