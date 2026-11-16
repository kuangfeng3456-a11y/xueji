"""学习内容时效雷达服务单元测试。

覆盖规则扫描的年份/大纲/篇幅判断、评分与等级、报告 upsert、
资料数量上限以及 LLM 分支的结果校验与回退。全部 LLM 交互使用假客户端。
"""

import asyncio
import json
from datetime import date

import pytest
from sqlalchemy import func, select

from app import llm as llm_module
from app.models import Evidence, FreshnessReport, Material
from app.services import freshness as freshness_module
from app.services.freshness import _rule_scan, scan_freshness

CURRENT_YEAR = date.today().year


def _material(db, user, goal, filename="资料.txt", content=""):
    item = Material(user_id=user.id, goal_id=goal.id, filename=filename, content=content)
    db.add(item)
    db.flush()
    return item


def _enable_llm(monkeypatch, payload):
    monkeypatch.setattr(llm_module.llm, "base_url", "https://fake.local/v1")
    monkeypatch.setattr(llm_module.llm, "api_key", "test-key")

    async def fake_chat_json(system, user):
        return payload

    monkeypatch.setattr(llm_module.llm, "chat_json", fake_chat_json)
    assert llm_module.llm.available is True


LONG_TEXT = "这是一段用于测试的资料内容。" * 30


# --------------------------------------------------------------------------
# 规则扫描
# --------------------------------------------------------------------------


def test_rule_scan_reports_missing_year_outline_and_thin_content():
    material = Material(filename="旧资料.txt", content="很短的内容")

    data = _rule_scan(material, CURRENT_YEAR)

    assert data["score"] == 55
    assert data["engine"] == "rule"
    assert len(data["issues"]) == 3
    assert "没有标注年份或大纲版本" in data["issues"][0]
    assert "未发现考纲对照" in data["issues"][1]
    assert "资料内容较少" in data["issues"][2]
    assert "核对最新考试大纲" in data["suggestion"]


def test_rule_scan_fresh_material_has_no_issue():
    material = Material(
        filename="新资料.txt",
        content="%d 年最新大纲：%s" % (CURRENT_YEAR, LONG_TEXT),
    )

    data = _rule_scan(material, CURRENT_YEAR)

    assert data["score"] == 90
    assert data["issues"] == []


def test_rule_scan_flags_outdated_year():
    material = Material(
        filename="过时资料.txt",
        content="%d 年考纲：%s" % (CURRENT_YEAR - 3, LONG_TEXT),
    )

    data = _rule_scan(material, CURRENT_YEAR)

    assert data["score"] == max(20, 90 - 3 * 10)
    assert len(data["issues"]) == 1
    assert str(CURRENT_YEAR - 3) in data["issues"][0]
    assert str(CURRENT_YEAR) in data["issues"][0]


def test_rule_scan_floor_score_is_twenty():
    material = Material(
        filename="远古资料.txt",
        content="2015 年考纲：%s" % LONG_TEXT,
    )

    data = _rule_scan(material, CURRENT_YEAR)

    assert data["score"] == 20


def test_rule_scan_last_year_is_treated_as_current():
    material = Material(
        filename="去年资料.txt",
        content="%d 年考纲：%s" % (CURRENT_YEAR - 1, LONG_TEXT),
    )

    data = _rule_scan(material, CURRENT_YEAR)

    assert data["score"] == 80
    assert data["issues"] == []


def test_rule_scan_uses_latest_year_in_text():
    material = Material(
        filename="多版本.txt",
        content="2019 年大纲，%d 年补充说明。%s" % (CURRENT_YEAR, LONG_TEXT),
    )

    data = _rule_scan(material, CURRENT_YEAR)

    assert data["score"] == 90
    assert data["issues"] == []


def test_rule_scan_ignores_non_target_years():
    material = Material(
        filename="年份干扰.txt",
        content="2010 年 2029 年 %s" % LONG_TEXT,
    )

    # 2010 不在可识别区间，2029 可识别；因此最新年份为 2029，高于当前年份时按满分计算
    data = _rule_scan(material, CURRENT_YEAR)

    assert data["score"] == 90
    assert "资料最新年份为 2029" not in data["issues"]


# --------------------------------------------------------------------------
# 扫描与报告
# --------------------------------------------------------------------------


def test_scan_freshness_without_materials_returns_zero_overall(db, db_user_goal):
    user, goal = db_user_goal

    result = asyncio.run(scan_freshness(db, user, goal))

    assert result["items"] == []
    assert result["overall"] == 0
    assert result["scanned_at"] is not None
    assert db.scalar(select(func.count()).select_from(FreshnessReport)) == 0


def test_scan_freshness_builds_reports_and_average(db, db_user_goal):
    user, goal = db_user_goal
    fresh = _material(
        db,
        user,
        goal,
        "新资料.txt",
        "%d 年最新大纲：%s" % (CURRENT_YEAR, LONG_TEXT),
    )
    stale = _material(db, user, goal, "旧资料.txt", "2018 年考纲：很短")
    db.commit()

    result = asyncio.run(scan_freshness(db, user, goal))

    assert [item["material_id"] for item in result["items"]] == [fresh.id, stale.id]
    assert [item["level"] for item in result["items"]] == ["fresh", "stale"]
    assert result["items"][0]["score"] == 90
    assert result["items"][1]["score"] == max(20, 90 - (CURRENT_YEAR - 2018) * 10)
    assert result["overall"] == round(
        (result["items"][0]["score"] + result["items"][1]["score"]) / 2
    )

    reports = db.scalars(select(FreshnessReport).order_by(FreshnessReport.material_id)).all()
    assert len(reports) == 2
    assert reports[0].engine == "rule"
    assert json.loads(reports[0].issues) == []


def test_scan_freshness_warning_level_for_mid_score(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    _material(db, user, goal, "中等资料.txt", "内容")
    db.commit()
    _enable_llm(monkeypatch, {"score": 65, "issues": ["缺少真题"], "suggestion": ""})

    result = asyncio.run(scan_freshness(db, user, goal))

    assert result["items"][0]["score"] == 65
    assert result["items"][0]["level"] == "warning"
    assert result["items"][0]["engine"] == "llm"


def test_scan_freshness_updates_existing_report(db, db_user_goal):
    user, goal = db_user_goal
    material = _material(db, user, goal, "资料.txt", "内容")
    db.commit()

    first = asyncio.run(scan_freshness(db, user, goal))
    material.content = "%d 年最新大纲：%s" % (CURRENT_YEAR, LONG_TEXT)
    db.commit()
    second = asyncio.run(scan_freshness(db, user, goal))

    assert db.scalar(select(func.count()).select_from(FreshnessReport)) == 1
    report = db.scalars(select(FreshnessReport)).one()
    assert report.material_id == material.id
    assert first["items"][0]["score"] == 55
    assert second["items"][0]["score"] == 90
    assert second["overall"] == 90


def test_scan_freshness_limits_to_five_materials(db, db_user_goal):
    user, goal = db_user_goal
    for index in range(7):
        _material(db, user, goal, "资料%s.txt" % index, "内容")
    db.commit()

    result = asyncio.run(scan_freshness(db, user, goal))

    assert len(result["items"]) == 5
    assert db.scalar(select(func.count()).select_from(FreshnessReport)) == 5


def test_scan_freshness_writes_evidence_per_material(db, db_user_goal):
    user, goal = db_user_goal
    _material(db, user, goal, "资料一.txt", "内容一")
    _material(db, user, goal, "资料二.txt", "内容二")
    db.commit()

    asyncio.run(scan_freshness(db, user, goal))

    rows = db.scalars(select(Evidence).where(Evidence.kind == "freshness_scan")).all()
    assert len(rows) == 2
    subjects = {row.subject for row in rows}
    assert subjects == {"资料一.txt", "资料二.txt"}
    payload = json.loads(rows[0].payload)
    assert set(payload) >= {"score", "issues"}
    assert rows[0].engine == "rule"


def test_scan_freshness_uses_llm_and_truncates_fields(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    _material(db, user, goal, "资料.txt", LONG_TEXT)
    db.commit()
    _enable_llm(
        monkeypatch,
        {
            "score": 140,
            "issues": ["问题一", "问题二", "问题三", "问题四"],
            "suggestion": "建议" * 200,
        },
    )

    result = asyncio.run(scan_freshness(db, user, goal))

    item = result["items"][0]
    assert item["score"] == 100
    assert item["issues"] == ["问题一", "问题二", "问题三"]
    assert len(item["suggestion"]) == 200
    assert item["engine"] == "llm"
    report = db.scalars(select(FreshnessReport)).one()
    assert report.engine == "llm"


def test_scan_freshness_llm_default_suggestion(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    _material(db, user, goal, "资料.txt", LONG_TEXT)
    db.commit()
    _enable_llm(monkeypatch, {"score": 72, "issues": "oops", "suggestion": ""})

    result = asyncio.run(scan_freshness(db, user, goal))

    item = result["items"][0]
    assert item["score"] == 72
    assert item["issues"] == []
    assert item["suggestion"] == "核对最新考试大纲与真题。"


def test_scan_freshness_falls_back_when_llm_score_invalid(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    _material(db, user, goal, "资料.txt", "%d 年大纲：%s" % (CURRENT_YEAR, LONG_TEXT))
    db.commit()
    _enable_llm(monkeypatch, {"score": "80", "issues": [], "suggestion": "无效"})

    result = asyncio.run(scan_freshness(db, user, goal))

    assert result["items"][0]["score"] == 90
    assert result["items"][0]["engine"] == "rule"


def test_scan_freshness_skips_llm_when_unavailable(db, db_user_goal, monkeypatch):
    user, goal = db_user_goal
    _material(db, user, goal, "资料.txt", "内容")
    db.commit()
    monkeypatch.setattr(llm_module.llm, "base_url", "")
    monkeypatch.setattr(llm_module.llm, "api_key", "")

    result = asyncio.run(scan_freshness(db, user, goal))

    assert llm_module.llm.available is False
    assert result["items"][0]["engine"] == "rule"


def test_scan_freshness_returns_datetime_scanned_at(db, db_user_goal):
    user, goal = db_user_goal
    _material(db, user, goal, "资料.txt", "内容")
    db.commit()

    result = asyncio.run(scan_freshness(db, user, goal))

    assert result["scanned_at"].year >= 2020