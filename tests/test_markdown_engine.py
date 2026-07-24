"""markdown_engine.py — md_to_html() / embed_images_as_data_uri() 테스트."""
import base64
from pathlib import Path

from book_forge.publish.markdown_engine import (
    embed_images_as_data_uri,
    guess_image_media_type,
    md_to_html,
    rewrite_images_for_epub,
)


def test_md_to_html_basic_heading_and_paragraph() -> None:
    # toc 확장이 heading에 id를 자동 부여하므로 태그+본문 텍스트만 확인한다.
    html = md_to_html("# 제목\n\n본문입니다.")
    assert "<h1" in html and ">제목</h1>" in html
    assert "<p>본문입니다.</p>" in html


def test_md_to_html_preserves_html_start_block() -> None:
    md = "본문\n\n@@HTML_START@@\n<div class=\"custom\">raw</div>\n@@HTML_END@@\n\n다음 문단"
    html = md_to_html(md)
    assert '<div class="lf-html-block"' in html
    assert '<div class="custom">raw</div>' in html


def test_md_to_html_preserves_mermaid_block() -> None:
    md = "```mermaid\nflowchart TD\nA --> B\n```"
    html = md_to_html(md)
    assert '<div class="mermaid"' in html
    assert "flowchart TD" in html


def test_md_to_html_wraps_table_for_scroll() -> None:
    md = "| a | b |\n|---|---|\n| 1 | 2 |"
    html = md_to_html(md)
    assert '<div class="table-wrap">' in html
    assert "<table>" in html


def test_md_to_html_tip_box_split_from_blockquote() -> None:
    md = "> 일반 참고\n\n> 💡 팁입니다"
    html = md_to_html(md)
    assert "<blockquote>" in html
    assert '<div class="tip-box">' in html


def test_embed_images_as_data_uri_inlines_local_png(tmp_path) -> None:
    img_path = tmp_path / "images" / "sample.png"
    img_path.parent.mkdir()
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    img_path.write_bytes(png_bytes)

    html = '<img src="./images/sample.png" alt="샘플">'
    result = embed_images_as_data_uri(html, tmp_path)

    assert "data:image/png;base64," in result
    assert "./images/sample.png" not in result


def test_embed_images_as_data_uri_leaves_missing_file_untouched() -> None:
    html = '<img src="./images/missing.png">'
    result = embed_images_as_data_uri(html, __import__("pathlib").Path("/nonexistent"))
    assert result == html


def test_embed_images_as_data_uri_leaves_remote_url_untouched() -> None:
    html = '<img src="https://example.com/a.png">'
    result = embed_images_as_data_uri(html, __import__("pathlib").Path("/tmp"))
    assert result == html


# ── EPUB 전용 이미지 재작성(일반 능력 AJ) ────────────────────────────────────


def test_guess_image_media_type_known_and_svg_override() -> None:
    assert guess_image_media_type("a.png") == "image/png"
    assert guess_image_media_type("a.svg") == "image/svg+xml"
    assert guess_image_media_type("a.unknownext") == "application/octet-stream"


def test_rewrite_images_for_epub_rewrites_src_and_collects_file(tmp_path: Path) -> None:
    img_path = tmp_path / "images" / "sample.png"
    img_path.parent.mkdir()
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    img_path.write_bytes(png_bytes)

    html = '<img src="./images/sample.png" alt="샘플">'
    rewritten, collected = rewrite_images_for_epub(html, tmp_path, prefix="chap01")

    assert 'src="images/chap01_sample.png"' in rewritten
    assert collected == [(img_path.resolve(), "chap01_sample.png")]


def test_rewrite_images_for_epub_leaves_missing_and_remote_untouched(tmp_path: Path) -> None:
    html = '<img src="./images/missing.png"><img src="https://example.com/a.png">'
    rewritten, collected = rewrite_images_for_epub(html, tmp_path, prefix="chap01")
    assert rewritten == html
    assert collected == []
