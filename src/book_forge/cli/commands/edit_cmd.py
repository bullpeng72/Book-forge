"""`book-forge edit` — 웹 기반 도서 편집기 (Part/Chapter 트리 + 이미지 갤러리)."""
from __future__ import annotations

import click

from book_forge.cli.project_utils import load_book_config


@click.command()
@click.argument("slug")
@click.option("--port", type=int, default=5858, help="서버 포트 (기본: 5858)")
@click.option("--no-browser", is_flag=True, help="브라우저 자동 오픈 비활성화")
def edit(slug: str, port: int, no_browser: bool) -> None:
    """SLUG 프로젝트를 웹 에디터로 연다."""
    from book_forge.editor.server import run_editor  # lazy import — [serve] extra(flask)

    config = load_book_config(slug)
    click.echo(f"📖 Book-forge 편집기: http://localhost:{port}")
    click.echo(f"   프로젝트: {config.project_dir}")
    click.echo("   종료: Ctrl+C")
    run_editor(config, port=port, open_browser=not no_browser)
