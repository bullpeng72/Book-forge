"""`book-forge build html|pdf|slides` — MD → HTML/PDF/발표자료 산출물 생성."""
from __future__ import annotations

from typing import Optional

import click

from book_forge.cli.project_utils import load_book_config
from book_forge.config import load_config
from book_forge.eval.monitor import build_book_monitor
from book_forge.exceptions import BookForgeError
from book_forge.llm.provider import create_llm
from book_forge.publish.epub_builder import build_epub as _build_epub
from book_forge.publish.html_builder import build_html as _build_html
from book_forge.publish.pdf_builder import build_pdf as _build_pdf
from book_forge.publish.slide_builder import build_slides as _build_slides


@click.group()
def build() -> None:
    """MD → HTML / PDF / Slides 산출물을 생성한다."""


@build.command(name="html")
@click.argument("slug")
@click.option(
    "--with-index", is_flag=True,
    help="책 끝에 백틱 기술 용어 찾아보기(색인) 섹션을 추가 (일반 능력 AL, 기본 off)",
)
def build_html_cmd(slug: str, with_index: bool) -> None:
    """SLUG 프로젝트의 전체 도서를 단일 HTML로 빌드한다."""
    config = load_book_config(slug)
    click.echo("📚 HTML 빌드 중...")
    out_path = _build_html(config, with_index=with_index)
    size_kb = out_path.stat().st_size // 1024
    click.echo(f"✅ 완료: {out_path} ({size_kb} KB)")


@build.command(name="pdf")
@click.argument("slug")
@click.option("--chapter", type=int, default=None, help="특정 챕터 번호만 빌드 (미지정 시 전체)")
@click.option(
    "--with-index", is_flag=True,
    help="책 끝에 백틱 기술 용어 찾아보기(색인) PDF를 추가 생성 (일반 능력 AL, --chapter 지정 시 무시)",
)
def build_pdf_cmd(slug: str, chapter: Optional[int], with_index: bool) -> None:
    """SLUG 프로젝트의 챕터를 Playwright로 PDF 인쇄한다."""
    config = load_book_config(slug)
    click.echo("📄 PDF 빌드 중 (Playwright)...")
    paths = _build_pdf(config, chapter_no=chapter, with_index=with_index)
    for p in paths:
        click.echo(f"  created: {p}")
    click.echo(f"✅ 완료: {len(paths)}개 PDF")


@build.command(name="epub")
@click.argument("slug")
def build_epub_cmd(slug: str) -> None:
    """SLUG 프로젝트의 전체 도서를 EPUB 3 컨테이너로 빌드한다 (일반 능력 AJ)."""
    config = load_book_config(slug)
    click.echo("📕 EPUB 빌드 중...")
    out_path = _build_epub(config)
    size_kb = out_path.stat().st_size // 1024
    click.echo(f"✅ 완료: {out_path} ({size_kb} KB)")


@build.command(name="slides")
@click.argument("slug")
@click.option("--chapter", type=int, default=None, help="특정 챕터 번호만 빌드 (미지정 시 전체)")
@click.option("--without-notes", is_flag=True, help="발표자 노트 제외 (기본: 포함)")
def build_slides_cmd(slug: str, chapter: Optional[int], without_notes: bool) -> None:
    """SLUG 프로젝트의 챕터를 Reveal.js 발표자료로 변환한다 (섹션마다 LLM 호출)."""
    load_config()
    config = load_book_config(slug)

    try:
        llm = create_llm()
    except BookForgeError as exc:
        raise click.ClickException(str(exc)) from exc

    monitor = build_book_monitor(output_dir=str(config.project_dir / "eval_results"))

    click.echo("🎬 발표자료 생성 중 (섹션마다 LLM 호출)...")
    out_path = _build_slides(
        config, llm, monitor, chapter_no=chapter, include_notes=not without_notes
    )
    monitor.save_to_file("slides")
    click.echo(f"✅ 완료: {out_path}")
