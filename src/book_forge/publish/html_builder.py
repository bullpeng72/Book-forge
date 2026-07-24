"""Book/AOO의 build_book.py를 BookConfig 기반으로 일반화해 이식한 HTML 빌더.

원본은 TOC_STRUCTURE를 손으로 유지해야 했다(새 챕터 추가 시 빌드 스크립트를
직접 고쳐야 함). 여기서는 01_목차.md 매니페스트(ChapterSpec)에서 사이드바
내비게이션을 자동 생성해 그 문제를 없앤다.
"""
from __future__ import annotations

from html import escape as _html_escape
from pathlib import Path

from book_forge.publish.book_index import IndexEntry, build_index_entries
from book_forge.publish.config import BookConfig
from book_forge.publish.markdown_engine import embed_images_as_data_uri, md_to_html
from book_forge.publish.toc_loader import load_toc

HTML_HEAD = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>__TITLE__</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script>mermaid.initialize({ startOnLoad: true, theme: 'default' });</script>
<style>
__CSS__
</style>
</head>
<body>
<script>hljs.highlightAll();</script>
"""

CSS = """
:root { --accent: __ACCENT__; }
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
       color: #1a1a1a; display: flex; }
nav.sidebar { width: 260px; flex-shrink: 0; height: 100vh; overflow-y: auto; position: sticky; top: 0;
              background: #f7f7f9; border-right: 1px solid #e0e0e0; padding: 16px 12px; }
nav.sidebar a { display: block; padding: 4px 8px; color: #333; text-decoration: none; font-size: 14px;
                border-radius: 4px; }
nav.sidebar a.part-heading { font-weight: 700; color: var(--accent); margin-top: 12px; }
nav.sidebar a.chapter-link { padding-left: 16px; }
nav.sidebar a:hover { background: #eee; }
main { flex: 1; max-width: 860px; margin: 0 auto; padding: 40px 32px 120px; }
section.chapter-section { margin-bottom: 64px; padding-top: 24px; border-top: 1px solid #eee; }
img { max-width: 100%; height: auto; display: block; margin: 12px auto; }
.table-wrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #ddd; padding: 6px 10px; font-size: 14px; }
.tip-box { background: #fff8e1; border-left: 4px solid #ffb300; padding: 10px 16px; margin: 16px 0; }
blockquote { border-left: 4px solid #ccc; margin: 16px 0; padding: 4px 16px; color: #555; }
pre { background: #282c34; color: #eee; padding: 12px; border-radius: 6px; overflow-x: auto; }
code { font-family: "SFMono-Regular", Menlo, monospace; }
section.title-page { text-align: center; padding: 120px 32px 80px; border-bottom: 1px solid #eee;
                      margin-bottom: 48px; }
section.title-page h1 { font-size: 2.4rem; color: var(--accent); margin: 0 0 24px; }
section.title-page .author { font-size: 1.1rem; margin: 0 0 8px; }
section.title-page .edition { font-size: 0.9rem; color: #666; margin: 0 0 32px; }
section.title-page .license { font-size: 0.8rem; color: #888; white-space: pre-wrap; }
section.book-index { margin-top: 64px; padding-top: 24px; border-top: 1px solid #eee; }
section.book-index dt { font-family: "SFMono-Regular", Menlo, monospace; font-weight: 700; margin-top: 10px; }
section.book-index dd { margin: 2px 0 0 16px; }
section.book-index dd a { color: var(--accent); text-decoration: none; margin-right: 8px; }
section.book-index dd a:hover { text-decoration: underline; }
"""

HTML_FOOTER = "</body>\n</html>\n"


def chapter_anchor_id(chapter_no: int) -> str:
    return f"ch{chapter_no:02d}"


def build_title_page(config: BookConfig) -> str:
    """표지 페이지 HTML을 조립한다(일반 능력 AI). 저자/저작권/판이 전부
    비어 있으면 빈 문자열을 반환한다 — 호출부가 아예 섹션을 안 붙이게.

    LLM을 호출하지 않는다 — 저자가 CLI에 입력한 값을 문자열 조립만 해서
    보여준다(창작 대상이 아니므로 환각 위험 자체가 없음).
    """
    if not (config.author or config.license_notice or config.edition):
        return ""
    parts = [f'<h1>{_html_escape(config.title)}</h1>']
    if config.author:
        parts.append(f'<p class="author">{_html_escape(config.author)}</p>')
    if config.edition:
        parts.append(f'<p class="edition">{_html_escape(config.edition)}</p>')
    if config.license_notice:
        parts.append(f'<p class="license">{_html_escape(config.license_notice)}</p>')
    return '<section class="title-page">\n' + "\n".join(parts) + "\n</section>"


def build_index_section(entries: list[IndexEntry], *, with_links: bool = True) -> str:
    """찾아보기 섹션 HTML을 조립한다(일반 능력 AL). 항목이 없으면 빈 문자열.

    with_links=False는 PDF 경로 전용 — 챕터별 개별 PDF 파일 구조라 다른 챕터
    PDF를 가리키는 앵커가 실제로 존재하지 않는다. HTML(단일 파일)에서만 실제
    앵커 링크를 건다(SPEC이 명시한 "HTML은 챕터 링크로 대체" 그대로).
    """
    if not entries:
        return ""
    parts = ['<section class="book-index" id="book-index">', "<h2>찾아보기</h2>", "<dl>"]
    for entry in entries:
        parts.append(f"<dt>{_html_escape(entry.term)}</dt>")
        if with_links:
            locations = " ".join(
                f'<a href="#{chapter_anchor_id(rc.spec.chapter_no)}">'
                f'Ch{rc.spec.chapter_no:02d}. {_html_escape(rc.spec.chapter_title)}</a>'
                for rc in entry.chapters
            )
        else:
            locations = ", ".join(
                f'Ch{rc.spec.chapter_no:02d}. {_html_escape(rc.spec.chapter_title)}'
                for rc in entry.chapters
            )
        parts.append(f"<dd>{locations}</dd>")
    parts.append("</dl>")
    parts.append("</section>")
    return "\n".join(parts)


def build_toc_sidebar(chapters) -> str:
    lines: list[str] = ['<nav class="sidebar">']
    last_part = None
    for rc in chapters:
        spec = rc.spec
        if spec.part_no != last_part:
            lines.append(
                f'<a class="part-heading">Part {spec.part_no}. {_html_escape(spec.part_title)}</a>'
            )
            last_part = spec.part_no
        anchor = chapter_anchor_id(spec.chapter_no)
        lines.append(
            f'<a class="chapter-link" href="#{anchor}">Ch{spec.chapter_no:02d}. '
            f'{_html_escape(spec.chapter_title)}</a>'
        )
    lines.append("</nav>")
    return "\n".join(lines)


def build_html(config: BookConfig, *, with_index: bool = False) -> Path:
    chapters = load_toc(config.project_dir)

    body_sections: list[str] = []
    for rc in chapters:
        anchor = chapter_anchor_id(rc.spec.chapter_no)
        if not rc.exists:
            body_sections.append(
                f'<section class="chapter-section" id="{anchor}">'
                f"<p>⚠️ 챕터 파일 없음: {rc.path.name}</p></section>"
            )
            continue
        raw = rc.path.read_text(encoding="utf-8")
        html_body = md_to_html(raw)
        html_body = embed_images_as_data_uri(html_body, rc.path.parent)
        body_sections.append(f'<section class="chapter-section" id="{anchor}">\n{html_body}\n</section>')

    index_section = build_index_section(build_index_entries(chapters)) if with_index else ""

    sidebar = build_toc_sidebar(chapters)
    css = CSS.replace("__ACCENT__", config.accent_color)
    head = HTML_HEAD.replace("__TITLE__", _html_escape(config.title)).replace("__CSS__", css)
    title_page = build_title_page(config)

    output = (
        head + sidebar + "\n<main>\n" + title_page + "\n"
        + "\n".join(body_sections) + "\n" + index_section + "\n</main>\n" + HTML_FOOTER
    )

    config.outputs_dir.mkdir(parents=True, exist_ok=True)
    config.html_output_path.write_text(output, encoding="utf-8")
    return config.html_output_path
