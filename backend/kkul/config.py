"""기준값을 한곳에 모은다 (03_interfaces.md 7장). 코드에 숫자를 직접 쓰지 않는다."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    # B부 시간표
    morning_cutoff: int = 540  # τ_m 9:00
    early_cutoff: int = 630  # τ_e 10:30
    gap_min: int = 60  # τ_g 연강 경계
    super_gap: int = 180  # τ_s 슈퍼공강
    lunch_window: tuple[int, int] = (690, 810)
    lunch_need: int = 45
    night_cutoff: int = 1080
    walk_speed: float = 70.0  # m/분
    hill_factor: float = 1.3
    gen_limit: int = 50_000
    gen_timeout_s: float = 2.0
    exam_weight: float = 2.0  # α
    deadline_weight: float = 1.0  # β
    crunch_threshold: float = 4.0  # θ
    # C부 전략
    mu_s: float = 30.0
    click_s: float = 5.0
    drop_rate: float = 0.05
    required_importance: float = 3.0
    tree_depth: int = 3
    sim_runs: int = 10_000
    seed: int = 0
    # 공통
    schema_version: int = 1

    # --- 아래는 03_interfaces.md 7장에 아직 없는 값 (인터페이스 이슈로 합의 필요) ---
    include_online: bool = False  # 온라인 사전제작 강의를 충돌·시간 특징에 넣을지
    shuttle_min: float = 30.0  # 다른 캠퍼스 이동 시간 t_셔틀
    exam_period_weeks: tuple[int, ...] = (8, 15, 16)  # K′ 계산에서 뺄 시험 기간 주차
    semester_weeks: int = 16
    eval_coverage_warn: float = 50.0  # coverage가 이보다 낮으면 "평가 정보 부족"
    optional_importance: float = 1.0  # 들으면 좋은 과목 중요도
    default_capacity: int = 40  # 정원을 모를 때 가정하는 정원
    estimate_r0: float = (
        0.5  # 인기도 추정 r₀ (보통 과목이 경쟁률 1–1.5쯤 되도록 손으로 맞춘 시작값)
    )
    estimate_beta: dict[str, float] = field(
        default_factory=lambda: {
            "scarcity": 0.6,  # 1 / 같은 과목 분반 수
            "major_core": 0.3,  # 전공핵심
            "prime_time": 0.3,  # 10:30–15:00 수업 비율
            "off_hours": -0.4,  # 9:00 이하 또는 18:00 이후 시작
            "dept_count": 0.15,  # log(1 + 전공 인정 학과 수)
        }
    )
    prime_window: tuple[int, int] = (630, 900)  # 인기 시간대 10:30–15:00
    sim_runs_sensitivity: int = 2_000
    top_k_success: int = 5  # "상위 5개 안 확보 확률"


# 정렬 구간 폭 δ_j 기본값 (01 B부 6.1). 여기 없는 열은 δ = 1 (정수값 그대로).
DEFAULT_BINS: dict[str, float] = {
    "gap_minutes": 30,
    "max_gap": 30,
    "longest_block": 30,
    "avg_stay": 60,
    "max_stay": 60,
    "walk_minutes": 10,
    "exam_ratio": 10,
    "homework_ratio": 10,
    "attend_ratio": 10,
    "eval_coverage": 10,
    "avg_workload": 0.5,
    "peak_load": 1,
    "peak_load_regular": 1,
}

DEFAULT_CONFIG = Config()
