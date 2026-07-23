"""`book-forge review` CLI 테스트 — LLM은 결정론적 fake로 대체해 오프라인 검증."""
from pathlib import Path

from click.testing import CliRunner

import book_forge.cli.project_utils as project_utils
from book_forge.cli.main import cli

TOC_MD = """## Part 1. 과일학

- Chapter 1. 사과 개론

```toc
1|과일학|1|사과 개론
```
"""


class _AgreeingLLM:
    model = "fake"

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        if "가독성(구조/설명)" in prompt:
            return "VERDICT: APPROVE\nREASON: 설명이 명확합니다."
        if "정확성(사실/근거)" in prompt:
            return "VERDICT: APPROVE\nREASON: 소스에 근거해 정확합니다."
        if "FINAL" in prompt:
            return "FINAL: APPROVE\nSUMMARY: 두 검토자 모두 승인했습니다."
        raise AssertionError(f"unexpected prompt: {prompt[:100]}")


def _make_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "projects" / "review-slug"
    part_dir = project_dir / "Part_1_과일학"
    part_dir.mkdir(parents=True)
    (project_dir / "00_기획안.md").write_text("# 과일책\n\n## 목적\n\n요약.", encoding="utf-8")
    (project_dir / "01_목차.md").write_text(TOC_MD, encoding="utf-8")
    (part_dir / "Chapter_01_사과_개론.md").write_text(
        "# Chapter 01: 사과 개론\n\n사과는 장미과 과일이다.\n", encoding="utf-8"
    )
    return project_dir


def test_review_command_prints_verdicts_and_final_decision(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("book_forge.cli.commands.review_cmd.create_llm", lambda: _AgreeingLLM())

    _make_project(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ["review", "review-slug", "1"])

    assert result.exit_code == 0, result.output
    assert "정확성 검토자" in result.output
    assert "가독성 검토자" in result.output
    assert "최종 판정: APPROVE" in result.output
    assert "합의도: 1.00" in result.output


def test_review_command_missing_chapter_number_raises(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    _make_project(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ["review", "review-slug", "99"])

    assert result.exit_code != 0
    assert "찾을 수 없습니다" in result.output


def test_review_command_unwritten_chapter_raises(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    project_dir = _make_project(tmp_path)
    stub_path = project_dir / "Part_1_과일학" / "Chapter_01_사과_개론.md"
    stub_path.write_text("# Chapter 01: 사과 개론\n\n> TODO: 이 챕터를 집필하세요.\n", encoding="utf-8")
    stub_path.unlink()  # 아예 파일이 없는 케이스로 만든다

    runner = CliRunner()
    result = runner.invoke(cli, ["review", "review-slug", "1"])

    assert result.exit_code != 0
    assert "집필되지 않았습니다" in result.output
