"""Book-forge × Agent-Evaluator 통합 — PerformanceMonitor 팩토리.

Lecture_forge의 build_lecture_monitor() 패턴을 따른다. 여기서는 모니터 수준
옵션만 설정하고, Gate A-G Config는 각 에이전트(planner.py 등)에서
@agent_eval 호출 시 개별 지정한다.

일반 능력 AG(SPEC.md 4부) — 이 함수의 `enable_llm_judge`/`judge_model`
파라미터는 원래부터 있었지만, 실제로 확인해보니 7개 CLI 명령 전부 이 값을
넘기지 않는 "죽은 파라미터"였다(호출부가 항상 기본값만 씀). `new`/`draft`가
`--enable-llm-judge`/`--judge-model`로 실제 배선한다. Gate 가중치
(`gate_a_tcr_weight` 등, agent-evaluator가 이미 지원하지만 Book-forge 어디서도
노출 안 됐던 값)는 CLI 플래그 대신 `.env`(`BOOK_FORGE_GATE_*_WEIGHT`)로
읽는다 — 프로젝트 생성마다 매번 타이핑하기보다 "이 환경에서는 항상 이
기준으로 판정한다"는 저자별 고정 설정에 더 가깝기 때문(LLM Provider 선택과
같은 성격).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from agent_evaluator import PerformanceMonitor

# env var 이름 → PerformanceMonitor 키워드 인자 이름.
_GATE_WEIGHT_ENV_VARS = (
    ("BOOK_FORGE_GATE_A_TCR_WEIGHT", "gate_a_tcr_weight"),
    ("BOOK_FORGE_GATE_C_TCR_WEIGHT", "gate_c_tcr_weight"),
    ("BOOK_FORGE_GATE_B_LOOP_WEIGHT", "gate_b_loop_weight"),
)


def _gate_weight_overrides() -> dict[str, float]:
    """`.env`(load_config()가 이미 로드)에 설정된 Gate 가중치만 골라낸다.

    지정 안 된 항목은 PerformanceMonitor 자체 기본값(gate_a_tcr_weight=0.4 등,
    CLAUDE.md에 문서화됨)을 그대로 쓴다 — 하위 호환. 값이 float으로 파싱 안
    되면(오타 등) 그 항목만 조용히 무시한다 — 다른 alternative_suggester.py의
    "관대한 파싱, 실패해도 결과는 낸다" 원칙과 동일(잘못된 설정 하나 때문에
    전체 파이프라인이 죽으면 안 됨).
    """
    overrides: dict[str, float] = {}
    for env_name, kwarg_name in _GATE_WEIGHT_ENV_VARS:
        raw = os.environ.get(env_name)
        if raw is None:
            continue
        try:
            overrides[kwarg_name] = float(raw)
        except ValueError:
            continue
    return overrides


def build_book_monitor(
    output_dir: str = "eval_results/",
    *,
    enable_llm_judge: bool = False,
    judge_model: Optional[str] = None,
) -> PerformanceMonitor:
    """Book-forge 기획/집필 파이프라인용 PerformanceMonitor를 생성한다.

    Args:
        output_dir: 평가 결과 JSON/HTML 저장 경로 (프로젝트별 eval_results/).
        enable_llm_judge: True면 일부 샘플에 LLM 채점을 적용한다 (기본 off —
            로컬 Ollama 소형 모델로는 judge 품질이 들쭉날쭉할 수 있어 opt-in).
        judge_model: None이면 API 키 기반 자동 결정.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    return PerformanceMonitor(
        output_dir=output_dir,
        enable_security_metrics=True,   # Gate E — 외부 입력(향후 RAG 소스) 대비 상시 on
        enable_hallucination_detection=False,  # 비용 큰 항목은 opt-in 유지
        enable_llm_judge=enable_llm_judge,
        judge_model=judge_model,
        judge_sample_rate=0.2,
        auto_save=True,
        auto_save_interval=5,
        **_gate_weight_overrides(),
    )
