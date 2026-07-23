"""`book-forge review` — 다관점 리뷰어 패널로 이미 집필된 챕터를 검토한다.

일반 능력 G(자기실증 예제) — agents/review_panel.py의 감독자-작업자 패턴을
실행하는 얇은 CLI 래퍼다. 새 판정 로직은 없다: 여기서는 챕터 파일을 읽고
run_review_panel()을 호출해 결과를 출력할 뿐이다.
"""
from __future__ import annotations

import click

from book_forge.cli.project_utils import load_book_config
from book_forge.config import load_config
from book_forge.exceptions import BookForgeError
from book_forge.llm.provider import create_llm
from book_forge.publish.toc_loader import load_toc


@click.command()
@click.argument("slug")
@click.argument("chapter_no", type=int)
def review(slug: str, chapter_no: int) -> None:
    """SLUG 프로젝트의 CHAPTER_NO 챕터를 정확성/가독성 검토자 패널로 검토한다."""
    load_config()
    config = load_book_config(slug)
    chapters = load_toc(config.project_dir)

    rc = next((c for c in chapters if c.spec.chapter_no == chapter_no), None)
    if rc is None:
        raise click.ClickException(f"챕터 번호 {chapter_no}를 목차에서 찾을 수 없습니다.")
    if not rc.exists:
        raise click.ClickException(f"챕터 파일이 없습니다: {rc.path} (아직 집필되지 않았습니다)")

    chapter_md = rc.path.read_text(encoding="utf-8")

    try:
        llm = create_llm()
    except BookForgeError as exc:
        raise click.ClickException(str(exc)) from exc

    from book_forge.agents.review_panel import run_review_panel
    from book_forge.eval.monitor import build_book_monitor

    monitor = build_book_monitor(output_dir=str(config.project_dir / "eval_results"))

    click.echo(f"🧑‍⚖️  '{rc.spec.chapter_title}' 다관점 검토 중 (LLM 호출 3회)...")
    result = run_review_panel(
        chapter_title=rc.spec.chapter_title, chapter_md=chapter_md, llm=llm, monitor=monitor,
        chapter_no=chapter_no,
    )

    click.echo()
    for v in result.reviewer_verdicts:
        icon = "✅" if v.verdict == "approve" else "⚠️ "
        click.echo(f"{icon} [{v.role_name}] {v.verdict.upper()}: {v.reason}")

    click.echo(f"\n🤝 검토자 간 합의도: {result.consensus_score:.2f}")
    final_icon = "✅" if result.final_verdict == "approve" else "⚠️ "
    click.echo(f"\n{final_icon} 최종 판정: {result.final_verdict.upper()}")
    click.echo(f"   {result.final_summary}")

    monitor.save_to_file(f"review_ch{chapter_no:02d}")
    click.echo(
        f"\n📊 이 검토가 Gate F(다중 에이전트 협업) 지표를 채웁니다 — "
        f"book-forge gate {slug} 로 전체 판정을 확인하세요."
    )
