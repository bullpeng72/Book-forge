"""html_builder.py — build_html() 종단 테스트 (fixture 프로젝트, LLM 호출 없음)."""
from pathlib import Path

from book_forge.publish.config import BookConfig
from book_forge.publish.html_builder import build_html


def test_build_html_produces_self_contained_file(sample_project: Path) -> None:
    config = BookConfig(project_dir=sample_project, title="샘플 도서")
    out_path = build_html(config)

    assert out_path.exists()
    assert out_path.parent == sample_project / "outputs"

    html = out_path.read_text(encoding="utf-8")
    assert "<title>샘플 도서</title>" in html
    assert 'id="ch01"' in html and 'id="ch02"' in html
    assert "서론" in html and "환경 설정" in html
    assert "data:image/png;base64," in html  # 이미지가 인라인 임베드됐는지
    assert 'href="#ch01"' in html  # 사이드바 링크
    assert "mermaid@10" in html  # CDN 스크립트 포함


def test_build_html_marks_missing_chapter(sample_project: Path) -> None:
    (sample_project / "Part_1_기초" / "Chapter_02_환경_설정.md").unlink()
    config = BookConfig(project_dir=sample_project, title="샘플 도서")
    out_path = build_html(config)
    html = out_path.read_text(encoding="utf-8")
    assert "챕터 파일 없음" in html
