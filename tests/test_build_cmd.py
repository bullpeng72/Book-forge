"""`book-forge build html|pdf --with-index` 플래그가 실제로 빌더까지 전달되는지
스파이 패턴으로 확인한다(빌더 자체 동작은 test_html_builder.py/test_pdf_builder.py가
이미 검증 — 여기는 CLI 배선만 확인).
"""
from pathlib import Path

from click.testing import CliRunner

import book_forge.cli.commands.build_cmd as build_cmd_module
import book_forge.cli.project_utils as project_utils
from book_forge.cli.main import cli


def _make_project(tmp_path: Path) -> None:
    project_dir = tmp_path / "projects" / "sample-slug"
    part_dir = project_dir / "Part_1_기초"
    part_dir.mkdir(parents=True)
    (project_dir / "01_목차.md").write_text(
        "## Part 1. 기초\n- Chapter 1. 서론\n\n```toc\n1|기초|1|서론\n```\n", encoding="utf-8"
    )
    (part_dir / "Chapter_01_서론.md").write_text("# Chapter 01: 서론\n\n본문.", encoding="utf-8")


def test_build_html_passes_with_index_flag(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    _make_project(tmp_path)
    captured = {}

    def fake_build_html(config, **kwargs):
        captured.update(kwargs)
        out = tmp_path / "out.html"
        out.write_text("<html></html>", encoding="utf-8")
        return out

    monkeypatch.setattr(build_cmd_module, "_build_html", fake_build_html)

    runner = CliRunner()
    result = runner.invoke(cli, ["build", "html", "sample-slug", "--with-index"])

    assert result.exit_code == 0
    assert captured == {"with_index": True}


def test_build_html_default_with_index_false(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    _make_project(tmp_path)
    captured = {}

    def fake_build_html(config, **kwargs):
        captured.update(kwargs)
        out = tmp_path / "out.html"
        out.write_text("<html></html>", encoding="utf-8")
        return out

    monkeypatch.setattr(build_cmd_module, "_build_html", fake_build_html)

    runner = CliRunner()
    result = runner.invoke(cli, ["build", "html", "sample-slug"])

    assert result.exit_code == 0
    assert captured == {"with_index": False}


def test_build_pdf_passes_with_index_flag(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    _make_project(tmp_path)
    captured = {}

    def fake_build_pdf(config, *, chapter_no=None, with_index=False):
        captured["chapter_no"] = chapter_no
        captured["with_index"] = with_index
        return []

    monkeypatch.setattr(build_cmd_module, "_build_pdf", fake_build_pdf)

    runner = CliRunner()
    result = runner.invoke(cli, ["build", "pdf", "sample-slug", "--with-index"])

    assert result.exit_code == 0
    assert captured == {"chapter_no": None, "with_index": True}
