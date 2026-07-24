"""agents/toc_designer.py — build_design_toc() 오프라인 테스트 (FakeLLM).

일반 능력 S(SPEC.md 2부) — code_structure 파라미터가 실제로 프롬프트에
반영되는지, 미지정 시 기존 동작과 동일한지 확인한다.
"""
from pathlib import Path

from book_forge.agents.toc_designer import build_design_toc
from book_forge.eval.monitor import build_book_monitor

TOC_RESPONSE = """## Part 1. 기초
- Chapter 1. 서론

```toc
1|기초|1|서론
```
"""


class RecordingLLM:
    model = "fake"

    def __init__(self) -> None:
        self.last_prompt = ""

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        self.last_prompt = prompt
        return TOC_RESPONSE


def test_design_toc_without_code_structure_omits_structure_block(tmp_path: Path) -> None:
    monitor = build_book_monitor(output_dir=str(tmp_path / "eval_results"))
    llm = RecordingLLM()
    design_toc = build_design_toc(llm, monitor)

    design_toc(proposal_md="## 목적\n\n요약", ground_truth="요약")

    assert "실제 코드 구조" not in llm.last_prompt


def test_design_toc_with_code_structure_includes_it_in_prompt(tmp_path: Path) -> None:
    monitor = build_book_monitor(output_dir=str(tmp_path / "eval_results"))
    llm = RecordingLLM()
    design_toc = build_design_toc(llm, monitor)

    design_toc(
        proposal_md="## 목적\n\n요약",
        code_structure="## planner.py\n- 클래스 `PlannerAgent` — 기획안을 생성한다",
        ground_truth="요약",
    )

    assert "실제 코드 구조" in llm.last_prompt
    assert "PlannerAgent" in llm.last_prompt
    assert "지어내" in llm.last_prompt


def test_design_toc_returns_toc_markdown(tmp_path: Path) -> None:
    monitor = build_book_monitor(output_dir=str(tmp_path / "eval_results"))
    result = build_design_toc(RecordingLLM(), monitor)(
        proposal_md="## 목적\n\n요약", ground_truth="요약"
    )
    assert "```toc" in result
