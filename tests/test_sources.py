"""knowledge/sources.py — 소스 어댑터 테스트 (실제 임베딩 호출 없이 청크 추출만 검증)."""
from pathlib import Path

import pytest

from book_forge.knowledge.sources import (
    load_code_repo_source,
    load_source,
    load_text_source,
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
