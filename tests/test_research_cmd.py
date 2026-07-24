"""`book-forge research` 테스트 — 검색/임베딩/LLM을 결정론적 fake로 대체해
오프라인으로 검증한다(일반 능력 N 전체 범위).
"""
from pathlib import Path

from click.testing import CliRunner

import book_forge.cli.commands.research_cmd as research_cmd_module
import book_forge.cli.project_utils as project_utils
import book_forge.knowledge.store as store_module
from book_forge.cli.commands.research_cmd import _select_candidates
from book_forge.cli.main import cli
from book_forge.knowledge.store import default_store_path
from book_forge.knowledge.web_search import SearchResult


class _FakeLLM:
    model = "fake"

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        return "QUERY: 사과 재배 방법\nQUERY: 사과 품종 비교"


def _fake_vector(text: str) -> list[float]:
    return [1.0, 0.0] if "사과" in text else [0.0, 1.0]


def _fake_embed_text(text: str, *, base_url: str = "", model: str = "") -> list[float]:
    return _fake_vector(text)


def _fake_embed_texts(texts, *, base_url: str = "", model: str = "") -> list[list[float]]:
    return [_fake_vector(t) for t in texts]


def _make_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "projects" / "research-slug"
    project_dir.mkdir(parents=True)
    (project_dir / "01_목차.md").write_text("```toc\n1|과일학|1|사과 개론\n```\n", encoding="utf-8")
    return project_dir


_FAKE_RESULTS = [
    SearchResult(title="사과 재배 가이드", url="https://a.example/apple-guide", snippet="요약 A"),
    SearchResult(title="사과 품종 정리", url="https://b.example/apple-varieties", snippet="요약 B"),
]


def test_select_candidates_empty_input_selects_all() -> None:
    assert _select_candidates(_FAKE_RESULTS, "") == _FAKE_RESULTS


def test_select_candidates_zero_selects_none() -> None:
    assert _select_candidates(_FAKE_RESULTS, "0") == []


def test_select_candidates_parses_comma_separated_indices() -> None:
    assert _select_candidates(_FAKE_RESULTS, "2") == [_FAKE_RESULTS[1]]


def test_select_candidates_ignores_out_of_range_and_non_numeric() -> None:
    assert _select_candidates(_FAKE_RESULTS, "1, 99, abc") == [_FAKE_RESULTS[0]]


def test_research_fetches_and_appends_selected_candidates(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(research_cmd_module, "create_llm", lambda: _FakeLLM())
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr(research_cmd_module, "search_web", lambda q, max_results=5: _FAKE_RESULTS)

    def _fake_load_source(source, **kwargs):
        return [f"# 출처: {source}\n사과 관련 웹 콘텐츠"]

    monkeypatch.setattr("book_forge.knowledge.sources.load_source", _fake_load_source)

    project_dir = _make_project(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ["research", "research-slug", "1", "--yes"])

    assert result.exit_code == 0, result.output
    assert "후보 2개" in result.output
    assert "https://a.example/apple-guide" in result.output

    store = store_module.KnowledgeStore.load(default_store_path(project_dir))
    assert len(store) == 2
    assert any("a.example" in c for c in store.chunks)
    assert any("b.example" in c for c in store.chunks)


def test_research_interactive_selection_only_adds_chosen_candidates(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(research_cmd_module, "create_llm", lambda: _FakeLLM())
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr(research_cmd_module, "search_web", lambda q, max_results=5: _FAKE_RESULTS)

    def _fake_load_source(source, **kwargs):
        return [f"# 출처: {source}\n사과 관련 웹 콘텐츠"]

    monkeypatch.setattr("book_forge.knowledge.sources.load_source", _fake_load_source)

    _make_project(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ["research", "research-slug", "1"], input="1\n")

    assert result.exit_code == 0, result.output
    store_path = default_store_path(tmp_path / "projects" / "research-slug")
    store = store_module.KnowledgeStore.load(store_path)
    assert len(store) == 1
    assert "a.example" in store.chunks[0]


def test_research_no_selection_does_not_touch_store(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(research_cmd_module, "create_llm", lambda: _FakeLLM())
    monkeypatch.setattr(research_cmd_module, "search_web", lambda q, max_results=5: _FAKE_RESULTS)

    project_dir = _make_project(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ["research", "research-slug", "1"], input="0\n")

    assert result.exit_code == 0, result.output
    assert "채택된 URL이 없습니다" in result.output
    assert not default_store_path(project_dir).is_file()


def test_research_falls_back_to_chapter_title_on_malformed_query_response(
    tmp_path: Path, monkeypatch
) -> None:
    class _MalformedLLM:
        model = "fake"

        def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
            return "형식을 안 지키는 응답"

    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(research_cmd_module, "create_llm", lambda: _MalformedLLM())

    captured_queries = []

    def _fake_search(query, max_results=5):
        captured_queries.append(query)
        return []

    monkeypatch.setattr(research_cmd_module, "search_web", _fake_search)

    _make_project(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ["research", "research-slug", "1"])

    assert result.exit_code == 0, result.output
    assert captured_queries == ["사과 개론"]  # 챕터 제목으로 폴백
    assert "검색 결과가 없습니다" in result.output


def test_research_continues_after_one_query_search_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(research_cmd_module, "create_llm", lambda: _FakeLLM())
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)

    def _flaky_search(query, max_results=5):
        if query == "사과 재배 방법":
            raise RuntimeError("HTTP 503")
        return _FAKE_RESULTS

    monkeypatch.setattr(research_cmd_module, "search_web", _flaky_search)

    def _fake_load_source(source, **kwargs):
        return [f"# 출처: {source}\n사과 관련 웹 콘텐츠"]

    monkeypatch.setattr("book_forge.knowledge.sources.load_source", _fake_load_source)

    _make_project(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ["research", "research-slug", "1", "--yes"])

    assert result.exit_code == 0, result.output
    assert "검색 실패 — 건너뜁니다" in result.output
    assert "후보 2개" in result.output


def test_research_missing_chapter_raises(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    _make_project(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ["research", "research-slug", "99"])

    assert result.exit_code != 0
    assert "챕터 번호 99를 목차에서 찾을 수 없습니다" in result.output
