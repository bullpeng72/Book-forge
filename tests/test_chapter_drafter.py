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


class _PromptEchoLLM:
    """실제 텍스트 대신 프롬프트 본문을 그대로 반환 — 어떤 템플릿이 선택됐는지 검증용."""

    model = "fake"

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        return prompt


def test_draft_chapter_uses_exercise_prompt_for_exercise_content_type(tmp_path: Path) -> None:
    monitor = build_book_monitor(output_dir=str(tmp_path / "eval_results"))
    draft_chapter = build_draft_chapter(_PromptEchoLLM(), monitor)

    result = draft_chapter(
        chapter_title="테스트 챕터",
        chapter_no=1,
        sources="소스 발췌문",
        ground_truth="테스트 챕터",
        content_type="exercise",
    )

    assert "실습(exercise) 형태로 작성하세요" in result
    assert "```python" in result  # 프롬프트가 코드 블록 요구를 명시


def test_draft_chapter_falls_back_to_default_prompt_for_diagram_content_type(
    tmp_path: Path,
) -> None:
    # diagram은 DiagramGeneratorAgent(agents/diagram_generator.py)로 승격됐다 —
    # chapter_drafter는 diagram을 모르는 content_type으로 취급해 기본 서술형
    # 프롬프트로 폴백해야 한다(draft_cmd.py가 diagram을 이 함수로 아예 안 보내지만,
    # 혹시 직접 호출되더라도 예외 없이 안전하게 동작해야 함).
    monitor = build_book_monitor(output_dir=str(tmp_path / "eval_results"))
    draft_chapter = build_draft_chapter(_PromptEchoLLM(), monitor)

    result = draft_chapter(
        chapter_title="테스트 챕터",
        chapter_no=1,
        sources="소스 발췌문",
        ground_truth="테스트 챕터",
        content_type="diagram",
    )

    assert "다이어그램 중심으로 작성하세요" not in result
    assert "`## `로 소제목을 나누어" in result  # 기본 DRAFT_PROMPT로 폴백


def test_draft_chapter_uses_default_prompt_for_narrative_content_type(tmp_path: Path) -> None:
    monitor = build_book_monitor(output_dir=str(tmp_path / "eval_results"))
    draft_chapter = build_draft_chapter(_PromptEchoLLM(), monitor)

    result = draft_chapter(
        chapter_title="테스트 챕터",
        chapter_no=1,
        sources="소스 발췌문",
        ground_truth="테스트 챕터",
        content_type="narrative",
    )

    assert "실습(exercise)" not in result
    assert "다이어그램 중심으로" not in result
