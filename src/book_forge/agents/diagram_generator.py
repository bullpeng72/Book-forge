"""DiagramGeneratorAgent — RAG 소스 발췌 → Mermaid 다이어그램 중심 챕터 (M5 확장,
9개 후보 기능의 7번). 일반 능력 B(콘텐츠 유형 분기)의 세 번째 전용 생성기.

ReferenceTableAgent(표)·ChapterDrafterAgent(서술형 산문)와 계측 배선(rag_mode=True로
HallucinationDetector 자동 활성화)은 동일하고 프롬프트/출력 형식만 다르다.

전에는 diagram content_type이 chapter_drafter.py의 일반 서술형 생성기에
전용 프롬프트만 얹는 방식이었다 — B의 다른 전용 생성기(reference_table.py)와
패턴이 달랐다. 이 모듈이 diagram을 reference_table과 같은 "독립 에이전트"
패턴으로 승격한다(draft_cmd.py가 chapter_drafter 대신 이 모듈을 호출).

이 에이전트는 "검증 가능한 형태로 생성"까지만 책임진다 — 생성된 mermaid
블록이 실제로 구조적으로 유효한지는 이 에이전트가 아니라
agents/demonstration_verifier.py(D, draft_cmd.py가 생성 직후 호출)가 검증한다.
"""
from __future__ import annotations

from typing import Callable

from agent_evaluator import PerformanceMonitor, SLAConfig, ThreatSeverityConfig, agent_eval
from agent_evaluator.decorators import EvalMetadata

from book_forge.llm.provider import LLM

DIAGRAM_SYSTEM_PROMPT = (
    "당신은 기술 도서 다이어그램 편집자입니다. 제공된 소스 발췌문에 근거해 "
    "개념·흐름·구조를 Mermaid 다이어그램으로 시각화합니다. 소스에 없는 "
    "관계나 단계를 지어내지 마세요."
)

DIAGRAM_PROMPT = """다음 챕터를 다이어그램 중심으로 작성하세요.

챕터 제목: {chapter_title}

--- 참고 소스 발췌 ---
{sources}

`# Chapter {chapter_no}: {chapter_title}` 로 시작하고, 아래 구조를 반드시
포함하세요:
1. 1~2문단의 짧은 도입부
2. ```mermaid 코드 블록 최소 1개 — `graph`/`flowchart`/`sequenceDiagram`/
   `classDiagram`/`stateDiagram` 중 하나로 시작하고, 실제 노드/엣지를 포함해야
   합니다(타입 선언만 있는 빈 다이어그램 금지)
3. 다이어그램 각 요소에 대한 간단한 설명

소스에 근거하지 않은 사실은 작성하지 마세요."""

GenerateFn = Callable[..., str]


def build_generate_diagram(llm: LLM, monitor: PerformanceMonitor) -> GenerateFn:
    @agent_eval(
        monitor,
        task_type="document_creation",
        question_arg="chapter_title",
        rag_mode=True,
        context_arg="sources",
        sla=SLAConfig(p95_ms=60_000, p99_ms=90_000),
        threat_severity=ThreatSeverityConfig(),
    )
    def generate_diagram(
        chapter_title: str,
        chapter_no: int,
        sources: str,
        ground_truth: str = "",
    ) -> tuple[str, EvalMetadata]:
        prompt = DIAGRAM_PROMPT.format(
            chapter_title=chapter_title, chapter_no=chapter_no, sources=sources[:6000]
        )
        diagram_md = llm.generate(prompt, system=DIAGRAM_SYSTEM_PROMPT, max_tokens=3000)
        return diagram_md, EvalMetadata(extra={"phase": "diagram", "chapter_no": chapter_no})

    return generate_diagram
