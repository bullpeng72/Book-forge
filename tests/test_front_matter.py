"""publish/front_matter.py — FrontMatter load/save 테스트 (일반 능력 AI)."""
from pathlib import Path

from book_forge.publish.front_matter import (
    FrontMatter,
    front_matter_path,
    load_front_matter,
    save_front_matter,
)


def test_front_matter_is_empty_when_all_fields_blank() -> None:
    assert FrontMatter().is_empty is True


def test_front_matter_not_empty_with_any_field_set() -> None:
    assert FrontMatter(author="홍길동").is_empty is False
    assert FrontMatter(license_notice="CC BY").is_empty is False
    assert FrontMatter(edition="1판").is_empty is False


def test_load_front_matter_returns_empty_when_file_missing(tmp_path: Path) -> None:
    assert load_front_matter(tmp_path) == FrontMatter()


def test_save_and_load_front_matter_roundtrip(tmp_path: Path) -> None:
    fm = FrontMatter(author="홍길동", license_notice="CC BY-NC 4.0", edition="2판")
    save_front_matter(tmp_path, fm)

    assert front_matter_path(tmp_path).is_file()
    assert load_front_matter(tmp_path) == fm


def test_save_front_matter_noop_when_empty(tmp_path: Path) -> None:
    save_front_matter(tmp_path, FrontMatter())
    assert not front_matter_path(tmp_path).exists()


def test_load_front_matter_handles_corrupt_json(tmp_path: Path) -> None:
    front_matter_path(tmp_path).write_text("{ not valid json", encoding="utf-8")
    assert load_front_matter(tmp_path) == FrontMatter()
