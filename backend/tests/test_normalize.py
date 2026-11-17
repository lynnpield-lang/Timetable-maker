from kkul import io
from kkul.loader.normalize import (
    normalize_course,
    parse_credits,
    parse_dept_list,
    parse_ratio,
    parse_time_string,
    validate_course,
)
from kkul.models import Slot
from tests.conftest import mk


def test_time_string_basic():
    slots, module, flipped, warns = parse_time_string(
        "화12:00-13:15【33303】,목13:30-14:45【33303】"
    )
    assert slots == [Slot(1, 720, 795, "33303"), Slot(3, 810, 885, "33303")]
    assert module is None and not flipped and not warns


def test_time_string_special():
    slots, module, flipped, _ = parse_time_string(
        "【모듈A】월09:00-10:15【미지정】,【1.5h(ON)+1.5h(OFF)】"
    )
    assert slots == [Slot(0, 540, 615, None)]
    assert module == "A"
    assert flipped


def test_small_parsers():
    assert parse_credits("3(3)") == (3, 3)
    assert parse_credits("2") == (2, 2)
    assert parse_ratio("30") == 30
    assert parse_ratio("") is None  # 빈 칸은 0이 아니라 None
    assert parse_ratio(None) is None
    assert parse_dept_list("경영학과,자유전공계열") == ("경영학과", "자유전공계열")
    assert parse_dept_list("") == ()


def test_normalize_course_row():
    row = {
        "HAKSU_NO": "BIZ2021",
        "BUNBAN": "1",
        "GWAMOK_NM": "관리회계",
        "HAKJUM": "3(3)",
        "GYOSU_NM": "조현권",
        "SIGAN_GANGUISIL": "화12:00-13:15【33303】,목13:30-14:45【33303】",
        "SUUP_HYUNGTAE_NM": "온라인[사전제작]",
    }
    extra = {
        "GYJUNINJ_HAKGWA": "경영학과,자유전공계열",
        "PYUNGGA_JUNGGAN": "50",
        "PYUNGGA_GIMAL": "50",
    }
    c, warns = normalize_course(row, extra)
    assert c.key == "BIZ2021-01"
    assert c.is_online
    assert c.major_depts == ("경영학과", "자유전공계열")
    assert c.restricted_depts == ()
    assert c.eval["mid"] == 50 and c.eval["attend"] is None
    assert c.eval_source == "web"
    assert not validate_course(c)


def test_validate_flags_bad_values():
    c = mk("BIZ1000-01", [(0, 600, 590, None)], eval={**mk("A-01", []).eval, "mid": 50})
    errs = validate_course(c)
    assert any("시작" in e for e in errs)
    assert any("합" in e for e in errs)


def test_csv_round_trip(tmp_path):
    c = mk(
        "BIZ2021-01",
        [(1, 720, 795, "33303"), (3, 810, 885, None)],
        teamwork=True,
        exam_weeks=(8, 15),
        major_depts=("경영학과", "자유전공계열"),
    )
    io.write_courses_file(tmp_path / "c.csv", [c])
    back = io.read_courses_file(tmp_path / "c.csv")["BIZ2021-01"]
    assert back == c
    assert back.workload_level is None  # 모르는 값은 None 그대로
