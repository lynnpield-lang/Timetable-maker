"""Nexacro SSV 응답 파싱 (01 A부 3단계).

형식: 레코드 구분 \\x1e, 칸 구분 \\x1f.
  SSV:utf-8 ␞ ErrorCode:int=0 ␞ ErrorMsg:string= ␞ Dataset:ds_main ␞
  _RowType_␟COL1:STRING(256)␟COL2:INT(10) ␞ N␟값␟값 ␞ … ␞ (빈 레코드) ␞ Dataset:…
"""

from __future__ import annotations

from kkul.errors import ParseError

RS = "\x1e"
US = "\x1f"
NULL = "\x03"


def _col_name(header: str) -> str:
    return header.split(":", 1)[0]


def parse_ssv(text: str) -> dict[str, list[dict[str, str | None]]]:
    """SSV 문자열 → {데이터셋 이름: [행 dict]}. ErrorCode가 0이 아니면 ParseError."""
    records = text.split(RS)
    if not records or not records[0].startswith("SSV"):
        raise ParseError("SSV 응답이 아니에요.", head=text[:40])
    datasets: dict[str, list[dict[str, str | None]]] = {}
    cur_name: str | None = None
    cols: list[str] | None = None
    for rec in records[1:]:
        if rec.startswith("ErrorCode"):
            code = rec.split("=", 1)[1] if "=" in rec else "0"
            if code.strip() not in ("0", ""):
                raise ParseError("학교 서버가 오류를 돌려줬어요.", error_code=code)
            continue
        if rec.startswith("Dataset:"):
            cur_name = rec.split(":", 1)[1].strip()
            datasets[cur_name] = []
            cols = None
            continue
        if cur_name is None:
            continue
        if rec == "":
            cur_name, cols = None, None
            continue
        fields = rec.split(US)
        if cols is None:
            if fields[0].startswith("_RowType_"):
                cols = [_col_name(h) for h in fields[1:]]
            else:
                cols = [_col_name(h) for h in fields]
            continue
        if fields[0] in ("N", "I", "U", "D", "O") and len(fields) == len(cols) + 1:
            fields = fields[1:]
        if fields and fields[0] == "D":
            continue
        row = {c: (None if v == NULL else v) for c, v in zip(cols, fields, strict=False)}
        datasets[cur_name].append(row)
    return datasets


def debug_view(text: str) -> str:
    """사람이 읽기 쉬운 모양으로 (디버깅용)."""
    return text.replace(RS, "\n").replace(US, " | ")
