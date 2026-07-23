"""project_utils.py — load_title() 회귀 테스트.

실제 오프라인 종단 검증(M7) 중 발견한 버그: PlannerAgent 산출물은 "## 목적"으로
시작하는데(PLAN_PROMPT 형식, H1 없음) load_title()이 "첫 비어있지 않은 줄"을
그대로 제목으로 썼다 — "목적"이 책 제목이 되어 outputs/목적.html 같은 파일이
생성됐다. new_cmd.py가 저장 시점에 H1을 붙이고, load_title()은 H1만 찾도록 수정.
"""
from pathlib import Path

from book_forge.cli.project_utils import load_title


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
