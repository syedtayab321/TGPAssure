from __future__ import annotations

"""Reusable QC-pipeline design primitives shared by every TGPAssure module.

The scientific engines remain module-owned.  This layer standardises how a UI
selects/order stages, stores presets, validates dependencies and invokes a
module runner with progress/cancellation.  Magnetic is the first adapter;
Seismic/Uphole/Seismetics, Gravity, Geodetic and Electrical can register their
own stage catalogs without changing the designer infrastructure.
"""

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Iterable, Protocol


ProgressCallback = Callable[[int, int, str], None]
CancellationCheck = Callable[[], bool]


@dataclass(frozen=True)
class QCStageDescriptor:
    key: str
    display_name: str
    category: str = "QC"
    description: str = ""
    dependencies: tuple[str, ...] = ()
    required: bool = False


@dataclass
class QCPipelineDesign:
    module_id: str
    name: str = "Automated QC"
    profile_name: str = "standard"
    stage_keys: list[str] = field(default_factory=list)
    threshold_overrides: dict[str, Any] = field(default_factory=dict)
    stop_on_failure: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1

    def normalized(self) -> "QCPipelineDesign":
        seen: set[str] = set()
        ordered = []
        for key in self.stage_keys:
            key = str(key).strip()
            if key and key not in seen:
                ordered.append(key); seen.add(key)
        self.module_id = str(self.module_id).strip().lower()
        self.name = str(self.name or "Automated QC").strip()
        self.profile_name = str(self.profile_name or "standard").strip().lower()
        self.stage_keys = ordered
        return self

    def to_json(self, *, indent: int = 2) -> str:
        self.normalized()
        return json.dumps(asdict(self), indent=indent, sort_keys=True, default=str)

    @classmethod
    def from_json(cls, payload: str | bytes) -> "QCPipelineDesign":
        data = json.loads(payload)
        return cls(**data).normalized()

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.write_text(self.to_json(indent=2), encoding="utf-8")
        return target

    @classmethod
    def load(cls, path: str | Path) -> "QCPipelineDesign":
        return cls.from_json(Path(path).read_text(encoding="utf-8"))


class QCModuleAdapter(Protocol):
    module_id: str

    def stages(self) -> Iterable[QCStageDescriptor]: ...

    def validate(self, design: QCPipelineDesign) -> list[str]: ...

    def execute(
        self,
        design: QCPipelineDesign,
        context: Any,
        *,
        progress_callback: ProgressCallback | None = None,
        cancellation_check: CancellationCheck | None = None,
    ) -> Any: ...


class AutomatedQCPipelineRegistry:
    """Thread-safe registry for module-specific QC adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, QCModuleAdapter] = {}
        self._lock = RLock()

    def register(self, adapter: QCModuleAdapter, *, replace: bool = False) -> None:
        key = str(adapter.module_id).strip().lower()
        if not key:
            raise ValueError("QC adapter module_id cannot be empty")
        with self._lock:
            if key in self._adapters and not replace:
                raise ValueError(f"QC adapter '{key}' is already registered")
            self._adapters[key] = adapter

    def unregister(self, module_id: str) -> None:
        with self._lock:
            self._adapters.pop(str(module_id).strip().lower(), None)

    def adapter(self, module_id: str) -> QCModuleAdapter:
        key = str(module_id).strip().lower()
        with self._lock:
            try:
                return self._adapters[key]
            except KeyError as exc:
                raise KeyError(f"No automated QC adapter registered for '{key}'") from exc

    def modules(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._adapters))

    def stages(self, module_id: str) -> tuple[QCStageDescriptor, ...]:
        return tuple(self.adapter(module_id).stages())

    def validate(self, design: QCPipelineDesign) -> list[str]:
        design.normalized()
        adapter = self.adapter(design.module_id)
        catalog = {stage.key: stage for stage in adapter.stages()}
        errors: list[str] = []
        unknown = [key for key in design.stage_keys if key not in catalog]
        if unknown:
            errors.append("Unknown stages: " + ", ".join(unknown))
        selected = set(design.stage_keys)
        for stage in catalog.values():
            if stage.required and stage.key not in selected:
                errors.append(f"Required stage is missing: {stage.display_name}")
            if stage.key in selected:
                missing = [dep for dep in stage.dependencies if dep not in selected]
                if missing:
                    errors.append(f"{stage.display_name} requires: {', '.join(missing)}")
        errors.extend(adapter.validate(design))
        return errors

    def execute(
        self,
        design: QCPipelineDesign,
        context: Any,
        *,
        progress_callback: ProgressCallback | None = None,
        cancellation_check: CancellationCheck | None = None,
    ) -> Any:
        errors = self.validate(design)
        if errors:
            raise ValueError("Invalid QC pipeline design: " + "; ".join(errors))
        return self.adapter(design.module_id).execute(
            design,
            context,
            progress_callback=progress_callback,
            cancellation_check=cancellation_check,
        )


GLOBAL_QC_PIPELINES = AutomatedQCPipelineRegistry()
