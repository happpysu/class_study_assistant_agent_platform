"""资料检索：向量语义检索优先（配置 EMBEDDING_API_KEY 时），关键词打分兜底。"""
import json
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Material, MaterialChunk
from . import embeddings
from .embeddings import EmbeddingUnavailableError

logger = logging.getLogger(__name__)

MAX_SCAN_CHUNKS = 3000


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: int
    material_id: int
    material_name: str
    content: str
    score: float


def _load_rows(db: Session, course_id: int):
    return db.execute(
        select(MaterialChunk, Material.filename)
        .join(Material, Material.id == MaterialChunk.material_id)
        .where(MaterialChunk.course_id == course_id)
        .limit(MAX_SCAN_CHUNKS)
    ).all()


def search_chunks(
    db: Session, course_id: int, query: str, limit: int = 6
) -> list[RetrievedChunk]:
    """课程内检索：向量可用时按余弦相似度排序，否则退回关键词打分。"""
    rows = _load_rows(db, course_id)
    if embeddings.is_configured():
        try:
            hits = _vector_search(rows, query, limit)
            if hits:
                return hits
        except EmbeddingUnavailableError:
            logger.warning("向量检索失败，退回关键词检索")
    return _keyword_search(rows, query, limit)


# ---------------------------------------------------------------- 向量检索

def _vector_search(rows, query: str, limit: int) -> list[RetrievedChunk]:
    query_vec = embeddings.embed_texts([query])[0]
    scored = []
    for chunk, filename in rows:
        if not chunk.embedding_json:
            continue  # 旧数据无向量时由关键词兜底覆盖
        try:
            vec = json.loads(chunk.embedding_json)
        except json.JSONDecodeError:
            continue
        score = embeddings.cosine(query_vec, vec)
        scored.append(
            RetrievedChunk(
                chunk_id=chunk.id,
                material_id=chunk.material_id,
                material_name=filename,
                content=chunk.content,
                score=round(score, 4),
            )
        )
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:limit]


# ---------------------------------------------------------------- 关键词检索

def _query_terms(query: str) -> list[str]:
    """英文按空格分词；中文补充二元词组（bigram）提升召回。"""
    terms = [t.lower() for t in query.split() if t.strip()]
    cjk = [ch for ch in query if "一" <= ch <= "鿿"]
    bigrams = ["".join(cjk[i : i + 2]) for i in range(len(cjk) - 1)]
    combined = list(dict.fromkeys(terms + bigrams))
    return combined or [query.strip().lower()]


def _keyword_search(rows, query: str, limit: int) -> list[RetrievedChunk]:
    terms = _query_terms(query)
    scored = []
    for chunk, filename in rows:
        lowered = chunk.content.lower()
        score = float(sum(lowered.count(term) for term in terms if term))
        if score > 0:
            scored.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    material_id=chunk.material_id,
                    material_name=filename,
                    content=chunk.content,
                    score=score,
                )
            )
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:limit]


def sample_chunks(db: Session, course_id: int, limit: int = 30) -> list[RetrievedChunk]:
    """无查询词时取课程内前若干切片（用于知识点整理）。"""
    rows = db.execute(
        select(MaterialChunk, Material.filename)
        .join(Material, Material.id == MaterialChunk.material_id)
        .where(MaterialChunk.course_id == course_id)
        .order_by(MaterialChunk.material_id, MaterialChunk.seq)
        .limit(limit)
    ).all()
    return [
        RetrievedChunk(
            chunk_id=chunk.id,
            material_id=chunk.material_id,
            material_name=filename,
            content=chunk.content,
            score=0.0,
        )
        for chunk, filename in rows
    ]
