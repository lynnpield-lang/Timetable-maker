"""앱 실행: uv run python main.py → http://localhost:8080 (API 문서 /docs).

화면은 저장소의 frontend/ui/ (NiceGUI, 이유찬 담당). 같은 프로세스에서 api.service를
바로 부르는 구조라, frontend/가 있으면 _mount_ui가 경로에 넣고 화면을 붙인다.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from api import routes, service
from api.backend import use_mock

log = logging.getLogger("kkul")
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


def create_app() -> FastAPI:
    """FastAPI 앱 (.env를 읽고 학기·목업 설정)."""
    load_dotenv()
    mock = os.environ.get("KKUL_MOCK", "0") == "1"
    use_mock(mock)
    if not mock:
        service.configure(os.environ.get("KKUL_TERM"))
    app = FastAPI(
        title="꿀시간표 API", version="0.1.0", description="시간표 생성·탐색·수강신청 전략"
    )
    routes.register(app)
    return app


def _mount_ui(app: FastAPI) -> bool:
    if FRONTEND_DIR.is_dir() and str(FRONTEND_DIR) not in sys.path:
        sys.path.insert(0, str(FRONTEND_DIR))
    try:
        import ui.layout  # noqa: F401  (ui/ 패키지가 페이지를 등록한다)
        from nicegui import ui as ng
    except ImportError:
        return False
    secret = os.environ.get("STORAGE_SECRET") or ""
    ng.run_with(app, storage_secret=secret)
    return True


app = create_app()

if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    if not _mount_ui(app):
        log.info("frontend/ui/가 아직 없어 API만 실행합니다: http://localhost:8080/docs")
    uvicorn.run(app, host="0.0.0.0", port=8080)
