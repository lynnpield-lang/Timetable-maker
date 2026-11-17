# 04. 협업 규칙과 제약조건

두 사람이 나눠 작업해도 프로그램이 한 번에 맞물리게 하는 규칙이다. **지키지 않으면 PR을 합치지 않는다.**

## 1. 역할과 파일 소유권

| 영역 | 주인 | 리뷰 | 파일 |
|---|---|---|---|
| A부 데이터 수집 | 이유찬 | 김지후 | `kkul/loader/skku_client.py`, `ssv.py`, `normalize.py`, `syllabus.py`, `build.py` |
| A부 LLM 추출 | 김지후 | 이유찬 | `kkul/loader/extract_syllabus.py`, `kkul/capture.py` |
| B부 시간표 | 김지후 | 이유찬 | `kkul/timetable/*` |
| C부 전략 (확률·순서·화면 연결) | 이유찬 | 김지후 | `kkul/strategy/probability.py`, `order.py` |
| C부 전략 (손실·트리·시뮬레이션·설명) | 김지후 | 이유찬 | `kkul/strategy/fallback.py`, `simulate.py`, `waitlist.py`, `explain.py` |
| API | 김지후 | 이유찬 | `api/service.py`, `api/routes.py`, `api/store.py` |
| 화면 | 이유찬 | 김지후 | `ui/**`, `main.py` |
| **공동 소유 (합의 필수)** | 둘 다 | 둘 다 | `kkul/models.py`, `kkul/config.py`, `kkul/io.py`, `kkul/llm.py`, `api/schemas.py`, `api/mock.py`, `docs/03_interfaces.md`, `pyproject.toml` |

- 남의 파일은 고치지 않는다. 필요하면 이슈나 메시지로 요청하거나, 고친 PR을 올리고 주인에게 리뷰를 받는다.
- 공동 소유 파일은 혼자 바꾸지 않는다 (3장 절차).

## 2. 층 구조 규칙 (import 방향)

```
ui/  →  api/  →  kkul/
```

| 규칙 | 이유 |
|---|---|
| `ui/`는 `api/service.py`와 `api/schemas.py`만 import한다 | 화면을 바꿔도 백엔드가 그대로 |
| `api/`만 `kkul/`을 import한다 | 변환 지점을 한곳으로 |
| `kkul/`은 `nicegui`, `fastapi`, `api`, `ui`를 import하지 않는다 | 계산 코드는 화면 없이 테스트 가능해야 함 |
| 네트워크 접속은 `kkul/loader/skku_client.py`, `kkul/loader/syllabus.py`, `kkul/llm.py`에서만 | 학교 서버·LLM 호출을 한곳에서 관리 |
| 파일 읽기·쓰기는 `kkul/io.py`와 `kkul/loader/`에서만 | 형식 통일 |
| `kkul/timetable/`, `kkul/strategy/`의 함수는 순수 함수 (같은 입력 → 같은 출력, 전역 상태 없음) | 테스트·캐시 가능 |

`tests/test_architecture.py`가 위 import 규칙을 검사한다 (파일을 읽어 금지된 import가 있으면 실패).

## 3. 인터페이스 변경 절차

[03_interfaces.md](03_interfaces.md)에 있는 것(파일 열, 자료형, 함수 이름·인자, API 스키마, 특징 열 이름, 오류 코드, 설정값 이름)을 바꿀 때:

1. 이슈를 열고 무엇을 왜 바꾸는지 적는다. 제목 앞에 `[인터페이스]`
2. 상대가 확인(댓글 "OK")한 뒤 작업한다.
3. **한 PR 안에서 함께 고친다**: `03_interfaces.md` + `models.py`/`schemas.py` + `mock.py` + 영향받는 테스트
4. 파일 형식이 바뀌면 `Config.schema_version`을 1 올리고 데이터를 다시 build한다.
5. 합친 뒤 단톡에 한 줄 알린다: "`free_day_set` 형식 str → list로 바뀜, pull 하세요"

이름만 바꾸는 것도 인터페이스 변경이다.

## 4. Git 규칙

### 브랜치
- `main`: 항상 실행되는 상태. 직접 push 금지, PR로만 합친다.
- 작업 브랜치: `<종류>/<짧은-설명>`. 종류는 `feat`, `fix`, `docs`, `refactor`, `test`, `data`
  - 예: `feat/filter-panel`, `fix/ssv-empty-row`, `data/2026-20-build`
- 브랜치는 짧게 (1–3일). 길어지면 중간에 나눠 합친다.

### 커밋 메시지
```
<종류>(<영역>): <무엇을 했는지, 한국어 한 줄>

(필요하면 본문: 왜 바꿨는지)
```
- 영역: `loader`, `timetable`, `strategy`, `api`, `ui`, `docs`, `data`, `config`
- 예: `feat(timetable): 슈퍼공강 횟수 특징 추가`, `fix(loader): 강의실 미지정 처리`

### PR
- 제목은 커밋 메시지 형식과 같게.
- 본문 체크리스트 (PR 템플릿으로 고정):
  - [ ] `uv run ruff check .` 통과
  - [ ] `uv run pytest` 통과
  - [ ] 인터페이스를 바꿨다면 3장 절차를 지켰다
  - [ ] 화면을 바꿨다면 스크린샷 첨부
  - [ ] `.env`, `data/raw/`, 캡처 이미지가 포함되지 않았다
- 상대가 **24시간 안에** 리뷰한다. 급하면 단톡에 알린다.
- 리뷰 후 PR 작성자가 직접 합친다 (squash merge).
- 충돌은 PR 작성자가 `main`을 받아 해결한다.

### 이슈 라벨
`A-data`, `B-timetable`, `C-strategy`, `api`, `ui`, `인터페이스`, `버그`, `질문`, `발표`

## 5. 코드 규칙

| 항목 | 규칙 |
|---|---|
| Python | 3.11 이상, 의존성은 `uv add`로만 추가하고 `pyproject.toml`·`uv.lock`을 같이 커밋 |
| 포맷·린트 | `ruff format`, `ruff check` (설정은 `pyproject.toml`, 줄 길이 100) |
| 이름 | 함수·변수 `snake_case`, 클래스 `PascalCase`, 상수 `UPPER_CASE`, 파일 `snake_case.py` |
| 타입 | 다른 모듈에서 쓰는 함수는 인자·반환 타입 표시 필수 |
| 주석·docstring | 한국어 가능. 공개 함수는 한 줄 docstring으로 무엇을 하는지 |
| 숫자 상수 | 기준값은 `Config`에서. 코드에 `180`, `540` 같은 숫자를 직접 쓰지 않는다 |
| 출력 | `print` 금지 (스크립트 제외). `logging.getLogger(__name__)` 사용 |
| 시간 | 시각은 1장 단위(분)로만 다룬다. `datetime`은 화면 표시 직전에만 |
| 랜덤 | 시뮬레이션은 `numpy.random.default_rng(cfg.seed)`만 사용 |
| 예외 | `kkul/errors.py`의 `KkulError` 하위 클래스로 던지고, `api/service.py`가 6장 오류 형식으로 바꾼다. 화면에 파이썬 오류 메시지를 그대로 보이지 않는다 |
| 비밀값 | 코드·로그·커밋에 키를 쓰지 않는다. `os.environ`은 `kkul/llm.py`, `main.py`에서만 읽는다 |

## 6. 데이터·외부 서비스 규칙

| 규칙 | 내용 |
|---|---|
| 학교 서버 | 로그인 없는 공개 화면의 요청만 사용. 요청 사이 1초 이상, 같은 요청은 캐시에서. build 때만 접속하고 앱 실행 중에는 접속하지 않는다 |
| 로그인 사이트 | GLS, 에브리타임 등 로그인이 필요한 사이트에 프로그램이 접속하지 않는다. 비밀번호를 받지 않는다 |
| 자동 신청 금지 | 수강신청을 자동으로 하는 기능을 만들지 않는다 (학교 규정의 매크로 제한). 실시간 모드는 안내만 |
| 개인정보 | 수업계획서 응답의 교수 연락처(전화·이메일)는 저장하지 않는다. 사용자 캡처는 서버 메모리에만 두고 파일로 남기지 않는다 |
| 원문 | 계획서 PDF 원본은 커밋하지 않는다. 뽑은 항목과 짧은 근거 인용만 저장 |
| LLM | 숫자는 코드가 계산하고 LLM은 추출·판단·설명만. 응답은 반드시 `call_json`으로 스키마 검증. 실패하면 LLM 없이 동작 |
| 커밋 금지 | `.env`, `data/raw/`, `*.pdf`, 캡처 이미지, `__pycache__`, `.venv` (`.gitignore`에 넣음) |

## 7. 테스트 규칙

- `tests/`에 모듈별 파일: `test_ssv.py`, `test_normalize.py`, `test_features.py`, `test_generate.py`, `test_query.py`, `test_strategy.py`, `test_api.py`, `test_architecture.py`
- 테스트용 작은 데이터는 `tests/fixtures/`에 둔다 (예: 손으로 만든 10과목짜리 `courses_test.csv`, SSV 응답 샘플). 실제 학교 서버·LLM을 부르는 테스트는 만들지 않는다 (가짜 응답으로 대체).
- 새 함수를 합칠 때는 테스트 1개 이상. 버그를 고치면 그 버그를 다시 잡는 테스트를 추가.
- `main`에 합치기 전 `uv run pytest` 전체 통과. (여유가 있으면 GitHub Actions로 PR마다 자동 실행)

## 8. 소통 규칙

| 언제 | 무엇 |
|---|---|
| 매일 (단톡, 3줄) | 어제 한 것 / 오늘 할 것 / 막힌 것 |
| 주 2회 (짧은 회의 15분) | 일정 확인, 인터페이스 변경 논의, 다음 주 목표 |
| 막혔을 때 | 2시간 넘게 막히면 바로 공유 |
| 인터페이스·공동 파일 | 반드시 이슈로 남김 (말로만 정하지 않기) |

## 9. 완료 기준 (Definition of Done)

기능 하나가 "끝났다"는 것은:

1. 코드가 `main`에 합쳐졌다
2. 테스트가 있고 통과한다
3. 목업이 아닌 실제 데이터로 화면에서 한 번 이상 동작을 확인했다
4. 관련 문서(`03_interfaces.md`, README의 기능 목록)가 최신이다
5. 오류·빈 상태(데이터 없음, LLM 키 없음)에서 앱이 멈추지 않는다
