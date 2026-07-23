"""agents/capstone_generator.py — build_generate_capstone()/parse_capstone_response()
오프라인 테스트 (FakeLLM, 실제 Ollama 없음)."""
from pathlib import Path

from book_forge.agents.capstone_generator import build_generate_capstone, parse_capstone_response
from book_forge.eval.monitor import build_book_monitor

_RAW_RESPONSE = """=== TEMPLATE ===
# Chapter 1: 리스트 다루기

## 목표
리스트 조작을 익힌다.

## 과제
add_item 함수를 완성하세요.

## 시작 코드
```python
def add_item(lst, item):
    # TODO: item을 lst에 추가하고 반환하세요
    pass
```

=== SOLUTION ===
# Chapter 1: 리스트 다루기 — 모범 정답

## 모범 정답
```python
def add_item(lst, item):
    lst.append(item)
    return lst
```

## 해설
append()는 리스트 끝에 원소를 추가합니다."""


class FakeLLM:
    model = "fake"

    def generate(self, prompt: str, *, system=None, max_tokens=4000) -> str:
        assert "테스트 챕터" in prompt
        assert "소스 발췌문" in prompt
        assert "=== TEMPLATE ===" in prompt  # 프롬프트가 구분자 형식을 요구
        return _RAW_RESPONSE


def test_generate_capstone_returns_raw_response_with_markers(tmp_path: Path) -> None:
    monitor = build_book_monitor(output_dir=str(tmp_path / "eval_results"))
    generate = build_generate_capstone(FakeLLM(), monitor)

    result = generate(
        chapter_title="테스트 챕터",
        chapter_no=1,
        sources="소스 발췌문 1\n\n소스 발췌문 2",
        ground_truth="테스트 챕터",
    )

    assert "=== TEMPLATE ===" in result
    assert "=== SOLUTION ===" in result


def test_parse_capstone_response_splits_template_and_solution() -> None:
    template, solution = parse_capstone_response(_RAW_RESPONSE)

    assert "# Chapter 1: 리스트 다루기" in template
    assert "TODO" in template
    assert "=== SOLUTION ===" not in template

    assert "모범 정답" in solution
    assert "lst.append(item)" in solution
    assert "TODO" not in solution


def test_parse_capstone_response_falls_back_safely_without_markers() -> None:
    template, solution = parse_capstone_response("구분자 없이 그냥 텍스트만 있는 응답입니다.")
    assert template == "구분자 없이 그냥 텍스트만 있는 응답입니다."
    assert solution == ""


def test_parse_capstone_response_falls_back_when_markers_reversed() -> None:
    reversed_raw = "=== SOLUTION ===\n정답 먼저\n\n=== TEMPLATE ===\n템플릿 나중"
    template, solution = parse_capstone_response(reversed_raw)
    assert solution == ""
    assert template == reversed_raw
