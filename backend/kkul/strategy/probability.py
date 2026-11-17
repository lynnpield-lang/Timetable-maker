"""경쟁률 정리와 성공 확률 (01 C부 1–2장)."""

from __future__ import annotations

import math
from collections import Counter
from functools import lru_cache

import numpy as np
from scipy.stats import binom

from kkul.config import Config
from kkul.models import Competition, Course


def popularity_features(course: Course, n_sections: int, cfg: Config) -> dict[str, float]:
    """인기도 추정 특징 z_x (01 C부 1.2)."""
    slots = course.slots
    total = sum(s.end - s.start for s in slots) or 1
    lo, hi = cfg.prime_window
    prime = sum(max(0, min(s.end, hi) - max(s.start, lo)) for s in slots) / total if slots else 0.0
    off = any(s.start <= cfg.morning_cutoff or s.start >= cfg.night_cutoff for s in slots)
    return {
        "scarcity": 1.0 / max(1, n_sections),
        "major_core": 1.0 if "전공핵심" in (course.category or "") else 0.0,
        "prime_time": prime,
        "off_hours": 1.0 if off else 0.0,
        "dept_count": math.log1p(len(course.major_depts)),
    }


def estimate_ratio(course: Course, n_sections: int, cfg: Config) -> float:
    """r̂ = r₀ · exp(Σ β_j z_j)."""
    z = popularity_features(course, n_sections, cfg)
    return cfg.estimate_r0 * math.exp(sum(cfg.estimate_beta.get(k, 0.0) * v for k, v in z.items()))


def fit_estimate(
    captured: dict[str, Competition], courses: dict[str, Course], cfg: Config
) -> tuple[float, dict[str, float]] | None:
    """캡처값이 쌓이면 log r = log r₀ + Σ β z 를 최소제곱으로 맞춘다. 표본이 적으면 None."""
    counts = Counter(c.code for c in courses.values())
    rows, ys = [], []
    names = list(cfg.estimate_beta)
    for k, comp in captured.items():
        r = comp.ratio
        if r is None or r <= 0 or k not in courses:
            continue
        z = popularity_features(courses[k], counts[courses[k].code], cfg)
        rows.append([1.0] + [z[n] for n in names])
        ys.append(math.log(r))
    if len(rows) < len(names) + 3:
        return None
    coef, *_ = np.linalg.lstsq(np.array(rows), np.array(ys), rcond=None)
    return float(math.exp(coef[0])), {n: float(b) for n, b in zip(names, coef[1:], strict=True)}


def build_competition(
    keys, courses: dict[str, Course], captured: dict[str, Competition], cfg: Config
) -> dict[str, Competition]:
    """분반별 (a, c, 출처). 캡처값이 없으면 추정값 (정원 모르면 기본 정원 가정)."""
    counts = Counter(c.code for c in courses.values())
    out: dict[str, Competition] = {}
    for k in keys:
        got = captured.get(k)
        if got is not None and got.capacity and got.applied is not None:
            out[k] = got
            continue
        cap = (got.capacity if got and got.capacity else None) or cfg.default_capacity
        c = courses.get(k)
        r = estimate_ratio(c, counts[c.code], cfg) if c else cfg.estimate_r0
        out[k] = Competition(k, cap, max(1, round(r * cap)), "estimate")
    return out


def arrival_cdf(t: float, mu: float) -> float:
    """경쟁자 신청 시각 분포 F(t) = 1 − e^{−t/μ}."""
    return 1.0 - math.exp(-t / mu) if mu > 0 else 1.0


@lru_cache(maxsize=65_536)
def success_prob(a: int, c: int, k: int, mu: float = 30.0, delta_t: float = 5.0) -> float:
    """k번째로 신청할 때 성공 확률 p_x(k) = P[Binomial(a−1, F(kΔ)) ≤ c−1] (01 C부 2.2)."""
    if c <= 0:
        return 0.0
    if a <= c:
        return 1.0
    f = arrival_cdf(k * delta_t, mu)
    return float(binom.cdf(c - 1, a - 1, f))


def comp_prob(comp: Competition, k: int, mu: float, delta_t: float) -> float:
    """Competition 하나의 p(k)."""
    if not comp.capacity or comp.applied is None:
        return 1.0
    return success_prob(int(comp.applied), int(comp.capacity), int(k), float(mu), float(delta_t))


def drop_prob(comp: Competition, k: int, mu: float, delta_t: float) -> float:
    """미루면 잃는 확률 d_x(k) = p(k) − p(k+1)."""
    return comp_prob(comp, k, mu, delta_t) - comp_prob(comp, k + 1, mu, delta_t)


def scale_competition(comp: dict[str, Competition], factor: float) -> dict[str, Competition]:
    """경쟁률을 factor배로 바꾼 사본 (민감도 분석용)."""
    return {
        k: Competition(
            k,
            v.capacity,
            None if v.applied is None else max(1, round(v.applied * factor)),
            v.source,
        )
        for k, v in comp.items()
    }
