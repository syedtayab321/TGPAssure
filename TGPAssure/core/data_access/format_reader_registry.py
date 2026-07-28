from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Type, Optional, Any
from pathlib import Path


class IFileReader(ABC):
    @abstractmethod
    def open(self, path: Path) -> Any:
        pass


class FormatReaderRegistry:
    def __init__(self) -> None:
        self._readers: Dict[str, Type[IFileReader]] = {}

    def register(self, format_id: str, reader_class: Type[IFileReader]) -> None:
        self._readers[format_id] = reader_class

    def get(self, format_id: str) -> Optional[Type[IFileReader]]:
        return self._readers.get(format_id)

    def has(self, format_id: str) -> bool:
        return format_id in self._readers

    def list_formats(self) -> list[str]:
        return list(self._readers.keys())

    def clear(self) -> None:
        self._readers.clear()