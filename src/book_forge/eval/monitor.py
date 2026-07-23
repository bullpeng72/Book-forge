"""Book-forge × Agent-Evaluator 통합 — PerformanceMonitor 팩토리.

Lecture_forge의 build_lecture_monitor() 패턴을 따른다. 여기서는 모니터 수준
옵션만 설정하고, Gate A-G Config는 각 에이전트(planner.py 등)에서
@agent_eval 호출 시 개별 지정한다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from agent_evaluator import PerformanceMonitor


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
    )
