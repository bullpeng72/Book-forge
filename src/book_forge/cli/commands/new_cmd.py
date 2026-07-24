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

from typing import Optional

import click
from agent_evaluator.gates.live_guardrail import GuardrailBlockedError

from book_forge.agents.planner import build_propose_plan
from book_forge.agents.review_loop import build_revise, run_review_loop
from book_forge.agents.scaffold import scaffold_project
from book_forge.agents.toc_designer import build_design_toc
from book_forge.cli.commands.draft_cmd import _SourcePath
from book_forge.config import ensure_project_dir, load_config, project_dir_for
from book_forge.eval.monitor import build_book_monitor
from book_forge.exceptions import BookForgeError
from book_forge.llm.provider import create_llm
from book_forge.models import parse_toc_manifest, slugify
from book_forge.publish.front_matter import FrontMatter, save_front_matter
from book_forge.publish.toc_loader import load_toc


@click.command()
@click.argument("title")
@click.option("--constraints", default="", help="저자 제약/요구사항 (자유 텍스트, 선택)")
@click.option("--author", default="", help="저자명 — HTML/PDF 표지 페이지에 표기 (선택, LLM 미생성)")
@click.option("--license-notice", "license_notice", default="", help="저작권/라이선스 고지 문구 (선택)")
@click.option("--edition", default="", help="판(edition) 표기, 예: '1판' (선택)")
@click.option(
    "--enable-llm-judge", is_flag=True,
    help="일부 샘플에 LLM 채점(faithfulness 등)을 추가 적용 (기본 off — 비용/지연 증가)",
)
@click.option(
    "--judge-model", default=None,
    help="[--enable-llm-judge] 채점에 쓸 모델 (미지정 시 API 키 기반 자동 결정)",
)
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
@click.option(
    "--check-package", default=None,
    help="[--source] 본문이 언급한 import/백틱 심볼이 이 패키지(설치된 패키지명 또는 로컬 "
         "디렉토리 경로)에 실제로 존재하는지 정적으로 대조(옵트인, 미지정 시 검사 없음)",
)
@click.option(
    "--execute-examples", is_flag=True,
    help="[--source, --check-package와 함께] python 코드 블록을 subprocess에서 실제 실행해 검증"
         "(LLM이 생성한 코드를 실행하는 위험을 인지하고 켤 것)",
)
@click.option(
    "--force", is_flag=True,
    help="이미 존재하는 프로젝트(같은 제목/슬러그)의 기획안·목차를 확인 없이 덮어쓰기",
)
def new(
    title: str, constraints: str, sources: tuple, top_k: int, min_coverage: float,
    check_package: str, execute_examples: bool, force: bool,
    author: str, license_notice: str, edition: str,
    enable_llm_judge: bool, judge_model: Optional[str],
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
    if execute_examples and not check_package:
        raise click.ClickException("--execute-examples는 --check-package와 함께 지정해야 합니다.")

    load_config()

    # 일반 능력 AH — ensure_project_dir()은 mkdir(exist_ok=True)만 쓰므로, 같은
    # 제목(슬러그)으로 다시 book-forge new를 실행하면 기존 00_기획안.md/
    # 01_목차.md가 경고 없이 덮어써졌다(실측 확인된 문제). 디렉토리를 실제로
    # 만들기 *전에* 기획안 파일 존재 여부만 확인한다 — 스캐폴딩된 빈 챕터
    # 파일은 덮어쓰기 판단 기준이 아니다(어차피 scaffold_project가 기존
    # 챕터는 건너뛴다).
    slug = slugify(title)
    existing_project_dir = project_dir_for(slug)
    if not force and (existing_project_dir / "00_기획안.md").is_file():
        if not click.confirm(
            f"\n⚠️  이미 존재하는 프로젝트입니다({existing_project_dir}). "
            "기존 기획안/목차를 덮어쓰시겠습니까?",
            default=False,
        ):
            click.echo("취소했습니다. 다른 제목을 쓰거나 --force로 덮어쓰세요.")
            raise SystemExit(0)

    project_dir = ensure_project_dir(slug)
    click.echo(f"📁 프로젝트 디렉토리: {project_dir}\n")

    # 일반 능력 AI — 저자명/저작권 고지/판 표기는 LLM이 창작할 대상이 아니라
    # 저자가 직접 입력한 값을 그대로 저장한다(front_matter.py 참고 — 별도
    # JSON 파일로 분리해 00_기획안.md의 기존 파싱 계약을 안 건드림). 전부
    # 빈 문자열이면 파일 자체를 안 만든다(save_front_matter의 is_empty 가드).
    save_front_matter(
        project_dir, FrontMatter(author=author, license_notice=license_notice, edition=edition)
    )

    try:
        llm = create_llm()
    except BookForgeError as exc:
        click.echo(f"❌ {exc}")
        raise SystemExit(1) from exc

    monitor = build_book_monitor(
        output_dir=str(project_dir / "eval_results"),
        enable_llm_judge=enable_llm_judge,
        judge_model=judge_model,
    )

    propose_plan = build_propose_plan(llm, monitor)
    design_toc = build_design_toc(llm, monitor)
    revise = build_revise(llm, monitor)

    # 일반 능력 S — --source에 코드 저장소 디렉토리가 있으면, 목차 설계
    # *이전에* H(구조적 코드 인덱싱)로 실제 모듈/클래스/함수 목록을 미리
    # 뽑아둔다. 순수 AST 정적 분석이라 임베딩/LLM 호출 없이 빠르다 — 소스를
    # 지식창고에 청크·임베딩하는 무거운 작업(아래 --source 자동 초안 단계)과는
    # 별개다. 실측 확인된 문제: 이 컨텍스트 없이는 "이 프로젝트를 분석"이라는
    # 제약을 자유 텍스트로 줘도 LLM이 존재하지 않는 서브시스템을 챕터로
    # 지어냈다(예: "컴포넌트 간 통신 메커니즘" — 실제 코드엔 없는 개념).
    code_structure = ""
    if sources:
        from book_forge.cli.commands.draft_cmd import _build_structure_summary_from_sources

        code_structure = _build_structure_summary_from_sources(sources) or ""
        if code_structure:
            click.echo("🔍 --source의 코드 저장소 구조를 미리 분석했습니다(목차 설계에 반영).")

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
    toc_md = design_toc(proposal_md=proposal_md, code_structure=code_structure)
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
    results = run_batch_draft(
        targets, store, llm, project_dir, top_k=top_k, min_coverage=min_coverage,
        check_package=check_package, execute_examples=execute_examples,
    )
    _print_batch_summary(results)
    click.echo(f"\n   완료. {project_dir} 에서 결과를 확인하세요.")
