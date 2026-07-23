"""`book-forge home` 테스트 — 실제 파일 탐색기를 열지 않도록 subprocess.run을 monkeypatch."""
from pathlib import Path

from click.testing import CliRunner

import book_forge.cli.commands.home_cmd as home_cmd
import book_forge.cli.project_utils as project_utils
from book_forge.cli.main import cli


def test_home_opens_data_dir_by_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(home_cmd, "get_data_dir", lambda: tmp_path / "BookForge")
    calls = []
    monkeypatch.setattr(home_cmd.subprocess, "run", lambda *a, **kw: calls.append(a))

    runner = CliRunner()
    result = runner.invoke(cli, ["home"])

    assert result.exit_code == 0
    assert (tmp_path / "BookForge").is_dir()
    assert len(calls) == 1


def test_home_opens_project_dir_when_slug_given(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(home_cmd, "get_data_dir", lambda: tmp_path)
    (tmp_path / "projects" / "my-slug").mkdir(parents=True)
    calls = []
    monkeypatch.setattr(home_cmd.subprocess, "run", lambda *a, **kw: calls.append(a))

    runner = CliRunner()
    result = runner.invoke(cli, ["home", "my-slug"])

    assert result.exit_code == 0
    assert len(calls) == 1


def test_home_unknown_slug_raises(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(home_cmd, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ["home", "nonexistent"])

    assert result.exit_code != 0
    assert "프로젝트를 찾을 수 없습니다" in result.output
