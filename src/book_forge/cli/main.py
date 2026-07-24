"""Book-forge CLI 진입점."""
from __future__ import annotations

import click

from book_forge.cli.commands.build_cmd import build
from book_forge.cli.commands.chat_cmd import chat
from book_forge.cli.commands.draft_cmd import draft
from book_forge.cli.commands.edit_cmd import edit
from book_forge.cli.commands.gate_cmd import gate
from book_forge.cli.commands.home_cmd import home
from book_forge.cli.commands.init_cmd import init
from book_forge.cli.commands.knowledge_cmd import knowledge
from book_forge.cli.commands.lint_cmd import lint
from book_forge.cli.commands.new_cmd import new
from book_forge.cli.commands.plan_cmd import plan
from book_forge.cli.commands.research_cmd import research
from book_forge.cli.commands.review_cmd import review

_STUB_COMMANDS = [
    ("scaffold", "M1", "승인된 목차 → Part/Chapter MD 스캐폴드 생성"),
]


@click.group()
@click.version_option(package_name="book-forge")
def cli() -> None:
    """Book-forge — 기획부터 HTML/PDF/발표자료까지, AI 협업 다권 저술 도구."""


cli.add_command(init)
cli.add_command(new)
cli.add_command(build)
cli.add_command(edit)
cli.add_command(gate)
cli.add_command(draft)
cli.add_command(home)
cli.add_command(plan)
cli.add_command(chat)
cli.add_command(review)
cli.add_command(knowledge)
cli.add_command(research)
cli.add_command(lint)


def _make_stub(name: str, milestone: str, summary: str) -> click.Command:
    @click.command(name=name, help=f"{summary} (미구현 — {milestone} 예정)")
    @click.argument("args", nargs=-1)
    def _cmd(args: tuple) -> None:
        click.echo(f"'{name}' 명령은 아직 구현되지 않았습니다 ({milestone}에서 구현 예정).")
        click.echo(f"  → {summary}")

    return _cmd


for _name, _milestone, _summary in _STUB_COMMANDS:
    cli.add_command(_make_stub(_name, _milestone, _summary))


if __name__ == "__main__":
    cli()
