"""성균관대 공개 전자시간표 요청 (01 A부 0–2단계). 학교 서버 접속은 이 파일과 syllabus.py에서만.

규칙: 로그인 없는 공개 요청만, 요청 사이 1초 이상, 503이면 2·4·8초 간격으로 3번까지 재시도,
응답 원문은 data/raw/<학기>/<종류>/<키>.ssv 에 저장하고 있으면 다시 요청하지 않는다.

⚠ 요청 본문 형식 중 일부는 아직 미확인이다 (01 A부 '데이터 출처' 표). scripts/skku_fetch.py v2에서
  확인한 세션·헤더·본문을 BASE_URL, DEFAULT_HEADERS, *_params 함수에 옮겨 확정한다.
"""

from __future__ import annotations

import logging
import time

import requests

from kkul import io
from kkul.errors import SkkuRequestError
from kkul.loader.ssv import RS, US, parse_ssv

log = logging.getLogger(__name__)

BASE_URL = "https://kingoinfo.skku.edu"  # ⚠ skku_fetch.py v2의 주소로 확인
PATHS = {
    "colleges": "/E_NHSSU900020M/selectBizType03.do",
    "departments": "/E_NHSSU900020M/selectBizType04.do",
    "major_courses": "/E_NHSSU900020M/selectMain.do",
    "all_courses": "/E_NHSSU900070M/selectMain.do",
    "syllabus": "/E_NHSSU900011P/selectMain0.do",
    "syllabus_file": "/E_NHSSU900011P/selectFile2.do",
    "attach_files": "/E_NAttachFile/selectAttachFiles.do",
    "download": "/E_Nsystem/fileDownload.do",
}
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (kkul-time student project; build once per term)",
    "Content-Type": "text/plain;charset=UTF-8",
    "Accept": "application/xml, text/xml, */*",
    "Referer": BASE_URL + "/",
    "Origin": BASE_URL,
}
MIN_INTERVAL_S = 1.0
RETRY_WAITS = (2, 4, 8)


def encode_params(params: dict[str, object]) -> str:
    """요청 변수를 SSV 본문으로 (Nexacro 형식)."""
    body = ["SSV:utf-8"]
    for k, v in params.items():
        body.append(f"{k}={'' if v is None else v}")
    return RS.join(body) + RS


class SkkuClient:
    """세션·헤더·간격·재시도·원문 캐시를 맡는다."""

    def __init__(self, term: str, base_url: str = BASE_URL, offline: bool = False) -> None:
        self.term = term
        self.base_url = base_url.rstrip("/")
        self.offline = offline  # True면 캐시만 사용 (파싱 코드 고칠 때)
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self._last = 0.0
        self.requests_made = 0

    def _wait(self) -> None:
        dt = time.monotonic() - self._last
        if dt < MIN_INTERVAL_S:
            time.sleep(MIN_INTERVAL_S - dt)
        self._last = time.monotonic()

    def _request(self, method: str, path: str, *, data: str | None = None, params=None) -> bytes:
        if self.offline:
            raise SkkuRequestError("오프라인 모드인데 캐시가 없어요.", path=path)
        url = self.base_url + path
        for attempt in range(len(RETRY_WAITS) + 1):
            self._wait()
            try:
                r = self.session.request(
                    method,
                    url,
                    data=data.encode("utf-8") if data else None,
                    params=params,
                    timeout=30,
                )
            except requests.RequestException as e:
                raise SkkuRequestError(
                    "학교 서버에 연결하지 못했어요.", path=path, error=str(e)
                ) from e
            self.requests_made += 1
            if r.status_code == 503 and attempt < len(RETRY_WAITS):
                log.warning("503 %s → %d초 뒤 재시도", path, RETRY_WAITS[attempt])
                time.sleep(RETRY_WAITS[attempt])
                continue
            if r.status_code != 200:
                raise SkkuRequestError(f"학교 서버 응답 {r.status_code}", path=path)
            return r.content
        raise SkkuRequestError("재시도 후에도 503", path=path)

    def fetch_ssv(self, kind: str, cache_key: str, params: dict[str, object]) -> dict:
        """SSV 요청 (캐시 우선) → 파싱한 데이터셋."""
        rel = f"{self.term}/{kind}/{cache_key}.ssv"
        raw = io.read_raw(rel)
        if raw is None:
            raw = self._request("POST", PATHS[kind], data=encode_params(params))
            io.write_raw(rel, raw)
        return parse_ssv(raw.decode("utf-8", errors="replace"))

    def fetch_bytes(self, kind: str, rel: str, params: dict[str, object]) -> bytes:
        """파일 다운로드 (GET, 캐시 우선)."""
        raw = io.read_raw(rel)
        if raw is None:
            raw = self._request("GET", PATHS[kind], params=params)
            io.write_raw(rel, raw)
        return raw


def first_rows(datasets: dict) -> list[dict]:
    """데이터셋이 하나뿐인 응답에서 행 목록."""
    for rows in datasets.values():
        if rows:
            return rows
    return []


# ------------------------------------------------------------------ 요청 변수 (⚠ 확인 필요)


def term_params(year: int, term: int) -> dict[str, object]:
    return {"GAESUL_YEAR": year, "GAESUL_TERM": term}


def list_departments(client: SkkuClient, year: int, term: int, campus: int = 1) -> list[dict]:
    """단과대 → 학과 코드 목록 (캠퍼스, 학과코드, 학과명)."""
    out = []
    colleges = first_rows(
        client.fetch_ssv(
            "colleges", f"campus{campus}", {**term_params(year, term), "CAMPUS_GB": campus}
        )
    )
    for col in colleges:
        ccode = col.get("CODE") or col.get("DANGWA_CD") or ""
        rows = first_rows(
            client.fetch_ssv(
                "departments",
                f"{campus}_{ccode}",
                {**term_params(year, term), "CAMPUS_GB": campus, "DANGWA_CD": ccode},
            )
        )
        for r in rows:
            out.append(
                {
                    "campus": campus,
                    "code": r.get("CODE") or r.get("HAKGWA_CD") or "",
                    "name": r.get("NAME") or r.get("HAKGWA_NM") or "",
                    "college": col.get("NAME") or col.get("DANGWA_NM") or "",
                }
            )
    return out


def list_courses(
    client: SkkuClient, year: int, term: int, dept: str, campus: int = 1
) -> list[dict]:
    """학사-전공과목 (900020M): 학과 하나의 분반 목록."""
    ds = client.fetch_ssv(
        "major_courses", dept, {**term_params(year, term), "CAMPUS_GB": campus, "HAKGWA_CD": dept}
    )
    return first_rows(ds)


def search_course(client: SkkuClient, year: int, term: int, code: str) -> list[dict]:
    """전체과목 검색 (900070M): 학수번호 하나 → 전공 인정 학과(GYJUNINJ_HAKGWA) 등."""
    ds = client.fetch_ssv("all_courses", code, {**term_params(year, term), "HAKSU_NO": code})
    return first_rows(ds)


def syllabus(client: SkkuClient, year: int, term: int, code: str, section: str) -> dict:
    """수업계획서 (900011P): 평가 비율·수강 대상 학과 등. 교수 연락처는 여기서 지운다."""
    ds = client.fetch_ssv(
        "syllabus",
        f"{code}-{section}",
        {**term_params(year, term), "HAKSU_NO": code, "BUNBAN": section},
    )
    merged: dict = {}
    for rows in ds.values():
        if rows:
            merged.update(rows[0])
    for private in ("HOME_TEL", "HANDPHONE_NO", "EMAIL", "OFFICE_TEL"):
        merged.pop(private, None)
    return merged


__all__ = [
    "SkkuClient",
    "US",
    "list_courses",
    "list_departments",
    "search_course",
    "syllabus",
]
