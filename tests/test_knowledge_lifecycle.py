"""knowledge/lifecycle.py — summarize_store() 테스트(Spec J)."""
from book_forge.knowledge.lifecycle import summarize_store
from book_forge.knowledge.store import KnowledgeStore


def test_summarize_store_groups_by_file_tag() -> None:
    store = KnowledgeStore(
        chunks=[
            "# 파일: a.py\ndef foo(): ...",
            "# 파일: a.py\ndef bar(): ...",
            "# 파일: b.py\ndef baz(): ...",
        ],
        _vectors=[[0.0], [0.0], [0.0]],
    )
    result = summarize_store(store)
    assert result == [("a.py", 2), ("b.py", 1)]


def test_summarize_store_groups_by_source_tag() -> None:
    store = KnowledgeStore(
        chunks=["# 출처: https://example.com/x\n본문 내용"],
        _vectors=[[0.0]],
    )
    result = summarize_store(store)
    assert result == [("https://example.com/x", 1)]


def test_summarize_store_untagged_chunks_grouped_last() -> None:
    store = KnowledgeStore(
        chunks=["# 파일: a.py\n내용", "태그 없는 청크", "또 다른 태그 없는 청크"],
        _vectors=[[0.0], [0.0], [0.0]],
    )
    result = summarize_store(store)
    assert result[-1] == ("(태그 없음)", 2)


def test_summarize_store_empty_store_returns_empty_list() -> None:
    assert summarize_store(KnowledgeStore()) == []
