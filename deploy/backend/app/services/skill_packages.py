"""多学科 Skill 包市场：内置可一键应用的学科知识点包。"""

import json
import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Goal, KnowledgePoint, Mastery, SkillPackage
from .knowledge import persist_points


def _leaf(name: str, parent: Optional[str], weight: float = 1.0) -> dict:
    return {"name": name, "parent": parent, "weight": weight}


PACKAGES = [
    {
        "slug": "cet4",
        "name": "大学英语四级包",
        "subject": "英语",
        "description": "听力、阅读、写作、翻译、词汇、语法六大模块，适合 CET-4 / 六级起步。",
        "tags": ["四六级", "大学英语", "词汇"],
        "points": [
            {"name": "听力", "parent": None, "weight": 1.8},
            _leaf("短对话", "听力", 1.4),
            _leaf("长对话", "听力", 1.5),
            _leaf("听力篇章", "听力", 1.6),
            {"name": "阅读", "parent": None, "weight": 2.0},
            _leaf("选词填空", "阅读", 1.4),
            _leaf("长篇阅读", "阅读", 1.7),
            _leaf("仔细阅读", "阅读", 1.9),
            {"name": "写作", "parent": None, "weight": 1.5},
            _leaf("议论文结构", "写作", 1.4),
            _leaf("常用句型", "写作", 1.3),
            {"name": "翻译", "parent": None, "weight": 1.4},
            _leaf("中国文化", "翻译", 1.3),
            _leaf("句子结构", "翻译", 1.4),
            {"name": "词汇", "parent": None, "weight": 1.6},
            _leaf("高频词汇", "词汇", 1.6),
            _leaf("熟词僻义", "词汇", 1.4),
            {"name": "语法", "parent": None, "weight": 1.2},
            _leaf("从句", "语法", 1.3),
            _leaf("非谓语动词", "语法", 1.2),
        ],
    },
    {
        "slug": "kaoyan-math",
        "name": "考研数学包",
        "subject": "数学",
        "description": "高数、线代、概率论三大板块，按考点权重排入每日可用时间。",
        "tags": ["考研", "数学一", "数学二"],
        "points": [
            {"name": "高等数学", "parent": None, "weight": 2.0},
            _leaf("函数与极限", "高等数学", 1.8),
            _leaf("导数与微分", "高等数学", 1.7),
            _leaf("不定积分", "高等数学", 1.6),
            _leaf("定积分", "高等数学", 1.8),
            _leaf("级数", "高等数学", 1.4),
            {"name": "线性代数", "parent": None, "weight": 1.7},
            _leaf("行列式", "线性代数", 1.4),
            _leaf("矩阵", "线性代数", 1.7),
            _leaf("向量", "线性代数", 1.5),
            _leaf("特征值与二次型", "线性代数", 1.6),
            {"name": "概率论与数理统计", "parent": None, "weight": 1.6},
            _leaf("随机变量", "概率论与数理统计", 1.5),
            _leaf("常见分布", "概率论与数理统计", 1.4),
            _leaf("期望与方差", "概率论与数理统计", 1.6),
            _leaf("大数定律与中心极限定理", "概率论与数理统计", 1.3),
        ],
    },
    {
        "slug": "hcia-datacom",
        "name": "HCIA-Datacom 包",
        "subject": "网络",
        "description": "覆盖数通认证的网络基础、路由交换、设备管理与安全考点。",
        "tags": ["华为认证", "HCIA", "数通"],
        "points": [
            {"name": "网络基础", "parent": None, "weight": 1.9},
            _leaf("OSI 与 TCP/IP 模型", "网络基础", 1.5),
            _leaf("IP 编址与子网划分", "网络基础", 1.8),
            _leaf("VLAN", "网络基础", 1.6),
            _leaf("STP", "网络基础", 1.4),
            {"name": "路由技术", "parent": None, "weight": 1.8},
            _leaf("静态路由", "路由技术", 1.4),
            _leaf("OSPF", "路由技术", 1.9),
            _leaf("RIP", "路由技术", 1.2),
            {"name": "设备管理", "parent": None, "weight": 1.3},
            _leaf("华为 VRP 命令", "设备管理", 1.5),
            _leaf("SSH 与 SNMP", "设备管理", 1.2),
            {"name": "网络安全", "parent": None, "weight": 1.4},
            _leaf("ACL", "网络安全", 1.5),
            _leaf("NAT", "网络安全", 1.4),
            _leaf("防火墙基础", "网络安全", 1.3),
        ],
    },
    {
        "slug": "computer-level2",
        "name": "计算机二级 Python 包",
        "subject": "计算机",
        "description": "Python 基础、数据结构、数据库与办公应用，适合全国计算机等级考试。",
        "tags": ["计算机二级", "Python", "等级考试"],
        "points": [
            {"name": "Python 基础", "parent": None, "weight": 1.8},
            _leaf("数据类型", "Python 基础", 1.5),
            _leaf("控制结构", "Python 基础", 1.5),
            _leaf("函数", "Python 基础", 1.6),
            _leaf("文件操作", "Python 基础", 1.4),
            {"name": "数据结构", "parent": None, "weight": 1.6},
            _leaf("列表与元组", "数据结构", 1.4),
            _leaf("字典与集合", "数据结构", 1.4),
            _leaf("字符串处理", "数据结构", 1.5),
            {"name": "数据库", "parent": None, "weight": 1.3},
            _leaf("SQL 基础", "数据库", 1.4),
            _leaf("MySQL 操作", "数据库", 1.2),
            {"name": "办公应用", "parent": None, "weight": 1.1},
            _leaf("Excel 数据处理", "办公应用", 1.2),
            _leaf("Word 文档处理", "办公应用", 1.0),
        ],
    },
]


def ensure_packages(db: Session) -> None:
    """把内置包同步到数据库，重复启动不会产生重复记录。"""
    existing = {row.slug: row for row in db.scalars(select(SkillPackage)).all()}
    for package in PACKAGES:
        config = json.dumps({"points": package["points"]}, ensure_ascii=False)
        row = existing.get(package["slug"])
        if row is None:
            db.add(
                SkillPackage(
                    slug=package["slug"],
                    name=package["name"],
                    subject=package["subject"],
                    description=package["description"],
                    tags=",".join(package["tags"]),
                    config=config,
                    official=True,
                )
            )
        else:
            row.name = package["name"]
            row.subject = package["subject"]
            row.description = package["description"]
            row.tags = ",".join(package["tags"])
            row.config = config
    db.flush()


def package_views(db: Session, goal: Optional[Goal]) -> List[dict]:
    ensure_packages(db)
    db.commit()
    rows = db.scalars(select(SkillPackage).order_by(SkillPackage.id.asc())).all()

    point_map = {}
    mastery_map = {}
    if goal is not None:
        points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)).all()
        point_map = {point.name.lower(): point for point in points}
        point_ids = [point.id for point in points]
        if point_ids:
            mastery_map = {
                row.kp_id: row
                for row in db.scalars(
                    select(Mastery).where(
                        Mastery.user_id == goal.user_id,
                        Mastery.kp_id.in_(point_ids),
                    )
                ).all()
            }

    result = []
    for row in rows:
        try:
            points = json.loads(row.config).get("points", [])
        except Exception:
            points = []
        names = [str(item.get("name", "")).lower() for item in points if item.get("name")]
        applied = sum(1 for name in names if name in point_map) if goal else 0
        details = []
        for item in points:
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            point = point_map.get(name.lower())
            record = mastery_map.get(point.id) if point else None
            try:
                weight = float(item.get("weight", 1.0))
            except (TypeError, ValueError):
                weight = 1.0
            details.append(
                {
                    "name": name,
                    "parent": item.get("parent"),
                    "weight": round(weight, 2),
                    "kp_id": point.id if point else None,
                    "mastery": record.value if record else None,
                    "next_review_at": record.next_review_at if record else None,
                }
            )
        result.append(
            {
                "slug": row.slug,
                "name": row.name,
                "subject": row.subject,
                "description": row.description,
                "tags": [tag for tag in row.tags.split(",") if tag],
                "official": bool(row.official),
                "point_count": len(names),
                "applied_count": applied,
                "applied": bool(names) and applied >= len(names),
                "points": [item.get("name") for item in points if item.get("name")],
                "point_details": details,
            }
        )
    return result


def apply_package(db: Session, user_id: int, goal: Goal, slug: str) -> dict:
    ensure_packages(db)
    row = db.scalar(select(SkillPackage).where(SkillPackage.slug == slug))
    if row is None:
        raise ValueError("Skill 包不存在")
    try:
        points = json.loads(row.config).get("points", [])
    except Exception:
        points = []
    created = persist_points(db, user_id, goal, points)
    db.commit()
    return {"package": row.name, "created": len(created), "total": len(points)}

def create_package(
    db: Session,
    name: str,
    subject: str,
    description: str,
    tags: List[str],
    points: List[dict],
) -> dict:
    """把用户自定义的知识点树注册为一个 Skill 包（official=False），可在市场中直接应用。"""
    cleaned: List[dict] = []
    seen = set()
    for item in points:
        point_name = str(item.get("name", "")).strip()
        if not point_name or point_name in seen:
            continue
        seen.add(point_name)
        try:
            weight = float(item.get("weight", 1.0))
        except (TypeError, ValueError):
            weight = 1.0
        parent = str(item.get("parent") or "").strip() or None
        cleaned.append(
            {"name": point_name, "parent": parent, "weight": round(min(5.0, max(0.1, weight)), 2)}
        )
    if not cleaned:
        raise ValueError("至少需要一个知识点")
    tops = {item["name"] for item in cleaned if not item["parent"]}
    for item in cleaned:
        if item["parent"] and item["parent"] not in tops:
            # 父节点未定义时提升为顶级，保证知识点树始终可落地
            item["parent"] = None

    slug = "custom-" + uuid.uuid4().hex[:8]
    db.add(
        SkillPackage(
            slug=slug,
            name=name.strip(),
            subject=(subject or "通用").strip(),
            description=(description or "").strip(),
            tags=",".join(tag.strip() for tag in tags if tag and tag.strip()),
            config=json.dumps({"points": cleaned}, ensure_ascii=False),
            official=False,
        )
    )
    db.commit()
    return {"slug": slug, "name": name.strip(), "point_count": len(cleaned), "official": False}
