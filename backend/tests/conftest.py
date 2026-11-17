from pathlib import Path

import pytest

from kkul import io
from kkul.config import Config
from kkul.models import EVAL_KEYS, Course, Slot

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def cfg() -> Config:
    return Config()


@pytest.fixture
def fixture_dir(monkeypatch):
    old = io.data_dir()
    io.set_data_dir(FIXTURES)
    yield FIXTURES
    io.set_data_dir(old)


@pytest.fixture
def courses(fixture_dir):
    return io.read_courses("test")


@pytest.fixture
def buildings(fixture_dir):
    return io.read_buildings()


def mk(key: str, slots, credits: int = 3, **kw) -> Course:
    """테스트용 Course를 짧게 만든다. slots: [(요일, 시작, 끝, 강의실)]."""
    code, sec = key.split("-")
    base = dict(
        key=key, code=code, section=sec, name=kw.pop("name", code), name_en="", credits=credits,
        hours=credits, professor=kw.pop("professor", "교수"), campus=1,
        slots=tuple(Slot(*s) if len(s) == 4 else Slot(*s, None) for s in slots),
        category="전공핵심", mode="오프라인", is_online=False, module=None, english=False, note="",
        restricted_depts=(), major_depts=(), language=None, prerequisite=None,
        eval={k: None for k in EVAL_KEYS}, eval_source="none", self_study=None, teamwork=None,
        exam_count=None, exam_weeks=None, deadline_weeks=None, workload_level=None,
        attendance_strict=None,
    )  # fmt: skip
    base.update(kw)
    return Course(**base)


def by_key(*cs: Course) -> dict[str, Course]:
    return {c.key: c for c in cs}
