"""LangChain/LangGraph-compatible LLM client.

Supports two providers, selected by CCE_LLM_PROVIDER:
- "gemini"   (default) -- direct ChatGoogleGenerativeAI.
- "litellm"  -- OpenAI-protocol client pointed at a LiteLLM proxy
                (CCE_LLM_BASE_URL), so any model the proxy exposes is
                reachable through one CCE_LLM_API_KEY without a
                provider-specific wrapper.
"""

from __future__ import annotations

import os
from typing import Any


DEFAULT_MODEL = "gemini-2.5-flash"


def complete(prompt: str, *, response_format: str = "text") -> str:
    provider = os.environ.get("CCE_LLM_PROVIDER", "gemini").strip().lower()
    message = _invoke_litellm(prompt) if provider == "litellm" else _invoke_gemini(prompt)
    if response_format != "text":
        return str(getattr(message, "content", message))
    return str(getattr(message, "content", message))


def _invoke_gemini(prompt: str) -> Any:
    api_key = os.environ.get("CCE_LLM_API_KEY")
    if not api_key:
        raise RuntimeError("missing CCE_LLM_API_KEY")

    from langchain_google_genai import ChatGoogleGenerativeAI

    model = ChatGoogleGenerativeAI(
        model=os.environ.get("CCE_LLM_MODEL", DEFAULT_MODEL),
        google_api_key=api_key,
        temperature=0,
    )
    return model.invoke(prompt)


def _invoke_litellm(prompt: str) -> Any:
    base_url = os.environ.get("CCE_LLM_BASE_URL")
    if not base_url:
        raise RuntimeError("missing CCE_LLM_BASE_URL for CCE_LLM_PROVIDER=litellm")
    api_key = os.environ.get("CCE_LLM_API_KEY")
    if not api_key:
        raise RuntimeError("missing CCE_LLM_API_KEY")

    from langchain_openai import ChatOpenAI

    kwargs: dict[str, Any] = dict(
        base_url=base_url,
        api_key=api_key,
        model=os.environ.get("CCE_LLM_MODEL", DEFAULT_MODEL),
        temperature=0,
        timeout=int(os.environ.get("CCE_LLM_TIMEOUT", "300")),
        max_retries=int(os.environ.get("CCE_LLM_MAX_RETRIES", "1")),
    )
    max_tokens = os.environ.get("CCE_LLM_MAX_TOKENS")
    if max_tokens:
        kwargs["max_tokens"] = int(max_tokens)

    model = ChatOpenAI(**kwargs)
    return model.invoke(prompt)
