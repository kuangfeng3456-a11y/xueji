"""可信资料 RAG：切块、索引与可定位到文件名/段落的检索引用。"""

import re
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import DocumentChunk, Material

MAX_CHUNK = 400


def split_chunks(text: str, max_len: int = MAX_CHUNK) -> List[str]:
    text = re.sub(r"\r\n?", "\n", text or "")
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: List[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= max_len:
            chunks.append(paragraph)
            continue
        buffer = ""
        for sentence in re.split(r"(?<=[。！？.!?])\s*", paragraph):
            if len(buffer) + len(sentence) > max_len and buffer:
                chunks.append(buffer)
                buffer = sentence
            else:
                buffer += sentence
        if buffer:
            chunks.append(buffer)
    return [chunk for chunk in chunks if chunk.strip()]


def index_material(db: Session, user_id: int, goal_id: int, material: Material) -> int:
    for row in db.scalars(
        select(DocumentChunk).where(DocumentChunk.material_id == material.id)
    ).all():
        db.delete(row)
    db.flush()
    chunks = split_chunks(material.content or "")
    for index, chunk in enumerate(chunks):
        db.add(
            DocumentChunk(
                user_id=user_id,
                goal_id=goal_id,
                material_id=material.id,
                chunk_index=index,
                page_no=index // 5 + 1,
                chunk_text=chunk[:2000],
            )
        )
    db.flush()
    return len(chunks)


def reindex_goal(db: Session, user_id: int, goal_id: int) -> Dict:
    materials = db.scalars(
        select(Material).where(Material.user_id == user_id, Material.goal_id == goal_id)
    ).all()
    total = 0
    for material in materials:
        total += index_material(db, user_id, goal_id, material)
    db.commit()
    return {"materials": len(materials), "chunks": total}


def _bigrams(text: str) -> set:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]", "", (text or "").lower())
    if len(cleaned) < 2:
        return {cleaned} if cleaned else set()
    return {cleaned[i : i + 2] for i in range(len(cleaned) - 1)}


def search(db: Session, user_id: int, goal_id: int, query: str, top_k: int = 5) -> List[Dict]:
    if not query or not query.strip():
        return []
    materials = {
        material.id: material
        for material in db.scalars(
            select(Material).where(Material.user_id == user_id, Material.goal_id == goal_id)
        ).all()
    }
    chunks = db.scalars(
        select(DocumentChunk).where(
            DocumentChunk.user_id == user_id, DocumentChunk.goal_id == goal_id
        )
    ).all()
    query_grams = _bigrams(query)
    if not query_grams:
        return []
    scored = []
    for chunk in chunks:
        overlap = len(query_grams & _bigrams(chunk.chunk_text))
        if overlap == 0:
            continue
        scored.append((overlap / len(query_grams), chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    results = []
    for score, chunk in scored[:top_k]:
        material = materials.get(chunk.material_id)
        results.append(
            {
                "material_id": chunk.material_id,
                "filename": material.filename if material else f"资料 {chunk.material_id}",
                "chunk_index": chunk.chunk_index,
                "page_no": chunk.page_no,
                "snippet": chunk.chunk_text[:180],
                "score": round(score, 3),
            }
        )
    return results