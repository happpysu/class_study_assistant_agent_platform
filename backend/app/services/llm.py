"""统一 LLM 客户端：支持 Anthropic 与 OpenAI 两种协议，均可自定义 base_url / api_key。

环境变量（backend/.env）：
    LLM_PROVIDER  anthropic | openai（默认 anthropic）
    LLM_API_KEY   API 密钥（也兼容 ANTHROPIC_API_KEY / OPENAI_API_KEY）
    LLM_BASE_URL  自定义接口地址（选填，用于代理/中转/第三方兼容服务）
    LLM_MODEL     模型名（anthropic 默认 claude-opus-4-8，openai 默认 gpt-4o-mini）
"""
import json
import logging
import os

from .. import config  # noqa: F401  导入即触发 .env 加载，保证独立使用本模块时配置生效

logger = logging.getLogger(__name__)

_DEFAULT_MODELS = {"anthropic": "claude-opus-4-8", "openai": "gpt-4o-mini"}


class LLMUnavailableError(Exception):
    """LLM 不可用（未配置密钥或调用失败）。"""


def provider() -> str:
    value = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
    return value if value in ("anthropic", "openai") else "anthropic"


def model_name() -> str:
    explicit = os.getenv("LLM_MODEL") or os.getenv("ANTHROPIC_MODEL")
    return explicit or _DEFAULT_MODELS[provider()]


def _api_key() -> str:
    if provider() == "openai":
        return os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
    return (
        os.getenv("LLM_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("ANTHROPIC_AUTH_TOKEN")
        or ""
    )


def _base_url() -> str | None:
    return os.getenv("LLM_BASE_URL") or None


def is_configured() -> bool:
    return bool(_api_key())


def info() -> dict:
    return {
        "provider": provider(),
        "model": model_name(),
        "base_url": _base_url() or "(默认官方地址)",
        "configured": is_configured(),
    }


def complete(system: str, user_content: str, max_tokens: int = 4096) -> str:
    """文本补全，按 LLM_PROVIDER 分发；任何异常统一收敛为 LLMUnavailableError。"""
    key = _api_key()
    if not key:
        raise LLMUnavailableError("未配置 LLM_API_KEY")
    try:
        if provider() == "openai":
            return _complete_openai(key, system, user_content, max_tokens)
        return _complete_anthropic(key, system, user_content, max_tokens)
    except Exception as exc:
        logger.warning("LLM 调用失败 [%s/%s]: %s", provider(), model_name(), exc)
        raise LLMUnavailableError(str(exc)) from exc


def complete_json(
    system: str, user_content: str, schema: dict, max_tokens: int = 8192
) -> dict:
    """JSON 补全：在提示词中约束 Schema，输出做容错解析（兼容所有协议/中转站）。"""
    schema_text = json.dumps(schema, ensure_ascii=False)
    json_system = (
        f"{system}\n\n输出要求：只输出一个 JSON 对象，必须符合以下 JSON Schema，"
        f"不要输出任何解释文字或 Markdown 代码块标记。\nJSON Schema:\n{schema_text}"
    )
    text = complete(json_system, user_content, max_tokens)
    return _extract_json(text)


def _complete_anthropic(
    key: str, system: str, user_content: str, max_tokens: int
) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=key, base_url=_base_url())
    response = client.messages.create(
        model=model_name(),
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    return "".join(b.text for b in response.content if b.type == "text")


def _complete_openai(key: str, system: str, user_content: str, max_tokens: int) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=key, base_url=_base_url())
    response = client.chat.completions.create(
        model=model_name(),
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
    )
    return response.choices[0].message.content or ""


def _extract_json(text: str) -> dict:
    """容错提取 JSON：剥离代码块围栏，截取首个 { 到末个 } 之间的内容。"""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise LLMUnavailableError("模型未返回有效 JSON")
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMUnavailableError(f"JSON 解析失败: {exc}") from exc
