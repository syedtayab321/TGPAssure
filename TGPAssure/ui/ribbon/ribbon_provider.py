from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional


@dataclass
class RibbonAction:
    label: str
    action_id: str
    enabled_predicate: Optional[Callable[[], bool]] = None
    icon_path: Optional[Path] = None
    icon: str = ""
    badge: Optional[str] = None
    presentation: str = "large"
    column: Optional[int] = None
    checkable: bool = False
    checked: bool = False
    accent: bool = False
    has_menu: bool = False


@dataclass
class RibbonGroup:
    label: str
    actions: List[RibbonAction]
    icon_path: Optional[Path] = None


class RibbonProvider(ABC):
    @abstractmethod
    def ribbon_tab_id(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def build_ribbon_groups(self) -> List[RibbonGroup]:
        raise NotImplementedError