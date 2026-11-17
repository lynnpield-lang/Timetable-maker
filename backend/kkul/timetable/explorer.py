"""필터·정렬·같은 모양 묶기 (01 B부 5–7)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from kkul.config import DEFAULT_BINS
from kkul.errors import InvalidFilter
from kkul.models import DAY_NAMES, Filters, SortKey

# 순환 import를 피하려고 열 정보는 analyzer에서 늦게 가져온다
_NULLABLE = {"walk_minutes", "exam_ratio", "homework_ratio", "attend_ratio", "avg_workload"}


def _feature_info():
    from kkul.timetable.analyzer import FEATURE_LABELS, INT_FEATURES, NUMERIC_FEATURES

    return NUMERIC_FEATURES, FEATURE_LABELS, INT_FEATURES


def validate(filters: Filters, sort: list[SortKey] | None = None) -> None:
    """없는 열 이름·범위 오류를 InvalidFilter로 알린다."""
    numeric, _, _ = _feature_info()
    for col, rng in filters.bounds.items():
        if col not in numeric:
            raise InvalidFilter(f"'{col}'은(는) 필터로 쓸 수 없는 열이에요.", column=col)
        lo, hi = rng
        if lo is not None and hi is not None and lo > hi:
            raise InvalidFilter(f"'{col}' 범위의 최소가 최대보다 커요.", column=col)
    for d in filters.free_days:
        if d not in range(6):
            raise InvalidFilter("요일은 0(월)–5(토)만 쓸 수 있어요.", day=d)
    for k in sort or []:
        if k.column not in numeric:
            raise InvalidFilter(f"'{k.column}'(으)로는 정렬할 수 없어요.", column=k.column)
        if k.direction not in (1, -1):
            raise InvalidFilter("정렬 방향은 1 또는 -1이에요.", column=k.column)


def _is_missing(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def row_passes(f: dict, filters: Filters) -> bool:
    """특징 dict 하나가 필터를 통과하는지. 모르는 값(None)은 범위를 어기지 않은 것으로 본다."""
    for col, (lo, hi) in filters.bounds.items():
        v = f.get(col)
        if _is_missing(v):
            continue
        if lo is not None and v < lo:
            return False
        if hi is not None and v > hi:
            return False
    if filters.free_days:
        free = set(str(f.get("free_day_set") or "").split("|"))
        if any(str(d) not in free for d in filters.free_days):
            return False
    if not filters.include_missing_eval and (f.get("eval_coverage") or 0) < 100:
        return False
    return True


def _mask(df: pd.DataFrame, filters: Filters, skip: str | None = None) -> pd.Series:
    m = pd.Series(True, index=df.index)
    for col, (lo, hi) in filters.bounds.items():
        if col == skip:
            continue
        s = df[col]
        ok = s.isna()
        cond = pd.Series(True, index=df.index)
        if lo is not None:
            cond &= s >= lo
        if hi is not None:
            cond &= s <= hi
        m &= ok | cond
    if filters.free_days and skip != "free_day_set":
        sets = df["free_day_set"].fillna("").astype(str).str.split("|")
        need = {str(d) for d in filters.free_days}
        m &= sets.map(lambda xs: need <= set(xs))
    if not filters.include_missing_eval and skip != "eval_coverage":
        m &= df["eval_coverage"].fillna(0) >= 100
    return m


def apply_filters(df: pd.DataFrame, filters: Filters) -> pd.DataFrame:
    """범위 조건의 교집합 𝒯_filter (01 B부 5)."""
    validate(filters)
    if df.empty:
        return df
    return df[_mask(df, filters)]


def sort_by_priority(
    df: pd.DataFrame, keys: list[SortKey], bins: dict[str, float] | None = None
) -> pd.DataFrame:
    """구간화한 사전식 순서 (01 B부 6). 마지막 키는 tt_id로 순서를 고정한다."""
    validate(Filters(), keys)
    bins = {**DEFAULT_BINS, **(bins or {})}
    if df.empty:
        return df.assign(rank=pd.Series(dtype=int))
    work = df.copy()
    by: list[str] = []
    for i, k in enumerate(keys):
        delta = float(bins.get(k.column, 1) or 1)
        q = np.floor(work[k.column].astype(float) / delta) * k.direction
        # 모르는 값은 맨 뒤로
        work[f"_q{i}"] = q.fillna(np.inf)
        by.append(f"_q{i}")
    by.append("tt_id")
    work = work.sort_values(by=by, kind="stable")
    work = work.drop(columns=[c for c in by if c.startswith("_q")])
    work["rank"] = np.arange(1, len(work) + 1)
    return work.reset_index(drop=True)


def fold_similar(df: pd.DataFrame) -> pd.DataFrame:
    """같은 시간 모양 묶기 (01 B부 7): 정렬 순서에서 묶음마다 첫 시간표만 남긴다."""
    if df.empty:
        return df
    sizes = df.groupby("shape_key")["tt_id"].transform("size")
    out = df.assign(group_size=sizes.astype(int))
    return out.drop_duplicates(subset="shape_key", keep="first").reset_index(drop=True)


def query(
    df: pd.DataFrame,
    filters: Filters,
    sort: list[SortKey],
    bins: dict[str, float] | None = None,
    fold: bool = True,
) -> pd.DataFrame:
    """필터 → 정렬 → (선택) 묶기. 결과에는 rank 열이 붙는다."""
    validate(filters, sort)
    ranked = sort_by_priority(apply_filters(df, filters), sort, bins)
    return fold_similar(ranked) if fold else ranked


def counts_without(df: pd.DataFrame, filters: Filters) -> dict[str, int]:
    """조건 j를 뺀 나머지 조건만 적용했을 때 남는 개수 (필터 옆 숫자)."""
    validate(filters)
    out: dict[str, int] = {}
    if df.empty:
        return {c: 0 for c in filters.bounds}
    for col in filters.bounds:
        out[col] = int(_mask(df, filters, skip=col).sum())
    if filters.free_days:
        out["free_day_set"] = int(_mask(df, filters, skip="free_day_set").sum())
    return out


def _step(col: str) -> float:
    _, _, ints = _feature_info()
    return 1.0 if col in ints else float(DEFAULT_BINS.get(col, 1))


def count_if_relaxed(df: pd.DataFrame, filters: Filters) -> dict[str, int]:
    """조건 j의 범위를 한 칸 넓혔을 때 남는 개수 count_j (결과 0개일 때 완화 제안용)."""
    validate(filters)
    out: dict[str, int] = {}
    if df.empty:
        return {c: 0 for c in filters.bounds}
    for col, (lo, hi) in filters.bounds.items():
        st = _step(col)
        wider = dict(filters.bounds)
        wider[col] = (None if lo is None else lo - st, None if hi is None else hi + st)
        f2 = Filters(wider, filters.free_days, filters.include_missing_eval)
        out[col] = int(_mask(df, f2).sum())
    for d in filters.free_days:
        f2 = Filters(
            filters.bounds,
            tuple(x for x in filters.free_days if x != d),
            filters.include_missing_eval,
        )
        out[f"free_day:{d}"] = int(_mask(df, f2).sum())
    if not filters.include_missing_eval:
        f2 = Filters(filters.bounds, filters.free_days, True)
        out["include_missing_eval"] = int(_mask(df, f2).sum())
    return out


def _fmt(v: float | None) -> str:
    if v is None:
        return "-"
    return str(int(v)) if float(v).is_integer() else f"{v:g}"


def relax_suggestions(df: pd.DataFrame, filters: Filters, top: int = 3) -> list[dict]:
    """가장 많이 늘어나는 완화 제안. 예: "9시 수업 요일 수 최대를 1→2로 올리면 12개가 생겨요"."""
    _, labels, _ = _feature_info()
    current = int(_mask(df, filters).sum()) if not df.empty else 0
    out = []
    for name, cnt in count_if_relaxed(df, filters).items():
        gain = cnt - current
        if gain <= 0:
            continue
        if name.startswith("free_day:"):
            d = int(name.split(":")[1])
            text = f"{DAY_NAMES[d]}요일 비우기를 끄면 {gain}개가 더 생겨요"
            change = {"free_days_remove": d}
        elif name == "include_missing_eval":
            text = f"평가 정보 없는 과목 포함 시간표도 보면 {gain}개가 더 생겨요"
            change = {"include_missing_eval": True}
        else:
            lo, hi = filters.bounds[name]
            st = _step(name)
            label = labels.get(name, name)
            parts = []
            if hi is not None:
                parts.append(f"최대를 {_fmt(hi)}→{_fmt(hi + st)}로 올리면")
            if lo is not None:
                parts.append(f"최소를 {_fmt(lo)}→{_fmt(lo - st)}로 내리면")
            text = f"{label} {' / '.join(parts)} {gain}개가 더 생겨요"
            change = {
                "column": name,
                "range": [None if lo is None else lo - st, None if hi is None else hi + st],
            }
        out.append({"key": name, "gain": gain, "count": cnt, "text": text, "change": change})
    out.sort(key=lambda x: (-x["gain"], x["key"]))
    return out[:top]
