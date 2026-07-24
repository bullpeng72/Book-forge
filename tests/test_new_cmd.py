"""`book-forge new` 테스트 — 특히 --source 통합(스캐폴딩 직후 자동 배치 초안).

LLM/임베딩은 결정론적 fake로 대체해 오프라인·빠르게 검증한다. 저자 승인 루프는
빈 입력(Enter) 두 번으로 기획안·목차를 즉시 승인한다.
"""
from pathlib import Path

from click.testing import CliRunner

import book_forge.config as config_module
import book_forge.knowledge.store as store_module
from book_forge.cli.main import cli

TOC_RESPONSE = """## Part 1. 기초
- Chapter 1. 서론
- Chapter 2. 심화

```toc
1|기초|1|서론
1|기초|2|심화
```
"""


class ScriptedLLM:
    model = "fake"

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        if "목차를 설계" in prompt or "```toc 코드 블록을 반드시" in prompt:
            return TOC_RESPONSE
        if "참고 소스 발췌" in prompt:
            return "# 자동 생성된 챕터\n\n고정된 자동 초안 본문입니다."
        return "## 목적\n\n요약입니다.\n\n## 대상 독자\n\n누구나."


def _fake_embed(*args, **kwargs):
    return [1.0]  # 항상 완전 일치 — 커버리지 임계값을 확실히 통과시켜 배치 로직만 검증


def test_new_without_source_does_not_auto_draft(tmp_path: Path, monkeypatch) -> None:
    # new_cmd.py는 project_utils가 아니라 config.ensure_project_dir()을 직접 쓴다 —
    # get_data_dir()의 바인딩이 모듈마다 따로라 config_module 쪽을 패치해야 한다
    # (project_utils.get_data_dir을 패치해도 이 경로엔 영향이 없다, 실측 확인).
    monkeypatch.setattr(config_module, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("book_forge.cli.commands.new_cmd.create_llm", lambda: ScriptedLLM())

    runner = CliRunner()
    result = runner.invoke(cli, ["new", "테스트북"], input="\n\n")

    assert result.exit_code == 0, result.output
    assert "집필하세요" in result.output
    assert "일괄 생성 요약" not in result.output

    project_dir = tmp_path / "projects" / "테스트북"
    ch1 = (project_dir / "Part_1_기초" / "Chapter_01_서론.md").read_text(encoding="utf-8")
    assert "TODO" in ch1  # --source 없었으니 스텁 그대로


def test_new_with_source_auto_drafts_all_chapters(tmp_path: Path, monkeypatch) -> None:
    # new_cmd.py는 project_utils가 아니라 config.ensure_project_dir()을 직접 쓴다 —
    # get_data_dir()의 바인딩이 모듈마다 따로라 config_module 쪽을 패치해야 한다
    # (project_utils.get_data_dir을 패치해도 이 경로엔 영향이 없다, 실측 확인).
    monkeypatch.setattr(config_module, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("book_forge.cli.commands.new_cmd.create_llm", lambda: ScriptedLLM())
    monkeypatch.setattr(store_module, "embed_text", _fake_embed)
    monkeypatch.setattr(store_module, "embed_texts", lambda texts, **kw: [[1.0] for _ in texts])

    source_file = tmp_path / "source.txt"
    source_file.write_text("배경 지식 소스입니다.", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli, ["new", "자동북", "--source", str(source_file)], input="\n\n"
    )

    assert result.exit_code == 0, result.output
    assert "일괄 생성 요약" in result.output
    assert "생성 2개, 건너뜀 0개" in result.output

    project_dir = tmp_path / "projects" / "자동북"
    ch1 = (project_dir / "Part_1_기초" / "Chapter_01_서론.md").read_text(encoding="utf-8")
    ch2 = (project_dir / "Part_1_기초" / "Chapter_02_심화.md").read_text(encoding="utf-8")
    assert "고정된 자동 초안 본문" in ch1
    assert "고정된 자동 초안 본문" in ch2

    # E: 지식창고가 프로젝트에 영속화됐는지
    assert (project_dir / "knowledge" / "store.json").is_file()


# 일반 능력 S(SPEC.md 2부) — --source에 코드 저장소 디렉토리가 있으면 목차
# 설계 프롬프트에 실제 구조 요약이 반영돼야 한다(RAG 배치 초안과는 별개 검증).
class _StructureAwareScriptedLLM:
    model = "fake"

    def __init__(self) -> None:
        self.toc_prompts: list[str] = []

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        if "목차를 설계" in prompt or "```toc 코드 블록을 반드시" in prompt:
            self.toc_prompts.append(prompt)
            return TOC_RESPONSE
        if "참고 소스 발췌" in prompt:
            return "# 자동 생성된 챕터\n\n고정된 자동 초안 본문입니다."
        return "## 목적\n\n요약입니다.\n\n## 대상 독자\n\n누구나."


def test_new_with_code_repo_source_injects_structure_into_toc_prompt(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(config_module, "get_data_dir", lambda: tmp_path)
    llm = _StructureAwareScriptedLLM()
    monkeypatch.setattr("book_forge.cli.commands.new_cmd.create_llm", lambda: llm)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed)
    monkeypatch.setattr(store_module, "embed_texts", lambda texts, **kw: [[1.0] for _ in texts])

    pkg_dir = tmp_path / "mypkg"
    pkg_dir.mkdir()
    (pkg_dir / "a.py").write_text(
        "class Foo:\n    \"\"\"Foo 클래스.\"\"\"\n    def bar(self):\n        pass\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        cli, ["new", "구조인지북", "--source", str(pkg_dir)], input="\n\n"
    )

    assert result.exit_code == 0, result.output
    assert "구조를 미리 분석했습니다" in result.output
    assert len(llm.toc_prompts) == 1
    assert "실제 코드 구조" in llm.toc_prompts[0]
    assert "Foo" in llm.toc_prompts[0]


def test_new_with_non_code_source_does_not_inject_structure(
    tmp_path: Path, monkeypatch
) -> None:
    # PDF/텍스트 파일만 준 경우(코드 저장소 디렉토리가 없음) — 구조 요약을
    # 못 만들므로 기존 프롬프트 그대로(하위 호환).
    monkeypatch.setattr(config_module, "get_data_dir", lambda: tmp_path)
    llm = _StructureAwareScriptedLLM()
    monkeypatch.setattr("book_forge.cli.commands.new_cmd.create_llm", lambda: llm)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed)
    monkeypatch.setattr(store_module, "embed_texts", lambda texts, **kw: [[1.0] for _ in texts])

    source_file = tmp_path / "source.txt"
    source_file.write_text("배경 지식 소스입니다.", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli, ["new", "비코드북", "--source", str(source_file)], input="\n\n"
    )

    assert result.exit_code == 0, result.output
    assert "구조를 미리 분석했습니다" not in result.output
    assert "실제 코드 구조" not in llm.toc_prompts[0]


# 일반 능력 AH — 같은 제목(슬러그)으로 book-forge new를 다시 실행하면
# 기존 기획안/목차를 경고 없이 덮어쓰던 문제(실측 확인)를 고쳤다.
def test_new_prompts_before_overwriting_existing_project(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(config_module, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("book_forge.cli.commands.new_cmd.create_llm", lambda: ScriptedLLM())

    runner = CliRunner()
    first = runner.invoke(cli, ["new", "재사용북"], input="\n\n")
    assert first.exit_code == 0, first.output

    proposal_path = tmp_path / "projects" / "재사용북" / "00_기획안.md"
    original_content = proposal_path.read_text(encoding="utf-8")

    second = runner.invoke(cli, ["new", "재사용북"], input="\n")  # 확인 프롬프트에 빈 입력=거부
    assert second.exit_code == 0, second.output
    assert "이미 존재하는 프로젝트입니다" in second.output
    assert "취소했습니다" in second.output
    assert proposal_path.read_text(encoding="utf-8") == original_content  # 덮어쓰지 않음


def test_new_overwrites_existing_project_when_confirmed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(config_module, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("book_forge.cli.commands.new_cmd.create_llm", lambda: ScriptedLLM())

    runner = CliRunner()
    runner.invoke(cli, ["new", "재사용북2"], input="\n\n")

    result = runner.invoke(cli, ["new", "재사용북2"], input="y\n\n\n")
    assert result.exit_code == 0, result.output
    assert "✅ 기획안 확정" in result.output


def test_new_force_skips_overwrite_confirmation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(config_module, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("book_forge.cli.commands.new_cmd.create_llm", lambda: ScriptedLLM())

    runner = CliRunner()
    runner.invoke(cli, ["new", "재사용북3"], input="\n\n")

    result = runner.invoke(cli, ["new", "재사용북3", "--force"], input="\n\n")
    assert result.exit_code == 0, result.output
    assert "이미 존재하는 프로젝트입니다" not in result.output
    assert "✅ 기획안 확정" in result.output


# 일반 능력 AI — --author/--license-notice/--edition이 front_matter.json으로 저장되는지.
def test_new_saves_front_matter_when_author_given(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(config_module, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("book_forge.cli.commands.new_cmd.create_llm", lambda: ScriptedLLM())

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "new", "저자표기북", "--author", "홍길동",
            "--license-notice", "CC BY-NC 4.0", "--edition", "1판",
        ],
        input="\n\n",
    )
    assert result.exit_code == 0, result.output

    from book_forge.publish.front_matter import load_front_matter

    front_matter = load_front_matter(tmp_path / "projects" / "저자표기북")
    assert front_matter.author == "홍길동"
    assert front_matter.license_notice == "CC BY-NC 4.0"
    assert front_matter.edition == "1판"


def test_new_no_front_matter_file_without_author_options(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(config_module, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("book_forge.cli.commands.new_cmd.create_llm", lambda: ScriptedLLM())

    runner = CliRunner()
    runner.invoke(cli, ["new", "저자미표기북"], input="\n\n")

    from book_forge.publish.front_matter import front_matter_path

    assert not front_matter_path(tmp_path / "projects" / "저자미표기북").exists()


# 일반 능력 AG — --enable-llm-judge/--judge-model이 build_book_monitor()까지 실제로 전달되는지.
def test_new_passes_llm_judge_flags_to_monitor(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(config_module, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("book_forge.cli.commands.new_cmd.create_llm", lambda: ScriptedLLM())

    captured_kwargs = {}
    import book_forge.cli.commands.new_cmd as new_cmd_module

    original_build_monitor = new_cmd_module.build_book_monitor

    def _spy_build_monitor(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return original_build_monitor(*args, **kwargs)

    monkeypatch.setattr(new_cmd_module, "build_book_monitor", _spy_build_monitor)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["new", "저지북", "--enable-llm-judge", "--judge-model", "claude-haiku-4-5-20251001"],
        input="\n\n",
    )

    assert result.exit_code == 0, result.output
    assert captured_kwargs.get("enable_llm_judge") is True
    assert captured_kwargs.get("judge_model") == "claude-haiku-4-5-20251001"
