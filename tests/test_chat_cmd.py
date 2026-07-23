"""`book-forge chat` 테스트 — CliRunner로 REPL 입력을 스크립트하고, 임베딩/LLM은
결정론적 fake로 대체해 오프라인·빠르게 검증한다.
"""
import json
from pathlib import Path

from click.testing import CliRunner

import book_forge.cli.project_utils as project_utils
import book_forge.knowledge.store as store_module
from book_forge.cli.main import cli


class FakeLLM:
    model = "fake"

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        return "고정된 답변입니다."


def _fake_embed_text(text: str, *, base_url: str = "", model: str = "") -> list[float]:
    return [1.0, 0.0]


def _make_project_with_store(tmp_path: Path) -> Path:
    project_dir = tmp_path / "projects" / "sample-slug"
    knowledge_dir = project_dir / "knowledge"
    knowledge_dir.mkdir(parents=True)
    (knowledge_dir / "store.json").write_text(
        json.dumps({"chunks": ["소스 청크 1"], "vectors": [[1.0, 0.0]]}), encoding="utf-8"
    )
    (project_dir / "00_기획안.md").write_text("# 샘플 책\n\n## 목적\n\n요약.", encoding="utf-8")
    return project_dir


def test_chat_answers_question_and_exits(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr("book_forge.cli.commands.chat_cmd.create_llm", lambda: FakeLLM())
    _make_project_with_store(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ["chat", "sample-slug"], input="질문 있어요\n/exit\n")

    assert result.exit_code == 0
    assert "고정된 답변입니다" in result.output
    # 세션 결과가 eval_results에 저장됐는지
    assert (tmp_path / "projects" / "sample-slug" / "eval_results" / "chat.json").is_file()


def test_chat_missing_store_raises(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    project_dir = tmp_path / "projects" / "empty-slug"
    project_dir.mkdir(parents=True)
    (project_dir / "00_기획안.md").write_text("# 빈 책\n\n## 목적\n\n요약.", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(cli, ["chat", "empty-slug"])

    assert result.exit_code != 0
    assert "지식창고가 없습니다" in result.output


def test_chat_no_matching_chunks_shows_fallback_message(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr("book_forge.cli.commands.chat_cmd.create_llm", lambda: FakeLLM())
    project_dir = _make_project_with_store(tmp_path)
    # 스토어를 빈 상태로 만들어 query_with_scores가 항상 빈 리스트를 반환하게 한다.
    (project_dir / "knowledge" / "store.json").write_text(
        json.dumps({"chunks": [], "vectors": []}), encoding="utf-8"
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["chat", "sample-slug"], input="질문\n/exit\n")

    assert result.exit_code == 0
    assert "관련 내용을 찾지 못했습니다" in result.output
    assert "고정된 답변입니다" not in result.output


class _HistoryEchoLLM:
    """실제 답변 대신 프롬프트를 그대로 반환 — 두 번째 질문에 첫 질문/답이 섞였는지 검증용."""

    model = "fake"

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        return prompt


def test_chat_includes_prior_turn_in_second_question_prompt(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr("book_forge.cli.commands.chat_cmd.create_llm", lambda: _HistoryEchoLLM())
    _make_project_with_store(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli, ["chat", "sample-slug"], input="첫 번째 질문\n두 번째 질문\n/exit\n"
    )

    assert result.exit_code == 0, result.output
    # 두 번째 질문에 대한 응답(프롬프트를 그대로 반환)에 첫 번째 질문/답변이 포함돼야 한다.
    assert "--- 이전 대화 ---" in result.output
    assert "첫 번째 질문" in result.output


def test_chat_prints_conversation_metrics_summary_on_exit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr("book_forge.cli.commands.chat_cmd.create_llm", lambda: FakeLLM())
    _make_project_with_store(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli, ["chat", "sample-slug"], input="첫 번째 질문\n두 번째 질문\n/exit\n"
    )

    assert result.exit_code == 0, result.output
    assert "지속형 상호작용 지표" in result.output
    assert "턴 수: 2" in result.output


def test_chat_session_saved_with_conversation_sessions(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_utils, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "embed_text", _fake_embed_text)
    monkeypatch.setattr("book_forge.cli.commands.chat_cmd.create_llm", lambda: FakeLLM())
    _make_project_with_store(tmp_path)

    runner = CliRunner()
    runner.invoke(cli, ["chat", "sample-slug"], input="질문\n/exit\n")

    saved = json.loads(
        (tmp_path / "projects" / "sample-slug" / "eval_results" / "chat.json").read_text(
            encoding="utf-8"
        )
    )
    sessions = saved["conversation_sessions"]
    assert sessions
    assert sessions[0]["turn_count"] == 1
