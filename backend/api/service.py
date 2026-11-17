"""화면과 REST가 함께 쓰는 함수. kkul/을 불러 schemas 형식으로 바꾼다 (02 '구조').

- ui/는 이 파일의 함수를 직접 부르고, routes.py는 같은 함수를 HTTP로 연다.
- kkul/의 KkulError는 그대로 올려 보내고, 화면·라우트는 error_body(e)로 03 6장 형식을 만든다.
"""

from __future__ import annotations

import dataclasses
import logging
import math
import threading
from collections import Counter
from dataclasses import dataclass

import pandas as pd

from api import schemas as S
from api.store import STORE, TimetableSet
from kkul import io, llm
from kkul import preferences as prefs
from kkul.capture import read_capture as _read_capture
from kkul.capture import to_competition
from kkul.config import DEFAULT_CONFIG, Config
from kkul.errors import (
    CourseNotFound,
    DataNotBuilt,
    KkulError,
    LLMInvalid,
    LLMUnavailable,
    TimetableSetNotFound,
)
from kkul.models import (
    Course,
    Filters,
    GenerateSpec,
    LiveState,
    SortKey,
    Timetable,
    WantedCourse,
    make_timetable,
)
from kkul.strategy import build_competition, explain, plan
from kkul.strategy import next_step as _next_step
from kkul.timetable import build_table, generate, query
from kkul.timetable.analyzer import FEATURE_COLUMNS, FEATURES
from kkul.timetable.details import details as _details
from kkul.timetable.details import grid_blocks, late_risk_slots, summarize_with_llm, tags_for
from kkul.timetable.eligibility import normalize_dept
from kkul.timetable.explorer import counts_without, relax_suggestions, validate

log = logging.getLogger(__name__)


# ------------------------------------------------------------------ 학기 데이터


@dataclass
class TermData:
    term: str
    courses: dict[str, Course]
    profiles: dict[str, dict]
    buildings: dict[str, dict]
    alias: dict[str, str]
    meta: dict
    sections_per_code: Counter


_lock = threading.Lock()
_state: dict = {"term": None, "data": None, "mock": False}


def configure(term: str | None, *, data_dir: str | None = None, mock: bool = False) -> None:
    """main.py가 시작할 때 부른다 (학기, 데이터 폴더, 목업 여부)."""
    with _lock:
        if data_dir is not None:
            io.set_data_dir(data_dir)
        _state.update({"term": term, "data": None, "mock": mock})
    STORE.clear()


def data() -> TermData:
    """학기 데이터 (서버 시작 후 처음 한 번 읽어 모든 사용자가 같이 씀)."""
    with _lock:
        if _state["data"] is not None:
            return _state["data"]
        term = _state["term"]
        if not term:
            raise DataNotBuilt("KKUL_TERM이 설정되지 않았어요.")
        courses = io.read_courses(term)
        d = TermData(
            term=term,
            courses=courses,
            profiles=io.read_profiles(term),
            buildings=io.read_buildings(),
            alias=io.read_dept_alias(),
            meta=io.read_meta(term) or {},
            sections_per_code=Counter(c.code for c in courses.values()),
        )
        _state["data"] = d
        return d


def error_body(e: KkulError) -> S.ErrorBody:
    """KkulError → 03 6장 오류 본문."""
    detail = {
        k: (v if isinstance(v, str | int | float | bool | None) else str(v))
        for k, v in e.detail.items()
    }
    return S.ErrorBody(code=e.code, message=e.message, detail=detail)


# ------------------------------------------------------------------ 변환 도우미


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if hasattr(v, "item"):  # numpy 값
        v = v.item()
    return v


def _features(row: dict) -> dict:
    return {c: _clean(row.get(c)) for c in FEATURE_COLUMNS}


def _course_summary(c: Course, d: TermData) -> S.CourseSummary:
    badges = []
    if c.restricted_depts:
        badges.append("수강 대상 제한")
    if c.english:
        badges.append("국제어")
    if c.is_online:
        badges.append("온라인")
    if c.module:
        badges.append(f"모듈 {c.module}")
    if c.eval_source == "pdf_llm":
        badges.append("계획서 PDF에서 자동 추출")
    elif c.eval_source == "none":
        badges.append("평가 비율 미입력")
    return S.CourseSummary(
        key=c.key,
        code=c.code,
        section=c.section,
        name=c.name,
        name_en=c.name_en,
        professor=c.professor,
        credits=c.credits,
        category=c.category,
        mode=c.mode,
        is_online=c.is_online,
        english=c.english,
        slots=[S.SlotOut(day=s.day, start=s.start, end=s.end, room=s.room) for s in c.slots],
        eval=dict(c.eval),
        eval_source=c.eval_source,
        restricted_depts=list(c.restricted_depts),
        major_depts=list(c.major_depts),
        badges=badges,
        sections_in_course=d.sections_per_code[c.code],
    )


def _card(row: dict, d: TermData, cfg: Config) -> S.TimetableCard:
    tt = tuple(row["sections"])
    late = late_risk_slots(tt, d.courses, d.buildings, cfg)
    f = _features(row)
    return S.TimetableCard(
        tt_id=row["tt_id"],
        rank=int(row.get("rank") or 0),
        sections=list(tt),
        grid=[S.GridBlock(**b) for b in grid_blocks(tt, d.courses, late)],
        tags=tags_for(f),
        features=f,
        group_size=int(row.get("group_size") or 1),
        credits=int(f.get("credits") or 0),
    )


def _filters(f: S.FiltersIn) -> Filters:
    return Filters(
        bounds={k: (v[0], v[1]) for k, v in f.bounds.items()},
        free_days=tuple(f.free_days),
        include_missing_eval=f.include_missing_eval,
    )


def _sort(keys: list[S.SortKeyIn]) -> list[SortKey]:
    return [SortKey(k.column, k.direction) for k in keys]


def _cfg_from(settings: S.SettingsIn) -> Config:
    changes = {k: v for k, v in settings.model_dump().items() if v is not None}
    return dataclasses.replace(DEFAULT_CONFIG, **changes)


# ------------------------------------------------------------------ 메타·과목


def get_meta() -> S.MetaOut:
    """학기, 캠퍼스, 학과 목록, 특징 열 설명."""
    d = data()
    depts = [S.Department(**x) for x in d.meta.get("department_list", [])]
    if not depts:  # build 때 학과 목록을 못 받았으면 과목 데이터에서 모은다
        names = sorted(
            {n for c in d.courses.values() for n in (*c.major_depts, *c.restricted_depts)}
        )
        depts = [S.Department(code=n, name=n) for n in names]
    return S.MetaOut(
        term=d.term,
        built_at=d.meta.get("built_at"),
        schema_version=DEFAULT_CONFIG.schema_version,
        campuses=sorted({c.campus for c in d.courses.values()}) or [1],
        departments=depts,
        counts=d.meta.get("counts", {}),
        features=[
            S.FeatureInfo(column=c, kind=k, better=b, label=lab) for c, k, b, lab in FEATURES
        ],
        llm_available=llm.available() or _state["mock"],
        mock=_state["mock"],
    )


def list_courses(
    q: str | None = None,
    dept: str | None = None,
    category: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> S.Page[S.CourseSummary]:
    """과목 검색 (이름·학수번호·교수, 학과, 이수구분)."""
    d = data()
    page_size = max(1, min(page_size, 100))
    items = sorted(d.courses.values(), key=lambda c: c.key)
    if q:
        ql = q.strip().lower()
        items = [
            c
            for c in items
            if ql in c.name.lower()
            or ql in c.key.lower()
            or ql in c.professor.lower()
            or ql in c.name_en.lower()
        ]
    if dept:
        nd = normalize_dept(dept, d.alias)
        items = [
            c
            for c in items
            if nd in {normalize_dept(x, d.alias) for x in (*c.major_depts, *c.restricted_depts)}
        ]
    if category:
        items = [c for c in items if category in c.category]
    start = (page - 1) * page_size
    return S.Page[S.CourseSummary](
        total=len(items),
        items=[_course_summary(c, d) for c in items[start : start + page_size]],
        page=page,
        page_size=page_size,
    )


def get_course(key: str) -> S.CourseSummary:
    d = data()
    if key not in d.courses:
        raise CourseNotFound(key=key)
    return _course_summary(d.courses[key], d)


# ------------------------------------------------------------------ 시간표


def generate_timetables(req: S.GenerateRequest) -> S.GenerateOut:
    """[시간표 만들기]: 생성 + 특징표를 서버 메모리에 저장하고 set_id를 돌려준다."""
    d = data()
    cfg = _cfg_from(req.settings)
    hard = _filters(req.hard)
    validate(hard)
    spec = GenerateSpec(
        wanted=tuple(
            WantedCourse(w.code, w.required, tuple(w.sections) if w.sections is not None else None)
            for w in req.wanted
        ),
        user_depts=tuple(req.user_depts),
        hard=hard,
        credit_range=(req.credit_min, req.credit_max),
        include_ineligible=req.include_ineligible,
        major_only=req.major_only,
        dept_alias=d.alias,
    )
    res = generate(d.courses, spec, cfg, d.buildings)
    table = build_table(res.timetables, d.courses, d.buildings, cfg, res.major_keys)
    ts = TimetableSet(
        set_id=STORE.new_id(),
        term=d.term,
        spec=spec,
        cfg=cfg,
        table=table,
        major_keys=frozenset(res.major_keys),
        ineligible_keys=frozenset(res.ineligible_keys),
        required_codes=frozenset(w.code for w in req.wanted if w.required),
        min_credits=req.credit_min,
        warnings=res.warnings,
        truncated=res.truncated,
    )
    ts.ranked = query(table, Filters(), [], fold=False)
    STORE.put(ts)
    warnings = list(res.warnings)
    if not res.timetables and not warnings:
        warnings.append("겹치지 않는 시간표가 없어요. 과목이나 꼭 지킬 조건을 바꿔 보세요.")
    return S.GenerateOut(
        set_id=ts.set_id,
        count=len(res.timetables),
        truncated=res.truncated,
        warnings=warnings,
        excluded=res.excluded,
        elapsed_s=round(res.elapsed_s, 3),
    )


def query_timetables(set_id: str, req: S.QueryRequest) -> S.QueryOut:
    """필터·정렬·묶기 + 필터별 남는 개수 + (0개면) 완화 제안."""
    d = data()
    ts = STORE.get(set_id)
    filters, sort = _filters(req.filters), _sort(req.sort)
    ranked = query(ts.table, filters, sort, req.bins, fold=False)
    ts.filters, ts.sort, ts.bins, ts.ranked = filters, sort, req.bins, ranked
    ts.cache.pop("strategy", None)
    shown = query(ts.table, filters, sort, req.bins, fold=True) if req.fold else ranked
    start = (req.page - 1) * req.page_size
    page_rows = shown.iloc[start : start + req.page_size].to_dict("records")
    relax = relax_suggestions(ts.table, filters) if ranked.empty else []
    return S.QueryOut(
        total=len(shown),
        total_unfolded=len(ranked),
        items=[_card(r, d, ts.cfg) for r in page_rows],
        counts=counts_without(ts.table, filters),
        relax=[S.RelaxSuggestion(**r) for r in relax],
        page=req.page,
        page_size=req.page_size,
    )


def similar_timetables(set_id: str, tt_id: str) -> S.SimilarOut:
    """같은 시간 모양 n개 더 보기 (현재 정렬 순서)."""
    d = data()
    ts = STORE.get(set_id)
    ranked = _ranked(ts)
    row = _row(ts, tt_id)
    same = ranked[ranked["shape_key"] == row["shape_key"]]
    return S.SimilarOut(
        total=len(same), items=[_card(r, d, ts.cfg) for r in same.to_dict("records")]
    )


def _ranked(ts: TimetableSet) -> pd.DataFrame:
    if ts.ranked is None:
        ts.ranked = query(ts.table, ts.filters, ts.sort, ts.bins, fold=False)
    return ts.ranked


def _row(ts: TimetableSet, tt_id: str) -> dict:
    hit = ts.table[ts.table["tt_id"] == tt_id]
    if hit.empty:
        raise TimetableSetNotFound("이 시간표를 찾지 못했어요. 다시 만들어 주세요.", tt_id=tt_id)
    row = hit.iloc[0].to_dict()
    ranked = _ranked(ts)
    r = ranked[ranked["tt_id"] == tt_id]
    row["rank"] = int(r.iloc[0]["rank"]) if not r.empty else None
    return row


def timetable_detail(set_id: str, tt_id: str) -> S.TimetableDetail:
    """상세 보기: 과목 카드, 주차별 부담, 몰리는 주 (LLM 호출 없음)."""
    d = data()
    ts = STORE.get(set_id)
    row = _row(ts, tt_id)
    tt: Timetable = tuple(row["sections"])
    det = _details(tt, d.courses, d.profiles, ts.cfg, d.buildings, ts.major_keys)
    return S.TimetableDetail(
        tt_id=tt_id,
        rank=row["rank"],
        sections=det["sections"],
        grid=[S.GridBlock(**b) for b in det["grid"]],
        tags=det["tags"],
        features={k: _clean(v) for k, v in det["features"].items()},
        cards=[S.CourseCard(**c) for c in det["cards"]],
        summary=S.DetailSummary(**det["summary"]),
    )


def summarize_timetable(set_id: str, tt_id: str) -> S.TextOut:
    """[이 시간표 요약해줘] (LLM). 결과는 시간표마다 캐시."""
    ts = STORE.get(set_id)
    key = ("summary", tt_id)
    if key in ts.cache:
        return S.TextOut(text=ts.cache[key])
    if not llm.available():
        raise LLMUnavailable()
    det = timetable_detail(set_id, tt_id)
    text = summarize_with_llm([c.model_dump() for c in det.cards], det.summary.model_dump())
    if not text:
        raise LLMInvalid()
    ts.cache[key] = text
    return S.TextOut(text=text)


def parse_preferences(text: str) -> S.PreferencesOut:
    """자연어 조건 → 필터·정렬 (LLM)."""
    if not llm.available():
        raise LLMUnavailable()
    out = prefs.parse_preferences(text)
    if out is None:
        raise LLMInvalid()
    return S.PreferencesOut(**out)


# ------------------------------------------------------------------ 캡처·경쟁률


def read_capture(images: list[tuple[bytes, str]], text: str | None = None) -> S.CaptureOut:
    """캡처 이미지(LLM)·붙여넣은 텍스트 → 확인용 행. 이미지는 저장하지 않는다."""
    d = data()
    if images and not llm.available() and not text:
        raise LLMUnavailable("AI 기능이 꺼져 있어요. 표에 직접 입력해 주세요.")
    imgs = [llm.Image(b, mt or "image/png") for b, mt in images]
    rows = _read_capture(imgs, text, d.courses)
    return S.CaptureOut(rows=[S.CaptureRowOut(**r) for r in rows])


def save_competition(set_id: str, req: S.CompetitionIn) -> S.SavedOut:
    """사용자가 확인한 정원·신청 인원을 set_id 아래 메모리에 저장."""
    d = data()
    ts = STORE.get(set_id)
    rows = []
    for r in req.rows:
        if r.key not in d.courses:
            raise CourseNotFound(key=r.key)
        rows.append(r.model_dump())
    ts.competition.update(to_competition(rows, "capture"))
    ts.cache.pop("strategy", None)
    return S.SavedOut(saved=len(rows))


# ------------------------------------------------------------------ 전략


def _strategy_cfg(ts: TimetableSet, req: S.StrategyRequest) -> Config:
    ch = {}
    if req.mu is not None:
        ch["mu_s"] = req.mu
    if req.delta_t is not None:
        ch["click_s"] = req.delta_t
    if req.drop is not None:
        ch["drop_rate"] = req.drop
    if req.m is not None:
        ch["tree_depth"] = req.m
    if req.sim_runs is not None:
        ch["sim_runs"] = req.sim_runs
    return dataclasses.replace(ts.cfg, **ch)


def _competition(ts: TimetableSet, ranked: pd.DataFrame, target: Timetable, cfg: Config):
    d = data()
    keys = set(target)
    for secs in ranked["sections"]:
        keys |= set(secs)
    return build_competition(sorted(keys), d.courses, ts.competition, cfg)


def get_strategy(set_id: str, tt_id: str, req: S.StrategyRequest | None = None) -> S.StrategyOut:
    """신청 순서·플랜 B 트리·시뮬레이션·정책 비교·민감도."""
    req = req or S.StrategyRequest()
    d = data()
    ts = STORE.get(set_id)
    ck = ("strategy", tt_id, req.model_dump_json())
    cache = ts.cache.setdefault("strategy", {})
    if ck in cache:
        return cache[ck]
    row = _row(ts, tt_id)
    target = make_timetable(row["sections"])
    cfg = _strategy_cfg(ts, req)
    ranked = _ranked(ts)
    comp = _competition(ts, ranked, target, cfg)
    res = plan(target, ranked, comp, cfg, ts.required_codes, ts.min_credits, req.sensitivity)
    order = []
    for o in res.order:
        od = dataclasses.asdict(o)
        od["name"] = d.courses[o.key].name if o.key in d.courses else ""
        order.append(S.OrderRowOut(**od))
    out = S.StrategyOut(
        set_id=set_id,
        tt_id=tt_id,
        target=list(target),
        order=order,
        tree=S.TreeNodeOut.model_validate(dataclasses.asdict(res.tree)),
        simulation=S.SimResultOut(**dataclasses.asdict(res.simulation)),
        policies=[S.SimResultOut(**dataclasses.asdict(p)) for p in res.policies],
        sensitivity=[S.SensitivityRow(**r) for r in res.sensitivity],
        robust_order=res.robust_order,
        competition=[
            S.CompetitionOut(
                key=k, capacity=c.capacity, applied=c.applied, ratio=c.ratio, source=c.source
            )
            for k, c in sorted(comp.items())
            if k in target
        ],
        assumptions=res.assumptions,
    )
    cache[ck] = out
    return out


def _plan_json(st: S.StrategyOut) -> dict:
    """LLM에 보낼 전략 요약 (숫자는 반올림해 둔다)."""
    leaves = []

    def walk(n: S.TreeNodeOut) -> None:
        if n.leaf:
            leaves.append(
                {
                    "reach_prob": round(n.reach_prob, 2),
                    "final_rank": n.final_rank,
                    "changes": n.changes,
                    "note": n.note,
                }
            )
        for ch in (n.on_success, n.on_fail):
            if ch:
                walk(ch)

    walk(st.tree)
    return {
        "order": [
            {
                "position": o.position,
                "key": o.key,
                "name": o.name,
                "ratio": None if o.ratio is None else round(o.ratio, 1),
                "ratio_source": o.ratio_source,
                "success_prob": round(o.success_prob, 2),
                "fallback_rank": o.fallback_rank,
                "tags": o.tags,
            }
            for o in st.order
        ],
        "tree_leaves": leaves,
        "policies": {p.policy: round(p.p_target, 2) for p in st.policies},
    }


def explain_strategy(set_id: str, tt_id: str) -> S.ExplainOut:
    """전략 설명 (LLM, 없으면 규칙 기반 태그)."""
    ts = STORE.get(set_id)
    key = ("explain", tt_id)
    if key in ts.cache:
        return ts.cache[key]
    st = get_strategy(set_id, tt_id)
    out = S.ExplainOut(**explain(_plan_json(st)))
    if out.source == "llm":
        ts.cache[key] = out
    return out


def next_step(set_id: str, req: S.NextRequest) -> S.NextOut:
    """실시간 모드: 성공/실패/대기 → 다음에 누를 학수번호."""
    ts = STORE.get(set_id)
    row = _row(ts, req.target_tt_id)
    target = make_timetable(row["sections"])
    ranked = _ranked(ts)
    comp = _competition(ts, ranked, target, ts.cfg)
    state = LiveState(
        target=target,
        secured=tuple(req.secured),
        failed=tuple(req.failed),
        waiting=dict(req.waiting),
        clicks=req.clicks,
    )
    ns = _next_step(state, ranked, comp, ts.cfg, ts.required_codes)
    return S.NextOut(
        next_keys=ns.next_keys,
        target_tt_id=ns.target_tt_id,
        target_sections=list(ns.target) if ns.target else None,
        target_rank=ns.target_rank,
        wait_advice=[S.WaitAdviceOut(**dataclasses.asdict(a)) for a in ns.wait_advice],
        message=ns.message,
    )


__all__ = [
    "configure",
    "error_body",
    "explain_strategy",
    "generate_timetables",
    "get_course",
    "get_meta",
    "get_strategy",
    "list_courses",
    "next_step",
    "parse_preferences",
    "query_timetables",
    "read_capture",
    "save_competition",
    "similar_timetables",
    "summarize_timetable",
    "timetable_detail",
]
