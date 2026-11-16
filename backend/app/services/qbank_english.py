"""英语类知识点题库（CET-4 目标下的听说读写译）。

每个知识点一个独立题库，题目只考该知识点本身，避免「矩阵/行列式/向量」共用一道题。
`points` 是精确知识点名（命中即用，不受关键词冲突影响），`match` 是给自定义知识点名兜底的关键词。
"""

from typing import Dict, List

ENGLISH_BANKS: List[Dict] = [
    {
        "key": "listening",
        "module": "听力",
        "points": ("听力", "听力理解"),
        "match": ("听力", "听写"),
        "language": "en",
        "items": [
            {
                "question": (
                    "W: The meeting was supposed to start at nine, but it's already twenty past.\n"
                    "M: Mr. Brown, our manager, had his flight delayed, so we'll wait another ten minutes.\n"
                    "What are they waiting for?"
                ),
                "options": [
                    "The manager's arrival",
                    "A call from the airport",
                    "The meeting room to open",
                    "A delayed report",
                ],
                "answer_index": 0,
                "explanation": "男士说经理 Brown 先生的航班延误，要再等十分钟，因此在等经理到场。",
            },
            {
                "question": (
                    "M: I'd like to book a double room for two nights, please.\n"
                    "W: I'm afraid we're fully booked this weekend. We can offer you a single room instead.\n"
                    "What does the woman say about the double room?"
                ),
                "options": [
                    "It is available next week",
                    "It is too expensive",
                    "It is unavailable this weekend",
                    "It has no window",
                ],
                "answer_index": 2,
                "explanation": "女士说周末已订满（fully booked），双人房本周末订不到。",
            },
            {
                "question": (
                    "A new study finds that students who take notes by hand remember more than those who type. "
                    "Researchers say writing slows the process down and forces the brain to choose key points.\n"
                    "What is the main finding of the study?"
                ),
                "options": [
                    "Typing is faster than writing",
                    "Students prefer digital notes",
                    "Note-taking should be banned",
                    "Handwriting notes helps memory",
                ],
                "answer_index": 3,
                "explanation": "短文首句即结论：手写笔记的学生记得更多。",
            },
            {
                "question": (
                    "W: Your passport and boarding pass, please. Put your bag on the belt.\n"
                    "M: Do I need to take out my laptop?\n"
                    "Where does the conversation most probably take place?"
                ),
                "options": [
                    "At a hotel front desk",
                    "At a security check",
                    "At a bank counter",
                    "At a ticket office",
                ],
                "answer_index": 1,
                "explanation": "检查护照、登机牌并要求把包放上传送带，是安检口的典型场景。",
            },
        ],
    },
    {
        "key": "short_dialogue",
        "module": "听力",
        "points": ("短对话",),
        "match": ("短对话",),
        "language": "en",
        "items": [
            {
                "question": (
                    "W: Did you finish the report for Mr. Lee?\n"
                    "M: I'm still waiting for the sales figures from the finance office.\n"
                    "What is the man waiting for?"
                ),
                "options": [
                    "Mr. Lee's approval",
                    "A meeting room",
                    "The sales figures",
                    "A new computer",
                ],
                "answer_index": 2,
                "explanation": "男士明确说还在等财务办公室的销售数据。",
            },
            {
                "question": (
                    "M: The train leaves at 8:15.\n"
                    "W: Then we'd better leave home by 7:30, or we'll be caught in the rush hour.\n"
                    "What does the woman suggest?"
                ),
                "options": [
                    "Leaving home earlier",
                    "Taking a taxi instead",
                    "Buying tickets online",
                    "Missing the train",
                ],
                "answer_index": 0,
                "explanation": "女士建议 7:30 前出门，以免赶上早高峰。",
            },
            {
                "question": (
                    "W: I can't believe the library is closed today.\n"
                    "M: It has been closed on Sundays since the renovation began in March.\n"
                    "What do we learn about the library?"
                ),
                "options": [
                    "It moved to a new building",
                    "It opens only on weekdays",
                    "It is closed every day",
                    "It has been closed on Sundays since March",
                ],
                "answer_index": 3,
                "explanation": "男士说自三月开始翻修以来，图书馆周日一直闭馆。",
            },
            {
                "question": (
                    "M: You look exhausted.\n"
                    "W: I stayed up until two preparing for today's presentation, and now I can hardly keep my eyes open.\n"
                    "Why is the woman tired?"
                ),
                "options": [
                    "She worked out in the gym",
                    "She prepared for a presentation late at night",
                    "She had a long meeting",
                    "She traveled all night",
                ],
                "answer_index": 1,
                "explanation": "女士说为准备今天的演讲熬到凌晨两点。",
            },
        ],
    },
    {
        "key": "long_dialogue",
        "module": "听力",
        "points": ("长对话",),
        "match": ("长对话",),
        "language": "en",
        "items": [
            {
                "question": (
                    "M: I saw your advertisement for a two-bedroom apartment near the campus.\n"
                    "W: Yes, it's 1,800 yuan a month, and the rent includes water and electricity.\n"
                    "M: That's reasonable. Can I see it this afternoon?\n"
                    "What do we learn about the apartment?"
                ),
                "options": [
                    "It is far from the campus",
                    "Its rent covers water and electricity",
                    "It has only one bedroom",
                    "It is free of charge",
                ],
                "answer_index": 1,
                "explanation": "女士说月租 1800 元，且含水费和电费。",
            },
            {
                "question": (
                    "W: I'm thinking of taking Professor Wang's course on data analysis.\n"
                    "M: You should check the requirements first. Last year half the class dropped out because of the workload.\n"
                    "What does the man advise the woman to do?"
                ),
                "options": [
                    "Drop the course immediately",
                    "Ask the professor for a job",
                    "Take an easier course instead",
                    "Check the course requirements first",
                ],
                "answer_index": 3,
                "explanation": "男士让她先看清课程要求，并提醒去年因课业量退课的人很多。",
            },
            {
                "question": (
                    "M: How did your interview go?\n"
                    "W: The manager asked a lot about my previous job, but said nothing about salary.\n"
                    "What can we learn from the conversation?"
                ),
                "options": [
                    "Salary was not discussed",
                    "She got the job",
                    "The manager was rude",
                    "She forgot her resume",
                ],
                "answer_index": 0,
                "explanation": "女士明确说经理没提薪水，因此薪资未被讨论。",
            },
            {
                "question": (
                    "W: Are you driving to the conference in Shanghai?\n"
                    "M: No, the high-speed train takes only four hours, and I can work on the way.\n"
                    "Why does the man choose the train?"
                ),
                "options": [
                    "It is cheaper than driving",
                    "He has no car",
                    "It saves time and lets him work",
                    "He dislikes flying",
                ],
                "answer_index": 2,
                "explanation": "男士说高铁只要四小时，而且路上能工作，兼顾省时与效率。",
            },
        ],
    },
    {
        "key": "listening_passage",
        "module": "听力",
        "points": ("听力篇章",),
        "match": ("听力篇章", "篇章听力", "讲座听力"),
        "language": "en",
        "items": [
            {
                "question": (
                    "Bike-sharing programs have spread to more than 200 cities. Supporters say they reduce traffic "
                    "and pollution, but critics complain that abandoned bikes block sidewalks.\n"
                    "What is the critics' main concern?"
                ),
                "options": [
                    "The high rental price",
                    "Bikes blocking sidewalks",
                    "The poor quality of bikes",
                    "The lack of parking spaces",
                ],
                "answer_index": 1,
                "explanation": "转折词 but 之后是批评者的关注点：废弃单车占道。",
            },
            {
                "question": (
                    "Researchers found that teenagers who use screens before bed take longer to fall asleep. "
                    "They suggest keeping phones out of the bedroom.\n"
                    "What do the researchers suggest?"
                ),
                "options": [
                    "Sleeping earlier on weekends",
                    "Using smaller screens",
                    "Keeping phones out of the bedroom",
                    "Taking sleeping pills",
                ],
                "answer_index": 2,
                "explanation": "研究者建议把手机拿出卧室。",
            },
            {
                "question": (
                    "Each year, over 3,000 students join the city's weekend reading program, helping children in "
                    "rural areas improve their reading skills.\n"
                    "What is the program mainly about?"
                ),
                "options": [
                    "Helping rural children read",
                    "Training new teachers",
                    "Raising money for schools",
                    "Building rural libraries",
                ],
                "answer_index": 0,
                "explanation": "短文说项目帮助农村孩子提高阅读能力。",
            },
            {
                "question": (
                    "The new city museum opens at nine every morning except Monday. Admission is free, but visitors "
                    "need to book online at least one day in advance.\n"
                    "What must visitors do before visiting the museum?"
                ),
                "options": [
                    "Pay an entrance fee",
                    "Come on Monday",
                    "Book online one day ahead",
                    "Bring a student card",
                ],
                "answer_index": 2,
                "explanation": "博物馆免费，但需至少提前一天网上预约。",
            },
        ],
    },
    {
        "key": "reading",
        "module": "阅读",
        "points": ("阅读", "阅读理解"),
        "match": ("阅读",),
        "language": "en",
        "items": [
            {
                "question": (
                    "Many companies now allow employees to work from home two days a week. They report higher "
                    "productivity and lower office costs, though some managers worry about teamwork.\n"
                    "What is the passage mainly about?"
                ),
                "options": [
                    "The benefits and concerns of remote work",
                    "How to rent an office",
                    "Why teamwork is important",
                    "The history of large companies",
                ],
                "answer_index": 0,
                "explanation": "全段既讲远程办公的好处，也讲管理者的顾虑。",
            },
            {
                "question": (
                    "Online courses have become popular, yet completion rates remain low: fewer than 15 percent of "
                    "learners finish a free course.\n"
                    "What does the passage say about free online courses?"
                ),
                "options": [
                    "They are too expensive",
                    "They attract few learners",
                    "Most learners do not finish them",
                    "They are better than classroom courses",
                ],
                "answer_index": 2,
                "explanation": "完成率不足 15%，说明多数学习者没有学完。",
            },
            {
                "question": (
                    "The city library now offers free Wi-Fi and quiet study rooms, making it an affordable place "
                    "for students to prepare for exams.\n"
                    'The word "affordable" is closest in meaning to:'
                ),
                "options": [
                    "difficult",
                    "optional",
                    "popular",
                    "not expensive",
                ],
                "answer_index": 3,
                "explanation": "affordable 意为「负担得起的、不贵的」。",
            },
            {
                "question": (
                    "Although the new policy was announced in June, few schools had put it into practice by the "
                    "end of the year.\n"
                    "What can be inferred?"
                ),
                "options": [
                    "The policy was canceled",
                    "Implementation was slow",
                    "Schools opposed the policy",
                    "The policy was announced twice",
                ],
                "answer_index": 1,
                "explanation": "政策六月公布、年底仍少有学校落实，可推知执行缓慢。",
            },
        ],
    },
    {
        "key": "banked_cloze",
        "module": "阅读",
        "points": ("选词填空",),
        "match": ("选词填空", "选词"),
        "language": "en",
        "items": [
            {
                "question": "The company decided to ______ the new product next month.",
                "options": ["launching", "launched", "launch", "launches"],
                "answer_index": 2,
                "explanation": "decide to do sth.，to 后接动词原形 launch。",
            },
            {
                "question": "She was ______ for her outstanding contribution to education.",
                "options": ["recognized", "recognizing", "recognize", "recognition"],
                "answer_index": 0,
                "explanation": "be recognized for 意为「因……受到认可」，用过去分词构成被动。",
            },
            {
                "question": "The heavy rain ______ the construction work for two days.",
                "options": ["delay", "delaying", "delays", "delayed"],
                "answer_index": 3,
                "explanation": "句子叙述已发生的事，用一般过去时 delayed。",
            },
            {
                "question": "The two countries agreed to ______ cooperation in clean energy.",
                "options": ["strengthened", "strengthen", "strengthening", "strengthens"],
                "answer_index": 1,
                "explanation": "agree to do sth.，to 后接动词原形 strengthen。",
            },
        ],
    },
    {
        "key": "long_reading",
        "module": "阅读",
        "points": ("长篇阅读",),
        "match": ("长篇阅读", "信息匹配", "段落匹配"),
        "language": "en",
        "items": [
            {
                "question": (
                    "Paragraph 3: Companies that invest in employee training see lower turnover and higher "
                    "customer satisfaction.\n"
                    "Which statement best matches Paragraph 3?"
                ),
                "options": [
                    "Training is too expensive for small firms",
                    "Training employees brings business benefits",
                    "Customers prefer trained staff only",
                    "Turnover is unrelated to training",
                ],
                "answer_index": 1,
                "explanation": "该段讲培训带来更低流失率和更高满意度，即商业收益。",
            },
            {
                "question": (
                    'In the passage, "a growing number of" is closest in meaning to:'
                ),
                "options": [
                    "a limited number of",
                    "a fixed number of",
                    "no more than",
                    "an increasing number of",
                ],
                "answer_index": 3,
                "explanation": "a growing number of = an increasing number of，越来越多的。",
            },
            {
                "question": (
                    "According to the passage, which group benefits most from the new subway line?\n"
                    "The line connects three suburbs with the city center, cutting commuting time by half for "
                    "residents there."
                ),
                "options": [
                    "People living in the suburbs",
                    "Taxi drivers",
                    "Shop owners downtown",
                    "Airline passengers",
                ],
                "answer_index": 0,
                "explanation": "新线路连接三个郊区与市中心，通勤时间减半，郊区居民受益最大。",
            },
            {
                "question": (
                    "Paragraph 5 discusses how cities can reduce waste by charging households for the garbage "
                    "they produce.\n"
                    "What is Paragraph 5 mainly about?"
                ),
                "options": [
                    "The cost of recycling plants",
                    "Why waste is increasing",
                    "A pricing method to cut waste",
                    "How households sort garbage",
                ],
                "answer_index": 2,
                "explanation": "该段讲按垃圾量收费这一价格手段来减少垃圾。",
            },
        ],
    },
    {
        "key": "careful_reading",
        "module": "阅读",
        "points": ("仔细阅读",),
        "match": ("仔细阅读", "篇章阅读"),
        "language": "en",
        "items": [
            {
                "question": (
                    "The regulation is far from perfect, but it is a necessary first step.\n"
                    "The author's attitude toward the new regulation can best be described as:"
                ),
                "options": [
                    "strongly opposed",
                    "completely indifferent",
                    "cautiously supportive",
                    "highly enthusiastic",
                ],
                "answer_index": 2,
                "explanation": "承认不完美（far from perfect）但认为必要，属于有保留的支持。",
            },
            {
                "question": (
                    "Studies show that students who sleep fewer than six hours a night perform worse on memory "
                    "tests than those who sleep eight hours.\n"
                    "What do the studies show?"
                ),
                "options": [
                    "Sleep has no effect on memory",
                    "Short sleep is linked to worse memory performance",
                    "Eight hours of sleep is harmful",
                    "Students need less sleep before exams",
                ],
                "answer_index": 1,
                "explanation": "研究对比说明睡眠不足与记忆表现更差相关。",
            },
            {
                "question": (
                    "In 2019, a national report revealed that half of the graduates lacked basic writing skills. "
                    "This finding explains why many universities have added writing courses.\n"
                    "The author mentions the 2019 report mainly to:"
                ),
                "options": [
                    "criticize universities",
                    "praise graduates",
                    "compare two countries",
                    "support the need for writing courses",
                ],
                "answer_index": 3,
                "explanation": "报告结论被用来解释高校增设写作课的原因。",
            },
            {
                "question": (
                    "Remote workers often report feeling isolated, even though they save time on commuting.\n"
                    "What can be inferred?"
                ),
                "options": [
                    "Remote work has social costs",
                    "Commuting improves productivity",
                    "Remote workers never meet colleagues",
                    "Saving time is unimportant",
                ],
                "answer_index": 0,
                "explanation": "虽省通勤时间，却常感孤立，说明远程办公有社交代价。",
            },
        ],
    },
    {
        "key": "writing",
        "module": "写作",
        "points": ("写作", "作文"),
        "match": ("写作", "作文"),
        "language": "en",
        "items": [
            {
                "question": "Which sentence best introduces the main argument of an essay about online learning?",
                "options": [
                    "Online learning is a topic I will discuss.",
                    "Online learning, though convenient, requires stronger self-discipline than classroom study.",
                    "Many people learn online.",
                    "I have used online learning for years.",
                ],
                "answer_index": 1,
                "explanation": "该句给出可论证的明确立场，且带让步结构，适合作论点句。",
            },
            {
                "question": "Which sentence best expresses a cause-effect relationship?",
                "options": [
                    "Students are busy and tired.",
                    "Students should sleep more.",
                    "As a result of tighter schedules, many students sleep less.",
                    "Sleeping is important for students.",
                ],
                "answer_index": 2,
                "explanation": "As a result of 明确引出因果关系。",
            },
            {
                "question": "Which sentence is the most appropriate conclusion for an argumentative essay?",
                "options": [
                    "In short, stricter waste sorting rules are necessary for a cleaner city.",
                    "Waste sorting is a popular topic.",
                    "I will talk about waste sorting next.",
                    "Some people sort waste, some do not.",
                ],
                "answer_index": 0,
                "explanation": "In short 收束全文并重申主张，符合结论句功能。",
            },
            {
                "question": "Which sentence best introduces a concession?",
                "options": [
                    "Therefore, the policy must be stopped.",
                    "The policy is completely wrong.",
                    "In addition, the policy costs money.",
                    "Admittedly, the policy has costs, but its long-term benefits outweigh them.",
                ],
                "answer_index": 3,
                "explanation": "Admittedly... but... 先让步再转折，是典型的让步句。",
            },
        ],
    },
    {
        "key": "argument_structure",
        "module": "写作",
        "points": ("议论文结构",),
        "match": ("议论文", "论证结构", "文章结构"),
        "language": "en",
        "items": [
            {
                "question": "Where does the thesis statement of an argumentative essay usually appear?",
                "options": [
                    "In the last sentence of the conclusion",
                    "In the title only",
                    "In every body paragraph",
                    "At the end of the introduction",
                ],
                "answer_index": 3,
                "explanation": "论点句通常出现在引言段末尾，统领全文。",
            },
            {
                "question": (
                    "A paragraph that presents the opposing view before refuting it is called:"
                ),
                "options": [
                    "a concession paragraph",
                    "a narrative paragraph",
                    "a definition paragraph",
                    "a summary paragraph",
                ],
                "answer_index": 0,
                "explanation": "先承认对方观点再反驳，是让步段（concession paragraph）。",
            },
            {
                "question": "Which of the following is a statistic used as evidence?",
                "options": [
                    "A personal story about a friend",
                    "An expert's opinion quoted in a blog",
                    "A 2024 survey showing 68 percent of students feel stressed",
                    "A famous saying",
                ],
                "answer_index": 2,
                "explanation": "含年份、样本与百分比的数据才是统计论据。",
            },
            {
                "question": "What is the main function of a topic sentence?",
                "options": [
                    "To list all the sources",
                    "To state the main idea of a paragraph",
                    "To end the essay",
                    "To introduce the author",
                ],
                "answer_index": 1,
                "explanation": "主题句的作用是概括该段主旨。",
            },
        ],
    },
    {
        "key": "sentence_patterns",
        "module": "写作",
        "points": ("常用句型",),
        "match": ("常用句型", "句型", "句式"),
        "language": "en",
        "items": [
            {
                "question": "Not until he lost his job ______ how much he depended on it.",
                "options": ["he realized", "he had realized", "did he realize", "he did realize"],
                "answer_index": 2,
                "explanation": "Not until 置于句首，主句部分倒装：did he realize。",
            },
            {
                "question": "It was in 2015 ______ the city opened its first subway line.",
                "options": ["when", "which", "where", "that"],
                "answer_index": 3,
                "explanation": "强调句型 It was ... that ...，强调时间状语。",
            },
            {
                "question": "It is high time that we ______ action to protect the environment.",
                "options": ["take", "took", "will take", "have taken"],
                "answer_index": 1,
                "explanation": "It is high time that 从句用过去式（或 should + 动词原形），表示早该做某事。",
            },
            {
                "question": "With all the work ______, she went home happily.",
                "options": ["finished", "finishing", "to finish", "finish"],
                "answer_index": 0,
                "explanation": "with 复合结构中，work 与 finish 是被动关系，用过去分词 finished。",
            },
        ],
    },
    {
        "key": "translation",
        "module": "翻译",
        "points": ("翻译", "汉译英"),
        "match": ("翻译", "汉译英"),
        "language": "en",
        "items": [
            {
                "question": "Choose the best English translation: 这项政策有助于缩小城乡差距。",
                "options": [
                    "The policy is helpful.",
                    "The policy helps narrow the gap between urban and rural areas.",
                    "The policy narrows the gap between city and country.",
                    "The policy helps to make the gap.",
                ],
                "answer_index": 1,
                "explanation": "「缩小城乡差距」的标准译法是 narrow the gap between urban and rural areas。",
            },
            {
                "question": "Choose the best English translation: 随着科技的发展，人们的生活方式发生了巨大变化。",
                "options": [
                    "With the development of technology, people's lifestyles have changed dramatically.",
                    "People life changed a lot.",
                    "Technology develops and people change.",
                    "Because technology, people's life changed.",
                ],
                "answer_index": 0,
                "explanation": "With the development of... 作伴随状语，dramatically 对应「巨大」。",
            },
            {
                "question": "Choose the best English translation: 春节是中国最重要的传统节日。",
                "options": [
                    "Spring Festival is a festival in China.",
                    "Chinese people like Spring Festival very much.",
                    "The Spring Festival is the most important traditional festival in China.",
                    "Spring Festival is important and traditional.",
                ],
                "answer_index": 2,
                "explanation": "最高级 the most important traditional festival 才对应「最重要的传统节日」。",
            },
            {
                "question": "Choose the best English translation: 越来越多的人意识到锻炼的重要性。",
                "options": [
                    "Many people exercise.",
                    "Exercise is important for people.",
                    "More people realize exercise.",
                    "More and more people are aware of the importance of exercise.",
                ],
                "answer_index": 3,
                "explanation": "be aware of the importance of 对应「意识到……的重要性」。",
            },
        ],
    },
    {
        "key": "chinese_culture",
        "module": "翻译",
        "points": ("中国文化",),
        "match": ("中国文化", "传统文化", "文化"),
        "language": "en",
        "items": [
            {
                "question": "Which festival is known as the Chinese Valentine's Day?",
                "options": ["Qixi", "Spring Festival", "Mid-Autumn Festival", "Lantern Festival"],
                "answer_index": 0,
                "explanation": "七夕（Qixi）源自牛郎织女传说，被称为中国情人节。",
            },
            {
                "question": "The Great Wall was mainly built to:",
                "options": [
                    "attract tourists",
                    "store grain",
                    "defend against invasions",
                    "mark provincial borders",
                ],
                "answer_index": 2,
                "explanation": "长城的主要历史功能是抵御北方入侵。",
            },
            {
                "question": "Peking Opera is best known for its:",
                "options": [
                    "simple plots and modern settings",
                    "combination of singing, acting and acrobatics",
                    "use of Western instruments only",
                    "spoken dialogue without music",
                ],
                "answer_index": 1,
                "explanation": "京剧以唱、念、做、打（含杂技）综合表演著称。",
            },
            {
                "question": "Which of the following is one of China's Four Great Inventions?",
                "options": ["the steam engine", "the telephone", "the electric light", "paper-making"],
                "answer_index": 3,
                "explanation": "四大发明为造纸术、印刷术、火药、指南针，paper-making 对应造纸术。",
            },
        ],
    },
    {
        "key": "sentence_structure",
        "module": "翻译",
        "points": ("句子结构",),
        "match": ("句子结构", "句法", "长难句"),
        "language": "en",
        "items": [
            {
                "question": "The number of students taking online courses ______ increasing.",
                "options": ["are", "is", "were", "have been"],
                "answer_index": 1,
                "explanation": "主语是 the number（单数），谓语用 is；a number of 才接复数。",
            },
            {
                "question": "Which sentence is grammatically correct?",
                "options": [
                    "Walking down the street, the trees looked beautiful.",
                    "Walking down the street, the trees were seen by me.",
                    "Walking down the street, trees look beautiful.",
                    "Walking down the street, I saw beautiful trees.",
                ],
                "answer_index": 3,
                "explanation": "分词短语的逻辑主语必须与主句主语一致，只有 D 的主语是 I。",
            },
            {
                "question": "______ the weather was bad, the match went on.",
                "options": ["Although", "Because", "So", "Therefore"],
                "answer_index": 0,
                "explanation": "前后为让步关系：虽然天气不好，比赛仍继续。",
            },
            {
                "question": "She likes reading, swimming and ______.",
                "options": ["to paint", "paint", "painting", "painted"],
                "answer_index": 2,
                "explanation": "并列结构需保持形式一致，与 reading、swimming 并列用动名词 painting。",
            },
        ],
    },
    {
        "key": "vocabulary",
        "module": "词汇",
        "points": ("词汇", "单词"),
        "match": ("词汇", "单词"),
        "language": "en",
        "items": [
            {
                "question": 'The word "address" in "address the problem" most nearly means:',
                "options": ["write down", "speak to", "live at", "deal with"],
                "answer_index": 3,
                "explanation": "address the problem 是固定搭配，意为「处理/解决」。",
            },
            {
                "question": 'Choose the word closest in meaning to "inevitable":',
                "options": ["unavoidable", "unclear", "unfair", "unusual"],
                "answer_index": 0,
                "explanation": "inevitable 表示「不可避免的」，与 unavoidable 同义。",
            },
            {
                "question": "The heavy rain will ______ the harvest.",
                "options": ["effect", "affect", "effort", "afford"],
                "answer_index": 1,
                "explanation": "affect 是动词「影响」；effect 作名词才是「影响、效果」。",
            },
            {
                "question": "She finally ______ a decision after a long discussion.",
                "options": ["did", "took", "made", "got"],
                "answer_index": 2,
                "explanation": "固定搭配 make a decision（做决定）。",
            },
        ],
    },
    {
        "key": "high_freq_words",
        "module": "词汇",
        "points": ("高频词汇", "核心词汇"),
        "match": ("高频词汇", "核心词汇"),
        "language": "en",
        "items": [
            {
                "question": 'The word "significant" most nearly means:',
                "options": ["very small", "temporary", "important", "difficult"],
                "answer_index": 2,
                "explanation": "significant 意为「重要的、显著的」。",
            },
            {
                "question": "We need a new ______ to solving this problem.",
                "options": ["approve", "approach", "appearance", "approval"],
                "answer_index": 1,
                "explanation": "an approach to doing sth. 表示「解决……的方法」。",
            },
            {
                "question": 'The word "available" most nearly means:',
                "options": ["able to be used or obtained", "easy to break", "very expensive", "difficult to find"],
                "answer_index": 0,
                "explanation": "available 意为「可获得的、可用的」。",
            },
            {
                "question": 'The phrase "contribute to" most nearly means:',
                "options": ["take away from", "depend on", "compete with", "help to cause"],
                "answer_index": 3,
                "explanation": "contribute to 意为「促成、有助于」。",
            },
        ],
    },
    {
        "key": "word_special_meaning",
        "module": "词汇",
        "points": ("熟词僻义", "一词多义"),
        "match": ("熟词僻义", "一词多义"),
        "language": "en",
        "items": [
            {
                "question": 'In "He delivered an address to the students", "address" means:',
                "options": ["a home", "a speech", "a letter", "a problem"],
                "answer_index": 1,
                "explanation": "deliver an address 意为「发表演讲」，address 此处是名词「演讲」。",
            },
            {
                "question": 'In "We booked a table for two", "book" means:',
                "options": ["read", "wrote", "canceled", "reserved"],
                "answer_index": 3,
                "explanation": "book 作动词意为「预订」，与 reserve 同义。",
            },
            {
                "question": 'In "She enjoys the company of her classmates", "company" means:',
                "options": ["a firm", "a group of soldiers", "the state of being with others", "a theater group"],
                "answer_index": 2,
                "explanation": "the company of sb. 指「与某人相伴」，不是「公司」。",
            },
            {
                "question": 'In "I figure he will arrive by noon", "figure" means:',
                "options": ["think", "draw", "count", "appear"],
                "answer_index": 0,
                "explanation": "figure 在口语中作动词，意为「认为、估计」。",
            },
        ],
    },
    {
        "key": "grammar",
        "module": "语法",
        "points": ("语法",),
        "match": ("语法", "时态", "语态"),
        "language": "en",
        "items": [
            {
                "question": "He ______ in Beijing since 2018.",
                "options": ["lives", "lived", "has lived", "is living"],
                "answer_index": 2,
                "explanation": "since + 时间点提示现在完成时，用 has lived。",
            },
            {
                "question": "The report ______ by the end of last week.",
                "options": ["had been finished", "has finished", "was finishing", "finishes"],
                "answer_index": 0,
                "explanation": "by the end of last week 是过去完成时的标志，且 report 与 finish 为被动关系。",
            },
            {
                "question": "If I ______ you, I would accept the offer.",
                "options": ["am", "was", "will be", "were"],
                "answer_index": 3,
                "explanation": "与现在事实相反的虚拟语气，be 动词一律用 were。",
            },
            {
                "question": "Neither the teacher nor the students ______ aware of the change.",
                "options": ["is", "were", "was", "has been"],
                "answer_index": 1,
                "explanation": "neither...nor... 遵循就近原则，靠近 students，用复数 were。",
            },
        ],
    },
    {
        "key": "clauses",
        "module": "语法",
        "points": ("从句",),
        "match": ("从句", "定语从句", "状语从句", "名词性从句"),
        "language": "en",
        "items": [
            {
                "question": "The book ______ I bought yesterday is very interesting.",
                "options": ["who", "which", "whose", "where"],
                "answer_index": 1,
                "explanation": "先行词是物，定语从句用 which（或 that）。",
            },
            {
                "question": "______ he is young, he has traveled to many countries.",
                "options": ["Because", "So", "If", "Although"],
                "answer_index": 3,
                "explanation": "前后为让步关系：虽然他年轻，却已游历多国。",
            },
            {
                "question": "______ he said at the meeting surprised everyone.",
                "options": ["What", "That", "Which", "Whether"],
                "answer_index": 0,
                "explanation": "主语从句缺 said 的宾语，用 what 引导。",
            },
            {
                "question": "The girl ______ father is a doctor studies very hard.",
                "options": ["who", "which", "whose", "whom"],
                "answer_index": 2,
                "explanation": "表示所属关系「女孩的父亲」，用 whose。",
            },
        ],
    },
    {
        "key": "non_finite_verbs",
        "module": "语法",
        "points": ("非谓语动词",),
        "match": ("非谓语", "分词", "动名词", "不定式"),
        "language": "en",
        "items": [
            {
                "question": "______ his homework, he went out to play.",
                "options": ["Finish", "Finished", "To finish", "Having finished"],
                "answer_index": 3,
                "explanation": "完成作业发生在出去玩之前，用现在分词完成式 Having finished 作时间状语。",
            },
            {
                "question": "She went to the library ______ some books.",
                "options": ["borrowing", "to borrow", "borrowed", "borrow"],
                "answer_index": 1,
                "explanation": "不定式 to borrow 作目的状语，表示去图书馆的目的。",
            },
            {
                "question": "______ in 1990, the bridge is still in good condition.",
                "options": ["Building", "To build", "Built", "Having built"],
                "answer_index": 2,
                "explanation": "桥是被建造的，用过去分词 Built 作状语。",
            },
            {
                "question": "______ regularly is good for your health.",
                "options": ["Exercising", "Exercised", "To exercising", "Exercise"],
                "answer_index": 0,
                "explanation": "动名词作主语，表示习惯性行为，用 Exercising。",
            },
        ],
    },
]
