"""`book-forge draft` 테스트 — 단일/배치(--all) 모드. 임베딩·LLM은 결정론적
fake로 대체해 오프라인·빠르게 검증한다.
"""
from pathlib import Path

from click.testing import CliRunner

import click
import pytest

import book_forge.cli.project_utils as project_utils
import book_forge.knowledge.store as store_module
from book_forge.cli.commands.draft_cmd import (
    ChapterDraftResult,
    _append_references_section,
    _build_structure_summary_from_sources,
    _cited_url_sources,
    _is_draftable,
    _SourcePath,
)
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


class _ExerciseLLM:
    """content_type=exercise 프롬프트를 받으면 유효한 python 코드 블록을 낸다."""

    model = "fake"

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        if "실습(exercise)" in prompt:
            return (
                "# Chapter 1: 사과 개론\n\n## 목표\n\n덧셈을 배운다.\n\n"
                "## 실습\n\n```python\ndef add(a, b):\n    return a + b\n```\n\n"
                "## 해설\n\n소스에 근거한 설명."
            )
        return "# 생성된 챕터\n\n고정된 초안 본문입니다."


def test_draft_single_chapter_exercise_type_runs_verification(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr("book_forge.cli.commands.draft_cmd.create_llm", lambda: _ExerciseLLM())

    project_dir = tmp_path / "projects" / "exercise-slug"
    part_dir = project_dir / "Part_1_기초"
    part_dir.mkdir(parents=True)
    toc_md = (
        "```toc\n1|기초|1|사과 개론|exercise\n```\n"
    )
    (project_dir / "01_목차.md").write_text(toc_md, encoding="utf-8")
    (part_dir / "Chapter_01_사과_개론.md").write_text(
        "# Chapter 01: 사과 개론\n\n> TODO: 이 챕터를 집필하세요.\n", encoding="utf-8"
    )

    source_file = tmp_path / "source.txt"
    source_file.write_text("사과에 대한 소스입니다", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli, ["draft", "exercise-slug", "1", "--source", str(source_file), "-y"]
    )

    assert result.exit_code == 0, result.output
    assert "🔬 실증 가능성 검증: ✅" in result.output

    ch1 = (part_dir / "Chapter_01_사과_개론.md").read_text(encoding="utf-8")
    assert "```python" in ch1


def test_draft_single_chapter_exercise_type_reports_missing_code_block(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)
    # FakeLLM은 content_type과 무관하게 코드 블록 없는 서술형 텍스트만 반환한다.
    monkeypatch.setattr("book_forge.cli.commands.draft_cmd.create_llm", lambda: FakeLLM())

    project_dir = tmp_path / "projects" / "exercise-slug2"
    part_dir = project_dir / "Part_1_기초"
    part_dir.mkdir(parents=True)
    toc_md = "```toc\n1|기초|1|사과 개론|exercise\n```\n"
    (project_dir / "01_목차.md").write_text(toc_md, encoding="utf-8")
    (part_dir / "Chapter_01_사과_개론.md").write_text(
        "# Chapter 01: 사과 개론\n\n> TODO: 이 챕터를 집필하세요.\n", encoding="utf-8"
    )

    source_file = tmp_path / "source.txt"
    source_file.write_text("사과에 대한 소스입니다", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli, ["draft", "exercise-slug2", "1", "--source", str(source_file), "-y"]
    )

    assert result.exit_code == 0, result.output
    assert "🔬 실증 가능성 검증: ⚠️" in result.output
    assert "python 코드 블록이 없습니다" in result.output


class _DiagramLLM:
    """content_type=diagram(DiagramGeneratorAgent) 프롬프트를 받으면 mermaid 블록을 낸다."""

    model = "fake"

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        if "다이어그램 중심으로" in prompt:
            return (
                "# Chapter 1: 파이프라인\n\n도입부.\n\n"
                "```mermaid\ngraph TD\n    A[요청] --> B[응답]\n```\n\n설명."
            )
        return "# 생성된 챕터\n\n고정된 초안 본문입니다."


def test_draft_single_chapter_diagram_type_routes_to_diagram_generator(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr("book_forge.cli.commands.draft_cmd.create_llm", lambda: _DiagramLLM())

    project_dir = tmp_path / "projects" / "diagram-slug"
    part_dir = project_dir / "Part_1_기초"
    part_dir.mkdir(parents=True)
    toc_md = "```toc\n1|기초|1|사과 개론|diagram\n```\n"
    (project_dir / "01_목차.md").write_text(toc_md, encoding="utf-8")
    (part_dir / "Chapter_01_사과_개론.md").write_text(
        "# Chapter 01: 사과 개론\n\n> TODO: 이 챕터를 집필하세요.\n", encoding="utf-8"
    )

    source_file = tmp_path / "source.txt"
    source_file.write_text("사과에 대한 소스입니다", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli, ["draft", "diagram-slug", "1", "--source", str(source_file), "-y"]
    )

    assert result.exit_code == 0, result.output
    assert "📈 다이어그램 생성 중" in result.output
    assert "🔬 실증 가능성 검증: ✅" in result.output

    ch1 = (part_dir / "Chapter_01_사과_개론.md").read_text(encoding="utf-8")
    assert "```mermaid" in ch1


class _RealSymbolLLM:
    """실제로 존재하는 agent_evaluator 심볼만 언급 — 정합성 검사 통과 케이스."""

    model = "fake"

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        return (
            "# 생성된 챕터\n\n`ScopeConfig`는 도구 이름 기반이며 "
            "`ScopeConfig.allowed_tools` 필드로 허용 도구를 지정합니다."
        )


class _FakeSymbolLLM:
    """실제로 존재하지 않는 심볼을 언급 — 정합성 검사 실패 케이스."""

    model = "fake"

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        return "# 생성된 챕터\n\n`ScopeConfig`는 `ScopeConfig.path`로 파일 경로를 제한합니다."


def test_draft_check_package_passes_for_real_symbols(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr("book_forge.cli.commands.draft_cmd.create_llm", lambda: _RealSymbolLLM())

    project_dir = tmp_path / "projects" / "consistency-slug"
    part_dir = project_dir / "Part_1_기초"
    part_dir.mkdir(parents=True)
    toc_md = "```toc\n1|기초|1|사과 개론\n```\n"
    (project_dir / "01_목차.md").write_text(toc_md, encoding="utf-8")
    (part_dir / "Chapter_01_사과_개론.md").write_text(
        "# Chapter 01: 사과 개론\n\n> TODO: 이 챕터를 집필하세요.\n", encoding="utf-8"
    )

    source_file = tmp_path / "source.txt"
    source_file.write_text("사과에 대한 소스입니다", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli, [
            "draft", "consistency-slug", "1", "--source", str(source_file), "-y",
            "--check-package", "agent_evaluator",
        ]
    )

    assert result.exit_code == 0, result.output
    assert "🔗 코드-본문 정합성: ✅" in result.output


def test_draft_check_package_flags_nonexistent_symbol(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr("book_forge.cli.commands.draft_cmd.create_llm", lambda: _FakeSymbolLLM())

    project_dir = tmp_path / "projects" / "consistency-slug2"
    part_dir = project_dir / "Part_1_기초"
    part_dir.mkdir(parents=True)
    toc_md = "```toc\n1|기초|1|사과 개론\n```\n"
    (project_dir / "01_목차.md").write_text(toc_md, encoding="utf-8")
    (part_dir / "Chapter_01_사과_개론.md").write_text(
        "# Chapter 01: 사과 개론\n\n> TODO: 이 챕터를 집필하세요.\n", encoding="utf-8"
    )

    source_file = tmp_path / "source.txt"
    source_file.write_text("사과에 대한 소스입니다", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli, [
            "draft", "consistency-slug2", "1", "--source", str(source_file), "-y",
            "--check-package", "agent_evaluator",
        ]
    )

    assert result.exit_code == 0, result.output
    assert "🔗 코드-본문 정합성: ⚠️" in result.output
    assert "ScopeConfig.path" in result.output


class _LocalSymbolLLM:
    """로컬 프로젝트 소스에 실제로 있는 심볼만 언급 — 로컬 대상 정합성 검사 통과 케이스."""

    model = "fake"

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        return "# 생성된 챕터\n\n`Worker` 클래스와 `build_worker` 함수가 정의돼 있습니다."


def test_draft_check_package_supports_local_directory_target(
    tmp_path: Path, monkeypatch
) -> None:
    # 일반 능력 I — --check-package에 설치된 패키지명 대신 로컬 디렉토리를
    # 줬을 때도 정합성 검사가 정상 동작해야 한다(pip install 안 한 분석
    # 대상 프로젝트를 --source로 분석하는 강의 유형 지원).
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr("book_forge.cli.commands.draft_cmd.create_llm", lambda: _LocalSymbolLLM())

    local_target = tmp_path / "analyzed_project"
    (local_target / "agents").mkdir(parents=True)
    (local_target / "agents" / "worker.py").write_text(
        "def build_worker(name):\n    return name\n\n\nclass Worker:\n    pass\n",
        encoding="utf-8",
    )

    project_dir = tmp_path / "projects" / "local-target-slug"
    part_dir = project_dir / "Part_1_기초"
    part_dir.mkdir(parents=True)
    toc_md = "```toc\n1|기초|1|사과 개론\n```\n"
    (project_dir / "01_목차.md").write_text(toc_md, encoding="utf-8")
    (part_dir / "Chapter_01_사과_개론.md").write_text(
        "# Chapter 01: 사과 개론\n\n> TODO: 이 챕터를 집필하세요.\n", encoding="utf-8"
    )

    source_file = tmp_path / "source.txt"
    source_file.write_text("사과에 대한 소스입니다", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli, [
            "draft", "local-target-slug", "1", "--source", str(source_file), "-y",
            "--check-package", str(local_target),
        ]
    )

    assert result.exit_code == 0, result.output
    assert "🔗 코드-본문 정합성: ✅" in result.output


def test_draft_check_package_pins_sdk_version_on_first_use(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr("book_forge.cli.commands.draft_cmd.create_llm", lambda: _RealSymbolLLM())

    project_dir = tmp_path / "projects" / "version-pin-slug"
    part_dir = project_dir / "Part_1_기초"
    part_dir.mkdir(parents=True)
    toc_md = "```toc\n1|기초|1|사과 개론\n```\n"
    (project_dir / "01_목차.md").write_text(toc_md, encoding="utf-8")
    (part_dir / "Chapter_01_사과_개론.md").write_text(
        "# Chapter 01: 사과 개론\n\n> TODO: 이 챕터를 집필하세요.\n", encoding="utf-8"
    )
    source_file = tmp_path / "source.txt"
    source_file.write_text("사과에 대한 소스입니다", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli, [
            "draft", "version-pin-slug", "1", "--source", str(source_file), "-y",
            "--check-package", "agent_evaluator",
        ]
    )

    assert result.exit_code == 0, result.output
    assert "agent_evaluator" in result.output and "기준)" in result.output

    from book_forge.agents.sdk_version_pin import load_pinned_versions

    pinned = load_pinned_versions(project_dir)
    assert "agent_evaluator" in pinned
    assert pinned["agent_evaluator"][0].isdigit()


def test_draft_check_package_warns_on_version_drift(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr("book_forge.cli.commands.draft_cmd.create_llm", lambda: _RealSymbolLLM())

    project_dir = tmp_path / "projects" / "drift-slug"
    part_dir = project_dir / "Part_1_기초"
    part_dir.mkdir(parents=True)
    toc_md = "```toc\n1|기초|1|사과 개론\n```\n"
    (project_dir / "01_목차.md").write_text(toc_md, encoding="utf-8")
    (part_dir / "Chapter_01_사과_개론.md").write_text(
        "# Chapter 01: 사과 개론\n\n> TODO: 이 챕터를 집필하세요.\n", encoding="utf-8"
    )
    source_file = tmp_path / "source.txt"
    source_file.write_text("사과에 대한 소스입니다", encoding="utf-8")

    from book_forge.agents.sdk_version_pin import sdk_versions_path

    project_dir.mkdir(parents=True, exist_ok=True)
    sdk_versions_path(project_dir).write_text(
        '{"agent_evaluator": "0.0.1"}', encoding="utf-8"
    )

    runner = CliRunner()
    result = runner.invoke(
        cli, [
            "draft", "drift-slug", "1", "--source", str(source_file), "-y",
            "--check-package", "agent_evaluator",
        ]
    )

    assert result.exit_code == 0, result.output
    assert "0.0.1로 고정됐지만" in result.output


class _ExecutableCodeLLM:
    """실제로 실행되면 성공하는 python 코드 블록을 낸다."""

    model = "fake"

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        return "# 생성된 챕터\n\n```python\ndef add(a, b):\n    return a + b\n\nassert add(1, 2) == 3\n```"


class _BrokenCodeLLM:
    """실행하면 실패하는(하지만 문법은 유효한) python 코드 블록을 낸다."""

    model = "fake"

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        return "# 생성된 챕터\n\n```python\nraise ValueError('boom')\n```"


def _make_single_chapter_project(tmp_path: Path, slug: str) -> Path:
    project_dir = tmp_path / "projects" / slug
    part_dir = project_dir / "Part_1_기초"
    part_dir.mkdir(parents=True)
    toc_md = "```toc\n1|기초|1|사과 개론\n```\n"
    (project_dir / "01_목차.md").write_text(toc_md, encoding="utf-8")
    (part_dir / "Chapter_01_사과_개론.md").write_text(
        "# Chapter 01: 사과 개론\n\n> TODO: 이 챕터를 집필하세요.\n", encoding="utf-8"
    )
    return project_dir


def test_execute_examples_requires_check_package(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["draft", "any-slug", "1", "--execute-examples"])
    assert result.exit_code != 0
    assert "--check-package와 함께" in result.output


def test_draft_execute_examples_passes_for_working_code(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr(
        "book_forge.cli.commands.draft_cmd.create_llm", lambda: _ExecutableCodeLLM()
    )

    _make_single_chapter_project(tmp_path, "exec-ok-slug")
    source_file = tmp_path / "source.txt"
    source_file.write_text("사과에 대한 소스입니다", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli, [
            "draft", "exec-ok-slug", "1", "--source", str(source_file), "-y",
            "--check-package", "agent_evaluator", "--execute-examples",
        ]
    )

    assert result.exit_code == 0, result.output
    assert "▶️  코드 실행 검증: ✅" in result.output


def test_draft_execute_examples_flags_runtime_failure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr("book_forge.cli.commands.draft_cmd.create_llm", lambda: _BrokenCodeLLM())

    _make_single_chapter_project(tmp_path, "exec-fail-slug")
    source_file = tmp_path / "source.txt"
    source_file.write_text("사과에 대한 소스입니다", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli, [
            "draft", "exec-fail-slug", "1", "--source", str(source_file), "-y",
            "--check-package", "agent_evaluator", "--execute-examples",
        ]
    )

    # 실행 실패해도 초안 저장은 그대로 진행된다(기존 원칙과 일관 — 참고용).
    assert result.exit_code == 0, result.output
    assert "▶️  코드 실행 검증: ⚠️" in result.output
    assert "ValueError" in result.output
    ch1 = (tmp_path / "projects" / "exec-fail-slug" / "Part_1_기초" / "Chapter_01_사과_개론.md")
    assert ch1.is_file()
    assert "raise ValueError" in ch1.read_text(encoding="utf-8")


class _CapstoneExecRoutingLLM:
    """템플릿을 실행하면 확실히 실패(raise)하고, 정답을 실행하면 확실히 성공하는
    코드를 낸다 — 실행 검증이 template이 아니라 solution을 실행했는지 명확히
    구분하기 위한 전용 fixture(기존 _CapstoneLLM은 둘 다 예외 없이 끝나는
    코드라 라우팅 증명에 못 씀)."""

    model = "fake"

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        return (
            "=== TEMPLATE ===\n"
            "# Chapter 1: 사과 개론\n\n## 시작 코드\n\n"
            "```python\nraise NotImplementedError('템플릿이 실행되면 여기서 실패해야 함')\n```\n\n"
            "=== SOLUTION ===\n"
            "# Chapter 1: 사과 개론 — 모범 정답\n\n## 모범 정답\n\n"
            "```python\nx = 1 + 1\nassert x == 2\n```\n\n## 해설\n\n정답 코드."
        )


def test_draft_execute_examples_runs_solution_not_template_for_capstone(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr(
        "book_forge.cli.commands.draft_cmd.create_llm", lambda: _CapstoneExecRoutingLLM()
    )

    project_dir = tmp_path / "projects" / "exec-capstone-slug"
    part_dir = project_dir / "Part_1_기초"
    part_dir.mkdir(parents=True)
    toc_md = "```toc\n1|기초|1|사과 개론|capstone\n```\n"
    (project_dir / "01_목차.md").write_text(toc_md, encoding="utf-8")
    (part_dir / "Chapter_01_사과_개론.md").write_text(
        "# Chapter 01: 사과 개론\n\n> TODO: 이 챕터를 집필하세요.\n", encoding="utf-8"
    )
    source_file = tmp_path / "source.txt"
    source_file.write_text("사과에 대한 소스입니다", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli, [
            "draft", "exec-capstone-slug", "1", "--source", str(source_file), "-y",
            "--check-package", "agent_evaluator", "--execute-examples",
        ]
    )

    # 정답이 실행됐다면 통과, 템플릿(NotImplementedError)이 실행됐다면 반드시 실패한다.
    assert result.exit_code == 0, result.output
    assert "▶️  코드 실행 검증: ✅" in result.output
    assert "NotImplementedError" not in result.output


def test_draft_without_check_package_skips_consistency_check(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr("book_forge.cli.commands.draft_cmd.create_llm", lambda: FakeLLM())

    project_dir = tmp_path / "projects" / "no-check-slug"
    part_dir = project_dir / "Part_1_기초"
    part_dir.mkdir(parents=True)
    toc_md = "```toc\n1|기초|1|사과 개론\n```\n"
    (project_dir / "01_목차.md").write_text(toc_md, encoding="utf-8")
    (part_dir / "Chapter_01_사과_개론.md").write_text(
        "# Chapter 01: 사과 개론\n\n> TODO: 이 챕터를 집필하세요.\n", encoding="utf-8"
    )

    source_file = tmp_path / "source.txt"
    source_file.write_text("사과에 대한 소스입니다", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli, ["draft", "no-check-slug", "1", "--source", str(source_file), "-y"]
    )

    assert result.exit_code == 0, result.output
    assert "코드-본문 정합성" not in result.output


class _CapstoneLLM:
    """content_type=capstone 프롬프트를 받으면 TEMPLATE/SOLUTION 구분자 응답을 낸다."""

    model = "fake"

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        if "실습/캡스톤 과제" in prompt:
            return (
                "=== TEMPLATE ===\n"
                "# Chapter 1: 사과 개론\n\n## 목표\n\n덧셈을 배운다.\n\n"
                "## 시작 코드\n\n```python\ndef add(a, b):\n    # TODO: 구현하세요\n    pass\n```\n\n"
                "=== SOLUTION ===\n"
                "# Chapter 1: 사과 개론 — 모범 정답\n\n## 모범 정답\n\n"
                "```python\ndef add(a, b):\n    return a + b\n```\n\n## 해설\n\n소스에 근거한 설명."
            )
        return "# 생성된 챕터\n\n고정된 초안 본문입니다."


def test_draft_single_chapter_capstone_type_writes_template_and_solution_files(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr("book_forge.cli.commands.draft_cmd.create_llm", lambda: _CapstoneLLM())

    project_dir = tmp_path / "projects" / "capstone-slug"
    part_dir = project_dir / "Part_1_기초"
    part_dir.mkdir(parents=True)
    toc_md = "```toc\n1|기초|1|사과 개론|capstone\n```\n"
    (project_dir / "01_목차.md").write_text(toc_md, encoding="utf-8")
    (part_dir / "Chapter_01_사과_개론.md").write_text(
        "# Chapter 01: 사과 개론\n\n> TODO: 이 챕터를 집필하세요.\n", encoding="utf-8"
    )

    source_file = tmp_path / "source.txt"
    source_file.write_text("사과에 대한 소스입니다", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli, ["draft", "capstone-slug", "1", "--source", str(source_file), "-y"]
    )

    assert result.exit_code == 0, result.output
    assert "🎓 실습/캡스톤 생성 중" in result.output
    assert "🔑 정답 저장" in result.output
    assert "🔬 실증 가능성 검증: ✅" in result.output

    template_path = part_dir / "Chapter_01_사과_개론.md"
    solution_path = part_dir / "Chapter_01_사과_개론_정답.md"
    assert solution_path.is_file()

    template_content = template_path.read_text(encoding="utf-8")
    solution_content = solution_path.read_text(encoding="utf-8")
    assert "TODO" in template_content
    assert "=== SOLUTION ===" not in template_content
    assert "return a + b" in solution_content
    assert "TODO" not in solution_content


def test_draft_capstone_solution_file_not_exposed_via_load_toc(
    tmp_path: Path, monkeypatch
) -> None:
    # load_toc()이 목차 매니페스트만 읽으므로 정답 사이드카 파일이 build/edit에
    # 노출되지 않아야 한다(정답 유출 방지) — 실제로 목차에 없는 파일임을 확인.
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr("book_forge.cli.commands.draft_cmd.create_llm", lambda: _CapstoneLLM())

    project_dir = tmp_path / "projects" / "capstone-slug2"
    part_dir = project_dir / "Part_1_기초"
    part_dir.mkdir(parents=True)
    toc_md = "```toc\n1|기초|1|사과 개론|capstone\n```\n"
    (project_dir / "01_목차.md").write_text(toc_md, encoding="utf-8")
    (part_dir / "Chapter_01_사과_개론.md").write_text(
        "# Chapter 01: 사과 개론\n\n> TODO: 이 챕터를 집필하세요.\n", encoding="utf-8"
    )

    source_file = tmp_path / "source.txt"
    source_file.write_text("사과에 대한 소스입니다", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(cli, ["draft", "capstone-slug2", "1", "--source", str(source_file), "-y"])

    from book_forge.publish.toc_loader import load_toc

    chapters = load_toc(project_dir)
    toc_paths = {rc.path for rc in chapters}
    solution_path = part_dir / "Chapter_01_사과_개론_정답.md"
    assert solution_path not in toc_paths


def test_draft_passes_max_per_source_through_to_query_with_scores(
    tmp_path: Path, monkeypatch
) -> None:
    # Spec K — CLI 옵션이 실제로 KnowledgeStore.query_with_scores(max_per_source=...)까지
    # 전달되는지만 확인한다(균형 조정 로직 자체는 test_knowledge_store.py가 검증).
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr("book_forge.cli.commands.draft_cmd.create_llm", lambda: FakeLLM())

    project_dir = tmp_path / "projects" / "maxsrc-slug"
    part_dir = project_dir / "Part_1_과일학"
    part_dir.mkdir(parents=True)
    (project_dir / "01_목차.md").write_text(
        "```toc\n1|과일학|1|사과 개론\n```\n", encoding="utf-8"
    )
    (part_dir / "Chapter_01_사과_개론.md").write_text(
        "# Chapter 01: 사과 개론\n\n> TODO: 이 챕터를 집필하세요.\n", encoding="utf-8"
    )
    source_file = tmp_path / "source.txt"
    source_file.write_text("사과에 대한 소스입니다", encoding="utf-8")

    captured_kwargs = {}
    original_query = store_module.KnowledgeStore.query_with_scores

    def _spy_query(self, text, top_k=5, *, max_per_source=None):
        captured_kwargs["max_per_source"] = max_per_source
        return original_query(self, text, top_k=top_k, max_per_source=max_per_source)

    monkeypatch.setattr(store_module.KnowledgeStore, "query_with_scores", _spy_query)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "draft", "maxsrc-slug", "1",
            "--source", str(source_file), "-y", "--max-per-source", "2",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured_kwargs["max_per_source"] == 2


def test_draft_max_per_source_defaults_to_none(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr("book_forge.cli.commands.draft_cmd.create_llm", lambda: FakeLLM())

    project_dir = tmp_path / "projects" / "maxsrc-default-slug"
    part_dir = project_dir / "Part_1_과일학"
    part_dir.mkdir(parents=True)
    (project_dir / "01_목차.md").write_text(
        "```toc\n1|과일학|1|사과 개론\n```\n", encoding="utf-8"
    )
    (part_dir / "Chapter_01_사과_개론.md").write_text(
        "# Chapter 01: 사과 개론\n\n> TODO: 이 챕터를 집필하세요.\n", encoding="utf-8"
    )
    source_file = tmp_path / "source.txt"
    source_file.write_text("사과에 대한 소스입니다", encoding="utf-8")

    captured_kwargs = {}
    original_query = store_module.KnowledgeStore.query_with_scores

    def _spy_query(self, text, top_k=5, *, max_per_source=None):
        captured_kwargs["max_per_source"] = max_per_source
        return original_query(self, text, top_k=top_k, max_per_source=max_per_source)

    monkeypatch.setattr(store_module.KnowledgeStore, "query_with_scores", _spy_query)

    runner = CliRunner()
    result = runner.invoke(
        cli, ["draft", "maxsrc-default-slug", "1", "--source", str(source_file), "-y"]
    )

    assert result.exit_code == 0, result.output
    assert captured_kwargs["max_per_source"] is None


def test_cited_url_sources_extracts_unique_urls_in_order() -> None:
    scored = [
        ("# 출처: https://a.example/x\n본문 A", 0.9),
        ("# 출처: https://b.example/y\n본문 B", 0.8),
        ("# 출처: https://a.example/x\n본문 A 이어지는 청크", 0.7),  # 중복 URL
        ("# 파일: local.py\n코드 청크", 0.6),  # 파일 소스는 대상 아님
        ("태그 없는 청크", 0.5),
    ]
    assert _cited_url_sources(scored) == ["https://a.example/x", "https://b.example/y"]


def test_cited_url_sources_empty_when_no_url_sources() -> None:
    scored = [("# 파일: local.py\n코드 청크", 0.9), ("태그 없는 청크", 0.5)]
    assert _cited_url_sources(scored) == []


def test_append_references_section_adds_section_when_urls_present() -> None:
    result = _append_references_section(
        "# Chapter 1: 제목\n\n본문", ["https://a.example", "https://b.example"]
    )
    assert result == (
        "# Chapter 1: 제목\n\n본문\n\n## 참고 자료\n"
        "- https://a.example\n- https://b.example\n"
    )


def test_append_references_section_noop_when_no_urls() -> None:
    original = "# Chapter 1: 제목\n\n본문"
    assert _append_references_section(original, []) == original


def test_draft_appends_references_section_for_url_sources(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr("book_forge.cli.commands.draft_cmd.create_llm", lambda: FakeLLM())

    def _fake_load_source(source, **kwargs):
        return [f"# 출처: {source}\n사과에 대한 웹 페이지 내용입니다"]

    monkeypatch.setattr("book_forge.knowledge.sources.load_source", _fake_load_source)

    project_dir = tmp_path / "projects" / "url-slug"
    part_dir = project_dir / "Part_1_과일학"
    part_dir.mkdir(parents=True)
    (project_dir / "01_목차.md").write_text("```toc\n1|과일학|1|사과 개론\n```\n", encoding="utf-8")
    (part_dir / "Chapter_01_사과_개론.md").write_text(
        "# Chapter 01: 사과 개론\n\n> TODO: 이 챕터를 집필하세요.\n", encoding="utf-8"
    )

    runner = CliRunner()
    result = runner.invoke(
        cli, ["draft", "url-slug", "1", "--source", "https://example.com/apples", "-y"]
    )

    assert result.exit_code == 0, result.output
    chapter_md = (part_dir / "Chapter_01_사과_개론.md").read_text(encoding="utf-8")
    assert "## 참고 자료" in chapter_md
    assert "https://example.com/apples" in chapter_md


def test_draft_without_source_fails_when_no_existing_store(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    project_dir = _make_batch_project(tmp_path)
    assert not (project_dir / "knowledge" / "store.json").exists()

    runner = CliRunner()
    result = runner.invoke(cli, ["draft", "batch-slug", "1"])

    assert result.exit_code != 0
    assert "--source를 최소 1개 지정해야 합니다" in result.output
    assert "book-forge research" in result.output


def test_draft_without_source_uses_existing_store(tmp_path: Path, monkeypatch) -> None:
    # 일반 능력 N — book-forge research가 미리 지식창고를 채워둔 시나리오를
    # 재현: --source 없이도 기존 지식창고만으로 초안이 생성돼야 한다.
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr("book_forge.cli.commands.draft_cmd.create_llm", lambda: FakeLLM())

    project_dir = _make_batch_project(tmp_path)
    store = store_module.KnowledgeStore()
    store.add(["사과에 대한 사전 수집 자료"])
    store.save(store_module.default_store_path(project_dir))

    runner = CliRunner()
    result = runner.invoke(cli, ["draft", "batch-slug", "1", "-y"])

    assert result.exit_code == 0, result.output
    assert "기존 지식창고를 그대로 사용합니다" in result.output
    ch1 = (project_dir / "Part_1_과일학" / "Chapter_01_사과_개론.md").read_text(encoding="utf-8")
    assert "고정된 초안 본문" in ch1


# ── module_reference (일반 능력 T) ──────────────────────────────────────────


def test_build_structure_summary_from_sources_indexes_local_directories(tmp_path: Path) -> None:
    pkg_dir = tmp_path / "mypkg"
    pkg_dir.mkdir()
    (pkg_dir / "a.py").write_text(
        "class Foo:\n    \"\"\"Foo 클래스.\"\"\"\n    def bar(self):\n        pass\n",
        encoding="utf-8",
    )
    summary = _build_structure_summary_from_sources((str(pkg_dir),))
    assert summary is not None
    assert "Foo" in summary


def test_build_structure_summary_from_sources_skips_urls_and_non_directories(tmp_path: Path) -> None:
    text_file = tmp_path / "notes.txt"
    text_file.write_text("텍스트 파일", encoding="utf-8")
    summary = _build_structure_summary_from_sources(
        ("https://example.com/page", str(text_file))
    )
    assert summary is None


def test_build_structure_summary_from_sources_no_sources_returns_none() -> None:
    assert _build_structure_summary_from_sources(()) is None


class _ModuleReferenceLLM:
    model = "fake"

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        return (
            "# Chapter 01: agents 레퍼런스\n\n"
            "| 모듈 | 이름 | 설명 |\n|---|---|---|\n"
            "| a.py | Foo | Foo 클래스 |\n"
        )


def test_draft_module_reference_uses_structure_index_not_rag_chunks(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr(
        "book_forge.cli.commands.draft_cmd.create_llm", lambda: _ModuleReferenceLLM()
    )

    # --source로 줄 실제 코드 저장소 디렉토리 — a.py 하나짜리 최소 패키지.
    pkg_dir = tmp_path / "mypkg"
    pkg_dir.mkdir()
    (pkg_dir / "a.py").write_text(
        "class Foo:\n    \"\"\"Foo 클래스.\"\"\"\n    def bar(self):\n        pass\n",
        encoding="utf-8",
    )

    project_dir = tmp_path / "projects" / "modref-slug"
    part_dir = project_dir / "Part_1_기초"
    part_dir.mkdir(parents=True)
    (project_dir / "01_목차.md").write_text(
        "```toc\n1|기초|1|agents 레퍼런스|module_reference\n```\n", encoding="utf-8"
    )
    (part_dir / "Chapter_01_agents_레퍼런스.md").write_text(
        "# Chapter 01: agents 레퍼런스\n\n> TODO: 이 챕터를 집필하세요.\n", encoding="utf-8"
    )

    runner = CliRunner()
    result = runner.invoke(
        cli, ["draft", "modref-slug", "1", "--source", str(pkg_dir), "--yes"]
    )

    assert result.exit_code == 0, result.output
    assert "구조 인덱스 기반 레퍼런스 생성" in result.output
    # 커버리지 검증기(T)가 실행돼 실증 가능성 검증 줄이 출력됐는지 확인.
    assert "실증 가능성 검증" in result.output
    chapter_md = (part_dir / "Chapter_01_agents_레퍼런스.md").read_text(encoding="utf-8")
    assert "Foo" in chapter_md


def test_draft_module_reference_without_directory_source_falls_back(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr(
        "book_forge.cli.commands.draft_cmd.create_llm", lambda: _ModuleReferenceLLM()
    )

    project_dir = tmp_path / "projects" / "modref-fallback-slug"
    part_dir = project_dir / "Part_1_기초"
    part_dir.mkdir(parents=True)
    (project_dir / "01_목차.md").write_text(
        "```toc\n1|기초|1|agents 레퍼런스|module_reference\n```\n", encoding="utf-8"
    )
    (part_dir / "Chapter_01_agents_레퍼런스.md").write_text(
        "# Chapter 01: agents 레퍼런스\n\n> TODO: 이 챕터를 집필하세요.\n", encoding="utf-8"
    )
    source_file = tmp_path / "notes.txt"
    source_file.write_text("사과에 대한 텍스트 소스입니다", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli, ["draft", "modref-fallback-slug", "1", "--source", str(source_file), "--yes"]
    )

    assert result.exit_code == 0, result.output
    assert "구조 요약을 만들 수 없습니다" in result.output


# 일반 능력 AG — --enable-llm-judge/--judge-model이 build_book_monitor()까지 실제로 전달되는지.
def test_draft_passes_llm_judge_flags_to_monitor(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr("book_forge.cli.commands.draft_cmd.create_llm", lambda: FakeLLM())

    captured_kwargs = {}
    import book_forge.cli.commands.draft_cmd as draft_cmd_module

    original_build_monitor = draft_cmd_module.build_book_monitor

    def _spy_build_monitor(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return original_build_monitor(*args, **kwargs)

    monkeypatch.setattr(draft_cmd_module, "build_book_monitor", _spy_build_monitor)

    project_dir = tmp_path / "projects" / "judge-slug"
    part_dir = project_dir / "Part_1_과일학"
    part_dir.mkdir(parents=True)
    (project_dir / "01_목차.md").write_text("```toc\n1|과일학|1|사과 개론\n```\n", encoding="utf-8")
    (part_dir / "Chapter_01_사과_개론.md").write_text(
        "# Chapter 01: 사과 개론\n\n> TODO: 이 챕터를 집필하세요.\n", encoding="utf-8"
    )
    source_file = tmp_path / "source.txt"
    source_file.write_text("사과에 대한 소스입니다", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "draft", "judge-slug", "1", "--source", str(source_file), "--yes",
            "--enable-llm-judge", "--judge-model", "claude-haiku-4-5-20251001",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured_kwargs.get("enable_llm_judge") is True
    assert captured_kwargs.get("judge_model") == "claude-haiku-4-5-20251001"


def test_draft_llm_judge_defaults_to_disabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr(store_module, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr("book_forge.cli.commands.draft_cmd.create_llm", lambda: FakeLLM())

    captured_kwargs = {}
    import book_forge.cli.commands.draft_cmd as draft_cmd_module

    original_build_monitor = draft_cmd_module.build_book_monitor

    def _spy_build_monitor(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return original_build_monitor(*args, **kwargs)

    monkeypatch.setattr(draft_cmd_module, "build_book_monitor", _spy_build_monitor)

    project_dir = tmp_path / "projects" / "no-judge-slug"
    part_dir = project_dir / "Part_1_과일학"
    part_dir.mkdir(parents=True)
    (project_dir / "01_목차.md").write_text("```toc\n1|과일학|1|사과 개론\n```\n", encoding="utf-8")
    (part_dir / "Chapter_01_사과_개론.md").write_text(
        "# Chapter 01: 사과 개론\n\n> TODO: 이 챕터를 집필하세요.\n", encoding="utf-8"
    )
    source_file = tmp_path / "source.txt"
    source_file.write_text("사과에 대한 소스입니다", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli, ["draft", "no-judge-slug", "1", "--source", str(source_file), "--yes"]
    )

    assert result.exit_code == 0, result.output
    assert captured_kwargs.get("enable_llm_judge") is False
    assert captured_kwargs.get("judge_model") is None
