"""demonstration_verifier.py — D(실증 가능성 게이트) 생성 후 정적 검증 테스트.

LLM/네트워크 없이 순수 함수만 검증한다(ast.parse/정규식 기반이라 결정론적).
"""
from book_forge.agents.demonstration_verifier import (
    verify_demonstration,
    verify_diagram,
    verify_exercise_code,
    verify_reference_table,
)

# ── exercise (python 코드 문법 검증) ──────────────────────────────────────


def test_verify_exercise_code_passes_with_valid_python() -> None:
    draft = """# Chapter 1

## 실습

```python
def add(a, b):
    return a + b
```
"""
    result = verify_exercise_code(draft)
    assert result.passed is True
    assert result.content_type == "exercise"
    assert not result.issues


def test_verify_exercise_code_fails_with_no_code_block() -> None:
    result = verify_exercise_code("# Chapter 1\n\n서술형 본문만 있음.")
    assert result.passed is False
    assert "없습니다" in result.detail


def test_verify_exercise_code_fails_with_syntax_error() -> None:
    draft = """```python
def broken(:
    pass
```
"""
    result = verify_exercise_code(draft)
    assert result.passed is False
    assert len(result.issues) == 1
    assert "문법 오류" in result.issues[0]


def test_verify_exercise_code_checks_all_blocks() -> None:
    draft = """```python
def ok():
    return 1
```

```python
def bad(:
    pass
```
"""
    result = verify_exercise_code(draft)
    assert result.passed is False
    assert "2개 중 1개" in result.detail


# ── diagram (mermaid 구조 검증) ────────────────────────────────────────────


def test_verify_diagram_passes_with_valid_mermaid() -> None:
    draft = """# Chapter 1

```mermaid
graph TD
    A[시작] --> B[끝]
```
"""
    result = verify_diagram(draft)
    assert result.passed is True
    assert result.content_type == "diagram"


def test_verify_diagram_fails_with_no_mermaid_block() -> None:
    result = verify_diagram("# Chapter 1\n\n다이어그램 없음.")
    assert result.passed is False
    assert "없습니다" in result.detail


def test_verify_diagram_fails_with_unknown_diagram_type() -> None:
    draft = """```mermaid
notarealtype foo --> bar
```
"""
    result = verify_diagram(draft)
    assert result.passed is False
    assert "알려진 mermaid 타입" in result.issues[0]


def test_verify_diagram_fails_with_empty_body() -> None:
    draft = """```mermaid
graph TD
```
"""
    result = verify_diagram(draft)
    assert result.passed is False
    assert "비어 있음" in result.issues[0]


# ── reference_table (소스-표 값 대조) ──────────────────────────────────────


def test_verify_reference_table_passes_when_values_in_source() -> None:
    sources = "AgentCoordinationTracker는 Gate F에 기여한다. ConsensusConfig는 합의 방식을 설정한다."
    draft = """| 트래커 | Gate |
|---|---|
| AgentCoordinationTracker | Gate F |
| ConsensusConfig | Gate F |
"""
    result = verify_reference_table(draft, sources)
    assert result.passed is True
    assert result.content_type == "reference_table"


def test_verify_reference_table_fails_when_values_not_in_source() -> None:
    sources = "관련 없는 다른 내용입니다."
    draft = """| 트래커 | Gate |
|---|---|
| 완전히지어낸트래커이름 | 완전히지어낸게이트 |
"""
    result = verify_reference_table(draft, sources)
    assert result.passed is False
    assert "소스 대조 비율" in result.issues[0]


def test_verify_reference_table_fails_with_no_table() -> None:
    result = verify_reference_table("# Chapter 1\n\n표가 없음.", "소스")
    assert result.passed is False
    assert "없습니다" in result.detail


# ── dispatcher ─────────────────────────────────────────────────────────────


def test_verify_demonstration_dispatches_by_content_type() -> None:
    exercise_draft = "```python\nx = 1\n```"
    assert verify_demonstration("exercise", exercise_draft, "").content_type == "exercise"

    diagram_draft = "```mermaid\ngraph TD\n    A --> B\n```"
    assert verify_demonstration("diagram", diagram_draft, "").content_type == "diagram"

    table_draft = "| a | b |\n|---|---|\n| x | y |\n"
    assert verify_demonstration("reference_table", table_draft, "x y").content_type == (
        "reference_table"
    )


def test_verify_demonstration_returns_none_for_narrative_and_unknown() -> None:
    assert verify_demonstration("narrative", "본문", "소스") is None
    assert verify_demonstration(None, "본문", "소스") is None
    assert verify_demonstration("unknown_type", "본문", "소스") is None
