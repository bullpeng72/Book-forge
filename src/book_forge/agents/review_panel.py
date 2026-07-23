"""ReviewPanelAgent — 다중 리뷰어 편집 패널 (일반 능력 G: 자기실증 예제).

Book-forge의 기존 6개 에이전트(Planner→TOCDesigner→ReviewLoop→Scaffold→
ChapterDrafter→SlideCondenser)는 전부 순차 파이프라인이다 — 서로 합의하거나,
충돌을 조정하거나, 역할을 나눠 맡는 상황이 한 번도 발생하지 않는다. 그래서
`book-forge gate`의 Gate F(Multi-Agent Coordination)는 지금까지 항상 N/A였다.

이 모듈이 Book-forge에서 처음으로 진짜 감독자-작업자(supervisor-worker) 패턴을
구현한다: 리뷰어(worker) 여러 명이 같은 챕터를 서로 다른 관점(정확성/가독성)에서
독립적으로 검토하고, ChiefEditorAgent(supervisor)가 그 판정을 종합해 최종
결론을 낸다. 합성 데모가 아니라 "초안을 승인 전에 다관점으로 검토"하는 실사용
가치가 있는 기능이고, 이 흐름 자체가 Gate F의 지금까지 비어있던 지표들을
실제로 채운다:

  - `AgentCoordinationTracker.track_interaction()` → coordination_score
    (감독자↔리뷰어 위임/응답을 실제로 기록)
  - `ConsensusConfig` → consensus_score (리뷰어 판정 간 합의도). 자유 텍스트
    어휘 유사도 대신 파싱된 VERDICT를 `agent_interactions=[{"agent","intent"}]`
    구조화 신호로 넘긴다(SPEC-009 REQ-1) — "같은 말을 다르게 썼는데 불일치로
    오판"되는 걸 피하기 위해서다.
  - `AgentRoleConfig` → role_compliance_score (각 리뷰어가 자기 관점에 맞는
    근거를 언급하고 다른 관점을 침범하지 않는지, allowed/forbidden_action_keywords로)
  - `ConflictResolutionConfig` → resolution_score (감독자가 리뷰어 간 불일치를
    실제로 언급하고 해결하는지, 응답 텍스트의 기본 한국어 마커로 판정)

`PropagationConfig`(정보 전파 충실도)는 이번 범위에 포함하지 않았다 — 자유
텍스트 근거를 key_facts로 어휘 매칭하는 건 한국어 토큰 분할 특성상 오탐이
잦아, 억지로 끼워 맞추기보다 다른 세 지표로 이미 Gate F가 실질적으로 채워지는
쪽을 택했다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

from agent_evaluator import (
    AgentRoleConfig,
    ConflictResolutionConfig,
    ConsensusConfig,
    PerformanceMonitor,
    agent_eval,
)
from agent_evaluator.decorators import EvalMetadata
from agent_evaluator.helpers.taskresult_helpers import eval_consensus

from book_forge.llm.provider import LLM

REVIEWER_SYSTEM_PROMPT = (
    "당신은 기술 도서 편집 검토자입니다. 담당 관점에서만 챕터를 평가하고, "
    "다른 관점의 판단은 하지 않습니다."
)

REVIEWER_PROMPT = """다음 챕터를 {focus_label} 관점에서만 검토하세요.

챕터 제목: {chapter_title}
검토 관점: {focus_description}

--- 챕터 본문 ---
{chapter_md}

출력 형식을 반드시 지키세요 (다른 텍스트 없이):
VERDICT: APPROVE 또는 REVISE
REASON: <1~2문장, {focus_label} 관점에서만>"""

CHIEF_EDITOR_SYSTEM_PROMPT = (
    "당신은 기술 도서 편집장입니다. 여러 검토자의 판정을 종합해 최종 결론을 "
    "내립니다. 검토자 간 판정이 다르면 그 불일치를 명시적으로 언급하고 이유를 "
    "들어 조정하세요."
)

CHIEF_EDITOR_PROMPT = """다음 챕터에 대한 검토자들의 판정을 종합해 최종 결론을 내리세요.

챕터 제목: {chapter_title}

--- 검토자 판정 ---
{reviews_text}

각 검토자의 판정이 같으면 합의된 결론을 그대로 반영하세요. 판정이 다르면 그
불일치를 명시적으로 언급한 뒤, 이유를 들어 최종적으로 해결하세요. 각 검토자가
제시한 근거를 최종 결론에 실제로 반영하세요.

출력 형식을 반드시 지키세요:
FINAL: APPROVE 또는 REVISE
SUMMARY: <검토자 근거를 반영한 2~4문장 결론>"""

# 리뷰어별 관점 — allowed는 "이 관점이면 최소 하나는 언급했을 근거 단어",
# forbidden은 "다른 관점을 침범하면 쓰였을 단어"로 AgentRoleConfig가 그대로 검사한다.
ACCURACY_REVIEWER = dict(
    role_name="정확성 검토자",
    focus_label="정확성(사실/근거)",
    focus_description=(
        "본문이 제공된 소스에 실제로 근거하는지, 사실 오류나 근거 없는 서술이 "
        "없는지만 평가하세요. 문체나 가독성은 언급하지 마세요."
    ),
    allowed_action_keywords=["근거", "사실", "소스", "정확"],
    forbidden_action_keywords=["가독성", "문체"],
)
READABILITY_REVIEWER = dict(
    role_name="가독성 검토자",
    focus_label="가독성(구조/설명)",
    focus_description=(
        "설명이 명확하고 독자가 따라가기 쉬운 구조인지만 평가하세요. 사실 "
        "정확성은 언급하지 마세요."
    ),
    allowed_action_keywords=["가독성", "구조", "설명", "이해"],
    forbidden_action_keywords=["근거", "사실"],
)
DEFAULT_REVIEWERS = (ACCURACY_REVIEWER, READABILITY_REVIEWER)

_VERDICT_RE = re.compile(r"VERDICT:\s*(APPROVE|REVISE)", re.IGNORECASE)
_REASON_RE = re.compile(r"REASON:\s*(.+)", re.IGNORECASE | re.DOTALL)
_FINAL_RE = re.compile(r"FINAL:\s*(APPROVE|REVISE)", re.IGNORECASE)
_SUMMARY_RE = re.compile(r"SUMMARY:\s*(.+)", re.IGNORECASE | re.DOTALL)

ReviewFn = Callable[..., str]
DecideFn = Callable[..., str]


def _parse_reviewer_output(text: str) -> tuple[str, str]:
    """``VERDICT:``/``REASON:`` 을 관대하게 파싱한다. 형식을 어겨도 예외를 던지지
    않고 안전한 폴백(REVISE, 원문 앞부분)으로 처리한다 — parse_alternatives와
    같은 원칙."""
    v_match = _VERDICT_RE.search(text)
    verdict = v_match.group(1).lower() if v_match else "revise"
    r_match = _REASON_RE.search(text)
    reason = r_match.group(1).strip().splitlines()[0].strip() if r_match else text.strip()[:200]
    return verdict, reason


def _parse_chief_editor_output(text: str) -> tuple[str, str]:
    f_match = _FINAL_RE.search(text)
    verdict = f_match.group(1).lower() if f_match else "revise"
    s_match = _SUMMARY_RE.search(text)
    summary = s_match.group(1).strip() if s_match else text.strip()
    return verdict, summary


def build_reviewer(
    llm: LLM,
    monitor: PerformanceMonitor,
    *,
    role_name: str,
    focus_label: str,
    focus_description: str,
    allowed_action_keywords: list[str],
    forbidden_action_keywords: list[str],
) -> ReviewFn:
    @agent_eval(
        monitor,
        task_type="document_review",
        question_arg="chapter_title",
        agent_role=AgentRoleConfig(
            role_name=role_name,
            allowed_action_keywords=allowed_action_keywords,
            forbidden_action_keywords=forbidden_action_keywords,
            role_violation_penalty=0.3,
        ),
    )
    def review(
        chapter_title: str, chapter_md: str, ground_truth: str = ""
    ) -> tuple[str, EvalMetadata]:
        prompt = REVIEWER_PROMPT.format(
            focus_label=focus_label,
            chapter_title=chapter_title,
            focus_description=focus_description,
            chapter_md=chapter_md[:6000],
        )
        text = llm.generate(prompt, system=REVIEWER_SYSTEM_PROMPT, max_tokens=300)
        return text, EvalMetadata(extra={"phase": "review", "role": role_name})

    return review


def build_chief_editor(llm: LLM, monitor: PerformanceMonitor) -> DecideFn:
    @agent_eval(
        monitor,
        task_type="document_review",
        question_arg="chapter_title",
        conflict_resolution=ConflictResolutionConfig(),
    )
    def decide(
        chapter_title: str, reviews_text: str, consensus: dict, ground_truth: str = ""
    ) -> tuple[str, EvalMetadata]:
        prompt = CHIEF_EDITOR_PROMPT.format(chapter_title=chapter_title, reviews_text=reviews_text)
        text = llm.generate(prompt, system=CHIEF_EDITOR_SYSTEM_PROMPT, max_tokens=500)
        return text, EvalMetadata(extra={"phase": "chief_editor", "consensus": consensus})

    return decide


@dataclass
class ReviewerVerdict:
    role_name: str
    verdict: str  # "approve" | "revise"
    reason: str
    raw_text: str


@dataclass
class ReviewPanelResult:
    reviewer_verdicts: list[ReviewerVerdict]
    consensus_score: float
    final_verdict: str  # "approve" | "revise"
    final_summary: str


def run_review_panel(
    chapter_title: str,
    chapter_md: str,
    llm: LLM,
    monitor: PerformanceMonitor,
    *,
    chapter_no: int = 0,
    reviewers: Optional[tuple] = None,
) -> ReviewPanelResult:
    """감독자-작업자 패턴으로 챕터를 다관점 검토한다.

    각 리뷰어(worker)를 독립 호출 → 감독자(chief editor)에게 위임/응답
    인터랙션을 기록 → 리뷰어 판정 간 합의도를 구조화 신호로 계산 → 감독자가
    최종 결론을 낸다. Gate F 4개 지표(coordination/consensus/agent_role/
    conflict_resolution)가 이 한 번의 호출로 전부 실제 값을 얻는다.
    """
    reviewer_configs = reviewers or DEFAULT_REVIEWERS
    task_id = f"review_ch{chapter_no:02d}"

    verdicts: list[ReviewerVerdict] = []
    for cfg in reviewer_configs:
        monitor.agent_coordination_tracker.track_interaction(
            task_id=task_id,
            from_agent="chief_editor",
            to_agent=cfg["role_name"],
            interaction_type="delegation",
            success=True,
        )
        review = build_reviewer(llm, monitor, **cfg)
        raw_text = review(chapter_title=chapter_title, chapter_md=chapter_md, ground_truth=chapter_title)
        verdict, reason = _parse_reviewer_output(raw_text)
        verdicts.append(
            ReviewerVerdict(role_name=cfg["role_name"], verdict=verdict, reason=reason, raw_text=raw_text)
        )
        monitor.agent_coordination_tracker.track_interaction(
            task_id=task_id,
            from_agent=cfg["role_name"],
            to_agent="chief_editor",
            interaction_type="communication",
            success=True,
        )

    # SPEC-009 REQ-1 구조화 신호 — VERDICT를 그대로 intent로 넘겨 자유 텍스트
    # 어휘 유사도가 아니라 판정 자체의 일치 여부로 합의를 계산한다.
    consensus_result = eval_consensus(
        responses=[v.raw_text for v in verdicts],
        agent_names=[v.role_name for v in verdicts],
        config=ConsensusConfig(),
        agent_interactions=[{"agent": v.role_name, "intent": v.verdict} for v in verdicts],
    )

    reviews_text = "\n\n".join(f"[{v.role_name}] {v.verdict.upper()}: {v.reason}" for v in verdicts)

    decide = build_chief_editor(llm, monitor)
    final_raw = decide(
        chapter_title=chapter_title,
        reviews_text=reviews_text,
        consensus=consensus_result,
        ground_truth=chapter_title,
    )
    final_verdict, final_summary = _parse_chief_editor_output(final_raw)

    return ReviewPanelResult(
        reviewer_verdicts=verdicts,
        consensus_score=consensus_result["consensus_score"],
        final_verdict=final_verdict,
        final_summary=final_summary,
    )
