from kkul import llm
from kkul.capture import check_rows, normalize_key, parse_text
from kkul.loader.extract_syllabus import SyllabusExtract, split_for_storage, validate_extract

SOURCE = """Course Syllabus
Evaluation: Attendance 10%, Homework 20%, Midterm 30%, Final 40%.
There is a team project due in week 10 and week 14.
Students with 4 absences or more receive F.
"""


def test_quote_check():
    assert llm.quote_in_source("Midterm  30%,\nFinal 40%", SOURCE)
    assert not llm.quote_in_source("Midterm 50%", SOURCE)


def test_grounded_sentences():
    src = {"order": [{"key": "BIZ2006-01", "success_prob": 0.71, "ratio": 2.1}]}
    text = "BIZ2006-01을 먼저 신청하세요. 성공 확률은 71%입니다. 경쟁률은 9.9입니다. ECO9999-01도 보세요."
    kept = llm.keep_grounded(text, src)
    assert "71%" in kept and "9.9" not in kept and "ECO9999" not in kept


def test_validate_extract_drops_ungrounded():
    ex = SyllabusExtract(
        eval={"attend": 10, "homework": 20, "mid": 30, "final": 40},
        teamwork=True,
        workload_level=4,
        exams={"count": 2, "weeks": [8, 15, 20]},
        attendance={"strict": True, "rule": "결석 4회 이상 F"},
        evidence={
            "eval": "Midterm 30%, Final 40%",
            "teamwork": "team project due in week 10",
            "workload_level": "weekly quizzes every week",  # 원문에 없음 → 폐기
            "exams": "Midterm 30%",
            "attendance": "4 absences or more receive F",
        },
    )
    items, logs = validate_extract(ex, SOURCE)
    assert items["eval"]["mid"] == 30
    assert items["teamwork"] is True
    assert "workload_level" not in items
    assert items["exams"]["weeks"] == [8, 15]  # 1–16 밖 주차는 버림
    cols, profile = split_for_storage("BIZ2006-01", items, "pdf")
    assert cols["eval_source"] == "pdf_llm" and cols["exam_weeks"] == (8, 15)
    assert profile["key"] == "BIZ2006-01" and "workload_level" not in profile["evidence"]


def test_bad_eval_sum_dropped():
    ex = SyllabusExtract(eval={"mid": 50, "final": 40}, evidence={"eval": "Midterm 30%"})
    items, logs = validate_extract(ex, SOURCE)
    assert "eval" not in items and any("폐기" in x for x in logs)


def test_web_eval_wins():
    ex = SyllabusExtract(eval={"mid": 60, "final": 40}, evidence={"eval": "Midterm 30%"})
    items, logs = validate_extract(ex, SOURCE, web_eval={"mid": 50, "final": 50})
    assert "eval" not in items


def test_call_json_without_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert not llm.available()
    assert llm.call_json("x", "y", SyllabusExtract) is None


def test_capture_text_and_check(courses):
    assert normalize_key("biz2021 1") == "BIZ2021-01"
    rows = parse_text("BIZ2021-01 정원 45 신청 50\nXYZ9999-1 30 10\nBIZ2006-01 0 3")
    checked = check_rows(rows, courses)
    assert checked[0]["ok"] and checked[0]["capacity"] == 45
    assert not checked[1]["ok"] and checked[1]["issue"] == "없는 분반이에요"
    assert not checked[2]["ok"]
