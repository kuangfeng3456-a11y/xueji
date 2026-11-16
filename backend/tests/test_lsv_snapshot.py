"""LSV 快照表（文档 2.3 / 附录 B）：快照落库、哈希可复算。"""

import hashlib
import json

from sqlalchemy import select

from app.models import KnowledgePoint, LsvSnapshot
from app.services.lsv import LSV_VERSION, build_lsv


def _add_points(db, goal, names=("听力", "阅读")):
    for index, name in enumerate(names):
        db.add(KnowledgePoint(goal_id=goal.id, name=name, weight=0.5 + index * 0.5))
    db.commit()


def test_build_lsv_persists_snapshot_with_hash(db, db_user_goal):
    user, goal = db_user_goal
    _add_points(db, goal)

    data = build_lsv(db, user, goal)

    row = db.scalars(select(LsvSnapshot)).one()
    assert row.snapshot_id == data["snapshot_id"]
    assert row.user_id == user.id
    assert row.goal_id == goal.id
    assert row.lsv_version == LSV_VERSION
    assert len(row.hash) == 64
    assert row.hash == data["snapshot_hash"]

    payload = json.loads(row.payload)
    assert payload["snapshot_id"] == data["snapshot_id"]
    assert payload["privacy"]["psychology_excluded"] is True
    assert "user_hash" in payload
    assert "nickname" not in payload and "username" not in payload
    assert hashlib.sha256(row.payload.encode("utf-8")).hexdigest() == row.hash


def test_each_build_creates_distinct_snapshot(db, db_user_goal):
    user, goal = db_user_goal
    _add_points(db, goal)

    first = build_lsv(db, user, goal)
    second = build_lsv(db, user, goal)

    assert first["snapshot_id"] != second["snapshot_id"]
    assert db.scalar(select(LsvSnapshot)) is not None
    assert len(db.scalars(select(LsvSnapshot)).all()) == 2


def test_snapshot_excludes_direct_identifiers(db, db_user_goal):
    user, goal = db_user_goal
    _add_points(db, goal)

    data = build_lsv(db, user, goal)

    serialized = json.dumps(data, ensure_ascii=False)
    assert user.username not in serialized
    assert "password" not in serialized
    assert data["user_hash"].startswith("u_")
