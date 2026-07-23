"""공유 pytest fixture — 최소 Book-forge 프로젝트 디렉토리."""
from __future__ import annotations

import base64
from pathlib import Path

import pytest

_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

TOC_MD = """# 목차

## Part 1. 기초
- Chapter 1. 서론
- Chapter 2. 환경 설정

```toc
1|기초|1|서론
1|기초|2|환경 설정
```
"""


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    """01_목차.md + Part_1_기초/Chapter_01,02 + 이미지 1장을 갖춘 최소 프로젝트."""
    project_dir = tmp_path / "sample-project"
    part_dir = project_dir / "Part_1_기초"
    images_dir = part_dir / "images"
    images_dir.mkdir(parents=True)

    (project_dir / "01_목차.md").write_text(TOC_MD, encoding="utf-8")
    (project_dir / "00_기획안.md").write_text("# 샘플 도서\n\n기획안 본문.", encoding="utf-8")

    (part_dir / "Chapter_01_서론.md").write_text(
        "# Chapter 01: 서론\n\n본문입니다.\n\n![그림](./images/sample.png)\n",
        encoding="utf-8",
    )
    (part_dir / "Chapter_02_환경_설정.md").write_text(
        "# Chapter 02: 환경 설정\n\n설치 방법을 설명합니다.\n",
        encoding="utf-8",
    )
    (images_dir / "sample.png").write_bytes(_TINY_PNG)

    return project_dir
