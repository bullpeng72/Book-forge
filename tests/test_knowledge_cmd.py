"""`book-forge knowledge status`/`reset` 테스트(Spec J)."""
from pathlib import Path

from click.testing import CliRunner

import book_forge.cli.project_utils as project_utils
from book_forge.cli.main import cli
from book_forge.knowledge.store import KnowledgeStore, default_store_path


def _make_project_with_store(tmp_path: Path) -> Path:
    project_dir = tmp_path / "projects" / "sample-slug"
    project_dir.mkdir(parents=True)
    store = KnowledgeStore(
        chunks=["# 파일: a.py\n내용1", "# 파일: a.py\n내용2", "# 파일: b.py\n내용3"],
        _vectors=[[0.0], [0.0], [0.0]],
    )
    store.save(default_store_path(project_dir))
    return project_dir


def test_knowledge_status_shows_per_source_breakdown(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    _make_project_with_store(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ["knowledge", "status", "sample-slug"])

    assert result.exit_code == 0
    assert "총 3개 청크" in result.output
    assert "a.py: 2개 청크" in result.output
    assert "b.py: 1개 청크" in result.output


def test_knowledge_status_missing_store_reports_cleanly(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    (tmp_path / "projects" / "empty-slug").mkdir(parents=True)

    runner = CliRunner()
    result = runner.invoke(cli, ["knowledge", "status", "empty-slug"])

    assert result.exit_code == 0
    assert "지식창고가 아직 없습니다" in result.output


def test_knowledge_reset_with_yes_deletes_store(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    project_dir = _make_project_with_store(tmp_path)
    store_path = default_store_path(project_dir)
    assert store_path.is_file()

    runner = CliRunner()
    result = runner.invoke(cli, ["knowledge", "reset", "sample-slug", "--yes"])

    assert result.exit_code == 0
    assert not store_path.is_file()
    assert "삭제했습니다" in result.output


def test_knowledge_reset_without_yes_prompts_and_can_be_aborted(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    project_dir = _make_project_with_store(tmp_path)
    store_path = default_store_path(project_dir)

    runner = CliRunner()
    result = runner.invoke(cli, ["knowledge", "reset", "sample-slug"], input="n\n")

    assert store_path.is_file()  # 취소했으니 그대로 남아있어야 함
    assert result.exit_code != 0


def test_knowledge_reset_missing_store_reports_cleanly(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    (tmp_path / "projects" / "empty-slug").mkdir(parents=True)

    runner = CliRunner()
    result = runner.invoke(cli, ["knowledge", "reset", "empty-slug", "--yes"])

    assert result.exit_code == 0
    assert "이미 없습니다" in result.output
