"""knowledge/code_index.py — 구조적 코드 인덱싱(일반 능력 H) 테스트.

LLM 미호출 순수 정적 분석(ast)이라 결정론적으로 검증한다.
"""
from pathlib import Path

from book_forge.knowledge.code_index import (
    build_structure_index,
    extract_module_summary,
    format_structure_summary,
)


def test_extract_module_summary_parses_imports_classes_functions() -> None:
    source = '''"""모듈 docstring."""
from __future__ import annotations

import os
from pathlib import Path


class Widget:
    """위젯 클래스."""

    def render(self) -> str:
        ...

    def _internal(self) -> None:
        ...


def build_widget(name: str, size: int) -> Widget:
    """이름과 크기로 위젯을 만든다."""
    return Widget()
'''
    summary = extract_module_summary("widgets.py", source)
    assert summary is not None
    assert summary.path == "widgets.py"
    assert "os" in summary.imports
    assert "pathlib" in summary.imports
    assert len(summary.classes) == 1
    assert summary.classes[0].name == "Widget"
    assert summary.classes[0].docstring == "위젯 클래스."
    assert summary.classes[0].methods == ["render"]  # _internal은 비공개라 제외
    assert len(summary.functions) == 1
    assert summary.functions[0].name == "build_widget"
    assert summary.functions[0].args == ["name", "size"]
    assert summary.functions[0].docstring == "이름과 크기로 위젯을 만든다."


def test_extract_module_summary_captures_class_bases() -> None:
    source = "class Sub(Base1, Base2):\n    pass\n"
    summary = extract_module_summary("sub.py", source)
    assert summary is not None
    assert summary.classes[0].bases == ["Base1", "Base2"]


def test_extract_module_summary_returns_none_on_syntax_error() -> None:
    assert extract_module_summary("broken.py", "def broken(:\n    pass") is None


def test_build_structure_index_walks_directory_and_skips_broken_files(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "good.py").write_text(
        "def hello():\n    pass\n", encoding="utf-8"
    )
    (tmp_path / "pkg" / "bad.py").write_text("def broken(:\n", encoding="utf-8")
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")

    summaries = build_structure_index(tmp_path)
    paths = {s.path for s in summaries}
    assert "pkg/good.py" in paths or "pkg\\good.py" in paths  # OS별 구분자
    assert not any("bad.py" in p for p in paths)  # 문법 오류 파일은 조용히 제외


def test_build_structure_index_skips_pycache_and_git(tmp_path: Path) -> None:
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "cached.py").write_text("x = 1", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "hook.py").write_text("x = 1", encoding="utf-8")
    (tmp_path / "real.py").write_text("x = 1", encoding="utf-8")

    summaries = build_structure_index(tmp_path)
    paths = [s.path for s in summaries]
    assert paths == ["real.py"]


def test_format_structure_summary_classifies_internal_vs_external_imports(
    tmp_path: Path,
) -> None:
    # tmp_path 자신의 이름이 내부 판정 기준이 되므로, 알려진 이름으로 디렉토리를 만든다.
    project_dir = tmp_path / "myproject"
    (project_dir / "agents").mkdir(parents=True)
    (project_dir / "agents" / "worker.py").write_text(
        "import os\nfrom myproject.agents.helper import Helper\n", encoding="utf-8"
    )

    summaries = build_structure_index(project_dir)
    text = format_structure_summary(summaries, project_dir)

    assert "내부 의존: myproject.agents.helper" in text
    assert "외부 의존: os" in text


def test_format_structure_summary_returns_empty_string_for_no_summaries() -> None:
    assert format_structure_summary([], Path("/nonexistent")) == ""


def test_format_structure_summary_includes_module_header_and_docstrings(
    tmp_path: Path,
) -> None:
    (tmp_path / "m.py").write_text(
        'def greet(name):\n    """인사말을 만든다."""\n    return f"hi {name}"\n',
        encoding="utf-8",
    )
    summaries = build_structure_index(tmp_path)
    text = format_structure_summary(summaries, tmp_path)

    assert "## m.py" in text
    assert "함수 `greet(name)` — 인사말을 만든다." in text
    assert "정적 분석" in text  # 청크 태그 — 검색 결과 출처 구분용
