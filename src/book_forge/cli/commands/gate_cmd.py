"""`book-forge gate` — Harness Gate A-G 판정. 새 판정 로직을 만들지 않고
agent-evaluator의 검증된 `agent-eval gate` CLI를 그대로 위임 호출한다.

`sys.executable -m agent_evaluator.cli.main`으로 호출하는 이유: 콘솔 스크립트
이름(`agent-eval`)에 의존하면 pipx처럼 의존성의 entry point가 PATH에 노출되지
않는 설치 방식에서 깨진다 — 모듈 경로 호출은 book-forge와 같은 인터프리터/venv를
그대로 쓰므로 항상 안전하다.

플래그는 `agent-eval gate --help`(agent_evaluator/cli/main.py의 gate_p 파서)
전체를 그대로 노출한다 — 일부만 골라 전달하면 CI에서 골든셋 회귀·baseline 저장
같은 기능이 book-forge 쪽에서만 안 되는 불일치가 생긴다.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional

import click

from book_forge.cli.project_utils import resolve_project_dir


def _latest_result_file(eval_dir: Path) -> Optional[Path]:
    if not eval_dir.is_dir():
        return None
    files = sorted(eval_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


@click.command()
@click.argument("slug")
@click.option(
    "--file", "result_file", type=click.Path(exists=True, dir_okay=False), default=None,
    help="게이팅할 결과 JSON 지정 (미지정 시 eval_results/ 안 최신 파일)",
)
@click.option(
    "--min-gate-score", type=float, default=0.5, show_default=True,
    help="Gate A-G 가중 평균 최소 점수 (0.0-1.0, 데이터 없는 Gate는 평균에서 제외)",
)
@click.option("--group-weights", default=None, help="Gate별 가중치. 예: A:2.0,E:3.0")
@click.option(
    "--gate-thresholds", default=None,
    help="Gate별 최소 점수(0.0-1.0). 예: A:0.8,D:0.9 — 미지정 Gate는 --min-gate-score 사용",
)
@click.option("--required-gates", default=None, help="검사할 Gate만 지정. 예: A,D,E (기본: 데이터 있는 전체)")
@click.option("--fail-on-gate-warn", is_flag=True, help="Gate 상태 'warn'도 실패로 취급")
@click.option("--tcr", type=float, default=None, help="최소 태스크 완료율 (%)")
@click.option("--accuracy", type=float, default=None, help="최소 정확도 (%)")
@click.option("--p95-latency", type=float, default=None, help="최대 P95 지연시간(초)")
@click.option("--hallucination", type=float, default=None, help="최대 환각률 (%)")
@click.option("--llm-judge", type=float, default=None, help="최소 LLM Judge 종합 점수 (0-5)")
@click.option("--baseline", type=click.Path(), default=None, help="baseline 파일 경로 (기본: <결과폴더>/baseline.json)")
@click.option("--baseline-version", default=None, help="버전별 독립 baseline 태그")
@click.option("--save-baseline", is_flag=True, help="현재 결과를 baseline으로 저장")
@click.option("--fail-on-regression", type=float, default=None, help="baseline 대비 허용 회귀(%) 초과 시 exit 2")
@click.option("--golden-set", type=click.Path(), default=None, help="골든셋 JSON 경로")
@click.option("--fail-on-golden-regression", is_flag=True, help="골든셋 케이스 누락/실패 시 exit 3")
@click.option("--junit-xml", default=None, help="JUnit XML 출력 경로 (CI 연동용)")
def gate(
    slug: str,
    result_file: Optional[str],
    min_gate_score: float,
    group_weights: Optional[str],
    gate_thresholds: Optional[str],
    required_gates: Optional[str],
    fail_on_gate_warn: bool,
    tcr: Optional[float],
    accuracy: Optional[float],
    p95_latency: Optional[float],
    hallucination: Optional[float],
    llm_judge: Optional[float],
    baseline: Optional[str],
    baseline_version: Optional[str],
    save_baseline: bool,
    fail_on_regression: Optional[float],
    golden_set: Optional[str],
    fail_on_golden_regression: bool,
    junit_xml: Optional[str],
) -> None:
    """SLUG 프로젝트의 최신(또는 지정) 평가 결과로 Harness Gate A-G를 판정한다.

    종료 코드도 agent-eval gate 그대로 전달한다: 0=통과, 1=미달, 2=baseline 대비 회귀,
    3=골든셋 회귀.
    """
    project_dir = resolve_project_dir(slug)
    eval_dir = project_dir / "eval_results"

    target = Path(result_file) if result_file else _latest_result_file(eval_dir)
    if target is None:
        raise click.ClickException(
            f"평가 결과 파일이 없습니다: {eval_dir} "
            "(book-forge new 또는 build slides 를 먼저 실행하세요)"
        )

    cmd = [
        sys.executable, "-m", "agent_evaluator.cli.main", "gate", str(target),
        "--min-gate-score", str(min_gate_score),
    ]
    if group_weights:
        cmd += ["--group-weights", group_weights]
    if gate_thresholds:
        cmd += ["--gate-thresholds", gate_thresholds]
    if required_gates:
        cmd += ["--required-gates", required_gates]
    if fail_on_gate_warn:
        cmd += ["--fail-on-gate-warn"]
    if tcr is not None:
        cmd += ["--tcr", str(tcr)]
    if accuracy is not None:
        cmd += ["--accuracy", str(accuracy)]
    if p95_latency is not None:
        cmd += ["--p95-latency", str(p95_latency)]
    if hallucination is not None:
        cmd += ["--hallucination", str(hallucination)]
    if llm_judge is not None:
        cmd += ["--llm-judge", str(llm_judge)]
    if baseline:
        cmd += ["--baseline", baseline]
    if baseline_version:
        cmd += ["--baseline-version", baseline_version]
    if save_baseline:
        cmd += ["--save-baseline"]
    if fail_on_regression is not None:
        cmd += ["--fail-on-regression", str(fail_on_regression)]
    if golden_set:
        cmd += ["--golden-set", golden_set]
    if fail_on_golden_regression:
        cmd += ["--fail-on-golden-regression"]
    if junit_xml:
        cmd += ["--junit-xml", junit_xml]

    click.echo(f"🚦 게이팅 대상: {target}")
    result = subprocess.run(cmd)
    raise SystemExit(result.returncode)
