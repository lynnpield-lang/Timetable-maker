"""A'부: 사용자 캡처 → 정원·신청 인원 (01 A부 '정원·경쟁률: 캡처 입력').

캡처 이미지와 결과는 서버 메모리에만 둔다. 이 모듈은 파일을 쓰지 않는다.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from kkul import llm
from kkul.models import Competition, Course

_KEY_RE = re.compile(r"([A-Z]{2,4}\d{3,4})\s*[-_ ]?\s*(\d{1,2})\b")
_LINE_RE = re.compile(r"([A-Z]{2,4}\d{3,4})\s*[-_ ]\s*(\d{1,2})\D+?(\d+)\D+?(\d+)")


class CaptureRow(BaseModel):
    key: str
    capacity: int | None = None
    applied: int | None = None


class CaptureOut(BaseModel):
    rows: list[CaptureRow]


def normalize_key(raw: str) -> str | None:
    """'BIZ2021-1', 'BIZ2021 01' → 'BIZ2021-01'."""
    m = _KEY_RE.search(raw.upper())
    if not m:
        return None
    return f"{m.group(1)}-{int(m.group(2)):02d}"


def parse_text(text: str) -> list[CaptureRow]:
    """붙여넣은 텍스트에서 '학수번호-분반 정원 신청인원'을 줄마다 읽는다 (LLM 없이)."""
    out = []
    for line in text.splitlines():
        m = _LINE_RE.search(line.upper())
        if m:
            out.append(
                CaptureRow(
                    key=f"{m.group(1)}-{int(m.group(2)):02d}",
                    capacity=int(m.group(3)),
                    applied=int(m.group(4)),
                )
            )
    return out


def check_rows(rows: list[CaptureRow], courses: dict[str, Course]) -> list[dict]:
    """대조: 없는 키·이상값을 표시한다. 사용자가 표에서 고친 뒤 확정한다."""
    out = []
    seen = set()
    for r in rows:
        key = normalize_key(r.key) or r.key
        issue = None
        if key not in courses:
            issue = "없는 분반이에요"
        elif key in seen:
            issue = "같은 분반이 두 번 나왔어요"
        elif r.capacity is None or r.applied is None:
            issue = "숫자를 읽지 못했어요"
        elif r.capacity <= 0:
            issue = "정원이 0 이하예요"
        elif r.applied < 0:
            issue = "신청 인원이 음수예요"
        seen.add(key)
        out.append(
            {
                "key": key,
                "capacity": r.capacity,
                "applied": r.applied,
                "ok": issue is None,
                "issue": issue,
            }
        )
    return out


def read_capture(
    images: list[llm.Image], text: str | None, courses: dict[str, Course]
) -> list[dict]:
    """캡처 이미지(LLM 비전)와 붙여넣은 텍스트를 읽어 확인용 행을 만든다."""
    rows: list[CaptureRow] = []
    if images:
        out = llm.call_json(
            "capture_read",
            "캡처에 보이는 분반별 정원과 신청 인원을 rows로 옮겨라.",
            CaptureOut,
            timeout=20,
            images=images,
            use_cache=False,
        )
        if out is not None:
            rows += out.rows
    if text:
        rows += parse_text(text)
    return check_rows(rows, courses)


def to_competition(rows: list[dict], source: str = "capture") -> dict[str, Competition]:
    """사용자가 확인한 행 → {키: Competition}."""
    out = {}
    for r in rows:
        if r.get("capacity") and r.get("applied") is not None and r["capacity"] > 0:
            out[r["key"]] = Competition(r["key"], int(r["capacity"]), int(r["applied"]), source)
    return out
