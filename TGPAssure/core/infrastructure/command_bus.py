from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, List, TypeVar, Generic, Any

T = TypeVar('T')

class Command(ABC, Generic[T]):
    @abstractmethod
    def execute(self) -> T:
        pass

    @abstractmethod
    def undo(self) -> None:
        pass

class CommandBus:
    def __init__(self) -> None:
        self._undo_stack: List[Command[Any]] = []
        self._redo_stack: List[Command[Any]] = []

    def push(self, command: Command[Any]) -> None:
        self._redo_stack.clear()
        self._undo_stack.append(command)
        command.execute()

    def undo(self) -> None:
        if not self._undo_stack:
            return
        command = self._undo_stack.pop()
        command.undo()
        self._redo_stack.append(command)

    def redo(self) -> None:
        if not self._redo_stack:
            return
        command = self._redo_stack.pop()
        command.execute()
        self._undo_stack.append(command)

    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    def clear(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()

    def get_undo_count(self) -> int:
        return len(self._undo_stack)

    def get_redo_count(self) -> int:
        return len(self._redo_stack)