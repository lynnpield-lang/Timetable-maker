"""목업 service: 같은 함수 이름·같은 반환 형식 (KKUL_MOCK=1).

tests/fixtures의 작은 데이터(14개 분반)로 실제 계산을 돌리고, LLM이 필요한 함수는 정해진 답을 돌려준다.
그래서 LLM 키나 학기 데이터 없이도 화면이 끝까지 돌아간다.
"""

from __future__ import annotations

from pathlib import Path

from api import schemas as S
from api import service

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
MOCK_TERM = "test"
_ready = False


def _ensure() -> None:
    global _ready
    if not _ready:
        service.configure(MOCK_TERM, data_dir=str(FIXTURE_DIR), mock=True)
        _ready = True


def error_body(e):
    return service.error_body(e)


def get_meta() -> S.MetaOut:
    _ensure()
    return service.get_meta()


def list_courses(q=None, dept=None, category=None, page=1, page_size=20):
    _ensure()
    return service.list_courses(q, dept, category, page, page_size)


def get_course(key: str) -> S.CourseSummary:
    _ensure()
    return service.get_course(key)


def generate_timetables(req: S.GenerateRequest) -> S.GenerateOut:
    _ensure()
    return service.generate_timetables(req)


def query_timetables(set_id: str, req: S.QueryRequest) -> S.QueryOut:
    _ensure()
    return service.query_timetables(set_id, req)


def similar_timetables(set_id: str, tt_id: str) -> S.SimilarOut:
    _ensure()
    return service.similar_timetables(set_id, tt_id)


def timetable_detail(set_id: str, tt_id: str) -> S.TimetableDetail:
    _ensure()
    return service.timetable_detail(set_id, tt_id)


def summarize_timetable(set_id: str, tt_id: str) -> S.TextOut:
    _ensure()
    det = service.timetable_detail(set_id, tt_id)
    busy = det.summary.crunch_weeks
    when = (
        f"{busy[0].week}주차에 일정이 몰려 있어요." if busy else "학기 중 크게 몰리는 주는 없어요."
    )
    return S.TextOut(text=f"(목업) {len(det.cards)}과목 시간표예요. {when}")


def parse_preferences(text: str) -> S.PreferencesOut:
    _ensure()
    filters: dict[str, list[float | None]] = {}
    free: list[int] = []
    unclear: list[str] = []
    if "금" in text:
        free.append(4)
    if "팀플" in text:
        filters["teamwork_courses"] = [None, 0]
    if "아침" in text or "9시" in text:
        filters["morning_days"] = [None, 0]
    if not (free or filters):
        unclear.append(text)
    return S.PreferencesOut(
        filters=filters, free_days=free, sort=[["super_gaps", 1]], unclear=unclear
    )


def read_capture(images, text=None) -> S.CaptureOut:
    _ensure()
    if text:
        return service.read_capture([], text)
    rows = [
        S.CaptureRowOut(key="BIZ2006-01", capacity=40, applied=84, ok=True),
        S.CaptureRowOut(key="BIZ2021-01", capacity=45, applied=50, ok=True),
        S.CaptureRowOut(
            key="XYZ9999-01", capacity=30, applied=10, ok=False, issue="없는 분반이에요"
        ),
    ]
    return S.CaptureOut(rows=rows)


def save_competition(set_id: str, req: S.CompetitionIn) -> S.SavedOut:
    _ensure()
    return service.save_competition(set_id, req)


def get_strategy(set_id: str, tt_id: str, req: S.StrategyRequest | None = None) -> S.StrategyOut:
    _ensure()
    req = req or S.StrategyRequest(sim_runs=1000, sensitivity=False)
    return service.get_strategy(set_id, tt_id, req)


def explain_strategy(set_id: str, tt_id: str) -> S.ExplainOut:
    _ensure()
    st = get_strategy(set_id, tt_id)
    first = st.order[0].key if st.order else "-"
    return S.ExplainOut(
        summary=f"(목업) {first}부터 신청하세요.",
        per_course=[S.PerCourseOut(key=o.key, reason=", ".join(o.tags)) for o in st.order],
        warnings=["대기순번을 받은 과목을 다시 신청하면 대기순번이 사라져요."],
        source="mock",
    )


def next_step(set_id: str, req: S.NextRequest) -> S.NextOut:
    _ensure()
    return service.next_step(set_id, req)
