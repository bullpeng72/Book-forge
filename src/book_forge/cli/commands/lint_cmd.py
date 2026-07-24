"""`book-forge lint` — 챕터 간 기술 용어 표기 일관성 검사(일반 능력 AK).

새 판정 로직이 아니라 이미 있는 인프라(코드-본문 정합성 검사기의 백틱 추출
정규식/제외 목록)를 재사용하는 발견·보고 전용 명령이다. 자동으로 표기를
통일하지 않는다 — 후보 목록을 보여주고 최종 판단은 저자가 한다.
"""
from __future__ import annotations

import click

from book_forge.agents.term_consistency_checker import find_term_variants
from book_forge.cli.project_utils import resolve_project_dir
from book_forge.publish.toc_loader import load_toc


@click.command()
@click.argument("slug")
@click.option(
    "--fail-on-inconsistency", is_flag=True,
    help="표기 불일치 후보가 하나라도 있으면 exit code 1 (CI 연동용)",
)
def lint(slug: str, fail_on_inconsistency: bool) -> None:
    """SLUG 프로젝트의 전체 챕터에서 백틱 기술 용어의 표기 불일치 후보를 찾아 보고한다."""
    project_dir = resolve_project_dir(slug)
    chapters = load_toc(project_dir)

    texts = []
    for rc in chapters:
        if not rc.exists:
            continue
        texts.append((f"Chapter {rc.spec.chapter_no} ({rc.spec.chapter_title})", rc.path.read_text(encoding="utf-8")))

    if not texts:
        click.echo("검사할 챕터 본문이 없습니다 (book-forge draft 로 먼저 초안을 생성하세요).")
        return

    groups = find_term_variants(texts)

    if not groups:
        click.echo(f"✅ 표기 불일치 후보 없음 ({len(texts)}개 챕터 검사).")
        return

    click.echo(f"⚠️  표기 불일치 후보 {len(groups)}건 ({len(texts)}개 챕터 검사):\n")
    for group in groups:
        click.echo(f"- 후보: {', '.join(sorted(group.variants))}")
        for variant, labels in group.variants.items():
            click.echo(f"    · `{variant}` — {', '.join(labels)}")
    click.echo("\n표기를 통일할지는 저자가 직접 판단하세요 — 자동 수정되지 않습니다.")

    if fail_on_inconsistency:
        raise SystemExit(1)
