"""01_목차.md 매니페스트를 읽어 실제 파일 경로가 채워진 ChapterSpec 목록을 만든다."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from book_forge.exceptions import BookForgeError
from book_forge.models import ChapterSpec, parse_toc_manifest


@dataclass(frozen=True)
class ResolvedChapter:
    spec: ChapterSpec
    path: Path

    @property
    def exists(self) -> bool:
        return self.path.is_file()


def load_toc(project_dir: Path) -> list[ResolvedChapter]:
    toc_path = project_dir / "01_목차.md"
    if not toc_path.is_file():
        raise BookForgeError(
            f"목차 파일이 없습니다: {toc_path} (book-forge new 로 먼저 프로젝트를 생성하세요)"
        )

    chapters = parse_toc_manifest(toc_path.read_text(encoding="utf-8"))
    return [
        ResolvedChapter(spec=spec, path=project_dir / spec.part_dir_name / spec.chapter_file_name)
        for spec in chapters
    ]
