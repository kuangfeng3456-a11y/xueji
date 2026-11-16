from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    nickname: Mapped[str] = mapped_column(String(64), default="同学")
    school: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    # 平台超级管理员：可访问 /api/admin 管理端点与研发内部工具。
    # 只由命令行脚本或现有超管授予，任何自助注册路径都不会写入该字段。
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    goals = relationship("Goal", back_populates="user", cascade="all, delete-orphan")


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    exam_name: Mapped[str] = mapped_column(String(128))
    exam_date: Mapped[date] = mapped_column(Date)
    daily_minutes: Mapped[int] = mapped_column(Integer, default=90)
    force_mode: Mapped[bool] = mapped_column(default=False)
    min_daily_minutes: Mapped[int] = mapped_column(Integer, default=30)
    camera_required: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="goals")
    knowledge_points = relationship("KnowledgePoint", back_populates="goal", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="goal", cascade="all, delete-orphan")


class KnowledgePoint(Base):
    __tablename__ = "knowledge_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("knowledge_points.id"), nullable=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    goal = relationship("Goal", back_populates="knowledge_points")


class Mastery(Base):
    __tablename__ = "mastery"
    __table_args__ = (UniqueConstraint("user_id", "kp_id", name="uq_mastery_user_kp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kp_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"), index=True)
    value: Mapped[float] = mapped_column(Float, default=0.0)
    review_stage: Mapped[int] = mapped_column(Integer, default=0)
    next_review_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MasteryHistory(Base):
    __tablename__ = "mastery_history"
    __table_args__ = (UniqueConstraint("user_id", "kp_id", "day", name="uq_history_user_kp_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kp_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    value: Mapped[float] = mapped_column(Float, default=0.0)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    kp_id: Mapped[Optional[int]] = mapped_column(ForeignKey("knowledge_points.id"), nullable=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    title: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(32), default="study")
    duration_min: Mapped[int] = mapped_column(Integer, default=20)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    reason: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str] = mapped_column(String(32), default="plan")
    skip_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    feedback: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    done_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    goal = relationship("Goal", back_populates="tasks")


class Mistake(Base):
    __tablename__ = "mistakes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    kp_id: Mapped[Optional[int]] = mapped_column(ForeignKey("knowledge_points.id"), nullable=True)
    question: Mapped[str] = mapped_column(Text)
    user_answer: Mapped[str] = mapped_column(Text, default="")
    correct_answer: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(32), default="concept")
    category_label: Mapped[str] = mapped_column(String(32), default="概念不清")
    # B2 干扰项诊断：错题所选干扰项绑定的错因（四类之一），旧数据为空
    distractor_cause: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    suggestion: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(32), default="text")
    image_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("user_id", "goal_id", "week_start", name="uq_report_week"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    week_start: Mapped[date] = mapped_column(Date)
    week_end: Mapped[date] = mapped_column(Date)
    completion_rate: Mapped[float] = mapped_column(Float, default=0.0)
    mastery_delta: Mapped[float] = mapped_column(Float, default=0.0)
    focus: Mapped[str] = mapped_column(String(255), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ReplanLog(Base):
    __tablename__ = "replan_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    trigger: Mapped[str] = mapped_column(String(64))
    changes: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class SchoolClass(Base):
    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(String(255), default="")
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    invite_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ClassMember(Base):
    __tablename__ = "class_members"
    __table_args__ = (UniqueConstraint("class_id", "user_id", name="uq_class_member"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="student")
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Buddy(Base):
    __tablename__ = "buddies"
    __table_args__ = (UniqueConstraint("user_id", "buddy_id", name="uq_buddy_pair"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    buddy_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SkillPackage(Base):
    __tablename__ = "skill_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    subject: Mapped[str] = mapped_column(String(64), default="通用")
    description: Mapped[str] = mapped_column(String(255), default="")
    tags: Mapped[str] = mapped_column(String(255), default="")
    config: Mapped[str] = mapped_column(Text, default="{}")
    official: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class FocusSession(Base):
    __tablename__ = "focus_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    planned_minutes: Mapped[int] = mapped_column(Integer, default=25)
    actual_minutes: Mapped[int] = mapped_column(Integer, default=0)
    camera_enabled: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(16), default="active")
    leaves: Mapped[int] = mapped_column(Integer, default=0)
    snapshots: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(String(255), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Violation(Base):
    __tablename__ = "violations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(32), default="abort")
    detail: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class KnowledgeDependency(Base):
    __tablename__ = "knowledge_dependencies"
    __table_args__ = (UniqueConstraint("goal_id", "from_kp_id", "to_kp_id", name="uq_dependency"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    from_kp_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"), index=True)
    to_kp_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"), index=True)
    source: Mapped[str] = mapped_column(String(16), default="tree")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class KnowledgeGap(Base):
    __tablename__ = "knowledge_gaps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    kp_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="candidate")
    evidence: Mapped[str] = mapped_column(String(255), default="")
    source: Mapped[str] = mapped_column(String(16), default="rule")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class LearningExperiment(Base):
    __tablename__ = "learning_experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    strategy: Mapped[str] = mapped_column(String(32), default="practice")
    status: Mapped[str] = mapped_column(String(16), default="running")
    days: Mapped[int] = mapped_column(Integer, default=3)
    start_date: Mapped[date] = mapped_column(Date, default=date.today)
    end_date: Mapped[date] = mapped_column(Date, default=date.today)
    pre_mastery: Mapped[float] = mapped_column(Float, default=0.0)
    post_mastery: Mapped[float] = mapped_column(Float, default=0.0)
    immediate_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    delayed_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class ProbeItem(Base):
    __tablename__ = "probe_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    kp_id: Mapped[Optional[int]] = mapped_column(ForeignKey("knowledge_points.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(16), default="probe")
    question: Mapped[str] = mapped_column(Text)
    options: Mapped[str] = mapped_column(Text, default="[]")
    answer_index: Mapped[int] = mapped_column(Integer, default=0)
    explanation: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    chosen_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    correct: Mapped[Optional[bool]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    answered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ThoughtTrace(Base):
    __tablename__ = "thought_traces"
    __table_args__ = (UniqueConstraint("mistake_id", name="uq_trace_mistake"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    mistake_id: Mapped[int] = mapped_column(ForeignKey("mistakes.id"), index=True)
    steps: Mapped[str] = mapped_column(Text, default="[]")
    error_step: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str] = mapped_column(Text, default="")
    engine: Mapped[str] = mapped_column(String(16), default="rule")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PanelReview(Base):
    __tablename__ = "panel_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    topic: Mapped[str] = mapped_column(String(120), default="今日学习计划")
    opinions: Mapped[str] = mapped_column(Text, default="[]")
    verdict: Mapped[str] = mapped_column(Text, default="")
    votes: Mapped[str] = mapped_column(Text, default="[]")
    engine: Mapped[str] = mapped_column(String(16), default="rule")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FreshnessReport(Base):
    __tablename__ = "freshness_reports"
    __table_args__ = (UniqueConstraint("material_id", name="uq_freshness_material"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), index=True)
    score: Mapped[int] = mapped_column(Integer, default=60)
    issues: Mapped[str] = mapped_column(Text, default="[]")
    suggestion: Mapped[str] = mapped_column(Text, default="")
    engine: Mapped[str] = mapped_column(String(16), default="rule")
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Evidence(Base):
    __tablename__ = "evidence_chain"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="decision")
    subject: Mapped[str] = mapped_column(String(120), default="")
    payload: Mapped[str] = mapped_column(Text, default="{}")
    output: Mapped[str] = mapped_column(Text, default="")
    engine: Mapped[str] = mapped_column(String(16), default="rule")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class PsychologyAssessment(Base):
    __tablename__ = "psychology_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    scale: Mapped[str] = mapped_column(String(32), default="phq9")
    score: Mapped[int] = mapped_column(Integer, default=0)
    max_score: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[str] = mapped_column(String(64), default="")
    answers: Mapped[str] = mapped_column(Text, default="[]")
    summary: Mapped[str] = mapped_column(Text, default="")
    engine: Mapped[str] = mapped_column(String(16), default="rule")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class RiskPrediction(Base):
    """知识漏洞早期预警：可复算风险分 + 因素贡献 + 证据 + 置信度。"""

    __tablename__ = "risk_predictions"
    __table_args__ = (UniqueConstraint("user_id", "goal_id", "kp_id", name="uq_risk_user_goal_kp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    kp_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"), index=True)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    level: Mapped[str] = mapped_column(String(16), default="low")
    factors: Mapped[str] = mapped_column(Text, default="[]")
    evidence: Mapped[str] = mapped_column(Text, default="{}")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    engine: Mapped[str] = mapped_column(String(16), default="rule")
    model_version: Mapped[str] = mapped_column(String(32), default="rule-risk-v1")
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AgentRun(Base):
    """多智能体运行审计：每个角色的输入、输出、证据、耗时与版本。"""

    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(48), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    agent_name: Mapped[str] = mapped_column(String(32), default="planner")
    role_order: Mapped[int] = mapped_column(Integer, default=0)
    input_ref: Mapped[str] = mapped_column(String(255), default="")
    output: Mapped[str] = mapped_column(Text, default="{}")
    evidence: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(16), default="ok")
    engine: Mapped[str] = mapped_column(String(16), default="rule")
    model_version: Mapped[str] = mapped_column(String(64), default="")
    prompt_version: Mapped[str] = mapped_column(String(32), default="panel-v2")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ExperimentMetric(Base):
    """策略实验指标：前测、过程、后测的可复算指标。"""

    __tablename__ = "experiment_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    experiment_id: Mapped[int] = mapped_column(
        ForeignKey("learning_experiments.id"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    metric: Mapped[str] = mapped_column(String(32), default="mastery")
    value: Mapped[float] = mapped_column(Float, default=0.0)
    phase: Mapped[str] = mapped_column(String(16), default="pre")
    note: Mapped[str] = mapped_column(String(255), default="")
    measured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class LearningEvent(Base):
    """统一学习事件流：答题、复习、任务、资料、提示等均可追溯。"""

    __tablename__ = "learning_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(32), default="answer", index=True)
    kp_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("knowledge_points.id"), nullable=True, index=True
    )
    payload: Mapped[str] = mapped_column(Text, default="{}")
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class QuizAttempt(Base):
    """随堂测答题记录：保留真实历史与汇总，避免只存在于浏览器会话中。"""

    __tablename__ = "quiz_attempts"
    __table_args__ = (
        UniqueConstraint("quiz_id", name="uq_quiz_attempt_quiz_id"),
        Index("ix_quiz_attempt_user_goal_created", "user_id", "goal_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quiz_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    score: Mapped[int] = mapped_column(Integer, default=0)
    correct: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    wrong_count: Mapped[int] = mapped_column(Integer, default=0)
    engine: Mapped[str] = mapped_column(String(16), default="rule")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class DocumentChunk(Base):
    """资料切块索引：为回答提供可定位到文件名与段落的真实引用。"""

    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    page_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    chunk_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class ConsentRecord(Base):
    """数据授权记录：学生可授权/撤销家长查看成长摘要。"""

    __tablename__ = "consent_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    scope: Mapped[str] = mapped_column(String(32), default="parent_report")
    granted: Mapped[bool] = mapped_column(default=False)
    granted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class EvalRun(Base):
    """AI 可靠性评测运行记录：正确率、延迟、失败率与模型版本。"""

    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    run_id: Mapped[str] = mapped_column(String(32), index=True)
    cases: Mapped[int] = mapped_column(Integer, default=0)
    correct: Mapped[int] = mapped_column(Integer, default=0)
    accuracy: Mapped[float] = mapped_column(Float, default=0.0)
    avg_latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    engine: Mapped[str] = mapped_column(String(16), default="rule")
    model_version: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class KnowledgeEdge(Base):
    """显式知识关系：先修、易混淆与相关，供图谱查询与推理使用。"""

    __tablename__ = "knowledge_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    from_kp_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id"), index=True
    )
    to_kp_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"), index=True)
    relation_type: Mapped[str] = mapped_column(String(16), default="prerequisite")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LsvSnapshot(Base):
    """学习者状态向量快照（文档 2.3）：每次有实质变化落一份，带 hash 可复算。"""

    __tablename__ = "lsv_snapshots"
    __table_args__ = (Index("ix_lsv_snapshots_user_as_of", "user_id", "as_of"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    as_of: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    lsv_version: Mapped[str] = mapped_column(String(16), default="2.0")
    payload: Mapped[str] = mapped_column(Text, default="{}")
    hash: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PromptVersion(Base):
    """提示词版本注册表（文档 6.6 / 附录 B）：正文哈希变化即视为新版本内容。"""

    __tablename__ = "prompt_versions"
    __table_args__ = (UniqueConstraint("prompt_id", "version", name="uq_prompt_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prompt_id: Mapped[str] = mapped_column(String(16), index=True)
    version: Mapped[str] = mapped_column(String(16))
    hash: Mapped[str] = mapped_column(String(64), default="")
    tier: Mapped[str] = mapped_column(String(16), default="")
    system_text: Mapped[str] = mapped_column(Text, default="")
    user_template: Mapped[str] = mapped_column(Text, default="")
    output_contract: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LlmCall(Base):
    """模型调用审计（文档 7.4）：渠道、模型、档位、token、延迟、校验与兜底标记。"""

    __tablename__ = "llm_calls"
    __table_args__ = (Index("ix_llm_calls_trace", "trace_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    prompt_id: Mapped[str] = mapped_column(String(16), default="", index=True)
    prompt_version: Mapped[str] = mapped_column(String(16), default="")
    prompt_hash: Mapped[str] = mapped_column(String(64), default="")
    model: Mapped[str] = mapped_column(String(64), default="")
    route: Mapped[str] = mapped_column(String(16), default="primary")
    tier: Mapped[str] = mapped_column(String(16), default="")
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    repaired: Mapped[bool] = mapped_column(Boolean, default=False)
    fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    validator_result: Mapped[str] = mapped_column(String(32), default="")
    error: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ReviewCard(Base):
    """记忆稳定度与复习计划（文档 5.2 / 附录 B）：按知识点维护 S、遗忘次数与下次复习日。"""

    __tablename__ = "review_cards"
    __table_args__ = (
        UniqueConstraint("user_id", "kp_id", name="uq_review_card_user_kp"),
        Index("ix_review_cards_next", "user_id", "next_review"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    kp_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"), index=True)
    stability: Mapped[float] = mapped_column(Float, default=1.0)
    difficulty: Mapped[float] = mapped_column(Float, default=0.3)
    lapses: Mapped[int] = mapped_column(Integer, default=0)
    reps: Mapped[int] = mapped_column(Integer, default=0)
    last_review: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    next_review: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class TaskVariant(Base):
    """任务三档版本（文档 5.4 / 附录 B）：标准 / 精简 / 最小，落库便于复算与回看。"""

    __tablename__ = "task_variants"
    __table_args__ = (UniqueConstraint("task_id", "tier", name="uq_task_variant"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    tier: Mapped[str] = mapped_column(String(16), default="standard")
    minutes: Mapped[int] = mapped_column(Integer, default=0)
    steps: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EventLog(Base):
    """事件日志（文档 7.5 / 附录 B）：event_id 幂等，记录处理器，供重放与审计。"""

    __tablename__ = "events"
    __table_args__ = (Index("ix_events_type_created", "type", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    type: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    goal_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    payload: Mapped[str] = mapped_column(Text, default="{}")
    handled_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EvalCase(Base):
    """提示词评测用例（文档 6.6 / 附录 B）：常规 / 边界 / 对抗三类标签。"""

    __tablename__ = "eval_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    prompt_id: Mapped[str] = mapped_column(String(16), default="", index=True)
    input: Mapped[str] = mapped_column(Text, default="")
    expected: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(String(64), default="normal")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SafetyEvent(Base):
    """安全事件（文档 9.3 / 附录 B）：只记类型与处置，不存对话原文。"""

    __tablename__ = "safety_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_hash: Mapped[str] = mapped_column(String(32), default="", index=True)
    type: Mapped[str] = mapped_column(String(16), default="injection")
    level: Mapped[str] = mapped_column(String(16), default="medium")
    action: Mapped[str] = mapped_column(String(64), default="flagged")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class VocabReview(Base):
    """词汇单词卡学习记录：逐词留痕「认识 / 模糊 / 不认识」，用于进度与掌握度汇总。"""

    __tablename__ = "vocab_reviews"
    __table_args__ = (Index("ix_vocab_reviews_user_goal", "user_id", "goal_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    kp_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"), index=True)
    word: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(16), default="known")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FeynmanSession(Base):
    """费曼检验场：把知识点讲给 AI 听，对照「预置要点」测覆盖率的讲解会话。

    要点清单在开讲前就存在服务端、不下发，评分只做「讲没讲到」的确定性覆盖判定，
    模型只辅助判命中，不参与「讲得好不好」的自由评价——防止被用户话术带偏。
    """

    __tablename__ = "feynman_sessions"
    __table_args__ = (Index("ix_feynman_user_goal", "user_id", "goal_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    kp_id: Mapped[Optional[int]] = mapped_column(ForeignKey("knowledge_points.id"), nullable=True)
    kp_name: Mapped[str] = mapped_column(String(128), default="")
    pick_reason: Mapped[str] = mapped_column(Text, default="")
    # JSON：[{"term":"定义域","hint":"讲清楚它成立的前提"}]，不下发给前端
    points: Mapped[str] = mapped_column(Text, default="[]")
    points_engine: Mapped[str] = mapped_column(String(8), default="rule")
    speech: Mapped[str] = mapped_column(Text, default="")
    speech_mode: Mapped[str] = mapped_column(String(8), default="text")
    coverage: Mapped[float] = mapped_column(Float, default=0.0)
    covered: Mapped[str] = mapped_column(Text, default="[]")
    missed: Mapped[str] = mapped_column(Text, default="[]")
    suspects: Mapped[str] = mapped_column(Text, default="[]")
    insight: Mapped[str] = mapped_column(Text, default="")
    engine: Mapped[str] = mapped_column(String(8), default="rule")
    submitted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ReverseTask(Base):
    """反向判卷：AI 扮演犯错的学生，用户当老师批改。

    错误（哪一步、哪类错、正确写法、必须提到的词）在出题时写死，
    批改结果按规则算分，模型只出题不判分。
    """

    __tablename__ = "reverse_tasks"
    __table_args__ = (Index("ix_reverse_user_goal", "user_id", "goal_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    kp_id: Mapped[Optional[int]] = mapped_column(ForeignKey("knowledge_points.id"), nullable=True)
    kp_name: Mapped[str] = mapped_column(String(128), default="")
    question: Mapped[str] = mapped_column(Text, default="")
    # JSON：[{"no":1,"text":"..."}]
    steps: Mapped[str] = mapped_column(Text, default="[]")
    error_step: Mapped[int] = mapped_column(Integer, default=1)
    error_type: Mapped[str] = mapped_column(String(16), default="概念不清")
    correct_step: Mapped[str] = mapped_column(Text, default="")
    key_terms: Mapped[str] = mapped_column(Text, default="[]")
    why: Mapped[str] = mapped_column(Text, default="")
    answer: Mapped[str] = mapped_column(Text, default="")
    engine: Mapped[str] = mapped_column(String(8), default="rule")
    picked_step: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    picked_type: Mapped[str] = mapped_column(String(16), default="")
    fix_text: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    detail: Mapped[str] = mapped_column(Text, default="{}")
    graded: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ImmuneDrill(Base):
    """错误免疫：把「反复犯的同一类错」当抗原来练。

    诱饵选项与正确选项在出题时写死（trap_key / correct_key），
    作答只做键比对，判定完全不经过模型。
    """

    __tablename__ = "immune_drills"
    __table_args__ = (Index("ix_immune_user_goal", "user_id", "goal_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    kp_id: Mapped[Optional[int]] = mapped_column(ForeignKey("knowledge_points.id"), nullable=True)
    kp_name: Mapped[str] = mapped_column(String(128), default="")
    fingerprint: Mapped[str] = mapped_column(String(128), default="", index=True)
    cause: Mapped[str] = mapped_column(String(16), default="概念不清")
    board: Mapped[str] = mapped_column(String(128), default="")
    question: Mapped[str] = mapped_column(Text, default="")
    # JSON：[{"key":"A","text":"..."}]
    options: Mapped[str] = mapped_column(Text, default="[]")
    trap_key: Mapped[str] = mapped_column(String(4), default="")
    correct_key: Mapped[str] = mapped_column(String(4), default="")
    trap_reason: Mapped[str] = mapped_column(Text, default="")
    why: Mapped[str] = mapped_column(Text, default="")
    origin_mistake_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    engine: Mapped[str] = mapped_column(String(8), default="rule")
    picked: Mapped[str] = mapped_column(String(4), default="")
    outcome: Mapped[str] = mapped_column(String(8), default="")
    answered: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ExamPrepStage(Base):
    """备考方案的一个阶段（基础/强化/冲刺/考前）。

    阶段是「整套方案」的一级单位：每个阶段有起止日期、目标保持率、
    以及一次阶段考试（Stage Exam）的真实成绩。
    """

    __tablename__ = "exam_prep_stages"
    __table_args__ = (Index("ix_exam_prep_user_goal", "user_id", "goal_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    phase: Mapped[str] = mapped_column(String(24), default="foundation")
    title: Mapped[str] = mapped_column(String(128), default="")
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date] = mapped_column(Date, index=True)
    day_count: Mapped[int] = mapped_column(Integer, default=0)
    ratio: Mapped[str] = mapped_column(String(64), default="")
    target_retention: Mapped[float] = mapped_column(Float, default=0.85)
    # 阶段考试真实成绩
    exam_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    exam_total: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    exam_passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    exam_engine: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    exam_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ExamPrepDay(Base):
    """备考方案的一天，含上午/下午/晚上三个时段。

    每天的三个时段是「网课式」课表的最小单元：每个时段绑定具体知识点、
    真实视频课程、随堂测与阶段考试标记。
    """

    __tablename__ = "exam_prep_days"
    __table_args__ = (
        Index("ix_exam_prep_day_user_goal", "user_id", "goal_id"),
        UniqueConstraint("user_id", "goal_id", "day_index", name="uq_exam_prep_day_index"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    stage_id: Mapped[Optional[int]] = mapped_column(ForeignKey("exam_prep_stages.id"), nullable=True)
    day_index: Mapped[int] = mapped_column(Integer, default=1)
    day_date: Mapped[date] = mapped_column(Date, index=True)
    phase: Mapped[str] = mapped_column(String(24), default="foundation")
    # JSON：[{"slot":"morning","title":"","focus":"","minutes":90,"kp_ids":[1,2],
    #        "video":{"bvid":"","title":"","url":"","author":"","duration":""},
    #        "engine":"live","status":"pending"}]
    slots: Mapped[str] = mapped_column(Text, default="[]")
    # 阶段考试日：当天晚上安排阶段模考
    has_stage_exam: Mapped[bool] = mapped_column(Boolean, default=False)
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ===== 账号安全：多设备会话与自助找回 =====


class AuthSession(Base):
    """一次登录 = 一条会话 = 一台设备。

    JWT 里带 jti，服务端按 jti 查这张表：撤销某行即让对应 token 立刻失效，
    这样「退出其他设备」和「改密后其他设备掉线」才有真实效果，
    而不是只在前端删掉本地 token。
    """

    __tablename__ = "auth_sessions"
    __table_args__ = (Index("ix_auth_sessions_user_revoked", "user_id", "revoked_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    device: Mapped[str] = mapped_column(String(64), default="未知设备")
    platform: Mapped[str] = mapped_column(String(16), default="web")
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_reason: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)


class RecoveryProfile(Base):
    """密保问题（两个）与验证失败限流计数。

    没有邮件/短信通道时，密保问题是唯一可自助验证「你是本人」的凭据；
    答案只存 pbkdf2 哈希，且做归一化（忽略大小写与空格），
    避免用户因为多打一个空格就永远找不回账号。
    """

    __tablename__ = "recovery_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    question1_key: Mapped[str] = mapped_column(String(32))
    answer1_hash: Mapped[str] = mapped_column(String(255))
    question2_key: Mapped[str] = mapped_column(String(32))
    answer2_hash: Mapped[str] = mapped_column(String(255))
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RecoveryCode(Base):
    """一次性恢复码。明文只在生成时返回一次，库里只有 sha256。"""

    __tablename__ = "recovery_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class PasswordResetTicket(Base):
    """验证通过后签发的一次性重置票据，10 分钟有效，用完即作废。"""

    __tablename__ = "password_reset_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    method: Mapped[str] = mapped_column(String(16), default="questions")
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Commitment(Base):
    """C3 实施意图微承诺：「如果—那么」式承诺，次日回看是否履行。

    文档 4.4：教练生成「如果—那么」承诺；次日回看是否履行，沉淀为习惯数据。
    指标口径：承诺履行率；与当日完成率的相关性。
    """

    __tablename__ = "commitments"
    __table_args__ = (
        Index("ix_commitment_user_goal_due", "user_id", "goal_id", "due_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    if_condition: Mapped[str] = mapped_column(String(255))
    then_action: Mapped[str] = mapped_column(String(255))
    due_date: Mapped[date] = mapped_column(Date, index=True)
    # pending 待履行 / fulfilled 已履行 / missed 已过期未履行 / cancelled 已取消
    status: Mapped[str] = mapped_column(String(16), default="pending")
    # coach 教练建议生成 / user 用户自建
    source: Mapped[str] = mapped_column(String(16), default="coach")
    checkin_note: Mapped[str] = mapped_column(String(255), default="")
    fulfilled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class DailyReview(Base):
    """当日学习复盘：精力、难点与额外收获，供次日排任务参考。"""

    __tablename__ = "daily_reviews"
    __table_args__ = (
        UniqueConstraint("user_id", "goal_id", "day", name="uq_daily_review_user_goal_day"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    energy: Mapped[int] = mapped_column(Integer, default=3)
    hard_note: Mapped[str] = mapped_column(Text, default="")
    extra_learned: Mapped[str] = mapped_column(Text, default="")
    # lighter 放缓 / same 保持 / heavier 加码
    next_pace: Mapped[str] = mapped_column(String(16), default="same")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
