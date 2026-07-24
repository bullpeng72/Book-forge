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


# ── 표지 페이지 PDF(일반 능력 AI) ────────────────────────────────────────────


def test_build_pdf_includes_title_page_when_author_given(sample_project: Path) -> None:
    config = BookConfig(project_dir=sample_project, title="샘플 도서", author="홍길동")
    paths = build_pdf(config)

    assert len(paths) == 3  # 표지 1 + 챕터 2
    title_page = paths[0]
    assert title_page.name == "00_표지.pdf"
    assert title_page.exists()
    assert title_page.stat().st_size > 1000


def test_build_pdf_omits_title_page_without_front_matter(sample_project: Path) -> None:
    config = BookConfig(project_dir=sample_project, title="샘플 도서")
    paths = build_pdf(config)
    assert len(paths) == 2  # 챕터만, 표지 없음
    assert all(p.name != "00_표지.pdf" for p in paths)


def test_build_pdf_single_chapter_mode_omits_title_page(sample_project: Path) -> None:
    # chapter_no를 지정한 단일 챕터 재생성 모드에서는 표지를 다시 안 만든다.
    config = BookConfig(project_dir=sample_project, title="샘플 도서", author="홍길동")
    paths = build_pdf(config, chapter_no=1)
    assert len(paths) == 1
    assert "Chapter_01" in paths[0].name


# ── 찾아보기(색인) PDF(일반 능력 AL) ─────────────────────────────────────────


def test_build_pdf_with_index_adds_index_pdf_when_terms_found(sample_project: Path) -> None:
    (sample_project / "Part_1_기초" / "Chapter_01_서론.md").write_text(
        "# Chapter 01: 서론\n\n`SampleTracker`를 소개한다.\n", encoding="utf-8"
    )
    config = BookConfig(project_dir=sample_project, title="샘플 도서")
    paths = build_pdf(config, with_index=True)

    assert len(paths) == 3  # 챕터 2 + 찾아보기 1
    index_path = paths[-1]
    assert index_path.name == "99_찾아보기.pdf"
    assert index_path.exists()
    assert index_path.stat().st_size > 1000


def test_build_pdf_without_index_flag_omits_index_pdf(sample_project: Path) -> None:
    (sample_project / "Part_1_기초" / "Chapter_01_서론.md").write_text(
        "# Chapter 01: 서론\n\n`SampleTracker`를 소개한다.\n", encoding="utf-8"
    )
    config = BookConfig(project_dir=sample_project, title="샘플 도서")
    paths = build_pdf(config)
    assert all(p.name != "99_찾아보기.pdf" for p in paths)


def test_build_pdf_with_index_but_no_terms_omits_index_pdf(sample_project: Path) -> None:
    config = BookConfig(project_dir=sample_project, title="샘플 도서")
    paths = build_pdf(config, with_index=True)
    assert all(p.name != "99_찾아보기.pdf" for p in paths)


def test_build_pdf_single_chapter_mode_ignores_with_index(sample_project: Path) -> None:
    config = BookConfig(project_dir=sample_project, title="샘플 도서")
    paths = build_pdf(config, chapter_no=1, with_index=True)
    assert len(paths) == 1
    assert "Chapter_01" in paths[0].name
