"""ResearchAgent — 챕터 제목에서 검색 쿼리를 생성한다(일반 능력 N 전체 범위,
SPEC.md 항목 N).

지금까지 Book-forge는 저자가 URL을 직접 --source로 지정해야만 웹 소스를 쓸 수
있었다 — "이 주제에 맞는 자료를 찾아온다"는 검색 단계 자체가 없었다. 이
에이전트는 그 첫 단계(쿼리 생성)만 담당한다. 실제 검색 실행은
`knowledge/web_search.py::search_web()`이 맡는다(관심사 분리 — 이 파일은
LLM 호출만, 검색은 순수 HTTP+파싱).
"""
from __future__ import annotations

from typing import Callable

from agent_evaluator import InstructionConfig, PerformanceMonitor, agent_eval
from agent_evaluator.decorators import EvalMetadata

from book_forge.agents.prompts import RESEARCH_QUERY_PROMPT, RESEARCH_QUERY_SYSTEM_PROMPT
from book_forge.llm.provider import LLM

GenerateQueriesFn = Callable[..., str]


def build_generate_search_queries(llm: LLM, monitor: PerformanceMonitor) -> GenerateQueriesFn:
    @agent_eval(
        monitor,
        task_type="planning",
        question_arg="chapter_title",
        instructions=InstructionConfig(fail_on_violation=False),
    )
    def generate_search_queries(
        chapter_title: str, ground_truth: str = ""
    ) -> tuple[str, EvalMetadata]:
        prompt = RESEARCH_QUERY_PROMPT.format(chapter_title=chapter_title)
        raw = llm.generate(prompt, system=RESEARCH_QUERY_SYSTEM_PROMPT, max_tokens=300)
        return raw, EvalMetadata(extra={"phase": "research_query_generation"})

    return generate_search_queries


def parse_search_queries(text: str, *, max_queries: int = 3) -> list[str]:
    """``QUERY: <쿼리>`` 줄을 관대하게 파싱한다. 형식을 어겨도 빈 리스트만
    반환하고 예외를 던지지 않는다(agents/alternative_suggester.py의
    parse_alternatives()와 같은 원칙) — 호출부(research_cmd.py)가 "쿼리 생성
    실패, 챕터 제목 자체를 쿼리로 대체" 폴백을 결정할 수 있게."""
    queries: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.upper().startswith("QUERY:"):
            continue
        query = stripped.split(":", 1)[1].strip()
        if query and query not in queries:
            queries.append(query)
        if len(queries) >= max_queries:
            break
    return queries
