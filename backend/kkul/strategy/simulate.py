"""몬테카를로 시뮬레이션·정책 비교·민감도 (01 C부 6장)."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable
from dataclasses import replace

import numpy as np

from kkul.config import Config
from kkul.models import Competition, SimResult, Timetable
from kkul.strategy.fallback import Planner, Ranked
from kkul.strategy.order import assign, optimal_order, value_matrix
from kkul.strategy.probability import comp_prob, scale_competition

Policy = Callable[[frozenset, frozenset, int], "str | None"]


def fixed_policy(order: list[str]) -> Policy:
    """정해진 순서대로 한 번씩, 플랜 B 없음."""

    def choose(a: frozenset, f: frozenset, clicks: int) -> str | None:
        for x in order:
            if x not in a and x not in f:
                return x
        return None

    return choose


def planner_policy(planner: Planner) -> Policy:
    """꿀시간표: 할당 순서 + 실패하면 Next로 갈아타기."""
    return planner.choose


def _ci(p: float, n: int) -> tuple[float, float]:
    h = 1.96 * math.sqrt(max(p * (1 - p), 0.0) / n) if n else 0.0
    return (max(0.0, p - h), min(1.0, p + h))


def draw_uniforms(n: int, max_clicks: int, seed: int) -> np.ndarray:
    """공통 난수: 같은 난수를 모든 정책에 쓴다."""
    return np.random.default_rng(seed).random((n, max_clicks))


def simulate(
    name: str,
    policy: Policy,
    comp: dict[str, Competition],
    ranked: Ranked,
    target: Timetable,
    cfg: Config,
    min_credits: int | None = None,
    uniforms: np.ndarray | None = None,
    n: int | None = None,
) -> SimResult:
    """한 정책을 N번 시뮬레이션해 지표를 낸다 (01 C부 6.1–6.2)."""
    n = n or cfg.sim_runs
    max_clicks = 4 * max(1, len(target)) + 8
    u = uniforms if uniforms is not None else draw_uniforms(n, max_clicks, cfg.seed)
    n = u.shape[0]
    max_clicks = u.shape[1]
    tset = frozenset(target)
    hit = top = minc = 0
    util = 0.0
    fails: Counter[str] = Counter()
    p_cache: dict[tuple[str, int], float] = {}

    def p(x: str, k: int) -> float:
        v = p_cache.get((x, k))
        if v is None:
            c = comp.get(x)
            v = 1.0 if c is None else comp_prob(c, k, cfg.mu_s, cfg.click_s)
            p_cache[(x, k)] = v
        return v

    for i in range(n):
        a: frozenset = frozenset()
        f: frozenset = frozenset()
        clicks = 0
        while clicks < max_clicks:
            x = policy(a, f, clicks)
            if x is None:
                break
            clicks += 1
            if u[i, clicks - 1] < p(x, clicks):
                a = a | {x}
            else:
                f = f | {x}
                fails[x] += 1
        row = ranked.find(a)
        if a == tset:
            hit += 1
        if row is not None and row.rank <= cfg.top_k_success:
            top += 1
        util += ranked.utility(row)
        if min_credits is not None and row is not None and row.credits >= min_credits:
            minc += 1
        elif min_credits is None and row is not None:
            minc += 1
    p_t = hit / n
    return SimResult(
        policy=name,
        runs=n,
        p_target=p_t,
        p_top_k=top / n,
        expected_utility=util / n,
        p_min_credits=minc / n,
        ci_target=_ci(p_t, n),
        most_failed=fails.most_common(1)[0][0] if fails else None,
        fail_counts=dict(fails),
    )


def policies_for(
    target: Timetable, planner: Planner, comp: dict[str, Competition]
) -> dict[str, Policy]:
    """비교할 세 정책 (01 C부 6.3)."""
    basic = sorted(target)
    by_ratio = sorted(target, key=lambda x: (-(comp[x].ratio or 0.0) if x in comp else 0.0, x))
    return {
        "basic": fixed_policy(basic),
        "ratio": fixed_policy(by_ratio),
        "kkul": planner_policy(planner),
    }


def compare_policies(
    target: Timetable,
    planner: Planner,
    comp: dict[str, Competition],
    ranked: Ranked,
    cfg: Config,
    min_credits: int | None = None,
    n: int | None = None,
) -> list[SimResult]:
    """같은 난수로 기본 / 경쟁률 순 / 꿀시간표를 비교한다."""
    n = n or cfg.sim_runs
    u = draw_uniforms(n, 4 * max(1, len(target)) + 8, cfg.seed)
    return [
        simulate(name, pol, comp, ranked, target, cfg, min_credits, u)
        for name, pol in policies_for(target, planner, comp).items()
    ]


def sensitivity(
    target: Timetable,
    ranked: Ranked,
    comp: dict[str, Competition],
    cfg: Config,
    imp,
    losses: dict[str, float],
    min_credits: int | None = None,
) -> tuple[list[dict], list[str]]:
    """가정(μ, Δ, 경쟁률)을 바꿔도 결론이 유지되는지 + 강건한 순서 (01 C부 6.4)."""
    scenarios = [
        ("기본", {}, 1.0),
        ("μ=10초", {"mu_s": 10.0}, 1.0),
        ("μ=60초", {"mu_s": 60.0}, 1.0),
        ("Δ=3초", {"click_s": 3.0}, 1.0),
        ("Δ=10초", {"click_s": 10.0}, 1.0),
        ("경쟁률 −30%", {}, 0.7),
        ("경쟁률 +30%", {}, 1.3),
    ]
    keys = sorted(target)
    base_order: list[str] | None = None
    rows: list[dict] = []
    v_sum = np.zeros((len(keys), len(keys)))
    for label, change, factor in scenarios:
        c2 = replace(cfg, **change)
        comp2 = scale_competition(comp, factor) if factor != 1.0 else comp

        def p(x: str, k: int, comp2=comp2, c2=c2) -> float:
            cc = comp2.get(x)
            return 1.0 if cc is None else comp_prob(cc, k, c2.mu_s, c2.click_s)

        order = optimal_order(keys, losses, p)
        v_sum += value_matrix(keys, losses, p)
        if base_order is None:
            base_order = order
        planner = Planner(ranked, comp2, c2, imp, target=target)
        res = compare_policies(
            target, planner, comp2, ranked, c2, min_credits, cfg.sim_runs_sensitivity
        )
        probs = {r.policy: r.p_target for r in res}
        rows.append(
            {
                "scenario": label,
                "mu": c2.mu_s,
                "delta_t": c2.click_s,
                "ratio_factor": factor,
                "order": order,
                "order_changed": order != base_order,
                "p_target": probs,
                "ranking_kept": probs["kkul"] >= probs["ratio"] - 1e-9
                and probs["kkul"] >= probs["basic"] - 1e-9,
            }
        )
    robust = assign(v_sum / len(scenarios), keys)
    return rows, robust
