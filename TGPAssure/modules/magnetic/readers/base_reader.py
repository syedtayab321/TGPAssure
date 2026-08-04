from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from modules.magnetic.models import MagneticDataRole, MagneticDataset, MagneticSurveyType


@dataclass(frozen=True)
class ReaderOptions:
    role: MagneticDataRole = MagneticDataRole.ROVER
    survey_type: MagneticSurveyType = MagneticSurveyType.GROUND
    crs: str | None = None
    coordinate_units: str = "m"
    magnetic_units: str = "nT"
    delimiter: str | None = None
    encoding: str = "utf-8-sig"
    timezone: str | None = None
    column_mapping: dict[str, str] = field(default_factory=dict)
    skip_rows: int = 0
    skip_columns: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


class MagneticFormatReader(ABC):
    @abstractmethod
    def can_read(self, path: Path) -> bool:
        raise NotImplementedError

    @abstractmethod
    def inspect(self, path: Path, options: ReaderOptions | None = None) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def read(self, path: Path, options: ReaderOptions | None = None) -> MagneticDataset:
        raise NotImplementedError
