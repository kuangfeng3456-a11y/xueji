"""演示数据种子脚本。

用法：
    python -m app.seed          # 若 demo 用户已存在则跳过
    python -m app.seed --reset  # 清空数据库并重建演示数据

密码来源（按优先级）：
    1. 环境变量 SEED_DEMO_PASSWORD / SEED_STUDENT_PASSWORD
    2. 未配置时随机生成，只在本次输出里打印一次
仓库里不再保存任何可用的固定密码，避免演示口令随代码一起流出。
"""

import os
import random
import secrets
import sys
from datetime import date, datetime, timedelta

from sqlalchemy import select

from .database import Base, SessionLocal, engine
from .models import (
    Buddy,
    ClassMember,
    Goal,
    KnowledgePoint,
    Material,
    Mistake,
    SchoolClass,
    Task,
    User,
)
from .security import hash_password
from .services.mastery_service import ensure_mastery, record_history
from .services.reporting import build_weekly_report
from .services.rules import MISTAKE_CATEGORIES, week_bounds

DEMO_USERNAME = os.getenv("SEED_DEMO_USERNAME", "demo").strip() or "demo"


def _seed_password(env_name: str) -> str:
    """种子账号密码：优先读环境变量，否则随机生成（仓库里不留固定口令）。"""
    configured = os.getenv(env_name, "").strip()
    if configured:
        return configured
    return secrets.token_urlsafe(9)


DEMO_PASSWORD = _seed_password("SEED_DEMO_PASSWORD")

KNOWLEDGE_TREE = [
    ("听力", None, 1.8, [
        ("短对话", 0.55),
        ("长对话", 0.48),
        ("听力篇章", 0.22),
    ]),
    ("阅读", None, 2.0, [
        ("选词填空", 0.52),
        ("长篇阅读", 0.46),
        ("仔细阅读", 0.31),
    ]),
    ("写作", None, 1.5, [
        ("议论文结构", 0.61),
        ("常用句型", 0.44),
    ]),
    ("翻译", None, 1.4, [
        ("中国文化", 0.39),
        ("句子结构", 0.28),
    ]),
    ("词汇", None, 1.6, [
        ("高频词汇", 0.58),
        ("熟词僻义", 0.33),
    ]),
    ("语法", None, 1.2, [
        ("从句", 0.5),
        ("非谓语动词", 0.3),
    ]),
]

MISTAKE_SEED = [
    ("听力篇章", "What does the woman imply about the meeting?", "She agrees to attend.", "She is not sure about the time.", "method"),
    ("听力篇章", "Why did the man call the woman?", "To ask for a report.", "To cancel an appointment.", "method"),
    ("听力篇章", "What can we infer from the conversation?", "The man will leave soon.", "The man has already left.", "concept"),
    ("仔细阅读", "According to the passage, the main reason is ______.", "lack of funding", "a change in policy", "concept"),
    ("熟词僻义", "The word 'address' in paragraph 2 most probably means ______.", "a speech", "a place", "careless"),
    ("翻译-句子结构", "翻译：随着科技的发展，人们的生活方式发生了巨大变化。", "People life changed a lot.", "People's lifestyles have changed dramatically with the development of technology.", "careless"),
    ("选词填空", "The company decided to ______ the new product next month.", "launch", "launching", "careless"),
    ("非谓语动词", "______ (finish) his homework, he went out to play.", "Finished", "Having finished", "method"),
]


def _build_points(db, goal, children_rows):
    parent_ids = {}
    for parent_name, _parent, weight, children in KNOWLEDGE_TREE:
        parent = KnowledgePoint(goal_id=goal.id, name=parent_name, parent_id=None, weight=weight)
        db.add(parent)
        db.flush()
        parent_ids[parent_name] = parent.id
        for child_name, mastery in children:
            child = KnowledgePoint(
                goal_id=goal.id, name=child_name, parent_id=parent.id, weight=round(1.0 + mastery, 2)
            )
            db.add(child)
            db.flush()
            children_rows.append((child, mastery))
    return children_rows


CLASS_NAME = "24 级人工智能 4 班"
# 演示班级里同学的初始密码：与 demo 同源，避免另存一份固定口令
DEFAULT_PASSWORD = DEMO_PASSWORD

STUDENTS = [
    {
        "username": "stu_lin",
        "nickname": "林晓",
        "school": "信息工程学院",
        "exam": "考研数学（数一）",
        "days": 32,
        "base": 0.42,
        "done_rate": 0.85,
        "hours": [8, 20],
    },
    {
        "username": "stu_chen",
        "nickname": "陈宇",
        "school": "计算机学院",
        "exam": "华为 HCIA-Datacom",
        "days": 18,
        "base": 0.56,
        "done_rate": 0.72,
        "hours": [14, 22],
    },
    {
        "username": "stu_wang",
        "nickname": "王悦",
        "school": "外国语学院",
        "exam": "大学英语六级",
        "days": 52,
        "base": 0.63,
        "done_rate": 0.92,
        "hours": [7, 19],
    },
]

STUDENT_POINTS = [
    "基础概念",
    "核心公式",
    "典型题型",
    "综合应用",
    "易错点",
    "真题训练",
    "方法技巧",
    "冲刺模拟",
]


def _seed_student(db, spec, today):
    user = db.scalar(select(User).where(User.username == spec["username"]))
    if user is None:
        user = User(
            username=spec["username"],
            password_hash=hash_password(DEFAULT_PASSWORD),
            nickname=spec["nickname"],
            school=spec["school"],
        )
        db.add(user)
        db.flush()

    goal = db.scalar(select(Goal).where(Goal.user_id == user.id))
    if goal is None:
        goal = Goal(
            user_id=user.id,
            exam_name=spec["exam"],
            exam_date=today + timedelta(days=spec["days"]),
            daily_minutes=90,
        )
        db.add(goal)
        db.flush()

    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)).all()
    if not points:
        parent = KnowledgePoint(goal_id=goal.id, name=spec["exam"], parent_id=None, weight=1.8)
        db.add(parent)
        db.flush()
        for index, name in enumerate(STUDENT_POINTS):
            point = KnowledgePoint(
                goal_id=goal.id, name=name, parent_id=parent.id, weight=1.0 + (index % 3) * 0.2
            )
            db.add(point)
            db.flush()
            record = ensure_mastery(db, user.id, point)
            record.value = round(max(0.08, min(0.95, spec["base"] + random.uniform(-0.15, 0.15))), 3)
            record.next_review_at = today + timedelta(days=random.randint(1, 5))
            record.review_stage = random.randint(0, 2)
            record_history(db, user.id, point.id, record.value, today)
        db.flush()
        points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)).all()

    has_tasks = db.scalar(select(Task).where(Task.user_id == user.id))
    if not has_tasks:
        leaf_points = [point for point in points if point.parent_id is not None]
        for offset in range(14, -1, -1):
            day = today - timedelta(days=offset)
            for index in range(2):
                if not leaf_points:
                    break
                point = random.choice(leaf_points)
                done = random.random() < spec["done_rate"]
                hour = spec["hours"][index % len(spec["hours"])]
                db.add(
                    Task(
                        user_id=user.id,
                        goal_id=goal.id,
                        kp_id=point.id,
                        day=day,
                        title=f"练习：{point.name}",
                        type="practice" if index else "review",
                        duration_min=30,
                        status="done" if done else "skipped",
                        reason="按你的目标与水平排入的同伴任务。",
                        priority=round(random.uniform(0.8, 3.0), 2),
                        source="plan",
                        done_at=datetime.combine(day, datetime.min.time()) + timedelta(hours=hour)
                        if done
                        else None,
                    )
                )
    db.flush()
    return user


def seed_materials(db, demo_user) -> None:
    """补一份旧版资料与一份新版大纲，便于演示内容时效雷达。"""
    goal = db.scalar(
        select(Goal).where(Goal.user_id == demo_user.id).order_by(Goal.created_at.desc()).limit(1)
    )
    if not goal:
        return
    existing = db.scalar(
        select(Material).where(Material.user_id == demo_user.id, Material.goal_id == goal.id)
    )
    if existing:
        return
    db.add(
        Material(
            user_id=demo_user.id,
            goal_id=goal.id,
            filename="2023 版四级真题词汇（旧版）",
            content=(
                "2023 年四级高频词汇整理，包含 800 个核心词与 200 道旧版真题。"
                "资料基于 2023 年考纲，未包含 2026 年新增题型与听力改革说明。"
            ),
        )
    )
    db.add(
        Material(
            user_id=demo_user.id,
            goal_id=goal.id,
            filename="2026 年四级新大纲与题型摘要",
            content=(
                "2026 年大学英语四级考试大纲摘要：听力增加长对话比例，阅读新增信息匹配题，"
                "写作强调逻辑结构。包含最新考试说明与样题。"
            ),
        )
    )
    db.flush()


def seed_social(db, demo_user) -> None:
    """补齐班级看板与学习搭子的演示数据，可重复执行。"""
    today = date.today()
    students = [_seed_student(db, spec, today) for spec in STUDENTS]

    school_class = db.scalar(select(SchoolClass).where(SchoolClass.name == CLASS_NAME))
    if school_class is None:
        school_class = SchoolClass(
            name=CLASS_NAME,
            description="人工智能专业 24 级 4 班 · 备考互助小组",
            owner_id=demo_user.id,
            invite_code="XUEJI4",
        )
        db.add(school_class)
        db.flush()

    member_ids = {
        row.user_id
        for row in db.scalars(select(ClassMember).where(ClassMember.class_id == school_class.id)).all()
    }
    if demo_user.id not in member_ids:
        db.add(ClassMember(class_id=school_class.id, user_id=demo_user.id, role="owner"))
    for student in students:
        if student.id not in member_ids:
            db.add(ClassMember(class_id=school_class.id, user_id=student.id, role="student"))

    existing_buddies = {
        row.buddy_id for row in db.scalars(select(Buddy).where(Buddy.user_id == demo_user.id)).all()
    }
    for student in students:
        if student.id not in existing_buddies:
            db.add(Buddy(user_id=demo_user.id, buddy_id=student.id))
            db.add(Buddy(user_id=student.id, buddy_id=demo_user.id))
    db.flush()


def seed() -> None:
    if "--reset" in sys.argv:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = db.scalar(select(User).where(User.username == DEMO_USERNAME))
        if existing:
            seed_social(db, existing)
            seed_materials(db, existing)
            db.commit()
            print("演示账号已存在，已补齐班级、学习搭子、同伴数据与时效演示资料。")
            print(f"  班级邀请码：XUEJI4（{CLASS_NAME}）")
            return

        random.seed(42)
        user = User(
            username=DEMO_USERNAME,
            password_hash=hash_password(DEMO_PASSWORD),
            nickname="小林",
            school="计算机学院",
        )
        db.add(user)
        db.flush()

        today = date.today()
        goal = Goal(
            user_id=user.id,
            exam_name="大学英语四级（CET-4）",
            exam_date=today + timedelta(days=45),
            daily_minutes=90,
        )
        db.add(goal)
        db.flush()

        children = _build_points(db, goal, [])
        point_map = {point.name: point for point in db.scalars(
            select(KnowledgePoint).where(KnowledgePoint.goal_id == goal.id)
        ).all()}

        for point, target in children:
            record = ensure_mastery(db, user.id, point)
            record.value = target
            record.next_review_at = today + timedelta(days=random.randint(1, 6))
            record.review_stage = random.randint(0, 2)
            for offset in range(21, -1, -1):
                if offset == 0:
                    value = target
                else:
                    value = max(0.05, target - 0.012 * offset + random.uniform(-0.01, 0.01))
                record_history(db, user.id, point.id, value, today - timedelta(days=offset))
        db.flush()

        leaf_points = [point for point, _ in children]
        task_titles = {
            "study": "学习",
            "review": "复习",
            "practice": "练习",
        }
        for offset in range(14, -1, -1):
            day = today - timedelta(days=offset)
            picks = random.sample(leaf_points, 3)
            for index, point in enumerate(picks):
                status = "done"
                if offset > 0 and random.random() < 0.15:
                    status = "skipped"
                elif offset == 0 and index == 2:
                    status = "pending"
                kind = "review" if index == 0 else ("study" if index == 1 else "practice")
                task = Task(
                    user_id=user.id,
                    goal_id=goal.id,
                    kp_id=point.id,
                    day=day,
                    title=f"{task_titles[kind]}：{point.name}",
                    type=kind,
                    duration_min=30,
                    status=status,
                    reason="按知识点权重与掌握度排入的微任务。",
                    priority=round(random.uniform(0.8, 3.2), 2),
                    source="plan",
                    done_at=datetime.combine(day, datetime.min.time()) + timedelta(hours=20)
                    if status == "done"
                    else None,
                )
                db.add(task)
        db.flush()

        for index, (kp_name, question, user_answer, correct_answer, category) in enumerate(MISTAKE_SEED):
            point = point_map.get(kp_name)
            created = datetime.utcnow() - timedelta(days=6 - index // 2, hours=index)
            db.add(
                Mistake(
                    user_id=user.id,
                    goal_id=goal.id,
                    kp_id=point.id if point else None,
                    question=question,
                    user_answer=user_answer,
                    correct_answer=correct_answer,
                    category=category,
                    category_label=MISTAKE_CATEGORIES[category],
                    suggestion={
                        "concept": "回到对应知识点，用 5 分钟重读定义并画出概念图，再用 2 道基础题确认理解。",
                        "method": "先看例题的解题步骤，再独立重做本题；把关键步骤写成 3 条方法卡片。",
                        "careless": "答案思路是对的，差在细节。做题时强制检查单位、符号和题干关键词。",
                        "time": "今天先做 10 分钟限时训练，每题限时 2 分钟，超时就标记跳过。",
                    }[category],
                    source="text",
                    created_at=created,
                )
            )
        db.commit()

        last_monday, _ = week_bounds(today - timedelta(days=7))
        build_weekly_report(db, user, goal, week_start=last_monday)
        seed_social(db, user)
        seed_materials(db, user)
        db.commit()

        print("演示数据已生成：")
        print(f"  账号：{DEMO_USERNAME}")
        print(f"  密码：{DEMO_PASSWORD}")
        if not os.getenv("SEED_DEMO_PASSWORD", "").strip():
            print("  （口令为随机生成，仅本次输出可见；需要固定口令请设置 SEED_DEMO_PASSWORD 后按 --reset 重跑）")
        print(f"  考试：{goal.exam_name}，还剩 45 天，每天 90 分钟")
        print(f"  知识点：{len(point_map)} 个，历史任务 45 条，错题 {len(MISTAKE_SEED)} 道")
        print(f"  班级：{CLASS_NAME}，邀请码 XUEJI4，含 3 位同学与学习搭子")
    finally:
        db.close()


if __name__ == "__main__":
    seed()