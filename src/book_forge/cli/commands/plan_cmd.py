"""`book-forge plan` — 기존 기획안/목차를 다시 열어 저자 승인 루프를 재개한다.

``--revise`` 없이 호출하면 현재 기획안/목차만 출력한다(미리보기, 변경 없음).
``--revise``를 주면 book-forge new와 동일한 리뷰 루프에 다시 들어가고, 목차가
바뀌면 agents.scaffold.reconcile_chapters()로 기존 챕터 파일을 보존하며 재조정한다.
"""
from __future__ import annotations

import click
from agent_evaluator.gates.live_guardrail import GuardrailBlockedError

from book_forge.agents.review_loop import build_revise, run_review_loop
from book_forge.agents.scaffold import reconcile_chapters
from book_forge.cli.project_utils import load_title, resolve_project_dir
from book_forge.config import load_config
from book_forge.eval.monitor import build_book_monitor
from book_forge.exceptions import BookForgeError
from book_forge.llm.provider import create_llm
from book_forge.models import parse_toc_manifest
from book_forge.publish.toc_loader import load_toc


def _strip_title_h1(text: str, title: str) -> str:
    """new_cmd.py가 저장 시점에 붙인 '# {title}\\n\\n' 헤더를 제거해, PlannerAgent가
    원래 생성하던 순수 본문(``## 목적``으로 시작)으로 되돌린다 — 그래야 REVISE_PROMPT가
    다루는 형식과 일치한다."""
    prefix = f"# {title}\n\n"
    return text[len(prefix) :] if text.startswith(prefix) else text


@click.command()
@click.argument("slug")
@click.option(
    "--revise", "revise_flag", is_flag=True,
    help="대화형 수정 루프로 진입 (미지정 시 현재 기획안/목차만 출력하고 종료)",
)
def plan(slug: str, revise_flag: bool) -> None:
    """SLUG 프로젝트의 기획안/목차를 다시 연다."""
    load_config()
    project_dir = resolve_project_dir(slug)

    proposal_path = project_dir / "00_기획안.md"
    toc_path = project_dir / "01_목차.md"
    if not proposal_path.is_file() or not toc_path.is_file():
        raise click.ClickException(
            f"기획안/목차가 없습니다: {project_dir} (book-forge new 로 먼저 생성하세요)"
        )

    title = load_title(project_dir)
    proposal_md = _strip_title_h1(proposal_path.read_text(encoding="utf-8"), title)
    toc_md = toc_path.read_text(encoding="utf-8")

    if not revise_flag:
        click.echo(f"📁 {project_dir}\n")
        click.echo("── 기획안 ──")
        click.echo(f"# {title}\n\n{proposal_md}")
        click.echo("\n── 목차 ──")
        click.echo(toc_md)
        click.echo("\n(수정하려면 --revise 를 붙이세요)")
        return

    # revise 전 상태를 기준선으로 캡처 — 01_목차.md를 새로 쓰기 전에 반드시 먼저 읽어야 한다.
    old_chapters = load_toc(project_dir)

    try:
        llm = create_llm()
    except BookForgeError as exc:
        raise click.ClickException(str(exc)) from exc

    monitor = build_book_monitor(output_dir=str(project_dir / "eval_results"))
    revise = build_revise(llm, monitor)

    def render(md: str) -> None:
        click.echo("\n" + "─" * 60)
        click.echo(md.strip())
        click.echo("─" * 60)

    def ask_feedback(label: str) -> str:
        return click.prompt(
            f"\n{label} (Enter=승인, 또는 수정 요청 입력)", default="", show_default=False
        )

    click.echo(f"📁 프로젝트: {project_dir}\n")

    click.echo("📝 기존 기획안 검토")
    proposal_md = run_review_loop(
        kind="plan", initial_md=proposal_md, revise_fn=revise,
        render=render, ask_feedback=lambda: ask_feedback("기획안 검토"),
    )
    proposal_path.write_text(f"# {title}\n\n{proposal_md}", encoding="utf-8")
    click.echo(f"\n✅ 기획안 갱신: {proposal_path}")

    click.echo("\n📋 기존 목차 검토")
    toc_md = run_review_loop(
        kind="toc", initial_md=toc_md, revise_fn=revise,
        render=render, ask_feedback=lambda: ask_feedback("목차 검토"),
    )

    try:
        new_specs = parse_toc_manifest(toc_md)
    except BookForgeError as exc:
        click.echo(f"\n❌ 목차 파싱 실패: {exc}")
        click.echo("   목차를 저장하지 않았습니다 — 기존 01_목차.md는 그대로입니다.")
        raise SystemExit(1) from exc

    toc_path.write_text(toc_md, encoding="utf-8")
    click.echo(f"\n✅ 목차 갱신: {toc_path} ({len(new_specs)}개 챕터)")

    click.echo("\n🔄 챕터 파일 재조정 중...")
    try:
        reconcile = reconcile_chapters(project_dir, old_chapters, new_specs)
    except GuardrailBlockedError as exc:
        click.echo(f"\n❌ 재조정 차단됨: {exc.verdict.reason}")
        raise SystemExit(1) from exc

    for path in reconcile.created:
        click.echo(f"  created: {path}")
    for old_path, new_path in reconcile.renamed:
        click.echo(f"  renamed: {old_path} → {new_path} (제목 변경, 기존 본문 보존)")
    if reconcile.orphaned:
        click.echo("\n⚠️  새 목차에서 빠졌지만 파일은 그대로 남아있는 챕터 (자동 삭제하지 않음):")
        for path in reconcile.orphaned:
            click.echo(f"  {path}")

    monitor.save_to_file("plan_revise")
    click.echo(f"\n✅ 완료. 계측 결과: {project_dir / 'eval_results'}")
