from __future__ import annotations

import pytest
from typing import List

from core.infrastructure.command_bus import Command, CommandBus

class AddItemCommand(Command[List[str]]):
    def __init__(self, items: List[str], item: str) -> None:
        self.items = items
        self.item = item
        self._executed = False

    def execute(self) -> List[str]:
        self.items.append(self.item)
        self._executed = True
        return self.items

    def undo(self) -> None:
        if self._executed:
            self.items.pop()
            self._executed = False

class RemoveItemCommand(Command[List[str]]):
    def __init__(self, items: List[str], item: str) -> None:
        self.items = items
        self.item = item
        self._removed = False
        self._index: int | None = None

    def execute(self) -> List[str]:
        if self.item in self.items:
            self._index = self.items.index(self.item)
            self.items.remove(self.item)
            self._removed = True
        return self.items

    def undo(self) -> None:
        if self._removed and self._index is not None:
            self.items.insert(self._index, self.item)
            self._removed = False

class CounterCommand(Command[int]):
    def __init__(self) -> None:
        self.value = 0

    def execute(self) -> int:
        self.value += 1
        return self.value

    def undo(self) -> None:
        self.value -= 1

def test_push_and_execute_command() -> None:
    bus = CommandBus()
    items: List[str] = []
    command = AddItemCommand(items, "test")
    bus.push(command)
    assert "test" in items
    assert len(items) == 1

def test_undo_single_command() -> None:
    bus = CommandBus()
    items: List[str] = []
    command = AddItemCommand(items, "test")
    bus.push(command)
    assert len(items) == 1
    bus.undo()
    assert len(items) == 0

def test_redo_single_command() -> None:
    bus = CommandBus()
    items: List[str] = []
    command = AddItemCommand(items, "test")
    bus.push(command)
    assert len(items) == 1
    bus.undo()
    assert len(items) == 0
    bus.redo()
    assert len(items) == 1
    assert items[0] == "test"

def test_multiple_commands_undo_redo_order() -> None:
    bus = CommandBus()
    items: List[str] = []
    bus.push(AddItemCommand(items, "a"))
    bus.push(AddItemCommand(items, "b"))
    bus.push(AddItemCommand(items, "c"))
    assert items == ["a", "b", "c"]
    bus.undo()
    assert items == ["a", "b"]
    bus.undo()
    assert items == ["a"]
    bus.redo()
    assert items == ["a", "b"]
    bus.redo()
    assert items == ["a", "b", "c"]

def test_new_command_clears_redo_stack() -> None:
    bus = CommandBus()
    items: List[str] = []
    bus.push(AddItemCommand(items, "a"))
    bus.push(AddItemCommand(items, "b"))
    assert items == ["a", "b"]
    bus.undo()
    assert items == ["a"]
    bus.push(AddItemCommand(items, "c"))
    assert items == ["a", "c"]
    assert not bus.can_redo()

def test_can_undo_and_can_redo() -> None:
    bus = CommandBus()
    assert not bus.can_undo()
    assert not bus.can_redo()
    bus.push(CounterCommand())
    assert bus.can_undo()
    assert not bus.can_redo()
    bus.undo()
    assert not bus.can_undo()
    assert bus.can_redo()

def test_undo_with_empty_stack_does_nothing() -> None:
    bus = CommandBus()
    bus.undo()
    assert not bus.can_undo()

def test_redo_with_empty_stack_does_nothing() -> None:
    bus = CommandBus()
    bus.redo()
    assert not bus.can_redo()

def test_clear_method() -> None:
    bus = CommandBus()
    bus.push(CounterCommand())
    bus.push(CounterCommand())
    assert bus.get_undo_count() == 2
    bus.clear()
    assert bus.get_undo_count() == 0
    assert bus.get_redo_count() == 0
    assert not bus.can_undo()
    assert not bus.can_redo()

def test_complex_undo_redo_sequence() -> None:
    bus = CommandBus()
    items: List[str] = []
    bus.push(AddItemCommand(items, "a"))
    bus.push(AddItemCommand(items, "b"))
    bus.push(AddItemCommand(items, "c"))
    assert items == ["a", "b", "c"]
    bus.undo()
    assert items == ["a", "b"]
    bus.push(AddItemCommand(items, "d"))
    assert items == ["a", "b", "d"]
    bus.undo()
    assert items == ["a", "b"]
    bus.undo()
    assert items == ["a"]
    bus.redo()
    assert items == ["a", "b"]
    bus.redo()
    assert items == ["a", "b", "d"]
    assert not bus.can_redo()

def test_remove_item_undo_redo() -> None:
    bus = CommandBus()
    items: List[str] = ["a", "b", "c"]
    bus.push(RemoveItemCommand(items, "b"))
    assert items == ["a", "c"]
    bus.undo()
    assert items == ["a", "b", "c"]
    bus.redo()
    assert items == ["a", "c"]

def test_command_return_values() -> None:
    bus = CommandBus()
    counter = CounterCommand()
    bus.push(counter)
    assert counter.value == 1
    bus.undo()
    assert counter.value == 0
    bus.redo()
    assert counter.value == 1
