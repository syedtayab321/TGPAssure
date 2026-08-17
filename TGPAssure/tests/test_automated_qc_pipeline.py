from __future__ import annotations

from dataclasses import dataclass

from core.domain.automated_qc_pipeline import (
    AutomatedQCPipelineRegistry, QCPipelineDesign, QCStageDescriptor,
)


@dataclass
class _Adapter:
    module_id: str = "demo"

    def stages(self):
        return (
            QCStageDescriptor("load", "Load", required=True),
            QCStageDescriptor("qc", "QC", dependencies=("load",)),
        )

    def validate(self, design):
        return []

    def execute(self, design, context, *, progress_callback=None, cancellation_check=None):
        return {"stages": list(design.stage_keys), "context": context}


def test_design_roundtrip_and_registry_execution():
    registry = AutomatedQCPipelineRegistry()
    registry.register(_Adapter())
    design = QCPipelineDesign("demo", stage_keys=["load", "qc", "qc"])
    restored = QCPipelineDesign.from_json(design.to_json())
    assert restored.stage_keys == ["load", "qc"]
    assert registry.validate(restored) == []
    assert registry.execute(restored, {"x": 1})["stages"] == ["load", "qc"]


def test_registry_dependency_validation():
    registry = AutomatedQCPipelineRegistry(); registry.register(_Adapter())
    errors = registry.validate(QCPipelineDesign("demo", stage_keys=["qc"]))
    assert any("Required stage" in error for error in errors)
    assert any("requires" in error for error in errors)
