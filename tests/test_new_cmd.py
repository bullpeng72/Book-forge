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
