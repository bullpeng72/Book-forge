"""`book-forge knowledge status`/`reset` — 지식창고(RAG 캐시) 라이프사이클 관리(Spec J).

`KnowledgeStore.add()`는 중복 제거가 없고, `collect_sources_into_store()`(draft_cmd.py)는
항상 기존 store.json을 불러와 append만 한다 — 소스를 잘못 골랐을 때 되돌릴 방법이
"파일을 직접 rm"밖에 없었다(실전 6챕터 집필 중 겪은 문제, SPEC.md 항목 J: OpenCode
플러그인 TS 파일 하나가 한 번 섞여 들어간 뒤 그 심볼들이 이후 여러 챕터의 검색
결과를 계속 오염시켰다). 이 명령은 그 수동 삭제 작업을 감싼 얇은 CLI 래퍼일 뿐,
새 판정 로직은 없다 — status는 lifecycle.summarize_store(), reset은 파일 삭제뿐이다.
"""
from __future__ import annotations

import click

from book_forge.cli.project_utils import resolve_project_dir
from book_forge.knowledge.lifecycle import summarize_store
from book_forge.knowledge.store import KnowledgeStore, default_store_path


@click.group(name="knowledge")
def knowledge() -> None:
    """지식창고(RAG 소스 캐시) 상태 확인/초기화."""


@knowledge.command(name="status")
@click.argument("slug")
def status(slug: str) -> None:
    """소스별 청크 분포를 보여준다."""
    project_dir = resolve_project_dir(slug)
    store_path = default_store_path(project_dir)
    if not store_path.is_file():
        click.echo(f"지식창고가 아직 없습니다: {store_path}")
        return
    store = KnowledgeStore.load(store_path)
    click.echo(f"📚 총 {len(store)}개 청크 ({store_path})")
    for label, count in summarize_store(store):
        click.echo(f"  {label}: {count}개 청크")


@knowledge.command(name="reset")
@click.argument("slug")
@click.option("--yes", is_flag=True, help="확인 프롬프트 없이 즉시 삭제")
def reset(slug: str, yes: bool) -> None:
    """지식창고를 통째로 삭제한다(RAG 캐시일 뿐 저작 콘텐츠는 영향 없음)."""
    project_dir = resolve_project_dir(slug)
    store_path = default_store_path(project_dir)
    if not store_path.is_file():
        click.echo(f"지식창고가 이미 없습니다: {store_path}")
        return
    if not yes:
        click.confirm(
            f"{store_path}를 삭제합니다 — 되돌릴 수 없습니다. 계속할까요?", abort=True
        )
    store_path.unlink()
    click.echo(f"🗑  지식창고를 삭제했습니다: {store_path}")
