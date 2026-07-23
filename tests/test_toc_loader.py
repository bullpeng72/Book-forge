"""toc_loader.py — load_toc() 테스트 (LLM 호출 없이 fixture 프로젝트 사용)."""
from pathlib import Path

import pytest

from book_forge.exceptions import BookForgeError
from book_forge.publish.toc_loader import load_toc


def test_load_toc_resolves_existing_chapter_paths(sample_project: Path) -> None:
    chapters = load_toc(sample_project)
    assert len(chapters) == 2
    assert chapters[0].spec.chapter_title == "서론"
    assert chapters[0].exists
    assert chapters[0].path == sample_project / "Part_1_기초" / "Chapter_01_서론.md"


def test_load_toc_missing_toc_file_raises(tmp_path: Path) -> None:
    with pytest.raises(BookForgeError, match="목차 파일이 없습니다"):
        load_toc(tmp_path)


def test_load_toc_marks_missing_chapter_file(sample_project: Path) -> None:
    (sample_project / "Part_1_기초" / "Chapter_02_환경_설정.md").unlink()
    chapters = load_toc(sample_project)
    assert chapters[0].exists
    assert not chapters[1].exists
