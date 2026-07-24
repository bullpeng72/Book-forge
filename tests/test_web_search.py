"""knowledge/web_search.py — search_web() 테스트.

fixture HTML은 실제 DuckDuckGo html.duckduckgo.com/html/ 응답을 2026-07에 직접
받아 구조를 확인한 뒤 축약한 것이다(리다이렉트 링크의 uddg 인코딩 형식 포함) —
실제 markup과 어긋나면 파서가 조용히 빈 결과를 반환할 위험이 있어, 진짜
구조를 그대로 반영해 회귀를 잡는다.
"""
from book_forge.knowledge.web_search import SearchResult, search_web

_SAMPLE_HTML = """
<div class="results">
  <div class="result results_links results_links_deep web-result ">
    <div class="links_main links_deep result__body">
      <h2 class="result__title">
        <a rel="nofollow" class="result__a"
           href="//duckduckgo.com/l/?uddg=https%3A%2F%2Frealpython.com%2Fasync%2Dio%2Dpython%2F&amp;rut=abc">
          Python&#x27;s asyncio: A Hands-On Walkthrough - Real Python
        </a>
      </h2>
      <div class="result__extras">
        <a class="result__snippet"
           href="//duckduckgo.com/l/?uddg=https%3A%2F%2Frealpython.com%2Fasync%2Dio%2Dpython%2F&amp;rut=abc">
          <b>Python&#x27;s</b> <b>asyncio</b> library enables concurrent code with async/await.
        </a>
      </div>
    </div>
  </div>
  <div class="result results_links results_links_deep web-result ">
    <div class="links_main links_deep result__body">
      <h2 class="result__title">
        <a rel="nofollow" class="result__a"
           href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.python.org%2F3%2Flibrary%2Fasyncio.html&amp;rut=def">
          asyncio — Asynchronous I/O — Python documentation
        </a>
      </h2>
      <div class="result__extras">
        <a class="result__snippet"
           href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.python.org%2F3%2Flibrary%2Fasyncio.html&amp;rut=def">
          asyncio is a library to write concurrent code using the async/await syntax.
        </a>
      </div>
    </div>
  </div>
</div>
"""


# DuckDuckGo가 항상 uddg 리다이렉트 링크를 주는 게 아니다 — 실측 확인(2026-07):
# 한국어 쿼리("비동기 프로그래밍 개념 설명")에서는 절대 URL을 href에 그대로
# 준다. 이 형식만 처리하고 위 _SAMPLE_HTML(리다이렉트 형식)만 테스트했을 때는
# 실제 book-forge research 실행에서 결과가 통째로 0개로 나오는 회귀가 있었다.
_SAMPLE_HTML_DIRECT_LINKS = """
<div class="results">
  <div class="result results_links results_links_deep web-result ">
    <div class="links_main links_deep result__body">
      <h2 class="result__title">
        <a rel="nofollow" class="result__a"
           href="https://velog.io/@khy226/%EB%8F%99%EA%B8%B0-%EB%B9%84%EB%8F%99%EA%B8%B0%EB%9E%80-Promise">
          동기, 비동기란? (+Promise, async/await 개념) - 벨로그
        </a>
      </h2>
      <div class="result__extras">
        <a class="result__snippet"
           href="https://velog.io/@khy226/%EB%8F%99%EA%B8%B0-%EB%B9%84%EB%8F%99%EA%B8%B0%EB%9E%80-Promise">
          <b>비동기</b> 처리를 예로 Web API, Ajax, setTimeout 등이 있다.
        </a>
      </div>
    </div>
  </div>
</div>
"""


class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_search_web_parses_titles_urls_and_snippets(monkeypatch) -> None:
    def fake_post(url, data=None, timeout=None, headers=None):
        assert url == "https://html.duckduckgo.com/html/"
        assert data == {"q": "python asyncio tutorial"}
        assert headers is not None and "User-Agent" in headers
        return _FakeResponse(_SAMPLE_HTML)

    import requests

    monkeypatch.setattr(requests, "post", fake_post)

    results = search_web("python asyncio tutorial")

    assert results == [
        SearchResult(
            title="Python's asyncio: A Hands-On Walkthrough - Real Python",
            url="https://realpython.com/async-io-python/",
            snippet="Python's asyncio library enables concurrent code with async/await.",
        ),
        SearchResult(
            title="asyncio — Asynchronous I/O — Python documentation",
            url="https://docs.python.org/3/library/asyncio.html",
            snippet="asyncio is a library to write concurrent code using the async/await syntax.",
        ),
    ]


def test_search_web_parses_direct_absolute_url_links(monkeypatch) -> None:
    def fake_post(url, data=None, timeout=None, headers=None):
        return _FakeResponse(_SAMPLE_HTML_DIRECT_LINKS)

    import requests

    monkeypatch.setattr(requests, "post", fake_post)

    results = search_web("비동기 프로그래밍 개념 설명")

    assert results == [
        SearchResult(
            title="동기, 비동기란? (+Promise, async/await 개념) - 벨로그",
            url="https://velog.io/@khy226/%EB%8F%99%EA%B8%B0-%EB%B9%84%EB%8F%99%EA%B8%B0%EB%9E%80-Promise",
            snippet="비동기 처리를 예로 Web API, Ajax, setTimeout 등이 있다.",
        )
    ]


def test_search_web_respects_max_results(monkeypatch) -> None:
    import requests

    monkeypatch.setattr(
        requests, "post", lambda url, data=None, timeout=None, headers=None: _FakeResponse(
            _SAMPLE_HTML
        )
    )

    results = search_web("python asyncio tutorial", max_results=1)
    assert len(results) == 1
    assert results[0].url == "https://realpython.com/async-io-python/"


def test_search_web_empty_page_returns_no_results(monkeypatch) -> None:
    import requests

    monkeypatch.setattr(
        requests, "post",
        lambda url, data=None, timeout=None, headers=None: _FakeResponse("<div>No results.</div>"),
    )
    assert search_web("아무도 안 검색하는 희귀 쿼리") == []


def test_search_web_raises_on_http_error(monkeypatch) -> None:
    import requests

    monkeypatch.setattr(
        requests, "post",
        lambda url, data=None, timeout=None, headers=None: _FakeResponse("", status_code=503),
    )
    try:
        search_web("아무 쿼리")
        raised = False
    except RuntimeError:
        raised = True
    assert raised
