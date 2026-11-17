"""C부: 수강신청 전략 (03 5장 함수 약속)."""

from kkul.strategy.core import next_step, plan
from kkul.strategy.explain import explain
from kkul.strategy.probability import build_competition, estimate_ratio, success_prob
from kkul.strategy.waitlist import wait_prob

__all__ = [
    "build_competition",
    "estimate_ratio",
    "explain",
    "next_step",
    "plan",
    "success_prob",
    "wait_prob",
]
