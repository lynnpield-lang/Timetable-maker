"""요청·응답 pydantic 모델 (03_interfaces.md 6장, 02 'API 목록'). 공동 소유."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

# 03 4장 특징 열. kkul/timetable/analyzer.py의 FEATURES와 같아야 한다 (tests/test_api.py가 검사)
FEATURE_COLUMNS: tuple[str, ...] = (
    "morning_days",
    "early_days",
    "morning_streak",
    "super_gaps",
    "gap_minutes",
    "max_gap",
    "longest_block",
    "free_days",
    "free_day_set",
    "avg_stay",
    "max_stay",
    "lunch_days",
    "night_classes",
    "late_risk",
    "walk_minutes",
    "credits",
    "major_credits",
    "exam_ratio",
    "homework_ratio",
    "attend_ratio",
    "eval_coverage",
    "teamwork_courses",
    "strict_attendance",
    "avg_workload",
    "peak_load",
    "peak_load_regular",
    "crunch_weeks",
)

T = TypeVar("T")


class ErrorBody(BaseModel):
    code: str
    message: str
    detail: dict = Field(default_factory=dict)


class Page(BaseModel, Generic[T]):
    total: int
    items: list[T]
    page: int = 1
    page_size: int = 20


# ------------------------------------------------------------------ 메타·과목


class Department(BaseModel):
    code: str
    name: str
    campus: int = 1
    college: str = ""


class FeatureInfo(BaseModel):
    column: str
    label: str
    better: int  # +1 낮을수록 / −1 높을수록 / 0 없음
    kind: str  # int / float / str (뒤에 ?가 붙으면 모를 수 있음)


class MetaOut(BaseModel):
    term: str
    built_at: str | None = None
    schema_version: int
    campuses: list[int]
    departments: list[Department]
    counts: dict[str, int] = Field(default_factory=dict)
    features: list[FeatureInfo]
    llm_available: bool
    mock: bool = False


class SlotOut(BaseModel):
    day: int
    start: int
    end: int
    room: str | None = None


class CourseSummary(BaseModel):
    key: str
    code: str
    section: str
    name: str
    name_en: str = ""
    professor: str
    credits: int
    category: str
    mode: str
    is_online: bool
    english: bool
    slots: list[SlotOut]
    eval: dict[str, int | None]
    eval_source: str
    restricted_depts: list[str]
    major_depts: list[str]
    badges: list[str] = Field(default_factory=list)
    sections_in_course: int = 1


# ------------------------------------------------------------------ 시간표 만들기·찾기


class WantedIn(BaseModel):
    code: str
    required: bool = True
    sections: list[str] | None = None


class FiltersIn(BaseModel):
    bounds: dict[str, tuple[float | None, float | None]] = Field(default_factory=dict)
    free_days: list[int] = Field(default_factory=list)
    include_missing_eval: bool = True


class SortKeyIn(BaseModel):
    column: str
    direction: int = 1


class SettingsIn(BaseModel):
    """사용자가 화면에서 바꾸는 기준값 (Config 일부)."""

    morning_cutoff: int | None = None
    early_cutoff: int | None = None
    gap_min: int | None = None
    super_gap: int | None = None
    lunch_need: int | None = None
    include_online: bool | None = None


class GenerateRequest(BaseModel):
    user_depts: list[str] = Field(default_factory=list)
    wanted: list[WantedIn]
    hard: FiltersIn = Field(default_factory=FiltersIn)
    credit_min: int | None = None
    credit_max: int | None = None
    include_ineligible: bool = False
    major_only: bool = False
    settings: SettingsIn = Field(default_factory=SettingsIn)


class GenerateOut(BaseModel):
    set_id: str
    count: int
    truncated: bool
    warnings: list[str]
    excluded: dict[str, list[str]] = Field(default_factory=dict)
    elapsed_s: float = 0.0


class QueryRequest(BaseModel):
    filters: FiltersIn = Field(default_factory=FiltersIn)
    sort: list[SortKeyIn] = Field(default_factory=list)
    bins: dict[str, float] = Field(default_factory=dict)
    fold: bool = True
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class GridBlock(BaseModel):
    key: str
    name: str
    day: int
    start: int
    end: int
    room: str | None = None
    color: int
    online: bool
    late_risk: bool


class TimetableCard(BaseModel):
    tt_id: str
    rank: int
    sections: list[str]
    grid: list[GridBlock]
    tags: list[str]
    features: dict[str, float | str | None]
    group_size: int
    credits: int


class RelaxSuggestion(BaseModel):
    key: str
    gain: int
    count: int
    text: str
    change: dict


class QueryOut(BaseModel):
    total: int
    total_unfolded: int
    items: list[TimetableCard]
    counts: dict[str, int]
    relax: list[RelaxSuggestion]
    page: int
    page_size: int


class SimilarOut(BaseModel):
    total: int
    items: list[TimetableCard]


class CourseCard(BaseModel):
    key: str
    code: str
    name: str
    professor: str
    credits: int
    category: str
    mode: str
    is_online: bool
    english: bool
    is_major: bool = False
    language: str | None = None
    lecture_style: list[str] | None = None
    eval: dict[str, int | None]
    eval_source: str
    exam_count: int | None = None
    exam_types: list[str] | None = None
    open_book: bool | None = None
    exam_weeks: list[int] | None = None
    assignments: list[dict] | None = None
    teamwork: bool | None = None
    attendance_rule: str | None = None
    attendance_strict: bool | None = None
    workload_level: int | None = None
    deadline_weeks: list[int] | None = None
    prerequisite: str | None = None
    materials: list[str] | None = None
    notes: list[str] | None = None
    evidence: dict[str, str] = Field(default_factory=dict)
    source: str | None = None
    has_profile: bool


class CrunchWeek(BaseModel):
    week: int
    load: float
    items: list[str]
    text: str


class DetailSummary(BaseModel):
    weekly_load: list[float]
    weekly_load_by_course: dict[str, list[float]]
    crunch_weeks: list[CrunchWeek]
    eval: dict[str, float | int | bool | None]
    counts: dict[str, int]
    styles: dict[str, int]


class TimetableDetail(BaseModel):
    tt_id: str
    rank: int | None = None
    sections: list[str]
    grid: list[GridBlock]
    tags: list[str]
    features: dict[str, float | str | None]
    cards: list[CourseCard]
    summary: DetailSummary


class TextIn(BaseModel):
    text: str


class TextOut(BaseModel):
    text: str


class PreferencesOut(BaseModel):
    filters: dict[str, list[float | None]]
    free_days: list[int]
    sort: list[list]
    unclear: list[str]


# ------------------------------------------------------------------ 캡처·경쟁률


class CaptureRowOut(BaseModel):
    key: str
    capacity: int | None = None
    applied: int | None = None
    ok: bool
    issue: str | None = None


class CaptureOut(BaseModel):
    rows: list[CaptureRowOut]


class CompetitionRowIn(BaseModel):
    key: str
    capacity: int = Field(gt=0)
    applied: int = Field(ge=0)


class CompetitionIn(BaseModel):
    rows: list[CompetitionRowIn]


class SavedOut(BaseModel):
    saved: int


class CompetitionOut(BaseModel):
    key: str
    capacity: int | None
    applied: int | None
    ratio: float | None
    source: str


# ------------------------------------------------------------------ 전략


class StrategyRequest(BaseModel):
    mu: float | None = Field(default=None, gt=0)
    delta_t: float | None = Field(default=None, gt=0)
    drop: float | None = Field(default=None, ge=0, le=1)
    m: int | None = Field(default=None, ge=0, le=5)
    sim_runs: int | None = Field(default=None, ge=100, le=50_000)
    sensitivity: bool = True


class OrderRowOut(BaseModel):
    position: int
    key: str
    name: str = ""
    ratio: float | None
    ratio_source: str
    success_prob: float
    loss: float
    fallback_tt_id: str | None
    fallback_rank: int | None
    fallback_sections: list[str] | None
    tags: list[str]


class TreeNodeOut(BaseModel):
    key: str | None
    click: int
    success_prob: float | None
    reach_prob: float
    then: list[str] = Field(default_factory=list)
    on_success: TreeNodeOut | None = None
    on_fail: TreeNodeOut | None = None
    leaf: bool = False
    final_sections: list[str] | None = None
    final_tt_id: str | None = None
    final_rank: int | None = None
    changes: list[str] = Field(default_factory=list)
    note: str = ""


class SimResultOut(BaseModel):
    policy: str
    runs: int
    p_target: float
    p_top_k: float
    expected_utility: float
    p_min_credits: float
    ci_target: tuple[float, float]
    most_failed: str | None
    fail_counts: dict[str, int] = Field(default_factory=dict)


class SensitivityRow(BaseModel):
    scenario: str
    mu: float
    delta_t: float
    ratio_factor: float
    order: list[str]
    order_changed: bool
    p_target: dict[str, float]
    ranking_kept: bool


class StrategyOut(BaseModel):
    set_id: str
    tt_id: str
    target: list[str]
    order: list[OrderRowOut]
    tree: TreeNodeOut
    simulation: SimResultOut
    policies: list[SimResultOut]
    sensitivity: list[SensitivityRow]
    robust_order: list[str]
    competition: list[CompetitionOut]
    assumptions: dict[str, float]


class PerCourseOut(BaseModel):
    key: str
    reason: str


class ExplainOut(BaseModel):
    summary: str
    per_course: list[PerCourseOut]
    warnings: list[str]
    source: str = "rule"


class NextRequest(BaseModel):
    target_tt_id: str
    secured: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)
    waiting: dict[str, int] = Field(default_factory=dict)
    clicks: int = 0


class WaitAdviceOut(BaseModel):
    key: str
    queue: int
    p_wait: float
    wait_value: float
    switch_value: float
    advice: str
    message: str


class NextOut(BaseModel):
    next_keys: list[str]
    target_tt_id: str | None
    target_sections: list[str] | None
    target_rank: int | None
    wait_advice: list[WaitAdviceOut]
    message: str


TreeNodeOut.model_rebuild()
