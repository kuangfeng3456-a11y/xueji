"""多智能体学习评审团服务单元测试。

覆盖四角色规则意见、投票与总裁决、真实数据聚合、证据链写入，
以及 LLM 意见数量不足时的规则回退。全部 LLM 交互使用假客户端。
"""

import asyncio
import json
from datetime import date

import httpx
from sqlalchemy import select

from app import llm as llm_module
from app.models import (
    Evidence,
    KnowledgeGap,
    KnowledgePoint,
    LearningExperiment,
    Mastery,
    PanelReview,
    Task,
)
from app.services import panel as panel_module
from app.services.panel import ROLES, _fallback, run_review


def _readiness(score=72, coverage=0.8, load_ratio=0.6):
    return {"score": score, "coverage": coverage, "load_ratio": load_ratio}


def _risk(level="medium", reason="负荷偏高", suggestion="压缩任务", title="时间风险"):
    return {"title": title, "level": level, "reason": reason, "suggestion": suggestion}


def _enable_llm(monkeypatch, payload):
    monkeypatch.setattr(llm_module.llm, "base_url", "https://fake.local/v1")
    monkeypatch.setattr(llm_module.llm, "api_key", "test-key")

    async def fake_chat_json(system, user):
        return payload

    monkeypatch.setattr(llm_module.llm, "chat_json", fake_chat_json)
    assert llm_module.llm.available is True


# --------------------------------------------------------------------------
# 规则意见
# --------------------------------------------------------------------------


def test_fallback_produces_four_roles_and_optimistic_votes():
    result = _fallback(_readiness(), [], 0, 2, 60, 0)

    assert [item["role"] for item in result["opinions"]] == ROLES
    planner, diagnoser, risk_officer, coach = result["opinions"]
    assert planner["view"] == "今日有 2 个任务、约 60 分钟，负荷比 60%。"
    assert planner["concern"] == "节奏基本可控"
    assert planner["suggestion"] == "按当前顺序执行"
    assert "准备度 72%" in diagnoser["view"]
    assert diagnoser["concern"] == "知识覆盖尚可"
    assert diagnoser["suggestion"] == "继续用探针寻找隐藏盲区"
    assert risk_officer["view"] == "识别到 0 类风险。"
    assert risk_officer["concern"] == "暂无高风险"
    assert risk_officer["suggestion"] == "保持监测"
    assert coach["concern"] == "策略偏好数据不足"
    assert coach["suggestion"] == "做一次 3 天小实验"
    # 无风险时四角色投票必须与乐观裁决保持一致，全部投支持
    assert result["votes"] == ["支持", "支持", "支持", "支持"]
    assert len(set(result["votes"])) == 1
    assert "可适度增加迁移与挑战训练" in result["verdict"]


def test_fallback_flags_overload_and_low_coverage():
    result = _fallback(_readiness(coverage=0.3, load_ratio=1.4), [], 2, 5, 240, 3)

    planner, diagnoser, _, coach = result["opinions"]
    assert planner["view"] == "今日有 5 个任务、约 240 分钟，负荷比 140%。"
    assert planner["concern"] == "任务量与可用时间不匹配"
    assert planner["suggestion"] == "优先保留 1 个高优先级任务"
    assert diagnoser["concern"] == "掌握度覆盖不足"
    assert diagnoser["suggestion"] == "先修复高权重薄弱点并做验证题"
    assert coach["concern"] == "已有个人策略基线"
    assert coach["suggestion"] == "按收益最高的策略执行"
    assert result["verdict"].startswith("评审团建议：当前状态稳定")


def test_fallback_uses_highest_risk_and_votes_by_support():
    risks = [_risk("medium", "逾期 3 个", "颗粒度降载", "执行风险"), _risk("high")]

    result = _fallback(_readiness(), risks, 0, 1, 30, 0)

    risk_officer = result["opinions"][2]
    assert risk_officer["view"] == "识别到 2 类风险。"
    assert risk_officer["concern"] == "逾期 3 个"
    assert risk_officer["suggestion"] == "颗粒度降载"
    # support = 非 high 风险数(1) + 1 = 2，因此前两位投支持
    assert result["votes"] == ["支持", "支持", "保留", "保留"]
    assert result["verdict"] == "评审团建议：先处理最高风险，再执行今日关键任务；暂不扩大学习范围。"


def test_fallback_all_high_risks_keep_cautious_vote():
    risks = [_risk("high"), _risk("high")]

    result = _fallback(_readiness(), risks, 0, 0, 0, 0)

    assert result["votes"] == ["支持", "保留", "保留", "保留"]


def test_fallback_counts_support_capped_at_four():
    risks = [_risk("medium"), _risk("low"), _risk("low"), _risk("low"), _risk("low")]

    result = _fallback(_readiness(), risks, 0, 0, 0, 0)

    assert result["votes"] == ["支持", "支持", "支持", "支持"]


# --------------------------------------------------------------------------
# 评审流程
# --------------------------------------------------------------------------


def test_run_review_aggregates_facts_and_records_evidence(
    db, db_user_goal, monkeypatch
):
    user, goal = db_user_goal
    today = date(2026, 5, 20)
    point = KnowledgePoint(goal_id=goal.id, name="时态", weight=1.0)
    db.add(point)
    db.flush()
    db.add(Mastery(user_id=user.id, kp_id=point.id, value=0.2))
    db.add(
        Task(
            user_id=user.id,
            goal_id=goal.id,
            day=today,
            title="复习时态",
            type="review",
            duration_min=30,
            status="pending",
            reason="测试",
            priority=1.0,
            source="plan",
        )
    )
    db.add(
        Task(
            user_id=user.id,
            goal_id=goal.id,
            day=today,
            title="已完成任务",
            type="study",
            duration_min=50,
            status="done",
            reason="测试",
            priority=1.0,
            source="plan",
        )
    )
    db.add(
        KnowledgeGap(
            user_id=user.id,
            goal_id=goal.id,
            kp_id=point.id,
            status="verified",
            evidence="验证失败",
        )
    )
    db.add(
        LearningExperiment(
            user_id=user.id,
            goal_id=goal.id,
            strategy="practice",
            status="running",
            days=3,
            start_date=today,
            end_date=today,
        )
    )
    db.commit()

    monkeypatch.setattr(
        panel_module,
        "compute_readiness",
        lambda session, user_obj, goal_obj, today_arg=None: _readiness(66, 0.42, 1.4),
    )
    monkeypatch.setattr(
        panel_module, "build_risks", lambda session, user_obj, goal_obj, today_arg=None: []
    )

    result = asyncio.run(run_review(db, user, goal, "今天该不该加题", today=today))

    assert result["id"] is not None
    assert result["topic"] == "今天该不该加题"
    assert len(result["opinions"]) == 4
    assert len(result["votes"]) == 4
    assert result["engine"] == "rule"
    assert result["created_at"] is not None

    stored = db.get(PanelReview, result["id"])
    assert stored.topic == "今天该不该加题"
    assert [item["role"] for item in json.loads(stored.opinions)] == ROLES
    assert json.loads(stored.votes) == result["votes"]

    evidence = db.scalars(select(Evidence).where(Evidence.kind == "panel_review")).one()
    payload = json.loads(evidence.payload)
    assert payload == {
        "topic": "今天该不该加题",
        "preparedness": 66,
        "coverage": 0.42,
        "load_ratio": 1.4,
        "risks": [],
        "gaps": 1,
        "today_tasks": 1,
        "today_minutes": 30,
        "experiments": 1,
        # 证据链 2.0 的附加字段（snapshot_id / 校验 / 路由 / 兜底标记）
        "evidence_version": "2.0",
        "snapshot_id": payload["snapshot_id"],
        "validation": "passed",
        "route": "rule",
        "fallback": True,
    }
    assert payload["snapshot_id"].startswith("ev_")
    assert evidence.engine == "rule"
    assert evidence.output == result["verdict"]


def test_run_review_uses_llm_when_three_opinions_present(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    monkeypatch.setattr(
        panel_module,
        "compute_readiness",
        lambda session, user_obj, goal_obj, today_arg=None: _readiness(),
    )
    monkeypatch.setattr(
        panel_module, "build_risks", lambda session, user_obj, goal_obj, today_arg=None: []
    )
    _enable_llm(
        monkeypatch,
        {
            "opinions": [
                {"role": "计划官", "view": "负荷可控", "concern": "无", "suggestion": "执行"},
                {"role": "诊断官", "view": "覆盖良好", "concern": "无", "suggestion": "加练"},
                {"role": "风险官", "view": "暂无风险", "concern": "无", "suggestion": "监测"},
                {"role": "多余角色", "view": "应被忽略", "concern": "无", "suggestion": "忽略"},
                {"role": "第五个角色", "view": "应被忽略", "concern": "无", "suggestion": "忽略"},
            ],
            "verdict": "裁" * 500,
            "votes": ["支持", "支持", "保留"],
        },
    )

    result = asyncio.run(run_review(db, user, goal, "是否加练"))

    assert result["engine"] == "llm"
    assert len(result["opinions"]) == 4
    assert [item["role"] for item in result["opinions"]] == [
        "计划官",
        "诊断官",
        "风险官",
        "多余角色",
    ]
    assert len(result["verdict"]) == 400
    assert result["votes"] == ["支持", "支持", "保留"]
    evidence = db.scalars(select(Evidence).where(Evidence.kind == "panel_review")).one()
    assert evidence.engine == "llm"


def test_run_review_falls_back_when_llm_opinions_insufficient(
    db, db_user_goal, monkeypatch
):
    user, goal = db_user_goal
    monkeypatch.setattr(
        panel_module,
        "compute_readiness",
        lambda session, user_obj, goal_obj, today_arg=None: _readiness(),
    )
    monkeypatch.setattr(
        panel_module, "build_risks", lambda session, user_obj, goal_obj, today_arg=None: []
    )
    _enable_llm(
        monkeypatch,
        {
            "opinions": [
                {"role": "计划官", "view": "a", "concern": "b", "suggestion": "c"},
                {"role": "诊断官", "view": "a", "concern": "b", "suggestion": "c"},
            ],
            "verdict": "不足三条",
            "votes": ["支持"],
        },
    )

    result = asyncio.run(run_review(db, user, goal, "是否加练"))

    assert result["engine"] == "rule"
    assert len(result["opinions"]) == 4
    assert result["verdict"] != "不足三条"


def test_run_review_falls_back_when_llm_payload_invalid(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    monkeypatch.setattr(
        panel_module,
        "compute_readiness",
        lambda session, user_obj, goal_obj, today_arg=None: _readiness(),
    )
    monkeypatch.setattr(
        panel_module, "build_risks", lambda session, user_obj, goal_obj, today_arg=None: []
    )
    _enable_llm(monkeypatch, {"opinions": "oops"})

    result = asyncio.run(run_review(db, user, goal, "是否加练"))

    assert result["engine"] == "rule"
    # LLM 不可用时回退规则引擎，无风险场景四票一致支持
    assert result["votes"] == ["支持", "支持", "支持", "支持"]


def test_run_review_skips_non_dict_opinions(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    monkeypatch.setattr(
        panel_module,
        "compute_readiness",
        lambda session, user_obj, goal_obj, today_arg=None: _readiness(),
    )
    monkeypatch.setattr(
        panel_module, "build_risks", lambda session, user_obj, goal_obj, today_arg=None: []
    )
    _enable_llm(
        monkeypatch,
        {
            "opinions": [
                "not-a-dict",
                {"role": "计划官", "view": "a", "concern": "b", "suggestion": "c"},
                {"role": "诊断官", "view": "a", "concern": "b", "suggestion": "c"},
                {"role": "风险官", "view": "a", "concern": "b", "suggestion": "c"},
            ],
            "verdict": "非字典项被跳过",
            "votes": "not-a-list",
        },
    )

    result = asyncio.run(run_review(db, user, goal, "是否加练"))

    assert result["engine"] == "llm"
    assert len(result["opinions"]) == 3
    assert result["votes"] == []
    assert result["verdict"] == "非字典项被跳过"


def test_run_review_truncates_topic_and_role_fields(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    monkeypatch.setattr(
        panel_module,
        "compute_readiness",
        lambda session, user_obj, goal_obj, today_arg=None: _readiness(),
    )
    monkeypatch.setattr(
        panel_module, "build_risks", lambda session, user_obj, goal_obj, today_arg=None: []
    )
    _enable_llm(
        monkeypatch,
        {
            "opinions": [
                {"role": "角" * 30, "view": "v" * 500, "concern": "c" * 500, "suggestion": "s" * 500},
                {"role": "诊断官", "view": "a", "concern": "b", "suggestion": "c"},
                {"role": "风险官", "view": "a", "concern": "b", "suggestion": "c"},
            ],
            "verdict": "结论",
            "votes": ["支持"],
        },
    )

    result = asyncio.run(run_review(db, user, goal, "主" * 300))

    assert len(result["topic"]) == 120
    opinion = result["opinions"][0]
    assert len(opinion["role"]) == 12
    assert len(opinion["view"]) == 200
    assert len(opinion["concern"]) == 200
    assert len(opinion["suggestion"]) == 200

def test_run_review_without_risks_votes_unanimous_and_skips_network(
    db, db_user_goal, monkeypatch
):
    """无风险场景：四角色投票一致支持，且不发起任何真实 LLM 请求。"""
    user, goal = db_user_goal
    monkeypatch.setattr(
        panel_module,
        "compute_readiness",
        lambda session, user_obj, goal_obj, today_arg=None: _readiness(),
    )
    monkeypatch.setattr(
        panel_module, "build_risks", lambda session, user_obj, goal_obj, today_arg=None: []
    )

    async def forbidden_post(*args, **kwargs):
        raise AssertionError("禁用真实 DeepSeek：测试不得发起网络请求")

    monkeypatch.setattr(httpx.AsyncClient, "post", forbidden_post)

    result = asyncio.run(run_review(db, user, goal, "今天是否加题"))

    assert result["engine"] == "rule"
    assert result["votes"] == ["支持", "支持", "支持", "支持"]
    assert all(vote == "支持" for vote in result["votes"])
    assert "可适度增加迁移与挑战训练" in result["verdict"]

    stored = db.get(PanelReview, result["id"])
    assert json.loads(stored.votes) == ["支持", "支持", "支持", "支持"]
    assert stored.engine == "rule"

    evidence = db.scalars(select(Evidence).where(Evidence.kind == "panel_review")).one()
    assert evidence.engine == "rule"
    assert json.loads(evidence.payload)["risks"] == []
