"""쿼리 문자열로 후보 URL을 자동으로 찾는다(일반 능력 N 전체 범위 — SPEC.md 항목 N).

지금까지 Book-forge는 저자가 URL을 직접 지정해야만 웹 소스를 쓸 수 있었다
(`--source https://...`, 일반 능력 A) — "이 주제에 맞는 자료를 찾아온다"는
검색 단계 자체가 없었다. 이 모듈이 그 검색 단계를 담당한다.

DuckDuckGo의 API 키 없는 HTML 엔드포인트(``html.duckduckgo.com/html/``)를
`requests`로 직접 호출해 결과 페이지를 파싱한다 — 공식 검색 API가 아니라
"HTML 페이지를 저자가 브라우저로 열어보듯 가져와 파싱"하는 방식이라, 페이지
구조가 바뀌면 파싱이 깨질 수 있다(알려진 한계, 아래 문서화). Tavily 같은
전용 검색 API 대신 이 방식을 고른 이유: API 키/회원가입/비용 없이 Book-forge의
"바로 시작할 수 있다" 원칙을 그대로 유지할 수 있고, 이미 `knowledge/sources.py`가
`html.parser`(표준 라이브러리)만으로 HTML을 파싱하는 것과 같은 "무거운 의존성을
추가하지 않는다" 원칙을 따른다.
"""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlparse

_SEARCH_URL = "https://html.duckduckgo.com/html/"
_USER_AGENT = "Book-forge/0.1 (+https://github.com)"


@dataclass(frozen=True)
class SearchResult:
    """검색 결과 후보 하나 — 저자가 확인하고 채택 여부를 고를 수 있도록 제목/요약을 함께 담는다."""

    title: str
    url: str
    snippet: str = ""


class _DuckDuckGoResultParser(HTMLParser):
    """``<a class="result__a">``(제목)와 ``<a class="result__snippet">``(요약)만 뽑는다.

    실제 DuckDuckGo HTML 결과 페이지를 직접 받아 구조를 확인하고 만든
    파서다(2026-07 기준) — 제목 링크가 항상 요약보다 문서 순서상 먼저
    나오므로, 제목을 만나면 새 결과를 append하고 그다음 나오는 요약을
    가장 최근 결과에 채워 넣는 단순한 상태 기계로 충분하다. 요약 안의
    ``<b>`` 강조 태그는 `handle_data`가 텍스트 조각별로 호출되므로 무시하고
    이어붙이면 자동으로 사라진다(태그 자체는 캡처하지 않으므로).
    """

    def __init__(self) -> None:
        super().__init__()
        self._capture: str | None = None
        self._current_url: str | None = None
        self._parts: list[str] = []
        self.results: list[SearchResult] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attrs_dict = dict(attrs)
        classes = (attrs_dict.get("class") or "").split()
        if "result__a" in classes:
            self._capture = "title"
            self._current_url = self._extract_target_url(attrs_dict.get("href") or "")
            self._parts = []
        elif "result__snippet" in classes:
            self._capture = "snippet"
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._capture is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._capture is None:
            return
        text = "".join(self._parts).strip()
        if self._capture == "title" and self._current_url:
            self.results.append(SearchResult(title=text, url=self._current_url))
        elif self._capture == "snippet" and self.results:
            last = self.results[-1]
            self.results[-1] = SearchResult(title=last.title, url=last.url, snippet=text)
        self._capture = None

    @staticmethod
    def _extract_target_url(href: str) -> str | None:
        """결과 링크에서 실제 대상 URL을 뽑는다.

        실측(2026-07, 같은 세션 안에서 영어 쿼리와 한국어 쿼리로 각각 확인):
        DuckDuckGo는 쿼리에 따라 두 형식을 섞어 준다 —
        (1) 리다이렉트 링크 ``//duckduckgo.com/l/?uddg=<인코딩된 URL>&rut=...``
            (영어 쿼리 "python asyncio tutorial"에서 관찰),
        (2) 그냥 절대 URL ``https://velog.io/...`` (한국어 쿼리
            "비동기 프로그래밍 개념 설명"에서 관찰). (1)만 처리하도록 짜서
            처음엔 (2) 형식의 결과를 전부 조용히 버렸다(빈 결과 반환, 에러
            없음) — 실제 book-forge research를 한국어 챕터 제목으로 돌려보고서야
            발견했다. 이제 uddg 파라미터가 있으면 리다이렉트로, 없고 http(s)
            절대 URL이면 그대로 대상으로 인정한다.
        """
        if not href:
            return None
        parsed = urlparse(href)
        query = parse_qs(parsed.query)
        if "uddg" in query:
            target = query["uddg"][0]
            return unquote(target) if target else None
        if parsed.scheme in ("http", "https"):
            return href
        return None


def search_web(query: str, *, max_results: int = 5, timeout: int = 15) -> list[SearchResult]:
    """쿼리 문자열로 DuckDuckGo를 검색해 후보 URL을 최대 max_results개 반환한다.

    다른 사용자에게 자동으로 요청을 보내는 크롤러가 아니라, 저자가 지정한(또는
    ResearchAgent가 생성한) 쿼리 하나를 그 자리에서 한 번 검색하는 동작이다
    (재귀적으로 결과를 따라가지 않음 — knowledge/sources.py의 load_url_source()와
    같은 원칙).
    """
    import requests  # 코어 의존성 — [rag] extra 없이도 이미 설치돼 있음

    response = requests.post(
        _SEARCH_URL,
        data={"q": query},
        timeout=timeout,
        headers={"User-Agent": _USER_AGENT},
    )
    response.raise_for_status()

    parser = _DuckDuckGoResultParser()
    parser.feed(response.text)
    return parser.results[:max_results]
