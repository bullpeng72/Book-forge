"""agents/module_reference.py — build_generate_module_reference() 오프라인 테스트 (FakeLLM)."""
from pathlib import Path

from book_forge.agents.module_reference import build_generate_module_reference
from book_forge.eval.monitor import build_book_monitor


class FakeLLM:
    model = "fake"

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        assert "구조 요약" in prompt
        assert "빠짐없이" in prompt
        return (
            "# Chapter 01: agents 패키지 레퍼런스\n\n"
            "| 모듈 | 이름 | 설명 |\n|---|---|---|\n"
            "| planner.py | PlannerAgent | 기획안을 생성한다 |"
        )


def test_generate_module_reference_returns_markdown_table(tmp_path: Path) -> None:
    monitor = build_book_monitor(output_dir=str(tmp_path / "eval_results"))
    generate = build_generate_module_reference(FakeLLM(), monitor)

    result = generate(
        chapter_title="agents 패키지 레퍼런스",
        chapter_no=1,
        sources="## planner.py\n- 클래스 `PlannerAgent` — 기획안을 생성한다",
        ground_truth="agents 패키지 레퍼런스",
    )

    assert "| 모듈 | 이름 | 설명 |" in result
    assert "PlannerAgent" in result
