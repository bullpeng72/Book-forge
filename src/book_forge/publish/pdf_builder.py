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

from book_forge.publish.book_index import build_index_entries
from book_forge.publish.config import BookConfig
from book_forge.publish.html_builder import (
    CSS,
    HTML_FOOTER,
    HTML_HEAD,
    build_index_section,
    build_title_page,
    chapter_anchor_id,
)
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


def _render_title_page_pdf(browser, config: BookConfig, out_path: Path) -> None:
    """표지 페이지만 담은 별도 PDF를 만든다(일반 능력 AI).

    PDF는 챕터별로 따로 파일을 만드는 구조라(도서 전체를 한 파일로 묶는
    개념이 없음) "표지"도 자연스럽게 같은 패턴으로 별도 파일 하나로
    만든다 — 기존 챕터 렌더링 경로(`_standalone_chapter_html`)를 그대로
    재사용, 새 렌더링 로직 없음.
    """
    section = build_title_page(config)
    full_html = _standalone_chapter_html(config.title, section, config.accent_color)

    page = browser.new_page()
    page.set_content(full_html, wait_until="networkidle")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    page.pdf(
        path=str(out_path),
        format="A4",
        margin={"top": "22mm", "right": "20mm", "bottom": "25mm", "left": "25mm"},
        print_background=True,
    )
    page.close()


def _render_index_pdf(browser, entries, config: BookConfig, out_path: Path) -> None:
    """찾아보기 페이지만 담은 별도 PDF를 만든다(일반 능력 AL).

    표지(AI)와 같은 패턴 — 챕터별 개별 파일 구조라 "찾아보기"도 자연스럽게
    별도 파일 하나로 만든다. with_links=False: 다른 챕터 PDF를 가리키는
    앵커가 실제로 존재하지 않으므로(파일이 분리돼 있음) 챕터 번호/제목
    텍스트만 표기한다.
    """
    section = build_index_section(entries, with_links=False)
    full_html = _standalone_chapter_html("찾아보기", section, config.accent_color)

    page = browser.new_page()
    page.set_content(full_html, wait_until="networkidle")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    page.pdf(
        path=str(out_path),
        format="A4",
        margin={"top": "22mm", "right": "20mm", "bottom": "25mm", "left": "25mm"},
        print_background=True,
    )
    page.close()


def build_pdf(
    config: BookConfig, chapter_no: Optional[int] = None, *, with_index: bool = False
) -> list[Path]:
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
            # 표지는 책 전체 개념이라 특정 챕터만 뽑아 만들 때(chapter_no
            # 지정)는 안 만든다 — 매번 재생성하는 챕터 PDF에 표지가 섞이면
            # 오히려 헷갈린다.
            if chapter_no is None and build_title_page(config):
                title_page_path = config.pdf_output_dir / "00_표지.pdf"
                _render_title_page_pdf(browser, config, title_page_path)
                outputs.append(title_page_path)
            for rc in chapters:
                if not rc.exists:
                    continue
                out_path = (
                    config.pdf_output_dir / rc.spec.part_dir_name / rc.spec.chapter_file_name
                ).with_suffix(".pdf")
                _render_chapter_pdf(browser, rc, config, out_path)
                outputs.append(out_path)

            # 찾아보기도 표지와 같은 이유로 책 전체 빌드(chapter_no=None)일
            # 때만 만든다. 옵트인(with_index)인 이유: 매 빌드마다 전체
            # 챕터를 다시 읽어 용어를 재추출하는 추가 비용이 있고, 아직
            # 초안이 미완성인 프로젝트에서는 결과가 자주 바뀌어 의미가
            # 적다 — 저자가 필요할 때만 켜도록 둔다.
            if chapter_no is None and with_index:
                entries = build_index_entries(chapters)
                if entries:
                    index_path = config.pdf_output_dir / "99_찾아보기.pdf"
                    _render_index_pdf(browser, entries, config, index_path)
                    outputs.append(index_path)
        finally:
            browser.close()
    return outputs
