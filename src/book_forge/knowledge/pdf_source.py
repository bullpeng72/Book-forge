"""PDF → 텍스트 청크. 집필 보조 RAG 소스 수집 전용, 단순 고정 크기 슬라이딩 청킹."""
from __future__ import annotations

from pathlib import Path


def extract_pdf_text(path: Path) -> str:
    from pypdf import PdfReader  # lazy import — [rag] extra

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def chunk_text(
    text: str, *, chunk_size: int = 800, overlap: int = 100, collapse_whitespace: bool = True
) -> list[str]:
    """chunk_size 글자 단위로 overlap을 두고 자른다.

    문장/단락 경계를 존중하지 않는 단순 고정폭 청킹 — RAG 소스 규모가 작을 때는
    검색 재현율에 큰 영향이 없고, 문장 경계 탐지 로직을 추가할 이유가 없다.

    collapse_whitespace: PDF 추출 텍스트는 줄바꿈/공백이 뒤죽박죽이라 기본값 True로
    전부 단일 공백으로 정규화한다. 코드/마크다운 소스는 줄 구조 자체가 의미가 있어
    (들여쓰기, 함수 경계) knowledge/sources.py가 False로 호출한다.
    """
    normalized = " ".join(text.split()) if collapse_whitespace else text.strip()
    if not normalized:
        return []

    chunks: list[str] = []
    start = 0
    step = max(chunk_size - overlap, 1)
    while start < len(normalized):
        chunks.append(normalized[start : start + chunk_size])
        start += step
    return chunks


def load_pdf_chunks(path: Path, *, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    return chunk_text(extract_pdf_text(path), chunk_size=chunk_size, overlap=overlap)
