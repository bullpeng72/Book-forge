"""Book/AOO의 build_pdf_chapters.py를 간략화해 이식한 챕터별 PDF 빌더.

원본은 Mermaid SVG를 별도 렌더 페이지에서 캡처해 청크 단위로 자르는 정교한
로직을 갖고 있다 — 이 M2 구현은 그 정교함 전부를 이식하지 않는다. 대신
mermaid.js의 startOnLoad 자동 렌더링이 끝날 때까지 대기한 뒤 그대로
인쇄하는 더 단순한 경로를 쓴다 (매우 큰 다이어그램이나 페이지 경계를 걸치는
경우 잘림이 발생할 수 있음 — 알려진 한계, 후속 개선 과제).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from book_forge.publish.config import BookConfig
from book_forge.publish.html_builder import CSS, HTML_FOOTER, HTML_HEAD, chapter_anchor_id
from book_forge.publish.markdown_engine import embed_images_as_data_uri, md_to_html
from book_forge.publish.toc_loader import ResolvedChapter, load_toc

# naturalWidth > 본문 폭인 경우 attribute를 직접 재지정해 레이아웃 오버플로를 막는다
# (Chrome PDF 엔진은 attribute 값을 intrinsic size로 쓰기 때문 — build_pdf_chapters.py와 동일 원리).
_RESIZE_IMAGES_JS = """
(() => {
  const availW = document.querySelector('main').clientWidth;
  document.querySelectorAll('main img').forEach((img) => {
    const iw = img.naturalWidth, ih = img.naturalHeight;
    if (iw > 0 && iw > availW) {
      img.setAttribute('width', Math.round(availW));
      img.setAttribute('height', Math.round(ih * availW / iw));
    }
  });
})();
"""


def _standalone_chapter_html(title: str, chapter_html: str, accent: str) -> str:
    css = CSS.replace("__ACCENT__", accent) + "\nnav.sidebar { display: none; } main { max-width: 100%; }\n"
    head = HTML_HEAD.replace("__TITLE__", title).replace("__CSS__", css)
    return head + "\n<main>\n" + chapter_html + "\n</main>\n" + HTML_FOOTER


def _render_chapter_pdf(browser, rc: ResolvedChapter, config: BookConfig, out_path: Path) -> None:
    raw = rc.path.read_text(encoding="utf-8")
    html_body = md_to_html(raw)
    html_body = embed_images_as_data_uri(html_body, rc.path.parent)
    anchor = chapter_anchor_id(rc.spec.chapter_no)
    section = f'<section class="chapter-section" id="{anchor}">\n{html_body}\n</section>'
    title = f"Chapter {rc.spec.chapter_no:02d}. {rc.spec.chapter_title}"
    full_html = _standalone_chapter_html(title, section, config.accent_color)

    page = browser.new_page()
    page.set_content(full_html, wait_until="networkidle")
    page.wait_for_timeout(800)  # mermaid startOnLoad 렌더링 대기
    page.evaluate(_RESIZE_IMAGES_JS)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    page.pdf(
        path=str(out_path),
        format="A4",
        margin={"top": "22mm", "right": "20mm", "bottom": "25mm", "left": "25mm"},
        print_background=True,
    )
    page.close()


def build_pdf(config: BookConfig, chapter_no: Optional[int] = None) -> list[Path]:
    from playwright.sync_api import sync_playwright  # lazy import — [pdf] extra, 무거운 의존성

    chapters = load_toc(config.project_dir)
    if chapter_no is not None:
        chapters = [rc for rc in chapters if rc.spec.chapter_no == chapter_no]
        if not chapters:
            raise ValueError(f"챕터 번호 {chapter_no}를 목차에서 찾을 수 없습니다.")

    outputs: list[Path] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            for rc in chapters:
                if not rc.exists:
                    continue
                out_path = (
                    config.pdf_output_dir / rc.spec.part_dir_name / rc.spec.chapter_file_name
                ).with_suffix(".pdf")
                _render_chapter_pdf(browser, rc, config, out_path)
                outputs.append(out_path)
        finally:
            browser.close()
    return outputs
