import itertools

from kkul.models import Filters, GenerateSpec, WantedCourse
from kkul.timetable import build_table
from kkul.timetable.eligibility import is_eligible, is_major, normalize_dept
from kkul.timetable.explorer import apply_filters
from kkul.timetable.masks import slots_overlap
from kkul.timetable.scheduler import generate
from tests.conftest import mk

CODES = ["BIZ2021", "BIZ2006", "BIZ3001", "BIZ2030", "ECO2001"]


def spec(**kw):
    kw.setdefault("wanted", tuple(WantedCourse(c) for c in CODES))
    kw.setdefault("user_depts", ("경영학과",))
    return GenerateSpec(**kw)


def test_dept_normalization():
    assert normalize_dept("경영학과") == normalize_dept("경영학") == normalize_dept(" 경영 학부")
    alias = {"경영": "경영학과"}
    assert normalize_dept("경영", alias) == normalize_dept("경영학과")


def test_eligibility():
    free = mk("A-01", [])
    only_eco = mk("B-01", [], restricted_depts=("경제학과",), major_depts=("경제학과",))
    assert is_eligible(free, ["경영학과"])
    assert not is_eligible(only_eco, ["경영학과"])
    assert is_eligible(only_eco, ["경영학과", "경제학"])  # 복수전공으로 통과
    assert is_major(only_eco, ["경제학"])
    assert not is_major(free, ["경영학과"])


def test_no_overlap_anywhere(courses, cfg):
    res = generate(courses, spec(), cfg)
    assert res.timetables
    for tt in res.timetables:
        slots = [s for k in tt for s in courses[k].slots]
        for a, b in itertools.combinations(slots, 2):
            assert not slots_overlap(a, b)
        assert len({courses[k].code for k in tt}) == len(tt)


def test_ineligible_excluded_and_reported(courses, cfg):
    res = generate(courses, spec(), cfg)
    assert res.excluded == {"BIZ3001": ["BIZ3001-02"]}
    assert all("BIZ3001-02" not in tt for tt in res.timetables)
    res2 = generate(courses, spec(include_ineligible=True), cfg)
    assert "BIZ3001-02" in res2.ineligible_keys
    assert any("BIZ3001-02" in tt for tt in res2.timetables)


def test_all_sections_restricted_warning(cfg):
    a = mk("FIN3000-01", [(0, 600, 675)], name="재무특강", restricted_depts=("경제학과",))
    b = mk("FIN3000-02", [(1, 600, 675)], name="재무특강", restricted_depts=("경제학과",))
    res = generate({a.key: a, b.key: b}, spec(wanted=(WantedCourse("FIN3000"),)), cfg)
    assert not res.timetables
    assert any("모두 수강 대상이" in w for w in res.warnings)


def test_optional_course_can_be_skipped(courses, cfg):
    s = spec(wanted=(WantedCourse("BIZ2021"), WantedCourse("GEDH001", required=False)))
    res = generate(courses, s, cfg)
    sizes = {len(tt) for tt in res.timetables}
    assert sizes == {1, 2}


def test_pruning_equals_filter_after(courses, buildings, cfg):
    """가지치기 켜고 생성 == 끄고 생성한 뒤 필터 (01 B부 4.3)."""
    hard = Filters(
        bounds={"morning_days": (None, 1), "teamwork_courses": (None, 1), "free_days": (1, None)}
    )
    s = spec(hard=hard)
    pruned = generate(courses, s, cfg, buildings)
    full = generate(courses, spec(), cfg, buildings, prune=False)
    df = build_table(full.timetables, courses, buildings, cfg, full.major_keys)
    expected = sorted(tuple(t) for t in apply_filters(df, hard)["sections"])
    assert sorted(pruned.timetables) == expected


def test_credit_range_and_free_day(courses, cfg):
    s = spec(
        wanted=(*[WantedCourse(c) for c in CODES], WantedCourse("GEDH001", required=False)),
        credit_range=(17, 17),
        hard=Filters(free_days=(4,)),
    )
    res = generate(courses, s, cfg)
    for tt in res.timetables:
        assert sum(courses[k].credits for k in tt) == 17
        assert all(s.day != 4 for k in tt for s in courses[k].slots)


def test_limit_truncates(courses, cfg):
    from dataclasses import replace

    res = generate(courses, spec(), replace(cfg, gen_limit=5))
    assert res.truncated and len(res.timetables) == 5
