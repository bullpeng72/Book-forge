"""agents/research_agent.py — parse_search_queries()/build_generate_search_queries() 테스트."""
from pathlib import Path

from book_forge.agents.research_agent import build_generate_search_queries, parse_search_queries
from book_forge.eval.monitor import build_book_monitor

WELL_FORMED = """QUERY: python asyncio tutorial 2025
QUERY: asyncio event loop 공식 문서
QUERY: python async await 예제
"""


def test_parse_search_queries_well_formed() -> None:
    queries = parse_search_queries(WELL_FORMED)
    assert queries == [
        "python asyncio tutorial 2025",
        "asyncio event loop 공식 문서",
        "python async await 예제",
    ]


def test_parse_search_queries_ignores_non_query_lines() -> None:
    text = "설명 문장입니다.\nQUERY: 쿼리 1\n다른 잡담"
    assert parse_search_queries(text) == ["쿼리 1"]


def test_parse_search_queries_no_matches_returns_empty_list() -> None:
    assert parse_search_queries("형식을 전혀 안 지킨 텍스트") == []


def test_parse_search_queries_deduplicates() -> None:
    text = "QUERY: 같은 쿼리\nQUERY: 같은 쿼리\nQUERY: 다른 쿼리"
    assert parse_search_queries(text) == ["같은 쿼리", "다른 쿼리"]


def test_parse_search_queries_respects_max_queries() -> None:
    text = "QUERY: a\nQUERY: b\nQUERY: c\nQUERY: d"
    assert parse_search_queries(text, max_queries=2) == ["a", "b"]


class FakeLLM:
    model = "fake"

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        assert "챕터 제목" in prompt or "테스트 챕터" in prompt
        return WELL_FORMED


def test_build_generate_search_queries_returns_llm_response(tmp_path: Path) -> None:
    monitor = build_book_monitor(output_dir=str(tmp_path / "eval_results"))
    generate = build_generate_search_queries(FakeLLM(), monitor)

    result = generate(chapter_title="테스트 챕터", ground_truth="테스트 챕터")

    assert "QUERY:" in result
    assert parse_search_queries(result)
