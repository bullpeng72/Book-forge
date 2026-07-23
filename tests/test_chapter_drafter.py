"""chapter_drafter.py — build_draft_chapter() 오프라인 테스트 (FakeLLM, 실제 Ollama 없음)."""
from pathlib import Path

from book_forge.agents.chapter_drafter import build_draft_chapter
from book_forge.eval.monitor import build_book_monitor


class FakeLLM:
    model = "fake"

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        assert "테스트 챕터" in prompt
        assert "소스 발췌문" in prompt
        return "# Chapter 01: 테스트 챕터\n\n소스에 근거한 본문."


def test_draft_chapter_returns_llm_response(tmp_path: Path) -> None:
    monitor = build_book_monitor(output_dir=str(tmp_path / "eval_results"))
    draft_chapter = build_draft_chapter(FakeLLM(), monitor)

    result = draft_chapter(
        chapter_title="테스트 챕터",
        chapter_no=1,
        sources="소스 발췌문 1\n\n소스 발췌문 2",
        ground_truth="테스트 챕터",
    )

    assert "소스에 근거한 본문" in result
