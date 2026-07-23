"""`book-forge new` — 주제 → 기획안 → 목차, 저자 승인까지 대화형 반복."""
from __future__ import annotations

import click
from agent_evaluator.gates.live_guardrail import GuardrailBlockedError

from book_forge.agents.planner import build_propose_plan
from book_forge.agents.review_loop import build_revise, run_review_loop
from book_forge.agents.scaffold import scaffold_project
from book_forge.agents.toc_designer import build_design_toc
from book_forge.config import ensure_project_dir, load_config
from book_forge.eval.monitor import build_book_monitor
from book_forge.exceptions import BookForgeError
from book_forge.llm.provider import create_llm
from book_forge.models import parse_toc_manifest, slugify


@click.command()
@click.argument("title")
@click.option("--constraints", default="", help="저자 제약/요구사항 (자유 텍스트, 선택)")
def new(title: str, constraints: str) -> None:
    """주제(TITLE)로 신규 프로젝트를 만들고 기획→목차 대화형 루프를 진행한다."""
    load_config()

    slug = slugify(title)
    project_dir = ensure_project_dir(slug)
    click.echo(f"📁 프로젝트 디렉토리: {project_dir}\n")

    try:
        llm = create_llm()
    except BookForgeError as exc:
        click.echo(f"❌ {exc}")
        raise SystemExit(1) from exc

    monitor = build_book_monitor(output_dir=str(project_dir / "eval_results"))

    propose_plan = build_propose_plan(llm, monitor)
    design_toc = build_design_toc(llm, monitor)
    revise = build_revise(llm, monitor)

    def render(md: str) -> None:
        click.echo("\n" + "─" * 60)
        click.echo(md.strip())
        click.echo("─" * 60)

    def ask_feedback(prompt_label: str) -> str:
        return click.prompt(
            f"\n{prompt_label} (Enter=승인, 또는 수정 요청 입력)",
            default="",
            show_default=False,
        )

    click.echo("📝 기획안 생성 중 (LLM 호출)...")
    proposal_md = propose_plan(
        topic=title, constraints=constraints, ground_truth=f"{title} {constraints}"
    )
    proposal_md = run_review_loop(
        kind="plan",
        initial_md=proposal_md,
        revise_fn=revise,
        render=render,
        ask_feedback=lambda: ask_feedback("기획안 검토"),
    )

    # PlannerAgent는 "## 목적"으로 시작하는 본문만 생성한다(PLAN_PROMPT 형식) — 책
    # 제목 자체는 어디에도 없다. build/edit/gate가 프로젝트 제목을 알아내는 유일한
    # 방법이 00_기획안.md 첫 줄이므로, 저장 시점에 H1로 명시적으로 붙여준다.
    proposal_path = project_dir / "00_기획안.md"
    proposal_path.write_text(f"# {title}\n\n{proposal_md}", encoding="utf-8")
    click.echo(f"\n✅ 기획안 확정: {proposal_path}")

    click.echo("\n📋 목차 설계 중 (LLM 호출)...")
    toc_md = design_toc(proposal_md=proposal_md)
    toc_md = run_review_loop(
        kind="toc",
        initial_md=toc_md,
        revise_fn=revise,
        render=render,
        ask_feedback=lambda: ask_feedback("목차 검토"),
    )

    try:
        chapters = parse_toc_manifest(toc_md)
    except BookForgeError as exc:
        click.echo(f"\n❌ 목차 파싱 실패: {exc}")
        click.echo("   LLM이 ```toc 블록 형식을 지키지 않았습니다. book-forge new를 다시 실행하세요.")
        raise SystemExit(1) from exc

    toc_path = project_dir / "01_목차.md"
    toc_path.write_text(toc_md, encoding="utf-8")
    click.echo(f"\n✅ 목차 확정: {toc_path} ({len(chapters)}개 챕터)")

    click.echo("\n🏗️  챕터 스캐폴드 생성 중...")
    try:
        results = scaffold_project(project_dir, chapters)
    except GuardrailBlockedError as exc:
        click.echo(f"\n❌ 스캐폴딩 차단됨: {exc.verdict.reason}")
        raise SystemExit(1) from exc

    for line in results:
        click.echo(f"  {line}")

    monitor.save_to_file("planning")
    click.echo(f"\n✅ 완료. 계측 결과: {project_dir / 'eval_results'}")
    click.echo(f"   다음: {project_dir} 아래 Part_*/Chapter_*.md 를 집필하세요.")
