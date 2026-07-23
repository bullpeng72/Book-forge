"""agents/diagram_generator.py — build_generate_diagram() 오프라인 테스트 (FakeLLM)."""
from pathlib import Path

from book_forge.agents.diagram_generator import build_generate_diagram
from book_forge.eval.monitor import build_book_monitor


class FakeLLM:
    model = "fake"

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        assert "파이프라인 흐름" in prompt
        assert "소스 발췌" in prompt
        return (
            "# Chapter 01: 파이프라인 흐름\n\n"
            "```mermaid\ngraph TD\n    A[요청] --> B[처리] --> C[응답]\n```\n\n"
            "각 단계는 소스에 근거합니다."
        )


def test_generate_diagram_returns_mermaid_block(tmp_path: Path) -> None:
    monitor = build_book_monitor(output_dir=str(tmp_path / "eval_results"))
    generate = build_generate_diagram(FakeLLM(), monitor)

    result = generate(
        chapter_title="파이프라인 흐름",
        chapter_no=1,
        sources="소스 발췌문: 요청은 처리를 거쳐 응답이 된다.",
        ground_truth="파이프라인 흐름",
    )

    assert "```mermaid" in result
    assert "graph TD" in result
