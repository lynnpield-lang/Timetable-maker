# 03. 인터페이스 명세 (데이터·함수·API 약속)

두 사람이 따로 만든 코드가 한 번에 맞물리도록, **주고받는 모든 것의 형식**을 여기서 정한다. 이 문서와 코드(`kkul/models.py`, `kkul/config.py`, `api/schemas.py`)가 다르면 버그로 본다. 바꾸는 절차는 [04_conventions.md](04_conventions.md)의 "인터페이스 변경 절차"를 따른다.

- 현재 스키마 버전: **1**
- 담당: 공동 (변경은 반드시 두 사람 합의)

---

## 1. 공통 단위와 표기

| 항목 | 규칙 | 예 |
|---|---|---|
| 분반 키 | `학수번호-분반`, 정규식 `^[A-Z]{2,4}\d{3,4}-\d{2}$` (실데이터로 1주차에 확정) | `BIZ2021-01` |
| 과목 코드 | 분반 키의 앞부분 | `BIZ2021` |
| 학기 | `<연도>_<학기코드>`, 학기코드 10 = 1학기, 20 = 2학기 | `2026_20` |
| 시각 | 자정부터의 **분**, 정수 | 10:30 → `630` |
| 요일 | 정수 0–5 = 월–토 | 수요일 → `2` |
| 학기 주차 | 정수 1–16 | |
| 비율 | **정수 퍼센트 0–100** (0.3 같은 소수 금지) | 30% → `30` |
| 학점·시수 | 정수 | |
| 모르는 값 | **`None`** (CSV에서는 빈칸). 절대 0으로 채우지 않는다 | |
| 문자열 인코딩 | UTF-8 | |
| 날짜·시각 | ISO 8601, 한국 시간 | `2026-11-13T16:40:00+09:00` |
| 건물 번호 | 강의실 코드 앞 두 자리, 문자열 | `33303` → `"33"` |

> 모르는 값을 0으로 채우면 "시험 0%", "팀플 없음"으로 잘못 계산된다. `None`과 0은 반드시 구분한다.

## 2. 파일 형식

모든 데이터 파일은 `data/` 아래에 둔다. 학기별 파일은 이름에 학기를 붙인다.

| 파일 | 만드는 곳 | 커밋 | 형식 |
|---|---|---|---|
| `data/courses_<학기>.csv` | `kkul/loader/build.py` | ✅ | CSV, UTF-8, 헤더 있음 |
| `data/profiles_<학기>.jsonl` | `kkul/loader/extract_syllabus.py` | ✅ | 한 줄에 JSON 하나 |
| `data/meta_<학기>.json` | `kkul/loader/build.py` | ✅ | JSON |
| `data/buildings.csv` | 손으로 입력 | ✅ | CSV |
| `data/dept_alias.csv` | 손으로 입력 | ✅ | CSV |
| `data/raw/**` | `kkul/loader/skku_client.py`, `syllabus.py` | ❌ | SSV 원문, PDF |
| 사용자 캡처·`competition.csv` | 앱 실행 중 | ❌ | 서버 메모리 (파일로 남기지 않음) |

### 2.1 CSV 공통 규칙
- 구분자 `,`, 따옴표 `"`, 줄바꿈 `\n`, 첫 줄은 열 이름
- 목록 값은 `|`로 잇는다: `경영학과|자유전공계열`
- 참/거짓은 `1` / `0`, 모르면 빈칸
- 숫자를 모르면 빈칸
- 읽기·쓰기는 `kkul/io.py`의 `read_courses()`, `write_courses()`만 쓴다. 각자 `pd.read_csv`로 직접 읽지 않는다 (형 변환이 달라지는 것을 막기 위해).

### 2.2 `courses_<학기>.csv` 열

| 열 | 형 | 설명 | 예 |
|---|---|---|---|
| `key` | str | 분반 키 (유일) | `BIZ2021-01` |
| `code` | str | 과목 코드 | `BIZ2021` |
| `section` | str | 분반 | `01` |
| `name` | str | 과목명 | `관리회계` |
| `name_en` | str | 영문 과목명 | `Managerial Accounting` |
| `credits` | int | 학점 | `3` |
| `hours` | int | 시수 | `3` |
| `professor` | str | 교수 이름 | `조현권` |
| `campus` | int | 1 = 인문사회, 2 = 자연과학 (2는 확인 필요) | `1` |
| `slots` | str | 수업 조각 `요일-시작-끝`을 `;`로 이음 | `1-720-795;3-810-885` |
| `rooms` | str | `slots`와 같은 순서의 강의실, `;`로 이음, 없으면 빈 칸 | `33303;33303` |
| `category` | str | 이수구분 | `전공핵심` |
| `mode` | str | 수업 형태 | `오프라인` |
| `is_online` | bool | 온라인 사전제작 여부 | `0` |
| `module` | str? | 모듈 강좌 표시 | `A` |
| `english` | bool | 국제어수업 | `1` |
| `note` | str | 비고 | `*6모듈강좌(모듈A)` |
| `restricted_depts` | list | 수강 대상 학과 (비면 제한 없음) | |
| `major_depts` | list | 전공 인정 학과 | `경영학과\|자유전공계열` |
| `language` | str? | 수업 언어 | `영어` |
| `prerequisite` | str? | 선수과목 | |
| `eval_attend` … `eval_etc` | int? | 평가 비율 8개: `attend, homework, quiz, mid, final, presentation, project, etc` | `10` |
| `eval_source` | str | `web` / `pdf_llm` / `none` | `pdf_llm` |
| `self_study` | str? | 예습·복습 시간 | |
| `teamwork` | bool? | 팀플 여부 | `1` |
| `exam_count` | int? | 시험 횟수 | `2` |
| `exam_weeks` | list[int]? | 시험 주차 | `8\|15` |
| `deadline_weeks` | list[int]? | 주요 과제·발표 마감 주차 | `10\|14` |
| `workload_level` | int? | 과제 부담 1–5 | `4` |
| `attendance_strict` | bool? | 출석 엄격 | `1` |

### 2.3 `profiles_<학기>.jsonl` (한 줄 = 분반 하나)

```json
{"key": "BIZ2021-01",
 "source": "pdf",
 "extracted_at": "2026-11-20T21:03:00+09:00",
 "lecture_style": ["강의", "사례 토론"],
 "exams": {"count": 2, "types": ["서술형"], "open_book": false, "weeks": [8, 15]},
 "assignments": [{"name": "팀 프로젝트", "team": true, "count": 1, "weeks": [10, 14]}],
 "attendance": {"strict": true, "rule": "결석 4회 이상 F"},
 "materials": ["교재명"],
 "prerequisite": "회계원리",
 "notes": ["모듈 강좌: 학기 전반부 6주"],
 "evidence": {"eval": "Midterm 30%, Final 30%", "teamwork": "team project"}}
```

- 없는 항목은 키를 빼지 말고 `null`로 둔다.
- `evidence`의 문장은 원문에 실제로 있는 짧은 인용만 (검증을 통과한 것만 저장).
- 원문 전체 텍스트는 저장하지 않는다.

### 2.4 `meta_<학기>.json`

```json
{"schema_version": 1, "term": "2026_20", "built_at": "2026-11-20T21:10:00+09:00",
 "departments": ["316901"], "counts": {"sections": 108, "parse_failed": 0,
 "eval_web": 41, "eval_pdf": 52, "eval_none": 15}}
```

앱은 시작할 때 `schema_version`을 확인하고, 코드가 기대하는 버전과 다르면 "데이터를 다시 build하세요"를 띄운다.

### 2.5 손으로 만드는 파일

`buildings.csv`

| 열 | 형 | 예 |
|---|---|---|
| `building` | str | `33` |
| `name` | str | `경영관` |
| `campus` | int | `1` |
| `lat`, `lon` | float? | `37.5880`, `126.9930` |

`dept_alias.csv`

| 열 | 형 | 예 |
|---|---|---|
| `alias` | str | `경영학` |
| `canonical` | str | `경영학과` |

## 3. Python 자료형 (`kkul/models.py`)

```python
from dataclasses import dataclass
from typing import NamedTuple

class Slot(NamedTuple):
    day: int          # 0=월 … 5=토
    start: int        # 분
    end: int          # 분
    room: str | None  # "33303"

@dataclass(frozen=True)
class Course:
    key: str; code: str; section: str
    name: str; name_en: str
    credits: int; hours: int
    professor: str; campus: int
    slots: tuple[Slot, ...]
    category: str; mode: str; is_online: bool
    module: str | None; english: bool; note: str
    restricted_depts: tuple[str, ...]; major_depts: tuple[str, ...]
    language: str | None; prerequisite: str | None
    eval: dict[str, int | None]          # 8개 키 고정 (2.2의 eval_* 순서)
    eval_source: str
    self_study: str | None
    teamwork: bool | None; exam_count: int | None
    exam_weeks: tuple[int, ...] | None; deadline_weeks: tuple[int, ...] | None
    workload_level: int | None; attendance_strict: bool | None

Timetable = tuple[str, ...]   # 분반 키를 정렬한 튜플. 같은 시간표는 항상 같은 튜플
```

- `Course`는 바꿀 수 없는 객체(`frozen`)다. 값을 바꾸려면 새로 만든다.
- 시간표는 `Course` 목록이 아니라 **키 튜플**로 주고받는다. 필요한 곳에서 `courses_by_key[k]`로 찾는다.
- 시간표 id(`tt_id`)는 키 튜플을 `|`로 이은 문자열의 SHA-1 앞 10자리. 같은 시간표는 어디서 만들어도 같은 id가 된다.

## 4. 특징표 열 이름 (B부 ↔ 화면 ↔ API 공통)

백엔드 문서의 기호와 코드의 열 이름을 이 표로 고정한다. 필터·정렬·화면 표시는 모두 이 열 이름을 쓴다.

| 기호 | 열 이름 | 형 | 좋은 방향 | 화면 이름 |
|---|---|---|---|---|
| M | `morning_days` | int | 낮을수록 | 9시 수업 요일 수 |
| E | `early_days` | int | 낮을수록 | 10시 반 이전 수업 요일 수 |
| M_streak | `morning_streak` | int | 낮을수록 | 9시 수업 연속 일수 |
| S | `super_gaps` | int | 낮을수록 | 슈퍼공강 횟수 |
| G | `gap_minutes` | int | 낮을수록 | 공강 합 (분) |
| G_max | `max_gap` | int | 낮을수록 | 가장 긴 공강 (분) |
| L | `longest_block` | int | 낮을수록 | 최장 연강 (분) |
| F | `free_days` | int | 높을수록 | 우주공강 일수 |
| F_set | `free_day_set` | str | — | 우주공강 요일 (`4` = 금, 여러 개면 `\|`로 이음) |
| H | `avg_stay` | int | 낮을수록 | 평균 체류시간 (분) |
| H_max | `max_stay` | int | 낮을수록 | 최대 체류시간 (분) |
| P | `lunch_days` | int | 높을수록 | 점심시간 있는 날 |
| N | `night_classes` | int | 낮을수록 | 야간 수업 수 |
| R | `late_risk` | int | 낮을수록 | 지각 위험 이동 |
| V | `walk_minutes` | int? | 낮을수록 | 이동 시간 합 (분) |
| C | `credits` | int | — | 총 학점 |
| C_major | `major_credits` | int | 높을수록 | 전공 인정 학점 |
| X | `exam_ratio` | float? | 낮을수록 | 시험 비중 (%) |
| Y | `homework_ratio` | float? | 낮을수록 | 과제 비중 (%) |
| Z | `attend_ratio` | float? | — | 출석 비중 (%) |
| coverage | `eval_coverage` | float | 높을수록 | 평가 정보가 있는 학점 비율 (%) |
| Q | `teamwork_courses` | int | 낮을수록 | 팀플 과목 수 |
| A_s | `strict_attendance` | int | 낮을수록 | 출석 엄격 과목 수 |
| W̄ | `avg_workload` | float? | 낮을수록 | 평균 과제 부담 (1–5) |
| K | `peak_load` | float | 낮을수록 | 가장 바쁜 주 부담 |
| K′ | `peak_load_regular` | float | 낮을수록 | 시험 기간 뺀 가장 바쁜 주 부담 |
| J | `crunch_weeks` | int | 낮을수록 | 몰리는 주 수 |

특징표에는 이 밖에 `tt_id`(str), `sections`(키 튜플), `shape_key`(같은 시간 모양 묶음 키, str), `group_size`(int) 열이 있다.

열을 추가할 때는 이 표, `kkul/timetable/analyzer.py`, `api/schemas.py`의 `FEATURE_COLUMNS`를 같은 PR에서 함께 고친다.

## 5. 모듈 사이 함수 약속

함수 이름·인자·반환형은 아래로 고정한다. 내부 구현은 담당자가 자유롭게 한다. 각 함수의 자세한 정의는 [01_backend_pipeline.md](01_backend_pipeline.md)의 해당 절.

```python
# kkul/io.py  (공동)
read_courses(term: str) -> dict[str, Course]
write_courses(term: str, courses: list[Course]) -> None
read_profiles(term: str) -> dict[str, dict]

# kkul/loader  (A부)
build(year: int, term: int, depts: list[str] | None = None) -> BuildReport

# kkul/timetable  (B부)
generate(courses: dict[str, Course], req: GenerateSpec) -> GenerateResult   # 1.5–4
build_table(timetables: list[Timetable], courses, buildings, cfg) -> pd.DataFrame
query(df: pd.DataFrame, filters: Filters, sort: list[SortKey], bins: dict[str, float], fold: bool) -> pd.DataFrame
count_if_relaxed(df, filters) -> dict[str, int]
details(tt: Timetable, courses, profiles, cfg) -> dict                     # 8.1–8.2

# kkul/strategy  (C부)
plan(target: Timetable, ranked: pd.DataFrame, comp: dict[str, Competition], cfg) -> StrategyResult
next_step(state: LiveState, ranked: pd.DataFrame, comp, cfg) -> NextStep

# kkul/llm.py  (공동 사용)
call_json(task: str, prompt: str, schema: type[BaseModel], timeout: float = 10) -> BaseModel | None
```

- `kkul/` 안의 함수는 **화면을 모른다**: NiceGUI·FastAPI를 import하지 않는다.
- `GenerateSpec`, `Filters`, `SortKey`, `Competition`, `StrategyResult`, `LiveState`, `NextStep`은 `kkul/models.py`에 dataclass로 둔다. API는 같은 이름의 pydantic 모델을 `api/schemas.py`에 두고 서로 변환한다.

## 6. API 약속 (`api/schemas.py`)

엔드포인트 목록은 [02_frontend_plan.md](02_frontend_plan.md)의 "API 목록"을 따른다. 공통 규칙:

| 항목 | 규칙 |
|---|---|
| 경로 | `/api/` 아래, 소문자, 복수형 명사 (`/api/timetables`) |
| 요청·응답 | JSON, pydantic 모델. 필드 이름은 snake_case, 4장의 열 이름과 같게 |
| 시각·요일·비율 | 1장 단위 그대로 (분, 0–5, 0–100) |
| 모르는 값 | `null` |
| 목록 응답 | `{"total": int, "items": [...]}` |
| 페이지 | `page` (1부터), `page_size` (기본 20, 최대 100) |
| 오류 | HTTP 상태 + 본문 `{"code": "TT_SET_NOT_FOUND", "message": "사용자에게 보여줄 한국어 문장", "detail": {...}}` |

오류 코드 (추가할 때 여기에 적는다):

| 코드 | HTTP | 뜻 |
|---|---|---|
| `DATA_NOT_BUILT` | 503 | 학기 데이터 없음 또는 스키마 버전 다름 |
| `COURSE_NOT_FOUND` | 404 | 없는 분반 키 |
| `TT_SET_NOT_FOUND` | 404 | 시간표 집합이 만료됨 → 다시 만들기 |
| `GEN_LIMIT` | 200 + `truncated: true` | 생성 상한 도달 (오류 아님, 경고) |
| `INVALID_FILTER` | 422 | 없는 열 이름이나 범위 오류 |
| `LLM_UNAVAILABLE` | 503 | 키 없음, 시간 초과 |
| `LLM_INVALID` | 502 | LLM 응답이 스키마·검증 실패 |

## 7. 설정값 (`kkul/config.py`)

기준값은 코드 곳곳에 숫자로 쓰지 않고 `Config` 한곳에서 가져온다.

```python
@dataclass(frozen=True)
class Config:
    # B부 시간표
    morning_cutoff: int = 540      # τ_m 9:00
    early_cutoff: int = 630        # τ_e 10:30
    gap_min: int = 60              # τ_g 연강 경계
    super_gap: int = 180           # τ_s 슈퍼공강
    lunch_window: tuple[int, int] = (690, 810)
    lunch_need: int = 45
    night_cutoff: int = 1080
    walk_speed: float = 70.0       # m/분
    hill_factor: float = 1.3
    gen_limit: int = 50_000
    gen_timeout_s: float = 2.0
    exam_weight: float = 2.0       # α
    deadline_weight: float = 1.0   # β
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
```

사용자가 화면에서 바꾸는 값(예: 슈퍼공강 기준)은 `dataclasses.replace(cfg, super_gap=150)`으로 새 `Config`를 만들어 넘긴다.

## 8. 환경 변수 (`.env`)

| 이름 | 필수 | 뜻 |
|---|---|---|
| `LLM_PROVIDER` | 아니오 | `anthropic` 또는 `openai` |
| `LLM_API_KEY` | 아니오 | 없으면 LLM 기능 숨김 |
| `LLM_MODEL` | 아니오 | 모델 이름 |
| `KKUL_TERM` | 예 | 앱이 읽을 학기, 예 `2026_20` |
| `KKUL_MOCK` | 아니오 | `1`이면 `api/mock.py` 사용 |
| `STORAGE_SECRET` | 예 | NiceGUI 사용자 저장소 암호화 키 |

`.env.example`에 이름만 적어 커밋하고, 실제 `.env`는 커밋하지 않는다.
