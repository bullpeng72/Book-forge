"""agents/code_consistency_checker.py — 로컬 코드베이스 대상 검증(일반 능력 I) 테스트.

verify_code_consistency()가 target_package를 로컬 디렉토리로 자동 감지해
verify_code_consistency_local()로 위임하는지, 그리고 그 위임된 로직 자체가
정확한지 검증한다. LLM/네트워크 없이 결정론적(ast 정적 분석 기반).
"""
from pathlib import Path

from book_forge.agents.code_consistency_checker import (
    verify_code_consistency,
    verify_code_consistency_local,
)


def _make_local_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "myproject"
    (project_dir / "agents").mkdir(parents=True)
    (project_dir / "agents" / "worker.py").write_text(
        "import os\n\n\ndef build_worker(name):\n    return name\n\n\n"
        "class Worker:\n    pass\n",
        encoding="utf-8",
    )
    return project_dir


def test_verify_code_consistency_local_passes_for_real_backtick_symbol(tmp_path: Path) -> None:
    project_dir = _make_local_project(tmp_path)
    draft = "`Worker`와 `build_worker`는 실제로 존재하는 심볼입니다."
    result = verify_code_consistency_local(draft, target_dir=project_dir)
    assert result.passed is True
    assert not result.issues


def test_verify_code_consistency_local_catches_nonexistent_backtick_symbol(
    tmp_path: Path,
) -> None:
    project_dir = _make_local_project(tmp_path)
    draft = "`NonExistentThing`이라는 클래스가 있습니다."
    result = verify_code_consistency_local(draft, target_dir=project_dir)
    assert result.passed is False
    assert any("NonExistentThing" in issue for issue in result.issues)


def test_verify_code_consistency_local_checks_import_statements(tmp_path: Path) -> None:
    project_dir = _make_local_project(tmp_path)
    draft = "```python\nfrom myproject.agents.worker import build_worker\n```"
    result = verify_code_consistency_local(draft, target_dir=project_dir)
    assert result.passed is True


def test_verify_code_consistency_local_flags_nonexistent_import(tmp_path: Path) -> None:
    project_dir = _make_local_project(tmp_path)
    draft = "```python\nfrom myproject.agents.worker import nonexistent_func\n```"
    result = verify_code_consistency_local(draft, target_dir=project_dir)
    assert result.passed is False
    assert any("nonexistent_func" in issue for issue in result.issues)


def test_verify_code_consistency_local_matches_when_target_is_subdirectory(
    tmp_path: Path,
) -> None:
    # 실측으로 발견한 케이스: target_dir가 패키지 루트(myproject)가 아니라
    # 그 서브디렉토리(agents)를 가리켜도, import 경로 세그먼트 어디든
    # 일치하면 대조 대상으로 잡아야 한다(첫 세그먼트만 보면 놓침).
    project_dir = _make_local_project(tmp_path)
    subdirectory = project_dir / "agents"
    draft = "```python\nfrom myproject.agents.worker import nonexistent_func\n```"
    result = verify_code_consistency_local(draft, target_dir=subdirectory)
    assert result.passed is False
    assert any("nonexistent_func" in issue for issue in result.issues)


def test_verify_code_consistency_local_ignores_unrelated_imports(tmp_path: Path) -> None:
    project_dir = _make_local_project(tmp_path)
    draft = "```python\nimport os\nfrom pathlib import Path\n```"
    result = verify_code_consistency_local(draft, target_dir=project_dir)
    assert result.passed is True
    assert "대조할 항목이 없습니다" in result.detail


def test_verify_code_consistency_local_fails_when_no_py_modules_found(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    result = verify_code_consistency_local("아무 내용", target_dir=empty_dir)
    assert result.passed is False
    assert "찾지 못했습니다" in result.detail


def test_verify_code_consistency_auto_dispatches_to_local_mode_for_directory(
    tmp_path: Path,
) -> None:
    project_dir = _make_local_project(tmp_path)
    draft = "`Worker`는 실제 클래스입니다."
    result = verify_code_consistency(draft, target_package=str(project_dir))
    assert result.passed is True


def test_verify_code_consistency_still_uses_importlib_for_installed_package_name() -> None:
    # 회귀 방지 — 로컬 모드 추가가 기존 설치 패키지 경로를 깨면 안 된다.
    result = verify_code_consistency(
        "`ScopeConfig`는 실제로 존재합니다.", target_package="agent_evaluator"
    )
    assert result.passed is True
