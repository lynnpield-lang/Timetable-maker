"""선택한 시간표 상세 보기 (01 B부 8). 화면을 열 때 LLM을 기다리지 않는다."""

from __future__ import annotations

import json
from collections import Counter

from pydantic import BaseModel, Field

from kkul import llm
from kkul.config import Config
from kkul.models import DAY_NAMES, EVAL_KEYS, Course, Timetable
from kkul.timetable.analyzer import Analyzer, effective_slots, move_minutes, weekly_load

STYLE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("토론형", ("토론", "발표", "세미나", "discussion")),
    ("실습형", ("실습", "실험", "코딩", "프로젝트", "lab")),
)


def style_type(card: dict) -> str:
    """강의 스타일 태그 → 강의형 / 토론형 / 실습형."""
    tags = " ".join(card.get("lecture_style") or []).lower()
    for name, words in STYLE_RULES:
        if any(w.lower() in tags for w in words):
            return name
    return "강의형"


def course_card(key: str, profiles: dict[str, dict], courses: dict[str, Course]) -> dict:
    """과목 카드 (01 B부 8.1). 계획서가 없으면 칸을 비우고 has_profile = False."""
    c = courses[key]
    p = profiles.get(key) or {}
    exams = p.get("exams") or {}
    attendance = p.get("attendance") or {}
    return {
        "key": key,
        "code": c.code,
        "name": c.name,
        "professor": c.professor,
        "credits": c.credits,
        "category": c.category,
        "mode": c.mode,
        "is_online": c.is_online,
        "english": c.english,
        "language": c.language,
        "lecture_style": p.get("lecture_style"),
        "eval": {k: c.eval.get(k) for k in EVAL_KEYS},
        "eval_source": c.eval_source,
        "exam_count": exams.get("count", c.exam_count),
        "exam_types": exams.get("types"),
        "open_book": exams.get("open_book"),
        "exam_weeks": exams.get("weeks") or (list(c.exam_weeks) if c.exam_weeks else None),
        "assignments": p.get("assignments"),
        "teamwork": c.teamwork,
        "attendance_rule": attendance.get("rule"),
        "attendance_strict": c.attendance_strict,
        "workload_level": c.workload_level,
        "deadline_weeks": list(c.deadline_weeks) if c.deadline_weeks else None,
        "prerequisite": p.get("prerequisite") or c.prerequisite,
        "materials": p.get("materials"),
        "notes": p.get("notes"),
        "evidence": p.get("evidence") or {},
        "source": p.get("source") or ("web" if c.eval_source == "web" else None),
        "has_profile": bool(p),
    }


def _week_items(c: Course, w: int) -> list[str]:
    items = []
    if c.exam_weeks and w in c.exam_weeks:
        items.append(f"{c.name} 시험")
    if c.deadline_weeks and w in c.deadline_weeks:
        items.append(f"{c.name} 과제·발표 마감")
    return items


def timetable_summary(
    tt: Timetable, courses: dict[str, Course], cards: list[dict], cfg: Config, features: dict
) -> dict:
    """시간표 전체 요약 (01 B부 8.2): 주차별 부담(과목별 쌓기), 몰리는 주, 평가 구성, 개수."""
    cs = [courses[k] for k in tt]
    per_course = {c.key: weekly_load([c], cfg) for c in cs}
    total = weekly_load(cs, cfg)
    crunch = []
    for w, v in enumerate(total, start=1):
        if v >= cfg.crunch_threshold:
            items = [it for c in cs for it in _week_items(c, w)]
            crunch.append(
                {"week": w, "load": v, "items": items, "text": f"{w}주차: " + " + ".join(items)}
            )
    styles = Counter(style_type(card) for card in cards if card.get("lecture_style"))
    coverage = features.get("eval_coverage") or 0.0
    return {
        "weekly_load": total,
        "weekly_load_by_course": per_course,
        "crunch_weeks": crunch,
        "eval": {
            "exam_ratio": features.get("exam_ratio"),
            "homework_ratio": features.get("homework_ratio"),
            "attend_ratio": features.get("attend_ratio"),
            "coverage": coverage,
            "covered_courses": sum(1 for c in cs if c.has_eval),
            "total_courses": len(cs),
            "low_coverage": coverage < cfg.eval_coverage_warn,
        },
        "counts": {
            "teamwork": features.get("teamwork_courses", 0),
            "strict_attendance": features.get("strict_attendance", 0),
            "english": sum(1 for c in cs if c.english),
            "online": sum(1 for c in cs if c.is_online),
            "no_profile": sum(1 for card in cards if not card["has_profile"]),
        },
        "styles": dict(styles),
    }


def grid_blocks(
    tt: Timetable, courses: dict[str, Course], late_pairs: set | None = None
) -> list[dict]:
    """주간 격자에 그릴 블록."""
    out = []
    for i, k in enumerate(sorted(tt)):
        c = courses[k]
        for s in c.slots:
            out.append(
                {
                    "key": k,
                    "name": c.name,
                    "day": s.day,
                    "start": s.start,
                    "end": s.end,
                    "room": s.room,
                    "color": i,
                    "online": c.is_online,
                    "late_risk": bool(late_pairs and (k, s.day, s.start) in late_pairs),
                }
            )
    return out


def late_risk_slots(tt: Timetable, courses: dict[str, Course], buildings: dict, cfg: Config) -> set:
    """지각 위험이 있는 (분반, 요일, 시작) — 이동 뒤 도착하는 수업."""
    by_day: dict[int, list] = {}
    for k in tt:
        for s in effective_slots(courses[k], cfg):
            by_day.setdefault(s.day, []).append((s.start, s.end, s.building, k))
    out = set()
    for d, seq in by_day.items():
        seq.sort()
        for a, b in zip(seq, seq[1:], strict=False):
            t = move_minutes(a[2], b[2], buildings, cfg)
            if t is not None and t > b[0] - a[1]:
                out.add((b[3], d, b[0]))
    return out


def tags_for(f: dict) -> list[str]:
    """결과 카드 요약 태그. 예: ["금 우주공강", "슈퍼공강 없음", "9시 수업 1회"]."""
    tags = []
    if f.get("free_day_set"):
        days = [DAY_NAMES[int(d)] for d in str(f["free_day_set"]).split("|") if d != ""]
        tags.append(f"{'·'.join(days)} 우주공강")
    sg = f.get("super_gaps") or 0
    tags.append("슈퍼공강 없음" if sg == 0 else f"슈퍼공강 {int(sg)}회")
    md = f.get("morning_days") or 0
    tags.append("9시 수업 없음" if md == 0 else f"9시 수업 {int(md)}회")
    if (f.get("late_risk") or 0) > 0:
        tags.append(f"지각 위험 {int(f['late_risk'])}곳")
    if (f.get("teamwork_courses") or 0) > 0:
        tags.append(f"팀플 {int(f['teamwork_courses'])}과목")
    return tags


def details(
    tt: Timetable,
    courses: dict[str, Course],
    profiles: dict[str, dict],
    cfg: Config,
    buildings: dict | None = None,
    major_keys=(),
) -> dict:
    """선택한 시간표 상세: 과목 카드 + 전체 요약 + 격자 + 특징 (01 B부 8.1–8.2)."""
    an = Analyzer(courses, buildings, cfg, major_keys)
    features = an.analyze(tt)
    cards = [course_card(k, profiles, courses) for k in sorted(tt)]
    for card in cards:
        card["is_major"] = card["key"] in set(major_keys)
    late = late_risk_slots(tt, courses, buildings or {}, cfg)
    return {
        "sections": list(sorted(tt)),
        "features": features,
        "tags": tags_for(features),
        "grid": grid_blocks(tt, courses, late),
        "cards": cards,
        "summary": timetable_summary(tt, courses, cards, cfg, features),
    }


class _SummaryOut(BaseModel):
    text: str = Field(description="3–5문장 한국어 요약")


def summarize_with_llm(cards: list[dict], summary: dict) -> str | None:
    """종합 코멘트 (01 B부 8.3). 입력에 없는 숫자·학수번호가 나온 문장은 버린다. 실패하면 None."""
    slim_cards = [
        {k: v for k, v in c.items() if k not in ("evidence",) and v not in (None, [], {})}
        for c in cards
    ]
    payload = {"cards": slim_cards, "summary": summary}
    out = llm.call_json(
        "timetable_summary",
        json.dumps(payload, ensure_ascii=False),
        _SummaryOut,
        timeout=10,
    )
    if out is None:
        return None
    text = llm.keep_grounded(out.text, payload)
    return text or None
