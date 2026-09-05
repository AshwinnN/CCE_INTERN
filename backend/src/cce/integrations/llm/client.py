"""LangChain/LangGraph-compatible Gemini client."""

from __future__ import annotations

import os
from typing import Any


DEFAULT_MODEL = "gemini-2.5-flash"


def complete(prompt: str, *, response_format: str = "text") -> str:
    api_key = os.environ.get("CCE_LLM_API_KEY")
    if not api_key:
        raise RuntimeError("missing CCE_LLM_API_KEY")

    from langchain_google_genai import ChatGoogleGenerativeAI

    model = ChatGoogleGenerativeAI(
        model=os.environ.get("CCE_LLM_MODEL", DEFAULT_MODEL),
        google_api_key=api_key,
        temperature=0,
    )
    message: Any = model.invoke(prompt)
    if response_format != "text":
        return str(getattr(message, "content", message))
    return str(getattr(message, "content", message))
