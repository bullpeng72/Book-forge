"""Book/AOO의 build_book.py md_to_html()/_rewrite_img_paths_for_book()을 이식한
마크다운 변환 엔진 — 새 판정/변환 로직이 아니라 검증된 기존 로직의 재사용이다.

``@@HTML_START@@ / @@HTML_END@@``, ```` ```mermaid ````, blockquote 내부 fenced
code block을 표준 markdown 파서가 깨뜨리지 않도록 사전 추출 → 변환 → 복원하는
3단계 패턴은 원본(agent-evaluator 레포 Media/Book/build_book.py)과 동일하다.
"""
from __future__ import annotations

import base64
import mimetypes
import re
from html import escape as _html_escape
from pathlib import Path

import markdown as md_lib

_IMG_MIME_OVERRIDES = {".svg": "image/svg+xml"}
_TIP_START_PAT = re.compile(r"^[\s]*(?:👨‍💻|📊|🔧|🚨|💡)")


def md_to_html(text: str) -> str:
    """mermaid / raw-HTML 블록을 보존하면서 markdown → HTML 변환."""
    saved_blocks: list[tuple[str, str]] = []

    def extract_html_block(m: re.Match) -> str:
        saved_blocks.append(("custom_html", m.group(1).strip()))
        return f"@@BLOCK_{len(saved_blocks) - 1}@@"

    text = re.sub(
        r"@@HTML_START@@\s*\n(.*?)@@HTML_END@@", extract_html_block, text, flags=re.DOTALL
    )

    def extract_mermaid(m: re.Match) -> str:
        saved_blocks.append(("mermaid", m.group(1)))
        return f"@@BLOCK_{len(saved_blocks) - 1}@@"

    text = re.sub(r"```mermaid\s*\n(.*?)```", extract_mermaid, text, flags=re.DOTALL)

    def extract_bq_code(m: re.Match) -> str:
        lang = (m.group(1) or "").strip()
        body = m.group(2)
        lines: list[str] = []
        for line in body.split("\n"):
            if line.startswith("> "):
                lines.append(line[2:])
            elif line.rstrip() == ">":
                lines.append("")
        code = "\n".join(lines).rstrip("\n")
        escaped = _html_escape(code)
        cls_attr = f' class="language-{lang}"' if lang else ""
        raw_html = f"<pre><code{cls_attr}>{escaped}</code></pre>"
        saved_blocks.append(("html", raw_html))
        return f"@@BLOCK_{len(saved_blocks) - 1}@@"

    text = re.sub(
        r"^> ```(\w*)\n(.*?)^> ```\s*$",
        extract_bq_code,
        text,
        flags=re.MULTILINE | re.DOTALL,
    )

    converter = md_lib.Markdown(
        extensions=["fenced_code", "tables", "toc", "attr_list", "def_list", "nl2br", "sane_lists"],
        extension_configs={"toc": {"permalink": False}},
    )
    html = converter.convert(text)

    def restore_block(m: re.Match) -> str:
        idx = int(m.group(1))
        kind, content = saved_blocks[idx]
        if kind == "mermaid":
            return f'<div class="mermaid" data-lf-preserve="mermaid">{content}</div>'
        if kind == "custom_html":
            if content.strip().startswith("<style"):
                return content
            return f'<div class="lf-html-block" data-lf-preserve="html">{content}</div>'
        return content  # blockquote 내 코드 블록 등 — 그대로 반환

    html = re.sub(r"<p>\s*@@BLOCK_(\d+)@@\s*</p>", restore_block, html)
    html = re.sub(r"<p>\s*@@BLOCK_(\d+)@@\s*<br\s*/?>\s*</p>", restore_block, html)
    html = re.sub(r"@@BLOCK_(\d+)@@", restore_block, html)

    def _split_blockquote(m: re.Match) -> str:
        inner = m.group(1)
        segs = re.split(r"(?=<p[\s>])", inner)
        bq_buf: list[str] = []
        tip_buf: list[str] = []
        result: list[str] = []

        def _flush_bq() -> None:
            if bq_buf:
                result.append(f"<blockquote>{''.join(bq_buf)}</blockquote>")
                bq_buf.clear()

        def _flush_tip() -> None:
            if tip_buf:
                result.append(f'<div class="tip-box">{"".join(tip_buf)}</div>')
                tip_buf.clear()

        for seg in segs:
            if not seg.strip():
                continue
            plain = re.sub(r"<[^>]+>", "", seg).strip()
            if _TIP_START_PAT.match(plain):
                _flush_bq()
                tip_buf.append(seg)
            else:
                _flush_tip()
                bq_buf.append(seg)

        _flush_bq()
        _flush_tip()
        return "\n".join(result) if result else m.group(0)

    html = re.sub(r"<blockquote>(.*?)</blockquote>", _split_blockquote, html, flags=re.DOTALL)

    html = re.sub(r"(<table\b)", r'<div class="table-wrap">\1', html)
    html = re.sub(r"(</table>)", r"\1</div>", html)

    return html


def embed_images_as_data_uri(html_str: str, md_dir: Path) -> str:
    """img src를 base64 data URI로 인라인 임베드해 HTML이 이미지 파일 없이도
    독립적으로(다른 PC로 옮기거나 이메일 첨부만 해도) 열리도록 만든다.

    http(s)://, data:, file://, # 로 시작하는 src는 이미 절대/인라인이므로 그대로 둔다.
    """

    def _to_data_uri(m: re.Match) -> str:
        src = m.group(1)
        if src.startswith(("http://", "https://", "data:", "file://", "#")):
            return m.group(0)
        abs_path = (md_dir / src).resolve()
        if not abs_path.is_file():
            return m.group(0)
        mime = (
            _IMG_MIME_OVERRIDES.get(abs_path.suffix.lower())
            or mimetypes.guess_type(abs_path.name)[0]
            or "application/octet-stream"
        )
        encoded = base64.b64encode(abs_path.read_bytes()).decode("ascii")
        return f'src="data:{mime};base64,{encoded}"'

    return re.sub(r'src="([^"]+)"', _to_data_uri, html_str)
