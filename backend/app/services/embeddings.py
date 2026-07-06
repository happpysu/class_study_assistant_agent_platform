"""向量嵌入服务：调用 OpenAI 兼容的 /embeddings 接口（Anthropic 无嵌入接口）。

环境变量（backend/.env）：
    EMBEDDING_API_KEY   嵌入服务密钥（未配置时检索自动退回关键词模式）
    EMBEDDING_BASE_URL  接口地址（如 SiliconFlow: https://api.siliconflow.cn/v1）
    EMBEDDING_MODEL     模型名（默认 text-embedding-3-small；国内常用 BAAI/bge-m3）
"""
import logging
import math
import os

from .. import config  # noqa: F401  导入即触发 .env 加载

logger = logging.getLogger(__name__)

_BATCH_SIZE = 32
_DEFAULT_MODEL = "text-embedding-3-small"


class EmbeddingUnavailableError(Exception):
    """嵌入服务不可用（未配置密钥或调用失败）。"""


def is_configured() -> bool:
    return bool(os.getenv("EMBEDDING_API_KEY"))


def model_name() -> str:
    return os.getenv("EMBEDDING_MODEL") or _DEFAULT_MODEL


def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量嵌入，保持输入顺序；任何异常统一收敛为 EmbeddingUnavailableError。"""
    key = os.getenv("EMBEDDING_API_KEY")
    if not key:
        raise EmbeddingUnavailableError("未配置 EMBEDDING_API_KEY")
    try:
        from openai import OpenAI

        client = OpenAI(api_key=key, base_url=os.getenv("EMBEDDING_BASE_URL") or None)
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH_SIZE):
            batch = texts[start : start + _BATCH_SIZE]
            response = client.embeddings.create(model=model_name(), input=batch)
            ordered = sorted(response.data, key=lambda item: item.index)
            vectors.extend([item.embedding for item in ordered])
        return vectors
    except Exception as exc:
        logger.warning("嵌入调用失败 [%s]: %s", model_name(), exc)
        raise EmbeddingUnavailableError(str(exc)) from exc


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
