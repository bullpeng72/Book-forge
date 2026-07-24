#!/usr/bin/env python3
"""Book-forge로 읽는 AI 에이전트와 Harness Engineering — markdown → single HTML converter.

Media/AOO/build_aoo_book.py의 변환 엔진(마크다운→HTML, TOC, 검색, 사이드바)을
그대로 재사용하되, 이 책(Book-forge/Book/)의 실제 디렉토리·챕터 구조에 맞춰
다시 구성한다. 00_기획안.md·02_목차_초안.md(집필 관리용 문서)는 AOO와 동일한
관례로 이 책 산출물에서 제외한다.
"""

import importlib.util
import platform
import re
import sys
import unicodedata
from html import escape as _html_escape
from pathlib import Path

# ── 의존성 확인 ────────────────────────────────────────────────────────────────


def _check_dependencies() -> None:
    missing = []
    if importlib.util.find_spec("markdown") is None:
        missing.append("markdown")

    if missing:
        os_name = platform.system()
        print(f"❌ 필수 패키지 누락: {', '.join(missing)}")
        print("\n설치 방법:")
        print(f"  pip install {' '.join(missing)}")
        if os_name == "Darwin":
            print("  brew install pandoc pango")
        elif os_name == "Linux":
            print("  sudo apt install pandoc libpango-1.0-0")
        sys.exit(1)


_check_dependencies()

import markdown as md_lib

BOOK_DIR = Path(__file__).parent
OUTPUT_FILE = BOOK_DIR / "book-forge-agent-harness.html"


# ── Book-forge / Agent-Evaluator 버전 자동 읽기 — 이 책이 인용한 두 소스의 버전 ──
def _read_version(pyproject_path: Path, fallback: str) -> str:
    try:
        if sys.version_info >= (3, 11):
            import tomllib

            with open(pyproject_path, "rb") as _f:
                return tomllib.load(_f)["project"]["version"]
    except Exception:
        pass
    try:
        raw = pyproject_path.read_text(encoding="utf-8")
        m = re.search(r'^version\s*=\s*"([^"]+)"', raw, re.MULTILINE)
        if m:
            return m.group(1)
    except Exception:
        pass
    return fallback


BOOK_FORGE_VERSION = _read_version(BOOK_DIR.parent / "pyproject.toml", "0.1.0")
AGENT_EVALUATOR_VERSION = _read_version(
    BOOK_DIR.parent.parent / "Agent-Evaluator" / "pyproject.toml", "0.9.9"
)


def robust_path(fpath: Path) -> Path:
    """NFC/NFD 정규화 차이로 인한 파일 미인식 문제 해결 (macOS 한글 파일명)."""
    if fpath.exists():
        return fpath
    try:
        rel_parts = fpath.relative_to(BOOK_DIR).parts
    except ValueError:
        return fpath
    current = BOOK_DIR
    for part in rel_parts:
        nfc_part = unicodedata.normalize("NFC", part)
        found = False
        if not current.exists():
            break
        for entry in current.iterdir():
            if unicodedata.normalize("NFC", entry.name) == nfc_part:
                current = entry
                found = True
                break
        if not found:
            current = current / part
    return current


# ── 변환 순서 — 02_목차_초안.md 기준 ────────────────────────────────────────────
ORDERED_FILES = [
    robust_path(BOOK_DIR / "00_서문.md"),
    robust_path(BOOK_DIR / "Part_I_AI_에이전트란_무엇인가/Chapter_01_에이전트의_최소_구성_요소.md"),
    robust_path(BOOK_DIR / "Part_I_AI_에이전트란_무엇인가/Chapter_02_단일_에이전트의_동작_흐름.md"),
    robust_path(BOOK_DIR / "Part_I_AI_에이전트란_무엇인가/Chapter_03_에이전트는_왜_어떻게_실패하는가.md"),
    robust_path(BOOK_DIR / "Part_II_Book_forge의_멀티에이전트_협업/Chapter_04_순차_파이프라인_협업.md"),
    robust_path(BOOK_DIR / "Part_II_Book_forge의_멀티에이전트_협업/Chapter_05_검토자_편집장_협업.md"),
    robust_path(BOOK_DIR / "Part_II_Book_forge의_멀티에이전트_협업/Chapter_06_사람_에이전트_반복_개정_루프.md"),
    robust_path(BOOK_DIR / "Part_II_Book_forge의_멀티에이전트_협업/Chapter_07_지식창고를_매개로_한_협업.md"),
    robust_path(BOOK_DIR / "Part_III_배치_평가로_품질을_계측한다/Chapter_08_agent_eval_데코레이터_해부.md"),
    robust_path(BOOK_DIR / "Part_III_배치_평가로_품질을_계측한다/Chapter_09_Gate_A_G가_실제로_측정하는_것.md"),
    robust_path(BOOK_DIR / "Part_III_배치_평가로_품질을_계측한다/Chapter_10_정적_검증기_3종.md"),
    robust_path(BOOK_DIR / "Part_III_배치_평가로_품질을_계측한다/Chapter_11_책_전체를_하나로.md"),
    robust_path(BOOK_DIR / "Part_IV_실행_전에_막고_조정한다/Chapter_12_LiveGuardrail과_tool_guard.md"),
    robust_path(BOOK_DIR / "Part_IV_실행_전에_막고_조정한다/Chapter_13_팀_동시성과_편집_충돌_방지.md"),
    robust_path(BOOK_DIR / "Part_IV_실행_전에_막고_조정한다/Chapter_14_품질_기준을_프로젝트마다_다르게.md"),
    robust_path(BOOK_DIR / "Part_IV_실행_전에_막고_조정한다/Chapter_15_한계와_열린_문제.md"),
    robust_path(BOOK_DIR / "Appendix/A_Harness_Config_사용현황.md"),
]

# ── Mermaid / raw-HTML 주입 — 이 책의 다이어그램은 챕터 본문에 ```mermaid로
#    이미 직접 작성돼 있어 별도 주입이 필요 없다. 확장 지점만 남겨둔다.
MERMAID_INJECTIONS: dict[str, list[tuple[str, str]]] = {}

# ── HTML 템플릿 — Media/AOO/build_aoo_book.py의 재사용 가능한 부분을 그대로 유지 ──
HTML_HEAD = """\
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Book-forge로 읽는 AI 에이전트와 Harness Engineering</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&family=Noto+Serif+KR:wght@400;700&family=JetBrains+Mono:wght@400;500&family=Noto+Sans+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/atom-one-dark.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/languages/python.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/languages/bash.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/languages/yaml.min.js"></script>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --primary: #4527a0;
  --primary-light: #5e35b1;
  --accent: #00897b;
  --accent-light: #4db6ac;
  --warn: #f57f17;
  --danger: #c62828;
  --success: #2e7d32;
  --bg: #fafafa;
  --surface: #ffffff;
  --border: #e0e0e0;
  --text: #212121;
  --text-secondary: #616161;
  --code-bg: #f5f5f5;
  --sidebar-w: 280px;
  --font-body: 'Noto Sans KR', 'Apple SD Gothic Neo', sans-serif;
  --font-serif: 'Noto Serif KR', serif;
  --font-mono: 'JetBrains Mono', 'Noto Sans Mono', 'Menlo', monospace;
}

html { scroll-behavior: smooth; font-size: 16px; }
body { font-family: var(--font-body); color: var(--text); background: var(--bg); line-height: 1.8; display: flex; }

/* ── Sidebar TOC ── */
#sidebar {
  position: fixed; top: 0; left: 0; width: var(--sidebar-w); height: 100vh;
  overflow-y: auto; background: var(--primary); color: #fff; padding: 0;
  z-index: 100; font-size: 0.8rem;
}
#sidebar-header {
  padding: 20px 16px 12px; background: rgba(0,0,0,0.25);
  font-family: var(--font-serif); font-size: 0.85rem; font-weight: 700; line-height: 1.4;
  border-bottom: 1px solid rgba(255,255,255,0.1);
}
#sidebar-header small { display: block; font-size: 0.7rem; font-weight: 300; opacity: 0.75; margin-top: 4px; }
#sidebar-header .subtitle {
  display: block; font-size: 0.72rem; font-weight: 400; font-style: italic; opacity: 0.82;
  margin-top: 7px; padding-top: 7px; border-top: 1px solid rgba(255,255,255,0.18);
  line-height: 1.55; letter-spacing: 0.01em;
}
#toc { padding: 8px 0 40px; }
#toc a { display: block; padding: 4px 16px; color: rgba(255,255,255,0.8); text-decoration: none; transition: background 0.15s, color 0.15s; line-height: 1.4; }
#toc a:hover { background: rgba(255,255,255,0.1); color: #fff; }
#toc a.part-heading {
  padding: 10px 16px 4px; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase; color: rgba(255,255,255,0.45); cursor: default;
}
#toc a.chapter { padding-left: 24px; font-size: 0.78rem; }
#toc a.appendix { padding-left: 24px; font-size: 0.75rem; color: rgba(255,255,255,0.65); }
#toc a.active { background: rgba(255,255,255,0.15); color: #fff; font-weight: 500; }

/* ── Main content ── */
#main { margin-left: var(--sidebar-w); min-height: 100vh; width: calc(100% - var(--sidebar-w)); padding: 0 48px 80px 48px; }

/* ── Chapter sections ── */
.chapter-section { border-top: 3px solid var(--primary); margin-top: 64px; padding-top: 48px; }
.chapter-section:first-of-type { border-top: none; margin-top: 0; padding-top: 40px; }
.part-divider { margin: 80px 0 0; padding: 20px 0 10px; border-top: 1px solid var(--border); }
.part-divider h2 { font-family: var(--font-serif); font-size: 1.4rem; color: var(--primary); letter-spacing: 0.02em; }

/* ── Typography ── */
h1, h2, h3, h4, h5, h6 { font-family: var(--font-serif); line-height: 1.35; }
h1 { font-size: 2.2rem; color: var(--primary); margin: 40px 0 20px; padding-bottom: 12px; border-bottom: 2px solid var(--primary); }
h2 { font-size: 1.55rem; color: var(--primary-light); margin: 36px 0 14px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }
h3 { font-size: 1.2rem; color: var(--text); margin: 28px 0 10px; }
h4 { font-size: 1.05rem; color: var(--text); margin: 20px 0 8px; }
h5, h6 { font-size: 0.95rem; color: var(--text-secondary); margin: 16px 0 6px; }

.chapter-section h2 { font-size: 2.2rem; color: var(--primary); margin: 40px 0 20px; padding-bottom: 12px; border-bottom: 2px solid var(--primary); }
.chapter-section h3 { font-size: 1.55rem; color: var(--primary-light); margin: 36px 0 14px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }
.chapter-section h4 { font-size: 1.2rem; color: var(--text); margin: 28px 0 10px; }
.chapter-section h5 { font-size: 1.05rem; color: var(--text); margin: 20px 0 8px; }

p { margin: 0 0 14px; }
ul, ol { margin: 0 0 14px 24px; }
li { margin: 4px 0; }
ul li ul { margin-top: 4px; }
strong { color: var(--primary); font-weight: 700; }
em { font-style: italic; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
hr { border: none; border-top: 1px solid var(--border); margin: 32px 0; }

/* ── Code ── */
code {
  font-family: var(--font-mono); font-size: 0.84em; background: #fff0f0; color: #c0392b;
  padding: 2px 7px; border-radius: 4px; border: 1px solid #ffd5d5;
}
pre {
  background: #282c34; border-radius: 10px; padding: 20px 22px; overflow-x: auto;
  margin: 16px 0 22px; position: relative; font-size: 0.84rem; line-height: 1.65;
  border: 1px solid #3a3f4b; box-shadow: 0 2px 8px rgba(0,0,0,0.18);
}
pre code { background: transparent !important; color: #abb2bf !important; padding: 0; font-size: inherit; border-radius: 0; border: none; }
.hljs { background: transparent !important; color: #abb2bf !important; padding: 0 !important; }
.hljs-comment, .hljs-quote { color: #7c8899 !important; font-style: italic; }
.hljs-keyword, .hljs-selector-tag, .hljs-built_in { color: #c678dd !important; font-weight: 500; }
.hljs-string, .hljs-attr { color: #98c379 !important; }
.hljs-number, .hljs-literal { color: #d19a66 !important; }
.hljs-title, .hljs-title.function_, .hljs-function .hljs-title { color: #61afef !important; }
.hljs-class .hljs-title, .hljs-title.class_ { color: #e5c07b !important; }
.hljs-variable, .hljs-params { color: #e06c75 !important; }
.hljs-meta { color: #61afef !important; }
.hljs-operator, .hljs-punctuation { color: #abb2bf !important; }
pre strong { color: #e5c07b; }
pre code.plain-code, pre code.plain-code * { color: #abb2bf !important; font-style: normal !important; font-weight: normal !important; }
pre { font-feature-settings: "liga" 0, "calt" 0; text-rendering: optimizeLegibility; }
@font-face {
  font-family: 'JetBrains Mono'; src: local('Noto Sans Mono');
  unicode-range: U+AC00-D7AF, U+1100-11FF, U+3130-318F, U+A960-A97F, U+D7B0-D7FF;
}

/* ── Tables ── */
.table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; margin: 16px 0 22px; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }
table { width: 100%; border-collapse: collapse; margin: 0; font-size: 0.88rem; overflow: hidden; border-radius: 8px; }
th { background: var(--primary); color: #fff; padding: 10px 14px; text-align: left; font-weight: 500; font-size: 0.83rem; }
td { padding: 9px 14px; border-bottom: 1px solid var(--border); vertical-align: middle; }
tr:last-child td { border-bottom: none; }
tr:nth-child(even) td { background: #f8f7ff; }
tr:hover td { background: #f0edfb; }

/* ── Blockquote (callouts) ── */
blockquote { border-left: 4px solid var(--accent); background: #e0f2f1; padding: 12px 18px; margin: 16px 0; border-radius: 0 8px 8px 0; font-size: 0.93rem; }
blockquote p { margin-bottom: 6px; }
blockquote p:last-child { margin-bottom: 0; }
blockquote strong { color: var(--accent); }
blockquote code { background: rgba(0,0,0,0.06); }

/* ── TIP box (👨‍💻 개발자 TIP · 📋 QA 관리자 TIP) ── */
.tip-box { border-left: 4px solid #f59e0b; background: #fffbeb; padding: 12px 18px; margin: 16px 0; border-radius: 0 8px 8px 0; font-size: 0.93rem; }
.tip-box p { margin-bottom: 6px; }
.tip-box p:last-child { margin-bottom: 0; }
.tip-box strong { color: #b45309; }
.tip-box code { background: rgba(0,0,0,0.06); }

/* ── Mermaid diagrams ── */
.mermaid { background: #f8f7ff; border: 1px solid var(--border); border-radius: 10px; padding: 20px; margin: 20px 0 24px; text-align: center; overflow-x: auto; }

/* ── Badge / pill ── */
.badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.73rem; font-weight: 600; letter-spacing: 0.03em; }
.badge-pass { background: #c8e6c9; color: #1b5e20; }
.badge-fail { background: #ffcdd2; color: #b71c1c; }
.badge-warn { background: #fff9c4; color: #f57f17; }

/* ── Print ── */
@media print {
  #sidebar { display: none; }
  #main { margin-left: 0; max-width: 100%; padding: 0 20mm; }
  .chapter-section { page-break-before: always; }
  .chapter-section:first-of-type { page-break-before: avoid; }
  a { color: var(--text); }
  pre { background: #f5f5f5; color: var(--text); border: 1px solid #ccc; }
  pre code { color: var(--text); }
}

/* ── Responsive ── */
@media (max-width: 768px) {
  :root { --sidebar-w: 0px; }
  #sidebar { display: none; }
  #main { margin-left: 0; padding: 20px; }
}

/* ── figure / 외부 이미지 ── */
.my-6 { margin-top: 1.5rem; margin-bottom: 1.5rem; }
.text-center { text-align: center; }
.max-w-full { max-width: 100%; height: auto; }
.rounded { border-radius: 0.375rem; }
.shadow { box-shadow: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.08); }
.mx-auto { margin-left: auto; margin-right: auto; display: block; }
img:not(.mermaid img) { max-width: 100%; height: auto; display: block; margin: 12px auto; border-radius: 6px; }
figure { margin: 24px 0; text-align: center; }
figcaption { font-size: 0.82rem; color: var(--text-secondary); margin-top: 8px; font-style: italic; line-height: 1.5; }

/* ── Search ── */
#search-wrap { padding: 8px 12px 10px; background: rgba(0,0,0,0.18); border-bottom: 1px solid rgba(255,255,255,0.07); }
#search-box {
  width: 100%; padding: 6px 10px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.15);
  background: rgba(255,255,255,0.1); color: #fff; font-size: 0.8rem; font-family: var(--font-body);
  outline: none; box-sizing: border-box; transition: background 0.15s, border-color 0.15s;
}
#search-box::placeholder { color: rgba(255,255,255,0.38); }
#search-box:focus { background: rgba(255,255,255,0.17); border-color: rgba(255,255,255,0.3); }
#search-meta { display: flex; align-items: center; justify-content: space-between; margin-top: 5px; min-height: 18px; }
#search-count { font-size: 0.7rem; color: rgba(255,255,255,0.5); }
#search-nav { display: flex; gap: 3px; }
#search-nav button {
  background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.12); color: rgba(255,255,255,0.65);
  border-radius: 4px; padding: 1px 7px; font-size: 0.73rem; cursor: pointer; line-height: 1.5; transition: background 0.12s;
}
#search-nav button:hover:not(:disabled) { background: rgba(255,255,255,0.18); color: #fff; }
#search-nav button:disabled { opacity: 0.28; cursor: default; }
mark.search-hit { background: #ffeb3b; color: #212121; border-radius: 2px; padding: 0 1px; font-style: inherit; font-weight: inherit; }
mark.search-hit.current { background: #ff9800; color: #fff; outline: 2px solid #ff9800; }
@media print { #search-wrap { display: none; } mark.search-hit { background: none; } }
</style>
</head>
<body>
"""

HTML_SIDEBAR_START = (
    '<nav id="sidebar"><div id="sidebar-header">Book-forge × Agent-Evaluator'
    '<span class="subtitle">Book-forge로 읽는<br>AI 에이전트와 Harness Engineering</span>'
    f'<small>Book-forge v{BOOK_FORGE_VERSION} · Agent-Evaluator v{AGENT_EVALUATOR_VERSION} 기준</small></div>'
    '<div id="search-wrap">'
    '<input id="search-box" type="search" placeholder="\U0001f50d 본문 검색…" autocomplete="off" spellcheck="false">'
    '<div id="search-meta">'
    '<span id="search-count"></span>'
    '<div id="search-nav">'
    '<button id="search-prev" disabled title="이전 결과">▲</button>'
    '<button id="search-next" disabled title="다음 결과">▼</button>'
    "</div>"
    "</div>"
    "</div>"
    '<div id="toc">'
)
HTML_SIDEBAR_END = "</div></nav>"

HTML_MAIN_START = '<main id="main">'
HTML_MAIN_END = "</main>"

HTML_FOOT = """\
<script>
mermaid.initialize({ startOnLoad: true, theme: 'default', securityLevel: 'loose', fontFamily: 'Noto Sans KR, sans-serif' });
document.addEventListener('DOMContentLoaded', function() {
  const ALLOWED = new Set(['python','bash','shell','sh','yaml','json','javascript','js','text','plaintext','html','css','sql','markdown','md']);
  document.querySelectorAll('pre code').forEach(block => {
    const cls = block.className || '';
    const langMatch = cls.match(/language-([a-z0-9_+-]+)/);
    if (langMatch && ALLOWED.has(langMatch[1]) && langMatch[1] !== 'text' && langMatch[1] !== 'plaintext') {
      hljs.highlightElement(block);
    }
    if (!langMatch || langMatch[1] === 'text' || langMatch[1] === 'plaintext') {
      block.classList.add('plain-code');
    }
  });
  const sections = document.querySelectorAll('.chapter-section[id]');
  const tocLinks = document.querySelectorAll('#toc a[href^="#"]');
  const observer = new IntersectionObserver(entries => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        tocLinks.forEach(a => a.classList.toggle('active', a.getAttribute('href') === '#' + e.target.id));
      }
    });
  }, { rootMargin: '-10% 0px -80% 0px' });
  sections.forEach(s => observer.observe(s));
});
</script>
<script>
/* ── In-page Search ── */
(function () {
  var box   = document.getElementById('search-box');
  var count = document.getElementById('search-count');
  var bPrev = document.getElementById('search-prev');
  var bNext = document.getElementById('search-next');
  var main  = document.getElementById('main');
  if (!box || !main) return;

  var hits = [], cur = -1, timer;

  function clearMarks() {
    main.querySelectorAll('mark.search-hit').forEach(function (m) {
      m.parentNode.replaceChild(document.createTextNode(m.textContent), m);
    });
    main.normalize();
    hits = []; cur = -1;
  }

  function applySearch(term) {
    clearMarks();
    if (!term) { count.textContent = ''; bPrev.disabled = bNext.disabled = true; return; }
    var lterm = term.toLowerCase();
    var tlen  = term.length;
    var walker = document.createTreeWalker(
      main, NodeFilter.SHOW_TEXT,
      { acceptNode: function (node) {
          var el = node.parentElement;
          if (!el) return NodeFilter.FILTER_REJECT;
          if (el.closest('pre, code, .mermaid, script, style, mark'))
            return NodeFilter.FILTER_REJECT;
          return node.nodeValue.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP;
        }
      }
    );
    var nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(function (node) {
      var val  = node.nodeValue;
      var lval = val.toLowerCase();
      if (lval.indexOf(lterm) === -1) return;
      var frag = document.createDocumentFragment();
      var last = 0, idx;
      while ((idx = lval.indexOf(lterm, last)) !== -1) {
        if (idx > last) frag.appendChild(document.createTextNode(val.slice(last, idx)));
        var mark = document.createElement('mark');
        mark.className = 'search-hit';
        mark.textContent = val.slice(idx, idx + tlen);
        frag.appendChild(mark);
        hits.push(mark);
        last = idx + tlen;
      }
      if (last < val.length) frag.appendChild(document.createTextNode(val.slice(last)));
      node.parentNode.replaceChild(frag, node);
    });
    if (hits.length) {
      cur = 0; setCurrent(); count.textContent = hits.length + '건 발견';
    } else {
      count.textContent = '일치 없음';
    }
    bPrev.disabled = bNext.disabled = hits.length < 2;
  }

  function setCurrent() {
    hits.forEach(function (m, i) { m.classList.toggle('current', i === cur); });
    if (hits[cur]) hits[cur].scrollIntoView({ behavior: 'smooth', block: 'center' });
    if (hits.length > 1) count.textContent = (cur + 1) + ' / ' + hits.length + '건';
  }

  box.addEventListener('input', function () {
    clearTimeout(timer);
    timer = setTimeout(function () { applySearch(box.value.trim()); }, 250);
  });
  box.addEventListener('keydown', function (e) {
    if (e.key === 'Enter')  { e.preventDefault(); if (hits.length) { cur = (cur + 1) % hits.length; setCurrent(); } }
    if (e.key === 'Escape') { box.value = ''; clearMarks(); count.textContent = ''; bPrev.disabled = bNext.disabled = true; box.blur(); }
  });
  bNext.addEventListener('click', function () {
    if (!hits.length) return; cur = (cur + 1) % hits.length; setCurrent();
  });
  bPrev.addEventListener('click', function () {
    if (!hits.length) return; cur = (cur - 1 + hits.length) % hits.length; setCurrent();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === '/' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
      e.preventDefault(); box.focus(); box.select();
    }
  });
})();
</script>
</body>
</html>
"""

# ── TOC 구조 정의 — 02_목차_초안.md 기준 ────────────────────────────────────────
TOC_STRUCTURE = [
    ("chapter", "00_서문", "preface", "서문"),
    ("part", "Part I — AI 에이전트란 무엇인가"),
    ("chapter", "Chapter_01", "ch01", "01. 에이전트의 최소 구성 요소"),
    ("chapter", "Chapter_02", "ch02", "02. 단일 에이전트의 동작 흐름 — PlannerAgent 해부"),
    ("chapter", "Chapter_03", "ch03", "03. 에이전트는 왜, 어떻게 실패하는가"),
    ("part", "Part II — Book-forge의 멀티 에이전트 협업"),
    ("chapter", "Chapter_04", "ch04", "04. 순차 파이프라인 협업"),
    ("chapter", "Chapter_05", "ch05", "05. 검토자-편집장 협업 — ReviewPanel"),
    ("chapter", "Chapter_06", "ch06", "06. 사람-에이전트 반복 개정 루프"),
    ("chapter", "Chapter_07", "ch07", "07. 지식창고를 매개로 한 협업"),
    ("part", "Part III — 배치 평가로 품질을 계측한다"),
    ("chapter", "Chapter_08", "ch08", "08. @agent_eval 데코레이터 해부"),
    ("chapter", "Chapter_09", "ch09", "09. Gate A–G가 실제로 측정하는 것"),
    ("chapter", "Chapter_10", "ch10", "10. LLM 없이 잡아내는 환각 — 정적 검증기 3종"),
    ("chapter", "Chapter_11", "ch11", "11. 책 전체를 하나로 — book-forge gate"),
    ("part", "Part IV — 실행 전에 막고, 조정한다"),
    ("chapter", "Chapter_12", "ch12", "12. LiveGuardrail과 tool_guard"),
    ("chapter", "Chapter_13", "ch13", "13. 팀 동시성과 편집 충돌 방지"),
    ("chapter", "Chapter_14", "ch14", "14. 품질 기준을 프로젝트마다 다르게"),
    ("chapter", "Chapter_15", "ch15", "15. 한계와 열린 문제"),
    ("part", "부록"),
    ("appendix", "A_Harness_Config", "appA", "부록 A. Harness Config 사용 현황"),
]

STEM_TO_ID: dict[str, str] = {}
for item in TOC_STRUCTURE:
    if item[0] in ("chapter", "appendix"):
        STEM_TO_ID[item[1]] = item[2]


def stem_id(path: Path) -> str:
    stem = path.stem
    for key, sid in STEM_TO_ID.items():
        if key in stem:
            return sid
    return re.sub(r"[^a-zA-Z0-9_-]", "_", stem)


def inject_mermaid(stem: str, text: str) -> str:
    """@@HTML_START@@/```mermaid 블록 주입 지점 — 이 책은 다이어그램을 챕터 본문에
    직접 작성해 비어 있다(확장 지점만 유지)."""
    stem = unicodedata.normalize("NFC", stem)
    for file_key, injections in MERMAID_INJECTIONS.items():
        if file_key not in stem:
            continue
        for anchor, block in injections:
            lines = text.split("\n")
            inserted = False
            for i, line in enumerate(lines):
                if anchor in line:
                    lines.insert(i + 1, "\n" + block)
                    inserted = True
                    break
            text = "\n".join(lines)
            if not inserted:
                lines = text.split("\n")
                for i, line in enumerate(lines):
                    if line.startswith("# "):
                        lines.insert(i + 1, "\n" + block)
                        break
                text = "\n".join(lines)
    return text


# TIP 콜아웃 이모지 — 이 책은 👨‍💻(개발자)·📋(QA 관리자) 두 종류만 사용
_TIP_START_PAT = re.compile(r"^[\s]*(?:👨‍💻|📋|📊|🔧|🚨|💡)")


def md_to_html(text: str) -> str:
    """mermaid / raw-HTML 블록을 보존하면서 markdown → HTML 변환."""
    saved_blocks: list[str] = []

    def extract_html_block(m: re.Match) -> str:
        saved_blocks.append(("custom_html", m.group(1).strip()))
        return f"@@BLOCK_{len(saved_blocks) - 1}@@"

    text = re.sub(r"@@HTML_START@@\s*\n(.*?)@@HTML_END@@", extract_html_block, text, flags=re.DOTALL)

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
        return content

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


def demote_headings(html: str) -> str:
    """섹션 body 헤딩을 1레벨 강등 (h1→h2, h2→h3, h3→h4, h4→h5). 역순 치환으로 이중 치환 방지."""
    for level in range(4, 0, -1):
        html = re.sub(
            rf'(</?h){level}(\s|>)',
            lambda m, lv=level: f'{m.group(1)}{lv + 1}{m.group(2)}',
            html,
        )
    return html


def build_toc_html() -> str:
    lines: list[str] = []
    for item in TOC_STRUCTURE:
        if item[0] == "part":
            lines.append(f'<a class="part-heading">{item[1]}</a>')
        elif item[0] == "chapter":
            lines.append(f'<a class="chapter toc-link" href="#{item[2]}">{item[3]}</a>')
        elif item[0] == "appendix":
            lines.append(f'<a class="appendix toc-link" href="#{item[2]}">{item[3]}</a>')
    return "\n".join(lines)


def _rewrite_img_paths_for_book(html_str: str, md_dir: Path) -> str:
    """img src의 상대 경로를 OUTPUT_FILE(BOOK_DIR) 기준 상대 경로로 재작성한다."""
    def _to_rel(m: re.Match) -> str:
        src = m.group(1)
        if src.startswith(("http://", "https://", "data:", "file://", "#")):
            return m.group(0)
        abs_path = (md_dir / src).resolve()
        try:
            rel_path = abs_path.relative_to(BOOK_DIR)
            return f'src="{rel_path}"'
        except ValueError:
            return f'src="{abs_path}"'
    return re.sub(r'src="([^"]+)"', _to_rel, html_str)


def build_book() -> None:
    print("📚 Building Book-forge × Agent-Evaluator 책 HTML...")
    parts: list[str] = []

    for fpath in ORDERED_FILES:
        if not fpath.exists():
            print(f"  ⚠️  Missing: {fpath.name}")
            continue

        print(f"  📄 {fpath.name}")
        raw = fpath.read_text(encoding="utf-8")

        raw = inject_mermaid(fpath.stem, raw)

        html_body = md_to_html(raw)
        html_body = _rewrite_img_paths_for_book(html_body, fpath.parent)

        sid = stem_id(fpath)

        _h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html_body, re.DOTALL)
        _title_text = re.sub(r"<[^>]+>", "", _h1.group(1)).strip() if _h1 else sid

        html_body = demote_headings(html_body)

        parts.append(
            f'<section class="chapter-section" id="{sid}" data-section-title="{_html_escape(_title_text)}">'
            f"\n{html_body}\n</section>"
        )

    toc_html = build_toc_html()
    output = (
        HTML_HEAD
        + HTML_SIDEBAR_START
        + toc_html
        + HTML_SIDEBAR_END
        + HTML_MAIN_START
        + "\n".join(parts)
        + HTML_MAIN_END
        + HTML_FOOT
    )

    OUTPUT_FILE.write_text(output, encoding="utf-8")
    size_kb = OUTPUT_FILE.stat().st_size // 1024
    print(f"\n✅ Done: {OUTPUT_FILE}  ({size_kb} KB)")


if __name__ == "__main__":
    build_book()
