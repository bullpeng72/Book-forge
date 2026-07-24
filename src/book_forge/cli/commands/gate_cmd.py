"""`book-forge gate` — Harness Gate A-G 판정. 새 판정 로직을 만들지 않고
agent-evaluator의 검증된 `agent-eval gate` CLI를 그대로 위임 호출한다.

`sys.executable -m agent_evaluator.cli.main`으로 호출하는 이유: 콘솔 스크립트
이름(`agent-eval`)에 의존하면 pipx처럼 의존성의 entry point가 PATH에 노출되지
않는 설치 방식에서 깨진다 — 모듈 경로 호출은 book-forge와 같은 인터프리터/venv를
그대로 쓰므로 항상 안전하다.

플래그는 `agent-eval gate --help`(agent_evaluator/cli/main.py의 gate_p 파서)
전체를 그대로 노출한다 — 일부만 골라 전달하면 CI에서 골든셋 회귀·baseline 저장
같은 기능이 book-forge 쪽에서만 안 되는 불일치가 생긴다.

일반 능력 AF(SPEC.md 4부) — `--file`을 안 주면 예전엔 eval_results/의
mtime 기준 최신 파일 **하나만** 골랐다. 그런데 `draft_cmd.py`는 챕터마다
별도 PerformanceMonitor로 `draft_ch{N}.json`을 따로 저장한다 — "책 전체가
배포 가능한가"를 물어야 할 `book-forge gate <slug>`가 실제로는 저자가
가장 최근에 건드린 챕터 하나만 판정하는 걸 실측으로 확인했다(6챕터 책에서
Chapter 5 하나만 게이팅됨, 나머지 5개 무시). agent-evaluator에 이미 있는
`PerformanceMonitor.load_from_file()`/`.merge()`(새 판정 로직이 아니라 이미
검증된 SDK 기능)로 eval_results/의 모든 결과 파일을 하나로 합친 뒤 그 병합
리포트를 게이팅한다 — 파일이 하나뿐이면 기존 동작과 완전히 동일(하위 호환).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional

import click

from book_forge.cli.project_utils import resolve_project_dir

_MERGED_RESULT_FILENAME = "_merged_gate_result.json"
_NON_REPORT_FILENAMES = {"baseline.json", _MERGED_RESULT_FILENAME}


def _all_result_files(eval_dir: Path) -> list[Path]:
    """eval_results/의 챕터별 결과 JSON 전부를 이름순으로 반환한다.

    baseline.json(리포트가 아니라 --save-baseline이 저장한 비교 기준)과
    이 함수 스스로 만드는 병합 산출물(_merged_gate_result.json)은 제외한다
    — 후자를 안 걸러내면 다음 gate 실행 때 이전 병합 결과가 또 병합
    입력으로 들어가는 피드백 루프가 생긴다.
    """
    if not eval_dir.is_dir():
        return []
    return sorted(
        p for p in eval_dir.glob("*.json") if p.name not in _NON_REPORT_FILENAMES
    )


def _merge_result_files(files: list[Path]) -> Path:
    """여러 챕터 결과 파일을 하나의 PerformanceMonitor로 합쳐 저장하고 그 경로를 반환한다.

    PerformanceMonitor.load_from_file()/.merge()는 agent-evaluator가 이미
    제공하는 SDK 기능이다(D8) — Book-forge가 직접 병합 로직을 구현하지
    않는다. files는 최소 1개 이상이어야 한다(호출부가 보장).
    """
    from agent_evaluator import PerformanceMonitor

    merged = PerformanceMonitor.load_from_file(str(files[0]))
    for extra in files[1:]:
        merged = merged.merge(PerformanceMonitor.load_from_file(str(extra)))
    output_path = files[0].parent / _MERGED_RESULT_FILENAME
    merged.save_to_file(str(output_path))
    return output_path


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

    if result_file:
        target = Path(result_file)
    else:
        # AF: --file을 안 주면 eval_results/의 모든 챕터 결과를 책 전체
        # 하나로 집계한다 — 파일이 1개뿐이면 그 파일 자체를 그대로 쓰므로
        # (병합 왕복 없이) 단일 챕터 프로젝트에서는 기존 동작과 동일하다.
        files = _all_result_files(eval_dir)
        if not files:
            raise click.ClickException(
                f"평가 결과 파일이 없습니다: {eval_dir} "
                "(book-forge new 또는 build slides 를 먼저 실행하세요)"
            )
        if len(files) == 1:
            target = files[0]
        else:
            target = _merge_result_files(files)
            click.echo(
                f"📚 {len(files)}개 결과 파일을 책 전체로 집계했습니다: "
                + ", ".join(f.name for f in files)
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
