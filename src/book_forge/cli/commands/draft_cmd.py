"""`book-forge draft` — RAG 보조 챕터 초안 생성 (옵션, [rag] extra 필요).

일반 능력 A(소스 어댑터)·B(콘텐츠 유형 분기)·C(근거 검증 계층)·D(실증 가능성
게이트)·F(대안 제안)가 전부 이 명령에서 만난다:
  - A: --source는 PDF/코드 저장소 디렉토리/텍스트 파일을 자동 판별해 받는다.
  - B: 챕터의 content_type이 reference_table이면 전용 생성기로 분기한다.
  - C: 생성 전 소스 커버리지(코사인 유사도)를 점검하고, 생성 직후 Gate 점수를
       CLI에 바로 보여준다(book-forge gate를 따로 안 돌려도 됨).
  - D: content_type이 exercise/diagram(실증이 필요한 유형)이면 커버리지
       임계값을 더 엄격하게 적용한다 — C의 메커니즘을 재사용할 뿐 별도 판정
       로직을 새로 만들지 않는다.
  - F: 커버리지가 낮으면 AlternativeSuggesterAgent가 대안을 제안하고, 저자가
       그대로 진행할지 취소할지 선택한다(자동 차단이 아니라 자문).
"""
from __future__ import annotations

from pathlib import Path

import click

from book_forge.cli.project_utils import load_book_config
from book_forge.config import load_config
from book_forge.eval.gate_summary import format_gate_line, load_gate_scores
from book_forge.eval.monitor import build_book_monitor
from book_forge.exceptions import BookForgeError
from book_forge.llm.provider import create_llm
from book_forge.publish.toc_loader import load_toc

_STUB_MARKER = "TODO: 이 챕터를 집필하세요"

# D: 실증이 필요한 콘텐츠 유형은 서술형보다 엄격한 커버리지 기준을 적용한다.
_STRICT_CONTENT_TYPES = {"exercise", "diagram"}
_STRICT_COVERAGE_BONUS = 0.15


@click.command()
@click.argument("slug")
@click.argument("chapter_no", type=int)
@click.option(
    "--source", "sources", multiple=True,
    type=click.Path(exists=True),
    help="RAG 소스 경로 — PDF/코드 저장소 디렉토리/텍스트 파일 (여러 번 지정 가능, 최소 1개 필수)",
)
@click.option("--top-k", type=int, default=8, show_default=True, help="검색할 소스 청크 수")
@click.option(
    "--min-coverage", type=float, default=0.5, show_default=True,
    help="생성 전 평균 소스 유사도 임계값 (참고용 휴리스틱 — 임베딩 모델마다 절대값 신뢰도가 다를 수 있음)",
)
@click.option("--yes", "-y", is_flag=True, help="커버리지가 낮아도 확인 없이 진행")
@click.option("--force", is_flag=True, help="기존에 집필된 챕터도 덮어쓰기")
def draft(
    slug: str,
    chapter_no: int,
    sources: tuple,
    top_k: int,
    min_coverage: float,
    yes: bool,
    force: bool,
) -> None:
    """SLUG 프로젝트의 CHAPTER_NO 챕터를 --source 기반 RAG로 초안 생성한다."""
    try:
        from book_forge.knowledge.sources import load_source
        from book_forge.knowledge.store import KnowledgeStore, default_store_path
    except ImportError as exc:
        raise click.ClickException(
            'RAG 기능에 필요한 패키지가 없습니다. pip install -e ".[rag]" 로 설치하세요.'
        ) from exc

    if not sources:
        raise click.ClickException("--source를 최소 1개 지정해야 합니다 (PDF/디렉토리/텍스트 파일).")

    load_config()
    config = load_book_config(slug)

    chapters = load_toc(config.project_dir)
    rc = next((c for c in chapters if c.spec.chapter_no == chapter_no), None)
    if rc is None:
        raise click.ClickException(f"챕터 번호 {chapter_no}를 목차에서 찾을 수 없습니다.")

    if rc.exists and not force:
        existing = rc.path.read_text(encoding="utf-8")
        if _STUB_MARKER not in existing:
            raise click.ClickException(
                f"챕터에 이미 내용이 있습니다: {rc.path}\n덮어쓰려면 --force를 쓰세요."
            )

    # E: 프로젝트 영속 지식창고 — draft가 쌓은 소스를 book-forge chat이 이어서 쓴다.
    store_path = default_store_path(config.project_dir)
    if store_path.is_file():
        store = KnowledgeStore.load(store_path)
        click.echo(f"📚 기존 지식창고 불러옴: {len(store)}개 청크")
    else:
        store = KnowledgeStore()

    # A: 소스 어댑터 — PDF/디렉토리(코드 저장소)/텍스트 파일을 자동 판별.
    click.echo(f"📚 소스 {len(sources)}개 수집·임베딩 중 (Ollama)...")
    for src in sources:
        chunks = load_source(Path(src))
        store.add(chunks)
        click.echo(f"  {src}: {len(chunks)}개 청크")
    store.save(store_path)

    click.echo(f"🔍 '{rc.spec.chapter_title}' 관련 청크 검색 중 (top_k={top_k})...")
    scored = store.query_with_scores(rc.spec.chapter_title, top_k=top_k)
    if not scored:
        raise click.ClickException("검색된 소스 청크가 없습니다 — 소스 내용을 확인하세요.")
    avg_score = sum(s for _, s in scored) / len(scored)
    sources_text = "\n\n---\n\n".join(chunk for chunk, _ in scored)

    try:
        llm = create_llm()
    except BookForgeError as exc:
        raise click.ClickException(str(exc)) from exc

    monitor = build_book_monitor(output_dir=str(config.project_dir / "eval_results"))

    # D: 실증이 필요한 유형(exercise/diagram)은 C의 임계값을 그대로 쓰되 더 엄격하게.
    effective_min_coverage = min_coverage
    if rc.spec.content_type in _STRICT_CONTENT_TYPES:
        effective_min_coverage = min_coverage + _STRICT_COVERAGE_BONUS
        click.echo(
            f"   (이 챕터는 '{rc.spec.content_type}' 유형이라 커버리지 기준을 "
            f"{effective_min_coverage:.2f}로 엄격하게 적용합니다)"
        )
    click.echo(f"   평균 소스 유사도: {avg_score:.3f} (참고용 휴리스틱)")

    # C(사전 점검) → F(대안 제안): 커버리지가 낮으면 경고하고 대안을 제시한다.
    if avg_score < effective_min_coverage and not yes:
        click.echo(
            f"\n⚠️  소스 커버리지가 낮습니다(평균 {avg_score:.3f} < 임계값 "
            f"{effective_min_coverage:.2f}). 근거 없는 서술이 섞일 위험이 있습니다."
        )
        from book_forge.agents.alternative_suggester import (
            build_suggest_alternatives,
            parse_alternatives,
        )

        click.echo("💡 대안을 생성하는 중...")
        suggest_alternatives = build_suggest_alternatives(llm, monitor)
        raw = suggest_alternatives(
            chapter_title=rc.spec.chapter_title,
            reason=f"평균 소스 유사도 {avg_score:.3f}로 낮음 (top_k={top_k}개 청크 검색)",
            ground_truth=rc.spec.chapter_title,
        )
        alternatives = parse_alternatives(raw)
        if alternatives:
            click.echo("\n제안된 대안:")
            for i, (summary, reason) in enumerate(alternatives, 1):
                click.echo(f"  {i}. {summary}")
                if reason:
                    click.echo(f"     → {reason}")

        if not click.confirm("\n그래도 이대로 초안을 생성하시겠습니까?", default=False):
            click.echo(
                "취소했습니다. --source를 추가하거나, 위 대안을 참고해 "
                "book-forge plan --revise 로 챕터 범위를 조정한 뒤 다시 시도하세요."
            )
            raise SystemExit(0)

    # B: 콘텐츠 유형에 따라 전용 생성기로 분기.
    if rc.spec.content_type == "reference_table":
        from book_forge.agents.reference_table import build_generate_reference_table

        click.echo("📊 레퍼런스 표 생성 중 (LLM 호출)...")
        generate = build_generate_reference_table(llm, monitor)
    else:
        from book_forge.agents.chapter_drafter import build_draft_chapter

        click.echo("✍️  초안 생성 중 (LLM 호출)...")
        generate = build_draft_chapter(llm, monitor)

    draft_md = generate(
        chapter_title=rc.spec.chapter_title,
        chapter_no=chapter_no,
        sources=sources_text,
        ground_truth=rc.spec.chapter_title,
    )

    rc.path.parent.mkdir(parents=True, exist_ok=True)
    rc.path.write_text(draft_md, encoding="utf-8")
    result_path = monitor.save_to_file("draft")
    click.echo(f"✅ 완료: {rc.path}")

    # C(사후 노출): eval_results/ 를 따로 열어보지 않아도 즉시 확인 가능하게.
    _print_gate_summary(result_path)


def _print_gate_summary(result_path) -> None:
    try:
        scores = load_gate_scores(Path(result_path))
    except (OSError, ValueError):
        return
    click.echo("\n📈 이 초안의 Gate 점수 (참고용 — 전체 판정은 book-forge gate로):")
    for gate_key in "ABCDEFG":
        click.echo(format_gate_line(gate_key, scores.get(gate_key)))
    c_score = scores.get("C")
    if c_score is not None and c_score < 0.7:
        click.echo("\n⚠️  Gate C(신뢰성) 점수가 낮습니다 — 근거 없는 서술이 섞였을 수 있습니다. 검토하세요.")
