"""PlannerAgent — 주제/제약 → 기획안 마크다운.

@agent_eval을 직접 붙일 수 있는 이유: 이 함수의 산출물이 처음부터 마크다운
문자열이라 (str, EvalMetadata) 반환 계약과 자연스럽게 맞는다 (Lecture_forge가
Pydantic 모델 반환 때문에 Adapter 클래스를 따로 둔 것과 다른 지점).
"""
from __future__ import annotations

from typing import Callable

from agent_evaluator import (
    ExplainabilityConfig,
    GoalAlignmentConfig,
    InstructionConfig,
    PerformanceMonitor,
    agent_eval,
)
from agent_evaluator.decorators import EvalMetadata

from book_forge.agents.prompts import PLAN_PROMPT, PLAN_SYSTEM_PROMPT
from book_forge.llm.provider import LLM

ProposePlanFn = Callable[..., str]


def build_propose_plan(llm: LLM, monitor: PerformanceMonitor) -> ProposePlanFn:
    """monitor/llm을 주입해 계측이 붙은 propose_plan()을 만든다.

    monitor는 프로젝트(책)마다 새로 생성되므로(각자 다른 eval_results/ 경로),
    모듈 import 시점에 고정 데코레이션할 수 없다 — 팩토리 패턴으로 세션마다
    데코레이션한다.
    """

    @agent_eval(
        monitor,
        task_type="planning",
        question_arg="topic",
        # Gate A: 저자 제약이 기획안에 실제로 반영됐는지는 AccuracyEvaluator가
        # response(기획안) vs ground_truth(topic+constraints) 토큰 F1로 측정한다.
        goal_alignment=GoalAlignmentConfig(ignore_no_tool_tasks=False),
        instructions=InstructionConfig(fail_on_violation=False),
        explainability=ExplainabilityConfig(min_reasoning_length=30),
    )
    def propose_plan(
        topic: str, constraints: str, ground_truth: str = ""
    ) -> tuple[str, EvalMetadata]:
        prompt = PLAN_PROMPT.format(topic=topic, constraints=constraints or "없음")
        proposal_md = llm.generate(prompt, system=PLAN_SYSTEM_PROMPT)
        return proposal_md, EvalMetadata(extra={"phase": "planning", "topic": topic})

    return propose_plan
