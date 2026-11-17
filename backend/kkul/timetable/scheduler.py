"""후보 거르기·같은 시간 묶기·조합 생성·가지치기 (01 B부 1.5, 4장)."""

from __future__ import annotations

import itertools
import logging
import time
from collections import defaultdict
from dataclasses import dataclass

from kkul.config import DEFAULT_CONFIG, Config
from kkul.models import EVAL_KEYS, Course, Filters, GenerateResult, GenerateSpec, Timetable
from kkul.timetable.analyzer import (
    MONOTONE_DOWN,
    MONOTONE_UP,
    Analyzer,
    course_mask,
    effective_slots,
)
from kkul.timetable.eligibility import is_eligible, is_major
from kkul.timetable.explorer import row_passes
from kkul.timetable.masks import EMPTY, mask_or, overlaps

log = logging.getLogger(__name__)


@dataclass
class _Group:
    """특징 벡터가 같은 분반 묶음 (같은 시간·건물·계획서 값)."""

    mask: tuple[int, ...]
    keys: list[str]
    credits: int

    @property
    def rep(self) -> str:
        return self.keys[0]


def _group_key(c: Course, cfg: Config, major: bool) -> tuple:
    slots = tuple(sorted((s.day, s.start, s.end, s.building) for s in effective_slots(c, cfg)))
    return (
        slots,
        c.credits,
        tuple(c.eval.get(k) for k in EVAL_KEYS),
        c.teamwork,
        c.attendance_strict,
        c.workload_level,
        c.exam_weeks,
        c.deadline_weeks,
        major,
    )


def filter_sections(
    courses: dict[str, Course], spec: GenerateSpec, cfg: Config, analyzer: Analyzer
) -> tuple[dict[str, list[Course]], GenerateResult]:
    """과목별 후보 분반: 허용 분반 · 수강 자격 · 전공 인정 · 꼭 지킬 조건 (분반 하나만으로)."""
    by_code: dict[str, list[Course]] = defaultdict(list)
    for c in courses.values():
        by_code[c.code].append(c)
    res = GenerateResult(timetables=[])
    out: dict[str, list[Course]] = {}
    for w in spec.wanted:
        secs = sorted(by_code.get(w.code, []), key=lambda c: c.key)
        if w.sections is not None:
            allowed = set(w.sections)
            secs = [c for c in secs if c.key in allowed]
        if not secs:
            res.warnings.append(f"{w.code}: 개설된 분반을 찾지 못했어요.")
            out[w.code] = []
            continue
        name = secs[0].name
        if spec.user_depts or any(c.restricted_depts for c in secs):
            elig = [c for c in secs if is_eligible(c, spec.user_depts, spec.dept_alias)]
            bad = [c for c in secs if c not in elig]
            if bad:
                if spec.include_ineligible:
                    res.ineligible_keys |= {c.key for c in bad}
                else:
                    res.excluded[w.code] = [c.key for c in bad]
                    if not elig:
                        depts = sorted({d for c in bad for d in c.restricted_depts})
                        res.warnings.append(
                            f"{name} {len(bad)}개 분반 모두 수강 대상이 "
                            f"{', '.join(depts)}(으)로 제한돼 있어요."
                        )
                    secs = elig
        majors = {c.key for c in secs if is_major(c, spec.user_depts, spec.dept_alias)}
        res.major_keys |= majors
        if spec.major_only:
            secs = [c for c in secs if c.key in majors]
            if not secs:
                res.warnings.append(f"{name}: 내 전공으로 인정되는 분반이 없어요.")
        before = len(secs)
        secs = [c for c in secs if not _violates_monotone(analyzer, (c.key,), spec, cfg)]
        if before and not secs:
            res.warnings.append(f"{name}: 꼭 지킬 조건을 만족하는 분반이 없어요.")
        out[w.code] = secs
    return out, res


def group_same_time(
    sections: dict[str, list[Course]], cfg: Config, major_keys: set[str]
) -> dict[str, list[_Group]]:
    """같은 시간·건물·계획서 값의 분반을 묶는다 (01 B부 4.2). 묶음 안 분반은 f가 같다."""
    out: dict[str, list[_Group]] = {}
    for code, secs in sections.items():
        groups: dict[tuple, _Group] = {}
        for c in secs:
            gk = _group_key(c, cfg, c.key in major_keys)
            g = groups.get(gk)
            if g is None:
                groups[gk] = _Group(course_mask(c, cfg), [c.key], c.credits)
            else:
                g.keys.append(c.key)
        out[code] = list(groups.values())
    return out


def _monotone_bounds(hard: Filters) -> list[tuple[str, float | None, float | None]]:
    return [
        (col, lo, hi)
        for col, (lo, hi) in hard.bounds.items()
        if (col in MONOTONE_UP and hi is not None) or (col in MONOTONE_DOWN and lo is not None)
    ]


def _violates_monotone(analyzer: Analyzer, keys, spec: GenerateSpec, cfg: Config) -> bool:
    """부분 시간표가 이미 단조 조건을 어겼는지 (어기면 가지를 버려도 결과가 같다)."""
    hard = spec.hard
    hi_c = spec.credit_range[1]
    mb = _monotone_bounds(hard)
    if hard.free_days:
        m = analyzer.tt_mask(keys)
        if any(m[d] for d in hard.free_days):
            return True
    if hi_c is not None and sum(analyzer.courses[k].credits for k in keys) > hi_c:
        return True
    if not mb:
        return False
    f = analyzer.analyze(keys, walk=False)
    for col, lo, hi in mb:
        v = f.get(col)
        if v is None:
            continue
        if col in MONOTONE_UP and hi is not None and v > hi:
            return True
        if col in MONOTONE_DOWN and lo is not None and v < lo:
            return True
    return False


def generate(
    courses: dict[str, Course],
    req: GenerateSpec,
    cfg: Config = DEFAULT_CONFIG,
    buildings: dict | None = None,
    prune: bool = True,
) -> GenerateResult:
    """겹치지 않는 시간표를 모두 만든다 (01 B부 1.5–4). 꼭 지킬 조건은 결과에도 적용된다."""
    t0 = time.perf_counter()
    analyzer = Analyzer(courses, buildings, cfg)
    sections, res = filter_sections(courses, req, cfg, analyzer)
    analyzer.major_keys = frozenset(res.major_keys)
    required = {w.code for w in req.wanted if w.required}
    groups = group_same_time(sections, cfg, res.major_keys)

    missing_req = [c for c in required if not groups.get(c)]
    if missing_req:
        res.warnings.append(
            "꼭 들을 과목 중 넣을 수 있는 분반이 없는 과목이 있어 시간표를 만들 수 없어요."
        )
        res.elapsed_s = time.perf_counter() - t0
        return res

    order = sorted(
        (c for c in groups if groups[c]),
        key=lambda c: (c not in required, len(groups[c]), c),
    )
    max_credit_after = [0] * (len(order) + 1)
    for i in range(len(order) - 1, -1, -1):
        max_credit_after[i] = max_credit_after[i + 1] + max(g.credits for g in groups[order[i]])
    lo_c, hi_c = req.credit_range
    limit = cfg.gen_limit
    out: list[Timetable] = []
    state = {"nodes": 0, "stop": False}

    def emit(chosen: list[_Group]) -> None:
        rep_keys = tuple(g.rep for g in chosen)
        credits = sum(g.credits for g in chosen)
        if lo_c is not None and credits < lo_c:
            return
        if hi_c is not None and credits > hi_c:
            return
        f = analyzer.analyze(rep_keys)
        if not row_passes(f, req.hard):
            return
        for combo in itertools.product(*(g.keys for g in chosen)):
            out.append(tuple(sorted(combo)))
            if len(out) >= limit:
                state["stop"] = True
                return

    def rec(i: int, mask, chosen: list[_Group], credits: int) -> None:
        if state["stop"]:
            return
        state["nodes"] += 1
        if state["nodes"] % 512 == 0 and time.perf_counter() - t0 > cfg.gen_timeout_s:
            state["stop"] = True
            return
        if lo_c is not None and credits + max_credit_after[i] < lo_c:
            return
        if i == len(order):
            if chosen:
                emit(chosen)
            return
        code = order[i]
        for g in groups[code]:
            if overlaps(mask, g.mask):
                continue
            chosen.append(g)
            if not prune or not _violates_monotone(
                analyzer, tuple(x.rep for x in chosen), req, cfg
            ):
                rec(i + 1, mask_or(mask, g.mask), chosen, credits + g.credits)
            chosen.pop()
            if state["stop"]:
                return
        if code not in required:
            rec(i + 1, mask, chosen, credits)

    rec(0, EMPTY, [], 0)
    res.timetables = sorted(set(out))
    res.truncated = state["stop"]
    if res.truncated:
        res.warnings.append("일부만 만들었어요. 과목이나 꼭 지킬 조건을 더 정해 주세요.")
    res.elapsed_s = time.perf_counter() - t0
    log.info("시간표 %d개 생성 (%.2fs, 노드 %d)", len(out), res.elapsed_s, state["nodes"])
    return res
