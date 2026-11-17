import random

import pytest

from kkul.models import EVAL_KEYS
from kkul.timetable.analyzer import (
    FEATURE_COLUMNS,
    MONOTONE_DOWN,
    MONOTONE_UP,
    Analyzer,
    analyze,
    build_table,
    weekly_load,
)
from kkul.timetable.masks import overlaps, slot_bits, to_mask
from tests.conftest import by_key, mk


def f_of(cfg, *cs, buildings=None):
    d = by_key(*cs)
    return analyze(tuple(sorted(d)), d, buildings, cfg)


@pytest.mark.parametrize("gap,expected", [(179, 0), (180, 1)])
def test_super_gap_boundary(cfg, gap, expected):
    a = mk("AAA1000-01", [(0, 540, 600)])
    b = mk("BBB1000-01", [(0, 600 + gap, 700 + gap)])
    f = f_of(cfg, a, b)
    assert f["super_gaps"] == expected
    assert f["gap_minutes"] == gap  # 60분 이상이라 공강 합에 들어감
    assert f["max_gap"] == gap


def test_short_break_is_continuous(cfg):
    a = mk("AAA1000-01", [(0, 630, 705)])
    b = mk("BBB1000-01", [(0, 720, 795)])  # 15분 쉬는 시간
    f = f_of(cfg, a, b)
    assert f["gap_minutes"] == 0
    assert f["longest_block"] == 165
    assert f["super_gaps"] == 0


@pytest.mark.parametrize("start,expected", [(540, 1), (545, 0)])
def test_morning_boundary(cfg, start, expected):
    f = f_of(cfg, mk("AAA1000-01", [(0, start, start + 75)]))
    assert f["morning_days"] == expected


def test_morning_streak_and_free_days(cfg):
    a = mk("AAA1000-01", [(0, 540, 615), (1, 540, 615)])
    b = mk("BBB1000-01", [(3, 540, 615)])
    f = f_of(cfg, a, b)
    assert f["morning_days"] == 3
    assert f["morning_streak"] == 2
    assert f["free_days"] == 2
    assert f["free_day_set"] == "2|4"


@pytest.mark.parametrize("end,expected", [(765, 1), (766, 0)])
def test_lunch_boundary(cfg, end, expected):
    # 점심 창 [690, 810): 수업 720–end 뒤에 남는 시간 810−end (45 / 44분)
    f = f_of(cfg, mk("AAA1000-01", [(0, 720, end)]))
    assert f["lunch_days"] == expected


def test_night_and_stay(cfg):
    a = mk("AAA1000-01", [(1, 600, 675)])
    b = mk("BBB1000-01", [(1, 1080, 1190)])
    f = f_of(cfg, a, b)
    assert f["night_classes"] == 1
    assert f["avg_stay"] == f["max_stay"] == 590


def test_eval_missing_is_not_zero(cfg):
    ev = {k: None for k in EVAL_KEYS}
    with_eval = mk("AAA1000-01", [(0, 600, 675)], eval={**ev, "mid": 40, "final": 40, "attend": 20})
    no_eval = mk("BBB1000-01", [(1, 600, 675)])
    f = f_of(cfg, with_eval, no_eval)
    assert f["exam_ratio"] == 80  # 평가 정보 없는 과목은 0으로 섞이지 않는다
    assert f["eval_coverage"] == 50
    f2 = f_of(cfg, no_eval)
    assert f2["exam_ratio"] is None
    assert f2["eval_coverage"] == 0


def test_weekly_load_same_exam_week(cfg):
    a = mk("AAA1000-01", [(0, 600, 675)], exam_weeks=(8,))
    b = mk("BBB1000-01", [(1, 600, 675)], exam_weeks=(8,), deadline_weeks=(10,))
    load = weekly_load([a, b], cfg)
    assert load[7] == 2 * cfg.exam_weight
    assert load[9] == cfg.deadline_weight
    f = f_of(cfg, a, b)
    assert f["peak_load"] == 4.0
    assert f["crunch_weeks"] == 1
    assert f["peak_load_regular"] == 1.0  # 시험 기간(8주차)을 빼면 10주차 마감만


def test_walk_and_late_risk(cfg, buildings):
    a = mk("AAA1000-01", [(0, 630, 705, "33401")])
    b = mk("BBB1000-01", [(0, 720, 795, "61201")])  # 15분 안에 먼 건물
    f = f_of(cfg, a, b, buildings=buildings)
    assert f["late_risk"] == 1
    assert f["walk_minutes"] > 15
    c = mk("CCC1000-01", [(0, 720, 795, "33402")])  # 같은 건물
    f2 = f_of(cfg, a, c, buildings=buildings)
    assert f2["late_risk"] == 0 and f2["walk_minutes"] == 0
    d = mk("DDD1000-01", [(0, 720, 795, "02101")])  # 좌표 모르는 건물
    assert f_of(cfg, a, d, buildings=buildings)["walk_minutes"] is None


def test_online_excluded_from_time(cfg):
    a = mk("AAA1000-01", [(0, 540, 615)], is_online=True, mode="온라인[사전제작]")
    f = f_of(cfg, a)
    assert f["morning_days"] == 0 and f["free_days"] == 5 and f["credits"] == 3


def test_masks():
    assert slot_bits(0, 5) == 1
    assert slot_bits(5, 12) == 0b110  # ⌊5/5⌋=1 … ⌈12/5⌉−1=2
    a = mk("AAA1000-01", [(0, 600, 675)])
    b = mk("BBB1000-01", [(0, 675, 750)])  # 끝과 시작이 같으면 겹치지 않음
    c = mk("CCC1000-01", [(0, 670, 700)])
    assert not overlaps(to_mask(a.slots), to_mask(b.slots))
    assert overlaps(to_mask(a.slots), to_mask(c.slots))


def test_build_table_columns(cfg, courses, buildings):
    tts = [("BIZ2021-01", "BIZ3001-01"), ("BIZ2006-02", "BIZ2021-01"), ("BIZ2006-03", "BIZ2021-01")]
    df = build_table(tts, courses, buildings, cfg)
    for col in (*FEATURE_COLUMNS, "tt_id", "sections", "shape_key", "group_size"):
        assert col in df.columns
    # BIZ2006-02/03은 시간이 같아 같은 모양
    assert df.loc[1, "shape_key"] == df.loc[2, "shape_key"]
    assert df.loc[1, "group_size"] == 2


def test_monotone_features_never_decrease(cfg, courses, buildings):
    """4.3 표: 무작위 부분 시간표에 분반을 더해도 단조 증가 특징은 줄지 않는다."""
    rng = random.Random(0)
    an = Analyzer(courses, buildings, cfg)
    keys = sorted(courses)
    for _ in range(300):
        rng.shuffle(keys)
        part: list[str] = []
        mask = to_mask(())
        for k in keys:
            m = an.mask(k)
            if any(a & b for a, b in zip(mask, m, strict=True)) or any(
                courses[k].code == courses[p].code for p in part
            ):
                continue
            before = an.analyze(tuple(part), walk=False) if part else None
            part.append(k)
            mask = tuple(a | b for a, b in zip(mask, m, strict=True))
            after = an.analyze(tuple(part), walk=False)
            if before is None:
                continue
            for col in MONOTONE_UP:
                assert after[col] >= before[col], col
            for col in MONOTONE_DOWN:
                assert after[col] <= before[col], col
