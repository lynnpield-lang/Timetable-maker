# 05. 개발 가이드

처음 저장소를 받은 날부터 발표 날까지, 실제로 손을 움직일 때 보는 문서다.

## 1. 처음 한 번 세팅

```bash
git clone https://github.com/lynnpield-lang/Timetable-maker.git
cd Timetable-maker
uv sync                      # pyproject.toml + uv.lock 대로 설치
cp .env.example .env         # 값 채우기 (03_interfaces.md 8장)
uv run pytest                # 전부 통과하면 준비 끝
```

- uv가 없으면: https://docs.astral.sh/uv/ 설치 안내를 따른다.
- VS Code 권장 확장: Python, Ruff. 저장할 때 자동 포맷을 켠다.

## 2. 자주 쓰는 명령

| 하고 싶은 것 | 명령 |
|---|---|
| 앱 실행 (실제 데이터) | `uv run python main.py` → http://localhost:8080 |
| 앱 실행 (목업) | `KKUL_MOCK=1 uv run python main.py` (Windows PowerShell: `$env:KKUL_MOCK=1; uv run python main.py`) |
| API 문서 보기 | 앱 실행 후 http://localhost:8080/docs |
| 학기 데이터 만들기 | `uv run python -m kkul.loader.build --year 2026 --term 20 --depts 316901` |
| 계획서 추출만 다시 | `uv run python -m kkul.loader.extract_syllabus --term 2026_20` |
| 테스트 | `uv run pytest` (하나만: `uv run pytest tests/test_features.py -k super_gap`) |
| 포맷·린트 | `uv run ruff format . && uv run ruff check .` |
| 패키지 추가 | `uv add <이름>` (개발용은 `uv add --dev <이름>`) → 단톡에 알리기 |

## 3. 하루 작업 흐름

```
git switch main && git pull
git switch -c feat/<할-일>
  … 코드 + 테스트 작성 …
uv run ruff format . && uv run ruff check . && uv run pytest
git add -p && git commit -m "feat(timetable): …"
git push -u origin feat/<할-일>
→ GitHub에서 PR 만들기 → 상대 리뷰 → squash merge
```

## 4. 주차별 체크리스트

상세 일정은 [01_backend_pipeline.md](01_backend_pipeline.md) "통합 일정", [02_frontend_plan.md](02_frontend_plan.md) "일정".

### 1주 (11/13–11/18): 뼈대와 약속
- [ ] 저장소 구조 만들기 (`kkul/`, `api/`, `ui/`, `tests/`, `data/`, `docs/`)
- [ ] `pyproject.toml` (ruff 설정 포함), `.gitignore`, `.env.example`, PR 템플릿
- [ ] **공동**: `kkul/models.py`, `kkul/config.py`, `kkul/io.py`, `api/schemas.py` 확정
- [ ] **공동**: `api/mock.py` (모든 service 함수의 가짜 버전)
- [ ] `tests/test_architecture.py` (import 규칙 검사)
- [ ] 이유찬: 남은 학교 요청 확인, 경영학과 하나로 `courses_2026_20.csv`, 화면 5개 뼈대(목업)
- [ ] 김지후: 비트마스크·백트래킹·특징 3.1–3.7, 경계값 테스트
- [ ] 주말 확인: 목업으로 화면 이동이 끝까지 되고, 실제 CSV로 시간표가 생성된다

### 2주 (11/19–11/25): 최소 버전
- [ ] 전체 학과 데이터 build, 계획서 PDF 수집
- [ ] 필터·정렬·수강 자격, `service.py` 실제 연결
- [ ] 시작·찾기 화면 완성, 단순 신청 순서
- [ ] 계획서 LLM 추출 (경영학과)
- [ ] 주말 확인: 실제 데이터로 **과목 담기 → 시간표 → 필터·정렬 → 신청 순서**

### 3주 (11/26–12/02): 핵심 기능
- [ ] 상세 보기, 학기 부담 특징, 계획서 추출 정확도 측정 (20개)
- [ ] 이항 성공 확률, 헝가리안 순서, 손실, 플랜 B 트리, 시뮬레이션
- [ ] 전략 화면 ①②, 캡처 입력
- [ ] 주말 확인: 상세 보기·플랜 B·정책 비교가 실제 데이터로 나온다

### 4주 (12/03–12/10): 마무리 (12/10 구현 마감)
- [ ] 동선, 종합 코멘트, 민감도, 대기 판단, 실시간 모드
- [ ] 오류·빈 상태 점검 (6장)
- [ ] README 최신화, 스크린샷
- [ ] 코드 정리: 안 쓰는 코드 삭제, ruff 경고 0

### 발표 주 (12/11–12/17)
- [ ] 시연 시나리오 확정 (8장), 리허설 2회 이상
- [ ] 시연 영상 녹화 (네트워크 문제 대비)

## 5. 개발 팁

### 목업 우선
화면 작업은 `KKUL_MOCK=1`로 시작한다. `mock.py`는 `api/schemas.py`의 모델을 그대로 돌려주므로, 백엔드가 없어도 화면이 끝까지 돌아간다. 실제 연결은 `service.py`만 바꾸면 된다.

### 작은 테스트 데이터
`tests/fixtures/courses_test.csv`에 10과목 정도를 손으로 만들어 둔다. 경계값(9:00 시작, 정확히 180분 공강, 15분 쉬는 시간, 다른 건물 연강, 온라인 과목, 평가 비율 없음)을 일부러 넣는다. 대부분의 테스트는 이 파일로 돌린다.

### 학교 응답 다루기
- SSV 응답은 레코드 구분 `\x1e`, 칸 구분 `\x1f`. 디버깅할 때는 `text.replace("\x1e", "\n").replace("\x1f", " | ")`로 보면 읽기 쉽다.
- 요청이 503이면 헤더(User-Agent, Referer, Origin)를 먼저 확인한다 (`skku_fetch.py` v2 참고).
- 원문은 `data/raw/`에 캐시되므로 파싱 코드를 고칠 때는 서버에 다시 요청하지 말고 캐시로 반복한다.

### NiceGUI
- `ui.run(reload=True)`로 코드 저장 시 자동 새로고침.
- 무거운 계산은 `await run.cpu_bound(함수, 인자)`. 이 함수는 모듈 최상위 함수여야 하고, 인자·반환값이 pickle 가능해야 한다 (DataFrame은 가능, 람다는 불가).
- 슬라이더 연속 호출은 짧은 지연(0.3초) 뒤 한 번만 `query`를 부르도록 묶는다.

### LLM
- 프롬프트는 `kkul/prompts/<작업>.md` 파일로 따로 두고 버전을 남긴다 (코드 안 긴 문자열 금지).
- 개발 중에는 같은 입력의 응답을 `data/raw/llm_cache/`에 저장해 재사용한다 (비용·시간 절약, 커밋 안 함).
- 정확도 측정용 정답 20개는 `tests/fixtures/syllabus_gold.jsonl`.

### 성능 확인
`uv run python -m kkul.timetable.bench --courses 6 8`처럼 과목 수별 생성 시간을 재는 작은 스크립트를 둔다. 목표는 6–8과목 2초 이내.

## 6. 출시 전 점검 (오류·빈 상태)

| 상황 | 기대 동작 | 확인 |
|---|---|---|
| `.env`에 LLM 키 없음 | LLM 버튼이 숨겨지고 나머지 정상 | [ ] |
| 데이터 파일 없음 / 스키마 버전 다름 | "데이터를 다시 build하세요" 안내 | [ ] |
| 담은 과목이 0개 | [시간표 만들기] 비활성 | [ ] |
| 결과 0개 | 완화 제안 버튼 | [ ] |
| 생성 상한 도달 | 경고와 함께 일부 결과 | [ ] |
| 계획서 정보 없는 과목 | 카드 칸 비우고 "정보 없음" | [ ] |
| 캡처 읽기 실패 | 직접 입력 표 | [ ] |
| 서버 재시작 후 이전 시간표 열기 | "다시 만들기" 버튼 | [ ] |
| 휴대폰 폭에서 실시간 모드 | 버튼이 화면 안 | [ ] |

## 7. 위험과 대응

| 위험 | 가능성 | 대응 |
|---|---|---|
| 학교 서버가 스크립트 요청을 막음 | 중 | 이미 받은 원문 캐시로 개발 계속. 최후에는 Playwright로 공개 페이지 열어 받기, 그래도 안 되면 학과 일부를 수동 정리 |
| 수강 대상·전공 인정 필드 의미가 추정과 다름 | 중 | 확정 전까지 전공 인정 필드로는 제외하지 않음 (표시만) |
| PDF 계획서 추출 정확도 낮음 | 중 | 근거 인용 검증으로 틀린 값은 버림. 정확도 수치를 그대로 발표 |
| 조합 폭발로 생성이 느림 | 중 | 꼭 지킬 조건 먼저 거르기, 같은 시간 묶기, 가지치기, 상한 |
| 일정 지연 (특히 3주차 김지후) | 높음 | 우선순위: 최소 버전 > 상세 보기 > 플랜 B > 시뮬레이션 > 동선 > 종합 코멘트. 뒤에서부터 뺀다 |
| 인터페이스 불일치로 통합 실패 | 중 | 1주차 공동 파일 확정, 목업, 같은 pydantic 모델로 검증하는 테스트 |
| LLM 비용·속도 | 낮음 | build 때 한 번만, 결과 캐시, 화면에서는 버튼 눌렀을 때만 |
| 발표 당일 네트워크 문제 | 중 | 데이터는 미리 build해 커밋. LLM 결과도 캐시. 시연 영상 준비 |

## 8. 발표 시연 시나리오 (초안, 7–8분)

1. **문제** (30초): 수강신청 전 시간표 짜기의 불편함
2. **데이터** (1분): 공개 전자시간표·계획서 PDF를 로그인 없이 수집, LLM이 계획서를 구조화 + 근거 인용 검증, 정확도 수치
3. **시간표 찾기** (2분): 과목 담기 → 시간표 수백 개 → "금요일 쉬고 팀플 싫어" 입력 → 필터·정렬 → 남는 개수 변화
4. **상세 보기** (1분): 과목 카드, 학기 부담 그래프, 몰리는 주 경고
5. **수강신청 전략** (2분): 신청 순서(할당 문제), 플랜 B 트리, 정책 비교 시뮬레이션 결과
6. **설계** (1분): 백엔드·API·화면 분리, `/docs` API 문서, 역할 분담과 인터페이스 약속
7. **한계와 다음 단계** (30초): 경쟁률 가정값, 데이터 범위

시연은 미리 정한 과목 5개로 한다. 화면이 멈출 경우를 대비해 같은 흐름의 녹화 영상을 준비한다.

## 9. 참고 자료

- NiceGUI 문서: https://nicegui.io/documentation
- FastAPI 문서: https://fastapi.tiangolo.com/
- pydantic 문서: https://docs.pydantic.dev/
- uv 문서: https://docs.astral.sh/uv/
- SciPy `linear_sum_assignment`(헝가리안), `binom`(이항분포): https://docs.scipy.org/doc/scipy/reference/
- 기존 테스트 스크립트: `scripts/skku_fetch.py`(과목 목록), `scripts/syllabus_fetch.py`(계획서 PDF)
