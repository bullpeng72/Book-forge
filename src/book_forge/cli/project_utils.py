"""CLI 커맨드 공용 — 프로젝트 슬러그 → BookConfig 해석 (build/edit/gate 공유)."""
from __future__ import annotations

from pathlib import Path

import click

from book_forge.config import get_data_dir
from book_forge.publish.config import BookConfig
from book_forge.publish.front_matter import load_front_matter


def resolve_project_dir(slug: str) -> Path:
    project_dir = get_data_dir() / "projects" / slug
    if not project_dir.is_dir():
        raise click.ClickException(f"프로젝트를 찾을 수 없습니다: {project_dir}")
    return project_dir


def load_title(project_dir: Path) -> str:
    """00_기획안.md의 첫 H1(``# 제목``) 줄을 프로젝트 제목으로 삼는다.

    "첫 비어있지 않은 줄"이 아니라 명시적으로 H1만 찾는 이유: PlannerAgent가
    생성하는 본문은 "## 목적"으로 시작한다(PLAN_PROMPT 형식) — H2를 title로
    잘못 집어내는 걸 막으려면 헤딩 레벨을 구분해야 한다. `new_cmd.py`가 저장
    시점에 항상 H1을 맨 위에 붙인다.
    """
    proposal = project_dir / "00_기획안.md"
    if proposal.is_file():
        for line in proposal.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("## "):
                return stripped[2:].strip()
    return project_dir.name


def load_book_config(slug: str) -> BookConfig:
    project_dir = resolve_project_dir(slug)
    front_matter = load_front_matter(project_dir)
    return BookConfig(
        project_dir=project_dir,
        title=load_title(project_dir),
        author=front_matter.author,
        license_notice=front_matter.license_notice,
        edition=front_matter.edition,
    )
