from __future__ import annotations

from modules.magnetic.context import MagneticQcContext
from modules.magnetic.magnetic_engine import MAGNETIC_QC_STAGES, MagneticQcPipeline
from modules.magnetic.magnetic_processing_engine import MagneticProcessingEngine
from modules.magnetic.magnetic_profiles import get_profile


def test_full_pipeline_executes_all_magnetic_stages(magnetic_datasets):
    rover, base = magnetic_datasets
    processing = MagneticProcessingEngine()
    processing.despike(rover)
    processing.apply_diurnal_correction(rover, base)
    processing.level_lines(rover)
    grid = processing.grid(rover, cell_size=25.0)
    profile = get_profile("standard")
    context = MagneticQcContext(
        rover_dataset=rover,
        base_dataset=base,
        profile_name=profile.name,
        thresholds=profile.thresholds,
        processing_products={"grid": grid},
    )

    result = MagneticQcPipeline().run(context)

    assert len(result.stage_outcomes) == len(MAGNETIC_QC_STAGES)
    assert result.stage_outcomes[-1].stage_key == "summary"
    assert 0.0 <= result.score <= 100.0
    assert result.status.value in {"pass", "warn", "fail"}
    assert context.line_statistics
    assert context.base_statistics


def test_field_profile_is_more_tolerant_than_strict():
    field = get_profile("field")
    strict = get_profile("strict")
    assert field.thresholds["base_gap_max_s"] > strict.thresholds["base_gap_max_s"]
    assert field.thresholds["noise_rms_max_nt"] > strict.thresholds["noise_rms_max_nt"]
    assert field.thresholds["tie_misclosure_max_nt"] > strict.thresholds["tie_misclosure_max_nt"]
