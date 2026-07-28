from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, Optional

from core.domain.qc_engine import QCPipeline, QCStageDefinition
from core.data_access.project_repository import ProjectRepository
from modules.seismic.segy_qc.stages.upload import UploadStage
from modules.seismic.segy_qc.stages.validation import ValidationStage
from modules.seismic.segy_qc.stages.metadata_extraction import MetadataExtractionStage
from modules.seismic.segy_qc.stages.header_reading import HeaderReadingStage
from modules.seismic.segy_qc.stages.geometry_qc import GeometryQCStage
from modules.seismic.segy_qc.stages.navigation_qc import NavigationQCStage
from modules.seismic.segy_qc.stages.trace_qc import TraceQCStage
from modules.seismic.segy_qc.stages.amplitude_qc import AmplitudeQCStage
from modules.seismic.segy_qc.stages.noise_qc import NoiseQCStage
from modules.seismic.segy_qc.stages.frequency_qc import FrequencyQCStage
from modules.seismic.segy_qc.stages.statics_qc import StaticsQCStage
from modules.seismic.segy_qc.stages.coordinate_qc import CoordinateQCStage
from modules.seismic.segy_qc.stages.summary import SummaryStage
from modules.seismic.segy_qc.stages.report_generation import ReportGenerationStage


class SegyQcPipeline:
    def __init__(self, project_repo: ProjectRepository, derived_path: Optional[Path] = None) -> None:
        self.project_repo = project_repo
        self.derived_path = derived_path or Path("derived")

    def create_pipeline(self) -> QCPipeline:
        stages = [
            QCStageDefinition("upload", lambda: UploadStage(self.project_repo)),
            QCStageDefinition("validation", lambda: ValidationStage()),
            QCStageDefinition("metadata", lambda: MetadataExtractionStage()),
            QCStageDefinition("header_reading", lambda: HeaderReadingStage()),
            QCStageDefinition("geometry", lambda: GeometryQCStage(expected_fold_min=1, expected_fold_max=1000)),
            QCStageDefinition("navigation", lambda: NavigationQCStage(max_velocity=5000.0)),
            QCStageDefinition("trace_qc", lambda: TraceQCStage(noise_floor_threshold=1e-6), dependencies=["header_reading"]),
            QCStageDefinition("amplitude", lambda: AmplitudeQCStage(dc_bias_threshold=0.1)),
            QCStageDefinition("noise", lambda: NoiseQCStage(spike_threshold=10.0)),
            QCStageDefinition("frequency", lambda: FrequencyQCStage(min_bandwidth=10.0)),
            QCStageDefinition("statics", lambda: StaticsQCStage(max_static_magnitude=1000.0), skippable_on_prior_failure=True),
            QCStageDefinition("coordinate", lambda: CoordinateQCStage()),
            QCStageDefinition("summary", lambda: SummaryStage(), dependencies=["header_reading"]),
            QCStageDefinition("report", lambda: ReportGenerationStage(), dependencies=["summary"])
        ]

        return QCPipeline("SEG-Y QC Pipeline", stages)

    def prepare_context(self, file_path: Path, file_uuid: Optional[str] = None) -> Dict[str, Any]:
        context = {
            "file_path": str(file_path),
            "derived_path": str(self.derived_path),
            "stage_results": []
        }

        if file_uuid:
            context["file_uuid"] = file_uuid

        return context