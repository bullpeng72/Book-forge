"""ModuleReferenceAgent — H(구조적 코드 인덱싱)가 파싱한 전체 모듈/클래스/함수
목록을 빠짐없이 다루는 레퍼런스 챕터를 만든다(일반 능력 T, SPEC.md 2부).

`reference_table.py`는 RAG로 검색된 소스 발췌문에서 "확인되는 값만" 표로
만든다 — 검색이 놓친 항목은 애초에 LLM 눈에 안 보이므로 조용히 빠진다(실측:
Book-forge 자신의 agents/ 13개 파일 중 4개만 우연히 top-k에 뽑혀 다뤄짐).
이 에이전트는 RAG 검색을 거치지 않고, H가 만든 구조 요약(모든 모듈/클래스/
함수를 결정론적으로 나열)을 그대로 `sources`로 받는다 — "어떤 항목이
존재하는가"는 코드가 이미 결정했으므로 LLM은 그 목록의 설명 문구만 채운다.
누락 여부는 `agents/demonstration_verifier.py::verify_module_reference_coverage()`가
생성 직후 정적으로 검증한다(reference_table의 "값을 지어내지 않았는가"
검증과 반대 방향 — 여기서는 "빠뜨리지 않았는가"를 본다).
"""
from __future__ import annotations

from typing import Callable

from agent_evaluator import PerformanceMonitor, SLAConfig, ThreatSeverityConfig, agent_eval
from agent_evaluator.decorators import EvalMetadata

from book_forge.llm.provider import LLM

MODULE_REFERENCE_SYSTEM_PROMPT = (
    "당신은 기술 문서 편집자입니다. 제공된 구조 요약(모듈/클래스/함수 목록)에 있는 "
    "항목만 표로 정리합니다. 목록에 없는 항목을 만들어내지 말고, 목록에 있는 "
    "항목은 하나도 빠짐없이 표에 포함하세요."
)

MODULE_REFERENCE_PROMPT = """다음 챕터를 구조 요약 기반 레퍼런스 표로 작성하세요.

챕터 제목: {chapter_title}

--- 구조 요약 (정적 분석, 아래 목록에 있는 항목만 다룰 것) ---
{sources}

`# Chapter {chapter_no}: {chapter_title}` 로 시작하고, 위 목록의 클래스/함수를
**하나도 빠짐없이** 마크다운 표(모듈 | 이름 | 설명)로 정리하세요. 설명은 주어진
docstring을 다듬어 한 줄로 쓰고, docstring이 없으면 "설명 없음"이라고 쓰세요.
표 앞에 1~2문장의 짧은 소개만 넣고, 목록에 없는 항목은 지어내지 마세요."""

GenerateFn = Callable[..., str]


def build_generate_module_reference(llm: LLM, monitor: PerformanceMonitor) -> GenerateFn:
    @agent_eval(
        monitor,
        task_type="document_creation",
        question_arg="chapter_title",
        rag_mode=True,
        context_arg="sources",
        sla=SLAConfig(p95_ms=90_000, p99_ms=120_000),
        threat_severity=ThreatSeverityConfig(),
    )
    def generate_module_reference(
        chapter_title: str,
        chapter_no: int,
        sources: str,
        ground_truth: str = "",
    ) -> tuple[str, EvalMetadata]:
        prompt = MODULE_REFERENCE_PROMPT.format(
            chapter_title=chapter_title, chapter_no=chapter_no, sources=sources[:8000]
        )
        table_md = llm.generate(prompt, system=MODULE_REFERENCE_SYSTEM_PROMPT, max_tokens=4000)
        return table_md, EvalMetadata(
            extra={"phase": "module_reference", "chapter_no": chapter_no}
        )

    return generate_module_reference
