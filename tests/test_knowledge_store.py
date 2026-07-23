"""knowledge/store.py — KnowledgeStore 테스트. 실제 Ollama 임베딩 호출을 피하려고
embed_text()/embed_texts()를 결정론적 fake로 monkeypatch한다.
"""
from pathlib import Path

import pytest

import book_forge.knowledge.store as store_module
from book_forge.knowledge.store import KnowledgeStore, default_store_path


def _fake_vector(text: str) -> list[float]:
    return [1.0, 0.0] if "사과" in text else [0.0, 1.0]


def _fake_embed_text(text: str, *, base_url: str = "", model: str = "") -> list[float]:
    return _fake_vector(text)


def _fake_embed_texts(texts: list[str], *, base_url: str = "", model: str = "") -> list[list[float]]:
    return [_fake_vector(t) for t in texts]


def test_knowledge_store_empty_query_returns_empty_list() -> None:
    store = KnowledgeStore()
    assert store.query("아무거나") == []


def test_knowledge_store_add_empty_list_is_noop() -> None:
    store = KnowledgeStore()
    store.add([])
    assert len(store) == 0


def test_knowledge_store_query_ranks_by_similarity(monkeypatch) -> None:
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)

    store = KnowledgeStore()
    store.add(["사과에 대한 문장", "바나나에 대한 문장", "사과와 바나나 모두 언급"])
    assert len(store) == 3

    results = store.query("사과가 궁금해요", top_k=2)
    assert len(results) == 2
    assert all("사과" in r for r in results)
    assert "바나나에 대한 문장" not in results


def test_knowledge_store_query_with_scores_exposes_similarity(monkeypatch) -> None:
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)

    store = KnowledgeStore()
    store.add(["사과에 대한 문장", "바나나에 대한 문장"])

    scored = store.query_with_scores("사과가 궁금해요", top_k=2)
    assert len(scored) == 2
    scores_by_chunk = dict(scored)
    assert scores_by_chunk["사과에 대한 문장"] > scores_by_chunk["바나나에 대한 문장"]
    assert scores_by_chunk["사과에 대한 문장"] == pytest.approx(1.0)
    assert scores_by_chunk["바나나에 대한 문장"] == pytest.approx(0.0, abs=1e-6)


def test_knowledge_store_query_with_scores_empty_store() -> None:
    store = KnowledgeStore()
    assert store.query_with_scores("아무거나") == []


def test_knowledge_store_save_and_load_roundtrip(tmp_path: Path) -> None:
    store = KnowledgeStore(chunks=["청크1", "청크2"], _vectors=[[1.0, 0.0], [0.0, 1.0]])
    path = tmp_path / "knowledge" / "store.json"

    store.save(path)
    assert path.is_file()

    loaded = KnowledgeStore.load(path)
    assert loaded.chunks == ["청크1", "청크2"]
    assert loaded._vectors == [[1.0, 0.0], [0.0, 1.0]]


def test_knowledge_store_merge_appends_without_recomputing() -> None:
    a = KnowledgeStore(chunks=["a1"], _vectors=[[1.0, 0.0]])
    b = KnowledgeStore(chunks=["b1"], _vectors=[[0.0, 1.0]])

    a.merge(b)

    assert a.chunks == ["a1", "b1"]
    assert a._vectors == [[1.0, 0.0], [0.0, 1.0]]
    assert len(a) == 2


def test_default_store_path_is_under_knowledge_dir(tmp_path: Path) -> None:
    assert default_store_path(tmp_path) == tmp_path / "knowledge" / "store.json"
