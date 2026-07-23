"""pdf_source.py — chunk_text() 순수 로직 테스트 (실제 PDF 파일 불필요)."""
from book_forge.knowledge.pdf_source import chunk_text


def test_chunk_text_splits_by_size_with_overlap() -> None:
    text = "가" * 1000
    chunks = chunk_text(text, chunk_size=400, overlap=100)
    assert len(chunks) == 4
    assert all(len(c) <= 400 for c in chunks)
    # overlap 검증: 두 번째 청크 앞부분이 첫 청크 뒷부분과 겹친다
    assert chunks[0][-100:] == chunks[1][:100]


def test_chunk_text_normalizes_whitespace() -> None:
    chunks = chunk_text("여러   공백과\n\n줄바꿈이   섞인   텍스트", chunk_size=100, overlap=0)
    assert len(chunks) == 1
    assert "  " not in chunks[0]


def test_chunk_text_empty_input_returns_empty_list() -> None:
    assert chunk_text("", chunk_size=100, overlap=10) == []
    assert chunk_text("   ", chunk_size=100, overlap=10) == []


def test_chunk_text_short_text_returns_single_chunk() -> None:
    chunks = chunk_text("짧은 텍스트", chunk_size=800, overlap=100)
    assert len(chunks) == 1
    assert chunks[0] == "짧은 텍스트"


def test_chunk_text_preserves_lines_when_collapse_disabled() -> None:
    code = "def foo():\n    return 1\n\n\ndef bar():\n    return 2\n"
    chunks = chunk_text(code, chunk_size=1000, overlap=0, collapse_whitespace=False)
    assert len(chunks) == 1
    assert "\n" in chunks[0]
    assert "    return 1" in chunks[0]  # 들여쓰기 보존


def test_chunk_text_collapses_by_default() -> None:
    code = "def foo():\n    return 1\n"
    chunks = chunk_text(code, chunk_size=1000, overlap=0)
    assert "\n" not in chunks[0]
