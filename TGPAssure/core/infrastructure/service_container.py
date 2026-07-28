from __future__ import annotations

from typing import TypeVar, Type, Dict, Any, cast

T = TypeVar('T')

class ServiceNotRegisteredError(Exception):
    def __init__(self, interface_type: Type[Any]) -> None:
        self.interface_type = interface_type
        super().__init__(f"Service of type {interface_type.__name__} is not registered")

class ServiceContainer:
    def __init__(self) -> None:
        self._services: Dict[Type[Any], Any] = {}

    def register(self, interface_type: Type[T], instance: T) -> None:
        if instance is None:
            raise ServiceNotRegisteredError(interface_type)
        self._services[interface_type] = instance

    def resolve(self, interface_type: Type[T]) -> T:
        if interface_type not in self._services:
            raise ServiceNotRegisteredError(interface_type)
        return cast(T, self._services[interface_type])

    def has(self, interface_type: Type[Any]) -> bool:
        return interface_type in self._services

    def clear(self) -> None:
        self._services.clear()