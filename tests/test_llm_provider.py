"""llm/provider.py create_llm() 팩토리 테스트 — SDK 호출 없이 분기 로직만 검증."""
import pytest

from book_forge.exceptions import LLMProviderError, MissingAPIKeyError, UnsupportedProviderError
from book_forge.llm.provider import OllamaLLM, create_llm


class _FakeOllamaResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


def test_create_llm_missing_openai_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    with pytest.raises(MissingAPIKeyError):
        create_llm()


def test_create_llm_unsupported_provider(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "not-a-real-provider")
    with pytest.raises(UnsupportedProviderError):
        create_llm()


def test_create_llm_ollama_needs_no_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    llm = create_llm()
    assert isinstance(llm, OllamaLLM)
    assert llm.model == "llama3.2"


def test_create_llm_explicit_provider_overrides_env(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    llm = create_llm(provider="ollama", model="custom-model")
    assert isinstance(llm, OllamaLLM)
    assert llm.model == "custom-model"


def test_create_llm_defaults_to_ollama_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    llm = create_llm()
    assert isinstance(llm, OllamaLLM)


def test_ollama_generate_sends_think_false(monkeypatch) -> None:
    # 실측 회귀: qwen3.6:35b-mlx 같은 추론("thinking") 모델은 think=False를
    # 안 보내면 num_predict 예산을 전부 <thinking>에 써버리고 실제 응답
    # 필드는 빈 문자열로 끝난다(done_reason="length") — 챕터 파일이 통째로
    # 빈 채 저장되는 실제 버그를 재현했었다. think=False가 페이로드에
    # 항상 포함되는지 확인한다.
    captured: dict = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return _FakeOllamaResponse({"response": "생성된 답변"})

    import requests

    monkeypatch.setattr(requests, "post", fake_post)

    llm = OllamaLLM(base_url="http://localhost:11434", model="qwen3.6:35b-mlx")
    result = llm.generate("프롬프트", system="시스템", max_tokens=500)

    assert result == "생성된 답변"
    assert captured["json"]["think"] is False
    assert captured["json"]["options"]["num_predict"] == 500


def test_ollama_generate_raises_on_empty_response(monkeypatch) -> None:
    # think=False로도 못 막는 원인(콘텐츠 필터링·네트워크 이상 등)으로 응답이
    # 비어 있을 때, 조용히 ""를 반환하면 @agent_eval이 "완료"로 기록해 Gate C가
    # 실패를 놓치고 챕터 파일이 빈 채 저장된다 — 반드시 예외로 전파돼야 한다.
    def fake_post(url, json, timeout):
        return _FakeOllamaResponse({"response": ""})

    import requests

    monkeypatch.setattr(requests, "post", fake_post)

    llm = OllamaLLM(base_url="http://localhost:11434", model="llama3.2")
    with pytest.raises(LLMProviderError):
        llm.generate("프롬프트")
