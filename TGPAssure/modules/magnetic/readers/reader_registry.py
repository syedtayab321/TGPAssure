from __future__ import annotations

from pathlib import Path

from modules.magnetic.exceptions import MagneticReadError
from modules.magnetic.readers.base_reader import MagneticFormatReader
from modules.magnetic.readers.bulucu_acquisition_reader import BulucuAcquisitionReader
from modules.magnetic.readers.enmag_acquisition_reader import EnmagAcquisitionReader
from modules.magnetic.readers.enmag37_reader import Enmag37Reader
from modules.magnetic.readers.generic_delimited_reader import GenericDelimitedMagneticReader


class MagneticReaderRegistry:
    """Ordered registry of magnetic input readers.

    Instrument/native formats must be tested before the generic delimited
    reader, otherwise event-based TXT/LOG files can be misinterpreted as a
    malformed CSV table.
    """

    def __init__(self) -> None:
        self._readers: list[MagneticFormatReader] = [
            BulucuAcquisitionReader(),
            EnmagAcquisitionReader(),
            Enmag37Reader(),
            GenericDelimitedMagneticReader(),
        ]

    def register(self, reader: MagneticFormatReader, *, first: bool = False) -> None:
        if first:
            self._readers.insert(0, reader)
        else:
            self._readers.append(reader)

    def resolve(self, path: str | Path) -> MagneticFormatReader:
        source = Path(path)
        for reader in self._readers:
            if reader.can_read(source):
                return reader
        raise MagneticReadError(
            f"No magnetic reader can identify '{source.name}'. "
            "Supported inputs include Bulucu acquisition logs, EnMag event logs, ENmag37 exports, "
            "and delimited CSV/TXT/DAT/LOG/XYZ tables."
        )
