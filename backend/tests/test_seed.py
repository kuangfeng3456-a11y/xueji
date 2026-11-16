from app import seed as seed_module
from app.models import (
    Buddy,
    ClassMember,
    Goal,
    KnowledgePoint,
    Mistake,
    Report,
    SchoolClass,
    Task,
    User,
)


def test_seed_creates_demo_dataset(capsys, db):
    seed_module.seed()
    output = capsys.readouterr().out
    assert "演示数据已生成" in output
    # 口令不再写死在仓库：默认随机生成并只在本次输出里打印
    assert seed_module.DEMO_PASSWORD in output
    assert len(seed_module.DEMO_PASSWORD) >= 8

    assert db.query(User).filter(User.username == "demo").one()
    goal = db.query(Goal).filter(Goal.exam_name.like("%四级%")).one()
    assert goal.daily_minutes == 90
    assert db.query(KnowledgePoint).filter(KnowledgePoint.goal_id == goal.id).count() == 20
    assert db.query(Task).filter(Task.goal_id == goal.id).count() == 45
    assert db.query(Mistake).filter(Mistake.goal_id == goal.id).count() == 8
    assert db.query(Report).filter(Report.goal_id == goal.id).count() == 1


def test_seed_creates_class_and_buddies(capsys, db):
    seed_module.seed()
    capsys.readouterr()

    demo = db.query(User).filter(User.username == "demo").one()
    assert db.query(User).count() == 1 + len(seed_module.STUDENTS)
    assert db.query(SchoolClass).filter(SchoolClass.name == seed_module.CLASS_NAME).count() == 1
    assert db.query(ClassMember).count() == 1 + len(seed_module.STUDENTS)
    assert db.query(Buddy).filter(Buddy.user_id == demo.id).count() == len(seed_module.STUDENTS)
    assert db.query(Buddy).filter(Buddy.buddy_id == demo.id).count() == len(seed_module.STUDENTS)


def test_seed_is_idempotent(capsys, db):
    seed_module.seed()
    capsys.readouterr()
    first_counts = {
        "users": db.query(User).count(),
        "classes": db.query(SchoolClass).count(),
        "members": db.query(ClassMember).count(),
        "buddies": db.query(Buddy).count(),
    }
    db.rollback()

    seed_module.seed()
    second = capsys.readouterr().out
    db.rollback()

    assert "已存在" in second
    assert db.query(User).filter(User.username == "demo").count() == 1
    assert db.query(User).count() == first_counts["users"]
    assert db.query(SchoolClass).count() == first_counts["classes"]
    assert db.query(ClassMember).count() == first_counts["members"]
    assert db.query(Buddy).count() == first_counts["buddies"]