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


# 일반 능력 AF — 챕터마다 별도 결과 파일이 있을 때 "최근 파일 하나"가 아니라
# 전체를 집계해 책 전체를 판정해야 한다(실측 확인된 문제의 회귀 방지).
def _make_project_with_multiple_chapter_results(tmp_path: Path, *, chapter_count: int) -> Path:
    from agent_evaluator import PerformanceMonitor, create_taskresult

    project_dir = tmp_path / "projects" / "multi-slug"
    eval_dir = project_dir / "eval_results"
    eval_dir.mkdir(parents=True)

    for i in range(1, chapter_count + 1):
        monitor = PerformanceMonitor(output_dir=str(eval_dir))
        response = f"챕터 {i}에 대한 기획안입니다. 목적: 초보자 대상 실습서 제작."
        task = create_taskresult(
            task_id=f"ch{i}-t1",
            question=f"챕터 {i} 초안을 작성하라",
            response=response,
            ground_truth=response,
            execution_time=1.0,
            task_type="planning",
        )
        monitor.record_task(task)
        monitor.save_to_file(f"draft_ch{i:02d}")
    return project_dir


def test_gate_without_file_aggregates_all_chapter_results(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    _make_project_with_multiple_chapter_results(tmp_path, chapter_count=6)

    runner = CliRunner()
    result = runner.invoke(cli, ["gate", "multi-slug", "--min-gate-score", "0.0"])

    assert result.exit_code == 0, result.output
    assert "6개 결과 파일을 책 전체로 집계했습니다" in result.output
    assert "_merged_gate_result.json" in result.output

    merged_path = tmp_path / "projects" / "multi-slug" / "eval_results" / "_merged_gate_result.json"
    assert merged_path.is_file()
    import json

    merged_data = json.loads(merged_path.read_text(encoding="utf-8"))
    assert merged_data["total_tasks"] == 6  # 6개 챕터의 태스크가 전부 합쳐짐


def test_gate_aggregation_excludes_baseline_and_previous_merge(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    project_dir = _make_project_with_multiple_chapter_results(tmp_path, chapter_count=2)
    eval_dir = project_dir / "eval_results"
    (eval_dir / "baseline.json").write_text("{}", encoding="utf-8")

    runner = CliRunner()
    first = runner.invoke(cli, ["gate", "multi-slug", "--min-gate-score", "0.0"])
    assert first.exit_code == 0, first.output

    # 병합 산출물이 이미 있는 상태에서 다시 실행해도 이전 병합 결과가 또
    # 입력으로 들어가 피드백 루프를 만들지 않아야 한다(태스크 수가 변하지 않음).
    second = runner.invoke(cli, ["gate", "multi-slug", "--min-gate-score", "0.0"])
    assert second.exit_code == 0, second.output
    assert "2개 결과 파일을 책 전체로 집계했습니다" in second.output  # 여전히 2개(baseline/병합본 제외)

    import json

    merged_data = json.loads(
        (eval_dir / "_merged_gate_result.json").read_text(encoding="utf-8")
    )
    assert merged_data["total_tasks"] == 2


def test_gate_single_chapter_result_unchanged_from_before(tmp_path: Path, monkeypatch) -> None:
    # 챕터 결과가 1개뿐이면 병합 왕복 없이 그 파일 자체를 그대로 쓴다(하위 호환).
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    project_dir = _make_project_with_multiple_chapter_results(tmp_path, chapter_count=1)

    runner = CliRunner()
    result = runner.invoke(cli, ["gate", "multi-slug", "--min-gate-score", "0.0"])

    assert result.exit_code == 0, result.output
    assert "책 전체로 집계했습니다" not in result.output
    assert "draft_ch01.json" in result.output
    assert not (project_dir / "eval_results" / "_merged_gate_result.json").exists()
