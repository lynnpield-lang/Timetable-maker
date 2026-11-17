"""과목 수별 생성 시간 측정: uv run python -m kkul.timetable.bench --courses 6 8

실제 데이터가 있으면 --term으로, 없으면 무작위로 만든 과목(과목마다 분반 sections개)으로 잰다.
목표: 6–8과목 2초 이내 (01 B부 테스트).
"""

from __future__ import annotations

import argparse
import random
import time

from kkul.config import DEFAULT_CONFIG
from kkul.models import EVAL_KEYS, Course, GenerateSpec, Slot, WantedCourse
from kkul.timetable.analyzer import build_table
from kkul.timetable.scheduler import generate

STARTS = (540, 630, 720, 810, 900, 990)


def synthetic(n_courses: int, sections: int, seed: int = 0) -> dict[str, Course]:
    """무작위 과목: 75분 수업 주 2회 (월수 / 화목) 또는 금요일 150분."""
    rng = random.Random(seed)
    out = {}
    for i in range(n_courses):
        code = f"SYN{1000 + i}"
        for s in range(1, sections + 1):
            st = rng.choice(STARTS)
            days = rng.choice(((0, 2), (1, 3), (4,)))
            dur = 150 if days == (4,) else 75
            slots = tuple(Slot(d, st, st + dur, f"{rng.randint(30, 35)}101") for d in days)
            key = f"{code}-{s:02d}"
            out[key] = Course(
                key, code, f"{s:02d}", code, "", 3, 3, f"P{s}", 1, slots, "전공", "오프라인",
                False, None, False, "", (), (), None, None, {k: None for k in EVAL_KEYS}, "none",
                None, None, None, None, None, None, None,
            )  # fmt: skip
    return out


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser()
    ap.add_argument("--courses", type=int, nargs="+", default=[6, 8])
    ap.add_argument("--sections", type=int, default=6)
    args = ap.parse_args()
    for n in args.courses:
        cs = synthetic(n, args.sections)
        spec = GenerateSpec(wanted=tuple(WantedCourse(f"SYN{1000 + i}") for i in range(n)))
        t0 = time.perf_counter()
        res = generate(cs, spec, DEFAULT_CONFIG)
        t1 = time.perf_counter()
        build_table(res.timetables, cs, {}, DEFAULT_CONFIG)
        t2 = time.perf_counter()
        print(
            f"{n}과목 × {args.sections}분반: 시간표 {len(res.timetables)}개"
            f"{' (상한)' if res.truncated else ''} / 생성 {t1 - t0:.2f}s / 특징표 {t2 - t1:.2f}s"
        )


if __name__ == "__main__":  # pragma: no cover
    main()
