"""ReferenceTableAgent — RAG 소스에서 구조화된 사실을 추출해 마크다운 표로 만든다
(일반 능력 B: 콘텐츠 유형 분기의 첫 전용 생성기).

ChapterDrafterAgent(서술형 산문)와 프롬프트/출력 형식만 다르고 나머지 계측
배선(rag_mode=True로 HallucinationDetector 자동 활성화)은 동일하다 — 표 형태
콘텐츠도 서술형과 똑같이 "소스에 없는 값을 지어내면 안 된다"는 근거 검증이 필요하다.
"""
from __future__ import annotations

from typing import Callable

from agent_evaluator import PerformanceMonitor, SLAConfig, ThreatSeverityConfig, agent_eval
from agent_evaluator.decorators import EvalMetadata

from book_forge.llm.provider import LLM

REFERENCE_TABLE_SYSTEM_PROMPT = (
    "당신은 기술 문서 편집자입니다. 제공된 소스 발췌문에서 구조화된 사실(용어,"
    "API/설정 이름, 명령어, 파라미터 등)만 추출해 마크다운 표로 정리합니다. "
    "소스에 명시되지 않은 값은 만들어내지 말고, 확인 안 되면 해당 행을 생략하세요."
)

REFERENCE_TABLE_PROMPT = """다음 챕터를 레퍼런스 표로 작성하세요.

챕터 제목: {chapter_title}

--- 참고 소스 발췌 ---
{sources}

`# Chapter {chapter_no}: {chapter_title}` 로 시작하고, 소스에서 확인되는 항목만
마크다운 표(헤더 행 포함)로 정리하세요. 표 앞에 1~2문장의 짧은 소개만 넣고,
서술형 설명 문단은 쓰지 마세요."""

GenerateFn = Callable[..., str]


def build_generate_reference_table(llm: LLM, monitor: PerformanceMonitor) -> GenerateFn:
    @agent_eval(
        monitor,
        task_type="document_creation",
        question_arg="chapter_title",
        rag_mode=True,
        context_arg="sources",
        sla=SLAConfig(p95_ms=60_000, p99_ms=90_000),
        threat_severity=ThreatSeverityConfig(),
    )
    def generate_reference_table(
        chapter_title: str,
        chapter_no: int,
        sources: str,
        ground_truth: str = "",
    ) -> tuple[str, EvalMetadata]:
        prompt = REFERENCE_TABLE_PROMPT.format(
            chapter_title=chapter_title, chapter_no=chapter_no, sources=sources[:6000]
        )
        table_md = llm.generate(prompt, system=REFERENCE_TABLE_SYSTEM_PROMPT, max_tokens=3000)
        return table_md, EvalMetadata(
            extra={"phase": "reference_table", "chapter_no": chapter_no}
        )

    return generate_reference_table
