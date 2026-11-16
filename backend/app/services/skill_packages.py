"""多学科 Skill 包市场：内置可一键应用的学科知识点包。"""

import json
import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Goal, KnowledgePoint, Mastery, SkillPackage, User
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
    {
        "slug": "cet6",
        "name": "大学英语六级包",
        "subject": "英语",
        "description": "六级听力、阅读、写作、翻译与学术词汇，适合已通过四级的同学。",
        "tags": ["六级", "大学英语", "写作"],
        "points": [
            {"name": "六级听力", "parent": None, "weight": 1.8},
            _leaf("长对话推理", "六级听力", 1.5),
            _leaf("讲座听力", "六级听力", 1.7),
            {"name": "六级阅读", "parent": None, "weight": 2.0},
            _leaf("仔细阅读", "六级阅读", 1.8),
            _leaf("信息匹配", "六级阅读", 1.6),
            {"name": "六级写作翻译", "parent": None, "weight": 1.6},
            _leaf("议论文论证", "六级写作翻译", 1.5),
            _leaf("段落翻译", "六级写作翻译", 1.4),
        ],
    },
    {
        "slug": "kaoyan-english",
        "name": "考研英语包",
        "subject": "英语",
        "description": "完形、阅读、新题型、翻译与写作，按考研英语一常见模块组织。",
        "tags": ["考研", "英语一", "阅读"],
        "points": [
            {"name": "完形填空", "parent": None, "weight": 1.3},
            _leaf("逻辑衔接", "完形填空", 1.3),
            _leaf("词义辨析", "完形填空", 1.4),
            {"name": "阅读理解", "parent": None, "weight": 2.0},
            _leaf("主旨题", "阅读理解", 1.6),
            _leaf("推理题", "阅读理解", 1.7),
            {"name": "写作", "parent": None, "weight": 1.6},
            _leaf("小作文", "写作", 1.4),
            _leaf("大作文", "写作", 1.7),
        ],
    },
    {
        "slug": "data-structure",
        "name": "数据结构包",
        "subject": "计算机",
        "description": "线性表、树、图、查找与排序，适合课程考试和考研专业课。",
        "tags": ["数据结构", "考研", "计算机"],
        "points": [
            {"name": "线性结构", "parent": None, "weight": 1.6},
            _leaf("栈与队列", "线性结构", 1.5),
            _leaf("链表", "线性结构", 1.4),
            {"name": "树与图", "parent": None, "weight": 1.9},
            _leaf("二叉树遍历", "树与图", 1.7),
            _leaf("图的遍历", "树与图", 1.6),
            {"name": "查找与排序", "parent": None, "weight": 1.7},
            _leaf("二分查找", "查找与排序", 1.4),
            _leaf("快速排序", "查找与排序", 1.6),
        ],
    },
    {
        "slug": "operating-system",
        "name": "操作系统包",
        "subject": "计算机",
        "description": "进程、内存、文件和死锁，覆盖操作系统课程的核心考点。",
        "tags": ["操作系统", "考研", "计算机"],
        "points": [
            {"name": "进程管理", "parent": None, "weight": 1.9},
            _leaf("进程与线程", "进程管理", 1.6),
            _leaf("调度算法", "进程管理", 1.7),
            {"name": "内存管理", "parent": None, "weight": 1.8},
            _leaf("分页", "内存管理", 1.6),
            _leaf("虚拟内存", "内存管理", 1.7),
            {"name": "文件与死锁", "parent": None, "weight": 1.5},
            _leaf("文件系统", "文件与死锁", 1.3),
            _leaf("死锁条件", "文件与死锁", 1.5),
        ],
    },
    {
        "slug": "computer-network",
        "name": "计算机网络包",
        "subject": "计算机",
        "description": "按五层模型整理网络课程考点，和认证包互补，面向课程考试。",
        "tags": ["计算机网络", "考研", "协议"],
        "points": [
            {"name": "物理与链路", "parent": None, "weight": 1.4},
            _leaf("编码与交换", "物理与链路", 1.2),
            _leaf("差错控制", "物理与链路", 1.3),
            {"name": "网络与传输", "parent": None, "weight": 1.9},
            _leaf("IP 与路由", "网络与传输", 1.7),
            _leaf("TCP 与 UDP", "网络与传输", 1.8),
            {"name": "应用层", "parent": None, "weight": 1.5},
            _leaf("HTTP", "应用层", 1.4),
            _leaf("DNS", "应用层", 1.3),
        ],
    },
    {
        "slug": "discrete-math",
        "name": "离散数学包",
        "subject": "数学",
        "description": "命题逻辑、集合、图论与关系，适合计算机专业基础课。",
        "tags": ["离散数学", "逻辑", "图论"],
        "points": [
            {"name": "数理逻辑", "parent": None, "weight": 1.7},
            _leaf("命题逻辑", "数理逻辑", 1.6),
            _leaf("谓词逻辑", "数理逻辑", 1.5),
            {"name": "集合与关系", "parent": None, "weight": 1.6},
            _leaf("集合运算", "集合与关系", 1.3),
            _leaf("等价关系", "集合与关系", 1.5),
            {"name": "图论", "parent": None, "weight": 1.6},
            _leaf("路径与连通", "图论", 1.4),
            _leaf("树", "图论", 1.4),
        ],
    },
    {
        "slug": "college-physics",
        "name": "大学物理包",
        "subject": "物理",
        "description": "力学、电磁学和波动光学，按大学物理课程的主线整理。",
        "tags": ["大学物理", "力学", "电磁学"],
        "points": [
            {"name": "力学", "parent": None, "weight": 1.8},
            _leaf("牛顿定律", "力学", 1.6),
            _leaf("动量与能量", "力学", 1.6),
            {"name": "电磁学", "parent": None, "weight": 1.8},
            _leaf("静电场", "电磁学", 1.6),
            _leaf("电磁感应", "电磁学", 1.5),
            {"name": "波动与光学", "parent": None, "weight": 1.4},
            _leaf("机械波", "波动与光学", 1.3),
            _leaf("干涉与衍射", "波动与光学", 1.4),
        ],
    },
    {
        "slug": "c-programming",
        "name": "C 语言程序设计包",
        "subject": "计算机",
        "description": "语法、指针、结构体与文件，适合程序设计基础课。",
        "tags": ["C语言", "程序设计", "指针"],
        "points": [
            {"name": "语言基础", "parent": None, "weight": 1.5},
            _leaf("数据类型", "语言基础", 1.3),
            _leaf("控制结构", "语言基础", 1.4),
            {"name": "函数与指针", "parent": None, "weight": 1.9},
            _leaf("函数调用", "函数与指针", 1.5),
            _leaf("指针与数组", "函数与指针", 1.8),
            {"name": "结构与文件", "parent": None, "weight": 1.4},
            _leaf("结构体", "结构与文件", 1.4),
            _leaf("文件读写", "结构与文件", 1.3),
        ],
    },
    {
        "slug": "marxism",
        "name": "马克思主义基本原理包",
        "subject": "思政",
        "description": "唯物论、辩证法、认识论和历史唯物主义，面向公共课复习。",
        "tags": ["思政", "马原", "公共课"],
        "points": [
            {"name": "唯物论", "parent": None, "weight": 1.5},
            _leaf("物质与意识", "唯物论", 1.4),
            _leaf("实践", "唯物论", 1.4),
            {"name": "辩证法", "parent": None, "weight": 1.7},
            _leaf("对立统一", "辩证法", 1.6),
            _leaf("质量互变", "辩证法", 1.4),
            {"name": "认识论与历史观", "parent": None, "weight": 1.6},
            _leaf("认识过程", "认识论与历史观", 1.4),
            _leaf("社会基本矛盾", "认识论与历史观", 1.5),
        ],
    },
    {
        "slug": "software-engineering",
        "name": "软件工程包",
        "subject": "计算机",
        "description": "需求、设计、测试与过程模型，适合软件工程课程复习。",
        "tags": ["软件工程", "测试", "需求"],
        "points": [
            {"name": "需求与设计", "parent": None, "weight": 1.7},
            _leaf("需求获取", "需求与设计", 1.5),
            _leaf("体系结构", "需求与设计", 1.5),
            {"name": "实现与测试", "parent": None, "weight": 1.7},
            _leaf("单元测试", "实现与测试", 1.4),
            _leaf("集成测试", "实现与测试", 1.4),
            {"name": "过程管理", "parent": None, "weight": 1.4},
            _leaf("瀑布与迭代", "过程管理", 1.3),
            _leaf("配置管理", "过程管理", 1.2),
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
                    status="approved",
                    shared=True,
                )
            )
        else:
            row.name = package["name"]
            row.subject = package["subject"]
            row.description = package["description"]
            row.tags = ",".join(package["tags"])
            row.config = config
            row.official = True
            row.status = "approved"
            row.shared = True
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
        status = row.status or "approved"
        if not row.official and (status != "approved" or not row.shared):
            continue
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
                "status": status,
                "shared": bool(row.shared),
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
    if (row.status or "approved") != "approved":
        raise ValueError("该学科包还在审核中，通过后才能使用")
    if not row.official and not row.shared:
        raise ValueError("该学科包尚未分享")
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
    author_id: Optional[int] = None,
) -> dict:
    """教师提交自定义知识点树。新建包为待审核，通过并分享后才会出现在学科包列表。"""
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
            status="pending",
            shared=False,
            author_id=author_id,
            review_note="",
        )
    )
    db.commit()
    return {
        "slug": slug,
        "name": name.strip(),
        "point_count": len(cleaned),
        "official": False,
        "status": "pending",
        "shared": False,
    }


def _points_of(row: SkillPackage) -> List[dict]:
    try:
        return list(json.loads(row.config).get("points", []))
    except Exception:
        return []


def package_brief(row: SkillPackage, author_name: str = "") -> dict:
    points = _points_of(row)
    return {
        "slug": row.slug,
        "name": row.name,
        "subject": row.subject,
        "description": row.description,
        "tags": [tag for tag in (row.tags or "").split(",") if tag],
        "official": bool(row.official),
        "status": row.status or "approved",
        "shared": bool(row.shared),
        "share_code": row.share_code or "",
        "author_id": row.author_id,
        "author_name": author_name,
        "review_note": row.review_note or "",
        "point_count": len(points),
        "points": [item.get("name") for item in points if item.get("name")],
    }


def review_queue(db: Session, author_id: Optional[int] = None) -> List[dict]:
    ensure_packages(db)
    db.commit()
    stmt = select(SkillPackage).where(SkillPackage.official.is_(False)).order_by(SkillPackage.id.desc())
    if author_id is not None:
        stmt = stmt.where(SkillPackage.author_id == author_id)
    rows = db.scalars(stmt).all()
    names = {}
    author_ids = {row.author_id for row in rows if row.author_id}
    if author_ids:
        for user in db.scalars(select(User).where(User.id.in_(author_ids))).all():
            names[user.id] = user.nickname or user.username
    return [package_brief(row, names.get(row.author_id, "")) for row in rows]


def review_package(db: Session, reviewer_id: int, slug: str, action: str, note: str = "") -> dict:
    ensure_packages(db)
    row = db.scalar(select(SkillPackage).where(SkillPackage.slug == slug))
    if row is None or row.official:
        raise ValueError("只能审核教师提交的学科包")
    if row.author_id == reviewer_id:
        raise ValueError("不能审核自己提交的学科包")
    if action not in ("approve", "reject"):
        raise ValueError("审核动作无效")
    row.status = "approved" if action == "approve" else "rejected"
    row.reviewer_id = reviewer_id
    row.review_note = (note or "").strip()[:200]
    if row.status != "approved":
        row.shared = False
        row.share_code = None
    db.commit()
    return package_brief(row)


def share_package(db: Session, user_id: int, slug: str) -> dict:
    row = db.scalar(select(SkillPackage).where(SkillPackage.slug == slug))
    if row is None or row.official:
        raise ValueError("学科包不存在")
    if row.author_id != user_id:
        raise ValueError("只有提交者可以分享")
    if (row.status or "") != "approved":
        raise ValueError("审核通过后才能分享")
    if not row.share_code:
        row.share_code = uuid.uuid4().hex[:8]
    row.shared = True
    db.commit()
    return package_brief(row)


def redeem_package(db: Session, user_id: int, goal: Goal, share_code: str) -> dict:
    code = (share_code or "").strip()
    row = db.scalar(select(SkillPackage).where(SkillPackage.share_code == code))
    if row is None or not row.shared or (row.status or "") != "approved":
        raise ValueError("分享码无效或学科包尚未开放")
    return apply_package(db, user_id, goal, row.slug)
