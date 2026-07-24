"""review_loop.py — run_review_loop 순수 로직 테스트 (fake revise_fn, LLM/모니터 불필요)."""
from book_forge.agents.review_loop import MAX_REVIEW_ROUNDS, run_review_loop


def test_run_review_loop_approves_immediately_on_empty_feedback() -> None:
    rendered = []
    result = run_review_loop(
        kind="plan",
        initial_md="draft-0",
        revise_fn=lambda **kw: "should not be called",
        render=rendered.append,
        ask_feedback=lambda: "",
    )
    assert result == "draft-0"
    assert rendered == ["draft-0"]


def test_run_review_loop_revises_until_approved() -> None:
    feedback_queue = ["더 짧게", "승인"]
    calls = []

    def fake_revise(**kwargs):
        calls.append(kwargs)
        return f"draft-{kwargs['round_no']}"

    result = run_review_loop(
        kind="plan",
        initial_md="draft-0",
        revise_fn=fake_revise,
        render=lambda md: None,
        ask_feedback=lambda: feedback_queue.pop(0),
    )
    assert result == "draft-1"
    assert len(calls) == 1
    assert calls[0]["feedback"] == "더 짧게"
    assert calls[0]["round_no"] == 1
    assert calls[0]["kind"] == "plan"


def test_run_review_loop_calls_on_feedback_for_each_actual_revision_round() -> None:
    feedback_queue = ["더 짧게", "표현만 다듬어줘", "승인"]
    collected: list[str] = []

    result = run_review_loop(
        kind="toc",
        initial_md="draft-0",
        revise_fn=lambda **kw: f"draft-{kw['round_no']}",
        render=lambda md: None,
        ask_feedback=lambda: feedback_queue.pop(0),
        on_feedback=collected.append,
    )
    assert result == "draft-2"
    assert collected == ["더 짧게", "표현만 다듬어줘"]


def test_run_review_loop_does_not_call_on_feedback_when_approved_immediately() -> None:
    collected: list[str] = []
    run_review_loop(
        kind="toc",
        initial_md="draft-0",
        revise_fn=lambda **kw: "should not be called",
        render=lambda md: None,
        ask_feedback=lambda: "",
        on_feedback=collected.append,
    )
    assert collected == []


def test_run_review_loop_caps_at_max_rounds() -> None:
    def fake_revise(**kwargs):
        return f"draft-{kwargs['round_no']}"

    result = run_review_loop(
        kind="toc",
        initial_md="draft-0",
        revise_fn=fake_revise,
        render=lambda md: None,
        ask_feedback=lambda: "계속 수정",
    )
    assert result == f"draft-{MAX_REVIEW_ROUNDS}"
