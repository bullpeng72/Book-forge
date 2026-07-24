"""`book-forge lint` 테스트."""
from pathlib import Path

from click.testing import CliRunner

import book_forge.cli.project_utils as project_utils
from book_forge.cli.main import cli

TOC_MD = """## Part 1. 과일학

- Chapter 1. 사과 개론
- Chapter 2. 바나나 심화

```toc
1|과일학|1|사과 개론
1|과일학|2|바나나 심화
```
"""


def _make_project(tmp_path: Path, *, ch1_body: str, ch2_body: str) -> Path:
    project_dir = tmp_path / "projects" / "lint-slug"
    part_dir = project_dir / "Part_1_과일학"
    part_dir.mkdir(parents=True)

    (project_dir / "01_목차.md").write_text(TOC_MD, encoding="utf-8")
    (part_dir / "Chapter_01_사과_개론.md").write_text(ch1_body, encoding="utf-8")
    (part_dir / "Chapter_02_바나나_심화.md").write_text(ch2_body, encoding="utf-8")
    return project_dir


def test_lint_reports_no_variants_when_consistent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    _make_project(
        tmp_path,
        ch1_body="`PerformanceMonitor`를 쓴다.",
        ch2_body="`PerformanceMonitor`를 또 쓴다.",
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["lint", "lint-slug"])

    assert result.exit_code == 0
    assert "불일치 후보 없음" in result.output


def test_lint_reports_variants_when_inconsistent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    _make_project(
        tmp_path,
        ch1_body="`ToolCallAnalyzer`를 쓴다.",
        ch2_body="`tool_call_analyzer`를 쓴다.",
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["lint", "lint-slug"])

    assert result.exit_code == 0
    assert "ToolCallAnalyzer" in result.output
    assert "tool_call_analyzer" in result.output
    assert "자동 수정되지 않습니다" in result.output


def test_lint_fail_on_inconsistency_flag_sets_exit_code(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    _make_project(
        tmp_path,
        ch1_body="`ToolCallAnalyzer`를 쓴다.",
        ch2_body="`tool_call_analyzer`를 쓴다.",
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["lint", "lint-slug", "--fail-on-inconsistency"])

    assert result.exit_code == 1


def test_lint_without_fail_flag_exits_zero_even_with_variants(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    _make_project(
        tmp_path,
        ch1_body="`ToolCallAnalyzer`를 쓴다.",
        ch2_body="`tool_call_analyzer`를 쓴다.",
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["lint", "lint-slug"])

    assert result.exit_code == 0
