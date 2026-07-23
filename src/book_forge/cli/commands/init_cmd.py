"""`book-forge init` — LLM provider 및 API 키 설정 마법사."""
from __future__ import annotations

from typing import Optional

import click

from book_forge.config import get_data_dir, resolve_env_path

PROVIDER_CHOICES = ["openai", "anthropic", "ollama"]


def _parse_env_file(path) -> dict:
    values: dict = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


@click.command()
@click.option(
    "--path", "custom_path", type=click.Path(dir_okay=False), default=None,
    help="커스텀 .env 저장 경로",
)
@click.option("-r", "--reconfigure", is_flag=True, help="기존 설정을 유지하며 항목별로 재설정")
@click.option("-s", "--show", "show_only", is_flag=True, help="현재 설정만 출력하고 종료")
def init(custom_path: Optional[str], reconfigure: bool, show_only: bool) -> None:
    """대화형으로 .env 파일을 생성/갱신한다."""
    env_path = resolve_env_path(custom_path)

    if show_only:
        if not env_path.exists():
            click.echo(f"❌ 설정 파일이 없습니다: {env_path}")
            click.echo("   book-forge init 을 먼저 실행하세요.")
            return
        click.echo(f"📄 현재 설정 ({env_path}):\n")
        click.echo(env_path.read_text(encoding="utf-8"))
        return

    existing = _parse_env_file(env_path)

    click.echo("📚 Book-forge 초기 설정\n")

    provider = click.prompt(
        "LLM Provider를 선택하세요",
        type=click.Choice(PROVIDER_CHOICES),
        default=existing.get("LLM_PROVIDER", "ollama"),
    )

    lines = [f"LLM_PROVIDER={provider}"]

    if provider == "openai":
        key = click.prompt(
            "OPENAI_API_KEY", default=existing.get("OPENAI_API_KEY") or None,
            hide_input=True, show_default=False,
        )
        lines.append(f"OPENAI_API_KEY={key}")
    elif provider == "anthropic":
        key = click.prompt(
            "ANTHROPIC_API_KEY", default=existing.get("ANTHROPIC_API_KEY") or None,
            hide_input=True, show_default=False,
        )
        lines.append(f"ANTHROPIC_API_KEY={key}")
    else:  # ollama
        base_url = click.prompt(
            "OLLAMA_BASE_URL", default=existing.get("OLLAMA_BASE_URL", "http://localhost:11434")
        )
        model = click.prompt("OLLAMA_MODEL", default=existing.get("OLLAMA_MODEL", "llama3.2"))
        lines.append(f"OLLAMA_BASE_URL={base_url}")
        lines.append(f"OLLAMA_MODEL={model}")

    # provider 무관하게 선택적 항목 — M5 RAG 소스 수집 단계에서 사용
    if reconfigure or not env_path.exists():
        serper_key = click.prompt(
            "SERPER_API_KEY (선택, 웹 검색 보조 — Enter로 건너뛰기)",
            default=existing.get("SERPER_API_KEY", ""), show_default=False,
        )
        if serper_key:
            lines.append(f"SERPER_API_KEY={serper_key}")
    elif existing.get("SERPER_API_KEY"):
        lines.append(f"SERPER_API_KEY={existing['SERPER_API_KEY']}")

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if env_path.parent == get_data_dir():
        try:
            env_path.chmod(0o600)
        except OSError:
            pass

    click.echo(f"\n✅ 설정 저장 완료: {env_path}")
