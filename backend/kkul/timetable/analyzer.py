"""시간표 특징 계산과 특징표 (01 B부 3장, 03 4장)."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

import pandas as pd

from kkul.config import Config
from kkul.models import DAYS, WEEKDAYS, Course, Timetable, tt_id
from kkul.timetable.masks import EMPTY, mask_or, shape_key, to_mask

# (열 이름, 형, 좋은 방향(+1 낮을수록 / −1 높을수록 / 0 없음), 화면 이름)
FEATURES: tuple[tuple[str, str, int, str], ...] = (
    ("morning_days", "int", 1, "9시 수업 요일 수"),
    ("early_days", "int", 1, "10시 반 이전 수업 요일 수"),
    ("morning_streak", "int", 1, "9시 수업 연속 일수"),
    ("super_gaps", "int", 1, "슈퍼공강 횟수"),
    ("gap_minutes", "int", 1, "공강 합 (분)"),
    ("max_gap", "int", 1, "가장 긴 공강 (분)"),
    ("longest_block", "int", 1, "최장 연강 (분)"),
    ("free_days", "int", -1, "우주공강 일수"),
    ("free_day_set", "str", 0, "우주공강 요일"),
    ("avg_stay", "int", 1, "평균 체류시간 (분)"),
    ("max_stay", "int", 1, "최대 체류시간 (분)"),
    ("lunch_days", "int", -1, "점심시간 있는 날"),
    ("night_classes", "int", 1, "야간 수업 수"),
    ("late_risk", "int", 1, "지각 위험 이동"),
    ("walk_minutes", "int?", 1, "이동 시간 합 (분)"),
    ("credits", "int", 0, "총 학점"),
    ("major_credits", "int", -1, "전공 인정 학점"),
    ("exam_ratio", "float?", 1, "시험 비중 (%)"),
    ("homework_ratio", "float?", 1, "과제 비중 (%)"),
    ("attend_ratio", "float?", 0, "출석 비중 (%)"),
    ("eval_coverage", "float", -1, "평가 정보가 있는 학점 비율 (%)"),
    ("teamwork_courses", "int", 1, "팀플 과목 수"),
    ("strict_attendance", "int", 1, "출석 엄격 과목 수"),
    ("avg_workload", "float?", 1, "평균 과제 부담 (1–5)"),
    ("peak_load", "float", 1, "가장 바쁜 주 부담"),
    ("peak_load_regular", "float", 1, "시험 기간 뺀 가장 바쁜 주 부담"),
    ("crunch_weeks", "int", 1, "몰리는 주 수"),
)
FEATURE_COLUMNS: tuple[str, ...] = tuple(f[0] for f in FEATURES)
NUMERIC_FEATURES: tuple[str, ...] = tuple(f[0] for f in FEATURES if f[1] != "str")
FEATURE_LABELS: dict[str, str] = {f[0]: f[3] for f in FEATURES}
FEATURE_BETTER: dict[str, int] = {f[0]: f[2] for f in FEATURES}
INT_FEATURES: frozenset[str] = frozenset(f[0] for f in FEATURES if f[1].startswith("int"))
EXTRA_COLUMNS: tuple[str, ...] = ("tt_id", "sections", "shape_key", "group_size")

# 01 B부 4.3: 수업을 더하면 늘거나 같은 특징 (상한 가지치기) / 줄거나 같은 특징 (하한 가지치기)
MONOTONE_UP: frozenset[str] = frozenset(
    {
        "morning_days",
        "early_days",
        "morning_streak",
        "night_classes",
        "credits",
        "major_credits",
        "teamwork_courses",
        "strict_attendance",
        "peak_load",
        "peak_load_regular",
        "crunch_weeks",
        "max_stay",
        "longest_block",
    }
)
MONOTONE_DOWN: frozenset[str] = frozenset({"free_days"})


def effective_slots(course: Course, cfg: Config):
    """시간 계산에 쓰는 조각. 온라인 사전제작 강의는 설정에 따라 뺀다."""
    if course.is_online and not cfg.include_online:
        return ()
    return course.slots


def course_mask(course: Course, cfg: Config):
    return to_mask(effective_slots(course, cfg))


# ------------------------------------------------------------------ 하루 단위 계산


@dataclass(frozen=True)
class DayStats:
    first: int
    last: int
    gaps: tuple[int, ...]
    longest_block: int
    lunch_ok: bool
    night: int
    walk: float | None  # 짧은 간격 이동 시간 합. 모르는 건물이 끼면 None
    late: int


def move_minutes(b1: str | None, b2: str | None, buildings: dict, cfg: Config) -> float | None:
    """연이은 두 수업 사이 이동 시간 t (01 B부 3.8). 모르면 None."""
    if b1 is not None and b1 == b2:
        return 0.0
    if b1 is None or b2 is None:
        return None
    p1, p2 = buildings.get(b1), buildings.get(b2)
    if not p1 or not p2:
        return None
    if p1.get("campus") != p2.get("campus"):
        return cfg.shuttle_min
    if None in (p1.get("lat"), p1.get("lon"), p2.get("lat"), p2.get("lon")):
        return None
    lat_mid = math.radians((p1["lat"] + p2["lat"]) / 2)
    dx = (p1["lon"] - p2["lon"]) * math.cos(lat_mid) * 111_320
    dy = (p1["lat"] - p2["lat"]) * 110_540
    return cfg.hill_factor * math.hypot(dx, dy) / cfg.walk_speed


def _lunch_free(seq, cfg: Config) -> int:
    """점심 창 안에서 수업이 없는 가장 긴 연속 구간 (분)."""
    lo, hi = cfg.lunch_window
    cur = lo
    best = 0
    for s, e, _ in seq:
        if e <= lo or s >= hi:
            continue
        best = max(best, min(s, hi) - cur)
        cur = max(cur, min(e, hi))
    return max(best, hi - cur)


def day_stats(
    seq: tuple[tuple[int, int, str | None], ...], buildings: dict, cfg: Config
) -> DayStats:
    """시작 시각순 수업 조각 (s, e, 건물) → 하루 통계."""
    gaps = tuple(seq[i + 1][0] - seq[i][1] for i in range(len(seq) - 1))
    # 연강 덩어리
    longest = 0
    blk_start = seq[0][0]
    blk_end = seq[0][1]
    for i, g in enumerate(gaps):
        nxt = seq[i + 1]
        if g >= cfg.gap_min:
            longest = max(longest, blk_end - blk_start)
            blk_start = nxt[0]
        blk_end = max(blk_end, nxt[1])
    longest = max(longest, blk_end - blk_start)
    walk: float | None = 0.0
    late = 0
    for i, g in enumerate(gaps):
        t = move_minutes(seq[i][2], seq[i + 1][2], buildings, cfg)
        if t is not None and t > g:
            late += 1
        if g < cfg.gap_min:
            if t is None:
                walk = None
            elif walk is not None:
                walk += t
    return DayStats(
        first=seq[0][0],
        last=max(e for _, e, _ in seq),
        gaps=gaps,
        longest_block=longest,
        lunch_ok=_lunch_free(seq, cfg) >= cfg.lunch_need,
        night=sum(1 for s, _, _ in seq if s >= cfg.night_cutoff),
        walk=walk,
        late=late,
    )


class Analyzer:
    """특징 계산기. 하루 단위 결과를 캐시해 수만 개 시간표도 빠르게 계산한다."""

    def __init__(
        self,
        courses: dict[str, Course],
        buildings: dict | None,
        cfg: Config,
        major_keys: Iterable[str] = (),
    ) -> None:
        self.courses = courses
        self.buildings = buildings or {}
        self.cfg = cfg
        self.major_keys = frozenset(major_keys)
        self._day_cache: dict[tuple, DayStats] = {}
        self._mask_cache: dict[str, tuple[int, ...]] = {}

    def mask(self, key: str):
        m = self._mask_cache.get(key)
        if m is None:
            m = course_mask(self.courses[key], self.cfg)
            self._mask_cache[key] = m
        return m

    def tt_mask(self, tt: Iterable[str]):
        m = EMPTY
        for k in tt:
            m = mask_or(m, self.mask(k))
        return m

    def _day_seqs(self, cs: list[Course]) -> dict[int, tuple]:
        by_day: dict[int, list] = {}
        for c in cs:
            for s in effective_slots(c, self.cfg):
                by_day.setdefault(s.day, []).append((s.start, s.end, s.building))
        return {d: tuple(sorted(v, key=lambda x: (x[0], x[1]))) for d, v in by_day.items()}

    def _day(self, seq) -> DayStats:
        st = self._day_cache.get(seq)
        if st is None:
            st = day_stats(seq, self.buildings, self.cfg)
            self._day_cache[seq] = st
        return st

    def analyze(self, tt: Iterable[str], walk: bool = True) -> dict:
        """시간표 하나의 특징 벡터 f(T) (01 B부 3장)."""
        cfg = self.cfg
        cs = [self.courses[k] for k in tt]
        seqs = self._day_seqs(cs)
        days = {d: self._day(seq) for d, seq in seqs.items()}
        on_days = sorted(days)

        morning_set = {d for d in on_days if days[d].first <= cfg.morning_cutoff}
        streak = best = 0
        for d in DAYS:
            streak = streak + 1 if d in morning_set else 0
            best = max(best, streak)
        all_gaps = [g for d in on_days for g in days[d].gaps]
        free = [d for d in WEEKDAYS if d not in days]
        stays = [days[d].last - days[d].first for d in on_days]

        f: dict = {
            "morning_days": len(morning_set),
            "early_days": sum(1 for d in on_days if days[d].first <= cfg.early_cutoff),
            "morning_streak": best,
            "super_gaps": sum(1 for g in all_gaps if g >= cfg.super_gap),
            "gap_minutes": sum(g for g in all_gaps if g >= cfg.gap_min),
            "max_gap": max(all_gaps, default=0),
            "longest_block": max((days[d].longest_block for d in on_days), default=0),
            "free_days": len(free),
            "free_day_set": "|".join(str(d) for d in free),
            "avg_stay": round(sum(stays) / len(stays)) if stays else 0,
            "max_stay": max(stays, default=0),
            "lunch_days": sum(1 for d in on_days if days[d].lunch_ok),
            "night_classes": sum(days[d].night for d in on_days),
        }
        if walk:
            f["late_risk"] = sum(days[d].late for d in on_days)
            walks = [days[d].walk for d in on_days]
            f["walk_minutes"] = None if any(w is None for w in walks) else round(sum(walks))
        else:
            f["late_risk"] = 0
            f["walk_minutes"] = None
        f.update(self._plan_features(cs))
        return f

    def _plan_features(self, cs: list[Course]) -> dict:
        """학점·평가 비율·계획서 특징 (01 B부 3.9, 3.11)."""
        cfg = self.cfg
        total = sum(c.credits for c in cs)
        evald = [c for c in cs if c.has_eval]
        ec = sum(c.credits for c in evald)

        def wavg(fn) -> float | None:
            if ec == 0:
                return None
            return round(sum(c.credits * fn(c) for c in evald) / ec, 1)

        ev = lambda c, k: c.eval.get(k) or 0  # noqa: E731  (평가 정보가 있는 과목 안의 빈 칸 = 0)
        wl = [c for c in cs if c.workload_level is not None]
        wlc = sum(c.credits for c in wl)
        load = weekly_load(cs, cfg)
        regular = [v for w, v in enumerate(load, start=1) if w not in cfg.exam_period_weeks]
        return {
            "credits": total,
            "major_credits": sum(c.credits for c in cs if c.key in self.major_keys),
            "exam_ratio": wavg(lambda c: ev(c, "mid") + ev(c, "final")),
            "homework_ratio": wavg(lambda c: ev(c, "homework")),
            "attend_ratio": wavg(lambda c: ev(c, "attend")),
            "eval_coverage": round(100 * ec / total, 1) if total else 0.0,
            "teamwork_courses": sum(1 for c in cs if c.teamwork is True),
            "strict_attendance": sum(1 for c in cs if c.attendance_strict is True),
            "avg_workload": (
                round(sum(c.credits * c.workload_level for c in wl) / wlc, 2) if wlc else None
            ),
            "peak_load": max(load, default=0.0),
            "peak_load_regular": max(regular, default=0.0),
            "crunch_weeks": sum(1 for v in load if v >= cfg.crunch_threshold),
        }

    def row(self, tt: Timetable) -> dict:
        f = self.analyze(tt)
        f["tt_id"] = tt_id(tt)
        f["sections"] = tt
        f["shape_key"] = shape_key(self.tt_mask(tt))
        return f


def weekly_load(courses: Iterable[Course], cfg: Config) -> list[float]:
    """주차별 부담 load_w (w = 1…16): 시험 α, 과제·발표 마감 β (01 B부 3.11)."""
    load = [0.0] * cfg.semester_weeks
    for c in courses:
        for w in c.exam_weeks or ():
            if 1 <= w <= cfg.semester_weeks:
                load[w - 1] += cfg.exam_weight
        for w in c.deadline_weeks or ():
            if 1 <= w <= cfg.semester_weeks:
                load[w - 1] += cfg.deadline_weight
    return load


def analyze(
    timetable: Timetable,
    courses: dict[str, Course],
    buildings: dict | None,
    cfg: Config,
    major_keys: Iterable[str] = (),
) -> dict:
    """시간표 하나의 특징 벡터 (편의 함수)."""
    return Analyzer(courses, buildings, cfg, major_keys).analyze(timetable)


def build_table(
    timetables: list[Timetable],
    courses: dict[str, Course],
    buildings: dict | None,
    cfg: Config,
    major_keys: Iterable[str] = (),
) -> pd.DataFrame:
    """특징표: 한 줄 = 시간표 하나 (03 4장 열 + tt_id, sections, shape_key, group_size)."""
    an = Analyzer(courses, buildings, cfg, major_keys)
    rows = [an.row(tt) for tt in timetables]
    cols = ["tt_id", "sections", *FEATURE_COLUMNS, "shape_key"]
    df = pd.DataFrame(rows, columns=cols)
    if df.empty:
        df["group_size"] = pd.Series(dtype=int)
        return df
    df["group_size"] = df.groupby("shape_key")["tt_id"].transform("size").astype(int)
    for col in FEATURE_COLUMNS:
        if col in INT_FEATURES and df[col].notna().all():
            df[col] = df[col].astype(int)
        elif col != "free_day_set":
            df[col] = df[col].astype(float)
    return df.reset_index(drop=True)
