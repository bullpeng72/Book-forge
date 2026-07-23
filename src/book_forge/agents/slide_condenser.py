"""SlideCondenserAgent — 책 섹션 하나 → 발표 슬라이드 한 장(TITLE/BULLET*/NOTES).

Lecture_forge의 `improve --to-slides`(섹션별 LLM 재작성, ≤35자 제목)와 같은
문제의식이지만, JSON이 아니라 줄 단위 접두어 형식을 쓴다 — 로컬 소형 Ollama
모델은 유효한 JSON을 안정적으로 못 지키는 경우가 많아, 접두어 매칭이 더
관대하고 실패에 강하다(형식을 어겨도 파싱이 완전히 죽지 않고 폴백한다).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from agent_evaluator import ExplainabilityConfig, InstructionConfig, PerformanceMonitor, SLAConfig, agent_eval
from agent_evaluator.decorators import EvalMetadata

from book_forge.agents.prompts import SLIDE_PROMPT, SLIDE_SYSTEM_PROMPT
from book_forge.llm.provider import LLM

CondenseFn = Callable[..., str]

MAX_TITLE_CHARS = 35


@dataclass(frozen=True)
class SlideContent:
    title: str
    bullets: list[str]
    notes: str


def parse_slide_response(text: str, fallback_title: str) -> SlideContent:
    """TITLE:/BULLET:/NOTES: 접두어 줄을 관대하게 파싱한다.

    형식을 지키지 않은 응답도 완전히 버리지 않고 최선의 폴백을 만든다 —
    슬라이드 한 장이 통째로 비는 것보다 다소 거친 폴백이 낫다는 판단.
    """
    title = fallback_title
    bullets: list[str] = []
    notes_parts: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        upper = stripped.upper()
        if upper.startswith("TITLE:"):
            candidate = stripped.split(":", 1)[1].strip()
            if candidate:
                title = candidate
        elif upper.startswith("BULLET:"):
            candidate = stripped.split(":", 1)[1].strip()
            if candidate:
                bullets.append(candidate)
        elif upper.startswith("NOTES:"):
            notes_parts.append(stripped.split(":", 1)[1].strip())

    if not bullets:
        # 형식을 전혀 안 지켰으면 본문 첫 줄들을 그대로 bullet 하나로 폴백한다.
        fallback_text = " ".join(text.strip().splitlines()[:2]).strip()
        bullets = [fallback_text[:200]] if fallback_text else ["(내용 없음)"]

    return SlideContent(
        title=title[:60],
        bullets=bullets[:5],
        notes=" ".join(p for p in notes_parts if p),
    )


def build_condense_section(llm: LLM, monitor: PerformanceMonitor) -> CondenseFn:
    @agent_eval(
        monitor,
        task_type="document_creation",
        question_arg="heading",
        # Gate A: 슬라이드가 섹션 제목/핵심어를 실제로 반영했는지.
        instructions=InstructionConfig(fail_on_violation=False),
        explainability=ExplainabilityConfig(min_reasoning_length=10),
        # Gate D: 섹션 하나당 응답이 과도하게 느려지지 않는지 (챕터당 수 회 호출되므로).
        # p99_ms를 명시하지 않으면 기본값(10_000)이 p95_ms보다 작아져 SLAConfig가
        # 경고를 낸다 — p95 < p99 관계를 명시적으로 지켜준다.
        sla=SLAConfig(p95_ms=20_000, p99_ms=30_000),
    )
    def condense_section(heading: str, body: str, ground_truth: str = "") -> tuple[str, EvalMetadata]:
        prompt = SLIDE_PROMPT.format(heading=heading, body=body[:3000])
        raw = llm.generate(prompt, system=SLIDE_SYSTEM_PROMPT, max_tokens=800)
        return raw, EvalMetadata(extra={"phase": "slide_condense", "heading": heading})

    return condense_section
