"""AlternativeSuggesterAgent — 낮은 소스 커버리지·실증 불가 신호가 나올 때
저자가 선택할 수 있는 대안을 제시한다 (일반 능력 F).

C(근거 검증 계층)·D(실증 가능성 게이트)가 "이대로 진행하면 위험하다"는 신호를
내면, 이 에이전트가 소비해서 구체적 대안을 만든다 — 단순 경고로 끝내지 않고
저자가 다음 행동을 고를 수 있게 하는 게 핵심.
"""
from __future__ import annotations

from typing import Callable

from agent_evaluator import ExplainabilityConfig, InstructionConfig, PerformanceMonitor, agent_eval
from agent_evaluator.decorators import EvalMetadata

from book_forge.agents.prompts import ALT_SUGGEST_PROMPT, ALT_SUGGEST_SYSTEM_PROMPT
from book_forge.llm.provider import LLM

SuggestFn = Callable[..., str]


def build_suggest_alternatives(llm: LLM, monitor: PerformanceMonitor) -> SuggestFn:
    @agent_eval(
        monitor,
        task_type="planning",
        question_arg="reason",
        # Gate A: 제안이 실제로 주어진 chapter_title/reason을 반영하는지.
        instructions=InstructionConfig(fail_on_violation=False),
        explainability=ExplainabilityConfig(min_reasoning_length=10),
    )
    def suggest_alternatives(
        chapter_title: str, reason: str, ground_truth: str = ""
    ) -> tuple[str, EvalMetadata]:
        prompt = ALT_SUGGEST_PROMPT.format(chapter_title=chapter_title, reason=reason)
        raw = llm.generate(prompt, system=ALT_SUGGEST_SYSTEM_PROMPT, max_tokens=800)
        return raw, EvalMetadata(extra={"phase": "alternative_suggestion", "reason": reason})

    return suggest_alternatives


def parse_alternatives(text: str) -> list[tuple[str, str]]:
    """``ALT: <요약> | <이유>`` 줄을 관대하게 파싱한다. 형식을 어겨도 빈 리스트만
    반환하고 예외를 던지지 않는다 — 호출부가 "제안 생성 실패"로 처리할 수 있게."""
    alternatives: list[tuple[str, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.upper().startswith("ALT:"):
            continue
        body = stripped.split(":", 1)[1].strip()
        if "|" in body:
            summary, reason = body.split("|", 1)
            alternatives.append((summary.strip(), reason.strip()))
        elif body:
            alternatives.append((body, ""))
    return alternatives
