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

from book_forge.agents.prompts import _CODE_STRUCTURE_BLOCK, TOC_PROMPT, TOC_SYSTEM_PROMPT
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
    def design_toc(
        proposal_md: str, code_structure: str = "", ground_truth: str = ""
    ) -> tuple[str, EvalMetadata]:
        # 일반 능력 S — code_structure(H가 만든 정적 분석 구조 요약)가 주어지면
        # 목차 설계 시점에 실제 모듈/클래스/함수 목록을 컨텍스트로 넣는다.
        # 지금까지는 --source가 draft 단계에서만 쓰여 목차가 코드를 전혀 못
        # 봤다 — 빈 문자열이면(코드 저장소 소스가 없거나 --source 자체가
        # 없는 기존 흐름) 기존 프롬프트와 동일하게 동작한다(하위 호환).
        code_structure_block = (
            _CODE_STRUCTURE_BLOCK.format(code_structure=code_structure[:6000])
            if code_structure
            else ""
        )
        prompt = TOC_PROMPT.format(proposal=proposal_md, code_structure_block=code_structure_block)
        toc_md = llm.generate(prompt, system=TOC_SYSTEM_PROMPT, max_tokens=6000)
        return toc_md, EvalMetadata(
            extra={"phase": "toc_design", "code_structure_used": bool(code_structure)}
        )

    return design_toc
