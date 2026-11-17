"""데이터 파일 읽기·쓰기 (03_interfaces.md 2장). 다른 모듈은 pd.read_csv로 직접 읽지 않는다."""

from __future__ import annotations

import csv
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from kkul.config import DEFAULT_CONFIG
from kkul.errors import DataNotBuilt
from kkul.models import EVAL_KEYS, Course, Slot

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_data_dir: Path = PROJECT_ROOT / "data"

KST = timezone(timedelta(hours=9))

COURSE_COLUMNS: tuple[str, ...] = (
    "key",
    "code",
    "section",
    "name",
    "name_en",
    "credits",
    "hours",
    "professor",
    "campus",
    "slots",
    "rooms",
    "category",
    "mode",
    "is_online",
    "module",
    "english",
    "note",
    "restricted_depts",
    "major_depts",
    "language",
    "prerequisite",
    *(f"eval_{k}" for k in EVAL_KEYS),
    "eval_source",
    "self_study",
    "teamwork",
    "exam_count",
    "exam_weeks",
    "deadline_weeks",
    "workload_level",
    "attendance_strict",
)


def data_dir() -> Path:
    """현재 데이터 폴더."""
    return _data_dir


def set_data_dir(path: str | Path) -> None:
    """데이터 폴더를 바꾼다 (테스트·목업용)."""
    global _data_dir
    _data_dir = Path(path)


def now_iso() -> str:
    """한국 시간 ISO 8601 문자열."""
    return datetime.now(KST).isoformat(timespec="seconds")


# ------------------------------------------------------------------ 값 변환


def _enc_bool(v: bool | None) -> str:
    return "" if v is None else ("1" if v else "0")


def _dec_bool(s: str) -> bool | None:
    s = s.strip()
    if s == "":
        return None
    return s in ("1", "true", "True")


def _enc_int(v: int | None) -> str:
    return "" if v is None else str(int(v))


def _dec_int(s: str) -> int | None:
    s = s.strip()
    if s == "":
        return None
    return int(float(s))


def _enc_str(v: str | None) -> str:
    return "" if v is None else v


def _dec_opt_str(s: str) -> str | None:
    return s if s != "" else None


def _enc_list(v) -> str:
    return "" if v is None else "|".join(str(x) for x in v)


def _dec_str_list(s: str) -> tuple[str, ...]:
    return tuple(x for x in s.split("|") if x) if s else ()


def _dec_int_list(s: str) -> tuple[int, ...] | None:
    if s.strip() == "":
        return None
    return tuple(int(x) for x in s.split("|") if x != "")


def encode_slots(slots: tuple[Slot, ...]) -> tuple[str, str]:
    """Slot 목록 → (slots 열, rooms 열)."""
    s = ";".join(f"{x.day}-{x.start}-{x.end}" for x in slots)
    r = ";".join(x.room or "" for x in slots) if any(x.room for x in slots) else ""
    return s, r


def decode_slots(slots: str, rooms: str) -> tuple[Slot, ...]:
    """(slots 열, rooms 열) → Slot 목록."""
    if not slots.strip():
        return ()
    parts = slots.split(";")
    room_parts = rooms.split(";") if rooms else [""] * len(parts)
    if len(room_parts) < len(parts):
        room_parts += [""] * (len(parts) - len(room_parts))
    out = []
    for p, r in zip(parts, room_parts, strict=False):
        d, s, e = (int(x) for x in p.split("-"))
        out.append(Slot(d, s, e, r or None))
    return tuple(out)


def course_to_row(c: Course) -> dict[str, str]:
    """Course → CSV 한 줄."""
    slots, rooms = encode_slots(c.slots)
    row = {
        "key": c.key,
        "code": c.code,
        "section": c.section,
        "name": c.name,
        "name_en": c.name_en,
        "credits": str(c.credits),
        "hours": str(c.hours),
        "professor": c.professor,
        "campus": str(c.campus),
        "slots": slots,
        "rooms": rooms,
        "category": c.category,
        "mode": c.mode,
        "is_online": _enc_bool(c.is_online),
        "module": _enc_str(c.module),
        "english": _enc_bool(c.english),
        "note": c.note,
        "restricted_depts": _enc_list(c.restricted_depts),
        "major_depts": _enc_list(c.major_depts),
        "language": _enc_str(c.language),
        "prerequisite": _enc_str(c.prerequisite),
        "eval_source": c.eval_source,
        "self_study": _enc_str(c.self_study),
        "teamwork": _enc_bool(c.teamwork),
        "exam_count": _enc_int(c.exam_count),
        "exam_weeks": _enc_list(c.exam_weeks),
        "deadline_weeks": _enc_list(c.deadline_weeks),
        "workload_level": _enc_int(c.workload_level),
        "attendance_strict": _enc_bool(c.attendance_strict),
    }
    for k in EVAL_KEYS:
        row[f"eval_{k}"] = _enc_int(c.eval.get(k))
    return row


def row_to_course(row: dict[str, str]) -> Course:
    """CSV 한 줄 → Course."""
    g = lambda k: row.get(k) or ""  # noqa: E731
    return Course(
        key=g("key"),
        code=g("code"),
        section=g("section"),
        name=g("name"),
        name_en=g("name_en"),
        credits=_dec_int(g("credits")) or 0,
        hours=_dec_int(g("hours")) or 0,
        professor=g("professor"),
        campus=_dec_int(g("campus")) or 1,
        slots=decode_slots(g("slots"), g("rooms")),
        category=g("category"),
        mode=g("mode"),
        is_online=bool(_dec_bool(g("is_online"))),
        module=_dec_opt_str(g("module")),
        english=bool(_dec_bool(g("english"))),
        note=g("note"),
        restricted_depts=_dec_str_list(g("restricted_depts")),
        major_depts=_dec_str_list(g("major_depts")),
        language=_dec_opt_str(g("language")),
        prerequisite=_dec_opt_str(g("prerequisite")),
        eval={k: _dec_int(g(f"eval_{k}")) for k in EVAL_KEYS},
        eval_source=g("eval_source") or "none",
        self_study=_dec_opt_str(g("self_study")),
        teamwork=_dec_bool(g("teamwork")),
        exam_count=_dec_int(g("exam_count")),
        exam_weeks=_dec_int_list(g("exam_weeks")),
        deadline_weeks=_dec_int_list(g("deadline_weeks")),
        workload_level=_dec_int(g("workload_level")),
        attendance_strict=_dec_bool(g("attendance_strict")),
    )


# ------------------------------------------------------------------ 학기 파일


def courses_path(term: str) -> Path:
    return _data_dir / f"courses_{term}.csv"


def profiles_path(term: str) -> Path:
    return _data_dir / f"profiles_{term}.jsonl"


def meta_path(term: str) -> Path:
    return _data_dir / f"meta_{term}.json"


def read_courses_file(path: str | Path) -> dict[str, Course]:
    """경로를 직접 지정해 courses CSV를 읽는다 (테스트 fixture용)."""
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        out: dict[str, Course] = {}
        for row in reader:
            c = row_to_course(row)
            out[c.key] = c
    return out


def read_courses(term: str) -> dict[str, Course]:
    """data/courses_<학기>.csv → {키: Course}. 없거나 스키마가 다르면 DataNotBuilt."""
    path = courses_path(term)
    if not path.exists():
        raise DataNotBuilt(term=term, path=str(path))
    meta = read_meta(term)
    if meta is not None and meta.get("schema_version") != DEFAULT_CONFIG.schema_version:
        raise DataNotBuilt(
            term=term,
            expected=DEFAULT_CONFIG.schema_version,
            found=meta.get("schema_version"),
        )
    return read_courses_file(path)


def write_courses_file(path: str | Path, courses: list[Course]) -> None:
    """Course 목록을 지정한 경로에 CSV로 쓴다."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(COURSE_COLUMNS), lineterminator="\n")
        w.writeheader()
        for c in sorted(courses, key=lambda x: x.key):
            w.writerow(course_to_row(c))


def write_courses(term: str, courses: list[Course]) -> None:
    """Course 목록 → data/courses_<학기>.csv."""
    write_courses_file(courses_path(term), courses)


def read_profiles(term: str) -> dict[str, dict]:
    """data/profiles_<학기>.jsonl → {키: 프로필}. 파일이 없으면 빈 dict."""
    path = profiles_path(term)
    if not path.exists():
        return {}
    out: dict[str, dict] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            p = json.loads(line)
            out[p["key"]] = p
    return out


def write_profiles(term: str, profiles: list[dict]) -> None:
    """프로필 목록 → data/profiles_<학기>.jsonl."""
    path = profiles_path(term)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for p in sorted(profiles, key=lambda x: x["key"]):
            f.write(json.dumps(p, ensure_ascii=False) + "\n")


def read_meta(term: str) -> dict | None:
    """data/meta_<학기>.json. 없으면 None."""
    path = meta_path(term)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_meta(term: str, meta: dict) -> None:
    path = meta_path(term)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


# ------------------------------------------------------------------ 손으로 만드는 파일


def read_buildings() -> dict[str, dict]:
    """data/buildings.csv → {건물 번호: {name, campus, lat, lon}}."""
    path = _data_dir / "buildings.csv"
    if not path.exists():
        return {}
    out: dict[str, dict] = {}
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            lat = row.get("lat") or ""
            lon = row.get("lon") or ""
            out[row["building"]] = {
                "name": row.get("name", ""),
                "campus": _dec_int(row.get("campus") or "") or 1,
                "lat": float(lat) if lat.strip() else None,
                "lon": float(lon) if lon.strip() else None,
            }
    return out


def read_dept_alias() -> dict[str, str]:
    """data/dept_alias.csv → {별칭: 정식 이름}."""
    path = _data_dir / "dept_alias.csv"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8", newline="") as f:
        return {row["alias"]: row["canonical"] for row in csv.DictReader(f)}


def read_departments(term: str) -> list[dict]:
    """학과 목록 (build 때 meta에 저장한 것)."""
    meta = read_meta(term) or {}
    return list(meta.get("department_list", []))


# ------------------------------------------------------------------ 캐시 (커밋하지 않음)


def raw_dir() -> Path:
    return _data_dir / "raw"


def read_raw(rel: str) -> bytes | None:
    """data/raw/<rel> 원문 캐시를 읽는다. 없으면 None."""
    path = raw_dir() / rel
    return path.read_bytes() if path.exists() else None


def write_raw(rel: str, content: bytes) -> Path:
    """data/raw/<rel>에 원문을 저장한다."""
    path = raw_dir() / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _llm_cache_path(task: str, payload: str) -> Path:
    h = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return raw_dir() / "llm_cache" / task / f"{h}.json"


def read_llm_cache(task: str, payload: str) -> str | None:
    """같은 입력의 LLM 응답 캐시 (개발용)."""
    path = _llm_cache_path(task, payload)
    return path.read_text(encoding="utf-8") if path.exists() else None


def write_llm_cache(task: str, payload: str, response: str) -> None:
    path = _llm_cache_path(task, payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(response, encoding="utf-8")


def read_prompt(task: str) -> str:
    """kkul/prompts/<task>.md 프롬프트를 읽는다."""
    return (Path(__file__).parent / "prompts" / f"{task}.md").read_text(encoding="utf-8")
