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


def test_query_with_scores_max_per_source_caps_dominant_file(monkeypatch) -> None:
    # Spec K 재현: 파일 하나(dominant.py)가 청크 대부분을 차지하면, 균형 조정 없이는
    # top_k 결과를 그 파일이 독점한다. max_per_source로 다른 소스에도 자리를 준다.
    # 동점 시 정렬 순서에 기대지 않도록 벡터를 직접 구성해 순위를 결정론적으로 만든다.
    monkeypatch.setattr(store_module, "embed_text", lambda t, **kw: [1.0, 0.0])
    chunks = [
        "# 파일: dominant.py\n청크 A",
        "# 파일: dominant.py\n청크 B",
        "# 파일: dominant.py\n청크 C",
        "# 파일: minor.py\n청크 D",
    ]
    vectors = [[1.0, 0.0], [0.9, 0.1], [0.8, 0.2], [0.7, 0.3]]
    store = KnowledgeStore(chunks=chunks, _vectors=vectors)

    balanced = store.query_with_scores("질문", top_k=2, max_per_source=1)
    labels = [chunk.split("\n")[0] for chunk, _ in balanced]
    assert labels == ["# 파일: dominant.py", "# 파일: minor.py"]

    unbalanced = store.query_with_scores("질문", top_k=2)
    unbalanced_labels = [chunk.split("\n")[0] for chunk, _ in unbalanced]
    assert unbalanced_labels == ["# 파일: dominant.py", "# 파일: dominant.py"]


def test_query_with_scores_max_per_source_none_is_unchanged_default(monkeypatch) -> None:
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)

    store = KnowledgeStore()
    store.add(["사과에 대한 문장", "바나나에 대한 문장", "사과와 바나나 모두 언급"])

    with_none = store.query_with_scores("사과가 궁금해요", top_k=2, max_per_source=None)
    without_param = store.query_with_scores("사과가 궁금해요", top_k=2)
    assert with_none == without_param


def test_query_with_scores_max_per_source_ignores_untagged_chunks(monkeypatch) -> None:
    # 태그 없는 청크(PDF 등)는 소스 식별이 안 되므로 균형 조정 대상이 아니다.
    monkeypatch.setattr(store_module, "embed_text", lambda t, **kw: [1.0, 0.0])
    chunks = ["청크 A(태그 없음)", "청크 B(태그 없음)", "청크 C(태그 없음)"]
    vectors = [[1.0, 0.0], [0.9, 0.1], [0.8, 0.2]]
    store = KnowledgeStore(chunks=chunks, _vectors=vectors)

    result = store.query_with_scores("질문", top_k=3, max_per_source=1)
    assert len(result) == 3  # 태그가 없어 전부 통과
