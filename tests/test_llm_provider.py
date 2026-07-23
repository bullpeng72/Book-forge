"""llm/provider.py create_llm() 팩토리 테스트 — SDK 호출 없이 분기 로직만 검증."""
import pytest

from book_forge.exceptions import MissingAPIKeyError, UnsupportedProviderError
from book_forge.llm.provider import OllamaLLM, create_llm


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
