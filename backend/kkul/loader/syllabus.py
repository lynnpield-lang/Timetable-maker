"""수업계획서 PDF 찾기·다운로드·텍스트 추출 (01 A부 2.5 ①②). PDF 원본은 커밋하지 않는다."""

from __future__ import annotations

import io as _io
import logging

from kkul.loader.skku_client import SkkuClient, first_rows, term_params

log = logging.getLogger(__name__)

MIN_TEXT_CHARS = 200


def find_pdf(client: SkkuClient, year: int, term: int, code: str, section: str) -> dict | None:
    """BIZ_PLN_FILE_ID → 첨부 파일 정보 {FILE_NM, DOWNLOAD_FILE_ID, FILE_SEQ}. 없으면 None."""
    rows = first_rows(
        client.fetch_ssv(
            "syllabus_file",
            f"{code}-{section}",
            {**term_params(year, term), "HAKSU_NO": code, "BUNBAN": section},
        )
    )
    file_id = rows[0].get("BIZ_PLN_FILE_ID") if rows else None
    if not file_id:
        return None
    files = first_rows(client.fetch_ssv("attach_files", file_id, {"FILE_ID": file_id}))
    pdfs = [f for f in files if str(f.get("FILE_NM", "")).lower().endswith(".pdf")]
    return pdfs[0] if pdfs else (files[0] if files else None)


def download_pdf(client: SkkuClient, key: str, info: dict) -> bytes:
    """PDF 원본 (data/raw/syllabus/<키>.pdf 캐시)."""
    return client.fetch_bytes(
        "download",
        f"syllabus/{key}.pdf",
        {"attachFileId": info.get("DOWNLOAD_FILE_ID"), "sequenceNumber": info.get("FILE_SEQ")},
    )


def pdf_text(pdf: bytes) -> tuple[str, str]:
    """PDF → (텍스트, 상태). 상태: ok / scanned_or_empty / error."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(_io.BytesIO(pdf))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception as e:  # 깨진 PDF
        log.warning("PDF 읽기 실패: %s", e)
        return "", "error"
    if len(text.strip()) < MIN_TEXT_CHARS:
        return text, "scanned_or_empty"
    return text, "ok"
