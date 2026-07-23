"""ChatAgent — 프로젝트 지식창고 기반 대화형 Q&A (일반 능력 E: 독자 상호작용).

ChapterDrafterAgent/ReferenceTableAgent와 계측 배선 원리는 같다(rag_mode=True로
HallucinationDetector 자동 활성화) — 산출물이 파일로 저장되는 챕터가 아니라
REPL에 즉시 출력되는 답변이라는 점만 다르다.

conversation_history는 rag_mode의 context_arg("sources")와는 별개다 —
HallucinationDetector는 여전히 지식창고 발췌문(sources)만 근거로 환각을
채점한다. 대화 이력은 순수하게 프롬프트에 "이전 대화" 섹션으로 얹혀 LLM이
"방금 말한 그거" 같은 지시대명사·이어지는 질문을 이해하게 돕는 용도다 — 세션
수준 지표(context_retention 등)는 chat_cmd.py가 ConversationSession으로
별도 계산한다.
"""
from __future__ import annotations

from typing import Callable

from agent_evaluator import PerformanceMonitor, SLAConfig, agent_eval
from agent_evaluator.decorators import EvalMetadata

from book_forge.llm.provider import LLM

CHAT_SYSTEM_PROMPT = (
    "당신은 이 프로젝트의 지식창고를 근거로 질문에 답하는 도우미입니다. "
    "제공된 발췌문에 없는 내용은 지어내지 말고, 모르면 모른다고 답하세요. "
    "이전 대화가 주어지면 맥락을 참고해 일관되게 답하세요."
)

CHAT_PROMPT = """다음 발췌문을 참고해 질문에 답하세요.

--- 참고 발췌 ---
{sources}{history_block}

--- 질문 ---
{question}
"""

_HISTORY_BLOCK_TEMPLATE = "\n\n--- 이전 대화 ---\n{history}"

AnswerFn = Callable[..., str]


def build_answer_question(llm: LLM, monitor: PerformanceMonitor) -> AnswerFn:
    @agent_eval(
        monitor,
        task_type="information_retrieval",
        question_arg="question",
        rag_mode=True,
        context_arg="sources",
        sla=SLAConfig(p95_ms=30_000, p99_ms=60_000),
    )
    def answer_question(
        question: str, sources: str, conversation_history: str = "", ground_truth: str = ""
    ) -> tuple[str, EvalMetadata]:
        history_block = (
            _HISTORY_BLOCK_TEMPLATE.format(history=conversation_history)
            if conversation_history
            else ""
        )
        prompt = CHAT_PROMPT.format(
            sources=sources[:6000], history_block=history_block, question=question
        )
        answer = llm.generate(prompt, system=CHAT_SYSTEM_PROMPT, max_tokens=1500)
        return answer, EvalMetadata(extra={"phase": "chat"})

    return answer_question
