"""knowledge/sources.py — 소스 어댑터 테스트 (실제 임베딩 호출 없이 청크 추출만 검증)."""
from pathlib import Path

import pytest

from book_forge.knowledge.sources import (
    extract_text_from_html,
    load_code_repo_source,
    load_source,
    load_text_source,
    load_url_source,
)


def test_load_text_source_chunks_markdown_file(tmp_path: Path) -> None:
    md = tmp_path / "notes.md"
    md.write_text("# 제목\n\n본문 내용입니다.", encoding="utf-8")

    chunks = load_text_source(md, chunk_size=1000, overlap=0)
    assert len(chunks) == 1
    assert "# 제목" in chunks[0]


def test_load_code_repo_source_tags_file_path_and_recurses(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("def foo():\n    return 1\n", encoding="utf-8")
    (tmp_path / "pkg" / "b.py").write_text("def bar():\n    return 2\n", encoding="utf-8")
    (tmp_path / "readme.txt").write_text("무시되는 확장자", encoding="utf-8")

    chunks = load_code_repo_source(tmp_path, chunk_size=1000, overlap=0)
    joined = "\n".join(chunks)
    assert "pkg/a.py" in joined or "pkg\\a.py" in joined  # 경로 태그 포함
    assert "def foo" in joined
    assert "def bar" in joined
    assert "무시되는 확장자" not in joined  # .txt는 기본 확장자 목록에 없음


def test_load_code_repo_source_skips_pycache_and_git(tmp_path: Path) -> None:
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "cached.py").write_text("skip me", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config.py").write_text("skip me too", encoding="utf-8")
    (tmp_path / "real.py").write_text("keep me", encoding="utf-8")

    chunks = load_code_repo_source(tmp_path, chunk_size=1000, overlap=0)
    joined = "\n".join(chunks)
    assert "skip me" not in joined
    assert "keep me" in joined


def test_load_source_dispatches_by_directory(tmp_path: Path) -> None:
    (tmp_path / "x.py").write_text("print('hi')", encoding="utf-8")
    chunks = load_source(tmp_path)
    assert any("print" in c for c in chunks)


def test_load_source_dispatches_by_text_extension(tmp_path: Path) -> None:
    f = tmp_path / "doc.md"
    f.write_text("문서 내용", encoding="utf-8")
    chunks = load_source(f)
    assert chunks == ["문서 내용"]


def test_load_source_unsupported_extension_raises(tmp_path: Path) -> None:
    f = tmp_path / "data.bin"
    f.write_bytes(b"\x00\x01")
    with pytest.raises(ValueError, match="지원하지 않는 소스 형식"):
        load_source(f)


def test_extract_text_from_html_strips_script_style_and_head() -> None:
    html = """
    <html><head><title>무시됨</title><style>body{color:red}</style></head>
    <body>
      <script>alert('무시됨')</script>
      <h1>제목입니다</h1>
      <p>본문 내용입니다.</p>
    </body></html>
    """
    text = extract_text_from_html(html)
    assert "제목입니다" in text
    assert "본문 내용입니다" in text
    assert "무시됨" not in text
    assert "alert" not in text


def test_extract_text_from_html_empty_body_returns_empty_string() -> None:
    assert extract_text_from_html("<html><head><style>x</style></head></html>") == ""


class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_load_url_source_fetches_and_chunks(monkeypatch) -> None:
    html = "<html><body><p>웹 페이지 본문입니다.</p></body></html>"

    def fake_get(url, timeout=None, headers=None):
        assert url == "https://example.com/article"
        assert headers is not None and "User-Agent" in headers
        return _FakeResponse(html)

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    chunks = load_url_source("https://example.com/article", chunk_size=1000, overlap=0)
    assert len(chunks) == 1
    assert "웹 페이지 본문입니다" in chunks[0]
    assert "https://example.com/article" in chunks[0]  # 출처 태그 포함


def test_load_url_source_empty_page_returns_no_chunks(monkeypatch) -> None:
    import requests

    monkeypatch.setattr(
        requests, "get", lambda url, timeout=None, headers=None: _FakeResponse("<html></html>")
    )
    assert load_url_source("https://example.com/empty") == []


def test_load_url_source_raises_on_http_error(monkeypatch) -> None:
    import requests

    monkeypatch.setattr(
        requests, "get", lambda url, timeout=None, headers=None: _FakeResponse("", status_code=404)
    )
    with pytest.raises(RuntimeError, match="HTTP 404"):
        load_url_source("https://example.com/missing")


def test_load_source_dispatches_url_to_url_loader(monkeypatch) -> None:
    import requests

    html = "<html><body><p>디스패치 테스트</p></body></html>"
    monkeypatch.setattr(
        requests, "get", lambda url, timeout=None, headers=None: _FakeResponse(html)
    )
    chunks = load_source("https://example.com/x", chunk_size=1000, overlap=0)
    assert any("디스패치 테스트" in c for c in chunks)
