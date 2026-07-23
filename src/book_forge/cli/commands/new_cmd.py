"""`book-forge new` — 주제 → 기획안 → 목차, 저자 승인까지 대화형 반복.

--source를 주면 목차 확정·스캐폴딩 직후 book-forge draft --all과 같은 배치
RAG 초안 생성까지 한 번에 이어간다("주제 입력 → 완성된 초안까지" 통합) — 별도
--auto-draft 플래그를 두지 않은 이유: --source 자체가 "이 소스로 뭘 하고
싶은가"의 유일한 신호이고, 소스를 줬는데 아무것도 안 하면 옵션의 존재 의미가
없다. 저커버리지 정책은 draft --all과 동일(스킵+리포트) — new는 이미 기획/목차
리뷰 루프로 사람이 붙어 있었으므로, 이어지는 배치 초안 단계까지 매 챕터 확인을
요구하면 자동화 취지가 무색해진다.
"""
from __future__ import annotations

import click
from agent_evaluator.gates.live_guardrail import GuardrailBlockedError

from book_forge.agents.planner import build_propose_plan
from book_forge.agents.review_loop import build_revise, run_review_loop
from book_forge.agents.scaffold import scaffold_project
from book_forge.agents.toc_designer import build_design_toc
from book_forge.cli.commands.draft_cmd import _SourcePath
from book_forge.config import ensure_project_dir, load_config
from book_forge.eval.monitor import build_book_monitor
from book_forge.exceptions import BookForgeError
from book_forge.llm.provider import create_llm
from book_forge.models import parse_toc_manifest, slugify
from book_forge.publish.toc_loader import load_toc


@click.command()
@click.argument("title")
@click.option("--constraints", default="", help="저자 제약/요구사항 (자유 텍스트, 선택)")
@click.option(
    "--source", "sources", multiple=True,
    type=_SourcePath(),
    help="RAG 소스 — PDF/코드 저장소 디렉토리/텍스트 파일/http(s):// URL. 지정하면 스캐폴딩 직후 "
         "전체 챕터를 자동으로 RAG 초안까지 생성한다([rag] extra 필요)",
)
@click.option("--top-k", type=int, default=8, show_default=True, help="[--source] 챕터당 검색할 소스 청크 수")
@click.option(
    "--min-coverage", type=float, default=0.5, show_default=True,
    help="[--source] 자동 초안 생성 전 평균 소스 유사도 임계값",
)
def new(
    title: str, constraints: str, sources: tuple, top_k: int, min_coverage: float
) -> None:
    """주제(TITLE)로 신규 프로젝트를 만들고 기획→목차 대화형 루프를 진행한다."""
    if sources:
        try:
            import numpy  # noqa: F401
            import pypdf  # noqa: F401
        except ImportError as exc:
            raise click.ClickException(
                'RAG 기능에 필요한 패키지가 없습니다. pip install -e ".[rag]" 로 설치하세요.'
            ) from exc

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

    if not sources:
        click.echo(f"   다음: {project_dir} 아래 Part_*/Chapter_*.md 를 집필하세요.")
        return

    # --source가 있으면 스캐폴딩 직후 곧바로 배치 RAG 초안까지 이어간다
    # (book-forge draft --all과 동일 로직 재사용 — 새 판정 로직 없음).
    from book_forge.cli.commands.draft_cmd import (
        _is_draftable,
        _print_batch_summary,
        collect_sources_into_store,
        run_batch_draft,
    )

    click.echo(f"\n📝 --source {len(sources)}개가 지정되어 전체 챕터를 자동으로 초안 생성합니다...")
    fresh_chapters = load_toc(project_dir)
    targets = [rc for rc in fresh_chapters if _is_draftable(rc, force=False)]
    store = collect_sources_into_store(project_dir, sources)
    results = run_batch_draft(targets, store, llm, project_dir, top_k=top_k, min_coverage=min_coverage)
    _print_batch_summary(results)
    click.echo(f"\n   완료. {project_dir} 에서 결과를 확인하세요.")
