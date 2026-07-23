"""eval/gate_summary.py — load_gate_scores()/format_gate_line() 테스트."""
import json
from pathlib import Path

from book_forge.eval.gate_summary import format_gate_line, load_gate_scores


def _write_result(tmp_path: Path, harness_groups: dict) -> Path:
    path = tmp_path / "result.json"
    path.write_text(
        json.dumps({"extra_metrics": {"harness_groups": harness_groups}}), encoding="utf-8"
    )
    return path


def test_load_gate_scores_reads_available_and_missing_gates(tmp_path: Path) -> None:
    path = _write_result(
        tmp_path,
        {
            "A": {"score": 0.72, "status": "pass"},
            "C": {"score": 0.4, "status": "fail"},
            # B/D/E/F/G 는 아예 없음 — N/A로 처리돼야 함
        },
    )
    scores = load_gate_scores(path)
    assert scores["A"] == 0.72
    assert scores["C"] == 0.4
    assert scores["B"] is None
    assert scores["G"] is None


def test_load_gate_scores_handles_null_score_field(tmp_path: Path) -> None:
    path = _write_result(tmp_path, {"F": {"score": None, "status": "n/a"}})
    scores = load_gate_scores(path)
    assert scores["F"] is None


def test_load_gate_scores_missing_harness_groups_key(tmp_path: Path) -> None:
    path = tmp_path / "result.json"
    path.write_text(json.dumps({}), encoding="utf-8")
    scores = load_gate_scores(path)
    assert all(v is None for v in scores.values())


def test_format_gate_line_shows_na_for_missing() -> None:
    assert "N/A" in format_gate_line("F", None)


def test_format_gate_line_icons_by_threshold() -> None:
    assert "✅" in format_gate_line("A", 0.9)
    assert "⚠️" in format_gate_line("A", 0.6)
    assert "❌" in format_gate_line("A", 0.2)
