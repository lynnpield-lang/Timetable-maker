"""LLM 설명 (01 C부 8장). 숫자·학수번호는 입력에 있는 것만 남긴다."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from kkul import llm


class PerCourse(BaseModel):
    key: str
    reason: str


class ExplainOut(BaseModel):
    summary: str = Field(description="전체 전략 요약 2–3문장")
    per_course: list[PerCourse] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def rule_based(plan_json: dict) -> dict:
    """LLM 없이 규칙 기반 태그로 만든 설명."""
    order = plan_json.get("order", [])
    per = [{"key": r["key"], "reason": ", ".join(r.get("tags", [])) or "-"} for r in order]
    warnings = ["대기순번을 받은 과목을 다시 신청하면 대기순번이 사라져요."]
    if any(r.get("ratio_source") == "estimate" for r in order):
        warnings.append("경쟁률 일부는 공개 정보로 추정한 값이에요. 캡처를 올리면 더 정확해져요.")
    first = order[0]["key"] if order else None
    summary = f"{first}부터 신청하세요." if first else "신청할 분반이 없어요."
    return {"summary": summary, "per_course": per, "warnings": warnings, "source": "rule"}


def explain(plan_json: dict, timeout: float = 10) -> dict:
    """순서표·트리·시뮬레이션 결과를 문장으로. 검증에 걸린 문장은 버리고, 실패하면 규칙 기반."""
    base = rule_based(plan_json)
    out = llm.call_json(
        "strategy_explain", json.dumps(plan_json, ensure_ascii=False), ExplainOut, timeout
    )
    if out is None:
        return base
    nums, keys = llm.allowed_from_input(plan_json)
    valid_keys = {r["key"] for r in plan_json.get("order", [])}

    def ok(s: str) -> bool:
        return llm.sentence_is_grounded(s, nums, keys)

    summary = " ".join(s for s in llm.split_sentences(out.summary) if ok(s))
    per = []
    for pc in out.per_course:
        if pc.key not in valid_keys:
            continue
        reason = " ".join(s for s in llm.split_sentences(pc.reason) if ok(s))
        per.append(
            {
                "key": pc.key,
                "reason": reason
                or next((b["reason"] for b in base["per_course"] if b["key"] == pc.key), "-"),
            }
        )
    seen = {p["key"] for p in per}
    per += [b for b in base["per_course"] if b["key"] not in seen]
    warnings = [w for w in out.warnings if ok(w)] or base["warnings"]
    return {
        "summary": summary or base["summary"],
        "per_course": per,
        "warnings": warnings,
        "source": "llm",
    }
