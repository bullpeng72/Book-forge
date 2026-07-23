"""소스 어댑터 — PDF/코드 저장소/마크다운/웹 URL 등 서로 다른 입력을 동일한
청크 리스트로 변환한다 (일반 능력 A: 소스 어댑터 다변화).

KnowledgeStore.add()는 청크 리스트(list[str])만 받으므로, 새 소스 타입을 추가할
때 이 파일에 함수 하나만 더 짜면 된다 — KnowledgeStore/embeddings 쪽은 손댈
필요가 없다. 현재 지원: PDF, 코드/텍스트 파일 1개, 코드 저장소 디렉토리,
http(s):// URL 1개.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

from book_forge.knowledge.pdf_source import chunk_text, extract_pdf_text

_CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".rb"}
_TEXT_EXTS = {".md", ".txt", ".rst"}
DEFAULT_SOURCE_EXTS = _CODE_EXTS | _TEXT_EXTS
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def load_pdf_source(path: Path, *, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    return chunk_text(extract_pdf_text(path), chunk_size=chunk_size, overlap=overlap)


def load_text_source(path: Path, *, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """마크다운/일반 텍스트/단일 코드 파일을 청크로 변환한다. 줄 구조를 보존한다."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    return chunk_text(text, chunk_size=chunk_size, overlap=overlap, collapse_whitespace=False)


def load_code_repo_source(
    directory: Path,
    *,
    extensions: Optional[set[str]] = None,
    max_files: int = 200,
    chunk_size: int = 500,
    overlap: int = 80,
) -> list[str]:
    """디렉토리를 재귀 탐색해 소스 파일들을 청크로 변환한다.

    chunk_size 기본값이 PDF(800)보다 작은 이유: 코드는 들여쓰기·구두점이 많아
    자연어보다 토큰 밀도가 높다 — 실측 결과 mxbai-embed-large 임베딩 모델의
    컨텍스트 길이를 1200자 청크가 실제로 초과해 500 에러가 발생했다(500자로도
    넘칠 수 있는 극단적 케이스는 embeddings.py의 자동 축소 재시도가 처리한다).

    파일 하나를 그대로 하나의 청크로 쓰지 않는 이유: 큰 파일은 top_k 검색에서
    통째로 밀려나거나 임베딩 품질이 떨어질 수 있어, 파일 내용 앞에 상대경로를
    붙인 뒤 chunk_text()로 분할한다 — 청크에 "# 파일: xxx.py"가 남아 있어야
    검색 결과가 어느 파일에서 왔는지 저자가 알 수 있다.
    """
    exts = extensions or _CODE_EXTS
    files = sorted(
        p
        for p in directory.rglob("*")
        if p.is_file()
        and p.suffix in exts
        and "__pycache__" not in p.parts
        and ".git" not in p.parts
    )[:max_files]

    chunks: list[str] = []
    for fpath in files:
        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = fpath.relative_to(directory)
        tagged = f"# 파일: {rel}\n{content}"
        chunks.extend(
            chunk_text(tagged, chunk_size=chunk_size, overlap=overlap, collapse_whitespace=False)
        )
    return chunks


class _HTMLTextExtractor(HTMLParser):
    """<script>/<style>/<head> 안의 텍스트는 버리고 나머지 텍스트만 모은다.

    trafilatura/readability 같은 전용 라이브러리를 쓰지 않고 표준 라이브러리
    html.parser로 최소한만 처리한다 — PDF/코드 어댑터와 같은 "무거운 의존성을
    추가하지 않는다" 원칙. 네비게이션·푸터 같은 잡음이 섞여 나올 수 있다(알려진
    한계 — 필요하면 검색 커버리지 점검(C)이 사후에 걸러낸다).
    """

    _SKIP_TAGS = {"script", "style", "noscript", "head"}

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self._parts.append(stripped)

    @property
    def text(self) -> str:
        return "\n".join(self._parts)


def extract_text_from_html(html: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(html)
    return parser.text


def load_url_source(
    url: str, *, chunk_size: int = 800, overlap: int = 100, timeout: int = 30
) -> list[str]:
    """URL 하나를 가져와 본문 텍스트만 추출해 청크로 변환한다.

    다른 사용자에게 자동으로 요청을 보내는 크롤러가 아니라, 저자가 --source로
    직접 지정한 URL 하나를 그 자리에서 한 번 가져오는 동작이다(재귀적으로
    링크를 따라가지 않음).
    """
    import requests  # 코어 의존성 — RAG([rag] extra) 없이도 이미 설치돼 있음

    response = requests.get(
        url, timeout=timeout, headers={"User-Agent": "Book-forge/0.1 (+https://github.com)"}
    )
    response.raise_for_status()
    text = extract_text_from_html(response.text)
    if not text.strip():
        return []
    tagged = f"# 출처: {url}\n{text}"
    return chunk_text(tagged, chunk_size=chunk_size, overlap=overlap, collapse_whitespace=True)


def load_source(source, **kwargs) -> list[str]:
    """URL 형식/디렉토리 여부/확장자로 알맞은 어댑터를 자동 선택한다.

    source는 str 또는 Path 둘 다 받는다 — 기존 호출부(Path 전달)와 새 URL
    문자열 호출부를 모두 지원해야 한다.
    """
    source_str = str(source)
    if _URL_RE.match(source_str):
        url_kwargs = {k: v for k, v in kwargs.items() if k in ("chunk_size", "overlap", "timeout")}
        return load_url_source(source_str, **url_kwargs)

    path = Path(source)
    if path.is_dir():
        return load_code_repo_source(path, **kwargs)

    text_kwargs = {k: v for k, v in kwargs.items() if k in ("chunk_size", "overlap")}
    if path.suffix.lower() == ".pdf":
        return load_pdf_source(path, **text_kwargs)
    if path.suffix.lower() in DEFAULT_SOURCE_EXTS:
        return load_text_source(path, **text_kwargs)

    raise ValueError(
        f"지원하지 않는 소스 형식: {source} (지원: .pdf, 코드/텍스트 파일, 디렉토리, http(s):// URL)"
    )
