"""
模块间交互聚合器：协调出题、诊断、掌握度、重排、学情等模块。

设计原则：
1. 单一职责：每个模块负责自己的域逻辑
2. 数据驱动：通过共享数据模型通信而不是直接调用
3. 事件驱动：关键动作触发事件，其他模块订阅
4. 降级兼容：任何模块故障都有备选方案
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from ..models import Goal, KnowledgePoint, Mastery, Mistake, Task, User, MasteryHistory
from .quiz import generate_quiz, QuizResult
from .mastery_service import apply_answer, ensure_mastery
from .planner import replan, ReplanResult
from ..agents.diagnoser import diagnose
from .psychology import compute_fatigue_index, get_risk_assessment


class QuizAnswerEvent:
    """用户做题事件：出题 → 答题 → 判分 → 诊断 → 重排 → 学情更新 的完整流程。"""
    
    def __init__(
        self,
        user_id: int,
        goal_id: int,
        kp_id: int,
        question: str,
        options: List[str],
        user_answer_index: int,
        correct_answer_index: int,
        quiz_source: str = "bank",  # bank / llm / rule
    ):
        self.user_id = user_id
        self.goal_id = goal_id
        self.kp_id = kp_id
        self.question = question
        self.options = options
        self.user_answer_index = user_answer_index
        self.correct_answer_index = correct_answer_index
        self.quiz_source = quiz_source
        self.is_correct = user_answer_index == correct_answer_index
        self.timestamp = datetime.now()
        
        # 流程中产生的中间结果
        self.mastery_before: Optional[float] = None
        self.mastery_after: Optional[float] = None
        self.diagnosis: Optional[Dict] = None  # 四类错因诊断结果
        self.replan_triggered: bool = False
        self.replan_result: Optional[ReplanResult] = None
        self.fatigue_index: Optional[float] = None
        self.risks: Optional[Dict] = None


async def process_quiz_answer(
    db: Session,
    user: User,
    goal: Goal,
    event: QuizAnswerEvent,
    auto_diagnose: bool = True,
    auto_replan: bool = True,
    auto_assess_risk: bool = True,
) -> Dict:
    """
    完整的答题流程编排。
    
    流程：
    1. 获取答题前的掌握度快照
    2. 提交答案 → 更新掌握度
    3. 如果答错 → 诊断四类错因
    4. 检查是否触发重排条件
    5. 如果需要 → 触发动态重排
    6. 计算疲劳指数与风险等级
    7. 返回完整结果供前端展示
    """
    
    # ========== Step 1: 获取当前掌握度 ==========
    kp = db.query(KnowledgePoint).filter_by(id=event.kp_id).first()
    if not kp:
        return {"error": "知识点不存在"}
    
    mastery_before = ensure_mastery(db, user.id, kp)
    event.mastery_before = mastery_before.value
    
    # ========== Step 2: 提交答案，更新掌握度 ==========
    mastery_after = apply_answer(db, user.id, kp, correct=event.is_correct)
    event.mastery_after = mastery_after.value
    
    db.commit()
    
    # ========== Step 3: 如果答错，诊断四类错因 ==========
    diagnosis_result = None
    if not event.is_correct and auto_diagnose:
        # 获取正确答案文本
        correct_answer_text = event.options[event.correct_answer_index]
        user_answer_text = event.options[event.user_answer_index]
        
        # 调用诊断器
        category, label, suggestion, engine = await diagnose(
            event.question,
            user_answer_text,
            correct_answer_text,
            kp.name,
        )
        
        diagnosis_result = {
            "category": category,
            "label": label,
            "suggestion": suggestion,
            "engine": engine,  # llm / rule
        }
        event.diagnosis = diagnosis_result
    
    # ========== Step 4: 检查重排触发条件 ==========
    # 触发条件：
    # - 同知识点 7 天内错题 >= 2 道
    # - 当日任务超时
    # - 连续逾期任务
    should_replan = False
    replan_trigger = None
    
    if auto_replan:
        # 检查错题触发
        recent_mistakes = db.query(Mistake).filter(
            Mistake.user_id == user.id,
            Mistake.goal_id == goal.id,
            Mistake.kp_id == event.kp_id,
            Mistake.created_at >= datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        ).count()
        
        if not event.is_correct and recent_mistakes >= 1:  # 加上当前错题共 >= 2 道
            should_replan = True
            replan_trigger = "double_mistake"
    
    # ========== Step 5: 触发动态重排 ==========
    if should_replan and auto_replan:
        replan_result = replan(db, user.id, goal, trigger=replan_trigger)
        event.replan_triggered = True
        event.replan_result = replan_result
    
    # ========== Step 6: 计算疲劳指数与风险 ==========
    if auto_assess_risk:
        fatigue = compute_fatigue_index(db, user.id, goal.id)
        event.fatigue_index = fatigue
        
        risks = get_risk_assessment(db, user.id, goal.id)
        event.risks = risks
    
    # ========== 返回结果 ==========
    return {
        "timestamp": event.timestamp.isoformat(),
        "user_id": event.user_id,
        "goal_id": event.goal_id,
        "kp_id": event.kp_id,
        "kp_name": kp.name,
        "quiz": {
            "question": event.question[:100],  # 截断
            "is_correct": event.is_correct,
            "user_answer": event.options[event.user_answer_index] if 0 <= event.user_answer_index < len(event.options) else "无效答案",
            "correct_answer": event.options[event.correct_answer_index],
            "quiz_source": event.quiz_source,
        },
        "mastery": {
            "before": event.mastery_before,
            "after": event.mastery_after,
            "change": event.mastery_after - event.mastery_before,
        },
        "diagnosis": diagnosis_result,
        "replan": {
            "triggered": event.replan_triggered,
            "trigger": replan_trigger,
            "result": event.replan_result.model_dump(mode="json") if event.replan_result else None,
        } if auto_replan else None,
        "psychology": {
            "fatigue_index": event.fatigue_index,
            "risks": event.risks,
        } if auto_assess_risk else None,
    }


class PlanGenerationEvent:
    """计划生成事件：资料导入 → 知识点提取 → 优先级排序 → 任务分配。"""
    
    def __init__(
        self,
        user_id: int,
        goal_id: int,
        exam_name: str,
        days: int = 7,
        daily_minutes: int = 120,
    ):
        self.user_id = user_id
        self.goal_id = goal_id
        self.exam_name = exam_name
        self.days = days
        self.daily_minutes = daily_minutes
        self.timestamp = datetime.now()
        
        # 生成结果
        self.knowledge_points: Optional[List[KnowledgePoint]] = None
        self.tasks: Optional[List[Task]] = None
        self.warnings: List[str] = []


async def process_plan_generation(
    db: Session,
    user: User,
    goal: Goal,
    event: PlanGenerationEvent,
) -> Dict:
    """
    完整的计划生成流程。
    
    流程：
    1. 检查资料是否已导入
    2. 提取知识点树
    3. 按权重、掌握度、临近系数排序
    4. 分配每日任务（按时长约束）
    5. 记录任务理由
    6. 返回周计划
    """
    # TODO: 与 planner.py 协调
    
    return {
        "timestamp": event.timestamp.isoformat(),
        "user_id": event.user_id,
        "goal_id": event.goal_id,
        "exam_name": event.exam_name,
        "days": event.days,
        "daily_minutes": event.daily_minutes,
        "knowledge_points_count": len(event.knowledge_points) if event.knowledge_points else 0,
        "tasks_generated": len(event.tasks) if event.tasks else 0,
        "warnings": event.warnings,
    }


class LearningStateSnapshot:
    """学习状态快照：用于周报、学情诊断、冲刺预测等场景。"""
    
    def __init__(self, user_id: int, goal_id: int):
        self.user_id = user_id
        self.goal_id = goal_id
        self.snapshot_time = datetime.now()
        
        # 学习状态数据
        self.total_mastery: Optional[float] = None  # 总体掌握度（加权平均）
        self.mastery_distribution: Dict[str, float] = {}  # 各知识点掌握度
        self.completion_rate: Optional[float] = None  # 完成率
        self.task_count_total: int = 0
        self.task_count_completed: int = 0
        self.mistake_count: int = 0
        self.mistake_categories: Dict[str, int] = {}  # 四类错因分布
        self.study_rhythm: Optional[Dict] = None  # 学习节奏画像
        self.fatigue_index: Optional[float] = None
        self.risks: Optional[List[str]] = None


def take_learning_state_snapshot(db: Session, user_id: int, goal_id: int) -> LearningStateSnapshot:
    """生成学习状态快照。"""
    snapshot = LearningStateSnapshot(user_id, goal_id)
    
    # 查询掌握度
    masteries = db.query(Mastery).filter(
        Mastery.user_id == user_id,
        Mastery.goal_id == goal_id,
    ).all()
    
    if masteries:
        snapshot.total_mastery = sum(m.value for m in masteries) / len(masteries)
        snapshot.mastery_distribution = {
            m.knowledge_point.name: m.value
            for m in masteries
        }
    
    # 查询任务完成率
    tasks = db.query(Task).filter(
        Task.user_id == user_id,
        Task.goal_id == goal_id,
    ).all()
    
    if tasks:
        snapshot.task_count_total = len(tasks)
        snapshot.task_count_completed = len([t for t in tasks if t.completed_at])
        snapshot.completion_rate = snapshot.task_count_completed / snapshot.task_count_total
    
    # 查询错题统计
    mistakes = db.query(Mistake).filter(
        Mistake.user_id == user_id,
        Mistake.goal_id == goal_id,
    ).all()
    
    if mistakes:
        snapshot.mistake_count = len(mistakes)
        snapshot.mistake_categories = {
            category: len([m for m in mistakes if m.category == category])
            for category in ["concept", "method", "careless", "time"]
        }
    
    return snapshot


# ============================================================================
# 模块交互总结
# ============================================================================

"""
核心交互流程（已梳理）：

1. **用户做题** (quiz_answer_event)
   - quiz.py: 出题（题库优先 → API → LLM → 规则）
   - agents.diagnoser: 诊断错因
   - mastery_service.py: 更新掌握度
   - planner.py: 检查重排条件，自动调整
   - psychology.py: 计算疲劳，评估风险

2. **生成计划** (plan_generation_event)
   - planner.py: 按权重、掌握度、时间排序
   - mastery_service.py: 查询各知识点掌握度
   - psychology.py: 监测学习节奏

3. **学情诊断**
   - 调用 take_learning_state_snapshot()
   - agents.coach: 生成诊断建议
   - agents.reporter: 生成周报

4. **冲刺预测**
   - services.advanced.py: 基于记忆曲线预测
   - psychology.py: 考虑疲劳因素

关键数据流向：
  User.id
    ├─ Goal.id → mastery / tasks / mistakes → 学情
    ├─ Quiz (user_answer) → mastery_update → task_replan
    ├─ Mistake (category) → diagnosis_suggestion → task_insertion
    └─ Psychology (fatigue) → load_adjustment / risk_alert

测试策略：
- 单元测试：每个模块独立测试
- 集成测试：模块交互流程
- E2E 测试：用户完整路径（注册 → 导资料 → 生成计划 → 做题 → 重排 → 周报）
"""
