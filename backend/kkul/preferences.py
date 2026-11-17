"""자연어 조건 → 필터·정렬 ("금요일 쉬고 팀플은 싫어"). LLM은 해석만, 검증은 코드가."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from kkul import llm
from kkul.timetable.analyzer import FEATURE_LABELS, NUMERIC_FEATURES


class PrefOut(BaseModel):
    filters: dict[str, list[float | None]] = Field(default_factory=dict)
    free_days: list[int] = Field(default_factory=list)
    sort: list[list] = Field(default_factory=list)
    unclear: list[str] = Field(default_factory=list)


def parse_preferences(text: str) -> dict | None:
    """문장을 {filters, free_days, sort, unclear}로. 없는 열·잘못된 값은 버린다. 실패하면 None."""
    columns = {c: FEATURE_LABELS[c] for c in NUMERIC_FEATURES}
    prompt = json.dumps({"text": text, "columns": columns}, ensure_ascii=False)
    out = llm.call_json("preferences_parse", prompt, PrefOut, timeout=10)
    if out is None:
        return None
    unclear = list(out.unclear)
    filters = {}
    for col, rng in out.filters.items():
        if col not in columns or len(rng) != 2:
            unclear.append(col)
            continue
        lo, hi = rng
        if lo is not None and hi is not None and lo > hi:
            unclear.append(col)
            continue
        filters[col] = [lo, hi]
    sort = []
    for item in out.sort:
        if len(item) == 2 and item[0] in columns and item[1] in (1, -1):
            sort.append([item[0], int(item[1])])
    free_days = sorted({d for d in out.free_days if isinstance(d, int) and 0 <= d <= 5})
    return {"filters": filters, "free_days": free_days, "sort": sort, "unclear": unclear}
