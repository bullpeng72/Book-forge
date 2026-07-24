"""html_builder.py — build_html() 종단 테스트 (fixture 프로젝트, LLM 호출 없음)."""
from pathlib import Path

from book_forge.publish.config import BookConfig
from book_forge.publish.html_builder import build_html, build_index_section, build_title_page


def test_build_html_produces_self_contained_file(sample_project: Path) -> None:
    config = BookConfig(project_dir=sample_project, title="샘플 도서")
    out_path = build_html(config)

    assert out_path.exists()
    assert out_path.parent == sample_project / "outputs"

    html = out_path.read_text(encoding="utf-8")
    assert "<title>샘플 도서</title>" in html
    assert 'id="ch01"' in html and 'id="ch02"' in html
    assert "서론" in html and "환경 설정" in html
    assert "data:image/png;base64," in html  # 이미지가 인라인 임베드됐는지
    assert 'href="#ch01"' in html  # 사이드바 링크
    assert "mermaid@10" in html  # CDN 스크립트 포함


def test_build_html_marks_missing_chapter(sample_project: Path) -> None:
    (sample_project / "Part_1_기초" / "Chapter_02_환경_설정.md").unlink()
    config = BookConfig(project_dir=sample_project, title="샘플 도서")
    out_path = build_html(config)
    html = out_path.read_text(encoding="utf-8")
    assert "챕터 파일 없음" in html


# ── 표지 페이지(일반 능력 AI) ────────────────────────────────────────────────


def test_build_title_page_empty_when_no_front_matter() -> None:
    config = BookConfig(project_dir=Path("/nonexistent"), title="샘플 도서")
    assert build_title_page(config) == ""


def test_build_title_page_includes_author_edition_license() -> None:
    config = BookConfig(
        project_dir=Path("/nonexistent"), title="샘플 도서",
        author="홍길동", edition="1판", license_notice="CC BY-NC 4.0",
    )
    html = build_title_page(config)
    assert '<section class="title-page">' in html
    assert "<h1>샘플 도서</h1>" in html
    assert '<p class="author">홍길동</p>' in html
    assert '<p class="edition">1판</p>' in html
    assert '<p class="license">CC BY-NC 4.0</p>' in html


def test_build_title_page_escapes_html(tmp_path: Path) -> None:
    config = BookConfig(project_dir=tmp_path, title="샘플", author="<script>alert(1)</script>")
    html = build_title_page(config)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_build_html_includes_title_page_when_author_given(sample_project: Path) -> None:
    config = BookConfig(project_dir=sample_project, title="샘플 도서", author="홍길동")
    out_path = build_html(config)
    html = out_path.read_text(encoding="utf-8")
    assert '<section class="title-page">' in html
    assert '<p class="author">홍길동</p>' in html


def test_build_html_omits_title_page_without_front_matter(sample_project: Path) -> None:
    config = BookConfig(project_dir=sample_project, title="샘플 도서")
    out_path = build_html(config)
    html = out_path.read_text(encoding="utf-8")
    assert 'class="title-page"' not in html


# ── 찾아보기(색인, 일반 능력 AL) ──────────────────────────────────────────────


def test_build_index_section_empty_when_no_entries() -> None:
    assert build_index_section([]) == ""


def test_build_html_omits_index_by_default(sample_project: Path) -> None:
    config = BookConfig(project_dir=sample_project, title="샘플 도서")
    out_path = build_html(config)
    html = out_path.read_text(encoding="utf-8")
    assert 'class="book-index"' not in html


def test_build_html_includes_index_when_flag_given(sample_project: Path) -> None:
    (sample_project / "Part_1_기초" / "Chapter_01_서론.md").write_text(
        "# Chapter 01: 서론\n\n`SampleTracker`를 소개한다.\n", encoding="utf-8"
    )
    config = BookConfig(project_dir=sample_project, title="샘플 도서")
    out_path = build_html(config, with_index=True)
    html = out_path.read_text(encoding="utf-8")
    assert 'class="book-index"' in html
    assert "SampleTracker" in html
    assert 'href="#ch01"' in html.split('id="book-index"')[1]  # 색인 항목이 실제 챕터 앵커를 가리킴


def test_build_html_with_index_but_no_terms_omits_section(sample_project: Path) -> None:
    config = BookConfig(project_dir=sample_project, title="샘플 도서")
    out_path = build_html(config, with_index=True)
    html = out_path.read_text(encoding="utf-8")
    assert 'class="book-index"' not in html
