"""课程资料上传、查看、检索与删除。"""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Course, Material, MaterialChunk, User
from ..models.material import MATERIAL_TYPES
from ..schemas.material import ChunkHit, MaterialOut
from ..services.extraction import chunk_text, extract_text
from ..services.retrieval import search_chunks
from ..services.security import get_current_user
from .courses import get_owned_course

router = APIRouter(prefix="/api", tags=["materials"])


def _get_owned_material(
    material_id: int, current: User, db: Session
) -> Material:
    material = db.get(Material, material_id)
    if material is None:
        raise HTTPException(status_code=404, detail="资料不存在")
    course = db.get(Course, material.course_id)
    if course is None or course.owner_id != current.id:
        raise HTTPException(status_code=404, detail="资料不存在")
    return material


@router.post(
    "/courses/{course_id}/materials",
    response_model=MaterialOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_material(
    file: UploadFile = File(...),
    mtype: str = Form("other"),
    description: str = Form(""),
    course: Course = Depends(get_owned_course),
    db: Session = Depends(get_db),
):
    if mtype not in MATERIAL_TYPES:
        raise HTTPException(status_code=422, detail=f"资料类型须为 {MATERIAL_TYPES} 之一")
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413, detail=f"文件超过 {settings.max_upload_mb}MB 限制"
        )
    original_name = Path(file.filename or "unnamed").name  # 防路径穿越
    stored_name = f"{uuid.uuid4().hex}_{original_name}"
    stored_path = settings.upload_dir / stored_name
    stored_path.write_bytes(data)

    material = Material(
        course_id=course.id,
        filename=original_name,
        stored_path=str(stored_path),
        mtype=mtype,
        description=description[:2000],
        size_bytes=len(data),
    )
    db.add(material)
    db.flush()

    text = extract_text(stored_path)
    for seq, chunk in enumerate(chunk_text(text)):
        db.add(
            MaterialChunk(
                material_id=material.id, course_id=course.id, seq=seq, content=chunk
            )
        )
    db.commit()
    db.refresh(material)
    return material


@router.get("/courses/{course_id}/materials", response_model=list[MaterialOut])
def list_materials(
    mtype: str | None = None,
    keyword: str | None = None,
    course: Course = Depends(get_owned_course),
    db: Session = Depends(get_db),
):
    stmt = select(Material).where(Material.course_id == course.id)
    if mtype:
        stmt = stmt.where(Material.mtype == mtype)
    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(
            Material.filename.like(pattern) | Material.description.like(pattern)
        )
    return db.execute(stmt.order_by(Material.created_at.desc())).scalars().all()


@router.get("/courses/{course_id}/materials/search", response_model=list[ChunkHit])
def search_material_content(
    q: str,
    course: Course = Depends(get_owned_course),
    db: Session = Depends(get_db),
):
    """按关键词检索课程资料内容片段（供人工查阅与 Agent 引用）。"""
    if not q.strip():
        raise HTTPException(status_code=422, detail="检索关键词不能为空")
    hits = search_chunks(db, course.id, q, limit=10)
    return [
        ChunkHit(
            material_id=h.material_id,
            material_name=h.material_name,
            chunk_id=h.chunk_id,
            excerpt=h.content[:200],
            score=h.score,
        )
        for h in hits
    ]


@router.get("/materials/{material_id}/download")
def download_material(
    material_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    material = _get_owned_material(material_id, current, db)
    path = Path(material.stored_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件已丢失")
    return FileResponse(path, filename=material.filename)


@router.delete("/materials/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_material(
    material_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    material = _get_owned_material(material_id, current, db)
    db.query(MaterialChunk).filter(MaterialChunk.material_id == material.id).delete(
        synchronize_session=False
    )
    path = Path(material.stored_path)
    db.delete(material)
    db.commit()
    if path.exists():
        path.unlink()
