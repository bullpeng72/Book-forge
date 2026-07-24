"""project_utils.py — load_title() 회귀 테스트.

실제 오프라인 종단 검증(M7) 중 발견한 버그: PlannerAgent 산출물은 "## 목적"으로
시작하는데(PLAN_PROMPT 형식, H1 없음) load_title()이 "첫 비어있지 않은 줄"을
그대로 제목으로 썼다 — "목적"이 책 제목이 되어 outputs/목적.html 같은 파일이
생성됐다. new_cmd.py가 저장 시점에 H1을 붙이고, load_title()은 H1만 찾도록 수정.
"""
from pathlib import Path

import book_forge.cli.project_utils as project_utils
from book_forge.cli.project_utils import load_book_config, load_title
from book_forge.publish.front_matter import FrontMatter, save_front_matter


def test_load_title_reads_h1_line(tmp_path: Path) -> None:
    (tmp_path / "00_기획안.md").write_text(
        "# 실제 책 제목\n\n## 목적\n\n본문...", encoding="utf-8"
    )
    assert load_title(tmp_path) == "실제 책 제목"


def test_load_title_does_not_mistake_h2_for_title(tmp_path: Path) -> None:
    """H1이 없고 '## 목적'만 있으면(과거 버그 재현 조건) H2를 제목으로 잘못 집지 않는다."""
    (tmp_path / "00_기획안.md").write_text("## 목적\n\n본문...", encoding="utf-8")
    assert load_title(tmp_path) == tmp_path.name


def test_load_title_missing_proposal_falls_back_to_dirname(tmp_path: Path) -> None:
    assert load_title(tmp_path) == tmp_path.name


# 일반 능력 AI — load_book_config()가 front_matter.json을 BookConfig에 반영하는지.
def test_load_book_config_includes_front_matter_when_present(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    project_dir = tmp_path / "projects" / "sample-slug"
    project_dir.mkdir(parents=True)
    (project_dir / "00_기획안.md").write_text("# 샘플 도서\n\n## 목적\n\n본문", encoding="utf-8")
    save_front_matter(project_dir, FrontMatter(author="홍길동", edition="1판"))

    config = load_book_config("sample-slug")
    assert config.title == "샘플 도서"
    assert config.author == "홍길동"
    assert config.edition == "1판"


def test_load_book_config_empty_front_matter_when_absent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    project_dir = tmp_path / "projects" / "no-front-matter-slug"
    project_dir.mkdir(parents=True)
    (project_dir / "00_기획안.md").write_text("# 다른 책\n\n## 목적\n\n본문", encoding="utf-8")

    config = load_book_config("no-front-matter-slug")
    assert config.author == ""
    assert config.license_notice == ""
    assert config.edition == ""
