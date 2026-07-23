"""평가 결과 JSON에서 Gate A-G 점수를 즉시 읽어 CLI에 보여주기 위한 경량 유틸.

``book-forge gate``가 ``agent-eval gate`` CLI 전체(baseline·회귀·골든셋 판정)를
위임하는 것과 달리, 이건 방금 기록한 세션 하나의 점수를 CLI 화면에 바로 보여주기
위한 조회 전용이다 — CI 게이팅 판정 로직은 여기 없다(그건 book-forge gate의 몫).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

GATE_LABELS = {
    "A": "목표 달성",
    "B": "행동 무결성",
    "C": "신뢰성",
    "D": "성능 계약",
    "E": "보안 경계",
    "F": "다중 에이전트",
    "G": "관측성",
}


def load_gate_scores(result_path: Path) -> dict[str, Optional[float]]:
    data = json.loads(result_path.read_text(encoding="utf-8"))
    harness = (data.get("extra_metrics") or {}).get("harness_groups", {})
    scores: dict[str, Optional[float]] = {}
    for key in "ABCDEFG":
        group = harness.get(key)
        score = group.get("score") if isinstance(group, dict) else None
        scores[key] = float(score) if score is not None else None
    return scores


def format_gate_line(gate: str, score: Optional[float]) -> str:
    label = GATE_LABELS.get(gate, gate)
    if score is None:
        return f"  · {gate} ({label}): N/A"
    if score >= 0.7:
        icon = "✅"
    elif score >= 0.5:
        icon = "⚠️ "
    else:
        icon = "❌"
    return f"  {icon} {gate} ({label}): {score:.3f}"
