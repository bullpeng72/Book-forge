"""epub_builder.py — build_epub() 통합 테스트. Playwright 없이 zipfile만으로 검증."""
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from book_forge.publish.config import BookConfig
from book_forge.publish.epub_builder import build_epub


def test_build_epub_produces_valid_container(sample_project: Path) -> None:
    config = BookConfig(project_dir=sample_project, title="샘플 도서")
    out_path = build_epub(config)

    assert out_path.exists()
    assert out_path.suffix == ".epub"

    with zipfile.ZipFile(out_path) as zf:
        names = zf.namelist()
        assert names[0] == "mimetype"  # EPUB 스펙: 첫 항목이자 비압축
        assert zf.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
        assert zf.read("mimetype") == b"application/epub+zip"
        assert "META-INF/container.xml" in names
        assert "OEBPS/content.opf" in names
        assert "OEBPS/nav.xhtml" in names
        assert "OEBPS/chap01.xhtml" in names
        assert "OEBPS/chap02.xhtml" in names

        # 핵심 XML 문서가 전부 well-formed XML로 파싱 가능한지 확인
        ET.fromstring(zf.read("META-INF/container.xml"))
        ET.fromstring(zf.read("OEBPS/content.opf"))
        ET.fromstring(zf.read("OEBPS/nav.xhtml"))
        ET.fromstring(zf.read("OEBPS/chap01.xhtml"))


def test_build_epub_embeds_image_as_real_file_not_data_uri(sample_project: Path) -> None:
    config = BookConfig(project_dir=sample_project, title="샘플 도서")
    out_path = build_epub(config)

    with zipfile.ZipFile(out_path) as zf:
        image_entries = [n for n in zf.namelist() if n.startswith("OEBPS/images/")]
        assert len(image_entries) == 1
        assert "chap01_sample.png" in image_entries[0]

        chap01 = zf.read("OEBPS/chap01.xhtml").decode("utf-8")
        assert "data:image/" not in chap01
        assert 'src="images/chap01_sample.png"' in chap01


def test_build_epub_includes_author_in_metadata(sample_project: Path) -> None:
    config = BookConfig(project_dir=sample_project, title="샘플 도서", author="홍길동")
    out_path = build_epub(config)
    with zipfile.ZipFile(out_path) as zf:
        opf = zf.read("OEBPS/content.opf").decode("utf-8")
        assert "<dc:creator>홍길동</dc:creator>" in opf


def test_build_epub_omits_creator_tag_without_author(sample_project: Path) -> None:
    config = BookConfig(project_dir=sample_project, title="샘플 도서")
    out_path = build_epub(config)
    with zipfile.ZipFile(out_path) as zf:
        opf = zf.read("OEBPS/content.opf").decode("utf-8")
        assert "dc:creator" not in opf


def test_build_epub_skips_missing_chapter_files(sample_project: Path) -> None:
    (sample_project / "Part_1_기초" / "Chapter_02_환경_설정.md").unlink()
    config = BookConfig(project_dir=sample_project, title="샘플 도서")
    out_path = build_epub(config)
    with zipfile.ZipFile(out_path) as zf:
        assert "OEBPS/chap01.xhtml" in zf.namelist()
        assert "OEBPS/chap02.xhtml" not in zf.namelist()


def test_build_epub_raises_when_no_chapters_exist(tmp_path: Path) -> None:
    project_dir = tmp_path / "empty-project"
    part_dir = project_dir / "Part_1_기초"
    part_dir.mkdir(parents=True)
    (project_dir / "01_목차.md").write_text(
        "## Part 1. 기초\n- Chapter 1. 서론\n\n```toc\n1|기초|1|서론\n```\n", encoding="utf-8"
    )
    config = BookConfig(project_dir=project_dir, title="빈 프로젝트")
    with pytest.raises(ValueError, match="챕터가 없습니다"):
        build_epub(config)


def test_build_epub_recovers_from_malformed_raw_html_block(sample_project: Path) -> None:
    # @@HTML_START@@ 블록은 escape 없이 그대로 삽입되므로, 짝이 안 맞는
    # 태그를 넣으면 well-formed XML이 깨질 수 있다 — 그 챕터만 안전하게
    # escape된 텍스트로 대체되고, EPUB 전체는 여전히 정상적으로 열려야 한다.
    (sample_project / "Part_1_기초" / "Chapter_01_서론.md").write_text(
        "# Chapter 01\n\n@@HTML_START@@\n<div>안 닫힌 태그\n@@HTML_END@@\n",
        encoding="utf-8",
    )
    config = BookConfig(project_dir=sample_project, title="샘플 도서")
    out_path = build_epub(config)

    with zipfile.ZipFile(out_path) as zf:
        chap01 = zf.read("OEBPS/chap01.xhtml")
        ET.fromstring(chap01)  # 예외 없이 파싱되면 안전하게 대체된 것
        assert b"<pre>" in chap01
