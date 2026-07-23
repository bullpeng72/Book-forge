"""scaffold.py — write_chapter_stub / scaffold_project 테스트 (LLM 호출 없음)."""
from pathlib import Path

import pytest

from book_forge.agents.scaffold import scaffold_project, write_chapter_stub
from book_forge.exceptions import BookForgeError
from book_forge.models import ChapterSpec


def test_write_chapter_stub_creates_file_and_images_dir(tmp_path: Path) -> None:
    result = write_chapter_stub(str(tmp_path), "Part_1_기초", "Chapter_01_서론.md", 1, "서론")
    chapter_path = tmp_path / "Part_1_기초" / "Chapter_01_서론.md"
    assert chapter_path.exists()
    assert (tmp_path / "Part_1_기초" / "images").is_dir()
    assert "created" in result
    assert "서론" in chapter_path.read_text(encoding="utf-8")


def test_write_chapter_stub_skips_existing_file(tmp_path: Path) -> None:
    write_chapter_stub(str(tmp_path), "Part_1_기초", "Chapter_01_서론.md", 1, "서론")
    result = write_chapter_stub(str(tmp_path), "Part_1_기초", "Chapter_01_서론.md", 1, "서론")
    assert "skipped" in result


def test_write_chapter_stub_blocks_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(BookForgeError, match="차단"):
        write_chapter_stub(str(tmp_path), "../../etc", "evil.md", 1, "제목")


def test_scaffold_project_creates_all_chapters(tmp_path: Path) -> None:
    chapters = [
        ChapterSpec(part_no=1, part_title="기초", chapter_no=1, chapter_title="서론"),
        ChapterSpec(part_no=1, part_title="기초", chapter_no=2, chapter_title="설치"),
        ChapterSpec(part_no=2, part_title="심화", chapter_no=3, chapter_title="아키텍처"),
    ]
    results = scaffold_project(tmp_path, chapters)
    assert len(results) == 3
    assert (tmp_path / "Part_1_기초" / "Chapter_01_서론.md").exists()
    assert (tmp_path / "Part_1_기초" / "Chapter_02_설치.md").exists()
    assert (tmp_path / "Part_2_심화" / "Chapter_03_아키텍처.md").exists()
