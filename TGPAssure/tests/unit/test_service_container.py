from __future__ import annotations

import pytest
from typing import Protocol, runtime_checkable

from core.infrastructure.service_container import ServiceContainer, ServiceNotRegisteredError

@runtime_checkable
class TestInterface(Protocol):
    def get_value(self) -> str:
        pass

class TestImplementation:
    def __init__(self, value: str = "test") -> None:
        self._value = value

    def get_value(self) -> str:
        return self._value

class AnotherImplementation:
    def get_value(self) -> str:
        return "another"

class UnrelatedClass:
    pass

def test_register_and_resolve() -> None:
    container = ServiceContainer()
    service = TestImplementation("hello")
    container.register(TestInterface, service)
    resolved = container.resolve(TestInterface)
    assert resolved is service
    assert resolved.get_value() == "hello"

def test_resolve_not_registered_raises_error() -> None:
    container = ServiceContainer()
    with pytest.raises(ServiceNotRegisteredError) as exc_info:
        container.resolve(TestInterface)
    assert "TestInterface" in str(exc_info.value)

def test_has_method() -> None:
    container = ServiceContainer()
    assert not container.has(TestInterface)
    container.register(TestInterface, TestImplementation())
    assert container.has(TestInterface)

def test_clear_method() -> None:
    container = ServiceContainer()
    container.register(TestInterface, TestImplementation())
    container.register(UnrelatedClass, UnrelatedClass())
    assert container.has(TestInterface)
    assert container.has(UnrelatedClass)
    container.clear()
    assert not container.has(TestInterface)
    assert not container.has(UnrelatedClass)

def test_multiple_registrations_overwrite() -> None:
    container = ServiceContainer()
    service1 = TestImplementation("first")
    service2 = TestImplementation("second")
    container.register(TestInterface, service1)
    resolved1 = container.resolve(TestInterface)
    assert resolved1.get_value() == "first"
    container.register(TestInterface, service2)
    resolved2 = container.resolve(TestInterface)
    assert resolved2.get_value() == "second"
    assert resolved2 is service2

def test_register_different_types() -> None:
    container = ServiceContainer()
    test_service = TestImplementation()
    unrelated = UnrelatedClass()
    container.register(TestInterface, test_service)
    container.register(UnrelatedClass, unrelated)
    resolved_test = container.resolve(TestInterface)
    resolved_unrelated = container.resolve(UnrelatedClass)
    assert resolved_test is test_service
    assert resolved_unrelated is unrelated

def test_interface_check_with_protocol() -> None:
    container = ServiceContainer()
    service = TestImplementation()
    container.register(TestInterface, service)
    resolved = container.resolve(TestInterface)
    assert isinstance(resolved, TestInterface)
    assert resolved.get_value() == "test"

def test_error_message_contains_type_name() -> None:
    container = ServiceContainer()
    with pytest.raises(ServiceNotRegisteredError) as exc_info:
        container.resolve(TestInterface)
    error_message = str(exc_info.value)
    assert "TestInterface" in error_message
    assert "not registered" in error_message

def test_register_none_raises() -> None:
    container = ServiceContainer()
    with pytest.raises(ServiceNotRegisteredError):
        container.register(TestInterface, None)