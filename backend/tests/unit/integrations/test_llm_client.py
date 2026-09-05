import os
import sys
import types

import pytest

from cce.integrations.llm import client


def test_complete_requires_api_key(monkeypatch):
    monkeypatch.delenv("CCE_LLM_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="CCE_LLM_API_KEY"):
        client.complete("hello")


def test_complete_passes_temperature_zero_and_model(monkeypatch):
    calls = {}
    module = types.ModuleType("langchain_google_genai")

    class ChatGoogleGenerativeAI:
        def __init__(self, **kwargs):
            calls["kwargs"] = kwargs

        def invoke(self, prompt):
            calls["prompt"] = prompt
            return types.SimpleNamespace(content="done")

    module.ChatGoogleGenerativeAI = ChatGoogleGenerativeAI
    monkeypatch.setitem(sys.modules, "langchain_google_genai", module)
    monkeypatch.setenv("CCE_LLM_API_KEY", "test-key")
    monkeypatch.setenv("CCE_LLM_MODEL", "gemini-test")

    assert client.complete("prompt") == "done"
    assert calls["kwargs"]["temperature"] == 0
    assert calls["kwargs"]["model"] == "gemini-test"
    assert calls["kwargs"]["google_api_key"] == "test-key"
    assert calls["prompt"] == "prompt"


def test_complete_can_be_used_in_langgraph_node(monkeypatch):
    pytest.importorskip("langgraph.graph")
    from langgraph.graph import END, StateGraph
    from typing import TypedDict

    module = types.ModuleType("langchain_google_genai")

    class ChatGoogleGenerativeAI:
        def __init__(self, **kwargs):
            pass

        def invoke(self, prompt):
            return types.SimpleNamespace(content=prompt.upper())

    module.ChatGoogleGenerativeAI = ChatGoogleGenerativeAI
    monkeypatch.setitem(sys.modules, "langchain_google_genai", module)
    monkeypatch.setenv("CCE_LLM_API_KEY", "test-key")
    monkeypatch.delenv("CCE_LLM_MODEL", raising=False)

    class State(TypedDict):
        prompt: str
        answer: str

    def node(state: State) -> State:
        return {"prompt": state["prompt"], "answer": client.complete(state["prompt"])}

    graph = StateGraph(State)
    graph.add_node("complete", node)
    graph.set_entry_point("complete")
    graph.add_edge("complete", END)
    compiled = graph.compile()

    assert compiled.invoke({"prompt": "hello", "answer": ""})["answer"] == "HELLO"
