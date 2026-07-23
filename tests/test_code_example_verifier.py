"""agents/code_example_verifier.py — verify_code_execution() 테스트.

실제 subprocess를 띄우므로 다른 검증기 테스트보다 느리지만(각 케이스 ~0.1-1초),
LLM/네트워크는 쓰지 않는다 — 순수 인터프리터 실행 검증.
"""
from pathlib import Path

from book_forge.agents.code_example_verifier import verify_code_execution


def test_verify_code_execution_passes_for_correct_code() -> None:
    draft = """# Chapter

```python
def add(a, b):
    return a + b

assert add(1, 2) == 3
```
"""
    result = verify_code_execution(draft)
    assert result.passed is True
    assert result.content_type == "code_execution"
    assert not result.issues


def test_verify_code_execution_fails_on_runtime_error() -> None:
    draft = """```python
def add(a, b):
    return a + b

assert add(1, 2) == 5
```
"""
    result = verify_code_execution(draft)
    assert result.passed is False
    assert len(result.issues) == 1
    assert "AssertionError" in result.issues[0]


def test_verify_code_execution_fails_on_import_error() -> None:
    draft = """```python
from agent_evaluator import NonExistentThing
```
"""
    result = verify_code_execution(draft)
    assert result.passed is False
    assert "ImportError" in result.issues[0]


def test_verify_code_execution_passes_when_no_code_blocks() -> None:
    result = verify_code_execution("# Chapter\n\n서술형 텍스트만 있음.")
    assert result.passed is True
    assert "없습니다" in result.detail


def test_verify_code_execution_checks_all_blocks_independently() -> None:
    draft = """```python
x = 1
```

```python
raise ValueError("boom")
```
"""
    result = verify_code_execution(draft)
    assert result.passed is False
    assert "2개 중 1개" in result.detail
    assert len(result.issues) == 1
    assert "ValueError" in result.issues[0]


def test_verify_code_execution_times_out_long_running_code() -> None:
    draft = """```python
import time
time.sleep(5)
```
"""
    result = verify_code_execution(draft, timeout=0.5)
    assert result.passed is False
    assert "초과" in result.issues[0]


# ── 로컬 코드베이스 대상(일반 능력 I) — PYTHONPATH 주입 ─────────────────────


def test_verify_code_execution_resolves_local_import_via_extra_pythonpath(
    tmp_path: Path,
) -> None:
    (tmp_path / "local_pkg.py").write_text("VALUE = 42\n", encoding="utf-8")
    draft = """```python
from local_pkg import VALUE
assert VALUE == 42
```
"""
    result = verify_code_execution(draft, extra_pythonpath=tmp_path)
    assert result.passed is True


def test_verify_code_execution_fails_local_import_without_extra_pythonpath(
    tmp_path: Path,
) -> None:
    (tmp_path / "local_pkg.py").write_text("VALUE = 42\n", encoding="utf-8")
    draft = """```python
from local_pkg import VALUE
```
"""
    result = verify_code_execution(draft)
    assert result.passed is False
    assert "ModuleNotFoundError" in result.issues[0] or "ImportError" in result.issues[0]


def test_verify_code_execution_accepts_relative_extra_pythonpath(
    tmp_path: Path, monkeypatch
) -> None:
    # 실측으로 발견한 회귀 케이스: subprocess의 cwd가 임시 디렉토리라, 상대
    # 경로를 절대 경로로 정규화하지 않으면 PYTHONPATH가 엉뚱한 곳을 가리킨다.
    (tmp_path / "local_pkg.py").write_text("VALUE = 7\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    draft = """```python
from local_pkg import VALUE
assert VALUE == 7
```
"""
    result = verify_code_execution(draft, extra_pythonpath=Path("."))
    assert result.passed is True
