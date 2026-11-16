import asyncio
import time
from datetime import date, datetime, timedelta

import pytest

from app.agents import coach, diagnoser, skills
from app.cache import Cache, MemoryCache
from app.models import Goal, Task, User


def _user(nickname="小林"):
    return User(id=1, username="u1", password_hash="x", nickname=nickname, school="计算机学院")


def _goal(created_at=None):
    return Goal(
        id=1,
        user_id=1,
        exam_name="CET-4",
        exam_date=date.today() + timedelta(days=20),
        daily_minutes=90,
        created_at=created_at or datetime.utcnow(),
    )


def _task(day=None, status="pending", minutes=30):
    return Task(
        id=1,
        user_id=1,
        goal_id=1,
        day=day or date.today(),
        title="任务",
        type="study",
        duration_min=minutes,
        status=status,
        reason="",
        priority=1.0,
        source="plan",
    )


def test_coach_without_goal():
    message = coach._rule_message(_user(), None, [], 0, 0, 20)
    assert "先设定一个考试目标" in message


def test_coach_without_tasks():
    message = coach._rule_message(_user(), _goal(), [], 0, 0, 20)
    assert "今天还没有任务" in message


def test_coach_warns_overdue_tasks():
    goal = _goal(created_at=datetime.utcnow())
    overdue = _task(day=date.today() - timedelta(days=2))
    message = coach._rule_message(_user(), goal, [overdue], 0, 0, 20)
    assert "落后" in message


def test_coach_praises_finished_day():
    goal = _goal()
    done = _task(status="done")
    message = coach._rule_message(_user(), goal, [done], 5, 0, 12)
    assert "全部完成" in message
    assert "连续打卡 5 天" in message


def test_coach_tips_for_many_mistakes():
    message = coach._rule_message(_user(), _goal(), [_task(minutes=45)], 0, 4, 20)
    assert "错题" in message
    assert "45 分钟" in message


def test_coach_tips_near_exam():
    message = coach._rule_message(_user(), _goal(), [_task()], 0, 1, 5)
    assert "冲刺期" in message


def test_coach_default_encouragement():
    message = coach._rule_message(_user(), _goal(), [_task()], 0, 1, 20)
    assert "启动比完美更重要" in message


class _FakeLLM:
    def __init__(self, reply, available=True):
        self.reply = reply
        self.available = available

    async def chat(self, system, user, temperature=0.2, max_tokens=900):
        return self.reply

    async def chat_json(self, system, user):
        return self.reply


def test_coach_message_uses_llm(monkeypatch):
    monkeypatch.setattr(coach, "llm", _FakeLLM("  明天先做听力。  "))
    text = asyncio.run(coach.coach_message(_user(), _goal(), [_task()], 1, 0, 10))
    assert text == "明天先做听力。"


def test_coach_message_falls_back_when_llm_empty(monkeypatch):
    monkeypatch.setattr(coach, "llm", _FakeLLM(None))
    text = asyncio.run(coach.coach_message(_user(), _goal(), [_task()], 0, 0, 10))
    assert "启动比完美更重要" in text


def test_coach_message_without_goal_skips_llm(monkeypatch):
    monkeypatch.setattr(coach, "llm", _FakeLLM("不应被调用"))
    text = asyncio.run(coach.coach_message(_user(), None, [], 0, 0, 10))
    assert "先设定一个考试目标" in text


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("概念不清", "concept"),
        ("概念", "concept"),
        ("concept", "concept"),
        ("方法不会", "method"),
        ("method", "method"),
        ("粗心", "careless"),
        ("Careless", "careless"),
        ("时间不够", "time"),
        ("TIME", "time"),
        ("未知类别", None),
        ("", None),
    ],
)
def test_diagnoser_normalises_categories(raw, expected):
    assert diagnoser._normalize_category(raw) == expected


def test_diagnose_uses_rules_without_llm(monkeypatch):
    monkeypatch.setattr(diagnoser, "llm", _FakeLLM(None, available=False))
    category, label, suggestion, engine = asyncio.run(
        diagnoser.diagnose("请计算该极限", "不会做", "0")
    )
    assert category == "method"
    assert label == "方法不会"
    assert engine == "rule"
    assert suggestion


def test_diagnose_uses_valid_llm_output(monkeypatch):
    monkeypatch.setattr(
        diagnoser, "llm", _FakeLLM({"category": "粗心", "suggestion": "检查单位与符号"})
    )
    category, label, suggestion, engine = asyncio.run(
        diagnoser.diagnose("题目", "3", "2")
    )
    assert (category, label, engine) == ("careless", "粗心", "llm")
    assert suggestion == "检查单位与符号"


def test_diagnose_falls_back_when_llm_output_invalid(monkeypatch):
    monkeypatch.setattr(diagnoser, "llm", _FakeLLM({"category": "不存在的类别", "suggestion": "x"}))
    category, _, _, engine = asyncio.run(diagnoser.diagnose("请计算", "不会", "0"))
    assert engine == "rule"
    assert category == "method"

    monkeypatch.setattr(diagnoser, "llm", _FakeLLM({"category": "concept", "suggestion": "   "}))
    category, _, _, engine = asyncio.run(diagnoser.diagnose("下列哪个正确", "不会", "B"))
    assert engine == "rule"
    assert category == "concept"


def test_skills_registry():
    registered = skills.list_skills()
    assert len(registered) == 8
    assert {item["agent"] for item in registered} == {"Planner", "Diagnoser", "Coach", "Reporter"}
    builder = skills.get_skill("skill-package-builder")
    assert builder is not None and builder["rules"]
    assert skills.get_skill("plan-builder")["name"] == "plan-builder"
    assert skills.get_skill("missing") is None


def test_memory_cache_basic_operations():
    store = MemoryCache()
    assert store.get("missing") is None
    store.set("k", "v", ttl=60)
    assert store.get("k") == "v"
    store.delete("k")
    assert store.get("k") is None
    # ttl=0 表示不过期
    store.set("forever", "v", ttl=0)
    assert store.get("forever") == "v"


def test_memory_cache_expiry():
    store = MemoryCache()
    store.set("k", "v", ttl=1)
    store._data["k"] = (time.time() - 10, "v")
    assert store.get("k") is None
    assert "k" not in store._data


def test_memory_cache_incr_and_window_reset():
    store = MemoryCache()
    assert store.incr("rate", 60) == 1
    assert store.incr("rate", 60) == 2
    store._data["rate"] = (time.time() - 1, "30")
    # 窗口过期后重新从 1 开始，避免限流永久生效
    assert store.incr("rate", 60) == 1


class _FakeRedis:
    def __init__(self):
        self.data = {}
        self.expired = []

    def get(self, key):
        return self.data.get(key)

    def setex(self, key, ttl, value):
        self.data[key] = value

    def delete(self, key):
        self.data.pop(key, None)

    def incr(self, key):
        self.data[key] = int(self.data.get(key, 0)) + 1
        return self.data[key]

    def expire(self, key, ttl):
        self.expired.append(key)


class _BrokenRedis:
    def get(self, key):
        raise RuntimeError("down")

    def setex(self, key, ttl, value):
        raise RuntimeError("down")

    def delete(self, key):
        raise RuntimeError("down")

    def incr(self, key):
        raise RuntimeError("down")


def test_cache_fallback_backend():
    store = Cache()
    assert store.backend == "memory"
    assert store.get_json("missing") is None
    store.set_json("k", {"value": 1}, ttl=60)
    assert store.get_json("k") == {"value": 1}
    store.delete("k")
    assert store.get_json("k") is None
    assert store.incr("c", 60) == 1
    assert store.incr("c", 60) == 2


def test_cache_handles_broken_redis_gracefully():
    store = Cache()
    store._redis = _BrokenRedis()
    assert store.backend == "redis"
    # redis 全部异常时自动降级到内存缓存
    assert store.get_json("missing") is None
    store.set_json("k", {"value": 2}, ttl=60)
    assert store.get_json("k") == {"value": 2}
    store.delete("k")
    assert store.incr("c", 60) == 1


def test_cache_uses_redis_when_available():
    store = Cache()
    store._redis = _FakeRedis()
    store.set_json("k", {"value": 3}, ttl=30)
    assert store._redis.data["k"]
    assert store.get_json("k") == {"value": 3}
    assert store.incr("c", 60) == 1
    assert store._redis.expired == ["c"]
    assert store.incr("c", 60) == 2
    store.delete("k")
    assert store.get_json("k") is None


def test_cache_returns_none_on_invalid_json():
    store = Cache()
    store._fallback.set("bad", "not-json", ttl=60)
    assert store.get_json("bad") is None