import itertools

import numpy as np
import pandas as pd
import pytest
from scipy.stats import binom

from kkul.config import Config
from kkul.models import Competition, LiveState
from kkul.strategy import next_step, plan, success_prob, wait_prob
from kkul.strategy.fallback import Planner, Ranked, loss, tree_leaves
from kkul.strategy.order import assign, value_matrix
from kkul.strategy.probability import build_competition, estimate_ratio
from kkul.strategy.simulate import fixed_policy, simulate


def test_success_prob_properties():
    assert success_prob(30, 40, 1) == 1.0  # a ≤ c 이면 항상 1
    ps = [success_prob(90, 40, k) for k in range(1, 12)]
    assert all(a >= b for a, b in zip(ps, ps[1:], strict=False))  # k가 늘면 줄어든다
    # scipy와 직접 합한 값이 같다
    a, c, k, mu, dt = 90, 40, 3, 30.0, 5.0
    f = 1 - np.exp(-k * dt / mu)
    direct = sum(binom.pmf(i, a - 1, f) for i in range(c))
    assert success_prob(a, c, k, mu, dt) == pytest.approx(direct)


def test_wait_prob():
    assert wait_prob(1, 40, 0.0) == 0.0
    assert wait_prob(0, 40, 0.05) == 1.0
    assert wait_prob(1, 40, 0.05) > wait_prob(5, 40, 0.05)


def test_estimate_and_competition(courses):
    cfg = Config()
    r = estimate_ratio(courses["BIZ3001-01"], 2, cfg)
    assert 0.3 < r < 5
    comp = build_competition(
        ["BIZ3001-01", "BIZ2021-01"],
        courses,
        {"BIZ2021-01": Competition("BIZ2021-01", 40, 80, "capture")},
        cfg,
    )
    assert comp["BIZ2021-01"].source == "capture" and comp["BIZ2021-01"].ratio == 2.0
    assert (
        comp["BIZ3001-01"].source == "estimate"
        and comp["BIZ3001-01"].capacity == cfg.default_capacity
    )


@pytest.mark.parametrize("n", [3, 5, 7])
def test_hungarian_equals_bruteforce(n):
    rng = np.random.default_rng(n)
    keys = [f"K{i}" for i in range(n)]
    w = {k: float(rng.random()) for k in keys}
    caps = {k: int(rng.integers(10, 40)) for k in keys}
    apps = {k: int(caps[k] * rng.uniform(0.5, 3)) for k in keys}

    def p(x, k):
        return success_prob(apps[x], caps[x], k)

    v = value_matrix(keys, w, p)
    best = max(
        itertools.permutations(range(n)), key=lambda perm: sum(v[i, perm[i]] for i in range(n))
    )
    got = assign(v, keys)
    got_val = sum(v[keys.index(x), pos] for pos, x in enumerate(got))
    assert got_val == pytest.approx(sum(v[i, best[i]] for i in range(n)))


def ranked_df():
    """작은 정렬 결과: 과목 A(A-01/A-02), B(B-01/B-02), C(C-01)."""
    rows = [
        (("A-01", "B-01", "C-01"), 15),
        (("A-02", "B-01", "C-01"), 15),
        (("A-01", "B-02", "C-01"), 15),
        (("A-02", "B-02", "C-01"), 15),
        (("A-01", "B-01"), 12),
    ]
    return pd.DataFrame(
        {
            "tt_id": [f"t{i}" for i in range(len(rows))],
            "sections": [r[0] for r in rows],
            "credits": [r[1] for r in rows],
            "rank": list(range(1, len(rows) + 1)),
            "super_gaps": [0, 1, 0, 2, 0],
        }
    )


def comp_all(ratio_hot=2.5):
    keys = ["A-01", "A-02", "B-01", "B-02", "C-01"]
    out = {k: Competition(k, 40, 20, "capture") for k in keys}
    out["C-01"] = Competition("C-01", 40, int(40 * ratio_hot), "capture")
    return out


def test_loss_and_next():
    R = Ranked(ranked_df())
    target = ("A-01", "B-01", "C-01")
    w_a, fb_a = loss("A-01", target, R, 3.0)
    assert fb_a.rank == 2 and w_a == pytest.approx(3.0 * (1 / 5))
    w_c, fb_c = loss("C-01", target, R, 3.0)
    assert fb_c.rank == 5
    assert w_c > w_a  # 대안이 나쁠수록 손실이 크다
    nxt = R.next({"B-01"}, {"A-01"})
    assert "B-01" in nxt.sections and "A-01" not in nxt.sections


def test_plan_end_to_end():
    cfg = Config(sim_runs=2000, sim_runs_sensitivity=300)
    target = ("A-01", "B-01", "C-01")
    res = plan(target, ranked_df(), comp_all(), cfg, required_codes=("A", "B", "C"), min_credits=15)
    assert res.order[0].key == "C-01"  # 경쟁 높고 대체 나쁨 → 먼저
    assert sorted(o.key for o in res.order) == list(target)
    leaves = tree_leaves(res.tree)
    assert 1 <= len(leaves) <= 2**cfg.tree_depth
    assert sum(lf.reach_prob for lf in leaves) == pytest.approx(1.0)
    p = {r.policy: r.p_target for r in res.policies}
    assert p["kkul"] >= p["basic"] - 1e-9
    assert res.sensitivity and res.robust_order


def test_simulation_reproducible_and_certain():
    cfg = Config(sim_runs=500)
    R = Ranked(ranked_df())
    target = ("A-01", "B-01", "C-01")
    comp = comp_all(ratio_hot=0.5)  # 모두 정원 이하 → p = 1
    pol = fixed_policy(sorted(target))
    r1 = simulate("basic", pol, comp, R, target, cfg)
    assert r1.p_target == 1.0
    comp2 = comp_all()
    a = simulate("basic", pol, comp2, R, target, cfg)
    b = simulate("basic", pol, comp2, R, target, cfg)
    assert a.p_target == b.p_target  # 시드 고정 → 같은 결과


def test_next_step_after_failure():
    cfg = Config()
    target = ("A-01", "B-01", "C-01")
    st = LiveState(target=target, secured=("C-01",), failed=("A-01",), clicks=2)
    ns = next_step(st, ranked_df(), comp_all(), cfg)
    assert ns.target is not None
    assert "C-01" in ns.target and "A-01" not in ns.target
    assert ns.next_keys and ns.next_keys[0] not in ("A-01", "C-01")


def test_planner_prefers_chosen_target():
    cfg = Config()
    R = Ranked(ranked_df())
    target = ("A-02", "B-02", "C-01")  # 4위를 골라도 처음 목표는 그것
    pl = Planner(R, comp_all(), cfg, lambda k: 1.0, target=target)
    cur, order = pl.plan_state(frozenset(), frozenset(), 0)
    assert cur.sections == frozenset(target)
    assert set(order) == set(target)
