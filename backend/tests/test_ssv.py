import pytest

from kkul.errors import ParseError
from kkul.loader.ssv import NULL, RS, US, parse_ssv

SAMPLE = RS.join(
    [
        "SSV:utf-8",
        "ErrorCode:int=0",
        "ErrorMsg:string=",
        "Dataset:ds_main",
        US.join(["_RowType_", "HAKSU_NO:STRING(10)", "BUNBAN:STRING(2)", "BIGO:STRING(100)"]),
        US.join(["N", "BIZ2021", "01", NULL]),
        US.join(["N", "BIZ2006", "02", "*6모듈강좌(모듈A)"]),
        "",
        "Dataset:ds_other",
        US.join(["_RowType_", "CODE:STRING(5)"]),
        US.join(["N", "X1"]),
        "",
    ]
)


def test_parse_two_datasets():
    ds = parse_ssv(SAMPLE)
    assert set(ds) == {"ds_main", "ds_other"}
    assert ds["ds_main"][0] == {"HAKSU_NO": "BIZ2021", "BUNBAN": "01", "BIGO": None}
    assert ds["ds_main"][1]["BIGO"] == "*6모듈강좌(모듈A)"
    assert ds["ds_other"] == [{"CODE": "X1"}]


def test_error_code_raises():
    with pytest.raises(ParseError):
        parse_ssv(RS.join(["SSV:utf-8", "ErrorCode:int=-1", "ErrorMsg:string=fail"]))


def test_not_ssv():
    with pytest.raises(ParseError):
        parse_ssv("<html>")
