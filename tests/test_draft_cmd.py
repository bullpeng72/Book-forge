"""`book-forge draft` 테스트 — 단일/배치(--all) 모드. 임베딩·LLM은 결정론적
fake로 대체해 오프라인·빠르게 검증한다.
"""
from pathlib import Path

from click.testing import CliRunner

import click
import pytest

import book_forge.cli.project_utils as project_utils
import book_forge.knowledge.store as store_module
from book_forge.cli.commands.draft_cmd import ChapterDraftResult, _is_draftable, _SourcePath
from book_forge.cli.main import cli
from book_forge.models import ChapterSpec
from book_forge.publish.toc_loader import ResolvedChapter


class FakeLLM:
    model = "fake"

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        return "# 생성된 챕터\n\n고정된 초안 본문입니다."


def _fake_vector(text: str) -> list[float]:
    return [1.0, 0.0] if "사과" in text else [0.0, 1.0]


def _fake_embed_text(text: str, *, base_url: str = "", model: str = "") -> list[float]:
    return _fake_vector(text)


def _fake_embed_texts(texts: list[str], *, base_url: str = "", model: str = "") -> list[list[float]]:
    return [_fake_vector(t) for t in texts]


TOC_MD = """## Part 1. 과일학

- Chapter 1. 사과 개론
- Chapter 2. 바나나 심화
- Chapter 3. 이미 완성

```toc
1|과일학|1|사과 개론
1|과일학|2|바나나 심화
1|과일학|3|이미 완성
```
"""


def _make_batch_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "projects" / "batch-slug"
    part_dir = project_dir / "Part_1_과일학"
    part_dir.mkdir(parents=True)

    (project_dir / "00_기획안.md").write_text("# 과일책\n\n## 목적\n\n요약.", encoding="utf-8")
    (project_dir / "01_목차.md").write_text(TOC_MD, encoding="utf-8")

    (part_dir / "Chapter_01_사과_개론.md").write_text(
        "# Chapter 01: 사과 개론\n\n> TODO: 이 챕터를 집필하세요.\n", encoding="utf-8"
    )
    (part_dir / "Chapter_02_바나나_심화.md").write_text(
        "# Chapter 02: 바나나 심화\n\n> TODO: 이 챕터를 집필하세요.\n", encoding="utf-8"
    )
    (part_dir / "Chapter_03_이미_완성.md").write_text(
        "# Chapter 03: 이미 완성\n\n이미 저자가 다 썼습니다.\n", encoding="utf-8"
    )
    return project_dir


def test_is_draftable_stub_chapter_true() -> None:
    spec = ChapterSpec(part_no=1, part_title="a", chapter_no=1, chapter_title="b")
    rc = ResolvedChapter(spec=spec, path=Path("/nonexistent"))
    assert _is_draftable(rc, force=False) is True  # 파일 자체가 없음 → 집필 가능


def test_is_draftable_authored_chapter_false(tmp_path: Path) -> None:
    path = tmp_path / "ch.md"
    path.write_text("# 실제 본문", encoding="utf-8")
    spec = ChapterSpec(part_no=1, part_title="a", chapter_no=1, chapter_title="b")
    rc = ResolvedChapter(spec=spec, path=path)
    assert _is_draftable(rc, force=False) is False


def test_is_draftable_force_overrides(tmp_path: Path) -> None:
    path = tmp_path / "ch.md"
    path.write_text("# 실제 본문", encoding="utf-8")
    spec = ChapterSpec(part_no=1, part_title="a", chapter_no=1, chapter_title="b")
    rc = ResolvedChapter(spec=spec, path=path)
    assert _is_draftable(rc, force=True) is True


def test_batch_and_chapter_no_mutually_exclusive(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["draft", "any-slug", "1", "--all"])
    assert result.exit_code != 0
    assert "함께 쓸 수 없습니다" in result.output


def test_neither_chapter_no_nor_all_raises(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["draft", "any-slug"])
    assert result.exit_code != 0
    assert "--all" in result.output


def test_draft_all_creates_stub_chapters_and_skips_low_coverage_and_authored(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr("book_forge.cli.commands.draft_cmd.create_llm", lambda: FakeLLM())

    project_dir = _make_batch_project(tmp_path)
    source_file = tmp_path / "source.txt"
    source_file.write_text("사과에 대한 소스입니다", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli, ["draft", "batch-slug", "--all", "--source", str(source_file)]
    )

    assert result.exit_code == 0, result.output
    # Ch1(사과 개론)은 소스와 유사도가 높아 생성됨
    ch1 = (project_dir / "Part_1_과일학" / "Chapter_01_사과_개론.md").read_text(encoding="utf-8")
    assert "고정된 초안 본문" in ch1
    # Ch2(바나나 심화)는 소스와 무관해 낮은 커버리지로 건너뜀 — 원래 스텁 그대로
    ch2 = (project_dir / "Part_1_과일학" / "Chapter_02_바나나_심화.md").read_text(encoding="utf-8")
    assert "TODO" in ch2
    # Ch3(이미 완성)은 애초에 대상에서 제외됨 — 원문 그대로
    ch3 = (project_dir / "Part_1_과일학" / "Chapter_03_이미_완성.md").read_text(encoding="utf-8")
    assert "이미 저자가 다 썼습니다" in ch3

    assert "일괄 생성 요약" in result.output
    assert "생성 1개, 건너뜀 1개" in result.output


def test_draft_all_no_targets_when_all_authored(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)

    project_dir = _make_batch_project(tmp_path)
    # 스텁 두 개도 저자가 이미 쓴 것으로 바꿔서 대상이 하나도 없게 만든다.
    for name in ("Chapter_01_사과_개론.md", "Chapter_02_바나나_심화.md"):
        (project_dir / "Part_1_과일학" / name).write_text("# 다 씀\n\n완료.", encoding="utf-8")

    source_file = tmp_path / "source.txt"
    source_file.write_text("아무 내용", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli, ["draft", "batch-slug", "--all", "--source", str(source_file)]
    )

    assert result.exit_code == 0
    assert "모든 챕터가 이미 집필" in result.output


def test_chapter_draft_result_dataclass_defaults() -> None:
    result = ChapterDraftResult(chapter_no=1, chapter_title="제목", status="created")
    assert result.avg_coverage is None
    assert result.gate_c_score is None


def test_source_path_type_passes_through_urls_without_filesystem_check() -> None:
    source_type = _SourcePath()
    assert source_type.convert("https://example.com/doc", None, None) == "https://example.com/doc"
    assert source_type.convert("http://example.com/doc", None, None) == "http://example.com/doc"


def test_source_path_type_validates_local_paths_exist() -> None:
    source_type = _SourcePath()
    with pytest.raises(click.BadParameter):
        source_type.convert("/no/such/path/exists", None, None)


def test_source_path_type_accepts_existing_local_path(tmp_path: Path) -> None:
    f = tmp_path / "source.txt"
    f.write_text("내용", encoding="utf-8")
    source_type = _SourcePath()
    assert source_type.convert(str(f), None, None) == str(f)
