"""词汇模块：内置 CET-4 词表 + 有道式单词卡学习记录。

词表按知识点归组：`高频词汇`、`熟词僻义`。前端以单词卡形式呈现，
用户对每个词标记「认识 / 模糊 / 不认识」，一轮结束后按正确率汇总更新掌握度。
"""

from datetime import date, datetime
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import KnowledgePoint, VocabReview
from .flashcards import review_card


def _w(word: str, phonetic: str, pos: str, meaning: str, example: str, example_cn: str) -> dict:
    return {
        "word": word,
        "phonetic": phonetic,
        "pos": pos,
        "meaning": meaning,
        "example": example,
        "example_cn": example_cn,
    }


HIGH_FREQUENCY = [
    _w("abandon", "/əˈbændən/", "v.", "放弃；抛弃", "He abandoned the plan after the first failure.",
       "第一次失败后他就放弃了这个计划。"),
    _w("ability", "/əˈbɪləti/", "n.", "能力；才能", "She has the ability to solve complex problems.",
       "她有解决复杂问题的能力。"),
    _w("absorb", "/əbˈzɔːb/", "v.", "吸收；理解", "Plants absorb water through their roots.",
       "植物通过根部吸收水分。"),
    _w("academic", "/ˌækəˈdemɪk/", "adj.", "学术的；学院的", "Academic writing requires a clear structure.",
       "学术写作需要清晰的结构。"),
    _w("access", "/ˈækses/", "n./v.", "使用权；获取", "Students have free access to the library.",
       "学生可以免费使用图书馆。"),
    _w("accompany", "/əˈkʌmpəni/", "v.", "陪伴；伴随", "She accompanied her friend to the hospital.",
       "她陪朋友去了医院。"),
    _w("accurate", "/ˈækjərət/", "adj.", "准确的", "The report gives an accurate description of the event.",
       "这份报告对事件描述准确。"),
    _w("achieve", "/əˈtʃiːv/", "v.", "实现；达到", "He achieved his goal in three months.",
       "他三个月内实现了目标。"),
    _w("acquire", "/əˈkwaɪə(r)/", "v.", "获得；习得", "Children acquire language remarkably quickly.",
       "孩子习得语言快得惊人。"),
    _w("adapt", "/əˈdæpt/", "v.", "适应；改编", "We must adapt to the new environment.",
       "我们必须适应新环境。"),
    _w("adequate", "/ˈædɪkwət/", "adj.", "足够的；适当的", "Make sure you get adequate sleep before the exam.",
       "考试前要确保睡眠充足。"),
    _w("adjust", "/əˈdʒʌst/", "v.", "调整；适应", "Please adjust the volume before you start.",
       "开始前请调整音量。"),
    _w("advantage", "/ədˈvɑːntɪdʒ/", "n.", "优势；有利条件", "Smaller classes have clear advantages.",
       "小班授课有明显优势。"),
    _w("affect", "/əˈfekt/", "v.", "影响", "Noise can affect your concentration.",
       "噪音会影响你的注意力。"),
    _w("alternative", "/ɔːlˈtɜːnətɪv/", "n./adj.", "替代方案；备选的", "We need an alternative plan in case it rains.",
       "我们得准备一个备选方案以防下雨。"),
    _w("analyze", "/ˈænəlaɪz/", "v.", "分析", "Analyze the data before drawing conclusions.",
       "下结论之前先分析数据。"),
    _w("anxious", "/ˈæŋkʃəs/", "adj.", "焦虑的；渴望的", "She felt anxious before the exam.",
       "考试前她感到焦虑。"),
    _w("apparent", "/əˈpærənt/", "adj.", "显然的；表面的", "It was apparent that he was very tired.",
       "很明显他非常累。"),
    _w("approach", "/əˈprəʊtʃ/", "n./v.", "方法；接近", "This approach works better for beginners.",
       "这个方法对初学者更有效。"),
    _w("appropriate", "/əˈprəʊpriət/", "adj.", "合适的", "Choose appropriate examples for each point.",
       "为每个论点选择合适的例子。"),
    _w("assess", "/əˈses/", "v.", "评估", "Teachers assess students' progress every month.",
       "老师每月评估学生的进步。"),
    _w("assume", "/əˈsjuːm/", "v.", "假设；认为", "Don't assume that everyone agrees with you.",
       "不要假设所有人都同意你。"),
    _w("attitude", "/ˈætɪtjuːd/", "n.", "态度", "A positive attitude makes learning easier.",
       "积极的态度让学习更轻松。"),
    _w("available", "/əˈveɪləbl/", "adj.", "可获得的；有空的", "The full text is available online.",
       "全文可以在线获取。"),
    _w("benefit", "/ˈbenɪfɪt/", "n./v.", "益处；有益于", "Regular reading benefits your memory.",
       "规律阅读对记忆有益。"),
    _w("capacity", "/kəˈpæsəti/", "n.", "容量；能力", "The hall has a capacity of five hundred.",
       "这个大厅可容纳五百人。"),
    _w("challenge", "/ˈtʃælɪndʒ/", "n./v.", "挑战；质疑", "Learning a language is a long-term challenge.",
       "学一门语言是长期的挑战。"),
    _w("circumstance", "/ˈsɜːkəmstəns/", "n.", "情况；环境", "Under no circumstances should you give up.",
       "任何情况下你都不该放弃。"),
    _w("commit", "/kəˈmɪt/", "v.", "承诺；投入", "She committed to studying thirty minutes a day.",
       "她承诺每天学习三十分钟。"),
    _w("compensate", "/ˈkɒmpenseɪt/", "v.", "补偿；弥补", "Hard work can compensate for a lack of talent.",
       "努力可以弥补天赋的不足。"),
    _w("concentrate", "/ˈkɒnsntreɪt/", "v.", "集中；专注", "I can't concentrate with the TV on.",
       "开着电视我无法集中注意力。"),
    _w("conclude", "/kənˈkluːd/", "v.", "得出结论；结束", "The study concluded that sleep matters most.",
       "这项研究得出结论：睡眠最重要。"),
    _w("confidence", "/ˈkɒnfɪdəns/", "n.", "信心；信任", "Practice is what builds confidence.",
       "练习才能建立信心。"),
    _w("consequence", "/ˈkɒnsɪkwəns/", "n.", "后果；结果", "Every choice has its consequences.",
       "每个选择都有其后果。"),
    _w("consider", "/kənˈsɪdə(r)/", "v.", "考虑；认为", "Consider the cost before you decide.",
       "决定之前先考虑成本。"),
    _w("consistent", "/kənˈsɪstənt/", "adj.", "一致的；持续的", "Keep a consistent routine during the exam week.",
       "考试周要保持稳定的作息。"),
    _w("contribute", "/kənˈtrɪbjuːt/", "v.", "贡献；促成", "Everyone can contribute ideas to the plan.",
       "每个人都能为计划贡献想法。"),
    _w("convince", "/kənˈvɪns/", "v.", "说服；使确信", "He convinced me to try again.",
       "他说服我再试一次。"),
    _w("decline", "/dɪˈklaɪn/", "v./n.", "下降；婉拒", "Sales declined sharply last month.",
       "上个月销量急剧下降。"),
    _w("demonstrate", "/ˈdemənstreɪt/", "v.", "证明；演示", "The results demonstrate the effect of practice.",
       "结果证明了练习的效果。"),
]

RARE_MEANING = [
    _w("address", "/əˈdres/", "v.", "处理；向…讲话（非常义：地址）", "We must address this issue first.",
       "我们必须先处理这个问题。"),
    _w("appreciate", "/əˈpriːʃieɪt/", "v.", "意识到；感激", "I appreciate how difficult this is.",
       "我意识到这有多难。"),
    _w("article", "/ˈɑːtɪkl/", "n.", "条文（非常义：文章）", "Please read Article 3 of the contract.",
       "请阅读合同第三条。"),
    _w("balance", "/ˈbæləns/", "n.", "余额（非常义：平衡）", "Check your account balance online.",
       "在线查看你的账户余额。"),
    _w("bear", "/beə(r)/", "v.", "承担；忍受", "Who will bear the cost of the repair?",
       "谁来承担维修费用？"),
    _w("book", "/bʊk/", "v.", "预订（非常义：书）", "Book a seat two weeks in advance.",
       "提前两周订座。"),
    _w("capital", "/ˈkæpɪtl/", "n.", "资本（非常义：首都）", "The team raised enough capital to start.",
       "团队筹到了足够的启动资本。"),
    _w("charge", "/tʃɑːdʒ/", "v.", "收费；指控", "They charge ten yuan for delivery.",
       "配送收费十元。"),
    _w("company", "/ˈkʌmpəni/", "n.", "陪伴（非常义：公司）", "I really enjoy your company.",
       "我很喜欢你的陪伴。"),
    _w("content", "/kənˈtent/", "adj.", "满足的（非常义：内容）", "She is content with her progress.",
       "她对自己的进步感到满足。"),
    _w("couch", "/kaʊtʃ/", "v.", "措辞；表达", "The letter is couched in polite terms.",
       "这封信措辞礼貌。"),
    _w("exercise", "/ˈeksəsaɪz/", "n.", "行使（非常义：锻炼）", "The exercise of power needs clear limits.",
       "行使权力需要明确边界。"),
    _w("figure", "/ˈfɪɡə(r)/", "n.", "数字（非常义：身材）", "These figures are not final yet.",
       "这些数字还不是最终结果。"),
    _w("issue", "/ˈɪʃuː/", "n.", "议题（非常义：发行）", "This is a key issue for the whole class.",
       "这是全班的关键议题。"),
    _w("labor", "/ˈleɪbə(r)/", "n.", "劳动（不可数）", "Labor costs are rising every year.",
       "劳动力成本每年都在上涨。"),
    _w("matter", "/ˈmætə(r)/", "v.", "要紧（非常义：物质）", "Details matter more than you think.",
       "细节比你想的更重要。"),
    _w("mean", "/miːn/", "adj.", "吝啬的（非常义：意味着）", "Don't be mean with your praise.",
       "别在表扬上太吝啬。"),
    _w("observe", "/əbˈzɜːv/", "v.", "遵守；评论", "All members must observe the rules.",
       "所有成员都必须遵守规则。"),
    _w("practice", "/ˈpræktɪs/", "n.", "惯例；执业", "It is common practice to reply within a day.",
       "一天内回复是这里的惯例。"),
    _w("subject", "/ˈsʌbdʒɪkt/", "adj.", "易受…影响的", "Prices are subject to change without notice.",
       "价格可能随时变动，不另行通知。"),
    _w("tip", "/tɪp/", "n.", "提示；小费", "Here is a useful tip for the listening part.",
       "这里有一个听力部分的实用提示。"),
    _w("weather", "/ˈweðə(r)/", "v.", "度过（难关）", "The company weathered the crisis last year.",
       "公司去年度过了危机。"),
]

DECKS = [
    {"key": "high-frequency", "name": "高频词汇", "keywords": ("高频", "词"), "words": HIGH_FREQUENCY},
    {"key": "rare-meaning", "name": "熟词僻义", "keywords": ("熟词",), "words": RARE_MEANING},
]


def _deck_by_name(name: str) -> Optional[dict]:
    text = (name or "").strip()
    if not text:
        return None
    for deck in DECKS:
        if deck["key"] == "rare-meaning" and any(k in text for k in deck["keywords"]):
            return deck
    for deck in DECKS:
        if any(k in text for k in deck["keywords"]):
            return deck
    return None


def _point_decks(db: Session, point: KnowledgePoint) -> List[dict]:
    """单个知识点：优先按名字命中的词表；父模块则合并其下子知识点命中的词表。"""
    decks: List[dict] = []
    hit = _deck_by_name(point.name)
    if hit:
        decks.append(hit)
    children = db.scalars(
        select(KnowledgePoint).where(KnowledgePoint.parent_id == point.id)
    ).all()
    for child in children:
        child_deck = _deck_by_name(child.name)
        if child_deck and child_deck not in decks:
            decks.append(child_deck)
    return decks


def _review_state(db: Session, user_id: int, goal_id: int, kp_id: int) -> Dict[str, str]:
    rows = db.scalars(
        select(VocabReview)
        .where(
            VocabReview.user_id == user_id,
            VocabReview.goal_id == goal_id,
            VocabReview.kp_id == kp_id,
        )
        .order_by(VocabReview.id.asc())
    ).all()
    return {row.word: row.action for row in rows}


def build_session(
    db: Session, user_id: int, goal_id: int, kp_id: int, limit: int = 20, offset: int = 0
) -> Dict:
    point = db.get(KnowledgePoint, kp_id)
    if point is None or point.goal_id != goal_id:
        raise ValueError("知识点不存在")
    decks = _point_decks(db, point)
    words: List[dict] = []
    for deck in decks:
        words.extend(deck["words"])
    if not words:
        raise ValueError("该知识点还没有配套词表")

    state = _review_state(db, user_id, goal_id, point.id)
    known = sum(1 for action in state.values() if action == "known")
    fresh = [item for item in words if item["word"] not in state]
    page = (fresh + [item for item in words if item["word"] in state])[: max(1, limit)]
    payload = []
    for item in page:
        row = dict(item)
        row["state"] = state.get(item["word"])
        payload.append(row)

    return {
        "kp_id": point.id,
        "title": point.name,
        "decks": [deck["name"] for deck in decks],
        "total": len(words),
        "learned": len(state),
        "known": known,
        "offset": offset,
        "words": payload,
    }


def record_review(
    db: Session, user_id: int, goal_id: int, kp_id: int, word: str, action: str
) -> Dict:
    point = db.get(KnowledgePoint, kp_id)
    if point is None or point.goal_id != goal_id:
        raise ValueError("知识点不存在")
    if action not in ("known", "fuzzy", "unknown"):
        raise ValueError("无法识别的学习结果")
    db.add(
        VocabReview(
            user_id=user_id,
            goal_id=goal_id,
            kp_id=kp_id,
            word=word[:64],
            action=action,
            created_at=datetime.utcnow(),
        )
    )
    db.commit()
    state = _review_state(db, user_id, goal_id, kp_id)
    return {"word": word, "learned": len(state), "known": sum(1 for v in state.values() if v == "known")}


def finish_session(
    db: Session, user_id: int, goal_id: int, kp_id: int, known: int, fuzzy: int, unknown: int
) -> Dict:
    """一轮结束后按正确率汇总：认识记正确，模糊与不认识记未掌握，更新掌握度与复习排期。"""
    total = max(1, known + fuzzy + unknown)
    rate = known / total
    remembered = rate >= 0.6
    result = review_card(db, user_id, goal_id, kp_id, remembered)
    return {
        "kp_id": kp_id,
        "rate": round(rate, 3),
        "mastery": result["mastery"],
        "next_review_at": result["next_review_at"],
        "today": date.today(),
    }
