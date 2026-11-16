"""自建题库（tikuAdapter）适配层测试。

要点：
- 题库记录能正确转成学迹题目结构（答案文本 → 选项下标，判分才对得上）
- 答案对不上任何选项、选项不足的脏数据要被丢掉，不能进入练习
- 按知识点取题带轮换；未配置题库时静默返回空，不影响出题链路
"""

import asyncio

from app.services import tiku_bank


def _run(coro):
    return asyncio.run(coro)


def _raw(question="∫₀¹ 2x dx 的值为：", options=("1", "0", "2", "1/2"), answer=("1",)):
    import json

    return {
        "id": 7,
        "question": question,
        "type": 0,
        "options": json.dumps(list(options), ensure_ascii=False),
        "answer": json.dumps(list(answer), ensure_ascii=False),
        "course_name": "定积分",
        "extra": "∫2x dx = x²，代入 0 到 1 得 1。",
    }


class FakeClient:
    def __init__(self, rows_by_course=None):
        self.rows_by_course = rows_by_course or {}
        self.calls = []

    async def list_by_course(self, course, limit=10, page=0):
        self.calls.append((course, limit, page))
        return self.rows_by_course.get(course, [])

    async def count_by_course(self, course):
        return len(self.rows_by_course.get(course, []))

    async def courses(self):
        return list(self.rows_by_course.keys())


def test_to_item_maps_answer_text_to_option_index():
    item = tiku_bank.to_item(_raw(), "定积分")
    assert item is not None
    assert item["options"] == ["1", "0", "2", "1/2"]
    assert item["answer_index"] == 0
    assert item["source"] == tiku_bank.SOURCE_TIKU
    assert item["kp_name"] == "定积分"
    assert item["explanation"].startswith("∫2x dx")


def test_to_item_picks_non_first_option():
    """答案在第二项时要映射到 1，不能恒为 0（否则全选 A 就满分）。"""
    item = tiku_bank.to_item(_raw(answer=("2",)), "定积分")
    assert item["answer_index"] == 2


def test_to_item_matches_answer_by_containment():
    """题库答案带前缀（如 "B 1"）时靠包含关系兜底匹配。"""
    item = tiku_bank.to_item(_raw(answer=("1",), options=("11", "1", "12", "13")), "定积分")
    assert item["answer_index"] == 1


def test_to_item_rejects_unusable_rows():
    import json

    # 答案对不上任何选项
    bad_answer = _raw(answer=("999",))
    assert tiku_bank.to_item(bad_answer, "定积分") is None
    # 选项只剩一个
    one_option = _raw()
    one_option["options"] = json.dumps(["1"])
    assert tiku_bank.to_item(one_option, "定积分") is None
    # 没有答案
    empty_answer = _raw(answer=())
    assert tiku_bank.to_item(empty_answer, "定积分") is None


def test_pick_returns_items_and_rotates(monkeypatch):
    rows = [
        _raw(question="题 1", answer=("1",)),
        _raw(question="题 2", answer=("0",)),
        _raw(question="题 3", answer=("2",)),
    ]
    fake = FakeClient({"定积分": rows})
    monkeypatch.setattr(tiku_bank, "get_client", lambda: fake)
    monkeypatch.setattr(tiku_bank.settings, "TIKU_ADAPTER_URL", "http://127.0.0.1:8060", raising=False)

    first = _run(tiku_bank.pick("定积分", 2, offset=0))
    second = _run(tiku_bank.pick("定积分", 2, offset=1))
    assert [item["question"] for item in first] == ["题 1", "题 2"]
    assert [item["question"] for item in second] == ["题 2", "题 3"]
    assert all(item["course_name"] == "定积分" for item in first)


def test_pick_returns_empty_when_not_configured(monkeypatch):
    monkeypatch.setattr(tiku_bank.settings, "TIKU_ADAPTER_URL", "", raising=False)
    assert _run(tiku_bank.pick("定积分", 2)) == []


def test_coverage_counts_per_point(monkeypatch):
    fake = FakeClient({"定积分": [_raw()], "线性代数": []})
    monkeypatch.setattr(tiku_bank, "get_client", lambda: fake)
    monkeypatch.setattr(tiku_bank.settings, "TIKU_ADAPTER_URL", "http://127.0.0.1:8060", raising=False)

    report = _run(tiku_bank.coverage(["定积分", "线性代数", "级数"]))
    assert report["status"] == "ok"
    assert report["points"]["定积分"]["count"] == 1
    assert report["points"]["定积分"]["covered"] is True
    assert report["points"]["线性代数"]["covered"] is False
    assert report["covered"] == 1


def test_bank_questions_have_enough_items_for_every_math_point():
    """程序化题源要保证每个数学考点都有 8 题以上，否则连着做两次就重复。"""
    from app.services import question_bank

    for name in (
        "定积分",
        "不定积分",
        "导数与微分",
        "函数与极限",
        "线性代数",
        "行列式",
        "矩阵",
        "向量",
        "特征值与二次型",
        "概率论与数理统计",
        "随机变量",
        "常见分布",
        "期望与方差",
        "大数定律与中心极限定理",
        "级数",
        "高等数学",
    ):
        info = question_bank.bank_of(name, "zh")
        assert info, f"{name} 没有对应题库"
        assert info["size"] >= 8, f"{name} 只有 {info['size']} 题"
