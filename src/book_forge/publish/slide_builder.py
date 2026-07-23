"""마크다운 챕터 → Reveal.js 발표자료.

Lecture_forge의 `improve --to-slides`와 문제의식은 같다(섹션별 LLM 재작성,
발표자 노트 기본 포함) — 다만 Book-forge 자체 파이프라인(01_목차.md 매니페스트,
공유 PerformanceMonitor)에 맞춰 새로 조립했다.
"""
from __future__ import annotations

from html import escape as _html_escape
from pathlib import Path
from typing import Optional

from agent_evaluator import PerformanceMonitor

from book_forge.agents.slide_condenser import SlideContent, build_condense_section, parse_slide_response
from book_forge.llm.provider import LLM
from book_forge.publish.config import BookConfig
from book_forge.publish.toc_loader import load_toc

REVEAL_HEAD = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@4/dist/reveal.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@4/dist/theme/white.css">
<style>
.reveal h2 { color: __ACCENT__; }
.reveal ul { text-align: left; }
.reveal section.chapter-title h1 { color: __ACCENT__; }
</style>
</head>
<body>
<div class="reveal"><div class="slides">
"""

REVEAL_FOOTER = """
</div></div>
<script src="https://cdn.jsdelivr.net/npm/reveal.js@4/dist/reveal.js"></script>
<script>
Reveal.initialize({ hash: true, slideNumber: true, showNotes: __SHOW_NOTES__ });
</script>
</body>
</html>
"""


def split_chapter_into_sections(markdown_text: str) -> list[tuple[str, str]]:
    """H1(챕터 제목)+인트로를 첫 섹션으로, 이후 ``## `` 헤딩마다 섹션을 분리한다.

    Book-forge 챕터 스캐폴드는 `# Chapter NN: 제목` 다음 `## N.M 소제목`
    구조를 쓰므로(IMAGES.md/Book 관례와 동일) 이 가정으로 충분하다.
    """
    lines = markdown_text.splitlines()
    sections: list[tuple[str, list[str]]] = []
    current_heading: Optional[str] = None
    current_body: list[str] = []

    for line in lines:
        if line.startswith("# ") and current_heading is None:
            current_heading = line[2:].strip()
            continue
        if line.startswith("## "):
            if current_heading is not None:
                sections.append((current_heading, current_body))
            current_heading = line[3:].strip()
            current_body = []
            continue
        current_body.append(line)

    if current_heading is not None:
        sections.append((current_heading, current_body))

    return [(h, "\n".join(b).strip()) for h, b in sections if "\n".join(b).strip()]


def render_slide_html(content: SlideContent, *, include_notes: bool, is_title_slide: bool = False) -> str:
    bullets_html = "\n".join(f"<li>{_html_escape(b)}</li>" for b in content.bullets)
    notes_html = (
        f'<aside class="notes">{_html_escape(content.notes)}</aside>'
        if include_notes and content.notes
        else ""
    )
    heading_tag = "h1" if is_title_slide else "h2"
    css_class = ' class="chapter-title"' if is_title_slide else ""
    return (
        f"<section{css_class}>\n"
        f"<{heading_tag}>{_html_escape(content.title)}</{heading_tag}>\n"
        f"<ul>\n{bullets_html}\n</ul>\n"
        f"{notes_html}\n"
        f"</section>\n"
    )


def build_slides(
    config: BookConfig,
    llm: LLM,
    monitor: PerformanceMonitor,
    *,
    chapter_no: Optional[int] = None,
    include_notes: bool = True,
) -> Path:
    chapters = load_toc(config.project_dir)
    if chapter_no is not None:
        chapters = [rc for rc in chapters if rc.spec.chapter_no == chapter_no]
        if not chapters:
            raise ValueError(f"챕터 번호 {chapter_no}를 목차에서 찾을 수 없습니다.")

    condense_section = build_condense_section(llm, monitor)

    slide_sections: list[str] = []
    for rc in chapters:
        if not rc.exists:
            continue
        raw_md = rc.path.read_text(encoding="utf-8")
        sections = split_chapter_into_sections(raw_md)
        for idx, (heading, body) in enumerate(sections):
            raw_response = condense_section(heading=heading, body=body, ground_truth=heading)
            content = parse_slide_response(raw_response, fallback_title=heading)
            slide_sections.append(
                render_slide_html(content, include_notes=include_notes, is_title_slide=(idx == 0))
            )

    head = REVEAL_HEAD.replace("__TITLE__", _html_escape(config.title)).replace(
        "__ACCENT__", config.accent_color
    )
    footer = REVEAL_FOOTER.replace("__SHOW_NOTES__", "true" if include_notes else "false")
    output = head + "\n".join(slide_sections) + footer

    config.outputs_dir.mkdir(parents=True, exist_ok=True)
    out_path = config.outputs_dir / f"{config.title_slug}_slides.html"
    out_path.write_text(output, encoding="utf-8")
    return out_path
