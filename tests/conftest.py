"""공유 pytest fixture — 최소 Book-forge 프로젝트 디렉토리 + 환경변수 격리."""
from __future__ import annotations

import base64
import os
from pathlib import Path

import pytest

_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.fixture(autouse=True)
def _isolated_environ():
    """모든 테스트가 os.environ 변경사항 없이 시작·종료하게 한다.

    실측으로 발견한 문제: chat/draft/new/plan 명령이 부르는 load_config()는
    python-dotenv의 load_dotenv()를 쓰는데, 이건 monkeypatch.setenv와 달리
    os.environ에 직접 대입해 테스트가 끝나도 자동으로 되돌아가지 않는다. 실제
    사용자 홈에 ~/Documents/BookForge/.env가 있으면(get_data_dir()을 모킹하지
    않은 테스트가 load_config()를 부를 때) 그 값이 os.environ에 새어나가
    이후 실행되는 다른 테스트(예: test_llm_provider.py의 OLLAMA_MODEL 기본값
    검증)를 오염시킨다 — 실제로 이 오염 때문에 테스트가 깨지는 걸 확인했다.
    매 테스트 전후로 전체 스냅샷을 뜨고 복원해 원천 차단한다.
    """
    original = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(original)

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
