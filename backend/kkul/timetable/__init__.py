"""B부: 시간표 생성·탐색 (03 5장 함수 약속)."""

from kkul.timetable.analyzer import FEATURE_COLUMNS, analyze, build_table, weekly_load
from kkul.timetable.details import details
from kkul.timetable.explorer import apply_filters, count_if_relaxed, query
from kkul.timetable.scheduler import generate

__all__ = [
    "FEATURE_COLUMNS",
    "analyze",
    "apply_filters",
    "build_table",
    "count_if_relaxed",
    "details",
    "generate",
    "query",
    "weekly_load",
]
