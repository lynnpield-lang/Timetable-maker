"""꿀시간표 공통 예외. api/service.py가 03_interfaces.md 6장 오류 형식으로 바꾼다."""

from __future__ import annotations


class KkulError(Exception):
    """모든 꿀시간표 예외의 부모. code는 03_interfaces.md 6장의 오류 코드."""

    code: str = "INTERNAL"
    http_status: int = 500
    default_message: str = "알 수 없는 오류가 발생했어요."

    def __init__(self, message: str | None = None, **detail: object) -> None:
        self.message = message or self.default_message
        self.detail = detail
        super().__init__(self.message)


class DataNotBuilt(KkulError):
    code = "DATA_NOT_BUILT"
    http_status = 503
    default_message = "학기 데이터가 없거나 버전이 달라요. 데이터를 다시 build하세요."


class CourseNotFound(KkulError):
    code = "COURSE_NOT_FOUND"
    http_status = 404
    default_message = "없는 분반이에요."


class TimetableSetNotFound(KkulError):
    code = "TT_SET_NOT_FOUND"
    http_status = 404
    default_message = "시간표 결과가 만료됐어요. 다시 만들어 주세요."


class InvalidFilter(KkulError):
    code = "INVALID_FILTER"
    http_status = 422
    default_message = "필터나 정렬 조건이 올바르지 않아요."


class LLMUnavailable(KkulError):
    code = "LLM_UNAVAILABLE"
    http_status = 503
    default_message = "AI 기능을 지금 쓸 수 없어요."


class LLMInvalid(KkulError):
    code = "LLM_INVALID"
    http_status = 502
    default_message = "AI 응답을 확인하지 못했어요."


class SkkuRequestError(KkulError):
    """학교 서버 요청 실패 (build 중에만 발생)."""

    code = "SKKU_REQUEST"
    http_status = 502
    default_message = "학교 서버 요청에 실패했어요."


class ParseError(KkulError):
    """원본 데이터 파싱 실패 (build 중에만 발생)."""

    code = "PARSE_ERROR"
    http_status = 500
    default_message = "원본 데이터를 읽지 못했어요."
