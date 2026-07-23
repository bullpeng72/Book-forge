"""slide_builder.py — split_chapter_into_sections()/render_slide_html()/build_slides() 테스트.

build_slides()는 실제 LLM 대신 결정론적 fake LLM을 주입해 오프라인·빠르게 검증한다.
"""
from pathlib import Path

from book_forge.agents.slide_condenser import SlideContent
from book_forge.eval.monitor import build_book_monitor
from book_forge.publish.config import BookConfig
from book_forge.publish.slide_builder import (
    build_slides,
    render_slide_html,
    split_chapter_into_sections,
)

CHAPTER_MD = """# Chapter 01: 서론

이 챕터는 도입부입니다.

## 1.1 문제의식

에이전트 평가가 왜 어려운지 설명합니다.

## 1.2 이 책의 구성

각 파트가 무엇을 다루는지 설명합니다.
"""


class FakeLLM:
    model = "fake"

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        return "TITLE: 고정 제목\nBULLET: 고정 항목 1\nBULLET: 고정 항목 2\nNOTES: 고정 노트"


def test_split_chapter_into_sections_separates_h1_intro_and_h2s() -> None:
    sections = split_chapter_into_sections(CHAPTER_MD)
    assert len(sections) == 3
    assert sections[0][0] == "Chapter 01: 서론"
    assert "도입부" in sections[0][1]
    assert sections[1][0] == "1.1 문제의식"
    assert sections[2][0] == "1.2 이 책의 구성"


def test_split_chapter_into_sections_drops_empty_sections() -> None:
    md = "# Chapter 01: 제목\n\n## 1.1 빈 섹션\n\n## 1.2 내용 있음\n\n실제 본문."
    sections = split_chapter_into_sections(md)
    titles = [h for h, _ in sections]
    assert "1.1 빈 섹션" not in titles
    assert "1.2 내용 있음" in titles


def test_render_slide_html_includes_notes_by_default() -> None:
    content = SlideContent(title="제목", bullets=["항목1", "항목2"], notes="발표 노트")
    html = render_slide_html(content, include_notes=True)
    assert "<h2>제목</h2>" in html
    assert "<li>항목1</li>" in html
    assert '<aside class="notes">발표 노트</aside>' in html


def test_render_slide_html_without_notes() -> None:
    content = SlideContent(title="제목", bullets=["항목1"], notes="발표 노트")
    html = render_slide_html(content, include_notes=False)
    assert "notes" not in html


def test_render_slide_html_title_slide_uses_h1() -> None:
    content = SlideContent(title="챕터 제목", bullets=["항목"], notes="")
    html = render_slide_html(content, include_notes=True, is_title_slide=True)
    assert '<section class="chapter-title">' in html
    assert "<h1>챕터 제목</h1>" in html


def test_build_slides_end_to_end_with_fake_llm(sample_project: Path) -> None:
    config = BookConfig(project_dir=sample_project, title="샘플 도서")
    monitor = build_book_monitor(output_dir=str(sample_project / "eval_results"))

    out_path = build_slides(config, FakeLLM(), monitor, include_notes=True)

    assert out_path.exists()
    html = out_path.read_text(encoding="utf-8")
    assert "reveal.js" in html
    assert html.count("고정 제목") >= 2  # 챕터 1, 2 각각 최소 1개 섹션
    assert '<aside class="notes">고정 노트</aside>' in html


def test_build_slides_chapter_filter(sample_project: Path) -> None:
    config = BookConfig(project_dir=sample_project, title="샘플 도서")
    monitor = build_book_monitor(output_dir=str(sample_project / "eval_results"))

    out_path = build_slides(config, FakeLLM(), monitor, chapter_no=1)
    html = out_path.read_text(encoding="utf-8")
    assert html.count("<section") == 1  # Chapter 1은 본문 없이 H1만 있어 섹션 1개
