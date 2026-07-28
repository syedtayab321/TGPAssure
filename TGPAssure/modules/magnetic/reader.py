from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.magnetic.models import MagneticDataRole, MagneticDataset, MagneticSurveyType
from modules.magnetic.readers.base_reader import ReaderOptions
from modules.magnetic.readers.reader_registry import MagneticReaderRegistry


class MagneticReader:
    """Facade for magnetic rover, stationary and base-station imports.

    The reader registry performs format detection first.  Callers do not need
    to know the file schema or CRS in advance. Native readers may provide a
    high-confidence CRS automatically; otherwise the dataset can still be
    imported with ``crs=None`` and only CRS-dependent QC stages will skip.
    """

    def __init__(self, registry: MagneticReaderRegistry | None = None) -> None:
        self.registry = registry or MagneticReaderRegistry()

    def inspect(self, path: str | Path, **options: Any) -> dict[str, Any]:
        source = Path(path)
        reader_options = self._options(**options)
        reader = self.registry.resolve(source)
        result = dict(reader.inspect(source, reader_options))
        result.setdefault("reader", type(reader).__name__)
        result.setdefault("path", str(source))
        return result

    def read(self, path: str | Path, **options: Any) -> MagneticDataset:
        source = Path(path)
        reader_options = self._options(**options)
        reader = self.registry.resolve(source)
        return reader.read(source, reader_options)

    def read_rover(self, path: str | Path, **options: Any) -> MagneticDataset:
        options["role"] = MagneticDataRole.ROVER
        return self.read(path, **options)

    def read_base(self, path: str | Path, **options: Any) -> MagneticDataset:
        options["role"] = MagneticDataRole.BASE
        options["survey_type"] = MagneticSurveyType.BASE_STATION
        return self.read(path, **options)

    @staticmethod
    def _options(**options: Any) -> ReaderOptions:
        role = options.pop("role", MagneticDataRole.ROVER)
        survey_type = options.pop("survey_type", MagneticSurveyType.GROUND)
        if isinstance(role, str):
            role = MagneticDataRole(role)
        if isinstance(survey_type, str):
            survey_type = MagneticSurveyType(survey_type)
        return ReaderOptions(role=role, survey_type=survey_type, **options)
