"""knowledge/embeddings.py — embed_text()의 컨텍스트 길이 초과 자동 축소 재시도 테스트.

실제 Ollama 호출 없이 requests.post를 fake로 대체한다.
"""
import pytest

from book_forge.knowledge.embeddings import embed_text


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_embed_text_retries_with_truncated_text_on_context_length_error(monkeypatch) -> None:
    calls: list[str] = []

    def fake_post(url, json, timeout):
        calls.append(json["prompt"])
        if len(json["prompt"]) > 10:
            return _FakeResponse(500, {"error": "the input length exceeds the context length"})
        return _FakeResponse(200, {"embedding": [0.1, 0.2]})

    monkeypatch.setattr("requests.post", fake_post)

    result = embed_text("x" * 20)

    assert result == [0.1, 0.2]
    assert len(calls) == 2
    assert len(calls[0]) == 20  # 첫 시도는 원문 그대로
    assert len(calls[1]) == 10  # 재시도는 절반으로 축소


def test_embed_text_does_not_retry_twice(monkeypatch) -> None:
    """축소해도 계속 실패하면 무한 재귀하지 않고 예외를 던진다."""
    calls: list[str] = []

    def fake_post(url, json, timeout):
        calls.append(json["prompt"])
        return _FakeResponse(500, {"error": "the input length exceeds the context length"})

    monkeypatch.setattr("requests.post", fake_post)

    with pytest.raises(RuntimeError):
        embed_text("x" * 20)

    assert len(calls) == 2  # 최초 시도 + 1회 재시도, 그 이상 반복하지 않음


def test_embed_text_raises_on_unrelated_500_error(monkeypatch) -> None:
    def fake_post(url, json, timeout):
        return _FakeResponse(500, {"error": "some other server error"})

    monkeypatch.setattr("requests.post", fake_post)

    with pytest.raises(RuntimeError):
        embed_text("short")


def test_embed_text_raises_on_missing_embedding_field(monkeypatch) -> None:
    def fake_post(url, json, timeout):
        return _FakeResponse(200, {})

    monkeypatch.setattr("requests.post", fake_post)

    with pytest.raises(ValueError, match="embedding"):
        embed_text("short")
