"""教师工作台、班级对比与教务对接。

未配置 ACADEMIC_BRIDGE_URL 时只使用内置样例名册，不访问真实学校系统，
也不读取或保存校级账号、口令或证书。
"""

import json
import os
import random
import string
import urllib.error
import urllib.request
from datetime import datetime
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AcademicLink, AcademicSyncLog, SchoolClass, User
from .teacher import teacher_dashboard


def _invite_code(db: Session) -> str:
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(30):
        code = "".join(random.choice(alphabet) for _ in range(6))
        if not db.scalar(select(SchoolClass).where(SchoolClass.invite_code == code)):
            return code
    raise ValueError("邀请码生成失败，请重试")

SAMPLE_PROFILES = {
    "sample-cs-2024-1": {
        "completion_rate": 0.82,
        "avg_mastery": 0.74,
        "top_weak": "指针与数组",
        "watch_count": 3,
        "suggestions": ["先集体讲指针与数组，再让掌握较好的同学带一次练习。"],
    },
    "sample-cs-2024-2": {
        "completion_rate": 0.51,
        "avg_mastery": 0.43,
        "top_weak": "TCP 与 UDP",
        "watch_count": 8,
        "suggestions": ["完成率偏低，建议先把每日任务收到能做完的长度。"],
    },
    "sample-ee-2023-1": {
        "completion_rate": 0.66,
        "avg_mastery": 0.58,
        "top_weak": "电磁感应",
        "watch_count": 5,
        "suggestions": ["电磁感应是当前弱项，可以安排一次集中纠错。"],
    },
}


SAMPLE_ROSTER = [
    {
        "external_id": "sample-cs-2024-1",
        "name": "计算机 2024 级 1 班",
        "department": "计算机学院",
        "student_count": 42,
    },
    {
        "external_id": "sample-cs-2024-2",
        "name": "计算机 2024 级 2 班",
        "department": "计算机学院",
        "student_count": 40,
    },
    {
        "external_id": "sample-ee-2023-1",
        "name": "电子信息 2023 级 1 班",
        "department": "电子学院",
        "student_count": 38,
    },
]


def bridge_target() -> Dict:
    mode = os.getenv("ACADEMIC_BRIDGE_MODE", "mock").strip().lower()
    url = os.getenv("ACADEMIC_BRIDGE_URL", "").strip()
    if mode == "http" and url:
        return {
            "mode": "http",
            "configured": True,
            "note": "已配置教务接口。同步时才会访问该地址；地址与凭证只留在服务端环境中，页面不展示。",
        }
    return {
        "mode": "mock",
        "configured": False,
        "note": "尚未配置校级教务地址。同步使用内置样例名册，只在你的账号下创建班级和邀请码，不会连接真实学校系统。",
    }


def _public_failure() -> str:
    return "教务接口请求失败，请稍后重试。地址与凭证不会显示在这里。"


def _fetch_http_roster() -> List[dict]:
    url = os.getenv("ACADEMIC_BRIDGE_URL", "").strip()
    token = os.getenv("ACADEMIC_BRIDGE_TOKEN", "").strip()
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=8) as response:
        raw = response.read(200_000)
    payload = json.loads(raw.decode("utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("classes") or payload.get("items") or []
    if not isinstance(payload, list):
        raise ValueError("名册格式无法识别")
    return payload


def _normalize_roster(items: List[dict]) -> List[dict]:
    cleaned = []
    for item in items:
        if not isinstance(item, dict):
            continue
        external_id = str(item.get("external_id") or item.get("id") or "").strip()[:64]
        name = str(item.get("name") or "").strip()[:60]
        if not external_id or not name:
            continue
        try:
            count = int(item.get("student_count") or 0)
        except (TypeError, ValueError):
            count = 0
        cleaned.append(
            {
                "external_id": external_id,
                "name": name,
                "department": str(item.get("department") or "")[:60],
                "student_count": max(0, count),
            }
        )
    return cleaned


def load_roster() -> Dict:
    target = bridge_target()
    if target["mode"] == "http":
        try:
            roster = _normalize_roster(_fetch_http_roster())
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError):
            return {"mode": "http", "status": "error", "detail": _public_failure(), "roster": []}
        if not roster:
            return {"mode": "http", "status": "error", "detail": "教务接口没有返回可识别的班级", "roster": []}
        return {"mode": "http", "status": "ok", "detail": f"已读取 {len(roster)} 个班级", "roster": roster}
    return {
        "mode": "mock",
        "status": "ok",
        "detail": "使用内置样例名册",
        "roster": list(SAMPLE_ROSTER),
    }


def _link_for(db: Session, user: User) -> AcademicLink:
    row = db.scalar(select(AcademicLink).where(AcademicLink.owner_id == user.id))
    if row is None:
        row = AcademicLink(
            owner_id=user.id,
            school_name=(user.school or "").strip(),
            provider="mock",
            status="idle",
        )
        db.add(row)
        db.flush()
    return row


def _log(db: Session, link: AcademicLink, direction: str, status: str, summary: dict) -> None:
    db.add(
        AcademicSyncLog(
            link_id=link.id,
            direction=direction,
            status=status,
            summary=json.dumps(summary, ensure_ascii=False)[:4000],
        )
    )


def owned_classes(db: Session, user: User) -> List[SchoolClass]:
    return db.scalars(
        select(SchoolClass).where(SchoolClass.owner_id == user.id).order_by(SchoolClass.id.asc())
    ).all()


def _class_metrics(db: Session, school_class: SchoolClass) -> dict:
    board = teacher_dashboard(db, school_class)
    weak = board["weak_points"][0]["name"] if board["weak_points"] else ""
    has_learning_data = board["member_count"] > 0 and bool(board["weak_points"] or board["completion_rate"])
    metrics = {
        "class_id": school_class.id,
        "name": school_class.name,
        "invite_code": school_class.invite_code,
        "external_ref": school_class.external_ref or "",
        "member_count": board["member_count"],
        "completion_rate": board["completion_rate"],
        "avg_mastery": board.get("avg_mastery") or 0.0,
        "watch_count": len(board["watch_list"]),
        "top_weak": weak,
        "suggestions": board["suggestions"][:2],
        "has_learning_data": has_learning_data,
        "basis": "live",
    }
    profile = SAMPLE_PROFILES.get(school_class.external_ref or "")
    if has_learning_data or not profile:
        return metrics
    metrics.update(
        {
            "completion_rate": profile["completion_rate"],
            "avg_mastery": profile["avg_mastery"],
            "watch_count": profile["watch_count"],
            "top_weak": profile["top_weak"],
            "suggestions": profile["suggestions"],
            "basis": "sample",
        }
    )
    return metrics


def workbench(db: Session, user: User) -> dict:
    classes = [_class_metrics(db, row) for row in owned_classes(db, user)]
    if not classes:
        focus = "还没有班级。可以在班级看板创建，或从教务对接同步名册。"
    else:
        lowest = min(classes, key=lambda item: item["completion_rate"])
        if all(not item["has_learning_data"] for item in classes):
            if any(item.get("basis") == "sample" for item in classes):
                focus = "名册已同步。完成率和弱项目前是样例对照，学生用邀请码加入并产生记录后会换成真实数据。"
            else:
                focus = "班级已建立，学生用邀请码加入并产生学习记录后，这里会显示完成率与薄弱点。"
        else:
            focus = f"优先查看「{lowest['name']}」，近 7 天完成率 {round(lowest['completion_rate'] * 100)}%。"
    return {
        "role": user.role or "student",
        "class_count": len(classes),
        "classes": classes,
        "focus": focus,
        "bridge": bridge_target(),
    }


def compare_classes(db: Session, user: User, class_ids: List[int]) -> dict:
    unique = []
    for class_id in class_ids:
        if class_id not in unique:
            unique.append(class_id)
    if len(unique) < 2:
        raise ValueError("请至少选择两个班级")
    if len(unique) > 8:
        raise ValueError("一次最多对比 8 个班级")
    rows = []
    for class_id in unique:
        school_class = db.get(SchoolClass, class_id)
        if school_class is None or school_class.owner_id != user.id:
            raise ValueError("只能对比自己负责的班级")
        metrics = _class_metrics(db, school_class)
        from .practice_loop import list_assignments

        assigned = list_assignments(db, school_class)
        if assigned:
            metrics["assignment_title"] = assigned[0]["title"]
            metrics["assignment_completion"] = round(
                sum(item["completion_rate"] for item in assigned) / len(assigned), 3
            )
            metrics["assignment_finished"] = sum(item["finished"] for item in assigned)
        rows.append(metrics)
    ranked = sorted(rows, key=lambda item: item["completion_rate"])
    return {
        "items": rows,
        "lowest": ranked[0],
        "highest": ranked[-1],
        "summary": _difference(rows),
        "note": "有学习记录的班级按真实数据对比。标为样例对照的数字只用于看差异，学生加入后会被替换。",
    }


def _difference(items: List[dict]) -> str:
    ordered = sorted(items, key=lambda item: item["completion_rate"], reverse=True)
    top, low = ordered[0], ordered[-1]
    if top["class_id"] == low["class_id"] or top["completion_rate"] == low["completion_rate"]:
        return "这几个班级目前的完成率相同，可以再看弱项是否一致。"
    sample = any(item.get("basis") == "sample" for item in items)
    tail = "其中样例对照会在学生加入并产生记录后改为真实数据。" if sample else ""
    return (
        f"「{top['name']}」完成率 {round(top['completion_rate'] * 100)}%，"
        f"平均掌握 {round((top.get('avg_mastery') or 0) * 100)}%，弱项是{top['top_weak'] or '暂无'}；"
        f"「{low['name']}」完成率 {round(low['completion_rate'] * 100)}%，"
        f"弱项是{low['top_weak'] or '暂无'}。{tail}"
    )


def sync_roster(db: Session, user: User) -> dict:
    loaded = load_roster()
    link = _link_for(db, user)
    link.provider = loaded["mode"]
    link.school_name = (user.school or link.school_name or "").strip()
    if loaded["status"] != "ok":
        link.status = "error"
        link.last_message = loaded["detail"][:200]
        _log(db, link, "pull", "error", {"detail": loaded["detail"]})
        db.commit()
        return {
            "status": "error",
            "mode": loaded["mode"],
            "detail": loaded["detail"],
            "created": [],
            "unchanged": [],
        }
    created = []
    unchanged = []
    for item in loaded["roster"]:
        existing = db.scalar(
            select(SchoolClass).where(
                SchoolClass.owner_id == user.id,
                SchoolClass.external_ref == item["external_id"],
            )
        )
        if existing:
            unchanged.append({"id": existing.id, "name": existing.name, "invite_code": existing.invite_code})
            continue
        school_class = SchoolClass(
            name=item["name"],
            description=(item["department"] or "教务名册")[:120],
            owner_id=user.id,
            invite_code=_invite_code(db),
            external_ref=item["external_id"],
        )
        db.add(school_class)
        db.flush()
        created.append(
            {
                "id": school_class.id,
                "name": school_class.name,
                "invite_code": school_class.invite_code,
                "listed_students": item["student_count"],
            }
        )
    link.status = "synced"
    link.last_sync_at = datetime.utcnow()
    link.last_message = loaded["detail"][:200]
    _log(
        db,
        link,
        "pull",
        "ok",
        {"created": len(created), "unchanged": len(unchanged), "mode": loaded["mode"]},
    )
    db.commit()
    return {
        "status": "ok",
        "mode": loaded["mode"],
        "detail": loaded["detail"] + "。名册中的人数只作对照，学生需使用邀请码加入后才有学习数据。",
        "created": created,
        "unchanged": unchanged,
    }


def push_summary(db: Session, user: User, class_id: int) -> dict:
    school_class = db.get(SchoolClass, class_id)
    if school_class is None or school_class.owner_id != user.id:
        raise ValueError("只能回传自己负责的班级")
    metrics = _class_metrics(db, school_class)
    summary = {
        "class_name": metrics["name"],
        "external_ref": metrics["external_ref"],
        "member_count": metrics["member_count"],
        "completion_rate": metrics["completion_rate"],
        "top_weak": metrics["top_weak"],
        "watch_count": metrics["watch_count"],
    }
    target = bridge_target()
    link = _link_for(db, user)
    link.provider = target["mode"]
    if target["mode"] == "http":
        try:
            _post_summary(summary)
            status = "ok"
            detail = "已把班级摘要交给已配置的教务接口。"
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            status = "error"
            detail = _public_failure()
    else:
        status = "accepted"
        detail = "尚未配置校级教务地址，摘要只保存在学迹内，没有发往外部系统。"
    link.status = "synced" if status != "error" else "error"
    link.last_message = detail[:200]
    _log(db, link, "push", "ok" if status != "error" else "error", summary)
    db.commit()
    return {"status": status, "mode": target["mode"], "detail": detail, "summary": summary}


def _post_summary(summary: dict) -> None:
    url = os.getenv("ACADEMIC_BRIDGE_URL", "").strip()
    token = os.getenv("ACADEMIC_BRIDGE_TOKEN", "").strip()
    if not url:
        raise ValueError("未配置教务接口地址")
    body = json.dumps({"summary": summary}, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=8) as response:
        response.read(20_000)


def recent_logs(db: Session, user: User, limit: int = 20) -> List[dict]:
    link = db.scalar(select(AcademicLink).where(AcademicLink.owner_id == user.id))
    if link is None:
        return []
    rows = db.scalars(
        select(AcademicSyncLog)
        .where(AcademicSyncLog.link_id == link.id)
        .order_by(AcademicSyncLog.id.desc())
        .limit(limit)
    ).all()
    items = []
    for row in rows:
        try:
            summary = json.loads(row.summary)
        except Exception:
            summary = {}
        items.append(
            {
                "id": row.id,
                "direction": row.direction,
                "status": row.status,
                "summary": summary,
                "created_at": row.created_at.isoformat(timespec="seconds"),
            }
        )
    return items
