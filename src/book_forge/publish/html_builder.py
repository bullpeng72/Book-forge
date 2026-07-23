"""Book/AOO의 build_book.py를 BookConfig 기반으로 일반화해 이식한 HTML 빌더.

원본은 TOC_STRUCTURE를 손으로 유지해야 했다(새 챕터 추가 시 빌드 스크립트를
직접 고쳐야 함). 여기서는 01_목차.md 매니페스트(ChapterSpec)에서 사이드바
내비게이션을 자동 생성해 그 문제를 없앤다.
"""
from __future__ import annotations

from html import escape as _html_escape
from pathlib import Path

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
"""

HTML_FOOTER = "</body>\n</html>\n"


def chapter_anchor_id(chapter_no: int) -> str:
    return f"ch{chapter_no:02d}"


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


def build_html(config: BookConfig) -> Path:
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

    sidebar = build_toc_sidebar(chapters)
    css = CSS.replace("__ACCENT__", config.accent_color)
    head = HTML_HEAD.replace("__TITLE__", _html_escape(config.title)).replace("__CSS__", css)

    output = head + sidebar + "\n<main>\n" + "\n".join(body_sections) + "\n</main>\n" + HTML_FOOTER

    config.outputs_dir.mkdir(parents=True, exist_ok=True)
    config.html_output_path.write_text(output, encoding="utf-8")
    return config.html_output_path
