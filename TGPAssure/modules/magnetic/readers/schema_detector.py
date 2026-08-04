from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from modules.magnetic.readers.column_mapper import MagneticColumnMapper


@dataclass(frozen=True)
class SchemaInspection:
    mapping: dict[str, str]
    required_missing: tuple[str, ...]
    optional_available: tuple[str, ...]
    confidence: float


class MagneticSchemaDetector:
    def __init__(self) -> None:
        self.mapper = MagneticColumnMapper()

    def inspect(self, headers: Iterable[str], *, base: bool = False) -> SchemaInspection:
        mapping = self.mapper.detect(headers)
        # A magnetic QC file may be a simple map/profile table containing only
        # coordinates and total field.  Time-dependent QC stages will skip when
        # no timestamp/date+time fields are mapped.
        required = {"total_field"}
        missing = tuple(sorted(name for name in required if name not in mapping))
        recognised = len(mapping)
        confidence = min(1.0, recognised / 8.0)
        optional = tuple(sorted(set(mapping) - {"timestamp", "date", "time", "total_field"}))
        return SchemaInspection(mapping, missing, optional, confidence)
