"""공통 자료형 (03_interfaces.md 3장, 5장). 공동 소유: 바꿀 때는 합의 필수."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import NamedTuple

EVAL_KEYS: tuple[str, ...] = (
    "attend",
    "homework",
    "quiz",
    "mid",
    "final",
    "presentation",
    "project",
    "etc",
)

DAY_NAMES: tuple[str, ...] = ("월", "화", "수", "목", "금", "토")
DAYS: tuple[int, ...] = (0, 1, 2, 3, 4, 5)
WEEKDAYS: tuple[int, ...] = (0, 1, 2, 3, 4)


class Slot(NamedTuple):
    day: int  # 0=월 … 5=토
    start: int  # 분
    end: int  # 분
    room: str | None  # "33303"

    @property
    def building(self) -> str | None:
        """강의실 코드 앞 두 자리 (03 1장)."""
        if not self.room or len(self.room) < 2 or not self.room[:2].isdigit():
            return None
        return self.room[:2]


@dataclass(frozen=True)
class Course:
    key: str
    code: str
    section: str
    name: str
    name_en: str
    credits: int
    hours: int
    professor: str
    campus: int
    slots: tuple[Slot, ...]
    category: str
    mode: str
    is_online: bool
    module: str | None
    english: bool
    note: str
    restricted_depts: tuple[str, ...]
    major_depts: tuple[str, ...]
    language: str | None
    prerequisite: str | None
    eval: dict[str, int | None]  # 8개 키 고정 (EVAL_KEYS 순서)
    eval_source: str  # web / pdf_llm / none
    self_study: str | None
    teamwork: bool | None
    exam_count: int | None
    exam_weeks: tuple[int, ...] | None
    deadline_weeks: tuple[int, ...] | None
    workload_level: int | None
    attendance_strict: bool | None

    def __hash__(self) -> int:  # eval이 dict라 기본 hash가 실패하므로 키로 해시
        return hash(self.key)

    @property
    def has_eval(self) -> bool:
        """평가 비율 정보가 하나라도 있는지."""
        return any(v is not None for v in self.eval.values())


Timetable = tuple[str, ...]  # 분반 키를 정렬한 튜플. 같은 시간표는 항상 같은 튜플


def make_timetable(keys) -> Timetable:
    """분반 키 모음을 정렬된 튜플(Timetable)로 만든다."""
    return tuple(sorted(keys))


def tt_id(tt: Timetable) -> str:
    """시간표 id: 키 튜플을 |로 이은 문자열의 SHA-1 앞 10자리 (03 3장)."""
    return hashlib.sha1("|".join(sorted(tt)).encode("utf-8")).hexdigest()[:10]


# ---------------------------------------------------------------- B부 요청·결과

Range = tuple[float | None, float | None]  # (하한, 상한), None = 제한 없음


@dataclass(frozen=True)
class WantedCourse:
    code: str  # 과목 코드 (BIZ2021)
    required: bool = True  # 꼭 들을 과목 / 들으면 좋은 과목
    sections: tuple[str, ...] | None = None  # 허용 분반 키. None = 전부


@dataclass(frozen=True)
class Filters:
    bounds: dict[str, Range] = field(default_factory=dict)  # 특징 열 → (l, u)
    free_days: tuple[int, ...] = ()  # 반드시 비울 요일 (F_set ∋ d)
    include_missing_eval: bool = True  # 끄면 eval_coverage == 100만


@dataclass(frozen=True)
class SortKey:
    column: str
    direction: int = 1  # +1 작은 값 먼저, −1 큰 값 먼저


@dataclass(frozen=True)
class GenerateSpec:
    wanted: tuple[WantedCourse, ...]
    user_depts: tuple[str, ...] = ()  # U = {u₀, u₁, …}
    hard: Filters = field(default_factory=Filters)  # 꼭 지킬 조건 (가지치기에 사용)
    credit_range: Range = (None, None)
    include_ineligible: bool = False  # 수강 대상 아닌 분반도 넣기
    major_only: bool = False  # 내 전공 인정 분반만
    dept_alias: dict[str, str] = field(default_factory=dict)


@dataclass
class GenerateResult:
    timetables: list[Timetable]
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)
    excluded: dict[str, list[str]] = field(default_factory=dict)  # 과목 코드 → 자격 때문에 뺀 분반
    ineligible_keys: set[str] = field(default_factory=set)  # 수강 대상 아님 배지
    major_keys: set[str] = field(default_factory=set)  # 내 전공 인정 배지
    elapsed_s: float = 0.0


# ---------------------------------------------------------------- C부 전략


@dataclass(frozen=True)
class Competition:
    key: str
    capacity: int | None
    applied: int | None
    source: str = "estimate"  # capture / manual / estimate

    @property
    def ratio(self) -> float | None:
        """경쟁률 r = a / c."""
        if not self.capacity or self.applied is None:
            return None
        return self.applied / self.capacity


@dataclass
class OrderRow:
    position: int
    key: str
    ratio: float | None
    ratio_source: str
    success_prob: float
    loss: float
    fallback_tt_id: str | None
    fallback_rank: int | None
    fallback_sections: list[str] | None
    tags: list[str]


@dataclass
class TreeNode:
    key: str | None  # 이 마디에서 신청할 분반. 잎이면 None
    click: int  # 몇 번째 클릭인지
    success_prob: float | None
    reach_prob: float  # 루트에서 이 마디에 올 확률
    on_success: TreeNode | None = None
    on_fail: TreeNode | None = None
    then: list[str] = field(default_factory=list)  # 갈래 없이 이어서 누를 분반 (성공 가정)
    # 잎 정보
    leaf: bool = False
    final_sections: list[str] | None = None
    final_tt_id: str | None = None
    final_rank: int | None = None
    changes: list[str] = field(default_factory=list)  # 목표 대비 특징 변화
    note: str = ""


@dataclass
class SimResult:
    policy: str
    runs: int
    p_target: float
    p_top_k: float
    expected_utility: float
    p_min_credits: float
    ci_target: tuple[float, float]
    most_failed: str | None
    fail_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class WaitAdvice:
    key: str
    queue: int
    p_wait: float
    wait_value: float
    switch_value: float
    advice: str  # wait / switch
    message: str


@dataclass
class StrategyResult:
    target: Timetable
    target_tt_id: str
    order: list[OrderRow]
    tree: TreeNode
    simulation: SimResult
    policies: list[SimResult]
    sensitivity: list[dict]
    robust_order: list[str]
    assumptions: dict[str, float]


@dataclass(frozen=True)
class LiveState:
    target: Timetable
    secured: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()
    waiting: dict[str, int] = field(default_factory=dict)  # 분반 키 → 대기 번호
    clicks: int = 0


@dataclass
class NextStep:
    next_keys: list[str]
    target: Timetable | None
    target_tt_id: str | None
    target_rank: int | None
    wait_advice: list[WaitAdvice]
    message: str
