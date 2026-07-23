"""BookConfig — 퍼블리싱(HTML/PDF/Slide) 엔진에 공통으로 전달하는 설정.

Book/AOO의 build_book.py/build_pdf_chapters.py가 BOOK_DIR/OUTPUT_FILE 등을
모듈 전역 상수로 하드코딩해 사실상 도서 하나당 스크립트 한 벌을 복붙 유지하던
문제를, 프로젝트마다 인스턴스 하나로 대체한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from book_forge.models import slugify


@dataclass
class BookConfig:
    project_dir: Path
    title: str
    accent_color: str = "#1a237e"

    @property
    def title_slug(self) -> str:
        return slugify(self.title)

    @property
    def toc_path(self) -> Path:
        return self.project_dir / "01_목차.md"

    @property
    def proposal_path(self) -> Path:
        return self.project_dir / "00_기획안.md"

    @property
    def outputs_dir(self) -> Path:
        return self.project_dir / "outputs"

    @property
    def html_output_path(self) -> Path:
        return self.outputs_dir / f"{self.title_slug}.html"

    @property
    def pdf_output_dir(self) -> Path:
        return self.outputs_dir / "pdf"
