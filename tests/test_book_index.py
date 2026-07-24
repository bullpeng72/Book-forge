"""book_index.build_index_entries() 오프라인 단위 테스트."""
from pathlib import Path

from book_forge.models import ChapterSpec
from book_forge.publish.book_index import build_index_entries
from book_forge.publish.toc_loader import ResolvedChapter


def _make_chapter(tmp_path: Path, chapter_no: int, title: str, body: str) -> ResolvedChapter:
    spec = ChapterSpec(part_no=1, part_title="기초", chapter_no=chapter_no, chapter_title=title)
    path = tmp_path / f"Chapter_{chapter_no:02d}.md"
    path.write_text(body, encoding="utf-8")
    return ResolvedChapter(spec=spec, path=path)


def test_build_index_entries_groups_by_term_alphabetically(tmp_path: Path) -> None:
    ch1 = _make_chapter(tmp_path, 1, "서론", "`ZebraTracker`와 `AlphaTracker`를 함께 쓴다.")
    ch2 = _make_chapter(tmp_path, 2, "심화", "`AlphaTracker`를 다시 언급한다.")

    entries = build_index_entries([ch1, ch2])

    assert [e.term for e in entries] == ["AlphaTracker", "ZebraTracker"]
    assert entries[0].chapters == [ch1, ch2]
    assert entries[1].chapters == [ch1]


def test_build_index_entries_skips_missing_chapter_files(tmp_path: Path) -> None:
    spec = ChapterSpec(part_no=1, part_title="기초", chapter_no=1, chapter_title="서론")
    missing = ResolvedChapter(spec=spec, path=tmp_path / "없음.md")

    assert build_index_entries([missing]) == []


def test_build_index_entries_empty_when_no_backtick_terms(tmp_path: Path) -> None:
    ch1 = _make_chapter(tmp_path, 1, "서론", "그냥 평범한 문장입니다.")

    assert build_index_entries([ch1]) == []
