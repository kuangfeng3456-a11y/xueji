"""知识依赖图与潜在漏洞诊断（knowledge_map）单元测试。"""

from sqlalchemy import select

from app.models import (
    KnowledgeDependency,
    KnowledgeGap,
    KnowledgePoint,
    Mastery,
    Mistake,
)
from app.services.knowledge_map import (
    _mastery_map,
    _mistake_counts,
    build_graph,
    ensure_dependencies,
    prerequisites,
    refresh_candidates,
)


def _point(db, goal, name, parent_id=None, weight=1.0):
    point = KnowledgePoint(goal_id=goal.id, name=name, parent_id=parent_id, weight=weight)
    db.add(point)
    db.flush()
    return point


def _mastery(db, user, point, value):
    db.add(Mastery(user_id=user.id, kp_id=point.id, value=value))
    db.flush()


def _mistake(db, user, goal, point, category="concept"):
    db.add(
        Mistake(
            user_id=user.id,
            goal_id=goal.id,
            kp_id=point.id,
            question="子网划分题目",
            user_answer="错误答案",
            correct_answer="正确答案",
            category=category,
            category_label="概念不清",
        )
    )
    db.flush()


# --------------------------------------------------------------------------
# ensure_dependencies
# --------------------------------------------------------------------------


def test_ensure_dependencies_builds_tree_and_sequence_edges(db, db_user_goal):
    user, goal = db_user_goal
    root = _point(db, goal, "听力")
    first = _point(db, goal, "短对话", root.id)
    second = _point(db, goal, "长对话", root.id)
    third = _point(db, goal, "听力篇章", root.id)
    db.commit()

    ensure_dependencies(db, goal)

    edges = db.scalars(
        select(KnowledgeDependency).where(KnowledgeDependency.goal_id == goal.id)
    ).all()
    triples = {(edge.from_kp_id, edge.to_kp_id, edge.source) for edge in edges}
    assert triples == {
        (root.id, first.id, "tree"),
        (root.id, second.id, "tree"),
        (root.id, third.id, "tree"),
        (first.id, second.id, "sequence"),
        (second.id, third.id, "sequence"),
    }

    # 再次调用应幂等，不会重复插入
    ensure_dependencies(db, goal)
    assert (
        len(
            db.scalars(
                select(KnowledgeDependency).where(KnowledgeDependency.goal_id == goal.id)
            ).all()
        )
        == 5
    )


def test_ensure_dependencies_without_points_is_noop(db, db_user_goal):
    user, goal = db_user_goal

    ensure_dependencies(db, goal)
    ensure_dependencies(db, goal)

    assert db.scalars(select(KnowledgeDependency)).all() == []


def test_ensure_dependencies_skips_duplicate_tree_and_sequence_edges(db, db_user_goal):
    user, goal = db_user_goal
    parent = _point(db, goal, "自环父节点")
    child = _point(db, goal, "子节点")
    # 父节点自引用且与子节点拥有同一个父节点，使 tree 边与 sequence 边重复
    parent.parent_id = parent.id
    child.parent_id = parent.id
    db.commit()

    ensure_dependencies(db, goal)

    edges = db.scalars(
        select(KnowledgeDependency).where(KnowledgeDependency.goal_id == goal.id)
    ).all()
    pairs = [(edge.from_kp_id, edge.to_kp_id) for edge in edges]
    assert pairs.count((parent.id, child.id)) == 1
    assert (parent.id, parent.id) in pairs
    assert len(edges) == 2


# --------------------------------------------------------------------------
# 掌握度 / 错题计数辅助函数
# --------------------------------------------------------------------------


def test_mastery_and_mistake_helpers_filter_goal_and_null_kp(db, db_user_goal):
    user, goal = db_user_goal
    first = _point(db, goal, "短对话")
    second = _point(db, goal, "长对话")
    _mastery(db, user, first, 0.4)
    _mastery(db, user, second, 0.7)
    _mistake(db, user, goal, first)
    _mistake(db, user, goal, first)
    _mistake(db, user, goal, second)
    db.add(
        Mistake(
            user_id=user.id,
            goal_id=goal.id,
            kp_id=None,
            question="无知识点错题",
            user_answer="答案",
            correct_answer="正确",
        )
    )
    db.commit()

    assert _mastery_map(db, user.id, goal.id) == {first.id: 0.4, second.id: 0.7}
    # kp_id 为空的错题不应计入任何知识点
    assert _mistake_counts(db, user.id, goal.id) == {first.id: 2, second.id: 1}


def test_helpers_return_empty_mapping_when_goal_has_no_points(db, db_user_goal):
    user, goal = db_user_goal

    assert _mastery_map(db, user.id, goal.id) == {}
    assert _mistake_counts(db, user.id, goal.id) == {}


# --------------------------------------------------------------------------
# prerequisites
# --------------------------------------------------------------------------


def test_prerequisites_follows_reverse_edges_with_depth_limit(db, db_user_goal):
    user, goal = db_user_goal
    first = _point(db, goal, "A")
    second = _point(db, goal, "B")
    third = _point(db, goal, "C")
    fourth = _point(db, goal, "D")
    for source, target in ((first, second), (second, third), (third, fourth)):
        db.add(
            KnowledgeDependency(
                goal_id=goal.id, from_kp_id=source.id, to_kp_id=target.id, source="tree"
            )
        )
    db.commit()

    assert prerequisites(db, goal.id, fourth.id, depth=2) == [third.id, second.id]
    # 深度 1 只能追溯一层
    assert prerequisites(db, goal.id, fourth.id, depth=1) == [third.id]


def test_prerequisites_handles_cycles_without_infinite_loop(db, db_user_goal):
    user, goal = db_user_goal
    first = _point(db, goal, "A")
    second = _point(db, goal, "B")
    db.add_all(
        [
            KnowledgeDependency(
                goal_id=goal.id, from_kp_id=first.id, to_kp_id=second.id, source="tree"
            ),
            KnowledgeDependency(
                goal_id=goal.id, from_kp_id=second.id, to_kp_id=first.id, source="tree"
            ),
        ]
    )
    db.commit()

    result = prerequisites(db, goal.id, first.id, depth=4)

    assert set(result) == {second.id, first.id}


# --------------------------------------------------------------------------
# refresh_candidates
# --------------------------------------------------------------------------


def test_refresh_candidates_triggers_on_repeated_mistakes(db, db_user_goal):
    user, goal = db_user_goal
    point = _point(db, goal, "短对话", weight=1.0)
    _mastery(db, user, point, 0.3)
    _mistake(db, user, goal, point)
    _mistake(db, user, goal, point)
    db.commit()

    gaps = refresh_candidates(db, user, goal)

    assert len(gaps) == 1
    assert gaps[0].kp_id == point.id
    assert gaps[0].status == "candidate"
    assert gaps[0].source == "rule"
    assert "掌握度 30%" in gaps[0].evidence
    assert "错题 2 道" in gaps[0].evidence


def test_refresh_candidates_triggers_on_high_weight_without_mistakes(db, db_user_goal):
    user, goal = db_user_goal
    point = _point(db, goal, "核心协议", weight=1.6)
    _mastery(db, user, point, 0.2)
    db.commit()

    gaps = refresh_candidates(db, user, goal)

    assert len(gaps) == 1
    assert gaps[0].kp_id == point.id
    assert "先修链" not in gaps[0].evidence


def test_refresh_candidates_triggers_on_weak_prerequisite(db, db_user_goal):
    user, goal = db_user_goal
    parent = _point(db, goal, "网络基础", weight=1.0)
    child = _point(db, goal, "子网划分", parent.id, weight=1.0)
    _mastery(db, user, parent, 0.1)
    _mastery(db, user, child, 0.4)
    db.commit()

    gaps = refresh_candidates(db, user, goal)

    # 父节点不是叶子，只应对叶子节点生成候选漏洞
    assert len(gaps) == 1
    assert gaps[0].kp_id == child.id
    assert "先修链中存在更薄弱环节" in gaps[0].evidence


def test_refresh_candidates_skips_existing_gap_and_healthy_point(db, db_user_goal):
    user, goal = db_user_goal
    healthy = _point(db, goal, "已掌握", weight=1.0)
    known = _point(db, goal, "已记录漏洞", weight=1.0)
    _mastery(db, user, healthy, 0.9)
    _mastery(db, user, known, 0.2)
    existing = KnowledgeGap(
        user_id=user.id,
        goal_id=goal.id,
        kp_id=known.id,
        status="candidate",
        evidence="人工标记",
        source="manual",
    )
    db.add(existing)
    db.commit()

    gaps = refresh_candidates(db, user, goal)

    assert len(gaps) == 1
    assert gaps[0].id == existing.id
    assert db.scalars(select(KnowledgeGap)).all().__len__() == 1


def test_refresh_candidates_falls_back_to_all_points_when_no_leaves(db, db_user_goal):
    user, goal = db_user_goal
    first = _point(db, goal, "A", weight=1.5)
    second = _point(db, goal, "B", weight=1.5)
    # 构造 A、B 互为父节点的异常数据，使叶子集合为空
    first.parent_id = second.id
    second.parent_id = first.id
    _mastery(db, user, first, 0.2)
    _mastery(db, user, second, 0.2)
    db.commit()

    gaps = refresh_candidates(db, user, goal)

    assert {gap.kp_id for gap in gaps} == {first.id, second.id}


def test_refresh_candidates_does_not_create_gap_for_healthy_point(db, db_user_goal):
    user, goal = db_user_goal
    point = _point(db, goal, "健康知识点", weight=1.0)
    _mastery(db, user, point, 0.9)
    db.commit()

    assert refresh_candidates(db, user, goal) == []
    assert db.scalars(select(KnowledgeGap)).all() == []


# --------------------------------------------------------------------------
# build_graph
# --------------------------------------------------------------------------


def test_build_graph_returns_nodes_edges_and_gap_sections(db, db_user_goal):
    user, goal = db_user_goal
    root = _point(db, goal, "听力", weight=1.5)
    candidate_point = _point(db, goal, "短对话", root.id, weight=1.0)
    verified_point = _point(db, goal, "长对话", root.id, weight=1.0)
    fixed_point = _point(db, goal, "听力篇章", root.id, weight=1.0)
    for point in (candidate_point, verified_point, fixed_point):
        _mastery(db, user, point, 0.9)
    _mistake(db, user, goal, candidate_point)
    db.add_all(
        [
            KnowledgeGap(
                user_id=user.id,
                goal_id=goal.id,
                kp_id=candidate_point.id,
                status="candidate",
                evidence="掌握度 20%，错题 2 道",
                source="rule",
            ),
            KnowledgeGap(
                user_id=user.id,
                goal_id=goal.id,
                kp_id=verified_point.id,
                status="verified",
                evidence="验证题答错 1 道",
                source="quiz",
            ),
            KnowledgeGap(
                user_id=user.id,
                goal_id=goal.id,
                kp_id=fixed_point.id,
                status="fixed",
                evidence="验证题全部通过",
                source="quiz",
            ),
        ]
    )
    db.commit()

    graph = build_graph(db, user, goal)

    assert len(graph["nodes"]) == 4
    assert len(graph["edges"]) == 5
    nodes = {node["kp_id"]: node for node in graph["nodes"]}
    assert nodes[candidate_point.id]["parent"] == "听力"
    assert nodes[candidate_point.id]["mastery"] == 0.9
    assert nodes[candidate_point.id]["mistake_count"] == 1
    assert nodes[candidate_point.id]["status"] == "candidate"
    assert nodes[verified_point.id]["status"] == "verified"

    assert [gap["kp_id"] for gap in graph["candidates"]] == [candidate_point.id]
    assert [gap["kp_id"] for gap in graph["verified"]] == [verified_point.id]
    assert graph["candidates"][0]["kp_name"] == "短对话"
    assert graph["candidates"][0]["evidence"] == "掌握度 20%，错题 2 道"
    assert graph["fixed_count"] == 1