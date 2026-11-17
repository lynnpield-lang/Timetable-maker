# 꿀시간표 (Timetable-maker)

성균관대 공개 강의 데이터로 **조건에 맞는 시간표를 만들어 고르게 하고, 고른 시간표의 수강신청 순서와 플랜 B까지 짜 주는** 웹앱.

공컴프 기말 팀 프로젝트 · 팀 **꿀 시간표** · 김지후, 이유찬

> 상태: 개발 중 (구현 기간 2026-11-12 ~ 12-10, 기말 발표 12-17)

## 무엇을 하나

| 단계 | 기능 |
|---|---|
| 과목 담기 | 학과·복수전공을 고르고 듣고 싶은 과목을 담는다. 수강 대상이 아닌 분반은 자동으로 빠지고, 전공 인정 여부와 평가 비율이 함께 보인다 |
| 시간표 찾기 | 겹치지 않는 시간표를 전부 만든 뒤, 9시 수업·슈퍼공강·우주공강·연강·동선·팀플·학기 중 몰리는 주 같은 조건으로 거르고 원하는 우선순위로 정렬한다. "금요일 쉬고 팀플은 싫어"처럼 말로 조건을 줄 수도 있다 |
| 상세 보기 | 고른 시간표의 과목별 강의 스타일·시험·과제·출석 규정(수업계획서에서 자동 추출, 원문 근거 포함)과 주차별 학기 부담 그래프 |
| 수강신청 전략 | 경쟁률(사용자 캡처 또는 추정)로 분반별 성공 확률을 계산하고, 신청 순서·실패 시 플랜 B 트리·성공 확률 시뮬레이션을 보여준다 |
| 실시간 모드 | 수강신청 당일 성공/실패만 누르면 다음에 신청할 학수번호를 알려준다 (자동 신청은 하지 않음) |

## 구조

```
┌ frontend/ui/ (화면)┐     ┌ backend/api/ (FastAPI)    ┐     ┌ backend/kkul/ (계산) ────────┐
│ 시작·찾기·상세·     │ ──▶ │ service: 화면과 REST 공용  │ ──▶ │ loader/   A. 데이터 수집·정리   │
│ 전략·실시간 모드    │     │ routes:  /api/... , /docs  │     │ timetable/ B. 시간표 생성·탐색 │
└────────────────────┘     └───────────────────────────┘     │ strategy/  C. 수강신청 전략    │
                                                              └──────────────────────────────┘
        학교 공개 전자시간표 ─(학기당 1회 build)─▶ backend/data/courses_<학기>.csv, profiles_<학기>.jsonl
```

- 전부 Python (NiceGUI 화면, FastAPI API, pandas·NumPy·SciPy 계산)
- 숫자는 코드가 계산하고, LLM은 계획서 구조화·캡처 읽기·자연어 조건 해석·설명에만 쓴다. LLM 결과는 스키마와 원문 근거로 검증한다.

## 빠른 시작

```bash
git clone https://github.com/lynnpield-lang/Timetable-maker.git
cd Timetable-maker/backend
uv sync
cp .env.example .env          # KKUL_TERM, STORAGE_SECRET 필수. LLM 키는 선택
uv run python main.py         # http://localhost:8080 , API 문서는 /docs
```

데이터가 아직 없으면 먼저 만든다 (학교 서버에 학기당 한 번만, `backend/`에서):

```bash
uv run python -m kkul.loader.build --year 2026 --term 20 --depts 316901
```

목업 데이터로 화면만 보려면 `KKUL_MOCK=1 uv run python main.py`.

## 환경 변수

| 이름 | 필수 | 설명 |
|---|---|---|
| `KKUL_TERM` | ✅ | 사용할 학기, 예 `2026_20` |
| `STORAGE_SECRET` | ✅ | 사용자 저장소 암호화 키 (아무 긴 문자열) |
| `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL` | | 없으면 LLM 기능만 꺼진다 |
| `KKUL_MOCK` | | `1`이면 목업 데이터 |

## 폴더

계획(문서)과 실제 코드를 나누고, 코드는 백엔드와 프론트엔드로 나눈다.

```
docs/                 계획·설계 문서 (00 기획서 ~ 05 개발 가이드)
backend/              백엔드 (Python 프로젝트: pyproject.toml, uv.lock, .env.example)
  kkul/               계산 (화면 없음): loader/ timetable/ strategy/ + models·config·io·llm
  api/                schemas(약속) · service · routes · mock · store
  data/               buildings.csv, dept_alias.csv, 빌드 결과 courses_*.csv 등
  tests/              pytest, fixtures/
  main.py             앱 실행 (frontend/ui가 있으면 같이 띄운다)
frontend/             프론트엔드 (NiceGUI)
  ui/                 pages/ components/ layout  ← 아직 비어 있음
```

자세한 내용은 [backend/README.md](backend/README.md), [frontend/README.md](frontend/README.md).

## 문서

| 문서 | 내용 |
|---|---|
| [docs/00_team_plan.md](docs/00_team_plan.md) | 11/11 제출 기획서 (원본) |
| [docs/01_backend_pipeline.md](docs/01_backend_pipeline.md) | 백엔드 전체 파이프라인: A 데이터 · B 시간표 · C 전략, 수학적 정의와 알고리즘 |
| [docs/02_frontend_plan.md](docs/02_frontend_plan.md) | 프론트엔드: NiceGUI 화면 5개, 컴포넌트, API 목록, 상태 관리 |
| [docs/03_interfaces.md](docs/03_interfaces.md) | **인터페이스 명세**: 단위, 파일 형식, 자료형, 특징 열 이름, 함수·API 약속, 설정값 |
| [docs/04_conventions.md](docs/04_conventions.md) | **협업 규칙**: 파일 소유권, import 방향, 변경 절차, Git, 코드·데이터·테스트 규칙 |
| [docs/05_dev_guide.md](docs/05_dev_guide.md) | 개발 가이드: 세팅, 명령, 주차별 체크리스트, 팁, 위험 대응, 시연 시나리오 |

## 역할

| 이름 | 맡은 부분 |
|---|---|
| 김지후 | 시간표 생성·탐색 알고리즘, 계획서 LLM 추출, 전략(손실·플랜 B·시뮬레이션·설명), API 연결, 발표 자료 |
| 이유찬 | 학교 데이터 수집·정리, 화면(NiceGUI) 전체, 전략(경쟁률·성공 확률·신청 순서), README·시연 영상 |

공동 (`backend/` 아래): `kkul/models.py`, `kkul/config.py`, `kkul/io.py`, `kkul/llm.py`, `api/schemas.py`, `api/mock.py` (자세히는 [협업 규칙](docs/04_conventions.md))

## 데이터와 이용 원칙

- 성균관대 전자시간표·수업계획서 중 **로그인 없이 공개된 정보**만, 학기당 한 번, 요청 사이 1초 이상 간격으로 수집한다.
- 로그인이 필요한 사이트(GLS, 에브리타임)에는 접속하지 않으며 비밀번호를 받지 않는다. 정원·신청 인원은 사용자가 직접 캡처해 올린다.
- 수강신청 자동화(매크로)는 만들지 않는다.
- 수업계획서 원본과 교수 연락처는 저장하지 않는다.

## 한계

- 경쟁률이 캡처 또는 추정값이고, 성공 확률 모델(신청 시각 분포 등)은 가정에 기반한다. 확률은 전략끼리 비교하는 지표로 본다.
- 1차 데이터 범위는 일부 학과와 교양이다.
- 학교 시스템이 바뀌면 수집 코드(`backend/kkul/loader/`)를 고쳐야 한다.
