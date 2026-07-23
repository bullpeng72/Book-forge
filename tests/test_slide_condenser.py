"""slide_condenser.py — parse_slide_response() 순수 파싱 테스트 (LLM 호출 없음)."""
from book_forge.agents.slide_condenser import parse_slide_response

WELL_FORMED = """TITLE: 에이전트와 LLM의 차이
BULLET: 단일 호출 vs 멀티스텝 실행
BULLET: 결정론적 vs 비결정론적
BULLET: 평가 방식이 근본적으로 다름
NOTES: 이 슬라이드는 도입부에서 문제의식을 세운다. 이후 섹션에서 구체적 사례를 다룬다."""


def test_parse_slide_response_well_formed() -> None:
    content = parse_slide_response(WELL_FORMED, fallback_title="fallback")
    assert content.title == "에이전트와 LLM의 차이"
    assert len(content.bullets) == 3
    assert "단일 호출" in content.bullets[0]
    assert "도입부" in content.notes


def test_parse_slide_response_caps_bullets_at_five() -> None:
    text = "TITLE: 제목\n" + "\n".join(f"BULLET: 항목{i}" for i in range(8))
    content = parse_slide_response(text, fallback_title="fallback")
    assert len(content.bullets) == 5


def test_parse_slide_response_missing_title_uses_fallback() -> None:
    content = parse_slide_response("BULLET: 항목 하나", fallback_title="원래 제목")
    assert content.title == "원래 제목"


def test_parse_slide_response_no_bullets_falls_back_to_raw_text() -> None:
    content = parse_slide_response("형식을 전혀 지키지 않은 자유 텍스트입니다.", fallback_title="제목")
    assert len(content.bullets) == 1
    assert "형식을 전혀" in content.bullets[0]


def test_parse_slide_response_empty_text_falls_back() -> None:
    content = parse_slide_response("", fallback_title="제목")
    assert content.bullets == ["(내용 없음)"]


def test_parse_slide_response_title_truncated_to_60_chars() -> None:
    long_title = "가" * 100
    content = parse_slide_response(f"TITLE: {long_title}\nBULLET: x", fallback_title="fallback")
    assert len(content.title) == 60
