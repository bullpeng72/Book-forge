"""agents/chat_agent.py — build_answer_question() 오프라인 테스트 (FakeLLM)."""
from pathlib import Path

from book_forge.agents.chat_agent import build_answer_question
from book_forge.eval.monitor import build_book_monitor


class FakeLLM:
    model = "fake"

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        assert "Gate C란 무엇인가요" in prompt
        assert "발췌" in prompt
        return "Gate C는 신뢰성을 다루는 게이트입니다."


def test_answer_question_returns_llm_response(tmp_path: Path) -> None:
    monitor = build_book_monitor(output_dir=str(tmp_path / "eval_results"))
    answer_question = build_answer_question(FakeLLM(), monitor)

    result = answer_question(
        question="Gate C란 무엇인가요?",
        sources="Gate C는 Reliability(신뢰성)를 다루는 Harness Gate이다.",
        ground_truth="Gate C란 무엇인가요?",
    )

    assert "신뢰성" in result
