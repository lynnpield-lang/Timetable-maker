"""테스트·목업용 작은 데이터 만들기: uv run python tests/fixtures/make_fixtures.py

경계값을 일부러 넣었다: 9:00 시작, 15분 쉬는 시간, 다른 건물 연강(먼 건물 61), 온라인 과목,
평가 비율 없음, 수강 대상 제한(BIZ3001-02), 같은 시간 다른 교수(BIZ2006-02/03), 야간 수업.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from kkul import io  # noqa: E402
from kkul.models import EVAL_KEYS, Course, Slot  # noqa: E402

HERE = Path(__file__).resolve().parent


def ev(**kw):
    return {k: kw.get(k) for k in EVAL_KEYS}


def C(key, name, prof, slots, credits=3, category="전공핵심", mode="오프라인", online=False,
      restricted=(), major=("경영학과",), eval_=None, src=None, teamwork=None, exam_weeks=None,
      deadline=None, workload=None, strict=None):  # fmt: skip
    code, sec = key.split("-")
    e = eval_ or ev()
    has = any(v is not None for v in e.values())
    return Course(
        key, code, sec, name, "", credits, credits, prof, 1, tuple(Slot(*s) for s in slots),
        category, mode, online, None, False, "", tuple(restricted), tuple(major), "한국어", None,
        e, src or ("web" if has else "none"), None, teamwork,
        len(exam_weeks) if exam_weeks else None,
        tuple(exam_weeks) if exam_weeks else None, tuple(deadline) if deadline else None,
        workload, strict,
    )  # fmt: skip


W = ev(attend=10, homework=20, mid=30, final=40)
P = ev(attend=10, homework=10, mid=30, final=30, project=20)
S = ev(homework=30, mid=30, final=40)
COURSES = [
    C("BIZ2021-01", "관리회계", "조현권", [(1, 720, 795, "33303"), (3, 810, 885, "33303")], eval_=W, exam_weeks=[8, 15], workload=3),
    C("BIZ2021-02", "관리회계", "김회계", [(0, 540, 615, "33101"), (2, 540, 615, "33101")], eval_=W, exam_weeks=[8, 15], workload=3),
    C("BIZ2006-01", "재무관리", "이재무", [(1, 540, 615, "33201"), (3, 540, 615, "33201")], eval_=P, src="pdf_llm", teamwork=True, exam_weeks=[8, 15], deadline=[10, 14], workload=4, strict=True),
    C("BIZ2006-02", "재무관리", "박재무", [(0, 900, 975, "32101"), (2, 900, 975, "32101")], eval_=P, src="pdf_llm", teamwork=True, exam_weeks=[8, 15], deadline=[10, 14], workload=4, strict=True),
    C("BIZ2006-03", "재무관리", "최재무", [(0, 900, 975, "32101"), (2, 900, 975, "32101")], eval_=P, src="pdf_llm", teamwork=True, exam_weeks=[8, 15], deadline=[10, 14], workload=4, strict=True),
    C("BIZ3001-01", "마케팅전략", "정마케", [(0, 630, 705, "33401"), (2, 630, 705, "33401")], teamwork=False, deadline=[10], workload=2),
    C("BIZ3001-02", "마케팅전략", "한마케", [(1, 900, 975, "33402"), (3, 900, 975, "33402")], restricted=("경제학과",), teamwork=False, deadline=[10], workload=2),
    C("BIZ2030-01", "경영통계", "오통계", [(1, 630, 705, "33501"), (3, 630, 705, "33501")], eval_=S, exam_weeks=[8, 15]),
    C("BIZ2030-02", "경영통계", "유통계", [(0, 720, 795, "61201"), (2, 720, 795, "61201")], eval_=S, exam_weeks=[8, 15]),
    C("ECO2001-01", "미시경제학", "강경제", [(0, 780, 855, "32201"), (2, 780, 855, "32201")], category="전공기초", major=("경제학과", "경영학과"), exam_weeks=[8, 14]),
    C("ECO2001-02", "미시경제학", "윤경제", [(4, 630, 795, "32202")], category="전공기초", major=("경제학과",)),
    C("GEDH001-01", "글쓰기", "서교양", [(4, 540, 650, "02101")], credits=2, category="교양", major=()),
    C("GEDH001-02", "글쓰기", "문교양", [(1, 1080, 1190, "02102")], credits=2, category="교양", major=()),
    C("GEDH001-03", "글쓰기", "노교양", [], credits=2, category="교양", mode="온라인[사전제작]", online=True, major=()),
]  # fmt: skip

PROFILES = [
    {
        "key": "BIZ2006-01", "source": "pdf", "extracted_at": "2026-11-14T00:00:00+09:00",
        "lecture_style": ["강의", "사례 토론"],
        "exams": {"count": 2, "types": ["서술형"], "open_book": False, "weeks": [8, 15]},
        "assignments": [{"name": "팀 프로젝트", "team": True, "count": 1, "weeks": [10, 14]}],
        "attendance": {"strict": True, "rule": "결석 4회 이상 F"},
        "materials": ["Corporate Finance"], "prerequisite": "회계원리", "notes": None,
        "evidence": {"teamwork": "team project", "attendance": "4 absences result in F"},
    },
    {
        "key": "BIZ2021-01", "source": "web", "extracted_at": "2026-11-14T00:00:00+09:00",
        "lecture_style": ["강의"],
        "exams": {"count": 2, "types": ["서술형"], "open_book": False, "weeks": [8, 15]},
        "assignments": None, "attendance": {"strict": False, "rule": None},
        "materials": None, "prerequisite": None, "notes": None, "evidence": {},
    },
]  # fmt: skip

META = {
    "schema_version": 1, "term": "test", "built_at": "2026-11-14T00:00:00+09:00",
    "departments": ["316901"],
    "department_list": [
        {"campus": 1, "code": "316901", "name": "경영학과", "college": "경영대학"},
        {"campus": 1, "code": "316902", "name": "경제학과", "college": "경제대학"},
    ],
    "counts": {"sections": 14, "parse_failed": 0, "eval_web": 4, "eval_pdf": 3, "eval_none": 7},
}  # fmt: skip

BUILDINGS = """building,name,campus,lat,lon
33,경영관,1,37.5880,126.9930
32,다산경제관,1,37.5876,126.9927
61,먼건물,1,37.5945,126.9995
02,호암관,1,,
"""


def main() -> None:
    io.set_data_dir(HERE)
    io.write_courses("test", COURSES)
    io.write_meta("test", META)
    io.write_profiles("test", PROFILES)
    (HERE / "buildings.csv").write_text(BUILDINGS, encoding="utf-8")
    (HERE / "dept_alias.csv").write_text(
        "alias,canonical\n경영,경영학과\n경제,경제학과\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
