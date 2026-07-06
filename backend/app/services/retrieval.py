"""资料检索：面向中文/英文混合文本的轻量关键词打分检索。"""
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Material, MaterialChunk

MAX_SCAN_CHUNKS = 3000


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: int
    material_id: int
    material_name: str
    content: str
    score: float


def _query_terms(query: str) -> list[str]:
    """英文按空格分词；中文补充二元词组（bigram）提升召回。"""
    terms = [t.lower() for t in query.split() if t.strip()]
    cjk = [ch for ch in query if "一" <= ch <= "鿿"]
    bigrams = ["".join(cjk[i : i + 2]) for i in range(len(cjk) - 1)]
    combined = list(dict.fromkeys(terms + bigrams))
    return combined or [query.strip().lower()]


def search_chunks(
    db: Session, course_id: int, query: str, limit: int = 6
) -> list[RetrievedChunk]:
    terms = _query_terms(query)
    rows = db.execute(
        select(MaterialChunk, Material.filename)
        .join(Material, Material.id == MaterialChunk.material_id)
        .where(MaterialChunk.course_id == course_id)
        .limit(MAX_SCAN_CHUNKS)
    ).all()

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
