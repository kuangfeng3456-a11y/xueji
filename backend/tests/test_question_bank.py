"""知识点题库与分科出题的测试。"""

import re

from app.services import question_bank

CJK = re.compile(r"[\u4e00-\u9fff]")

# 演示目标（CET-4 + 数学模块）下拉里的 36 个知识点 → 应命中的题库 key
EXPECTED_BANKS = {
    "听力": "listening",
    "短对话": "short_dialogue",
    "长对话": "long_dialogue",
    "听力篇章": "listening_passage",
    "阅读": "reading",
    "选词填空": "banked_cloze",
    "长篇阅读": "long_reading",
    "仔细阅读": "careful_reading",
    "写作": "writing",
    "议论文结构": "argument_structure",
    "常用句型": "sentence_patterns",
    "翻译": "translation",
    "中国文化": "chinese_culture",
    "句子结构": "sentence_structure",
    "词汇": "vocabulary",
    "高频词汇": "high_freq_words",
    "熟词僻义": "word_special_meaning",
    "语法": "grammar",
    "从句": "clauses",
    "非谓语动词": "non_finite_verbs",
    "高等数学": "advanced_math",
    "函数与极限": "limits",
    "导数与微分": "derivative",
    "不定积分": "indefinite_integral",
    "定积分": "definite_integral",
    "级数": "series",
    "线性代数": "linear_algebra",
    "矩阵": "matrix",
    "行列式": "determinant",
    "向量": "vector",
    "特征值与二次型": "eigen_quadratic",
    "概率论与数理统计": "probability",
    "随机变量": "random_variable",
    "常见分布": "common_distribution",
    "期望与方差": "expectation_variance",
    "大数定律与中心极限定理": "limit_theorems",
}


def test_bank_matches_math_and_english_points_separately():
    math_items = question_bank.pick("高等数学", 2)
    listening_items = question_bank.pick("听力", 2)
    assert len(math_items) >= 1 and len(listening_items) >= 1
    assert any(CJK.search(item["question"]) for item in math_items)
    assert all(not CJK.search(item["question"]) for item in listening_items)


def test_bank_covers_demo_knowledge_points():
    names = ["短对话", "仔细阅读", "高频词汇", "从句", "定积分", "矩阵", "期望与方差", "级数"]
    for name in names:
        assert question_bank.pick(name, 1), f"{name} 没有对应题库"


def test_every_point_maps_to_its_own_bank():
    """36 个知识点各自命中自己的题库，不再多知识点共用一道题。"""
    for name, key in EXPECTED_BANKS.items():
        info = question_bank.bank_of(name)
        assert info.get("key") == key, f"{name} 命中 {info.get('key')}，应为 {key}"
        assert info["size"] >= 4, f"{name} 题库只有 {info['size']} 题"


def test_law_of_large_numbers_is_probability_not_calculus():
    """修复关键词误配：大数定律不能被「极限」抢到高数题库。"""
    info = question_bank.bank_of("大数定律与中心极限定理")
    assert info["key"] == "limit_theorems"
    assert info["module"] == "概率论与数理统计"
    first = question_bank.pick("大数定律与中心极限定理", 1)[0]
    assert "切比雪夫" in first["question"]


def test_all_items_have_four_distinct_options_and_valid_answer():
    for bank in question_bank.banks():
        for item in bank["items"]:
            assert len(item["options"]) == 4, f"{bank['key']} 选项数不为 4"
            assert len(set(item["options"])) == 4, f"{bank['key']} 选项重复"
            assert 0 <= item["answer_index"] < 4, f"{bank['key']} 答案下标越界"


def test_no_question_shared_between_banks():
    """同一道题不能出现在两个题库里，避免「换了知识点还是同一题」。"""
    seen = {}
    for bank in question_bank.banks():
        for item in bank["items"]:
            question = item["question"]
            assert question not in seen, f"题目重复：{bank['key']} 与 {seen.get(question)}"
            seen[question] = bank["key"]


def test_pick_rotates_and_never_repeats_within_quiz():
    first = [item["question"] for item in question_bank.pick("矩阵", 2, offset=0)]
    second = [item["question"] for item in question_bank.pick("矩阵", 2, offset=2)]
    assert first and second
    assert not set(first) & set(second)


def test_pick_does_not_pad_when_limit_exceeds_bank_size():
    size = question_bank.bank_of("矩阵")["size"]
    # limit 大于库容量时只返回库里全部题目，不用重复题凑数
    items = question_bank.pick("矩阵", size + 10)
    assert len(items) == size
    assert len({item["question"] for item in items}) == len(items)


def test_generate_quiz_uses_bank_for_selected_point(db, db_user_goal):
    import asyncio

    from tests.conftest import add_points
    from app.services.quiz import generate_quiz

    user, goal = db_user_goal
    point = add_points(db, goal, names=("高等数学",))[0]
    db.commit()

    result = asyncio.run(generate_quiz(db, user, goal, point.id, 2))

    assert result["engine"] == "bank"
    assert result["questions"]
    assert all(item["kp_name"] == "高等数学" for item in result["questions"])
    assert all(CJK.search(item["question"]) for item in result["questions"])
    assert all(item["source"] == "内置题库" for item in result["questions"])
    # 对外接口只给干扰项归因，不泄漏正确答案
    for item in result["questions"]:
        assert "answer_index" not in item
        assert len(item["distractor_causes"]) == len(item["options"])


def test_generate_quiz_questions_come_from_the_point_bank(db, db_user_goal):
    """选「矩阵」出的题必须来自矩阵题库，不能混进行列式/向量的题。"""
    import asyncio

    from tests.conftest import add_points
    from app.services.quiz import generate_quiz

    user, goal = db_user_goal
    point = add_points(db, goal, names=("矩阵",))[0]
    db.commit()

    result = asyncio.run(generate_quiz(db, user, goal, point.id, 3))
    stems = {item["question"] for item in result["questions"]}
    matrix_stems = {item["question"] for item in question_bank.pick("矩阵", 4)}
    assert stems <= matrix_stems


def test_online_bank_cache_roundtrip():
    from app.services import quiz as quiz_module

    items = [{"question": "Q1", "options": ["A", "B", "C", "D"], "answer_index": 0}]
    quiz_module.store_bank(999, "波函数", items)
    assert quiz_module.cached_bank(999, "波函数", 2)[0]["question"] == "Q1"
    assert quiz_module.cached_bank(999, "未缓存", 2) == []


def test_external_question_bank_api_is_validated_and_cached(
    db_user_goal, monkeypatch
):
    import asyncio
    from types import SimpleNamespace

    from app.config import settings
    from app.services import quiz as quiz_module

    user, goal = db_user_goal
    point = SimpleNamespace(id=987, name="波函数")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "questions": [
                    {
                        "question": "波函数模平方的物理意义是：",
                        "options": ["概率密度", "能量本征值", "动量", "角动量"],
                        "answer_index": 0,
                        "explanation": "模平方表示概率密度。",
                        "kp_name": "波函数",
                    }
                ]
            }

    class FakeClient:
        def __init__(self, **kwargs):
            self.timeout = kwargs["timeout"]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, headers, json):
            assert url == "https://question-bank.example/questions"
            assert headers["Authorization"] == "Bearer test-key"
            assert json["knowledge_point"] == "波函数"
            assert json["question_type"] == "single_choice"
            return FakeResponse()

    monkeypatch.setattr(settings, "QUESTION_BANK_API_URL", "https://question-bank.example/questions")
    monkeypatch.setattr(settings, "QUESTION_BANK_API_KEY", "test-key")
    monkeypatch.setattr(quiz_module.httpx, "AsyncClient", FakeClient)

    items = asyncio.run(quiz_module.fetch_online_bank(goal, point, 1))

    assert len(items) == 1
    assert items[0]["source"] == question_bank.SOURCE_EXTERNAL
    assert quiz_module.cached_bank(goal.id, "波函数", 1)[0]["question"] == items[0]["question"]


def test_quiz_uses_external_bank_when_local_bank_is_too_small(
    db, db_user_goal, monkeypatch
):
    import asyncio

    from app.config import settings
    from tests.conftest import add_points
    from app.services import quiz as quiz_module

    user, goal = db_user_goal
    point = add_points(db, goal, names=("短对话",))[0]
    monkeypatch.setattr(settings, "QUESTION_BANK_API_URL", "https://question-bank.example/questions")
    external_items = [
        {
            "question": f"An external listening item {index}: What does the speaker imply?",
            "options": [
                "The office will close early.",
                "The report is already complete.",
                "A meeting has been canceled.",
                "The weather is changing.",
            ],
            "answer_index": 0,
            "explanation": "The speaker says the office will close early.",
            "kp_name": point.name,
            "kp_id": point.id,
            "source": question_bank.SOURCE_EXTERNAL,
            "option_reasons": ["", "常见错误", "常见错误", "常见错误"],
            "distractor_causes": [None, "concept", "method", "time"],
        }
        for index in range(2)
    ]

    async def fake_external_fetch(goal_row, selected_point, limit):
        assert selected_point.id == point.id
        assert limit == 6
        return external_items, {"status": "ok", "latency_ms": 1}

    monkeypatch.setattr(quiz_module, "fetch_external_bank", fake_external_fetch)
    result = asyncio.run(quiz_module.generate_quiz(db, user, goal, point.id, 6))

    assert result["engine"] == "bank+external"
    assert any(item["source"] == question_bank.SOURCE_EXTERNAL for item in result["questions"])
    assert all("answer_index" not in item for item in result["questions"])


def test_question_bank_catalog_endpoint_reports_coverage_without_answers(
    api, auth, goal, imported_points
):
    response = api(
        "GET",
        f"/api/goals/{goal['id']}/question-banks",
        token=auth["token"],
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["goal_id"] == goal["id"]
    assert body["summary"]["point_count"] > 0
    assert body["summary"]["local_count"] > 0
    assert body["external_api_configured"] is False
    assert all("answer_index" not in point and "options" not in point for point in body["points"])


def test_external_question_bank_probe_endpoint_sends_real_request(
    api, auth, goal, imported_points, monkeypatch
):
    from app.config import settings
    from app.api import study_tools

    monkeypatch.setattr(settings, "QUESTION_BANK_API_URL", "https://question-bank.example/questions")
    monkeypatch.setattr(settings, "QUESTION_BANK_API_KEY", "test-key")

    async def fake_external_fetch(goal_row, point, limit):
        assert goal_row.id == goal["id"]
        assert limit == 2
        return (
            [
                {
                    "question": "Why does the woman suggest delaying the trip?",
                    "options": [
                        "The weather may improve.",
                        "The train is fully booked.",
                        "She has lost her ticket.",
                        "The museum is closed.",
                    ],
                    "answer_index": 0,
                    "explanation": "She suggests waiting because the weather may improve.",
                    "source": "外部题库 API",
                }
            ],
            {
                "status": "ok",
                "latency_ms": 3,
                "detail": "接口连通，返回 1 道有效题目",
            },
        )

    monkeypatch.setattr(study_tools, "fetch_external_bank", fake_external_fetch)

    response = api(
        "POST",
        f"/api/goals/{goal['id']}/question-banks/test",
        token=auth["token"],
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["question_count"] == 1
    assert body["kp_name"]
    assert "test-key" not in response.text


def test_quiz_history_endpoint_persists_attempts_on_server(
    api, auth, goal, imported_points
):
    from app.cache import cache

    token = auth["token"]
    generated = api(
        "POST",
        f"/api/goals/{goal['id']}/quiz/generate",
        token=token,
        json={"count": 3},
    )
    assert generated.status_code == 200, generated.text
    quiz = generated.json()
    stored = cache.get_json(f"quiz:{auth['user']['id']}:{quiz['quiz_id']}")
    answers = [question["answer_index"] for question in stored["questions"]]
    submitted = api(
        "POST",
        f"/api/goals/{goal['id']}/quiz/submit",
        token=token,
        json={"quiz_id": quiz["quiz_id"], "answers": answers},
    )
    assert submitted.status_code == 200, submitted.text

    response = api(
        "GET",
        f"/api/goals/{goal['id']}/quiz/history",
        token=token,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["summary"]["correct"] == submitted.json()["correct"]
    assert body["summary"]["questions"] == submitted.json()["total"]
    assert body["items"][0]["score"] == 100
    assert body["items"][0]["engine"] == submitted.json()["engine"]

    deleted = api("DELETE", f"/api/goals/{goal['id']}", token=token)
    assert deleted.status_code == 204, deleted.text


def test_language_gate_blocks_cross_subject_match():
    """「概念辨析」含「辨析」二字，不带学科时会被英语近义词库命中；
    指定中文后必须落空，避免数学知识点出英文词汇题。"""
    fuzzy = question_bank.bank_of("概念辨析")
    assert fuzzy.get("language") == "en"

    assert question_bank.bank_of("概念辨析", "zh") == {}
    assert question_bank.pick("概念辨析", 2, language="zh") == []


def test_language_gate_keeps_correct_subject():
    """学科隔离不能把本来该命中的题库挡掉。"""
    assert question_bank.bank_of("听力", "en").get("key")
    assert question_bank.bank_of("定积分", "zh").get("module") == "高等数学"
