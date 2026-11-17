"""KKUL_MOCK에 따라 실제 service 또는 mock을 고른다. ui/도 이 함수로 고르면 된다."""

from __future__ import annotations

from types import ModuleType

_use_mock = False


def use_mock(flag: bool) -> None:
    global _use_mock
    _use_mock = flag


def backend() -> ModuleType:
    """service 또는 mock 모듈 (같은 함수 이름, 같은 반환 형식)."""
    if _use_mock:
        from api import mock

        return mock
    from api import service

    return service
