"""AuthorReviewLoop — 기획안/목차 초안을 저자 피드백에 따라 반복 개정한다.

``conversation_eval``이 다회 대화에 자연스러워 보이지만 실제 소스
(``decorators.py``의 ``_CONVERSATION_EVAL_UNUSED_HARNESS_PARAMS``)를 확인한
결과, 30개 Harness Config 전부가 시그니처로만 받고 평가에는 반영되지 않는다
(SPEC-039 REQ-5, Non-Goal). ``LoopDetectionConfig``가 실제로 작동하려면 라운드를
독립된 TaskResult로 기록해야 하므로, ``conversation_eval`` 대신 라운드마다
``@agent_eval``을 개별 호출하는 방식을 쓴다.
"""
from __future__ import annotations

from typing import Callable

from agent_evaluator import LoopDetectionConfig, PerformanceMonitor, agent_eval
from agent_evaluator.decorators import EvalMetadata

from book_forge.agents.prompts import REVISE_PROMPT, REVISE_SYSTEM_PROMPT
from book_forge.llm.provider import LLM

ReviseFn = Callable[..., str]

MAX_REVIEW_ROUNDS = 5


def build_revise(llm: LLM, monitor: PerformanceMonitor) -> ReviseFn:
    @agent_eval(
        monitor,
        task_type="planning",
        question_arg="feedback",
        # 라운드+종류(kind)를 task_id에 넣어야 LoopDetectionConfig가 "같은 피드백이
        # 반복되는지"를 태스크 단위로 정확히 판정한다. task_id_fn은 (args, kwargs)를
        # 받으므로, 호출부는 반드시 키워드 인자로 호출해야 한다.
        task_id_fn=lambda args, kwargs: f"review_{kwargs['kind']}_r{kwargs['round_no']}",
        loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=3),
    )
    def revise(
        current_md: str, feedback: str, round_no: int, kind: str, ground_truth: str = ""
    ) -> tuple[str, EvalMetadata]:
        prompt = REVISE_PROMPT.format(current=current_md, feedback=feedback)
        revised_md = llm.generate(prompt, system=REVISE_SYSTEM_PROMPT, max_tokens=6000)
        return revised_md, EvalMetadata(
            extra={"phase": "review_loop", "kind": kind, "round_no": round_no}
        )

    return revise


def run_review_loop(
    *,
    kind: str,
    initial_md: str,
    revise_fn: ReviseFn,
    render: Callable[[str], None],
    ask_feedback: Callable[[], str],
) -> str:
    """초안을 보여주고, 승인될 때까지 피드백을 반영해 재생성한다.

    ask_feedback()이 빈 문자열 또는 승인 표시("y"/"yes"/"승인"/"ok")를 반환하면
    현재 초안을 그대로 확정한다. MAX_REVIEW_ROUNDS를 넘기면 무한 반복을 막기
    위해 최신 초안으로 강제 진행한다 (LoopDetectionConfig는 "같은 피드백의
    반복"만 잡지, 라운드 수 자체를 제한하지 않으므로 이 상한은 애플리케이션
    레벨의 별도 안전장치다).
    """
    current = initial_md
    round_no = 0
    while True:
        render(current)
        if round_no >= MAX_REVIEW_ROUNDS:
            return current
        feedback = ask_feedback()
        if not feedback or feedback.strip().lower() in {"y", "yes", "승인", "ok"}:
            return current
        round_no += 1
        current = revise_fn(
            current_md=current,
            feedback=feedback,
            round_no=round_no,
            kind=kind,
            ground_truth=feedback,
        )
