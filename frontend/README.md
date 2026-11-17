# frontend

꿀시간표 화면 (NiceGUI). 담당 이유찬. 설계는 [docs/02_frontend_plan.md](../docs/02_frontend_plan.md).

아직 비어 있다. 화면 코드는 이 폴더 안의 `ui/` 패키지로 만든다.

```
frontend/
└ ui/
  ├ __init__.py
  ├ layout.py      # 페이지 등록 (backend/main.py가 import ui.layout 으로 붙인다)
  ├ pages/         # 시작·찾기·상세·전략·실시간 모드
  └ components/
```

## 규칙

- `ui/`는 `api.service`, `api.schemas`, `api.backend`만 import한다. `kkul`은 직접 쓰지 않는다 (`backend/tests/test_architecture.py`가 검사).
- 실행은 백엔드와 한 프로세스다: `cd backend && uv run python main.py` 하면 `frontend/`를 경로에 넣고 `ui.layout`을 불러 NiceGUI를 붙인다.
- NiceGUI 등 의존성은 `backend/pyproject.toml`에 `uv add nicegui`로 추가한다 (한 가상환경을 같이 쓴다).
- 백엔드 없이 화면만 만들 때는 `KKUL_MOCK=1`로 실행하면 `backend/tests/fixtures`의 목업 데이터가 나온다.
