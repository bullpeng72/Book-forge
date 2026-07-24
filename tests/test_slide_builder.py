"""slide_builder.py — split_chapter_into_sections()/render_slide_html()/build_slides() 테스트.

build_slides()는 실제 LLM 대신 결정론적 fake LLM을 주입해 오프라인·빠르게 검증한다.
"""
from pathlib import Path

from book_forge.agents.slide_condenser import SlideContent
from book_forge.eval.monitor import build_book_monitor
from book_forge.publish.config import BookConfig
from book_forge.publish.slide_builder import (
    build_slides,
    extract_code_blocks,
    render_code_slide_html,
    render_mermaid_slide_html,
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


# 일반 능력 R — 헤딩이 하나도 없는 챕터(실측: diagram content_type이 헤딩 없이
# 코드 펜스로 바로 시작)도 챕터 제목을 헤딩 삼아 최소 1개 섹션을 만들어야 한다.
def test_split_chapter_into_sections_falls_back_when_no_headings() -> None:
    md = "```mermaid\ngraph TD\n  A --> B\n```\n\n다이어그램 설명입니다."
    sections = split_chapter_into_sections(md, fallback_heading="다이어그램 챕터")
    assert len(sections) == 1
    assert sections[0][0] == "다이어그램 챕터"
    assert "graph TD" in sections[0][1]


def test_split_chapter_into_sections_empty_body_with_no_headings_returns_nothing() -> None:
    assert split_chapter_into_sections("   \n\n  ", fallback_heading="제목") == []


def test_split_chapter_into_sections_fallback_default_heading_when_unset() -> None:
    sections = split_chapter_into_sections("헤딩 없는 본문입니다.")
    assert sections[0][0] == "슬라이드"


# 일반 능력 P — 코드/다이어그램 펜스는 LLM에게 넘기기 전에 분리돼야 한다.
def test_extract_code_blocks_separates_prose_and_python_code() -> None:
    body = "설명 문단입니다.\n\n```python\ndef foo():\n    return 1\n```\n\n마무리 문단."
    prose, blocks = extract_code_blocks(body)
    assert "설명 문단" in prose
    assert "마무리 문단" in prose
    assert "def foo" not in prose
    assert blocks == [("python", "def foo():\n    return 1")]


def test_extract_code_blocks_handles_multiple_fences_and_mermaid() -> None:
    body = "```mermaid\ngraph TD\n  A --> B\n```\n\n텍스트\n\n```python\nx = 1\n```"
    prose, blocks = extract_code_blocks(body)
    assert prose == "텍스트"
    assert blocks == [("mermaid", "graph TD\n  A --> B"), ("python", "x = 1")]


def test_extract_code_blocks_no_fences_returns_body_unchanged() -> None:
    prose, blocks = extract_code_blocks("그냥 프로즈 문단입니다.")
    assert prose == "그냥 프로즈 문단입니다."
    assert blocks == []


def test_extract_code_blocks_untagged_fence_has_empty_language() -> None:
    prose, blocks = extract_code_blocks("```\nplain text block\n```")
    assert blocks == [("", "plain text block")]


def test_render_code_slide_html_escapes_and_tags_language() -> None:
    html = render_code_slide_html("python", "x = '<script>'")
    assert '<pre><code class="language-python">' in html
    assert "&lt;script&gt;" in html  # 이스케이프됨 — 실제 <script> 태그가 주입되지 않음


def test_render_code_slide_html_no_language_omits_class_attr() -> None:
    html = render_code_slide_html("", "plain text")
    assert "<pre><code>plain text</code></pre>" in html


def test_render_mermaid_slide_html_wraps_in_mermaid_div() -> None:
    html = render_mermaid_slide_html("graph TD\n  A --> B")
    assert '<div class="mermaid">' in html
    assert "graph TD" in html


def test_build_slides_preserves_code_blocks_verbatim(tmp_path: Path) -> None:
    # 일반 능력 P 종단 검증: 코드가 포함된 챕터로 슬라이드를 만들면 실제 코드가
    # (LLM 요약이 아니라) 원문 그대로 <pre><code>에 남아있어야 한다.
    project_dir = tmp_path / "code-project"
    part_dir = project_dir / "Part_1_기초"
    part_dir.mkdir(parents=True)
    (project_dir / "01_목차.md").write_text(
        "```toc\n1|기초|1|코드 챕터\n```\n", encoding="utf-8"
    )
    (part_dir / "Chapter_01_코드_챕터.md").write_text(
        "# Chapter 01: 코드 챕터\n\n## 예제\n\n설명 문단입니다.\n\n"
        "```python\ndef distinctive_marker():\n    return 42\n```\n",
        encoding="utf-8",
    )

    config = BookConfig(project_dir=project_dir, title="코드 도서")
    monitor = build_book_monitor(output_dir=str(project_dir / "eval_results"))
    out_path = build_slides(config, FakeLLM(), monitor)

    html = out_path.read_text(encoding="utf-8")
    assert "def distinctive_marker" in html
    assert '<pre><code class="language-python">' in html
    assert "highlight.min.js" in html
    assert "mermaid.min.js" in html


def test_build_slides_diagram_only_chapter_produces_at_least_one_slide(tmp_path: Path) -> None:
    # 일반 능력 R 종단 검증: 헤딩 없이 코드 펜스로 바로 시작하는 챕터도 슬라이드가
    # 0장으로 조용히 끝나지 않고 최소 1개(제목 슬라이드) + 다이어그램 슬라이드가 나와야 한다.
    project_dir = tmp_path / "diagram-project"
    part_dir = project_dir / "Part_1_기초"
    part_dir.mkdir(parents=True)
    (project_dir / "01_목차.md").write_text(
        "```toc\n1|기초|1|다이어그램 챕터|diagram\n```\n", encoding="utf-8"
    )
    (part_dir / "Chapter_01_다이어그램_챕터.md").write_text(
        "```mermaid\ngraph TD\n  A --> B\n```\n", encoding="utf-8"
    )

    config = BookConfig(project_dir=project_dir, title="다이어그램 도서")
    monitor = build_book_monitor(output_dir=str(project_dir / "eval_results"))
    out_path = build_slides(config, FakeLLM(), monitor)

    html = out_path.read_text(encoding="utf-8")
    assert html.count("<section") >= 2  # 제목 슬라이드 + 다이어그램 슬라이드
    assert '<div class="mermaid">' in html
    assert "graph TD" in html
