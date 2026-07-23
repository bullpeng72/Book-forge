"""LLM Provider 추상화 — OpenAI / Anthropic / Ollama 통합 인터페이스.

Lecture_forge의 ``create_llm()`` 팩토리 패턴을 따른다: ``LLM_PROVIDER`` 환경변수로
provider를 선택하면, 이후 모든 에이전트는 provider를 몰라도 되는 단일
``generate()`` 인터페이스만 사용한다. 각 provider SDK는 실제 선택된
provider에서만 지연 로딩(lazy import)한다 — 설치하지 않은 provider의
무거운 의존성을 강제로 끌고 오지 않기 위함.
"""
from __future__ import annotations

import os
from typing import Optional, Protocol, runtime_checkable

from book_forge.exceptions import MissingAPIKeyError, UnsupportedProviderError

DEFAULT_OPENAI_MODEL = "gpt-5-nano"
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_OLLAMA_MODEL = "llama3.2"


@runtime_checkable
class LLM(Protocol):
    """모든 provider 구현체가 만족해야 하는 최소 인터페이스."""

    model: str

    def generate(
        self, prompt: str, *, system: Optional[str] = None, max_tokens: int = 4000
    ) -> str: ...


class OpenAILLM:
    def __init__(self, api_key: str, model: str = DEFAULT_OPENAI_MODEL) -> None:
        from openai import OpenAI  # lazy import

        self._client = OpenAI(api_key=api_key)
        self.model = model

    def generate(
        self, prompt: str, *, system: Optional[str] = None, max_tokens: int = 4000
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""


class AnthropicLLM:
    def __init__(self, api_key: str, model: str = DEFAULT_ANTHROPIC_MODEL) -> None:
        from anthropic import Anthropic  # lazy import

        self._client = Anthropic(api_key=api_key)
        self.model = model

    def generate(
        self, prompt: str, *, system: Optional[str] = None, max_tokens: int = 4000
    ) -> str:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system or "",
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if hasattr(block, "text"))


class OllamaLLM:
    def __init__(self, base_url: str, model: str = DEFAULT_OLLAMA_MODEL) -> None:
        self._base_url = base_url.rstrip("/")
        self.model = model

    def generate(
        self, prompt: str, *, system: Optional[str] = None, max_tokens: int = 4000
    ) -> str:
        import requests  # lazy import

        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system or "",
            "stream": False,
            # think=False: 추론("thinking") 모델(예: qwen3 계열)은 응답 본문을
            # Ollama의 별도 "thinking" 필드에 담고 "response"는 비워둔다 —
            # num_predict 예산을 추론에 다 쓰면 최종 답변이 한 글자도 안
            # 나오고 response=""로 끝난다(실측 확인: qwen3.6:35b-mlx로
            # 챕터를 생성했더니 파일이 통째로 빈 채 저장됨, done_reason
            # "length"). think=False는 추론 모델의 사고 과정을 건너뛰고
            # 바로 답을 response에 채우게 강제한다. 추론을 지원하지 않는
            # 모델(예: qwen3-coder)은 이 옵션을 그냥 무시한다(실측 확인,
            # 에러 없음) — 항상 켜둬도 안전하다.
            "think": False,
            "options": {"num_predict": max_tokens},
        }
        response = requests.post(f"{self._base_url}/api/generate", json=payload, timeout=180)
        response.raise_for_status()
        return response.json().get("response", "")


def create_llm(provider: Optional[str] = None, model: Optional[str] = None) -> LLM:
    """환경변수 또는 인자로 지정된 provider에 맞는 LLM 인스턴스를 생성한다.

    provider 우선순위: 인자 > ``LLM_PROVIDER`` 환경변수 > ``"ollama"`` 기본값.
    기본값을 ollama로 둔 이유: API 키 없이 바로 동작해 오프라인/로컬 개발을
    1급 경로로 만든다 — OpenAI/Anthropic을 쓰려면 명시적으로 설정해야 한다.
    """
    resolved = (provider or os.environ.get("LLM_PROVIDER") or "ollama").lower()

    if resolved == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise MissingAPIKeyError(
                "OPENAI_API_KEY가 설정되지 않았습니다. `book-forge init`을 실행하세요."
            )
        return OpenAILLM(api_key=api_key, model=model or DEFAULT_OPENAI_MODEL)

    if resolved == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise MissingAPIKeyError(
                "ANTHROPIC_API_KEY가 설정되지 않았습니다. `book-forge init`을 실행하세요."
            )
        return AnthropicLLM(api_key=api_key, model=model or DEFAULT_ANTHROPIC_MODEL)

    if resolved == "ollama":
        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        return OllamaLLM(
            base_url=base_url,
            model=model or os.environ.get("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
        )

    raise UnsupportedProviderError(
        f"지원하지 않는 LLM_PROVIDER='{resolved}'. openai / anthropic / ollama 중 하나여야 합니다."
    )
