"""策略实验室：用小规模实验比较不同学习方式的收益。"""

from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    ExperimentMetric,
    Goal,
    KnowledgePoint,
    LearningExperiment,
    Mastery,
    Task,
    User,
)
from .rules import completion_rate

STRATEGY_LABELS = {
    "read": "精读理解",
    "practice": "刷题训练",
    "flashcard": "闪卡记忆",
    "ai_tutor": "AI 讲解",
}


def _avg_mastery(db: Session, user_id: int, goal_id: int) -> float:
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id == goal_id)).all()
    rows = db.scalars(
        select(Mastery).where(
            Mastery.user_id == user_id,
            Mastery.kp_id.in_([point.id for point in points] or [0]),
        )
    ).all()
    return round(sum(row.value for row in rows) / len(rows), 4) if rows else 0.0


def experiment_dict(experiment: LearningExperiment) -> Dict:
    gain = round(experiment.post_mastery - experiment.pre_mastery, 4)
    days_left = (experiment.end_date - date.today()).days
    return {
        "id": experiment.id,
        "strategy": experiment.strategy,
        "status": experiment.status,
        "days": experiment.days,
        "start_date": experiment.start_date,
        "end_date": experiment.end_date,
        "pre_mastery": experiment.pre_mastery,
        "post_mastery": experiment.post_mastery,
        "immediate_score": experiment.immediate_score,
        "delayed_score": experiment.delayed_score,
        "gain": gain,
        "note": experiment.note,
        # 到期未收尾：进行中但已过结束日，需要补延迟测试并提交结论。
        "expired": experiment.status == "running" and days_left < 0,
        "overdue_days": -days_left if experiment.status == "running" and days_left < 0 else 0,
        "days_left": days_left if experiment.status == "running" else 0,
    }


def start_experiment(
    db: Session, user: User, goal: Goal, strategy: str, days: int, today: Optional[date] = None
) -> LearningExperiment:
    today = today or date.today()
    experiment = LearningExperiment(
        user_id=user.id,
        goal_id=goal.id,
        strategy=strategy,
        status="running",
        days=days,
        start_date=today,
        end_date=today + timedelta(days=days - 1),
        pre_mastery=_avg_mastery(db, user.id, goal.id),
        post_mastery=_avg_mastery(db, user.id, goal.id),
    )
    db.add(experiment)
    db.flush()
    _record_metric(db, experiment, "mastery", experiment.pre_mastery, "pre", "实验开始平均掌握度")
    db.commit()
    db.refresh(experiment)
    return experiment


def finish_experiment(
    db: Session,
    user: User,
    experiment: LearningExperiment,
    immediate_score: int,
    delayed_score: int,
    note: str,
    today: Optional[date] = None,
) -> LearningExperiment:
    today = today or date.today()
    experiment.status = "finished"
    experiment.post_mastery = _avg_mastery(db, user.id, experiment.goal_id)
    experiment.immediate_score = immediate_score
    experiment.delayed_score = delayed_score
    experiment.note = note
    experiment.end_date = today
    _record_metric(db, experiment, "mastery", experiment.post_mastery, "post", "实验结束平均掌握度")
    _record_metric(db, experiment, "immediate_score", float(immediate_score), "post", "即时测试得分")
    _record_metric(db, experiment, "delayed_score", float(delayed_score), "post", "延迟测试得分")
    _record_metric(
        db,
        experiment,
        "mastery_gain",
        round(experiment.post_mastery - experiment.pre_mastery, 4),
        "post",
        "掌握度变化",
    )
    db.commit()
    db.refresh(experiment)
    return experiment


def _record_metric(
    db: Session,
    experiment: LearningExperiment,
    metric: str,
    value: float,
    phase: str,
    note: str = "",
) -> ExperimentMetric:
    row = ExperimentMetric(
        experiment_id=experiment.id,
        user_id=experiment.user_id,
        goal_id=experiment.goal_id,
        metric=metric,
        value=round(float(value), 4),
        phase=phase,
        note=note[:240],
    )
    db.add(row)
    return row


def build_ranking(db: Session, user_id: int, goal_id: int) -> List[Dict]:
    rows = db.scalars(
        select(LearningExperiment).where(
            LearningExperiment.user_id == user_id,
            LearningExperiment.goal_id == goal_id,
            LearningExperiment.status == "finished",
        )
    ).all()
    grouped: Dict[str, List[float]] = {}
    for row in rows:
        grouped.setdefault(row.strategy, []).append(row.post_mastery - row.pre_mastery)
    ranking = [
        {
            "strategy": strategy,
            "label": STRATEGY_LABELS.get(strategy, strategy),
            "avg_gain": round(sum(gains) / len(gains), 4),
            "experiments": len(gains),
        }
        for strategy, gains in grouped.items()
    ]
    ranking.sort(key=lambda item: item["avg_gain"], reverse=True)
    return ranking


def list_experiments(db: Session, user_id: int, goal_id: int) -> Dict:
    rows = db.scalars(
        select(LearningExperiment)
        .where(LearningExperiment.user_id == user_id, LearningExperiment.goal_id == goal_id)
        .order_by(LearningExperiment.created_at.desc())
    ).all()
    return {
        "items": [experiment_dict(row) for row in rows],
        "ranking": build_ranking(db, user_id, goal_id),
        "strategies": [
            {"key": key, "label": label} for key, label in STRATEGY_LABELS.items()
        ],
    }

def build_report(db: Session, experiment: LearningExperiment) -> Dict:
    metrics = db.scalars(
        select(ExperimentMetric)
        .where(ExperimentMetric.experiment_id == experiment.id)
        .order_by(ExperimentMetric.id.asc())
    ).all()
    metrics_out = [
        {"metric": row.metric, "value": round(row.value, 4), "phase": row.phase}
        for row in metrics
    ]

    tasks = db.scalars(
        select(Task).where(
            Task.user_id == experiment.user_id,
            Task.goal_id == experiment.goal_id,
            Task.day >= experiment.start_date,
            Task.day <= experiment.end_date,
        )
    ).all()
    judged = [task for task in tasks if task.status != "skipped"]
    done = [task for task in judged if task.status == "done"]
    sample_size = len(judged)
    rate = completion_rate(len(done), len(judged))

    gain = round(experiment.post_mastery - experiment.pre_mastery, 4)
    limitations = [
        "单人前后测，未设置对照组，不能把变化直接归因于该策略。",
        "样本量仅反映本周期任务数与自测次数，样本偏小时结论稳定性有限。",
        "掌握度与得分来自系统自测，存在测量误差与练习效应。",
    ]
    if sample_size < 5:
        verdict = "样本不足：建议延长实验周期或增加任务量后再判断。"
    elif gain > 0:
        verdict = "本周期内呈正向变化，可作为个人策略参考，建议继续观察。"
    else:
        verdict = "本周期收益不明显，建议调整策略或延长实验周期。"

    return {
        "experiment_id": experiment.id,
        "strategy": STRATEGY_LABELS.get(experiment.strategy, experiment.strategy),
        "days": experiment.days,
        "pre_mastery": round(experiment.pre_mastery, 4),
        "post_mastery": round(experiment.post_mastery, 4),
        "mastery_gain": gain,
        "sample_size": sample_size,
        "completion_rate": rate,
        "metrics": metrics_out,
        "limitations": limitations,
        "verdict": verdict,
    }