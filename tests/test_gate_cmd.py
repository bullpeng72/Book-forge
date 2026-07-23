"""`book-forge gate` 테스트.

agent-evaluator의 검증된 `agent-eval gate` CLI를 실제 서브프로세스로 위임
호출하므로(모킹하지 않음), 진짜 PerformanceMonitor로 만든 결과 JSON을
대상으로 실제 종료 코드까지 확인한다.
"""
from pathlib import Path

from agent_evaluator import PerformanceMonitor, create_taskresult
from click.testing import CliRunner

import book_forge.cli.project_utils as project_utils
from book_forge.cli.main import cli


def _make_project_with_result(tmp_path: Path, *, passing: bool) -> Path:
    project_dir = tmp_path / "projects" / "sample-slug"
    eval_dir = project_dir / "eval_results"
    eval_dir.mkdir(parents=True)

    monitor = PerformanceMonitor(output_dir=str(eval_dir))
    if passing:
        response = "주제 X를 다루는 기획안입니다. 목적: 초보자 대상 실습서 제작."
        task = create_taskresult(
            task_id="t1",
            question="주제 X에 대한 기획안을 작성하라",
            response=response,
            ground_truth=response,
            execution_time=1.0,
            task_type="planning",
        )
    else:
        task = create_taskresult(
            task_id="t1",
            question="주제 X에 대한 기획안을 작성하라",
            response="전혀 관련 없는 응답",
            ground_truth="주제 X를 다루는 기획안입니다. 목적: 초보자 대상 실습서 제작.",
            execution_time=1.0,
            task_type="planning",
            has_error=True,
        )
    monitor.record_task(task)
    monitor.save_to_file("planning")
    return project_dir


def test_gate_passes_with_low_threshold(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    _make_project_with_result(tmp_path, passing=True)

    runner = CliRunner()
    result = runner.invoke(cli, ["gate", "sample-slug", "--min-gate-score", "0.0"])

    assert result.exit_code == 0
    assert "게이팅 대상" in result.output


def test_gate_fails_with_high_threshold(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    _make_project_with_result(tmp_path, passing=False)

    runner = CliRunner()
    result = runner.invoke(cli, ["gate", "sample-slug", "--min-gate-score", "0.99"])

    assert result.exit_code == 1


def test_gate_missing_project_raises(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ["gate", "nonexistent-slug"])

    assert result.exit_code != 0
    assert "프로젝트를 찾을 수 없습니다" in result.output


def test_gate_missing_eval_results_raises(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    (tmp_path / "projects" / "empty-slug").mkdir(parents=True)

    runner = CliRunner()
    result = runner.invoke(cli, ["gate", "empty-slug"])

    assert result.exit_code != 0
    assert "평가 결과 파일이 없습니다" in result.output


def test_gate_explicit_file_overrides_latest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    project_dir = _make_project_with_result(tmp_path, passing=True)
    result_file = next((project_dir / "eval_results").glob("*.json"))

    runner = CliRunner()
    result = runner.invoke(
        cli, ["gate", "sample-slug", "--file", str(result_file), "--min-gate-score", "0.0"]
    )

    assert result.exit_code == 0
    assert str(result_file) in result.output
