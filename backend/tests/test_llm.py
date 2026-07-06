"""统一 LLM 客户端：提供商/模型解析与 JSON 容错提取（不发起网络请求）。"""
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
