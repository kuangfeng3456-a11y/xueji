"""
英语扩充题库：新增知识点库（CET-4 新增 10 库）。

与 qbank_english.py 合并后共 30 库 300+ 题。
包含词汇、语法、完形填空、翻译等高频题型。
"""

from typing import Dict, List

ENGLISH_BANKS_EXTENDED: List[Dict] = [
    {
        "key": "vocabulary_common",
        "module": "词汇",
        "points": ("常用词汇", "基础词汇"),
        "match": ("词汇", "单词", "常用词"),
        "language": "en",
        "items": [
            {
                "question": "The company's ______ increased dramatically after the new product launch.",
                "options": ["revenue", "revenge", "reverse", "reward"],
                "answer_index": 0,
                "explanation": "revenue 收入；revenge 报复；reverse 反转；reward 奖励。题意为「公司营收增长」。",
            },
            {
                "question": "Despite his ______ health, he still came to the meeting.",
                "options": ["poor", "pious", "poised", "poisonous"],
                "answer_index": 0,
                "explanation": "poor 差的、贫困的；pious 虔诚的；poised 镇定的；poisonous 有毒的。",
            },
            {
                "question": "She ______ her goals and never gave up.",
                "options": ["pursued", "prospered", "promoted", "proposed"],
                "answer_index": 0,
                "explanation": "pursued 追求；prospered 繁荣；promoted 推广；proposed 提议。",
            },
            {
                "question": "The meeting was ______ to next Monday due to the manager's absence.",
                "options": ["postponed", "promoted", "proposed", "proved"],
                "answer_index": 0,
                "explanation": "postponed 推迟；promoted 提升；proposed 提议；proved 证明。",
            },
            {
                "question": "He made a ______ effort to improve his English.",
                "options": ["conscious", "consistent", "consequent", "convenient"],
                "answer_index": 1,
                "explanation": "consistent 一致的、坚持的；conscious 有意识的；consequent 随后的；convenient 方便的。",
            },
            {
                "question": "The weather forecast ______ heavy rain tomorrow.",
                "options": ["predicts", "prevents", "preserves", "prepares"],
                "answer_index": 0,
                "explanation": "predicts 预测；prevents 防止；preserves 保护；prepares 准备。",
            },
            {
                "question": "Her ______ approach to problem-solving impressed everyone.",
                "options": ["practical", "partial", "particular", "principal"],
                "answer_index": 0,
                "explanation": "practical 实用的；partial 偏见的；particular 特定的；principal 主要的。",
            },
            {
                "question": "The new policy will ______ the company's efficiency.",
                "options": ["enhance", "enlarge", "enclose", "enforce"],
                "answer_index": 0,
                "explanation": "enhance 提升；enlarge 扩大；enclose 围闭；enforce 执行。",
            },
        ],
    },
    {
        "key": "synonyms_antonyms",
        "module": "词汇",
        "points": ("同义词辨析", "近义词", "词义辨析"),
        "match": ("同义词", "近义词", "辨析"),
        "language": "en",
        "items": [
            {
                "question": "'Fortunate' is closest in meaning to:",
                "options": ["lucky", "famous", "fearless", "formal"],
                "answer_index": 0,
                "explanation": "fortunate = lucky 幸运的。",
            },
            {
                "question": "Which word is the opposite of 'abundant'?",
                "options": ["scarce", "strange", "safe", "secure"],
                "answer_index": 0,
                "explanation": "scarce 稀缺的，是 abundant（充足的）的反义词。",
            },
            {
                "question": "'Facilitate' means to:",
                "options": ["make easy", "face difficulty", "fix completely", "fire someone"],
                "answer_index": 0,
                "explanation": "facilitate 帮助、便利、促进。",
            },
            {
                "question": "A 'candid' response is a ______ response.",
                "options": ["honest", "careful", "formal", "fast"],
                "answer_index": 0,
                "explanation": "candid 坦率的、诚实的。",
            },
            {
                "question": "'Diligent' and 'lazy' are:",
                "options": ["antonyms", "synonyms", "homophones", "homonyms"],
                "answer_index": 0,
                "explanation": "antonyms 反义词。",
            },
            {
                "question": "To 'diminish' means to:",
                "options": ["decrease", "develop", "define", "deliver"],
                "answer_index": 0,
                "explanation": "diminish 减少。",
            },
            {
                "question": "'Meager' is similar to:",
                "options": ["scanty", "mature", "severe", "sincere"],
                "answer_index": 0,
                "explanation": "meager 稀少的、不足的，scanty 同义。",
            },
            {
                "question": "A 'concise' statement is a ______ statement.",
                "options": ["brief", "bright", "broad", "broke"],
                "answer_index": 0,
                "explanation": "concise 简洁的、简明的。",
            },
        ],
    },
    {
        "key": "phrasal_verbs",
        "module": "语法",
        "points": ("短语动词", "动词短语"),
        "match": ("短语", "短语动词", "动词搭配"),
        "language": "en",
        "items": [
            {
                "question": "'Give up' means to:",
                "options": ["stop trying", "surrender", "lose", "all of the above"],
                "answer_index": 3,
                "explanation": "give up 放弃、投降。",
            },
            {
                "question": "'Look forward to' expresses:",
                "options": ["anticipation", "reluctance", "confusion", "criticism"],
                "answer_index": 0,
                "explanation": "look forward to 期待、盼望。",
            },
            {
                "question": "'Put off' means to:",
                "options": ["postpone", "turn off", "dislike", "disturb"],
                "answer_index": 0,
                "explanation": "put off 推迟。",
            },
            {
                "question": "'Get along with' someone means you:",
                "options": ["have a good relationship", "travel together", "understand well", "share interests"],
                "answer_index": 0,
                "explanation": "get along with 与……相处融洽。",
            },
            {
                "question": "To 'set up' a business means to:",
                "options": ["start it", "organize it", "establish it", "all of the above"],
                "answer_index": 3,
                "explanation": "set up 建立、创办。",
            },
            {
                "question": "'Carry out' means to:",
                "options": ["execute", "transport", "deliver", "complete"],
                "answer_index": 0,
                "explanation": "carry out 执行、实施。",
            },
            {
                "question": "'Run into' someone means:",
                "options": ["collide with", "meet by chance", "bump into", "both A and B"],
                "answer_index": 3,
                "explanation": "run into 偶然遇见、撞上。",
            },
            {
                "question": "'Come up with' an idea means to:",
                "options": ["think of it", "propose it", "suggest it", "all of the above"],
                "answer_index": 3,
                "explanation": "come up with 提出、想到。",
            },
        ],
    },
    {
        "key": "grammar_tense",
        "module": "语法",
        "points": ("时态", "英语时态"),
        "match": ("时态", "过去式", "现在完成时"),
        "language": "en",
        "items": [
            {
                "question": "'I have been working here for 5 years' uses the ______ tense.",
                "options": ["present perfect continuous", "past continuous", "simple past", "future perfect"],
                "answer_index": 0,
                "explanation": "have been working 是现在完成进行时。",
            },
            {
                "question": "Choose the correct tense: 'When I arrived, they ______ dinner.'",
                "options": ["were having", "have had", "had had", "will have"],
                "answer_index": 2,
                "explanation": "我到达时，他们已经吃过晚餐了，用过去完成时。",
            },
            {
                "question": "'She will be sleeping when you call' uses:",
                "options": ["future continuous", "simple future", "future perfect", "present continuous"],
                "answer_index": 0,
                "explanation": "will be sleeping 是将来进行时。",
            },
            {
                "question": "The present perfect is used to express:",
                "options": ["past actions with present relevance", "completed past actions", "habitual actions", "future plans"],
                "answer_index": 0,
                "explanation": "现在完成时表示过去发生但对现在有影响的动作。",
            },
            {
                "question": "'I study English' is in the ______ tense.",
                "options": ["simple present", "simple past", "present continuous", "present perfect"],
                "answer_index": 0,
                "explanation": "study 是一般现在时。",
            },
            {
                "question": "'By next year, I will have graduated' uses:",
                "options": ["future perfect", "simple future", "present perfect", "past perfect"],
                "answer_index": 0,
                "explanation": "will have graduated 是将来完成时。",
            },
            {
                "question": "Choose the correct form: 'If I ______ you, I would apologize.'",
                "options": ["were", "was", "am", "had been"],
                "answer_index": 0,
                "explanation": "虚拟条件从句用 were（即使主语是第一人称）。",
            },
            {
                "question": "'They had already left when I arrived' indicates:",
                "options": ["two past actions, one before the other", "simultaneous actions", "future actions", "habitual past actions"],
                "answer_index": 0,
                "explanation": "had left 表示在 arrived 之前已完成的动作。",
            },
        ],
    },
    {
        "key": "cloze_test",
        "module": "阅读",
        "points": ("完形填空", "篇章阅读"),
        "match": ("完形", "填空", "cloze"),
        "language": "en",
        "items": [
            {
                "question": "The student ______ hard for the exam and finally passed.",
                "options": ["studied", "studies", "studying", "study"],
                "answer_index": 0,
                "explanation": "与 finally passed 时间一致，用一般过去时。",
            },
            {
                "question": "Although she was tired, she ______ continue working.",
                "options": ["decided to", "decided", "decides to", "deciding to"],
                "answer_index": 0,
                "explanation": "decide to 后接动词原形。",
            },
            {
                "question": "The company provides its employees ______ health insurance.",
                "options": ["with", "to", "for", "at"],
                "answer_index": 0,
                "explanation": "provide sb. with sth. 为某人提供某物。",
            },
            {
                "question": "She was interested ______ learning about the new technology.",
                "options": ["in", "on", "at", "by"],
                "answer_index": 0,
                "explanation": "be interested in 对……感兴趣。",
            },
            {
                "question": "The teacher asked the students ______ submit their reports.",
                "options": ["to", "should", "would", "must"],
                "answer_index": 0,
                "explanation": "ask sb. to do 要求某人做某事。",
            },
            {
                "question": "______ the weather was bad, they still went hiking.",
                "options": ["Although", "Since", "While", "As"],
                "answer_index": 0,
                "explanation": "although 尽管，引出让步状语从句。",
            },
            {
                "question": "The more you practice, the ______ you will become.",
                "options": ["better", "best", "good", "goodly"],
                "answer_index": 0,
                "explanation": "the more... the... 结构中，better 是 good 的比较级。",
            },
            {
                "question": "He succeeded ______ working very hard.",
                "options": ["in", "by", "through", "with"],
                "answer_index": 1,
                "explanation": "succeed in / by 都可用，此处 by 表示通过方式。",
            },
        ],
    },
    {
        "key": "translation_english_chinese",
        "module": "翻译",
        "points": ("英汉翻译", "英译汉"),
        "match": ("翻译", "英汉翻译", "英译"),
        "language": "en",
        "items": [
            {
                "question": "Translate: 'She is a woman of great wisdom.'",
                "options": ["她是一个很聪明的女人。", "她是一个充满智慧的女人。", "她是一个学问高的女人。", "她是一个有大学问的女人。"],
                "answer_index": 1,
                "explanation": "great wisdom 意为充满大智慧，选项 B 最接近。",
            },
            {
                "question": "Translate: 'Time and tide wait for no man.'",
                "options": ["时间如潮水一样。", "时光似流水，一去不复返。", "时间和潮汐不等人。", "潮起潮落，时刻流逝。"],
                "answer_index": 1,
                "explanation": "这是著名的英文谚语，意为光阴易逝，不能浪费。",
            },
            {
                "question": "Translate: 'The conference is scheduled for next month.'",
                "options": ["会议是下个月计划的。", "会议被安排在下个月。", "下个月的会议被计划了。", "会议定在下个月。"],
                "answer_index": 3,
                "explanation": "schedule 表示安排时间，be scheduled for 被安排在……。",
            },
            {
                "question": "Translate: 'He has a gift for languages.'",
                "options": ["他是语言天才。", "他有学习语言的天赋。", "他是学语言的好手。", "B 和 C 都可以。"],
                "answer_index": 3,
                "explanation": "have a gift for 有天赋、特长。",
            },
            {
                "question": "Translate: 'The decision is beyond my control.'",
                "options": ["决定超出了我的能力。", "这个决定我无法控制。", "决定不在我的权力范围内。", "B 和 C 都可以。"],
                "answer_index": 3,
                "explanation": "beyond one's control 超出某人的控制范围。",
            },
            {
                "question": "Translate: 'She managed to overcome the difficulties.'",
                "options": ["她设法克服了困难。", "她管理好了困难。", "她努力克服困难。", "A 和 B 都可以。"],
                "answer_index": 0,
                "explanation": "managed to do 设法成功地做某事。",
            },
            {
                "question": "Translate: 'I cannot help but feel sorry for him.'",
                "options": ["我禁不住同情他。", "我无法帮助他，感到遗憾。", "我不得不为他感到遗憾。", "我忍不住同情他。"],
                "answer_index": 0,
                "explanation": "cannot but do = cannot help doing 禁不住、忍不住。",
            },
            {
                "question": "Translate: 'The book has been translated into 20 languages.'",
                "options": ["这本书被翻译成 20 种语言。", "这本书已经用 20 种语言翻译了。", "这本书被翻译成了 20 种语言。", "A 和 C 都可以。"],
                "answer_index": 3,
                "explanation": "被动语态表示书被翻译。",
            },
        ],
    },
    {
        "key": "sentence_error_correction",
        "module": "语法",
        "points": ("改错题", "句式改错"),
        "match": ("改错", "错误", "改正"),
        "language": "en",
        "items": [
            {
                "question": "Which sentence has an error? 'A. Neither of the students are present today. B. Neither student is present today. C. Both of the students are present. D. Each student is present.'",
                "options": ["A", "B", "C", "D"],
                "answer_index": 0,
                "explanation": "Neither + of + plural noun 用单数动词，should be 'Neither of the students is'。",
            },
            {
                "question": "Which is incorrect? 'A. He as well as his friends are coming. B. He and his friends are coming. C. His friends as well as he are coming. D. Neither statement is correct.'",
                "options": ["A", "B", "C", "D"],
                "answer_index": 0,
                "explanation": "A 中 as well as 连接时，主语由前面的名词决定，He 是单数，所以用 is。",
            },
            {
                "question": "Find the error: 'She asked if I was interested in joining them on a vacation to Europe.'",
                "options": ["No error", "on 应该改为 in", "joining 应改为 to join", "them 应改为 their"],
                "answer_index": 0,
                "explanation": "这个句子语法正确。",
            },
            {
                "question": "Which has an error? 'She is not only intelligent but also she is hardworking.'",
                "options": ["No error", "she is 应删除", "intelligent 改为 intelligence", "but also 改为 but"],
                "answer_index": 1,
                "explanation": "not only... but also... 后接平行结构，should be 'not only intelligent but also hardworking'。",
            },
            {
                "question": "Identify the error: 'If I was you, I would not make that mistake.'",
                "options": ["No error", "was 改为 were", "would 改为 will", "mistake 改为 error"],
                "answer_index": 1,
                "explanation": "虚拟条件句用 were，not was。",
            },
        ],
    },
]

# ==================== 与原 ENGLISH_BANKS 合并 ====================
# 使用时在 quiz.py 中：BANKS = ENGLISH_BANKS + ENGLISH_BANKS_EXTENDED + MATH_BANKS + MATH_BANKS_EXTENDED
