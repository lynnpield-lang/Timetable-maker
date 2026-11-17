"""service 함수를 REST로 공개: /api/... (자동 문서 /docs)."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from api import schemas as S
from api.backend import backend
from kkul.errors import KkulError

router = APIRouter(prefix="/api")


@router.get("/meta", response_model=S.MetaOut)
def meta():
    return backend().get_meta()


@router.get("/courses", response_model=S.Page[S.CourseSummary])
def courses(
    q: str | None = None,
    dept: str | None = None,
    category: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    return backend().list_courses(q, dept, category, page, page_size)


@router.get("/courses/{key}", response_model=S.CourseSummary)
def course(key: str):
    return backend().get_course(key)


@router.post("/timetables/generate", response_model=S.GenerateOut)
def generate(req: S.GenerateRequest):
    return backend().generate_timetables(req)


@router.post("/timetables/{set_id}/query", response_model=S.QueryOut)
def query(set_id: str, req: S.QueryRequest):
    return backend().query_timetables(set_id, req)


@router.get("/timetables/{set_id}/{tt_id}", response_model=S.TimetableDetail)
def detail(set_id: str, tt_id: str):
    return backend().timetable_detail(set_id, tt_id)


@router.get("/timetables/{set_id}/{tt_id}/similar", response_model=S.SimilarOut)
def similar(set_id: str, tt_id: str):
    return backend().similar_timetables(set_id, tt_id)


@router.post("/timetables/{set_id}/{tt_id}/summary", response_model=S.TextOut)
def summary(set_id: str, tt_id: str):
    return backend().summarize_timetable(set_id, tt_id)


@router.post("/preferences/parse", response_model=S.PreferencesOut)
def parse_preferences(req: S.TextIn):
    return backend().parse_preferences(req.text)


@router.post("/capture", response_model=S.CaptureOut)
async def capture(
    images: list[UploadFile] = File(default_factory=list),
    text: str | None = Form(default=None),
):
    data = [(await f.read(), f.content_type or "image/png") for f in images]
    return backend().read_capture(data, text)


@router.put("/competition/{set_id}", response_model=S.SavedOut)
def competition(set_id: str, req: S.CompetitionIn):
    return backend().save_competition(set_id, req)


@router.post("/strategy/{set_id}/next", response_model=S.NextOut)
def next_step(set_id: str, req: S.NextRequest):
    return backend().next_step(set_id, req)


@router.post("/strategy/{set_id}/{tt_id}", response_model=S.StrategyOut)
def strategy(set_id: str, tt_id: str, req: S.StrategyRequest | None = None):
    return backend().get_strategy(set_id, tt_id, req)


@router.post("/strategy/{set_id}/{tt_id}/explain", response_model=S.ExplainOut)
def explain(set_id: str, tt_id: str):
    return backend().explain_strategy(set_id, tt_id)


def register(app: FastAPI) -> None:
    """라우트와 오류 처리기를 앱에 붙인다."""
    from api.service import error_body

    @app.exception_handler(KkulError)
    async def _kkul_error(_: Request, e: KkulError):
        return JSONResponse(status_code=e.http_status, content=error_body(e).model_dump())

    app.include_router(router)
