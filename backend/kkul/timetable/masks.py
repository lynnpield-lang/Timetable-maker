"""비트마스크 표현 (01 B부 1): 하루를 5분 칸 288개로 나눈다."""

from __future__ import annotations

from kkul.models import DAYS, Slot

CELL = 5
CELLS_PER_DAY = 24 * 60 // CELL
Mask = tuple[int, ...]  # 요일 0–5 마스크
EMPTY: Mask = (0,) * len(DAYS)


def slot_bits(start: int, end: int) -> int:
    """[start, end) 구간의 비트: ⌊s/5⌋ … ⌈e/5⌉−1."""
    lo = start // CELL
    hi = -(-end // CELL)
    if hi <= lo:
        return 0
    return ((1 << (hi - lo)) - 1) << lo


def to_mask(slots) -> Mask:
    """수업 조각 목록 → 요일별 마스크 튜플."""
    m = [0] * len(DAYS)
    for s in slots:
        m[s.day] |= slot_bits(s.start, s.end)
    return tuple(m)


def mask_or(a: Mask, b: Mask) -> Mask:
    return tuple(x | y for x, y in zip(a, b, strict=True))


def overlaps(a: Mask, b: Mask) -> bool:
    """두 마스크가 겹치는지: ∃d B_d(x) ∧ B_d(y) ≠ 0."""
    return any(x & y for x, y in zip(a, b, strict=True))


def slots_overlap(a: Slot, b: Slot) -> bool:
    """구간 정의로 겹침 확인 (검산용)."""
    return a.day == b.day and a.start < b.end and b.start < a.end


def shape_key(mask: Mask) -> str:
    """같은 시간 모양 묶음 키."""
    return "-".join(format(x, "x") for x in mask)
