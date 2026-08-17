from __future__ import annotations

from typing import Any, Iterable

from core.domain.automated_qc_pipeline import QCPipelineDesign, QCStageDescriptor
from modules.magnetic.context import MagneticQcContext
from modules.magnetic.magnetic_engine import MAGNETIC_QC_STAGES, MagneticQcPipeline
from modules.magnetic.magnetic_profiles import PROFILES


_STAGE_META: dict[str, tuple[str, str]] = {
    "file_integrity": ("Input", "File readability, record integrity and basic completeness."),
    "schema": ("Input", "Required magnetic fields, units and schema consistency."),
    "metadata": ("Input", "Survey metadata completeness and acquisition context."),
    "timestamp": ("Navigation", "Timestamp order, duplicates, gaps and clock consistency."),
    "coordinate": ("Navigation", "Coordinate completeness, jumps and navigation validity."),
    "boundary": ("Navigation", "Survey coverage against the loaded project boundary."),
    "line_geometry": ("Geometry", "Traverse/tie geometry, azimuth and line straightness."),
    "station_spacing": ("Geometry", "Station and line spacing against survey design."),
    "sensor": ("Instrument", "Sensor range, validation fields and dual-sensor consistency."),
    "base_station": ("Corrections", "Base sampling, gaps, drift and base-station noise."),
    "diurnal": ("Corrections", "Diurnal correction magnitude and residual trend QC."),
    "spike_dropout": ("Signal QC", "Spikes, frozen values, dropouts and gross outliers."),
    "noise": ("Signal QC", "Line noise, rolling noise and local signal stability."),
    "gradient": ("Signal QC", "Magnetic-gradient consistency and gradient noise."),
    "repeat_station": ("Repeatability", "Repeat-station differences and repeatability RMS."),
    "tie_line": ("Leveling", "Traverse/tie intersections and misclosure statistics."),
    "platform": ("Acquisition", "Platform speed, altitude/clearance and heading QC."),
    "cultural_noise": ("Signal QC", "Potential cultural-noise and localized outlier screening."),
    "correction_audit": ("Processing", "Audit of processing products and correction provenance."),
    "leveling": ("Leveling", "Line bias and leveling-residual quality checks."),
    "grid": ("Grid", "Grid voids, extrapolation, support and edge-artifact QC."),
    "summary": ("Summary", "Final weighted status, score and consolidated findings."),
}


def magnetic_stage_descriptors() -> tuple[QCStageDescriptor, ...]:
    descriptors = []
    for key, display_name, _stage_class in MAGNETIC_QC_STAGES:
        category, description = _STAGE_META.get(key, ("QC", ""))
        descriptors.append(
            QCStageDescriptor(
                key=key,
                display_name=display_name,
                category=category,
                description=description,
                required=key == "summary",
            )
        )
    return tuple(descriptors)


class MagneticAutomatedQCAdapter:
    module_id = "magnetic"

    def __init__(self, pipeline: MagneticQcPipeline) -> None:
        self.pipeline = pipeline

    def stages(self) -> Iterable[QCStageDescriptor]:
        return magnetic_stage_descriptors()

    def validate(self, design: QCPipelineDesign) -> list[str]:
        errors: list[str] = []
        if design.profile_name not in PROFILES:
            errors.append(f"Unknown magnetic profile: {design.profile_name}")
        return errors

    def execute(
        self,
        design: QCPipelineDesign,
        context: MagneticQcContext,
        *,
        progress_callback=None,
        cancellation_check=None,
    ) -> Any:
        return self.pipeline.run(
            context,
            selected_stage_keys=design.stage_keys,
            progress_callback=progress_callback,
            cancellation_check=cancellation_check,
            stop_on_failure=design.stop_on_failure,
        )
