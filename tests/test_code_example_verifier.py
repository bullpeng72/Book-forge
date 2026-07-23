"""agents/code_example_verifier.py — verify_code_execution() 테스트.

실제 subprocess를 띄우므로 다른 검증기 테스트보다 느리지만(각 케이스 ~0.1-1초),
LLM/네트워크는 쓰지 않는다 — 순수 인터프리터 실행 검증.
"""
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
