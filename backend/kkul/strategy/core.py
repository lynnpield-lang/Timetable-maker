"""C부 진입점: plan (순서·트리·시뮬레이션) 과 next_step (실시간 모드)."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from kkul.config import Config
from kkul.models import (
    Competition,
    LiveState,
    NextStep,
    OrderRow,
    StrategyResult,
    Timetable,
    make_timetable,
    tt_id,
)
from kkul.strategy.fallback import Planner, Ranked, build_tree, code_of, loss, risky_keys
from kkul.strategy.order import optimal_order
from kkul.strategy.simulate import compare_policies, sensitivity
from kkul.strategy.waitlist import advise

HIGH_RATIO = 1.5
HIGH_LOSS = 0.5


def importance_fn(required_codes: Iterable[str], cfg: Config):
    """imp_x: 꼭 들을 과목 3, 들으면 좋은 과목 1 (설정값)."""
    req = frozenset(required_codes)

    def imp(key: str) -> float:
        if not req:
            return cfg.required_importance
        return cfg.required_importance if code_of(key) in req else cfg.optional_importance

    return imp


def _ensure_target(ranked: pd.DataFrame, target: Timetable) -> pd.DataFrame:
    """목표 시간표가 정렬 결과에 없으면 맨 앞에 넣는다 (사용자가 고른 시간표가 1순위)."""
    tset = frozenset(target)
    if any(frozenset(s) == tset for s in ranked["sections"]):
        return ranked
    row = {c: None for c in ranked.columns}
    row.update({"sections": tuple(sorted(target)), "tt_id": tt_id(target), "rank": 0})
    out = pd.concat([pd.DataFrame([row]), ranked], ignore_index=True)
    out["rank"] = range(1, len(out) + 1)
    return out


def _tags(ratio: float | None, source: str, w: float, fb_rank: int | None, imp: float) -> list[str]:
    tags = []
    if ratio is not None and ratio >= HIGH_RATIO:
        tags.append("경쟁 높음")
    elif ratio is not None and ratio < 1:
        tags.append("여유")
    if fb_rank is None:
        tags.append("대체 없음")
    elif w >= HIGH_LOSS * imp:
        tags.append("대체 적음")
    else:
        tags.append("대체 쉬움")
    if source == "estimate":
        tags.append("추정 경쟁률")
    return tags


def plan(
    target: Timetable,
    ranked: pd.DataFrame,
    comp: dict[str, Competition],
    cfg: Config,
    required_codes: Iterable[str] = (),
    min_credits: int | None = None,
    with_sensitivity: bool = True,
) -> StrategyResult:
    """목표 시간표의 신청 순서·플랜 B 트리·시뮬레이션·정책 비교·민감도 (01 C부 1–7)."""
    target = make_timetable(target)
    R = Ranked(_ensure_target(ranked, target))
    imp = importance_fn(required_codes, cfg)
    planner = Planner(R, comp, cfg, imp, target=target)

    losses: dict[str, float] = {}
    fbs = {}
    for x in target:
        losses[x], fbs[x] = loss(x, target, R, imp(x))
    order = optimal_order(list(target), losses, planner.p, start=1)
    rows: list[OrderRow] = []
    for i, x in enumerate(order, start=1):
        c = comp.get(x)
        fb = fbs[x]
        rows.append(
            OrderRow(
                position=i,
                key=x,
                ratio=None if c is None else c.ratio,
                ratio_source="none" if c is None else c.source,
                success_prob=planner.p(x, i),
                loss=losses[x],
                fallback_tt_id=fb.tt_id if fb else None,
                fallback_rank=fb.rank if fb else None,
                fallback_sections=sorted(fb.sections) if fb else None,
                tags=_tags(
                    None if c is None else c.ratio,
                    "none" if c is None else c.source,
                    losses[x],
                    fb.rank if fb else None,
                    imp(x),
                ),
            )
        )
    risky = risky_keys(rows, cfg.tree_depth)
    tree = build_tree(target, planner, risky, cfg.tree_depth)
    policies = compare_policies(target, planner, comp, R, cfg, min_credits)
    kkul = next(p for p in policies if p.policy == "kkul")
    sens, robust = (
        sensitivity(target, R, comp, cfg, imp, losses, min_credits)
        if with_sensitivity
        else ([], order)
    )
    return StrategyResult(
        target=target,
        target_tt_id=tt_id(target),
        order=rows,
        tree=tree,
        simulation=kkul,
        policies=policies,
        sensitivity=sens,
        robust_order=robust,
        assumptions={
            "mu": cfg.mu_s,
            "delta_t": cfg.click_s,
            "drop": cfg.drop_rate,
            "tree_depth": cfg.tree_depth,
            "sim_runs": cfg.sim_runs,
            "seed": cfg.seed,
        },
    )


def next_step(
    state: LiveState,
    ranked: pd.DataFrame,
    comp: dict[str, Competition],
    cfg: Config,
    required_codes: Iterable[str] = (),
) -> NextStep:
    """실시간 모드: 성공/실패/대기 결과로 다음에 누를 학수번호를 정한다 (01 C부 5.3, 7)."""
    target = make_timetable(state.target)
    R = Ranked(_ensure_target(ranked, target))
    imp = importance_fn(required_codes, cfg)
    planner = Planner(R, comp, cfg, imp, target=target)
    secured = set(state.secured)
    failed = set(state.failed)
    clicks = state.clicks or (len(secured) + len(failed))
    advice = []
    for key, q in sorted(state.waiting.items()):
        a = advise(key, q, secured, failed, clicks, planner)
        advice.append(a)
        if a.advice == "wait":
            secured.add(key)  # 기다리는 동안은 확보한 것처럼 두고 다른 과목을 진행
        else:
            failed.add(key)
    cur, order = planner.plan_state(frozenset(secured), frozenset(failed), clicks)
    waiting_kept = {a.key for a in advice if a.advice == "wait"}
    if cur is None:
        return NextStep(
            [],
            None,
            None,
            None,
            advice,
            "갈 수 있는 시간표가 없어요. 조건을 풀어 다시 찾아 주세요.",
        )
    if not order:
        msg = (
            "목표 시간표를 모두 확보했어요." if not waiting_kept else "남은 것은 대기 결과뿐이에요."
        )
        return NextStep([], tuple(sorted(cur.sections)), cur.tt_id, cur.rank, advice, msg)
    msg = f"다음: {order[0]}"
    if frozenset(target) != cur.sections:
        msg += f" (시간표 {cur.rank}위로 변경)"
    return NextStep(order, tuple(sorted(cur.sections)), cur.tt_id, cur.rank, advice, msg)
