"""서버 메모리 저장소: 생성한 시간표 집합을 set_id로 보관 (최근 20개, 30분 안 쓰면 삭제).

캡처 결과·경쟁률도 set_id 아래 메모리에만 둔다 (파일로 남기지 않음).
"""

from __future__ import annotations

import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field

import pandas as pd

from kkul.config import Config
from kkul.errors import TimetableSetNotFound
from kkul.models import Competition, Filters, GenerateSpec, SortKey

MAX_SETS = 20
TTL_S = 30 * 60


@dataclass
class TimetableSet:
    set_id: str
    term: str
    spec: GenerateSpec
    cfg: Config
    table: pd.DataFrame  # 특징표 (전체, 정렬 전)
    major_keys: frozenset[str]
    ineligible_keys: frozenset[str]
    required_codes: frozenset[str]
    min_credits: int | None
    warnings: list[str]
    truncated: bool
    # 마지막 조회 조건 (전략은 이 정렬 결과 𝒯_f를 쓴다)
    filters: Filters = field(default_factory=Filters)
    sort: list[SortKey] = field(default_factory=list)
    bins: dict[str, float] = field(default_factory=dict)
    ranked: pd.DataFrame | None = None  # 묶지 않은 정렬 결과 (rank 열 포함)
    competition: dict[str, Competition] = field(default_factory=dict)  # 사용자가 확인한 값
    cache: dict = field(default_factory=dict)  # 전략·요약 결과 캐시
    used_at: float = field(default_factory=time.monotonic)


class Store:
    def __init__(self, max_sets: int = MAX_SETS, ttl_s: float = TTL_S) -> None:
        self._sets: OrderedDict[str, TimetableSet] = OrderedDict()
        self._lock = threading.Lock()
        self.max_sets = max_sets
        self.ttl_s = ttl_s

    @staticmethod
    def new_id() -> str:
        return secrets.token_urlsafe(8)

    def _evict(self) -> None:
        now = time.monotonic()
        for sid in [s for s, v in self._sets.items() if now - v.used_at > self.ttl_s]:
            del self._sets[sid]
        while len(self._sets) > self.max_sets:
            self._sets.popitem(last=False)

    def put(self, ts: TimetableSet) -> None:
        with self._lock:
            self._sets[ts.set_id] = ts
            self._sets.move_to_end(ts.set_id)
            self._evict()

    def get(self, set_id: str) -> TimetableSet:
        with self._lock:
            self._evict()
            ts = self._sets.get(set_id)
            if ts is None:
                raise TimetableSetNotFound(set_id=set_id)
            ts.used_at = time.monotonic()
            self._sets.move_to_end(set_id)
            return ts

    def clear(self) -> None:
        with self._lock:
            self._sets.clear()

    def __len__(self) -> int:
        return len(self._sets)


STORE = Store()
