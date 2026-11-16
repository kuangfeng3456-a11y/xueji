"""可信资料 RAG 检索接口：返回可定位的文件名与段落引用。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_user_goal
from ..models import User
from ..services import rag
from ..services.learning_events import record_event

router = APIRouter(tags=["可信资料 RAG"])


class RagSearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    top_k: int = Field(default=5, ge=1, le=10)


@router.post("/goals/{goal_id}/documents/search")
def search_documents(
    goal_id: int,
    payload: RagSearchIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    goal = get_user_goal(goal_id, user, db)
    results = rag.search(db, user.id, goal.id, payload.query, payload.top_k)
    record_event(
        db,
        user.id,
        goal.id,
        "document_search",
        None,
        {"query": payload.query, "hits": len(results)},
    )
    db.commit()
    return {
        "query": payload.query,
        "results": results,
        "engine": "rule-lexical",
        "found": len(results),
        "message": "" if results else "未检索到可靠来源，不编造引用。",
    }


@router.post("/goals/{goal_id}/documents/reindex")
def reindex_documents(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    goal = get_user_goal(goal_id, user, db)
    return rag.reindex_goal(db, user.id, goal.id)