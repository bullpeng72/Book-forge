"""pdf_builder.py — build_pdf() 통합 테스트. 실제 Playwright/Chromium을 띄운다.

playwright 미설치([pdf] extra 없음) 환경에서는 자동 skip.
"""
from pathlib import Path

import pytest

pytest.importorskip("playwright")

from book_forge.publish.config import BookConfig  # noqa: E402
from book_forge.publish.pdf_builder import build_pdf  # noqa: E402


def test_build_pdf_creates_pdf_per_chapter(sample_project: Path) -> None:
    config = BookConfig(project_dir=sample_project, title="샘플 도서")
    paths = build_pdf(config)

    assert len(paths) == 2
    for p in paths:
        assert p.exists()
        assert p.suffix == ".pdf"
        assert p.stat().st_size > 1000  # 빈 PDF가 아님


def test_build_pdf_single_chapter_filter(sample_project: Path) -> None:
    config = BookConfig(project_dir=sample_project, title="샘플 도서")
    paths = build_pdf(config, chapter_no=1)
    assert len(paths) == 1
    assert "Chapter_01" in paths[0].name


def test_build_pdf_unknown_chapter_raises(sample_project: Path) -> None:
    config = BookConfig(project_dir=sample_project, title="샘플 도서")
    with pytest.raises(ValueError, match="찾을 수 없습니다"):
        build_pdf(config, chapter_no=99)
