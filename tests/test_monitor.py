"""eval/monitor.py — build_book_monitor()의 Gate 가중치 .env 오버라이드 테스트
(일반 능력 AG).
"""
from pathlib import Path

from book_forge.eval.monitor import _gate_weight_overrides, build_book_monitor


def test_gate_weight_overrides_empty_when_no_env_vars(monkeypatch) -> None:
    monkeypatch.delenv("BOOK_FORGE_GATE_A_TCR_WEIGHT", raising=False)
    monkeypatch.delenv("BOOK_FORGE_GATE_C_TCR_WEIGHT", raising=False)
    monkeypatch.delenv("BOOK_FORGE_GATE_B_LOOP_WEIGHT", raising=False)
    assert _gate_weight_overrides() == {}


def test_gate_weight_overrides_reads_set_env_vars(monkeypatch) -> None:
    monkeypatch.setenv("BOOK_FORGE_GATE_A_TCR_WEIGHT", "0.6")
    monkeypatch.setenv("BOOK_FORGE_GATE_B_LOOP_WEIGHT", "0.3")
    monkeypatch.delenv("BOOK_FORGE_GATE_C_TCR_WEIGHT", raising=False)

    overrides = _gate_weight_overrides()
    assert overrides == {"gate_a_tcr_weight": 0.6, "gate_b_loop_weight": 0.3}


def test_gate_weight_overrides_ignores_malformed_value(monkeypatch) -> None:
    monkeypatch.setenv("BOOK_FORGE_GATE_A_TCR_WEIGHT", "not-a-number")
    monkeypatch.delenv("BOOK_FORGE_GATE_C_TCR_WEIGHT", raising=False)
    monkeypatch.delenv("BOOK_FORGE_GATE_B_LOOP_WEIGHT", raising=False)

    assert _gate_weight_overrides() == {}


def test_build_book_monitor_applies_gate_weight_override(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BOOK_FORGE_GATE_A_TCR_WEIGHT", "0.7")
    monkeypatch.delenv("BOOK_FORGE_GATE_C_TCR_WEIGHT", raising=False)
    monkeypatch.delenv("BOOK_FORGE_GATE_B_LOOP_WEIGHT", raising=False)

    monitor = build_book_monitor(output_dir=str(tmp_path / "eval_results"))
    assert monitor._gate_a_tcr_weight == 0.7


def test_build_book_monitor_uses_default_weight_without_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("BOOK_FORGE_GATE_A_TCR_WEIGHT", raising=False)
    monkeypatch.delenv("BOOK_FORGE_GATE_C_TCR_WEIGHT", raising=False)
    monkeypatch.delenv("BOOK_FORGE_GATE_B_LOOP_WEIGHT", raising=False)

    monitor = build_book_monitor(output_dir=str(tmp_path / "eval_results"))
    assert monitor._gate_a_tcr_weight == 0.4  # PerformanceMonitor 자체 기본값
