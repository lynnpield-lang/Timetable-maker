import pandas as pd
import pytest

from kkul.errors import InvalidFilter
from kkul.models import Filters, GenerateSpec, SortKey, WantedCourse
from kkul.timetable import build_table, generate, query
from kkul.timetable.explorer import (
    apply_filters,
    count_if_relaxed,
    counts_without,
    fold_similar,
    relax_suggestions,
    sort_by_priority,
)


@pytest.fixture
def table(courses, buildings, cfg):
    s = GenerateSpec(
        wanted=tuple(
            WantedCourse(c) for c in ["BIZ2021", "BIZ2006", "BIZ3001", "BIZ2030", "ECO2001"]
        )
        + (WantedCourse("GEDH001", required=False),),
        user_depts=("경영학과",),
    )
    res = generate(courses, s, cfg, buildings)
    return build_table(res.timetables, courses, buildings, cfg, res.major_keys)


def small_df():
    return pd.DataFrame(
        {
            "tt_id": ["c", "a", "b", "d"],
            "sections": [("X",), ("Y",), ("Z",), ("W",)],
            "gap_minutes": [100.0, 95.0, 130.0, 90.0],
            "morning_days": [1, 1, 0, 2],
            "shape_key": ["s1", "s1", "s2", "s3"],
            "free_day_set": ["4", "", "4", "2|4"],
            "eval_coverage": [100.0, 50.0, 100.0, 100.0],
            "exam_ratio": [60.0, None, 40.0, 70.0],
        }
    )


def test_binned_lexicographic_sort():
    df = small_df()
    # 공강 합 30분 구간: 95,100 → 3 / 90 → 3 / 130 → 4. 같은 구간 안에서는 9시 수업 수
    out = sort_by_priority(df, [SortKey("gap_minutes", 1), SortKey("morning_days", 1)])
    assert list(out["tt_id"]) == ["a", "c", "d", "b"]
    assert list(out["rank"]) == [1, 2, 3, 4]
    # 같은 입력이면 같은 순서
    again = sort_by_priority(
        df.sample(frac=1, random_state=1), [SortKey("gap_minutes", 1), SortKey("morning_days", 1)]
    )
    assert list(again["tt_id"]) == list(out["tt_id"])


def test_descending_and_missing_last():
    out = sort_by_priority(small_df(), [SortKey("exam_ratio", -1)])
    assert list(out["tt_id"]) == ["d", "c", "b", "a"]  # 모르는 값(a)은 맨 뒤


def test_filters_and_missing_eval():
    df = small_df()
    assert set(apply_filters(df, Filters({"exam_ratio": (None, 60)}))["tt_id"]) == {"a", "b", "c"}
    strict = Filters({"exam_ratio": (None, 60)}, include_missing_eval=False)
    assert set(apply_filters(df, strict)["tt_id"]) == {"b", "c"}
    assert set(apply_filters(df, Filters(free_days=(2, 4)))["tt_id"]) == {"d"}


def test_fold_keeps_first_in_order():
    out = fold_similar(sort_by_priority(small_df(), [SortKey("morning_days", 1)]))
    assert list(out["tt_id"]) == ["b", "a", "d"]
    assert dict(zip(out["tt_id"], out["group_size"], strict=True)) == {"b": 1, "a": 2, "d": 1}


def test_counts_and_relax():
    df = small_df()
    f = Filters({"morning_days": (None, 0), "gap_minutes": (None, 120)})
    assert apply_filters(df, f).empty
    assert counts_without(df, f) == {"morning_days": 3, "gap_minutes": 1}
    relaxed = count_if_relaxed(df, f)
    assert relaxed["morning_days"] == 2  # 0→1로 올리면 a, c
    sug = relax_suggestions(df, f)
    assert sug[0]["key"] == "morning_days"
    assert "0→1" in sug[0]["text"] and "2개" in sug[0]["text"]


def test_invalid_filter():
    with pytest.raises(InvalidFilter):
        apply_filters(small_df(), Filters({"nope": (0, 1)}))
    with pytest.raises(InvalidFilter):
        apply_filters(small_df(), Filters({"morning_days": (3, 1)}))
    with pytest.raises(InvalidFilter):
        sort_by_priority(small_df(), [SortKey("free_day_set", 1)])


def test_query_on_real_table(table):
    out = query(table, Filters({"morning_days": (None, 1)}), [SortKey("super_gaps", 1)], fold=True)
    assert (out["morning_days"] <= 1).all()
    assert out["shape_key"].is_unique
    assert out["super_gaps"].is_monotonic_increasing
    # 첫 번째는 정렬 조건 기준 파레토 최적 (더 좋은 시간표가 없음)
    best = out.iloc[0]
    assert not (out["super_gaps"] < best["super_gaps"]).any()
