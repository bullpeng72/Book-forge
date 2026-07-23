"""CapstoneGeneratorAgent — 빈 실습 템플릿 + 별도 정답 생성 (9개 후보 기능의
9번, 일반 능력 B의 네 번째 전용 생성기).

기존 `exercise` content_type(`chapter_drafter.py`의 `DRAFT_PROMPT_EXERCISE`)은
"목표→실습 코드→해설"을 **한 파일**에 낸다 — 독자가 챕터를 열면 정답이 바로
보인다. capstone은 다른 생성 패턴이 필요하다: 독자가 실제로 풀어볼 빈
템플릿(TODO가 있는 미완성 스켈레톤)과, 별도 파일의 모범 정답+해설을 나눠
생성한다.

한 번의 LLM 호출로 두 부분을 구분자(``=== TEMPLATE ===``/``=== SOLUTION ===``)로
나눠 받는다 — 두 번 호출하면 템플릿과 정답이 서로 다른 문제를 다룰 위험이
있다(예: 템플릿은 리스트 실습인데 정답은 딕셔너리 실습을 생성). 반드시 한 번의
호출·같은 컨텍스트에서 나와야 한다.
"""
from __future__ import annotations

import re
from typing import Callable

from agent_evaluator import PerformanceMonitor, SLAConfig, ThreatSeverityConfig, agent_eval
from agent_evaluator.decorators import EvalMetadata

from book_forge.llm.provider import LLM

CAPSTONE_SYSTEM_PROMPT = (
    "당신은 기술 도서 실습 문제 출제자입니다. 독자가 직접 완성해야 할 빈 "
    "템플릿과, 별도의 모범 정답을 만듭니다. 템플릿에는 정답을 채우지 않습니다."
)

CAPSTONE_PROMPT = """다음 챕터를 실습/캡스톤 과제로 작성하세요.

챕터 제목: {chapter_title}

--- 참고 소스 발췌 ---
{sources}

두 부분을 반드시 순서대로, 아래 구분자를 정확히 지켜 출력하세요:

=== TEMPLATE ===
`# Chapter {chapter_no}: {chapter_title}` 로 시작하고 아래 구조를 포함하세요:
1. `## 목표` — 이 실습으로 무엇을 익히는지 2~3문장
2. `## 과제` — 독자가 무엇을 완성해야 하는지 설명
3. `## 시작 코드` — ```python 코드 블록 하나. 함수/클래스 뼈대만 있고, 본문은
   `# TODO: ...` 주석과 `pass` 또는 `raise NotImplementedError`로 남겨두세요.
   정답 로직을 채우지 마세요.

=== SOLUTION ===
`# Chapter {chapter_no}: {chapter_title} — 모범 정답` 으로 시작하고 아래 구조:
1. `## 모범 정답` — TEMPLATE의 TODO를 전부 채운 완전한 ```python 코드 블록
2. `## 해설` — 정답 코드가 왜 그렇게 동작하는지 소스에 근거해 설명

소스에 근거하지 않은 사실은 작성하지 마세요."""

_TEMPLATE_MARKER_RE = re.compile(r"===\s*TEMPLATE\s*===", re.IGNORECASE)
_SOLUTION_MARKER_RE = re.compile(r"===\s*SOLUTION\s*===", re.IGNORECASE)

CapstoneFn = Callable[..., str]


def build_generate_capstone(llm: LLM, monitor: PerformanceMonitor) -> CapstoneFn:
    @agent_eval(
        monitor,
        task_type="document_creation",
        question_arg="chapter_title",
        rag_mode=True,
        context_arg="sources",
        # 템플릿+정답 두 부분을 한 번에 생성하므로 서술형보다 응답이 길다 — SLA도 넉넉하게.
        sla=SLAConfig(p95_ms=90_000, p99_ms=120_000),
        threat_severity=ThreatSeverityConfig(),
    )
    def generate_capstone(
        chapter_title: str,
        chapter_no: int,
        sources: str,
        ground_truth: str = "",
    ) -> tuple[str, EvalMetadata]:
        prompt = CAPSTONE_PROMPT.format(
            chapter_title=chapter_title, chapter_no=chapter_no, sources=sources[:6000]
        )
        raw = llm.generate(prompt, system=CAPSTONE_SYSTEM_PROMPT, max_tokens=3500)
        return raw, EvalMetadata(extra={"phase": "capstone", "chapter_no": chapter_no})

    return generate_capstone


def parse_capstone_response(raw: str) -> tuple[str, str]:
    """``=== TEMPLATE ===``/``=== SOLUTION ===`` 구분자로 관대하게 분리한다.

    구분자가 없거나 순서가 뒤바뀌면(형식을 어긴 응답) 전체 텍스트를 템플릿으로,
    정답은 빈 문자열로 반환한다 — 예외를 던지지 않는다(parse_alternatives와
    같은 원칙). 호출부가 정답이 비어 있으면 검증 실패로 처리한다.
    """
    t_match = _TEMPLATE_MARKER_RE.search(raw)
    s_match = _SOLUTION_MARKER_RE.search(raw)

    if not t_match or not s_match or s_match.start() <= t_match.start():
        return raw.strip(), ""

    template = raw[t_match.end():s_match.start()].strip()
    solution = raw[s_match.end():].strip()
    return template, solution
