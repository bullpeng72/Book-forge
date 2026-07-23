"""agents/reference_table.py — build_generate_reference_table() 오프라인 테스트 (FakeLLM)."""
from pathlib import Path

from book_forge.agents.reference_table import build_generate_reference_table
from book_forge.eval.monitor import build_book_monitor


class FakeLLM:
    model = "fake"

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        assert "용어 사전" in prompt
        assert "소스 발췌" in prompt
        return "# Chapter 01: 용어 사전\n\n| 용어 | 정의 |\n|---|---|\n| Gate | 배포 판정 기준 |"


def test_generate_reference_table_returns_markdown_table(tmp_path: Path) -> None:
    monitor = build_book_monitor(output_dir=str(tmp_path / "eval_results"))
    generate = build_generate_reference_table(FakeLLM(), monitor)

    result = generate(
        chapter_title="용어 사전",
        chapter_no=1,
        sources="소스 발췌문: Gate는 배포 판정 기준이다.",
        ground_truth="용어 사전",
    )

    assert "| 용어 | 정의 |" in result
    assert "Gate" in result
