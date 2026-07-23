"""TOCDesignerAgent — 승인된 기획안 → Part/Chapter 목차.

목차는 사람이 읽는 마크다운 + ScaffoldAgent가 파싱하는 ```toc 매니페스트
블록을 함께 담는다 (book_forge.models.parse_toc_manifest 참고).
"""
from __future__ import annotations

from typing import Callable

from agent_evaluator import (
    ContextRetentionConfig,
    PerformanceMonitor,
    PlanConfig,
    SubtaskConfig,
    agent_eval,
)
from agent_evaluator.decorators import EvalMetadata

from book_forge.agents.prompts import TOC_PROMPT, TOC_SYSTEM_PROMPT
from book_forge.llm.provider import LLM

DesignTocFn = Callable[..., str]


def build_design_toc(llm: LLM, monitor: PerformanceMonitor) -> DesignTocFn:
    @agent_eval(
        monitor,
        task_type="planning",
        question_arg="proposal_md",
        # Gate A: 챕터(subtask)들이 기획안의 커버리지를 충족하는지,
        # 기획안의 결정사항(대상독자·차별점 등)을 목차가 이어받는지.
        plan_tracking=PlanConfig(),
        subtask_tracking=SubtaskConfig(),
        context_retention=ContextRetentionConfig(),
    )
    def design_toc(proposal_md: str, ground_truth: str = "") -> tuple[str, EvalMetadata]:
        prompt = TOC_PROMPT.format(proposal=proposal_md)
        toc_md = llm.generate(prompt, system=TOC_SYSTEM_PROMPT, max_tokens=6000)
        return toc_md, EvalMetadata(extra={"phase": "toc_design"})

    return design_toc
