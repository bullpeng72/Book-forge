"""models.py — slugify / parse_toc_manifest 테스트 (LLM 호출 없이 순수 로직만)."""
import pytest

from book_forge.exceptions import TocParseError
from book_forge.models import (
    ChapterSpec,
    append_toc_revision_entries,
    parse_toc_manifest,
    slugify,
)

VALID_TOC = """## Part 1. 기초
- Chapter 1. 서론
- Chapter 2. 환경 설정

## Part 2. 심화
- Chapter 3. 아키텍처

```toc
1|기초|1|서론
1|기초|2|환경 설정
2|심화|3|아키텍처
```
"""


def test_slugify_keeps_korean_and_strips_punctuation() -> None:
    assert slugify("AI 에이전트: 평가란?") == "AI_에이전트_평가란"


def test_slugify_collapses_repeated_separators() -> None:
    assert slugify("a   b---c") == "a_b_c"


def test_slugify_empty_falls_back_to_untitled() -> None:
    assert slugify("   ") == "untitled"


def test_chapter_spec_file_names() -> None:
    spec = ChapterSpec(part_no=1, part_title="기초", chapter_no=3, chapter_title="환경 설정")
    assert spec.part_dir_name == "Part_1_기초"
    assert spec.chapter_file_name == "Chapter_03_환경_설정.md"


def test_parse_toc_manifest_happy_path() -> None:
    chapters = parse_toc_manifest(VALID_TOC)
    assert len(chapters) == 3
    assert chapters[0] == ChapterSpec(part_no=1, part_title="기초", chapter_no=1, chapter_title="서론")
    assert chapters[2].part_title == "심화"


def test_parse_toc_manifest_missing_block_raises() -> None:
    with pytest.raises(TocParseError, match="toc 코드 블록"):
        parse_toc_manifest("## Part 1\n- Chapter 1")


def test_parse_toc_manifest_bad_field_count_raises() -> None:
    with pytest.raises(TocParseError, match="형식 오류"):
        parse_toc_manifest("```toc\n1|기초|1\n```")


def test_parse_toc_manifest_non_integer_raises() -> None:
    with pytest.raises(TocParseError, match="정수가 아닙니다"):
        parse_toc_manifest("```toc\nX|기초|1|서론\n```")


def test_parse_toc_manifest_empty_block_raises() -> None:
    with pytest.raises(TocParseError, match="비어 있습니다"):
        parse_toc_manifest("```toc\n\n```")


def test_parse_toc_manifest_defaults_to_narrative_content_type() -> None:
    chapters = parse_toc_manifest(VALID_TOC)
    assert all(c.content_type == "narrative" for c in chapters)


def test_parse_toc_manifest_reads_explicit_content_type() -> None:
    toc = "```toc\n1|기초|1|용어 사전|reference_table\n```"
    chapters = parse_toc_manifest(toc)
    assert chapters[0].content_type == "reference_table"


def test_parse_toc_manifest_unknown_content_type_falls_back_to_narrative() -> None:
    toc = "```toc\n1|기초|1|이상한 챕터|무언가_이상한_유형\n```"
    chapters = parse_toc_manifest(toc)
    assert chapters[0].content_type == "narrative"


def test_parse_toc_manifest_six_fields_raises() -> None:
    with pytest.raises(TocParseError, match="형식 오류"):
        parse_toc_manifest("```toc\n1|기초|1|제목|narrative|여분필드\n```")


def test_append_toc_revision_entries_creates_section_when_missing() -> None:
    result = append_toc_revision_entries(VALID_TOC, ["더 짧게"], today="2026-07-24")
    assert result.startswith("## 개정 이력\n- **2026-07-24**: 더 짧게\n\n## Part 1. 기초")


def test_append_toc_revision_entries_appends_to_existing_section() -> None:
    once = append_toc_revision_entries(VALID_TOC, ["더 짧게"], today="2026-07-14")
    twice = append_toc_revision_entries(once, ["표현만 다듬어줘"], today="2026-07-24")

    lines = twice.splitlines()
    header_idx = lines.index("## 개정 이력")
    assert lines[header_idx + 1] == "- **2026-07-14**: 더 짧게"
    assert lines[header_idx + 2] == "- **2026-07-24**: 표현만 다듬어줘"
    assert lines[header_idx + 3] == ""  # 개정 이력과 목차 본문 사이 구분용 빈 줄
    assert lines[header_idx + 4] == "## Part 1. 기초"
    # 기존 목차 매니페스트는 그대로 보존돼야 한다.
    assert "```toc" in twice
    assert twice.count("## Part 1. 기초") == 1


def test_append_toc_revision_entries_records_multiple_feedback_in_one_call() -> None:
    result = append_toc_revision_entries(
        VALID_TOC, ["첫 번째 요청", "두 번째 요청"], today="2026-07-24"
    )
    assert "- **2026-07-24**: 첫 번째 요청" in result
    assert "- **2026-07-24**: 두 번째 요청" in result


def test_append_toc_revision_entries_truncates_long_feedback() -> None:
    long_feedback = "가" * 300
    result = append_toc_revision_entries(VALID_TOC, [long_feedback], today="2026-07-24")
    entry_line = next(line for line in result.splitlines() if line.startswith("- **"))
    assert len(entry_line) < len(long_feedback)
    assert entry_line.endswith("…")


def test_append_toc_revision_entries_empty_list_is_effectively_noop_content() -> None:
    # 호출 자체는 허용하지만(호출자 책임은 plan_cmd.py가 짐), 항목이 없으면
    # 빈 헤더만 추가된다 — 실제 사용처(plan_cmd.py)는 feedback_entries가 비어
    # 있으면 아예 호출하지 않는다.
    result = append_toc_revision_entries(VALID_TOC, [], today="2026-07-24")
    assert result.startswith("## 개정 이력\n\n## Part 1. 기초")
