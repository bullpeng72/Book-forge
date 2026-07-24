"""term_consistency_checker.find_term_variants() 오프라인 단위 테스트."""
from book_forge.agents.term_consistency_checker import _fold_key, find_term_variants


def test_fold_key_ignores_case_and_punctuation() -> None:
    assert _fold_key("ToolCallAnalyzer") == _fold_key("tool_call_analyzer")
    assert _fold_key("ToolCallAnalyzer") == _fold_key("Tool-Call-Analyzer")


def test_find_term_variants_detects_inconsistent_spelling() -> None:
    chapters = [
        ("Chapter 1", "여기서는 `ToolCallAnalyzer`를 사용한다."),
        ("Chapter 2", "여기서는 `tool_call_analyzer`를 사용한다."),
    ]
    groups = find_term_variants(chapters)

    assert len(groups) == 1
    group = groups[0]
    assert set(group.variants) == {"ToolCallAnalyzer", "tool_call_analyzer"}
    assert group.variants["ToolCallAnalyzer"] == ["Chapter 1"]
    assert group.variants["tool_call_analyzer"] == ["Chapter 2"]


def test_find_term_variants_ignores_consistent_terms() -> None:
    chapters = [
        ("Chapter 1", "여기서는 `PerformanceMonitor`를 사용한다."),
        ("Chapter 2", "여기서도 `PerformanceMonitor`를 사용한다."),
    ]

    assert find_term_variants(chapters) == []


def test_find_term_variants_ignores_short_and_builtin_terms() -> None:
    chapters = [
        ("Chapter 1", "값이 `None`이거나 `x`일 수 있다."),
        ("Chapter 2", "값이 `none`이거나 `X`일 수 있다."),
    ]

    assert find_term_variants(chapters) == []


def test_find_term_variants_same_chapter_repeat_does_not_duplicate_label() -> None:
    chapters = [
        ("Chapter 1", "`ToolCallAnalyzer`를 두 번 언급한다: `ToolCallAnalyzer`."),
        ("Chapter 2", "`tool_call_analyzer`."),
    ]
    groups = find_term_variants(chapters)

    assert groups[0].variants["ToolCallAnalyzer"] == ["Chapter 1"]
