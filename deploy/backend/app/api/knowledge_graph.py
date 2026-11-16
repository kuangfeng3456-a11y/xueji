"""显式知识图谱接口：节点、先修/易混淆关系与邻居查询。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_user_goal
from ..models import User
from ..services import knowledge_graph

router = APIRouter(tags=["知识图谱"])


@router.get("/goals/{goal_id}/graph")
def graph(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    goal = get_user_goal(goal_id, user, db)
    return knowledge_graph.get_graph(db, user, goal)


@router.post("/goals/{goal_id}/graph/sync")
def sync_graph(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    goal = get_user_goal(goal_id, user, db)
    return knowledge_graph.sync_edges(db, goal.id)


@router.get("/goals/{goal_id}/graph/nodes/{kp_id}")
def graph_node(
    goal_id: int,
    kp_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    goal = get_user_goal(goal_id, user, db)
    try:
        return knowledge_graph.node_detail(db, user, goal, kp_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))