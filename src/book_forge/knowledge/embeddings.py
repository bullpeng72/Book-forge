"""Ollama `/api/embeddings` 기반 임베딩 — RAG는 현재 Ollama 임베딩만 지원한다.

chat LLM provider(OPENAI/ANTHROPIC/OLLAMA) 선택과 무관하게 항상 Ollama를 쓴다 —
OpenAI/Anthropic은 별도 임베딩 API 통합이 필요해 M5 범위를 벗어난다(알려진 한계,
README에 명시).
"""
from __future__ import annotations

import os

DEFAULT_EMBED_MODEL = "mxbai-embed-large"


def _is_context_length_error(response) -> bool:
    try:
        body = response.json()
    except ValueError:
        return False
    return "context length" in str(body.get("error", "")).lower()


def embed_text(
    text: str, *, base_url: str = "", model: str = "", timeout: int = 60, _retry: bool = True
) -> list[float]:
    """단일 텍스트를 Ollama 임베딩 벡터로 변환한다.

    mxbai-embed-large 등 임베딩 모델은 컨텍스트 길이 제한이 있어(실측: 코드
    저장소 소스의 긴 청크가 500 에러 "the input length exceeds the context
    length"를 유발함), 그 특정 오류에 한해 텍스트를 절반으로 잘라 한 번만
    재시도한다(_retry=False로 무한 재귀 방지) — 조용히 버리지 않고, 잘렸다는
    사실을 호출자가 알 수 있도록 예외 메시지에도 남긴다.
    """
    import requests  # lazy import — [rag] extra

    resolved_base = base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    resolved_model = model or os.environ.get("OLLAMA_EMBED_MODEL", DEFAULT_EMBED_MODEL)

    response = requests.post(
        f"{resolved_base.rstrip('/')}/api/embeddings",
        json={"model": resolved_model, "prompt": text},
        timeout=timeout,
    )

    if response.status_code == 500 and _retry and _is_context_length_error(response):
        truncated = text[: max(len(text) // 2, 1)]
        return embed_text(
            truncated, base_url=base_url, model=model, timeout=timeout, _retry=False
        )

    response.raise_for_status()
    embedding = response.json().get("embedding")
    if not embedding:
        raise ValueError(f"Ollama 임베딩 응답에 'embedding' 필드가 없습니다: {response.text[:200]}")
    return embedding


def embed_texts(texts: list[str], *, base_url: str = "", model: str = "") -> list[list[float]]:
    return [embed_text(t, base_url=base_url, model=model) for t in texts]
