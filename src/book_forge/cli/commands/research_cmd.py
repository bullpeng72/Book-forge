"""`book-forge research` — 챕터 제목에서 검색 쿼리를 생성하고 실제로 웹을
검색해 후보 URL을 모은 뒤, 저자가 확인한 것만 프로젝트 지식창고에 추가한다
(일반 능력 N 전체 범위 — SPEC.md 항목 N).

기존 --source(A)는 저자가 URL을 직접 알아야만 쓸 수 있었다 — 이 명령은 "이
주제에 맞는 자료를 찾아온다"는 검색 단계를 자동화한다. 검색 결과를 무조건
신뢰하지 않고 항상 저자에게 후보 목록(제목+요약+URL)을 보여주고 포함 여부를
직접 고르게 한다 — book-forge plan의 승인 루프와 같은 "최종 판단은 저자"
원칙이다(자동 신뢰도 평가/1차·2차 출처 분류 같은 판정 로직은 이 범위에
포함하지 않았다 — LLM이 안정적으로 못 하는 판단을 억지로 자동화하기보다,
저자가 제목/요약을 직접 훑어보고 고르는 편이 더 신뢰할 수 있다는 판단).

채택된 URL은 draft_cmd.py의 collect_sources_into_store()를 그대로 재사용해
지식창고에 추가한다(URL 소스 처리 로직 재사용, 새 로직 없음) — 이후
book-forge draft를 --source 없이 실행하면(draft_cmd.py가 기존 지식창고를
그대로 쓰도록 확장됨) 이 소스들도 검색 대상에 포함되고, 실제로 인용되면
일반 능력 N(범위 축소판)의 "## 참고 자료" 섹션에 자동으로 나타난다.
"""
from __future__ import annotations

import click

from book_forge.agents.research_agent import build_generate_search_queries, parse_search_queries
from book_forge.cli.commands.draft_cmd import collect_sources_into_store
from book_forge.cli.project_utils import load_book_config
from book_forge.config import load_config
from book_forge.eval.monitor import build_book_monitor
from book_forge.exceptions import BookForgeError
from book_forge.knowledge.web_search import SearchResult, search_web
from book_forge.llm.provider import create_llm
from book_forge.publish.toc_loader import load_toc


def _select_candidates(candidates: list[SearchResult], raw_choice: str) -> list[SearchResult]:
    """"1,3" 같은 번호 목록을 후보로 매핑한다. 빈 입력=전체, "0"=전체 제외.

    잘못된 번호(범위 밖, 숫자 아님)는 조용히 무시한다 — plan_cmd.py의 피드백
    입력처럼, 저자 입력을 관대하게 다루는 게 CLI 대화형 흐름의 원칙이다.
    """
    stripped = raw_choice.strip()
    if not stripped:
        return candidates
    if stripped == "0":
        return []
    chosen: list[SearchResult] = []
    for part in stripped.split(","):
        part = part.strip()
        if not part.isdigit():
            continue
        idx = int(part) - 1
        if 0 <= idx < len(candidates):
            chosen.append(candidates[idx])
    return chosen


@click.command()
@click.argument("slug")
@click.argument("chapter_no", type=int)
@click.option(
    "--max-queries", type=int, default=3, show_default=True, help="생성할 검색 쿼리 최대 개수"
)
@click.option(
    "--max-results-per-query", type=int, default=5, show_default=True,
    help="쿼리 하나당 검색 결과 최대 개수",
)
@click.option("--yes", "-y", is_flag=True, help="후보 URL 전체를 확인 없이 채택")
def research(
    slug: str, chapter_no: int, max_queries: int, max_results_per_query: int, yes: bool
) -> None:
    """SLUG 프로젝트 CHAPTER_NO 챕터의 자료를 자동으로 검색해 지식창고에 추가한다."""
    load_config()
    config = load_book_config(slug)
    chapters = load_toc(config.project_dir)
    rc = next((c for c in chapters if c.spec.chapter_no == chapter_no), None)
    if rc is None:
        raise click.ClickException(f"챕터 번호 {chapter_no}를 목차에서 찾을 수 없습니다.")

    try:
        llm = create_llm()
    except BookForgeError as exc:
        raise click.ClickException(str(exc)) from exc

    monitor = build_book_monitor(output_dir=str(config.project_dir / "eval_results"))

    click.echo(f"🔎 '{rc.spec.chapter_title}' 관련 검색 쿼리 생성 중 (LLM 호출)...")
    generate_queries = build_generate_search_queries(llm, monitor)
    raw_queries = generate_queries(
        chapter_title=rc.spec.chapter_title, ground_truth=rc.spec.chapter_title
    )
    queries = parse_search_queries(raw_queries, max_queries=max_queries)
    if not queries:
        # LLM이 형식을 안 지켜도 조용히 빈 손으로 끝내지 않는다 — 챕터 제목
        # 자체를 쿼리로 대체(alternative_suggester.py의 "실패해도 결과를 낸다"
        # 원칙과 동일한 폴백 철학).
        queries = [rc.spec.chapter_title]
        click.echo("   (쿼리 생성 형식이 맞지 않아 챕터 제목을 그대로 검색어로 씁니다)")
    click.echo(f"   검색 쿼리: {', '.join(queries)}")

    candidates: list[SearchResult] = []
    seen_urls: set[str] = set()
    for query in queries:
        click.echo(f"🌐 검색 중: {query!r}")
        try:
            results = search_web(query, max_results=max_results_per_query)
        except Exception as exc:
            # DuckDuckGo가 차단했거나(비정상 트래픽 감지) HTML 구조가 바뀌었을
            # 수 있다 — 한 쿼리 실패로 전체 명령이 죽지 않고 나머지 쿼리는 계속.
            click.echo(f"   ⚠️  검색 실패 — 건너뜁니다 ({exc})")
            continue
        for r in results:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                candidates.append(r)

    if not candidates:
        click.echo(
            "\n검색 결과가 없습니다. 네트워크 상태를 확인하거나 "
            "book-forge draft ... --source <URL>로 직접 지정하세요."
        )
        return

    click.echo(f"\n📋 후보 {len(candidates)}개:")
    for i, r in enumerate(candidates, 1):
        click.echo(f"  {i}. {r.title}")
        click.echo(f"     {r.url}")
        if r.snippet:
            click.echo(f"     {r.snippet[:120]}")

    if yes:
        chosen = candidates
    else:
        raw_choice = click.prompt(
            "\n포함할 후보 번호 (쉼표로 구분, Enter=전체 포함, 0=아무것도 포함 안 함)",
            default="", show_default=False,
        )
        chosen = _select_candidates(candidates, raw_choice)

    if not chosen:
        click.echo("채택된 URL이 없습니다. 지식창고를 변경하지 않았습니다.")
        return

    urls = tuple(r.url for r in chosen)
    click.echo(f"\n📚 채택된 {len(urls)}개 URL을 지식창고에 추가하는 중...")
    collect_sources_into_store(config.project_dir, urls)

    result_path = monitor.save_to_file(f"research_ch{chapter_no:02d}")
    click.echo(f"\n✅ 완료. 계측 결과: {result_path}")
    click.echo(f"   다음: book-forge draft {slug} {chapter_no} 로 초안을 생성하세요")
    click.echo("   (--source 없이 호출해도 방금 채운 지식창고를 그대로 씁니다).")
