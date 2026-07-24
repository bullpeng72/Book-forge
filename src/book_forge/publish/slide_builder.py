"""마크다운 챕터 → Reveal.js 발표자료.

Lecture_forge의 `improve --to-slides`와 문제의식은 같다(섹션별 LLM 재작성,
발표자 노트 기본 포함) — 다만 Book-forge 자체 파이프라인(01_목차.md 매니페스트,
공유 PerformanceMonitor)에 맞춰 새로 조립했다.

일반 능력 P/Q/R(코드 워크스루 강의자료 지원, 2026-07): Book-forge 자신의
`agents/` 패키지를 --source로 실제 강의자료를 만들어보고 발견한 세 가지
문제를 이 파일에서 함께 고쳤다(전부 슬라이드 조립 단계에 몰려 있어 한 곳에서
고치는 게 자연스럽다).
  - Q: `html_builder.py`(도서 HTML)는 mermaid.js/highlight.js를 CDN으로 로드하는데
    이 파일(발표자료)은 reveal.js 코어만 로드했다 — 코드/다이어그램이 슬라이드에
    살아남아도 렌더링될 방법이 없었다. html_builder.py와 같은 CDN·버전·초기화
    방식을 그대로 맞췄다(새 렌더링 규칙을 만들지 않고 기존 걸 재사용).
  - P: `condense_section()`(LLM)에 섹션 전체(코드 블록 포함)를 통째로 넘기면
    LLM이 코드를 전부 프로즈 요약으로 바꿔버린다(실측: 코드 블록 4개가 있는
    챕터로 슬라이드를 만들었더니 `<pre>`/`<code>` 태그가 0개 나옴). 이제
    LLM에게 넘기기 전에 코드 펜스(```python/```mermaid)를 먼저 뽑아내고,
    프로즈만 조건 요약(condense)한 뒤 뽑아낸 코드/다이어그램은 원문 그대로
    별도 슬라이드로 붙인다 — LLM이 코드를 "요약"하다 왜곡할 위험이 없다.
  - R: `split_chapter_into_sections()`는 `# `/`## ` 헤딩이 하나도 없으면(실측:
    diagram content_type 챕터가 헤딩 없이 ```mermaid로 바로 시작하는 경우가
    있었음) 섹션을 하나도 못 찾아 슬라이드가 조용히 0장 생성됐다. 헤딩이
    전혀 없어도 본문이 있으면 챕터 제목(`fallback_heading`)을 헤딩 삼아
    최소 1개 섹션은 만들도록 폴백을 추가했다.
"""
from __future__ import annotations

import re
from html import escape as _html_escape
from pathlib import Path
from typing import Optional

from agent_evaluator import PerformanceMonitor

from book_forge.agents.slide_condenser import SlideContent, build_condense_section, parse_slide_response
from book_forge.llm.provider import LLM
from book_forge.publish.config import BookConfig
from book_forge.publish.toc_loader import load_toc

# html_builder.py의 HTML_HEAD와 같은 CDN·버전을 쓴다 — 도서와 발표자료가 같은
# 소스에서 나온 코드/다이어그램을 서로 다르게 렌더링할 이유가 없다.
REVEAL_HEAD = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@4/dist/reveal.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@4/dist/theme/white.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css">
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<style>
.reveal h2 { color: __ACCENT__; }
.reveal ul { text-align: left; }
.reveal section.chapter-title h1 { color: __ACCENT__; }
.reveal pre code { max-height: 550px; }
</style>
</head>
<body>
<div class="reveal"><div class="slides">
"""

REVEAL_FOOTER = """
</div></div>
<script src="https://cdn.jsdelivr.net/npm/reveal.js@4/dist/reveal.js"></script>
<script>
mermaid.initialize({ startOnLoad: true, theme: 'default' });
hljs.highlightAll();
Reveal.initialize({ hash: true, slideNumber: true, showNotes: __SHOW_NOTES__ });
</script>
</body>
</html>
"""

# markdown_engine.py의 fenced-code 정규식과 같은 패턴 — "```lang\n...\n```" 형태의
# 코드 펜스를 뽑아낸다. 언어 태그가 없으면(그냥 ```) lang=""로 취급.
_CODE_FENCE_RE = re.compile(r"```(\w+)?\s*\n(.*?)```", re.DOTALL)


def extract_code_blocks(body: str) -> tuple[str, list[tuple[str, str]]]:
    """본문에서 코드 펜스를 전부 뽑아내고, (펜스가 제거된 프로즈, [(언어, 코드), ...])를 반환한다.

    LLM에게 프로즈 조건 요약을 시키기 전에 코드를 미리 분리해두면, 요약
    과정에서 코드가 왜곡되거나 사라질 위험이 없다(일반 능력 P).
    """
    blocks: list[tuple[str, str]] = []

    def _pull(match: "re.Match[str]") -> str:
        lang = (match.group(1) or "").strip().lower()
        blocks.append((lang, match.group(2).rstrip("\n")))
        return ""

    prose = _CODE_FENCE_RE.sub(_pull, body)
    return prose.strip(), blocks


def split_chapter_into_sections(
    markdown_text: str, *, fallback_heading: str = ""
) -> list[tuple[str, str]]:
    """H1(챕터 제목)+인트로를 첫 섹션으로, 이후 ``## `` 헤딩마다 섹션을 분리한다.

    Book-forge 챕터 스캐폴드는 `# Chapter NN: 제목` 다음 `## N.M 소제목`
    구조를 쓰므로(IMAGES.md/Book 관례와 동일) 이 가정으로 충분하다.

    fallback_heading(일반 능력 R): `# `/`## ` 헤딩이 하나도 없는 챕터(실측:
    diagram content_type이 헤딩 없이 코드 펜스로 바로 시작한 사례)는 기존
    로직으로는 섹션을 하나도 못 만들어 슬라이드가 조용히 0장 생성됐다 —
    본문이 있으면 챕터 제목을 헤딩 삼아 최소 1개 섹션은 만든다.
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
    elif any(line.strip() for line in current_body):
        sections.append((fallback_heading or "슬라이드", current_body))

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


def render_code_slide_html(language: str, code: str) -> str:
    """추출된 코드 펜스를 원문 그대로 별도 슬라이드로 렌더링한다(일반 능력 P).

    LLM을 거치지 않는다 — 요약이 아니라 "코드를 그대로 보여주는" 슬라이드라
    condense_section()과 무관하게 문자열 조립만으로 만든다(환각 위험 없음).
    """
    cls_attr = f' class="language-{_html_escape(language)}"' if language else ""
    return (
        "<section>\n"
        f"<pre><code{cls_attr}>{_html_escape(code)}</code></pre>\n"
        "</section>\n"
    )


def render_mermaid_slide_html(mermaid_source: str) -> str:
    """추출된 mermaid 펜스를 원문 그대로 별도 슬라이드로 렌더링한다(일반 능력 P).

    html_builder.py(markdown_engine.py)가 mermaid 블록을
    `<div class="mermaid">...</div>`로 렌더링하는 것과 같은 규칙을 쓴다 —
    mermaid.js가 이 클래스를 찾아 자동으로 SVG로 렌더링한다.
    """
    return f'<section>\n<div class="mermaid">\n{mermaid_source}\n</div>\n</section>\n'


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
        sections = split_chapter_into_sections(raw_md, fallback_heading=rc.spec.chapter_title)
        for idx, (heading, body) in enumerate(sections):
            # 일반 능력 P: 코드/다이어그램 펜스는 LLM 조건 요약에 넘기기 전에
            # 먼저 뽑아내 원문 그대로 별도 슬라이드로 붙인다 — 프로즈만 압축한다.
            prose, code_blocks = extract_code_blocks(body)
            if prose:
                raw_response = condense_section(heading=heading, body=prose, ground_truth=heading)
                content = parse_slide_response(raw_response, fallback_title=heading)
            else:
                # 본문이 코드/다이어그램뿐이면(예: diagram content_type) LLM을
                # 부르지 않고 헤딩만 있는 타이틀 슬라이드로 대체한다.
                content = SlideContent(title=heading, bullets=[], notes="")
            slide_sections.append(
                render_slide_html(content, include_notes=include_notes, is_title_slide=(idx == 0))
            )
            for lang, code in code_blocks:
                if lang == "mermaid":
                    slide_sections.append(render_mermaid_slide_html(code))
                else:
                    slide_sections.append(render_code_slide_html(lang, code))

    head = REVEAL_HEAD.replace("__TITLE__", _html_escape(config.title)).replace(
        "__ACCENT__", config.accent_color
    )
    footer = REVEAL_FOOTER.replace("__SHOW_NOTES__", "true" if include_notes else "false")
    output = head + "\n".join(slide_sections) + footer

    config.outputs_dir.mkdir(parents=True, exist_ok=True)
    out_path = config.outputs_dir / f"{config.title_slug}_slides.html"
    out_path.write_text(output, encoding="utf-8")
    return out_path
