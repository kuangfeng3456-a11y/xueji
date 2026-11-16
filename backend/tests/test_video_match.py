"""备考课表视频：核心词提取、标题相关性与过滤后的来源计数。"""

from app.services.exam_prep import (
    _filter_video_result,
    _kp_tokens,
    _video_relevance,
)


def test_kp_tokens_splits_compound_math_names():
    tokens = _kp_tokens("闭区间连续函数性质")
    assert "闭区间" in tokens
    assert "连续函数" in tokens


def test_kp_tokens_keeps_specific_derivative_term():
    tokens = _kp_tokens("高阶导数")
    assert "高阶导数" in tokens
    assert "导数" not in tokens


def test_kp_tokens_splits_on_generic_conjunction():
    tokens = _kp_tokens("隐函数与参数方程求导")
    assert "隐函数" in tokens
    assert "参数方程" in tokens


def test_video_relevance_accepts_natural_bilibili_title():
    token_map = {"闭区间连续函数性质": _kp_tokens("闭区间连续函数性质")}
    item = {
        "title": "【高等数学】闭区间上连续函数的性质 考研数学",
        "matched_keyword": "考研 闭区间连续函数性质",
    }
    assert _video_relevance(item, token_map) == "闭区间连续函数性质"


def test_video_relevance_rejects_unrelated_title():
    token_map = {"闭区间连续函数性质": _kp_tokens("闭区间连续函数性质")}
    item = {
        "title": "考研数学每日一笑 搞笑合集",
        "matched_keyword": "考研 闭区间连续函数性质",
    }
    assert _video_relevance(item, token_map) == ""


def test_filter_updates_sources_and_detail_when_unrelated():
    token_map = {"闭区间连续函数性质": _kp_tokens("闭区间连续函数性质")}
    result = {
        "items": [
            {
                "id": "1",
                "title": "今日搞笑合集",
                "source": "bilibili",
                "matched_keyword": "考研 闭区间连续函数性质",
            }
        ],
        "available": True,
        "detail": "",
        "sources": [
            {
                "name": "bilibili",
                "label": "B站",
                "configured": True,
                "available": True,
                "count": 6,
                "detail": "命中 6 条",
            }
        ],
    }
    _filter_video_result(result, token_map)
    assert result["items"] == []
    assert result["available"] is False
    assert "对不上" in result["detail"]
    assert result["sources"][0]["count"] == 0
    assert result["sources"][0]["available"] is False
    assert result["sources"][0]["retrieved"] == 6


def test_filter_keeps_matching_video_and_counts_it():
    token_map = {"闭区间连续函数性质": _kp_tokens("闭区间连续函数性质")}
    result = {
        "items": [
            {
                "id": "av1",
                "title": "闭区间上连续函数的性质",
                "source": "bilibili",
                "matched_keyword": "考研 连续函数",
            },
            {
                "id": "av2",
                "title": "搞笑合集",
                "source": "bilibili",
                "matched_keyword": "考研 连续函数",
            },
        ],
        "available": True,
        "detail": "",
        "sources": [
            {
                "name": "bilibili",
                "label": "B站",
                "configured": True,
                "available": True,
                "count": 2,
                "detail": "命中 2 条",
            }
        ],
    }
    _filter_video_result(result, token_map)
    assert [item["id"] for item in result["items"]] == ["av1"]
    assert result["available"] is True
    assert result["items"][0]["matched_kp"] == "闭区间连续函数性质"
    assert result["sources"][0]["count"] == 1
    assert result["sources"][0]["available"] is True

def test_kp_tokens_splits_english_topic_names():
    pronunciation = _kp_tokens("发音特征")
    assert "发音" in pronunciation
    mars = _kp_tokens("火星殖民文化")
    assert "火星" in mars
    assert "殖民" in mars
    method = _kp_tokens("学习方法")
    assert "学习方法" in method


def test_video_relevance_matches_pronunciation_synonym_title():
    token_map = {"发音特征": _kp_tokens("发音特征")}
    item = {"title": "快速掌握英式发音的特点", "matched_keyword": "英语 发音特征"}
    assert _video_relevance(item, token_map) == "发音特征"


def test_video_relevance_matches_mars_colony_title():
    token_map = {"火星殖民文化": _kp_tokens("火星殖民文化")}
    item = {"title": "人类如何殖民火星", "matched_keyword": "英语 火星殖民文化"}
    assert _video_relevance(item, token_map) == "火星殖民文化"


def test_video_relevance_matches_learning_method_synonym():
    token_map = {"学习方法": _kp_tokens("学习方法")}
    item = {"title": "四六级高效学习技巧分享", "matched_keyword": "英语 学习方法"}
    assert _video_relevance(item, token_map) == "学习方法"


def test_video_relevance_rejects_unrelated_english_joke_title():
    token_map = {"发音特征": _kp_tokens("发音特征")}
    item = {"title": "考研数学每日一笑 搞笑合集", "matched_keyword": "英语 发音特征"}
    assert _video_relevance(item, token_map) == ""


def test_video_relevance_does_not_match_culture_alone():
    token_map = {"火星殖民文化": _kp_tokens("火星殖民文化")}
    item = {"title": "中国传统文化英语演讲比赛", "matched_keyword": "英语 火星殖民文化"}
    assert _video_relevance(item, token_map) == ""
