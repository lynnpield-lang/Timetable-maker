"""수강 자격과 전공 인정 (01 B부 1.5)."""

from __future__ import annotations

import re

from kkul.models import Course

_SUFFIX_RE = re.compile(r"(과|부|전공)$")  # 경영학과·경영학부·경영학전공 → 경영학


def normalize_dept(name: str, alias: dict[str, str] | None = None) -> str:
    """학과 이름 정규화 ν: 공백 제거, 별칭 적용, 학과/학부/전공 접미사 통일."""
    s = re.sub(r"\s+", "", name or "")
    if alias:
        s = alias.get(s, s)
        s = re.sub(r"\s+", "", s)
    s = _SUFFIX_RE.sub("", s)
    if alias:  # 접미사를 뗀 이름에 대한 별칭도 확인
        s2 = re.sub(r"\s+", "", alias.get(s, s))
        s = _SUFFIX_RE.sub("", s2)
    return s


def _norm_set(names, alias) -> set[str]:
    return {normalize_dept(n, alias) for n in names if n}


def is_eligible(course: Course, user_depts, alias: dict[str, str] | None = None) -> bool:
    """수강 가능: 제한 학과가 없거나, 내 학과 중 하나가 제한 학과에 있다."""
    if not course.restricted_depts:
        return True
    return bool(_norm_set(user_depts, alias) & _norm_set(course.restricted_depts, alias))


def is_major(course: Course, user_depts, alias: dict[str, str] | None = None) -> bool:
    """전공 인정: 내 학과 중 하나가 전공 인정 학과에 있다."""
    if not course.major_depts:
        return False
    return bool(_norm_set(user_depts, alias) & _norm_set(course.major_depts, alias))
