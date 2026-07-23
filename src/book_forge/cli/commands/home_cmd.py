"""`book-forge home` — 데이터/프로젝트 폴더를 파일 탐색기로 연다."""
from __future__ import annotations

import platform
import subprocess
from pathlib import Path
from typing import Optional

import click

from book_forge.config import get_data_dir


def _open_in_file_manager(path: Path) -> None:
    system = platform.system()
    if system == "Darwin":
        subprocess.run(["open", str(path)], check=False)
    elif system == "Windows":
        subprocess.run(["explorer", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


@click.command()
@click.argument("slug", required=False, default=None)
def home(slug: Optional[str]) -> None:
    """데이터 폴더(SLUG 미지정 시) 또는 SLUG 프로젝트 폴더를 파일 탐색기로 연다."""
    data_dir = get_data_dir()
    if slug:
        path = data_dir / "projects" / slug
        if not path.is_dir():
            raise click.ClickException(f"프로젝트를 찾을 수 없습니다: {path}")
    else:
        path = data_dir
        path.mkdir(parents=True, exist_ok=True)

    click.echo(f"📂 {path}")
    _open_in_file_manager(path)
