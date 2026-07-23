"""`book-forge plan` 테스트. --revise 없는 미리보기 경로만 오프라인으로 검증한다
(--revise 경로는 new_cmd.py와 동일하게 실제 LLM 호출이 필요해 수동/실제 Ollama로 검증)."""
from pathlib import Path

from click.testing import CliRunner

import book_forge.cli.project_utils as project_utils
from book_forge.cli.commands.plan_cmd import _strip_title_h1
from book_forge.cli.main import cli


def test_strip_title_h1_removes_prefix() -> None:
    text = "# 책 제목\n\n## 목적\n\n본문..."
    assert _strip_title_h1(text, "책 제목") == "## 목적\n\n본문..."


def test_strip_title_h1_noop_when_prefix_missing() -> None:
    text = "## 목적\n\n본문..."
    assert _strip_title_h1(text, "책 제목") == text


def _make_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "projects" / "sample-slug"
    project_dir.mkdir(parents=True)
    (project_dir / "00_기획안.md").write_text("# 샘플 책\n\n## 목적\n\n요약.", encoding="utf-8")
    (project_dir / "01_목차.md").write_text(
        "## Part 1. 기초\n- Chapter 1. 서론\n\n```toc\n1|기초|1|서론\n```\n", encoding="utf-8"
    )
    return project_dir


def test_plan_preview_without_revise_flag(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    _make_project(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ["plan", "sample-slug"])

    assert result.exit_code == 0
    assert "샘플 책" in result.output
    assert "Chapter 1. 서론" in result.output
    assert "--revise" in result.output


def test_plan_missing_project_raises(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ["plan", "nonexistent"])

    assert result.exit_code != 0
    assert "프로젝트를 찾을 수 없습니다" in result.output


def test_plan_missing_proposal_raises(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    (tmp_path / "projects" / "empty-slug").mkdir(parents=True)

    runner = CliRunner()
    result = runner.invoke(cli, ["plan", "empty-slug"])

    assert result.exit_code != 0
    assert "기획안/목차가 없습니다" in result.output
