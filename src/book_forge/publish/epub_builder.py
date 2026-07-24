"""EPUB 3 컨테이너 조립 (일반 능력 AJ, SPEC.md 4부).

실제 전자책 유통(Amazon KDP, 교보문고 e-book 등)은 대부분 EPUB을 요구하는데
Book-forge는 HTML/PDF/Slides만 만들었다 — `publish/` 어디에도 EPUB 개념이
없었다.

SPEC이 명시한 대로 순수 zip 아카이브 포맷이라 Playwright 같은 무거운 브라우저
의존성이 필요 없다(PDF 빌드와 다른 지점) — 표준 라이브러리 `zipfile`만으로
조립한다. `md_to_html()`(HTML/PDF와 동일 변환 엔진, 새 파서 아님)을 그대로
재사용하되, 이미지는 base64 인라인이 아니라 EPUB 컨테이너 안에 실제 파일로
포함해야 한다(`markdown_engine.rewrite_images_for_epub()` — HTML의
`embed_images_as_data_uri()`와 대응되는 EPUB 전용 짝).

**알려진 한계**: mermaid 다이어그램/커스텀 HTML 블록(`@@HTML_START@@`)은
원본 텍스트를 그대로 삽입한다(HTML/PDF와 동일) — EPUB 리더 대부분은 리플로우
가능한(reflowable) 컨텐츠에서 JavaScript를 실행하지 않으므로 mermaid.js가
로드돼도 다이어그램은 렌더링되지 않고 원본 그래프 정의 텍스트가 그대로
보인다(PDF의 Mermaid 청크 잘림과 같은 급의 "알려진 한계" — 후속 개선 과제).
다만 EPUB 파일 자체가 깨지지는 않게, 조립된 챕터 XHTML이 well-formed XML이
아니면(raw 블록에 `<`/`&` 등이 섞여 있는 경우) 그 챕터만 escape된 원문
텍스트로 안전하게 대체한다 — 하나의 나쁜 챕터가 전자책 리더에서 파일 전체를
열 수 없게 만드는 것보다 훨씬 낫다.
"""
from __future__ import annotations

import uuid
import xml.etree.ElementTree as ET
import zipfile
from html import escape as _html_escape
from pathlib import Path

from book_forge.publish.config import BookConfig
from book_forge.publish.markdown_engine import (
    guess_image_media_type,
    md_to_html,
    rewrite_images_for_epub,
)
from book_forge.publish.toc_loader import ResolvedChapter, load_toc

_CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

_XHTML_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta charset="utf-8"/>
<title>__TITLE__</title>
</head>
<body>
__BODY__
</body>
</html>
"""


def _chapter_xhtml(title: str, body_html: str) -> str:
    return _XHTML_TEMPLATE.replace("__TITLE__", _html_escape(title)).replace("__BODY__", body_html)


def _safe_id(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in name)


def _well_formed_chapter_xhtml(title: str, body_html: str) -> str:
    """조립한 챕터 XHTML이 well-formed XML인지 확인하고, 아니면 안전하게 대체한다.

    mermaid/커스텀 HTML 원문 블록은 escape되지 않은 채로 삽입되므로(HTML/PDF와
    동일 동작) EPUB 리더가 요구하는 엄격한 XML 파싱을 항상 통과한다는 보장이
    없다 — 챕터 하나 때문에 EPUB 파일 전체가 안 열리는 것을 막는다.
    """
    xhtml = _chapter_xhtml(title, body_html)
    try:
        ET.fromstring(xhtml)
        return xhtml
    except ET.ParseError:
        fallback_body = f"<pre>{_html_escape(body_html)}</pre>"
        return _chapter_xhtml(title, fallback_body)


def _nav_xhtml(book_title: str, chapters: list[tuple[str, str]]) -> str:
    items = "\n".join(f'<li><a href="{item_id}.xhtml">{_html_escape(title)}</a></li>' for item_id, title in chapters)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><meta charset="utf-8"/><title>{_html_escape(book_title)}</title></head>
<body>
<nav epub:type="toc" id="toc">
<h1>{_html_escape(book_title)}</h1>
<ol>
{items}
</ol>
</nav>
</body>
</html>
"""


def _content_opf(
    config: BookConfig, chapters: list[tuple[str, str]], book_uuid: str, image_names: list[str]
) -> str:
    manifest_items = [
        f'<item id="{item_id}" href="{item_id}.xhtml" media-type="application/xhtml+xml"/>'
        for item_id, _title in chapters
    ]
    for name in image_names:
        media_type = guess_image_media_type(name)
        manifest_items.append(f'<item id="img_{_safe_id(name)}" href="images/{name}" media-type="{media_type}"/>')
    spine_items = [f'<itemref idref="{item_id}"/>' for item_id, _title in chapters]
    creator = f"<dc:creator>{_html_escape(config.author)}</dc:creator>" if config.author else ""

    return f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">urn:uuid:{book_uuid}</dc:identifier>
    <dc:title>{_html_escape(config.title)}</dc:title>
    <dc:language>ko</dc:language>
    {creator}
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    {chr(10).join(manifest_items)}
  </manifest>
  <spine>
    {chr(10).join(spine_items)}
  </spine>
</package>
"""


def build_epub(config: BookConfig) -> Path:
    chapters: list[ResolvedChapter] = [rc for rc in load_toc(config.project_dir) if rc.exists]
    if not chapters:
        raise ValueError("빌드할 챕터가 없습니다 (초안이 작성된 챕터가 하나도 없음).")

    book_uuid = str(uuid.uuid4())
    manifest_chapters: list[tuple[str, str]] = []
    chapter_xhtmls: dict[str, str] = {}
    all_images: list[tuple[Path, str]] = []

    for i, rc in enumerate(chapters, start=1):
        item_id = f"chap{i:02d}"
        title = f"Chapter {rc.spec.chapter_no:02d}. {rc.spec.chapter_title}"
        raw = rc.path.read_text(encoding="utf-8")
        html_body = md_to_html(raw)
        html_body, images = rewrite_images_for_epub(html_body, rc.path.parent, item_id)
        all_images.extend(images)
        chapter_xhtmls[item_id] = _well_formed_chapter_xhtml(title, html_body)
        manifest_chapters.append((item_id, title))

    nav_xhtml = _nav_xhtml(config.title, manifest_chapters)
    opf = _content_opf(config, manifest_chapters, book_uuid, [name for _, name in all_images])

    out_path = config.epub_output_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w") as zf:
        # mimetype은 EPUB 스펙상 압축 없이(STORED) 아카이브의 첫 항목이어야 한다.
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", _CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/nav.xhtml", nav_xhtml)
        for item_id, xhtml in chapter_xhtmls.items():
            zf.writestr(f"OEBPS/{item_id}.xhtml", xhtml)
        for abs_path, target_name in all_images:
            zf.write(abs_path, f"OEBPS/images/{target_name}")

    return out_path
