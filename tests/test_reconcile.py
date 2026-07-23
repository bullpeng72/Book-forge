"""agents/scaffold.py — reconcile_chapters() 테스트 (plan --revise가 쓰는 재조정 로직).

LLM 호출 없이 순수 파일 시스템 로직만 검증한다.
"""
from pathlib import Path

from book_forge.agents.scaffold import reconcile_chapters
from book_forge.models import ChapterSpec
from book_forge.publish.toc_loader import ResolvedChapter


def _make_authored_chapter(project_dir: Path, spec: ChapterSpec, content: str) -> ResolvedChapter:
    part_dir = project_dir / spec.part_dir_name
    part_dir.mkdir(parents=True, exist_ok=True)
    (part_dir / "images").mkdir(exist_ok=True)
    path = part_dir / spec.chapter_file_name
    path.write_text(content, encoding="utf-8")
    return ResolvedChapter(spec=spec, path=path)


def test_reconcile_creates_new_chapter(tmp_path: Path) -> None:
    old_spec = ChapterSpec(part_no=1, part_title="기초", chapter_no=1, chapter_title="서론")
    old_rc = _make_authored_chapter(tmp_path, old_spec, "# Chapter 01: 서론\n\n집필한 내용")

    new_specs = [old_spec, ChapterSpec(part_no=1, part_title="기초", chapter_no=2, chapter_title="새 챕터")]

    result = reconcile_chapters(tmp_path, [old_rc], new_specs)

    assert len(result.created) == 1
    assert "새_챕터" in result.created[0] or "새 챕터" in result.created[0]
    # 기존 챕터 1은 그대로 유지(재생성되지 않음)
    assert "집필한 내용" in old_rc.path.read_text(encoding="utf-8")


def test_reconcile_renames_when_title_changes_preserving_content(tmp_path: Path) -> None:
    old_spec = ChapterSpec(part_no=1, part_title="기초", chapter_no=1, chapter_title="옛 제목")
    old_rc = _make_authored_chapter(tmp_path, old_spec, "# Chapter 01: 옛 제목\n\n소중한 본문")
    (old_rc.path.parent / "images" / "pic.png").write_bytes(b"fake-png-bytes")

    new_spec = ChapterSpec(part_no=1, part_title="기초", chapter_no=1, chapter_title="새 제목")
    result = reconcile_chapters(tmp_path, [old_rc], [new_spec])

    assert len(result.renamed) == 1
    old_path_str, new_path_str = result.renamed[0]
    assert old_path_str == str(old_rc.path)
    new_path = Path(new_path_str)
    assert new_path.exists()
    assert "소중한 본문" in new_path.read_text(encoding="utf-8")
    assert not old_rc.path.exists()  # 이동했으므로 옛 경로엔 더 이상 없음
    assert (new_path.parent / "images" / "pic.png").exists()  # 이미지도 함께 이동


def test_reconcile_does_not_overwrite_existing_target(tmp_path: Path) -> None:
    spec = ChapterSpec(part_no=1, part_title="기초", chapter_no=1, chapter_title="서론")
    rc = _make_authored_chapter(tmp_path, spec, "# Chapter 01: 서론\n\n이미 있는 내용")

    result = reconcile_chapters(tmp_path, [rc], [spec])

    assert result.created == []
    assert result.renamed == []
    assert "이미 있는 내용" in rc.path.read_text(encoding="utf-8")


def test_reconcile_reports_orphaned_without_deleting(tmp_path: Path) -> None:
    spec1 = ChapterSpec(part_no=1, part_title="기초", chapter_no=1, chapter_title="서론")
    spec2 = ChapterSpec(part_no=1, part_title="기초", chapter_no=2, chapter_title="삭제될 챕터")
    rc1 = _make_authored_chapter(tmp_path, spec1, "# Chapter 01: 서론\n\n본문")
    rc2 = _make_authored_chapter(tmp_path, spec2, "# Chapter 02: 삭제될 챕터\n\n귀중한 본문")

    # 새 목차에는 chapter 1만 남음(2는 빠짐)
    result = reconcile_chapters(tmp_path, [rc1, rc2], [spec1])

    assert result.orphaned == [str(rc2.path)]
    assert rc2.path.exists()  # 자동 삭제하지 않음
    assert "귀중한 본문" in rc2.path.read_text(encoding="utf-8")
