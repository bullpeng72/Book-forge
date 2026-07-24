"""demonstration_verifier.py — D(실증 가능성 게이트) 생성 후 정적 검증 테스트.

LLM/네트워크 없이 순수 함수만 검증한다(ast.parse/정규식 기반이라 결정론적).
"""
from book_forge.agents.demonstration_verifier import (
    verify_capstone,
    verify_demonstration,
    verify_diagram,
    verify_exercise_code,
    verify_module_reference_coverage,
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


# ── diagram 그라운딩(일반 능력 U, 옵트인) ────────────────────────────────────


def test_verify_diagram_grounding_passes_when_nodes_match_source() -> None:
    # 실제 LLM 다이어그램 출력과 같은 대괄호 라벨 문법(예: A[PlannerAgent])을 쓴다 —
    # _MERMAID_NODE_LABEL_RE는 대괄호 라벨만 노드로 인식한다.
    draft = """```mermaid
graph TD
    A[PlannerAgent] --> B[ChatAgent]
```
"""
    sources = "## planner.py\n- 클래스 `PlannerAgent`\n## chat_agent.py\n- 클래스 `ChatAgent`"
    result = verify_diagram(draft, sources)
    assert result.passed is True


def test_verify_diagram_grounding_fails_when_nodes_are_invented() -> None:
    draft = """```mermaid
graph TD
    A[CompletelyMadeUpNode] --> B[AnotherFakeNode]
```
"""
    sources = "## planner.py\n- 클래스 `PlannerAgent`\n## chat_agent.py\n- 클래스 `ChatAgent`"
    result = verify_diagram(draft, sources)
    assert result.passed is False
    assert any("소스에서" in issue for issue in result.issues)


def test_verify_diagram_grounding_skipped_when_no_sources_given() -> None:
    # 하위 호환: sources_text를 안 주면(기존 호출부) 그라운딩 검사를 건너뛴다.
    draft = """```mermaid
graph TD
    A[CompletelyMadeUpNode] --> B[AnotherFakeNode]
```
"""
    result = verify_diagram(draft)
    assert result.passed is True


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


# ── module_reference (T: H가 나열한 항목이 전부 본문에 등장하는지) ──────────


_SAMPLE_STRUCTURE_SUMMARY = (
    "# 프로젝트 구조 요약 (정적 분석, 2개 모듈)\n\n"
    "## planner.py\n- 클래스 `PlannerAgent` — 기획안을 생성한다\n"
    "## chat_agent.py\n- 클래스 `ChatAgent` — 질문에 답한다\n"
    "- 함수 `build_answer_question(llm, monitor)` — 답변 함수를 만든다\n"
)


def test_verify_module_reference_coverage_passes_when_all_names_present() -> None:
    draft = (
        "| 모듈 | 이름 |\n|---|---|\n"
        "| planner.py | PlannerAgent |\n"
        "| chat_agent.py | ChatAgent |\n"
        "| chat_agent.py | build_answer_question |\n"
    )
    result = verify_module_reference_coverage(draft, _SAMPLE_STRUCTURE_SUMMARY)
    assert result.passed is True
    assert result.content_type == "module_reference"
    assert not result.issues


def test_verify_module_reference_coverage_fails_when_names_missing() -> None:
    draft = "| 모듈 | 이름 |\n|---|---|\n| planner.py | PlannerAgent |\n"
    result = verify_module_reference_coverage(draft, _SAMPLE_STRUCTURE_SUMMARY)
    assert result.passed is False
    assert any("ChatAgent" in issue for issue in result.issues)
    assert any("build_answer_question" in issue for issue in result.issues)


def test_verify_module_reference_coverage_no_items_in_summary_passes() -> None:
    result = verify_module_reference_coverage("아무 본문", "구조 요약에 항목이 없음")
    assert result.passed is True
    assert "찾지 못했습니다" in result.detail


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

    module_ref_draft = "| 모듈 | 이름 |\n|---|---|\n| planner.py | PlannerAgent |\n"
    assert verify_demonstration(
        "module_reference", module_ref_draft, "- 클래스 `PlannerAgent`"
    ).content_type == "module_reference"


def test_verify_demonstration_returns_none_for_narrative_and_unknown() -> None:
    assert verify_demonstration("narrative", "본문", "소스") is None
    assert verify_demonstration(None, "본문", "소스") is None
    assert verify_demonstration("unknown_type", "본문", "소스") is None


# ── capstone (빈 템플릿 + 별도 정답 대조) ───────────────────────────────────


def test_verify_capstone_passes_with_todo_template_and_complete_solution() -> None:
    template = "```python\ndef add(a, b):\n    # TODO: 구현하세요\n    pass\n```"
    solution = "```python\ndef add(a, b):\n    return a + b\n```"
    result = verify_capstone(template, solution)
    assert result.passed is True
    assert result.content_type == "capstone"
    assert not result.issues


def test_verify_capstone_fails_when_solution_missing() -> None:
    template = "```python\ndef add(a, b):\n    pass\n```"
    result = verify_capstone(template, "")
    assert result.passed is False
    assert "정답이 생성되지 않았습니다" in result.detail


def test_verify_capstone_fails_when_template_has_no_todo() -> None:
    # 템플릿에 TODO가 없으면 이미 답이 채워진 것처럼 보인다 — 검증 실패.
    template = "```python\ndef add(a, b):\n    return a + b\n```"
    solution = "```python\ndef add(a, b):\n    return a + b\n```"
    result = verify_capstone(template, solution)
    assert result.passed is False
    assert any("TODO 마커가 없습니다" in issue for issue in result.issues)


def test_verify_capstone_fails_when_solution_still_has_todo() -> None:
    template = "```python\ndef add(a, b):\n    # TODO\n    pass\n```"
    solution = "```python\ndef add(a, b):\n    # TODO: 아직 안 끝남\n    pass\n```"
    result = verify_capstone(template, solution)
    assert result.passed is False
    assert any("TODO가 남아있습니다" in issue for issue in result.issues)


def test_verify_capstone_fails_on_syntax_error_in_either_side() -> None:
    template = "```python\ndef add(a, b:\n    # TODO\n    pass\n```"
    solution = "```python\ndef add(a, b):\n    return a + b\n```"
    result = verify_capstone(template, solution)
    assert result.passed is False
    assert any("템플릿 코드 블록" in issue and "문법 오류" in issue for issue in result.issues)


def test_verify_capstone_fails_when_no_code_blocks_present() -> None:
    result = verify_capstone("서술형 텍스트만 있음", "서술형 텍스트만 있음")
    assert result.passed is False
    assert any("템플릿에 python 코드 블록이 없습니다" in issue for issue in result.issues)
    assert any("정답에 python 코드 블록이 없습니다" in issue for issue in result.issues)
