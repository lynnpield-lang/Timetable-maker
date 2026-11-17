# backend

꿀시간표의 계산(`kkul/`)과 API(`api/`). 화면은 [`../frontend`](../frontend), 설계는 [`../docs`](../docs)에 있다.

```bash
cd backend
uv sync
cp .env.example .env              # KKUL_TERM, STORAGE_SECRET. LLM 키는 선택
KKUL_MOCK=1 uv run python main.py # 목업 데이터로 실행 → http://localhost:8080/docs
uv run pytest                     # 테스트
uv run ruff check . && uv run ruff format --check .
```

실제 데이터 만들기 (학교 서버에 학기당 한 번):

```bash
uv run python -m kkul.loader.build --help
```

| 폴더 | 내용 |
|---|---|
| `kkul/loader/` | A. 학교 공개 전자시간표·계획서 수집과 정리 |
| `kkul/timetable/` | B. 시간표 생성·특징표·필터·정렬·상세 |
| `kkul/strategy/` | C. 경쟁률·성공 확률·신청 순서·플랜 B·시뮬레이션 |
| `kkul/` (나머지) | `models` `config` `io` `llm` `capture` `preferences` `prompts/` |
| `api/` | `schemas`(약속) `service` `routes` `store` `mock` `backend` |
| `data/` | `buildings.csv` `dept_alias.csv`, 빌드 결과 `courses_*.csv` `profiles_*.jsonl` `meta_*.json` |
| `tests/` | pytest, `fixtures/` (목업 데이터) |

import 방향은 `ui → api → kkul` 한 방향만 ([04_conventions.md](../docs/04_conventions.md) 2장, `tests/test_architecture.py`가 검사).

## 아직 확인이 필요한 것

- `kkul/loader/skku_client.py`의 `BASE_URL`·`PATHS`와 `kkul/loader/normalize.py`의 `FIELD_MAP` 중 ⚠ 표시: 실제 요청을 캡처해 맞춰야 한다.
- LLM 실제 호출 (키를 넣고 계획서 추출·요약·설명 확인).
- `kkul/config.py`의 경쟁률 추정 계수(`estimate_r0`, `estimate_beta`)는 임시값.
- `data/buildings.csv`는 한 줄뿐이다.
