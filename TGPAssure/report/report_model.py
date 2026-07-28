from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class ReportSectionType(Enum):
    TEXT = "text"
    TABLE = "table"
    CHART = "chart"
    HEADING = "heading"


@dataclass
class ReportSection(ABC):
    section_type: ReportSectionType
    title: str
    order: int = 0

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        pass


@dataclass
class TextSection(ReportSection):
    content: str = ""
    style: str = "body"

    def __init__(self, title: str, content: str = "", style: str = "body", order: int = 0) -> None:
        super().__init__(ReportSectionType.TEXT, title, order)
        self.content = content
        self.style = style

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.section_type.value,
            "title": self.title,
            "content": self.content,
            "style": self.style,
            "order": self.order
        }


@dataclass
class TableSection(ReportSection):
    headers: List[str] = field(default_factory=list)
    rows: List[List[Any]] = field(default_factory=list)
    column_widths: Optional[List[float]] = None

    def __init__(self, title: str, headers: Optional[List[str]] = None, 
                 rows: Optional[List[List[Any]]] = None, order: int = 0) -> None:
        super().__init__(ReportSectionType.TABLE, title, order)
        self.headers = headers or []
        self.rows = rows or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.section_type.value,
            "title": self.title,
            "headers": self.headers,
            "rows": self.rows,
            "order": self.order
        }


@dataclass
class ChartSection(ReportSection):
    chart_type: str = "bar"
    data: Dict[str, Any] = field(default_factory=dict)
    x_label: str = ""
    y_label: str = ""

    def __init__(
        self,
        title: str,
        chart_type: str = "bar",
        data: Optional[Dict[str, Any]] = None,
        order: int = 0,
        x_label: str = "",
        y_label: str = "",
    ) -> None:
        super().__init__(ReportSectionType.CHART, title, order)
        self.chart_type = chart_type
        self.data = data or {}
        self.x_label = x_label
        self.y_label = y_label

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.section_type.value,
            "title": self.title,
            "chart_type": self.chart_type,
            "data": self.data,
            "x_label": self.x_label,
            "y_label": self.y_label,
            "order": self.order
        }


@dataclass
class HeadingSection(ReportSection):
    level: int = 1

    def __init__(self, title: str, level: int = 1, order: int = 0) -> None:
        super().__init__(ReportSectionType.HEADING, title, order)
        self.level = level

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.section_type.value,
            "title": self.title,
            "level": self.level,
            "order": self.order
        }


class ReportModel:
    def __init__(self, title: str = "TGPAssure QC Report") -> None:
        self.title = title
        self.sections: List[ReportSection] = []
        self.metadata: Dict[str, Any] = {}

    def add_section(self, section: ReportSection) -> None:
        section.order = len(self.sections)
        self.sections.append(section)

    def get_sections_by_type(self, section_type: ReportSectionType) -> List[ReportSection]:
        return [s for s in self.sections if s.section_type == section_type]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "metadata": self.metadata,
            "sections": [s.to_dict() for s in sorted(self.sections, key=lambda x: x.order)]
        }

    def to_json(self) -> str:
        import json
        return json.dumps(self.to_dict(), indent=2)