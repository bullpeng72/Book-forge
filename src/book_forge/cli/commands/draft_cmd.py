"""`book-forge draft` — RAG 보조 챕터 초안 생성 (옵션, [rag] extra 필요).

일반 능력 A(소스 어댑터)·B(콘텐츠 유형 분기)·C(근거 검증 계층)·D(실증 가능성
게이트)·F(대안 제안)가 전부 이 명령에서 만난다:
  - A: --source는 PDF/코드 저장소 디렉토리/텍스트 파일/http(s):// URL을 자동 판별해 받는다.
  - B: 챕터의 content_type이 reference_table/diagram이면 전용 생성기로 분기한다.
  - C: 생성 전 소스 커버리지(코사인 유사도)를 점검하고, 생성 직후 Gate 점수를
       CLI에 바로 보여준다(book-forge gate를 따로 안 돌려도 됨).
  - D: content_type이 exercise/diagram(실증이 필요한 유형)이면 생성 전
       커버리지 임계값을 더 엄격하게 적용하고(C의 메커니즘 재사용), 생성 후에는
       demonstration_verifier.py가 exercise(코드 문법)·diagram(mermaid 구조)·
       reference_table(소스-표 값 대조)을 정적으로 검증해 CLI/배치 요약에
       즉시 노출한다(agent-evaluator의 Gate 점수와는 별개의 Book-forge 자체
       신호 — 참고용, 빌드를 막지 않음).
  - F: 커버리지가 낮으면 AlternativeSuggesterAgent가 대안을 제안한다.
  - C(확장): --check-package를 주면 본문이 언급한 import/백틱 심볼이 실제로
       그 패키지에 존재하는지 code_consistency_checker.py가 정적으로 대조한다
       (LLM 미호출, content_type과 무관하게 동작 — 옵트인, 기본은 검사 없음).

--all(배치 모드) vs 단일 챕터 모드는 낮은 커버리지 처리 정책이 다르다 — 이건
의도된 설계다: 단일 모드는 "저자가 지금 이 화면 앞에 있다"고 가정해 F의 대안을
보여주고 진행/취소를 직접 묻는다. --all은 사람이 결과를 나중에 확인한다고
가정해, 낮은 커버리지 챕터는 LLM 호출 없이(대안 생성 비용도 아낌) 건너뛰고
배치 종료 시 요약에만 남긴다 — 자동화할수록 "무엇을 건너뛰었는지 명확히
보고"가 "생성을 억지로 밀어붙이지 않는 것"보다 중요해진다는 판단.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import click

from book_forge.agents.demonstration_verifier import VerificationResult, verify_demonstration
from book_forge.cli.project_utils import load_book_config
from book_forge.config import load_config
from book_forge.eval.gate_summary import format_gate_line, load_gate_scores
from book_forge.eval.monitor import build_book_monitor
from book_forge.exceptions import BookForgeError
from book_forge.llm.provider import create_llm
from book_forge.publish.toc_loader import ResolvedChapter, load_toc

_STUB_MARKER = "TODO: 이 챕터를 집필하세요"

# D: 실증이 필요한 콘텐츠 유형은 서술형보다 엄격한 커버리지 기준을 적용한다.
_STRICT_CONTENT_TYPES = {"exercise", "diagram"}
_STRICT_COVERAGE_BONUS = 0.15


class _SourcePath(click.ParamType):
    """--source 값 검증 — http(s):// URL은 그대로 통과, 그 외엔 실제 존재하는 로컬 경로여야 한다."""

    name = "source"
    _path_type = click.Path(exists=True)

    def convert(self, value, param, ctx):
        if value.startswith(("http://", "https://")):
            return value
        return self._path_type.convert(value, param, ctx)


@dataclass
class ChapterDraftResult:
    chapter_no: int
    chapter_title: str
    status: str  # "created" | "skipped_low_coverage" | "cancelled"
    avg_coverage: Optional[float] = None
    gate_c_score: Optional[float] = None
    verification: Optional[VerificationResult] = None
    code_consistency: Optional[VerificationResult] = None


def _is_draftable(rc: ResolvedChapter, force: bool) -> bool:
    if force:
        return True
    if not rc.exists:
        return True
    return _STUB_MARKER in rc.path.read_text(encoding="utf-8")


def collect_sources_into_store(project_dir: Path, sources: tuple):
    """소스를 프로젝트 영속 지식창고에 청크·임베딩해 누적한다.

    book-forge draft와 book-forge new --source가 공유하는 로직 — 복제하지 않고
    이 함수 하나로 유지한다.
    """
    from book_forge.knowledge.sources import load_source
    from book_forge.knowledge.store import KnowledgeStore, default_store_path

    store_path = default_store_path(project_dir)
    if store_path.is_file():
        store = KnowledgeStore.load(store_path)
        click.echo(f"📚 기존 지식창고 불러옴: {len(store)}개 청크")
    else:
        store = KnowledgeStore()

    click.echo(f"📚 소스 {len(sources)}개 수집·임베딩 중 (Ollama)...")
    for src in sources:
        chunks = load_source(src)
        store.add(chunks)
        click.echo(f"  {src}: {len(chunks)}개 청크")
    store.save(store_path)
    return store


def run_batch_draft(
    targets: list[ResolvedChapter],
    store,
    llm,
    project_dir: Path,
    *,
    top_k: int = 8,
    min_coverage: float = 0.5,
    check_package: Optional[str] = None,
) -> list["ChapterDraftResult"]:
    """미집필 챕터 목록을 순회하며 배치 정책(저커버리지 스킵+리포트)으로 RAG 초안을 생성한다.

    book-forge draft --all과 book-forge new --source가 공유하는 로직.
    """
    results: list[ChapterDraftResult] = []
    for rc in targets:
        click.echo(f"\n── Chapter {rc.spec.chapter_no}: {rc.spec.chapter_title} ──")
        results.append(
            _draft_one_chapter(
                rc, store, llm, project_dir,
                top_k=top_k, min_coverage=min_coverage,
                yes=False, batch_mode=True, check_package=check_package,
            )
        )
    return results


@click.command()
@click.argument("slug")
@click.argument("chapter_no", type=int, required=False, default=None)
@click.option("--all", "draft_all", is_flag=True, help="목차의 미집필 챕터 전부를 일괄 생성 (배치 모드)")
@click.option(
    "--source", "sources", multiple=True,
    type=_SourcePath(),
    help="RAG 소스 경로 — PDF/코드 저장소 디렉토리/텍스트 파일/http(s):// URL (여러 번 지정 가능, 최소 1개 필수)",
)
@click.option("--top-k", type=int, default=8, show_default=True, help="검색할 소스 청크 수")
@click.option(
    "--min-coverage", type=float, default=0.5, show_default=True,
    help="생성 전 평균 소스 유사도 임계값 (참고용 휴리스틱 — 임베딩 모델마다 절대값 신뢰도가 다를 수 있음)",
)
@click.option("--yes", "-y", is_flag=True, help="[단일 모드] 커버리지가 낮아도 확인 없이 진행")
@click.option("--force", is_flag=True, help="기존에 집필된 챕터도 덮어쓰기")
@click.option(
    "--check-package", default=None,
    help="본문이 언급한 import/백틱 심볼이 이 패키지에 실제로 존재하는지 정적으로 대조"
         "(예: --check-package agent_evaluator, 옵트인, 미지정 시 검사 없음)",
)
def draft(
    slug: str,
    chapter_no: Optional[int],
    draft_all: bool,
    sources: tuple,
    top_k: int,
    min_coverage: float,
    yes: bool,
    force: bool,
    check_package: Optional[str],
) -> None:
    """SLUG 프로젝트의 CHAPTER_NO 챕터(또는 --all로 전체 미집필 챕터)를
    --source 기반 RAG로 초안 생성한다."""
    if draft_all and chapter_no is not None:
        raise click.ClickException("챕터 번호와 --all은 함께 쓸 수 없습니다.")
    if not draft_all and chapter_no is None:
        raise click.ClickException("챕터 번호를 지정하거나, 전체 일괄 생성은 --all을 쓰세요.")

    try:
        import numpy  # noqa: F401
        import pypdf  # noqa: F401
    except ImportError as exc:
        # book_forge.knowledge.* 모듈 자체는 pypdf/numpy를 함수 내부에서만 지연
        # import하므로, 모듈을 그냥 import하는 것만으로는 [rag] extra 미설치를
        # 잡아내지 못한다 — 실제 옵션 의존성을 직접 확인해야 한다.
        raise click.ClickException(
            'RAG 기능에 필요한 패키지가 없습니다. pip install -e ".[rag]" 로 설치하세요.'
        ) from exc

    if not sources:
        raise click.ClickException("--source를 최소 1개 지정해야 합니다 (PDF/디렉토리/텍스트 파일/URL).")

    load_config()
    config = load_book_config(slug)
    chapters = load_toc(config.project_dir)

    if draft_all:
        targets = [rc for rc in chapters if _is_draftable(rc, force)]
        if not targets:
            click.echo("모든 챕터가 이미 집필되어 있습니다. (--force로 덮어쓸 수 있습니다)")
            return
        click.echo(f"🗂  일괄 생성 대상: {len(targets)}개 챕터")
    else:
        rc = next((c for c in chapters if c.spec.chapter_no == chapter_no), None)
        if rc is None:
            raise click.ClickException(f"챕터 번호 {chapter_no}를 목차에서 찾을 수 없습니다.")
        if rc.exists and not force:
            existing = rc.path.read_text(encoding="utf-8")
            if _STUB_MARKER not in existing:
                raise click.ClickException(
                    f"챕터에 이미 내용이 있습니다: {rc.path}\n덮어쓰려면 --force를 쓰세요."
                )
        targets = [rc]

    # E + A: 프로젝트 영속 지식창고에 소스를 청크·임베딩해 누적(PDF/코드 저장소/텍스트/URL 자동 판별).
    store = collect_sources_into_store(config.project_dir, sources)

    try:
        llm = create_llm()
    except BookForgeError as exc:
        raise click.ClickException(str(exc)) from exc

    if draft_all:
        results = run_batch_draft(
            targets, store, llm, config.project_dir, top_k=top_k, min_coverage=min_coverage,
            check_package=check_package,
        )
        _print_batch_summary(results)
    else:
        _draft_one_chapter(
            targets[0], store, llm, config.project_dir,
            top_k=top_k, min_coverage=min_coverage, yes=yes, batch_mode=False,
            check_package=check_package,
        )


def _draft_one_chapter(
    rc: ResolvedChapter,
    store,
    llm,
    project_dir: Path,
    *,
    top_k: int,
    min_coverage: float,
    yes: bool,
    batch_mode: bool,
    check_package: Optional[str] = None,
) -> ChapterDraftResult:
    result = ChapterDraftResult(
        chapter_no=rc.spec.chapter_no, chapter_title=rc.spec.chapter_title, status="cancelled"
    )

    click.echo(f"🔍 '{rc.spec.chapter_title}' 관련 청크 검색 중 (top_k={top_k})...")
    scored = store.query_with_scores(rc.spec.chapter_title, top_k=top_k)
    if not scored:
        click.echo("  검색된 소스 청크가 없습니다 — 건너뜁니다.")
        return result
    avg_score = sum(s for _, s in scored) / len(scored)
    result.avg_coverage = avg_score
    sources_text = "\n\n---\n\n".join(chunk for chunk, _ in scored)

    monitor = build_book_monitor(output_dir=str(project_dir / "eval_results"))

    # D: 실증이 필요한 유형(exercise/diagram)은 C의 임계값을 그대로 쓰되 더 엄격하게.
    effective_min_coverage = min_coverage
    if rc.spec.content_type in _STRICT_CONTENT_TYPES:
        effective_min_coverage = min_coverage + _STRICT_COVERAGE_BONUS
        click.echo(
            f"   (이 챕터는 '{rc.spec.content_type}' 유형이라 커버리지 기준을 "
            f"{effective_min_coverage:.2f}로 엄격하게 적용합니다)"
        )
    click.echo(f"   평균 소스 유사도: {avg_score:.3f} (참고용 휴리스틱)")

    if avg_score < effective_min_coverage:
        if batch_mode:
            # 배치 모드: LLM 호출(대안 생성) 없이 건너뛰고 요약에만 남긴다.
            click.echo(
                f"⏭️  건너뜀 — 커버리지 {avg_score:.3f} < 임계값 {effective_min_coverage:.2f}"
            )
            result.status = "skipped_low_coverage"
            return result

        if not yes:
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
                result.status = "cancelled"
                return result

    # B: 콘텐츠 유형에 따라 전용 생성기로 분기.
    if rc.spec.content_type == "reference_table":
        from book_forge.agents.reference_table import build_generate_reference_table

        click.echo("📊 레퍼런스 표 생성 중 (LLM 호출)...")
        generate = build_generate_reference_table(llm, monitor)
        draft_md = generate(
            chapter_title=rc.spec.chapter_title,
            chapter_no=rc.spec.chapter_no,
            sources=sources_text,
            ground_truth=rc.spec.chapter_title,
        )
    elif rc.spec.content_type == "diagram":
        from book_forge.agents.diagram_generator import build_generate_diagram

        click.echo("📈 다이어그램 생성 중 (LLM 호출)...")
        generate = build_generate_diagram(llm, monitor)
        draft_md = generate(
            chapter_title=rc.spec.chapter_title,
            chapter_no=rc.spec.chapter_no,
            sources=sources_text,
            ground_truth=rc.spec.chapter_title,
        )
    else:
        from book_forge.agents.chapter_drafter import build_draft_chapter

        click.echo("✍️  초안 생성 중 (LLM 호출)...")
        generate = build_draft_chapter(llm, monitor)
        draft_md = generate(
            chapter_title=rc.spec.chapter_title,
            chapter_no=rc.spec.chapter_no,
            sources=sources_text,
            ground_truth=rc.spec.chapter_title,
            content_type=rc.spec.content_type,
        )

    rc.path.parent.mkdir(parents=True, exist_ok=True)
    rc.path.write_text(draft_md, encoding="utf-8")
    result_path = monitor.save_to_file(f"draft_ch{rc.spec.chapter_no:02d}")
    click.echo(f"✅ 완료: {rc.path}")

    result.status = "created"
    result.gate_c_score = _print_gate_summary(result_path)
    result.verification = _print_verification(rc.spec.content_type, draft_md, sources_text)
    if check_package:
        result.code_consistency = _print_code_consistency(check_package, draft_md)
    return result


def _print_gate_summary(result_path) -> Optional[float]:
    try:
        scores = load_gate_scores(Path(result_path))
    except (OSError, ValueError):
        return None
    click.echo("\n📈 이 초안의 Gate 점수 (참고용 — 전체 판정은 book-forge gate로):")
    for gate_key in "ABCDEFG":
        click.echo(format_gate_line(gate_key, scores.get(gate_key)))
    c_score = scores.get("C")
    if c_score is not None and c_score < 0.7:
        click.echo("\n⚠️  Gate C(신뢰성) 점수가 낮습니다 — 근거 없는 서술이 섞였을 수 있습니다. 검토하세요.")
    return c_score


def _print_verification(
    content_type: str, draft_md: str, sources_text: str
) -> Optional[VerificationResult]:
    """D(실증 가능성 게이트) 강화 — exercise/diagram/reference_table 생성 결과를
    정적으로 검증하고 CLI에 즉시 노출한다. narrative 등 대응 검증기가 없는
    유형은 아무것도 출력하지 않는다(기존 Gate C/D와 마찬가지로 참고용이며,
    실패해도 초안 자체는 이미 저장된 상태를 유지한다)."""
    result = verify_demonstration(content_type, draft_md, sources_text)
    if result is None:
        return None
    if result.passed:
        click.echo(f"🔬 실증 가능성 검증: ✅ {result.detail}")
    else:
        click.echo(f"🔬 실증 가능성 검증: ⚠️  {result.detail}")
        for issue in result.issues:
            click.echo(f"     → {issue}")
    return result


def _print_code_consistency(check_package: str, draft_md: str) -> VerificationResult:
    """C(근거 검증 계층) 확장 — 본문이 언급한 import/백틱 심볼이 실제로
    check_package에 존재하는지 정적으로 대조하고 CLI에 즉시 노출한다.
    LLM을 호출하지 않으며, 실패해도 초안 저장을 막지 않는다(참고용)."""
    from book_forge.agents.code_consistency_checker import verify_code_consistency

    result = verify_code_consistency(draft_md, target_package=check_package)
    if result.passed:
        click.echo(f"🔗 코드-본문 정합성: ✅ {result.detail}")
    else:
        click.echo(f"🔗 코드-본문 정합성: ⚠️  {result.detail}")
        for issue in result.issues:
            click.echo(f"     → {issue}")
    return result


def _print_batch_summary(results: list[ChapterDraftResult]) -> None:
    click.echo("\n" + "═" * 50)
    click.echo("📋 일괄 생성 요약")
    click.echo("═" * 50)
    for r in results:
        label = f"Ch{r.chapter_no:02d} {r.chapter_title}"
        if r.status == "created":
            if r.gate_c_score is None:
                click.echo(f"  · {label} (Gate C: N/A)")
            elif r.gate_c_score >= 0.7:
                click.echo(f"  ✅ {label} (Gate C: {r.gate_c_score:.3f})")
            else:
                click.echo(f"  ⚠️  {label} (Gate C: {r.gate_c_score:.3f}) — 검토 필요")
            if r.verification is not None and not r.verification.passed:
                click.echo(f"       🔬 실증 검증 실패: {r.verification.detail}")
            if r.code_consistency is not None and not r.code_consistency.passed:
                click.echo(f"       🔗 코드-본문 정합성 실패: {r.code_consistency.detail}")
        elif r.status == "skipped_low_coverage":
            click.echo(f"  ⏭️  {label} — 건너뜀 (커버리지 {r.avg_coverage:.3f} 미달)")
        else:
            click.echo(f"  ✋ {label} — 취소됨")

    created = sum(1 for r in results if r.status == "created")
    skipped = sum(1 for r in results if r.status == "skipped_low_coverage")
    verification_failed = sum(
        1 for r in results if r.verification is not None and not r.verification.passed
    )
    consistency_failed = sum(
        1 for r in results if r.code_consistency is not None and not r.code_consistency.passed
    )
    click.echo(f"\n생성 {created}개, 건너뜀 {skipped}개 (총 {len(results)}개)")
    if skipped:
        click.echo(
            "건너뛴 챕터는 --source를 추가하거나 book-forge plan --revise로 "
            "범위를 조정한 뒤 다시 시도하세요."
        )
    if verification_failed:
        click.echo(f"🔬 실증 가능성 검증 실패 {verification_failed}개 — 위 목록에서 검토하세요.")
    if consistency_failed:
        click.echo(f"🔗 코드-본문 정합성 실패 {consistency_failed}개 — 위 목록에서 검토하세요.")
