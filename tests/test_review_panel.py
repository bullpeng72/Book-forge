"""agents/review_panel.py — run_review_panel() 오프라인 테스트 (FakeLLM).

이 모듈이 처음으로 Book-forge에 진짜 감독자-작업자(supervisor-worker) 패턴을
도입하므로, Gate F(Multi-Agent Coordination)의 4개 지표(coordination/consensus/
agent_role/conflict_resolution)가 실제로 N/A가 아닌 값을 얻는지까지 확인한다.
"""
from pathlib import Path

from book_forge.agents.review_panel import (
    ReviewPanelResult,
    _parse_chief_editor_output,
    _parse_reviewer_output,
    run_review_panel,
)
from book_forge.eval.monitor import build_book_monitor


class _AgreeingLLM:
    """두 리뷰어가 모두 승인 — 합의(consensus_score=1.0) 케이스."""

    model = "fake"

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        if "가독성(구조/설명)" in prompt:
            return "VERDICT: APPROVE\nREASON: 설명이 명확하고 구조가 이해하기 쉽습니다."
        if "정확성(사실/근거)" in prompt:
            return "VERDICT: APPROVE\nREASON: 소스에 근거해 정확합니다."
        if "FINAL" in prompt:
            return "FINAL: APPROVE\nSUMMARY: 두 검토자 모두 승인해 합의된 결론을 그대로 반영합니다."
        raise AssertionError(f"unexpected prompt: {prompt[:100]}")


class _DisagreeingLLM:
    """정확성 검토자는 승인, 가독성 검토자는 수정 요청 — 불일치 케이스."""

    model = "fake"

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        if "가독성(구조/설명)" in prompt:
            return "VERDICT: REVISE\nREASON: 구조가 불명확합니다."
        if "정확성(사실/근거)" in prompt:
            return "VERDICT: APPROVE\nREASON: 소스에 근거해 정확합니다."
        if "FINAL" in prompt:
            return (
                "FINAL: REVISE\nSUMMARY: 정확성 검토자는 승인했지만 가독성 검토자가 "
                "구조 문제를 지적해 불일치가 있었습니다. 이를 해결하기 위해 REVISE로 "
                "최종 결정합니다."
            )
        raise AssertionError(f"unexpected prompt: {prompt[:100]}")


class _RoleViolatingLLM:
    """가독성 검토자가 담당 관점을 벗어나 정확성 어휘("근거")를 언급 — 역할 위반."""

    model = "fake"

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        if "가독성(구조/설명)" in prompt:
            return "VERDICT: REVISE\nREASON: 이 문장은 근거가 부족합니다."
        if "정확성(사실/근거)" in prompt:
            return "VERDICT: APPROVE\nREASON: 소스에 근거해 정확합니다."
        if "FINAL" in prompt:
            return "FINAL: REVISE\nSUMMARY: 불일치가 있어 해결을 위해 REVISE로 결정합니다."
        raise AssertionError(f"unexpected prompt: {prompt[:100]}")


def _run(llm, tmp_path: Path) -> tuple[ReviewPanelResult, dict]:
    monitor = build_book_monitor(output_dir=str(tmp_path / "eval_results"))
    result = run_review_panel(
        chapter_title="테스트 챕터", chapter_md="# 테스트 챕터\n\n본문", llm=llm, monitor=monitor,
        chapter_no=1,
    )
    report = monitor.generate_report()
    groups = (
        report.extra_metrics["harness_groups"]
        if hasattr(report, "extra_metrics")
        else report["extra_metrics"]["harness_groups"]
    )
    return result, groups["F"]["details"]


# ── 파서 단위 테스트 ────────────────────────────────────────────────────────


def test_parse_reviewer_output_parses_verdict_and_reason() -> None:
    verdict, reason = _parse_reviewer_output("VERDICT: APPROVE\nREASON: 근거가 충분합니다.")
    assert verdict == "approve"
    assert reason == "근거가 충분합니다."


def test_parse_reviewer_output_falls_back_safely_on_malformed_text() -> None:
    verdict, reason = _parse_reviewer_output("형식을 안 지킨 응답입니다.")
    assert verdict == "revise"  # 불명확하면 안전하게 수정 필요로 폴백
    assert reason


def test_parse_chief_editor_output_parses_final_and_summary() -> None:
    verdict, summary = _parse_chief_editor_output("FINAL: REVISE\nSUMMARY: 이유입니다.")
    assert verdict == "revise"
    assert summary == "이유입니다."


# ── run_review_panel() 통합 테스트 ──────────────────────────────────────────


def test_review_panel_unanimous_approval_yields_full_consensus(tmp_path: Path) -> None:
    result, details = _run(_AgreeingLLM(), tmp_path)

    assert [v.verdict for v in result.reviewer_verdicts] == ["approve", "approve"]
    assert result.consensus_score == 1.0
    assert result.final_verdict == "approve"

    assert details["avg_consensus"] == 1.0
    assert details["coordination_score"] is not None
    assert details["avg_role_compliance"] == 1.0
    assert details["avg_conflict_resolution"] == 1.0


def test_review_panel_disagreement_yields_zero_consensus(tmp_path: Path) -> None:
    result, details = _run(_DisagreeingLLM(), tmp_path)

    verdicts = {v.role_name: v.verdict for v in result.reviewer_verdicts}
    assert verdicts["정확성 검토자"] == "approve"
    assert verdicts["가독성 검토자"] == "revise"
    assert result.consensus_score == 0.0
    assert result.final_verdict == "revise"

    assert details["avg_consensus"] == 0.0
    # 감독자가 불일치를 명시적으로 언급하고 해결했으므로 conflict_resolution은 여전히 만점.
    assert details["avg_conflict_resolution"] == 1.0


def test_review_panel_role_violation_lowers_role_compliance(tmp_path: Path) -> None:
    result, details = _run(_RoleViolatingLLM(), tmp_path)

    assert result.reviewer_verdicts[1].role_name == "가독성 검토자"
    # 가독성 검토자가 forbidden 단어("근거")를 쓰고 allowed 단어를 하나도 안 써서
    # role_compliance_score가 1.0 미만으로 떨어져야 한다(정확성 검토자는 위반 없음).
    assert details["avg_role_compliance"] < 1.0


def test_review_panel_records_coordination_interactions(tmp_path: Path) -> None:
    monitor = build_book_monitor(output_dir=str(tmp_path / "eval_results"))
    run_review_panel(
        chapter_title="테스트 챕터", chapter_md="# 테스트 챕터\n\n본문", llm=_AgreeingLLM(),
        monitor=monitor, chapter_no=1,
    )
    interactions = monitor.agent_coordination_tracker.interactions
    # 리뷰어 2명 × (위임 1회 + 응답 1회) = 4건.
    assert len(interactions) == 4
    assert {i["interaction_type"] for i in interactions} == {"delegation", "communication"}
