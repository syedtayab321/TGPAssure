from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.magnetic.readers.base_reader import ReaderOptions
from modules.magnetic.readers.generic_delimited_reader import GenericDelimitedMagneticReader


class Enmag37Reader(GenericDelimitedMagneticReader):
    """ENmag37 rover/base reader using robust header and alias detection.

    ENmag37 exports vary by firmware and operator template. This reader accepts
    CSV/TXT/DAT/LOG exports, preserves all recognized instrument channels and
    records the detected mapping in dataset metadata.
    """

    SIGNATURES = ("enmag", "enmag37", "enerson")

    def can_read(self, path: Path) -> bool:
        if not super().can_read(path):
            return False
        try:
            with path.open("r", encoding="utf-8-sig", errors="ignore") as stream:
                header = stream.read(4096).lower()
        except OSError:
            return False
        return any(signature in header for signature in self.SIGNATURES) or "enmag" in path.name.lower()

    def read(self, path: Path, options: ReaderOptions | None = None):
        options = options or ReaderOptions()
        metadata = dict(options.metadata)
        metadata.setdefault("instrument_make", "Enerson")
        metadata.setdefault("instrument_model", "ENmag37")
        enriched = ReaderOptions(
            role=options.role,
            survey_type=options.survey_type,
            crs=options.crs,
            coordinate_units=options.coordinate_units,
            magnetic_units=options.magnetic_units,
            delimiter=options.delimiter,
            encoding=options.encoding,
            timezone=options.timezone,
            column_mapping=options.column_mapping,
            metadata=metadata,
        )
        return super().read(path, enriched)
