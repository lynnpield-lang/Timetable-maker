"""대기순번 판단 (01 C부 7장)."""

from __future__ import annotations

from scipy.stats import binom

from kkul.models import WaitAdvice
from kkul.strategy.fallback import Planner, code_of


def wait_prob(q: int, c: int, drop: float = 0.05) -> float:
    """대기 q번이 들어갈 확률 P[D ≥ q], D ~ Binomial(c, δ)."""
    if q <= 0:
        return 1.0
    if c <= 0 or drop <= 0:
        return 0.0
    return float(binom.sf(q - 1, c, drop))


def advise(key: str, queue: int, secured, failed, clicks: int, planner: Planner) -> WaitAdvice:
    """기다릴지 갈아탈지. 다른 분반을 신청하면 대기가 사라진다고 보수적으로 가정한다."""
    R = planner.R
    comp = planner.comp.get(key)
    cap = comp.capacity if comp and comp.capacity else planner.cfg.default_capacity
    pw = wait_prob(queue, cap, planner.cfg.drop_rate)
    a, f = frozenset(secured), frozenset(failed)
    cur = planner.current(a, f)
    # 기다리다 끝내 못 들어가면: 같은 과목을 통째로 빼고 남은 것으로 (나중엔 다른 분반도 찼다고 가정)
    same_course = {x for x in R.all_keys() if code_of(x) == code_of(key)}
    late_alt = planner.current(a, f | same_course)
    wait_value = pw * R.utility(cur) + (1 - pw) * R.utility(late_alt)
    # 지금 갈아타기: Next(A, F ∪ {x}) 의 새 분반을 다음 클릭들에서 확보할 확률
    alt = planner.current(a, f | {key})
    if alt is None:
        switch_value = R.utility(late_alt)
    else:
        need = sorted(alt.sections - a)
        p_all = 1.0
        for i, x in enumerate(need, start=1):
            p_all *= planner.p(x, clicks + i)
        switch_value = p_all * R.utility(alt) + (1 - p_all) * R.utility(late_alt)
    if wait_value >= switch_value:
        msg = (
            f"{key} 대기 {queue}번 유지: 들어갈 확률 약 {round(pw * 100)}%. "
            "이 과목은 다시 누르지 마세요 (다시 신청하면 대기순번이 사라져요)."
        )
        adv = "wait"
    else:
        repl = sorted(x for x in (alt.sections - a) if code_of(x) == code_of(key)) if alt else []
        others = sorted(x for x in (alt.sections - a) if code_of(x) != code_of(key)) if alt else []
        alt_keys = ", ".join(repl) if repl else "이 과목 빼기"
        if others:
            alt_keys += f" (이어서 {', '.join(others)})"
        msg = (
            f"{key} 대기 {queue}번은 들어갈 확률이 약 {round(pw * 100)}%로 낮아요. "
            f"대안 분반으로 이동: {alt_keys}"
        )
        adv = "switch"
    return WaitAdvice(key, queue, pw, wait_value, switch_value, adv, msg)
