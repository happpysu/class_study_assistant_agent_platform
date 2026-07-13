"""统一 LLM 客户端：提供商/模型解析与 JSON 容错提取（不发起网络请求）。"""
import sys
from types import SimpleNamespace

import pytest

from app.services import llm


def test_default_provider_and_model(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    assert llm.provider() == "anthropic"
    assert llm.model_name() == "claude-opus-4-8"


def test_openai_provider_and_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    assert llm.provider() == "openai"
    assert llm.model_name() == "gpt-4o-mini"
    monkeypatch.setenv("LLM_MODEL", "deepseek-chat")
    assert llm.model_name() == "deepseek-chat"


def test_invalid_provider_falls_back(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    assert llm.provider() == "anthropic"


def test_api_key_resolution(monkeypatch):
    for var in ("LLM_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    assert not llm.is_configured()

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert llm.is_configured()

    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert not llm.is_configured()  # openai 的 key 不应被 anthropic 采用
    monkeypatch.setenv("LLM_API_KEY", "sk-uni")
    assert llm.is_configured()


def test_complete_without_key_raises(monkeypatch):
    for var in ("LLM_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(llm.LLMUnavailableError):
        llm.complete("system", "hello")


def test_extract_json_plain():
    assert llm._extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_with_fence_and_prose():
    text = '好的，以下是结果：\n```json\n{"overview": "计划", "stages": []}\n```'
    assert llm._extract_json(text)["overview"] == "计划"


def test_extract_json_invalid_raises():
    with pytest.raises(llm.LLMUnavailableError):
        llm._extract_json("这里没有任何结构化内容")


def test_openai_agent_protocol_tool_round_trip(monkeypatch):
    calls = []
    streams = iter(
        [
            [
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(
                                content=None,
                                tool_calls=[
                                    SimpleNamespace(
                                        index=0,
                                        id="call-1",
                                        function=SimpleNamespace(
                                            name="lookup", arguments='{"query":"导数"}'
                                        ),
                                    )
                                ],
                            )
                        )
                    ]
                )
            ],
            [
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(content="工具结果已收到", tool_calls=[])
                        )
                    ]
                )
            ],
        ]
    )

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs["messages"])
            return next(streams)

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions())
    )
    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(OpenAI=lambda **kwargs: fake_client),
    )
    executed = []

    events = list(
        llm._agent_openai(
            "key",
            "system",
            "question",
            [{"name": "lookup", "description": "检索", "input_schema": {"type": "object"}}],
            lambda name, args: executed.append((name, args)) or '{"ok":true}',
        )
    )

    assert ("tool", {"name": "lookup", "input": {"query": "导数"}}) in events
    assert ("text", "工具结果已收到") in events
    assert executed == [("lookup", {"query": "导数"})]
    assert calls[1][-1]["role"] == "tool"


def test_anthropic_agent_protocol_tool_round_trip(monkeypatch):
    tool_block = SimpleNamespace(
        type="tool_use", id="tool-1", name="lookup", input={"query": "积分"}
    )
    responses = iter(
        [
            ([], SimpleNamespace(content=[tool_block])),
            (["已根据工具作答"], SimpleNamespace(content=[SimpleNamespace(type="text")])),
        ]
    )

    class FakeStream:
        def __init__(self):
            self.text_stream, self.response = next(responses)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get_final_message(self):
            return self.response

    fake_client = SimpleNamespace(
        messages=SimpleNamespace(stream=lambda **kwargs: FakeStream())
    )
    monkeypatch.setitem(
        sys.modules,
        "anthropic",
        SimpleNamespace(Anthropic=lambda **kwargs: fake_client),
    )
    executed = []

    events = list(
        llm._agent_anthropic(
            "key",
            "system",
            "question",
            [{"name": "lookup", "description": "检索", "input_schema": {"type": "object"}}],
            lambda name, args: executed.append((name, args)) or '{"ok":true}',
        )
    )

    assert ("tool", {"name": "lookup", "input": {"query": "积分"}}) in events
    assert ("text", "已根据工具作答") in events
    assert executed == [("lookup", {"query": "积分"})]
