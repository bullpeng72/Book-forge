"""ChapterDrafterAgent — RAG 소스 발췌 → 챕터 초안 마크다운 (M5, 옵션).

`rag_mode=True`는 agent_evaluator 내부에서 `enable_hallucination_detection=True`를
자동 설정한다(decorators.py E2) — 별도로 Gate C 환각 탐지를 켤 필요가 없다.
`context_arg="sources"`를 명시했으므로, HallucinationDetector가 `sources`(RAG
발췌문) 대비 `response`(초안)의 근거 없는 서술을 자동으로 채점한다.

content_type이 exercise면 전용 프롬프트로 코드 블록 생성을 명시적으로
요구한다(일반 능력 D 강화 — draft_cmd.py의 demonstration_verifier가 생성 직후
그 블록의 실존/유효성을 정적으로 검증하므로, 검증 대상이 애초에 생성되도록
프롬프트가 보장해야 한다). diagram은 여기서 다루지 않는다 — 전용
DiagramGeneratorAgent(agents/diagram_generator.py)로 승격됐다(reference_table.py와
같은 "독립 에이전트" 패턴, draft_cmd.py가 content_type으로 분기해서 호출한다).
"""
from __future__ import annotations

from typing import Callable

from agent_evaluator import PerformanceMonitor, SLAConfig, ThreatSeverityConfig, agent_eval
from agent_evaluator.decorators import EvalMetadata

from book_forge.agents.prompts import DRAFT_PROMPT, DRAFT_PROMPT_EXERCISE, DRAFT_SYSTEM_PROMPT
from book_forge.llm.provider import LLM

DraftFn = Callable[..., str]

_CONTENT_TYPE_PROMPTS = {
    "exercise": DRAFT_PROMPT_EXERCISE,
}


def build_draft_chapter(llm: LLM, monitor: PerformanceMonitor) -> DraftFn:
    @agent_eval(
        monitor,
        task_type="document_creation",
        question_arg="chapter_title",
        rag_mode=True,
        context_arg="sources",
        # Gate D: 소스가 길면 응답이 오래 걸릴 수 있어 여유 있게 설정.
        sla=SLAConfig(p95_ms=60_000, p99_ms=90_000),
        # Gate E: 외부 PDF/문서(RAG 소스)에 프롬프트 인젝션이 섞여 있을 가능성.
        threat_severity=ThreatSeverityConfig(),
    )
    def draft_chapter(
        chapter_title: str,
        chapter_no: int,
        sources: str,
        ground_truth: str = "",
        content_type: str = "narrative",
    ) -> tuple[str, EvalMetadata]:
        template = _CONTENT_TYPE_PROMPTS.get(content_type, DRAFT_PROMPT)
        prompt = template.format(
            chapter_title=chapter_title, chapter_no=chapter_no, sources=sources[:6000]
        )
        draft_md = llm.generate(prompt, system=DRAFT_SYSTEM_PROMPT, max_tokens=3000)
        return draft_md, EvalMetadata(extra={"phase": "drafting", "chapter_no": chapter_no})

    return draft_chapter
