"""손실·Next·플랜 B 결정 트리 (01 C부 3장, 5장)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from kkul.config import Config
from kkul.models import Competition, Timetable, TreeNode, tt_id
from kkul.strategy.order import optimal_order
from kkul.strategy.probability import comp_prob

CERTAIN = 0.999  # 성공 확률이 이보다 크면 갈래를 만들지 않는다

CHANGE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("credits", "학점"),
    ("free_days", "우주공강"),
    ("super_gaps", "슈퍼공강"),
    ("morning_days", "9시 수업"),
    ("gap_minutes", "공강 합(분)"),
    ("late_risk", "지각 위험"),
)


def code_of(key: str) -> str:
    """분반 키 → 과목 코드."""
    return key.rsplit("-", 1)[0]


@dataclass(frozen=True)
class RankedRow:
    sections: frozenset[str]
    rank: int
    tt_id: str
    credits: int
    features: dict = field(hash=False, compare=False)


class Ranked:
    """정렬된 시간표 집합 𝒯_f (B부 결과)를 빠르게 찾기 위한 묶음."""

    def __init__(self, ranked: pd.DataFrame) -> None:
        df = ranked if "rank" in ranked.columns else ranked.assign(rank=range(1, len(ranked) + 1))
        df = df.sort_values("rank", kind="stable")
        self.rows: list[RankedRow] = []
        for rec in df.to_dict("records"):
            secs = frozenset(rec["sections"])
            self.rows.append(
                RankedRow(
                    secs,
                    int(rec["rank"]),
                    rec.get("tt_id") or tt_id(tuple(secs)),
                    int(rec.get("credits") or 0),
                    rec,
                )
            )
        self.n = len(self.rows)
        self.by_set: dict[frozenset[str], RankedRow] = {r.sections: r for r in self.rows}
        self._next_cache: dict[tuple, RankedRow | None] = {}

    def all_keys(self) -> set[str]:
        out: set[str] = set()
        for r in self.rows:
            out |= r.sections
        return out

    def utility_rank(self, rank: int | None) -> float:
        """u(T) = 1 − (rank − 1) / |𝒯_f| (01 C부 3.1)."""
        if rank is None or self.n == 0:
            return 0.0
        return 1.0 - (rank - 1) / self.n

    def utility(self, row: RankedRow | None) -> float:
        return 0.0 if row is None else self.utility_rank(row.rank)

    def find(self, tt) -> RankedRow | None:
        return self.by_set.get(frozenset(tt))

    def next(self, secured, failed, allow_drop: bool = False) -> RankedRow | None:
        """Next(A, F) = 확보한 분반을 포함하고 실패한 분반이 없는 가장 좋은 시간표 (01 C부 5.1)."""
        a, f = frozenset(secured), frozenset(failed)
        ck = (a, f, allow_drop)
        if ck in self._next_cache:
            return self._next_cache[ck]
        best = None
        for r in self.rows:
            if (allow_drop or a <= r.sections) and not (r.sections & f):
                best = r
                break
        self._next_cache[ck] = best
        return best


def utility(timetable: Timetable, ranked: Ranked) -> float:
    """시간표 효용. 𝒯_f에 없으면 0."""
    return ranked.utility(ranked.find(timetable))


def loss(x: str, target: Timetable, ranked: Ranked, imp: float) -> tuple[float, RankedRow | None]:
    """w_x = imp_x · (u(T*) − u(fb(x))), fb(x) = x 없이 갈 수 있는 최선 (01 C부 3.3)."""
    t = ranked.find(target)
    u_t = ranked.utility(t) if t else 1.0
    fb = ranked.next((), (x,))
    return imp * max(0.0, u_t - ranked.utility(fb)), fb


class Planner:
    """상태 (A, F, 클릭 수)에서 다음 목표와 신청 순서를 정한다. 트리·시뮬레이션·실시간 모드 공용."""

    def __init__(
        self,
        ranked: Ranked,
        comp: dict[str, Competition],
        cfg: Config,
        imp: Callable[[str], float],
        allow_drop: bool = False,
        target: Timetable | None = None,
    ) -> None:
        self.R = ranked
        self.target = frozenset(target) if target else None
        self.target_row = ranked.find(target) if target else None
        self.comp = comp
        self.cfg = cfg
        self.imp = imp
        self.allow_drop = allow_drop
        self._order_cache: dict[tuple, tuple[RankedRow | None, list[str]]] = {}

    def p(self, key: str, k: int) -> float:
        c = self.comp.get(key)
        return 1.0 if c is None else comp_prob(c, k, self.cfg.mu_s, self.cfg.click_s)

    def current(self, secured, failed) -> RankedRow | None:
        """지금 노릴 시간표: 사용자가 고른 T*가 아직 가능하면 T*, 아니면 Next(A, F)."""
        a, f = frozenset(secured), frozenset(failed)
        if self.target_row is not None and a <= self.target and not (self.target & f):
            return self.target_row
        return self.R.next(a, f, self.allow_drop)

    def state_losses(self, secured, failed, cur: RankedRow, keys) -> dict[str, float]:
        """현재 목표 cur 기준, 분반 x 하나만 더 실패했을 때의 손실."""
        u_cur = self.R.utility(cur)
        out = {}
        for x in keys:
            fb = self.current(secured, set(failed) | {x})
            out[x] = self.imp(x) * max(0.0, u_cur - self.R.utility(fb))
        return out

    def plan_state(self, secured, failed, clicks: int) -> tuple[RankedRow | None, list[str]]:
        """(다음 목표, 남은 분반의 신청 순서)."""
        ck = (frozenset(secured), frozenset(failed), clicks)
        if ck in self._order_cache:
            return self._order_cache[ck]
        cur = self.current(secured, failed)
        if cur is None:
            res: tuple[RankedRow | None, list[str]] = (None, [])
        else:
            remaining = sorted(cur.sections - frozenset(secured))
            w = self.state_losses(secured, failed, cur, remaining)
            res = (cur, optimal_order(remaining, w, self.p, start=clicks + 1))
        self._order_cache[ck] = res
        return res

    def choose(self, secured, failed, clicks: int) -> str | None:
        """다음에 누를 분반 (없으면 None)."""
        _, order = self.plan_state(secured, failed, clicks)
        return order[0] if order else None


def describe_changes(final: RankedRow | None, target: RankedRow | None) -> list[str]:
    """목표 대비 특징 변화. 예: "슈퍼공강 +1"."""
    if final is None or target is None:
        return []
    out = []
    for col, label in CHANGE_COLUMNS:
        a, b = final.features.get(col), target.features.get(col)
        if a is None or b is None or a != a or b != b:  # NaN 제외
            continue
        d = a - b
        if d:
            out.append(
                f"{label} {'+' if d > 0 else ''}{int(d) if float(d).is_integer() else round(d, 1)}"
            )
    return out


def risky_keys(order_rows: list, m: int) -> set[str]:
    """위험도 (1 − p_x(π(x))) · w_x 상위 m개 분반 (01 C부 5.2)."""
    scored = [((1 - r.success_prob) * r.loss, r.key) for r in order_rows]
    scored = [s for s in scored if s[0] > 0]
    scored.sort(key=lambda s: (-s[0], s[1]))
    return {k for _, k in scored[:m]}


def build_tree(target: Timetable, planner: Planner, risky: set[str], m: int) -> TreeNode:
    """플랜 B 결정 트리. 위험한 분반에서만 성공/실패로 갈라지고 나머지는 성공으로 가정한다."""
    R = planner.R
    target_row = R.find(target)
    target_set = frozenset(target)

    def leaf(
        a: frozenset, clicks: int, reach: float, then: list[str], cur: RankedRow | None
    ) -> TreeNode:
        if cur is None:
            return TreeNode(
                key=None,
                click=clicks,
                success_prob=None,
                reach_prob=reach,
                then=then,
                leaf=True,
                final_sections=sorted(a),
                note="갈 수 있는 시간표가 없어요. 조건을 풀어 다시 찾아야 해요.",
            )
        note = "목표 시간표" if cur.sections == target_set else f"시간표 {cur.rank}위로 변경"
        return TreeNode(
            key=None,
            click=clicks,
            success_prob=None,
            reach_prob=reach,
            then=then,
            leaf=True,
            final_sections=sorted(cur.sections),
            final_tt_id=cur.tt_id,
            final_rank=cur.rank,
            changes=describe_changes(cur, target_row),
            note=note,
        )

    def node(a: frozenset, f: frozenset, clicks: int, reach: float, budget: int) -> TreeNode:
        then: list[str] = []
        while True:
            cur, order = planner.plan_state(a, f, clicks)
            if cur is None or not order:
                return leaf(a, clicks, reach, then, cur)
            x = order[0]
            clicks += 1
            p = planner.p(x, clicks)
            branch = budget > 0 and p < CERTAIN and (x in risky or x not in target_set)
            if not branch:
                then.append(x)
                a = a | {x}
                continue
            n = TreeNode(key=x, click=clicks, success_prob=p, reach_prob=reach, then=then)
            n.on_success = node(a | {x}, f, clicks, reach * p, budget - 1)
            n.on_fail = node(a, f | {x}, clicks, reach * (1 - p), budget - 1)
            return n

    return node(frozenset(), frozenset(), 0, 1.0, m)


def tree_leaves(n: TreeNode) -> list[TreeNode]:
    """트리의 잎 목록."""
    if n.leaf:
        return [n]
    out = []
    for ch in (n.on_success, n.on_fail):
        if ch is not None:
            out += tree_leaves(ch)
    return out
