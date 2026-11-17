"""A부 전체 실행: 코드 목록 → 과목 목록 → 계획서 → 파싱 → 정규화·병합 → 검증 → 저장.

실행: uv run python -m kkul.loader.build --year 2026 --term 20 --depts 316901
학기당 한 번만 실행한다. 원문은 data/raw/에 캐시되므로 중단·재개할 수 있다.
"""

from __future__ import annotations

import argparse
import csv
import logging
from dataclasses import dataclass, field

from kkul import io
from kkul.config import DEFAULT_CONFIG
from kkul.errors import KkulError
from kkul.loader import extract_syllabus, skku_client, syllabus
from kkul.loader.normalize import normalize_course, pick, validate_course
from kkul.models import Course

log = logging.getLogger(__name__)


@dataclass
class BuildReport:
    term: str
    departments: list[str]
    sections: int = 0
    parse_failed: int = 0
    time_ok: int = 0
    syllabus: int = 0
    eval_web: int = 0
    eval_pdf: int = 0
    eval_none: int = 0
    extract_dropped: int = 0
    requests: int = 0
    errors: list[str] = field(default_factory=list)

    def line(self) -> str:
        """출력 예: 경영학과 108개 / 시간 파싱 성공 108 / … (01 A부 5단계)."""
        return (
            f"{self.term} {self.sections}개 / 시간 파싱 성공 {self.time_ok} / 계획서 {self.syllabus} / "
            f"평가 비율: 웹 {self.eval_web}, PDF 추출 {self.eval_pdf}, 없음 {self.eval_none} / "
            f"추출 폐기 {self.extract_dropped} / 변환 실패 {self.parse_failed} / 요청 {self.requests}"
        )


def _write_parse_errors(rows: list[dict]) -> None:
    path = io.data_dir() / "parse_errors.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["key", "error", "raw"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def build(
    year: int,
    term: int,
    depts: list[str] | None = None,
    *,
    with_pdf: bool = True,
    with_llm: bool = True,
    offline: bool = False,
    campus: int = 1,
) -> BuildReport:
    """한 학기 데이터를 만들어 data/courses_·profiles_·meta_<학기> 로 저장한다."""
    term_key = f"{year}_{term}"
    client = skku_client.SkkuClient(term_key, offline=offline)
    dept_list: list[dict] = []
    if not depts:
        dept_list = skku_client.list_departments(client, year, term, campus)
        depts = [d["code"] for d in dept_list]
    report = BuildReport(term_key, list(depts))

    raw_rows: list[dict] = []
    for d in depts:
        try:
            rows = skku_client.list_courses(client, year, term, d, campus)
        except KkulError as e:
            report.errors.append(f"{d}: {e.message}")
            continue
        raw_rows += rows
        log.info("학과 %s: %d개 분반", d, len(rows))

    courses: dict[str, Course] = {}
    profiles: list[dict] = []
    errors: list[dict] = []
    searched: dict[str, dict] = {}
    for row in raw_rows:
        code = pick(row, "code")
        section = pick(row, "section").zfill(2)
        key = f"{code}-{section}"
        extra: dict = {}
        try:
            if code not in searched:
                hits = skku_client.search_course(client, year, term, code)
                searched[code] = hits[0] if hits else {}
            extra.update({k: v for k, v in searched[code].items() if k == "GYJUNINJ_HAKGWA"})
            syl = skku_client.syllabus(client, year, term, code, section)
            if syl:
                report.syllabus += 1
            extra.update(syl)
        except KkulError as e:
            report.errors.append(f"{key}: {e.message}")
        try:
            c, warns = normalize_course(row, extra, campus)
        except (ValueError, KeyError) as e:
            errors.append({"key": key, "error": str(e), "raw": str(row)[:500]})
            report.parse_failed += 1
            continue
        if warns:
            errors.append({"key": key, "error": "; ".join(warns), "raw": pick(row, "time")})
        problems = validate_course(c)
        if problems:
            errors.append({"key": key, "error": "; ".join(problems), "raw": ""})
        if c.slots or c.is_online:
            report.time_ok += 1
        # 2.5 PDF → LLM
        if with_pdf:
            try:
                info = syllabus.find_pdf(client, year, term, code, section)
                if info:
                    text, status = syllabus.pdf_text(syllabus.download_pdf(client, key, info))
                    if status == "ok" and with_llm:
                        res = extract_syllabus.extract_one(c, text)
                        if res is not None:
                            cols, profile, logs = res
                            report.extract_dropped += sum(
                                1 for x in logs if "폐기" in x or "근거" in x
                            )
                            profile["text_hash"] = extract_syllabus.text_hash(text)
                            c = extract_syllabus.apply_columns(c, cols)
                            profiles.append(profile)
            except KkulError as e:
                report.errors.append(f"{key} PDF: {e.message}")
        courses[c.key] = c

    for c in courses.values():
        if c.eval_source == "web":
            report.eval_web += 1
        elif c.eval_source == "pdf_llm":
            report.eval_pdf += 1
        else:
            report.eval_none += 1
    report.sections = len(courses)
    report.requests = client.requests_made

    io.write_courses(term_key, list(courses.values()))
    io.write_profiles(term_key, profiles)
    _write_parse_errors(errors)
    io.write_meta(
        term_key,
        {
            "schema_version": DEFAULT_CONFIG.schema_version,
            "term": term_key,
            "built_at": io.now_iso(),
            "departments": list(depts),
            "department_list": dept_list,
            "counts": {
                "sections": report.sections,
                "parse_failed": report.parse_failed,
                "eval_web": report.eval_web,
                "eval_pdf": report.eval_pdf,
                "eval_none": report.eval_none,
            },
        },
    )
    return report


def main() -> None:  # pragma: no cover - CLI
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="학기 데이터 build (학기당 1회)")
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--term", type=int, required=True, help="10 = 1학기, 20 = 2학기")
    ap.add_argument("--depts", nargs="*", help="학과 코드 (없으면 전체)")
    ap.add_argument("--campus", type=int, default=1)
    ap.add_argument("--no-pdf", action="store_true", help="계획서 PDF 수집 건너뛰기")
    ap.add_argument("--no-llm", action="store_true", help="LLM 추출 건너뛰기")
    ap.add_argument("--offline", action="store_true", help="data/raw 캐시만 사용")
    args = ap.parse_args()
    from dotenv import load_dotenv

    load_dotenv()
    rep = build(
        args.year,
        args.term,
        args.depts,
        with_pdf=not args.no_pdf,
        with_llm=not args.no_llm,
        offline=args.offline,
        campus=args.campus,
    )
    print(rep.line())
    for e in rep.errors[:20]:
        print("  !", e)


if __name__ == "__main__":  # pragma: no cover
    main()
