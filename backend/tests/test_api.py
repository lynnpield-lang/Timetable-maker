import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import mock, routes, schemas, service
from api.backend import use_mock
from kkul.timetable.analyzer import FEATURE_COLUMNS
from tests.conftest import FIXTURES

GEN = {
    "user_depts": ["경영학과"],
    "wanted": [{"code": c} for c in ["BIZ2021", "BIZ2006", "BIZ3001", "BIZ2030", "ECO2001"]]
    + [{"code": "GEDH001", "required": False}],
}


@pytest.fixture(params=["service", "mock"])
def client(request, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    if request.param == "service":
        use_mock(False)
        service.configure("test", data_dir=str(FIXTURES))
    else:
        mock._ready = False
        use_mock(True)
    app = FastAPI()
    routes.register(app)
    yield TestClient(app)
    use_mock(False)


def test_feature_columns_match():
    assert schemas.FEATURE_COLUMNS == FEATURE_COLUMNS


def test_full_flow(client):
    meta = client.get("/api/meta").json()
    schemas.MetaOut(**meta)
    assert meta["term"] == "test"

    courses = client.get("/api/courses", params={"q": "재무"}).json()
    assert courses["total"] == 3 and len(courses["items"]) == 3

    gen = client.post("/api/timetables/generate", json=GEN).json()
    schemas.GenerateOut(**gen)
    assert gen["count"] > 0
    sid = gen["set_id"]

    q = client.post(
        f"/api/timetables/{sid}/query",
        json={"sort": [{"column": "morning_days", "direction": 1}], "page_size": 5},
    ).json()
    schemas.QueryOut(**q)
    assert len(q["items"]) == 5 and q["items"][0]["rank"] == 1
    tid = q["items"][0]["tt_id"]

    det = client.get(f"/api/timetables/{sid}/{tid}").json()
    schemas.TimetableDetail(**det)
    assert len(det["summary"]["weekly_load"]) == 16

    sim = client.get(f"/api/timetables/{sid}/{tid}/similar").json()
    assert sim["total"] >= 1

    saved = client.put(
        f"/api/competition/{sid}",
        json={"rows": [{"key": "BIZ2006-01", "capacity": 40, "applied": 90}]},
    ).json()
    assert saved == {"saved": 1}

    st = client.post(
        f"/api/strategy/{sid}/{tid}", json={"sim_runs": 500, "sensitivity": False}
    ).json()
    schemas.StrategyOut(**st)
    assert {o["key"] for o in st["order"]} == set(st["target"])

    ex = client.post(f"/api/strategy/{sid}/{tid}/explain").json()
    schemas.ExplainOut(**ex)
    assert ex["per_course"]

    nxt = client.post(
        f"/api/strategy/{sid}/next",
        json={"target_tt_id": tid, "secured": [], "failed": [st["order"][0]["key"]], "clicks": 1},
    ).json()
    schemas.NextOut(**nxt)


def test_errors(client):
    r = client.post("/api/timetables/nope/query", json={})
    assert r.status_code == 404 and r.json()["code"] == "TT_SET_NOT_FOUND"
    gen = client.post("/api/timetables/generate", json=GEN).json()
    r = client.post(
        f"/api/timetables/{gen['set_id']}/query", json={"filters": {"bounds": {"nope": [0, 1]}}}
    )
    assert r.status_code == 422 and r.json()["code"] == "INVALID_FILTER"
    r = client.get("/api/courses/XYZ0000-01")
    assert r.status_code == 404 and r.json()["code"] == "COURSE_NOT_FOUND"


def test_zero_results_give_relax(client):
    gen = client.post("/api/timetables/generate", json=GEN).json()
    q = client.post(
        f"/api/timetables/{gen['set_id']}/query",
        json={
            "filters": {
                "bounds": {"morning_days": [None, 0], "super_gaps": [None, 0]},
                "free_days": [0, 4],
            }
        },
    ).json()
    assert q["total"] == 0
    assert q["relax"]


def test_llm_off_in_service():
    use_mock(False)
    service.configure("test", data_dir=str(FIXTURES))
    app = FastAPI()
    routes.register(app)
    c = TestClient(app)
    r = c.post("/api/preferences/parse", json={"text": "금요일 쉬고 싶어"})
    assert r.status_code == 503 and r.json()["code"] == "LLM_UNAVAILABLE"


def test_data_not_built(tmp_path):
    use_mock(False)
    service.configure("2099_10", data_dir=str(tmp_path))
    app = FastAPI()
    routes.register(app)
    r = TestClient(app).get("/api/meta")
    assert r.status_code == 503 and r.json()["code"] == "DATA_NOT_BUILT"
