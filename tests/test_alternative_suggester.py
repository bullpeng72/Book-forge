"""agents/alternative_suggester.py — parse_alternatives()/build_suggest_alternatives() 테스트."""
from pathlib import Path

from book_forge.agents.alternative_suggester import build_suggest_alternatives, parse_alternatives
from book_forge.eval.monitor import build_book_monitor

WELL_FORMED = """ALT: 이론 중심으로 범위 축소 | 실전 사례 없이도 개념 설명은 소스로 충분함
ALT: 소스 추가 후 재시도 | 관련 PDF를 더 모으면 커버리지가 개선될 가능성
"""


def test_parse_alternatives_well_formed() -> None:
    alts = parse_alternatives(WELL_FORMED)
    assert len(alts) == 2
    assert alts[0] == ("이론 중심으로 범위 축소", "실전 사례 없이도 개념 설명은 소스로 충분함")


def test_parse_alternatives_ignores_non_alt_lines() -> None:
    text = "설명 문장입니다.\nALT: 대안 1 | 이유1\n다른 잡담"
    alts = parse_alternatives(text)
    assert len(alts) == 1


def test_parse_alternatives_without_pipe_uses_empty_reason() -> None:
    alts = parse_alternatives("ALT: 이유 없는 대안")
    assert alts == [("이유 없는 대안", "")]


def test_parse_alternatives_no_matches_returns_empty_list() -> None:
    assert parse_alternatives("형식을 전혀 안 지킨 텍스트") == []


class FakeLLM:
    model = "fake"

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        assert "커버리지" in prompt or "소스" in prompt
        return WELL_FORMED


def test_build_suggest_alternatives_returns_llm_response(tmp_path: Path) -> None:
    monitor = build_book_monitor(output_dir=str(tmp_path / "eval_results"))
    suggest = build_suggest_alternatives(FakeLLM(), monitor)

    result = suggest(
        chapter_title="테스트 챕터",
        reason="평균 소스 유사도 0.2로 낮음",
        ground_truth="테스트 챕터",
    )

    assert "ALT:" in result
    assert parse_alternatives(result)
