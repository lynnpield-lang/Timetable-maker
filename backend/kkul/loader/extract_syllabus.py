"""계획서 텍스트 → LLM 구조화 추출 + 근거 검증 + 나눠 저장 (01 A부 2.5 ③–⑤).

실행: uv run python -m kkul.loader.extract_syllabus --term 2026_20
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import logging

from pydantic import BaseModel, Field

from kkul import io, llm
from kkul.models import EVAL_KEYS, Course

log = logging.getLogger(__name__)

WEEK_MIN, WEEK_MAX = 1, 16
EVIDENCE_REQUIRED = ("eval", "teamwork", "attendance", "workload_level", "exams", "assignments")


class EvalPart(BaseModel):
    attend: int | None = None
    homework: int | None = None
    quiz: int | None = None
    mid: int | None = None
    final: int | None = None
    presentation: int | None = None
    project: int | None = None
    etc: int | None = None


class Exams(BaseModel):
    count: int | None = None
    types: list[str] | None = None
    open_book: bool | None = None
    weeks: list[int] | None = None


class Assignment(BaseModel):
    name: str
    team: bool | None = None
    count: int | None = None
    weeks: list[int] | None = None


class Attendance(BaseModel):
    strict: bool | None = None
    rule: str | None = None


class SyllabusExtract(BaseModel):
    eval: EvalPart | None = None
    exams: Exams | None = None
    assignments: list[Assignment] | None = None
    teamwork: bool | None = None
    attendance: Attendance | None = None
    lecture_style: list[str] | None = None
    language: str | None = None
    materials: list[str] | None = None
    prerequisite: str | None = None
    workload_level: int | None = Field(default=None, ge=1, le=5)
    notes: list[str] | None = None
    evidence: dict[str, str] = Field(default_factory=dict)


def _weeks(ws: list[int] | None) -> list[int] | None:
    if ws is None:
        return None
    ok = sorted({w for w in ws if WEEK_MIN <= w <= WEEK_MAX})
    return ok or None


def validate_extract(
    ex: SyllabusExtract, source_text: str, web_eval: dict | None = None
) -> tuple[dict, list[str]]:
    """검증 (01 A부 2.5 ④). 반환: (통과한 항목 dict, 로그)."""
    logs: list[str] = []
    ev_ok = {k: q for k, q in ex.evidence.items() if llm.quote_in_source(q, source_text)}
    for k in set(ex.evidence) - set(ev_ok):
        logs.append(f"근거가 원문에 없음: {k}")

    def has_ev(name: str) -> bool:
        return name in ev_ok

    out: dict = {}
    # 평가 비율
    if ex.eval is not None and has_ev("eval"):
        vals = ex.eval.model_dump()
        nums = [v for v in vals.values() if v is not None]
        if nums and all(0 <= v <= 100 for v in nums) and abs(sum(nums) - 100) <= 1:
            out["eval"] = {k: vals.get(k) for k in EVAL_KEYS}
        else:
            logs.append(f"평가 비율 합 {sum(nums)} → 폐기")
    if web_eval and any(v is not None for v in web_eval.values()):
        if "eval" in out and out["eval"] != web_eval:
            logs.append(f"웹 평가 비율과 다름 (웹 값 사용): web={web_eval} pdf={out['eval']}")
        out.pop("eval", None)
    # 시험
    if ex.exams is not None and has_ev("exams"):
        out["exams"] = {
            "count": ex.exams.count,
            "types": ex.exams.types,
            "open_book": ex.exams.open_book,
            "weeks": _weeks(ex.exams.weeks),
        }
    # 과제
    if ex.assignments is not None and has_ev("assignments"):
        out["assignments"] = [
            {"name": a.name, "team": a.team, "count": a.count, "weeks": _weeks(a.weeks)}
            for a in ex.assignments
        ]
    if ex.teamwork is not None and has_ev("teamwork"):
        out["teamwork"] = ex.teamwork
    if ex.attendance is not None and has_ev("attendance"):
        out["attendance"] = {"strict": ex.attendance.strict, "rule": ex.attendance.rule}
    if ex.workload_level is not None and has_ev("workload_level"):
        out["workload_level"] = ex.workload_level
    for k in ("lecture_style", "language", "materials", "prerequisite", "notes"):
        v = getattr(ex, k)
        if v is not None:
            out[k] = v
    out["evidence"] = {k: q for k, q in ev_ok.items() if k in out or k not in EVIDENCE_REQUIRED}
    return out, logs


def split_for_storage(key: str, items: dict, source: str) -> tuple[dict, dict]:
    """(courses.csv에 넣을 열, profiles.jsonl 한 줄)로 나눈다 (01 A부 2.5 ⑤)."""
    exams = items.get("exams") or {}
    assigns = items.get("assignments")
    deadline = None
    if assigns:
        ws = sorted({w for a in assigns for w in (a.get("weeks") or [])})
        deadline = tuple(ws) or None
    att = items.get("attendance") or {}
    course_cols = {
        "teamwork": items.get("teamwork"),
        "exam_count": exams.get("count"),
        "exam_weeks": tuple(exams["weeks"]) if exams.get("weeks") else None,
        "deadline_weeks": deadline,
        "workload_level": items.get("workload_level"),
        "attendance_strict": att.get("strict"),
    }
    if "eval" in items:
        course_cols["eval"] = items["eval"]
        course_cols["eval_source"] = "pdf_llm"
    if items.get("language"):
        course_cols["language"] = items["language"]
    if items.get("prerequisite"):
        course_cols["prerequisite"] = items["prerequisite"]
    profile = {
        "key": key,
        "source": source,
        "extracted_at": io.now_iso(),
        "lecture_style": items.get("lecture_style"),
        "exams": items.get("exams"),
        "assignments": assigns,
        "attendance": items.get("attendance"),
        "materials": items.get("materials"),
        "prerequisite": items.get("prerequisite"),
        "notes": items.get("notes"),
        "evidence": items.get("evidence") or {},
    }
    return course_cols, profile


def extract_one(
    course: Course, text: str, timeout: float = 60
) -> tuple[dict, dict, list[str]] | None:
    """계획서 텍스트 하나를 추출·검증. LLM이 없거나 실패하면 None."""
    prompt = f"과목: {course.key} {course.name}\n\n--- 계획서 원문 ---\n{text}"
    ex = llm.call_json("syllabus_extract", prompt, SyllabusExtract, timeout=timeout)
    if ex is None:
        return None
    web_eval = dict(course.eval) if course.eval_source == "web" else None
    items, logs = validate_extract(ex, text, web_eval)
    cols, profile = split_for_storage(course.key, items, "pdf")
    return cols, profile, logs


def apply_columns(course: Course, cols: dict) -> Course:
    """추출한 열을 Course에 반영한 새 Course (frozen)."""
    return dataclasses.replace(course, **cols)


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def run(term: str) -> dict:
    """data/raw/syllabus/*.pdf 캐시로 추출을 다시 돌린다 (이미 추출한 분반은 해시가 같으면 건너뜀)."""
    from kkul.loader.syllabus import pdf_text

    courses = io.read_courses(term)
    profiles = io.read_profiles(term)
    stats = {"pdf": 0, "extracted": 0, "skipped": 0, "failed": 0, "scanned": 0}
    for key, c in sorted(courses.items()):
        raw = io.read_raw(f"syllabus/{key}.pdf")
        if raw is None:
            continue
        stats["pdf"] += 1
        text, status = pdf_text(raw)
        if status != "ok":
            stats["scanned"] += 1
            continue
        h = text_hash(text)
        if profiles.get(key, {}).get("text_hash") == h:
            stats["skipped"] += 1
            continue
        res = extract_one(c, text)
        if res is None:
            stats["failed"] += 1
            continue
        cols, profile, logs = res
        for line in logs:
            log.info("%s: %s", key, line)
        profile["text_hash"] = h
        courses[key] = apply_columns(c, cols)
        profiles[key] = profile
        stats["extracted"] += 1
    io.write_courses(term, list(courses.values()))
    io.write_profiles(term, list(profiles.values()))
    return stats


def main() -> None:  # pragma: no cover - CLI
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser(description="계획서 PDF LLM 추출만 다시 실행")
    ap.add_argument("--term", required=True, help="예: 2026_20")
    args = ap.parse_args()
    from dotenv import load_dotenv

    load_dotenv()
    print(run(args.term))


if __name__ == "__main__":  # pragma: no cover
    main()
