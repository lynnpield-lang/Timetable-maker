"""신청 순서 최적화 = 선형 할당 문제 (01 C부 4장)."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from scipy.optimize import linear_sum_assignment

TIE_EPS = 1e-3  # 손실이 모두 0이어도 미루면 잃는 확률이 큰 분반이 앞서게 하는 작은 가중치


def value_matrix(
    keys: list[str], w: dict[str, float], p: Callable[[str, int], float], start: int = 1
) -> np.ndarray:
    """V[x, k] = w_x · p_x(start + k)."""
    n = len(keys)
    v = np.zeros((n, n))
    for i, x in enumerate(keys):
        wx = w.get(x, 0.0) + TIE_EPS
        for j in range(n):
            v[i, j] = wx * p(x, start + j)
    return v


def assign(v: np.ndarray, keys: list[str]) -> list[str]:
    """V를 최대화하는 순서 (헝가리안)."""
    if not keys:
        return []
    rows, cols = linear_sum_assignment(v, maximize=True)
    pos = {keys[r]: c for r, c in zip(rows, cols, strict=True)}
    return sorted(keys, key=lambda x: pos[x])


def optimal_order(
    keys, w: dict[str, float], p: Callable[[str, int], float], start: int = 1
) -> list[str]:
    """max_π Σ w_x · p_x(π(x)) 를 푸는 신청 순서."""
    keys = sorted(keys)
    return assign(value_matrix(keys, w, p, start), keys)


def objective(
    order: list[str], w: dict[str, float], p: Callable[[str, int], float], start: int = 1
) -> float:
    """순서의 목적함수 값 Σ w_x · p_x(위치) (검산·비교용)."""
    return sum(w.get(x, 0.0) * p(x, start + i) for i, x in enumerate(order))
