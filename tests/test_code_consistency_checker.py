"""agents/code_consistency_checker.py — verify_code_consistency() 테스트.

실제 agent_evaluator 패키지(테스트 환경에 이미 설치됨)를 대상 패키지로 써서
검증한다 — LLM 호출 없이 결정론적이다. ScopeConfig.allowed_tools는 이 프로젝트
CLAUDE.md에 기록된 실제 회귀 시나리오(dataclass의 default_factory 필드는
hasattr()로 못 잡는다)를 그대로 재현하는 케이스라 의도적으로 포함했다.
"""
from book_forge.agents.code_consistency_checker import verify_code_consistency


def test_verify_code_consistency_passes_for_real_imports_and_symbols() -> None:
    draft = """# Chapter

```python
from agent_evaluator import ScopeConfig, SLAConfig

config = ScopeConfig(allowed_tools=["search"])
```

`ScopeConfig`는 도구 이름 기반이며 `ScopeConfig.allowed_tools` 필드로 허용 도구를
지정합니다."""
    result = verify_code_consistency(draft, target_package="agent_evaluator")
    assert result.passed is True
    assert result.content_type == "code_consistency"
    assert not result.issues


def test_verify_code_consistency_catches_nonexistent_import() -> None:
    draft = """```python
from agent_evaluator import NonExistentConfig
```"""
    result = verify_code_consistency(draft, target_package="agent_evaluator")
    assert result.passed is False
    assert any("NonExistentConfig" in issue for issue in result.issues)


def test_verify_code_consistency_catches_nonexistent_field_reference() -> None:
    # 실제 회귀 재현: ScopeConfig는 tool-name 기반이라 path 필드가 없다.
    draft = "`ScopeConfig`는 `ScopeConfig.path`로 파일 경로를 제한합니다."
    result = verify_code_consistency(draft, target_package="agent_evaluator")
    assert result.passed is False
    assert any("ScopeConfig.path" in issue for issue in result.issues)


def test_verify_code_consistency_resolves_default_factory_dataclass_fields() -> None:
    # hasattr()만 쓰면 default_factory 필드가 거짓 음성으로 나온다(회귀 방지).
    draft = "`ScopeConfig.allowed_tools`와 `ScopeConfig.forbidden_tools`는 모두 실제 필드입니다."
    result = verify_code_consistency(draft, target_package="agent_evaluator")
    assert result.passed is True
    assert not result.issues


def test_verify_code_consistency_ignores_python_builtins() -> None:
    # 실측 회귀: "음수인 경우 None으로 보정됩니다" 같은 정상 문장에서 `None`이
    # target_package 소속이 아니라며 오탐으로 잡혔었다.
    draft = (
        "`max_tool_calls`가 음수인 경우 `None`으로 보정됩니다. "
        "`ValueError`나 `TypeError`가 발생할 수도 있습니다."
    )
    result = verify_code_consistency(draft, target_package="agent_evaluator")
    assert result.passed is True
    assert "대조할 항목이 없습니다" in result.detail


def test_verify_code_consistency_ignores_unrelated_uppercase_acronyms() -> None:
    draft = "URL이나 PDF, API 같은 두문자어는 검증 대상이 아닙니다."
    result = verify_code_consistency(draft, target_package="agent_evaluator")
    assert result.passed is True
    assert "대조할 항목이 없습니다" in result.detail


def test_verify_code_consistency_ignores_stdlib_imports() -> None:
    draft = """```python
import os
from pathlib import Path
```"""
    result = verify_code_consistency(draft, target_package="agent_evaluator")
    assert result.passed is True
    assert "대조할 항목이 없습니다" in result.detail


def test_verify_code_consistency_reports_import_error_for_unknown_package() -> None:
    result = verify_code_consistency("아무 내용", target_package="이런_패키지는_없다_xyz")
    assert result.passed is False
    assert "import할 수 없습니다" in result.detail
