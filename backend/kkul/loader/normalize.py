"""원본 행 → Course 정규화 (01 A부 4단계)."""

from __future__ import annotations

import logging
import re

from kkul.models import EVAL_KEYS, Course, Slot

log = logging.getLogger(__name__)

DAY_INDEX = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}
_TIME_RE = re.compile(
    r"([월화수목금토])\s*(\d{1,2}):(\d{2})\s*[-~]\s*(\d{1,2}):(\d{2})(?:\s*【([^】]*)】)?"
)
_MODULE_RE = re.compile(r"모듈\s*([A-Z])")
_CREDITS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:\((\d+(?:\.\d+)?)\))?")

# 학교 응답 열 이름 → 우리 필드. ⚠ 1주차에 실제 응답으로 확정 (확인된 것은 ✅)
FIELD_MAP: dict[str, tuple[str, ...]] = {
    "code": ("HAKSU_NO", "SUBJECT_NO"),
    "section": ("BUNBAN", "CLASS_NO"),
    "name": ("GWAMOK_NM", "SUBJECT_NM", "KOR_NM"),
    "name_en": ("GWAMOK_ENG_NM", "ENG_NM"),
    "credits": ("HAKJUM", "HAKJUM_SISU", "CREDIT"),
    "professor": ("GYOSU_NM", "PROF_NM", "STAFF_NM"),
    "time": ("SIGAN_GANGUISIL", "LECT_TIME_ROOM", "TIME_ROOM"),
    "category": ("ISU_GB_NM", "ISU_NM", "COMPLETE_NM"),
    "mode": ("SUUP_HYUNGTAE_NM", "CLASS_TYPE_NM"),
    "english": ("GUKJE_YN", "FOREIGN_LANG_YN", "ENG_YN"),
    "note": ("BIGO", "REMARK"),
    "campus": ("CAMPUS_GB",),
    "restricted_depts": ("SUGANGDAESANG_HAKGWA",),  # ✅ 수업계획서
    "major_depts": ("GYJUNINJ_HAKGWA",),  # ✅ 전체과목 검색
    "language": ("SAYONG_EONEO", "LANG_NM"),
    "prerequisite": ("SUNSU_GWAMOK", "PRE_SUBJECT"),
    "self_study": ("YESEUP_BOKSEUP", "STUDY_TIME"),
    "eval_attend": ("PYUNGGA_CHULSEOK", "EVAL_ATTEND"),
    "eval_homework": ("PYUNGGA_GWAJE", "EVAL_HOMEWORK"),
    "eval_quiz": ("PYUNGGA_QUIZ", "EVAL_QUIZ"),
    "eval_mid": ("PYUNGGA_JUNGGAN", "EVAL_MID"),
    "eval_final": ("PYUNGGA_GIMAL", "EVAL_FINAL"),
    "eval_presentation": ("PYUNGGA_BALPYO", "EVAL_PRESENT"),
    "eval_project": ("PYUNGGA_PROJECT", "EVAL_PROJECT"),
    "eval_etc": ("PYUNGGA_GITA", "EVAL_ETC"),
}


def pick(row: dict, field: str, default: str = "") -> str:
    """FIELD_MAP 후보 열 중 처음으로 값이 있는 것."""
    for col in FIELD_MAP.get(field, (field,)):
        v = row.get(col)
        if v not in (None, ""):
            return str(v).strip()
    return default


def to_minutes(h: str, m: str) -> int:
    return int(h) * 60 + int(m)


def parse_time_string(s: str) -> tuple[list[Slot], str | None, bool, list[str]]:
    """'화12:00-13:15【33303】,목13:30-14:45【33303】' → (조각, 모듈, 플립러닝 여부, 경고)."""
    slots: list[Slot] = []
    warnings: list[str] = []
    module = None
    flipped = False
    if not s:
        return slots, module, flipped, warnings
    mm = _MODULE_RE.search(s)
    if mm:
        module = mm.group(1)
    if "(ON)" in s.upper() and "(OFF)" in s.upper():
        flipped = True
    for m in _TIME_RE.finditer(s):
        day = DAY_INDEX[m.group(1)]
        start = to_minutes(m.group(2), m.group(3))
        end = to_minutes(m.group(4), m.group(5))
        room = (m.group(6) or "").strip()
        if not room or room == "미지정" or not re.fullmatch(r"[0-9A-Za-z\-]+", room):
            room = None
        slots.append(Slot(day, start, end, room))
    leftover = _TIME_RE.sub("", s)
    leftover = re.sub(r"【[^】]*】|[,\s]", "", leftover)
    if leftover:
        warnings.append(f"시간 문자열 일부를 읽지 못함: {leftover}")
    return slots, module, flipped, warnings


def parse_credits(s: str) -> tuple[int, int]:
    """'3(3)' → (학점 3, 시수 3)."""
    m = _CREDITS_RE.search(s or "")
    if not m:
        return 0, 0
    c = int(float(m.group(1)))
    h = int(float(m.group(2))) if m.group(2) else c
    return c, h


def parse_ratio(s: str | None) -> int | None:
    """'30' → 30, '' → None (0으로 채우지 않는다)."""
    if s is None:
        return None
    s = str(s).strip().rstrip("%")
    if s == "":
        return None
    try:
        return int(round(float(s)))
    except ValueError:
        return None


def parse_dept_list(s: str | None) -> tuple[str, ...]:
    """'경영학과,자유전공계열' → ('경영학과', '자유전공계열'). 비면 () = 제한 없음."""
    if not s:
        return ()
    return tuple(x.strip() for x in re.split(r"[,/|]", s) if x.strip())


def parse_bool(s: str | None) -> bool:
    return str(s or "").strip().upper() in ("Y", "1", "TRUE", "O", "예")


def normalize_course(
    row: dict, extra: dict | None = None, campus_default: int = 1
) -> tuple[Course, list[str]]:
    """과목 목록 행 (+ 전체과목 검색·수업계획서 필드) → (Course, 경고)."""
    merged = {**row, **(extra or {})}
    code = pick(merged, "code")
    raw_section = pick(merged, "section")
    if not code or not raw_section:
        raise ValueError("학수번호 또는 분반이 없음")
    section = raw_section.zfill(2)
    slots, module, flipped, warns = parse_time_string(pick(merged, "time"))
    credits, hours = parse_credits(pick(merged, "credits"))
    mode = pick(merged, "mode") or ("플립러닝" if flipped else "오프라인")
    if flipped and "플립" not in mode:
        mode = "플립러닝"
    note = pick(merged, "note")
    if module is None:
        mm = _MODULE_RE.search(note)
        module = mm.group(1) if mm else None
    ev = {k: parse_ratio(pick(merged, f"eval_{k}", "") or None) for k in EVAL_KEYS}
    has_eval = any(v is not None for v in ev.values())
    campus = pick(merged, "campus")
    c = Course(
        key=f"{code}-{section}",
        code=code,
        section=section,
        name=pick(merged, "name"),
        name_en=pick(merged, "name_en"),
        credits=credits,
        hours=hours,
        professor=pick(merged, "professor"),
        campus=int(campus) if campus.isdigit() else campus_default,
        slots=tuple(slots),
        category=pick(merged, "category"),
        mode=mode,
        is_online="온라인" in mode,
        module=module,
        english=parse_bool(pick(merged, "english")),
        note=note,
        restricted_depts=parse_dept_list(pick(merged, "restricted_depts")),
        major_depts=parse_dept_list(pick(merged, "major_depts")),
        language=pick(merged, "language") or None,
        prerequisite=pick(merged, "prerequisite") or None,
        eval=ev,
        eval_source="web" if has_eval else "none",
        self_study=pick(merged, "self_study") or None,
        teamwork=None,
        exam_count=None,
        exam_weeks=None,
        deadline_weeks=None,
        workload_level=None,
        attendance_strict=None,
    )
    return c, warns


def validate_course(c: Course) -> list[str]:
    """검증 (01 A부 5단계): 시작 < 끝, 8:00–23:00, 월–토, 평가 비율 합 100."""
    errs = []
    for s in c.slots:
        if not s.start < s.end:
            errs.append(f"{c.key}: 시작이 끝보다 늦음 {s}")
        if s.start < 8 * 60 or s.end > 23 * 60:
            errs.append(f"{c.key}: 8:00–23:00 밖의 수업 {s}")
        if s.day not in DAY_INDEX.values():
            errs.append(f"{c.key}: 요일 범위 밖 {s}")
    if c.has_eval:
        total = sum(v or 0 for v in c.eval.values())
        if abs(total - 100) > 1:
            errs.append(f"{c.key}: 평가 비율 합이 {total}")
    return errs
