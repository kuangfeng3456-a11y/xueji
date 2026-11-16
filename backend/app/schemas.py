from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=6, max_length=64)
    nickname: Optional[str] = Field(default=None, max_length=32)
    school: Optional[str] = Field(default=None, max_length=64)
    role: str = Field(default="student", pattern="^(student|teacher|academic)$")

    @field_validator("username")
    @classmethod
    def username_alnum(cls, v: str) -> str:
        if not all(ch.isalnum() or ch in "._-" for ch in v):
            raise ValueError("用户名仅支持字母、数字、下划线、点和中划线")
        return v


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    nickname: str
    school: Optional[str] = None
    role: str = "student"
    is_superadmin: bool = False
    campus_access: bool = False
    created_at: datetime

    @model_validator(mode="after")
    def fill_campus_access(self):
        if self.is_superadmin or self.role in ("teacher", "academic"):
            self.campus_access = True
        return self


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
    session_id: Optional[int] = None


class SessionOut(BaseModel):
    """登录设备列表的一行；current 表示发起本次请求的设备。"""

    id: int
    device: str
    platform: str
    ip: Optional[str] = None
    created_at: datetime
    last_seen_at: datetime
    current: bool = False


class SecurityQuestionOut(BaseModel):
    key: str
    text: str


class SecurityOverview(BaseModel):
    has_questions: bool = False
    questions: List[SecurityQuestionOut] = Field(default_factory=list)
    codes_total: int = 0
    codes_unused: int = 0
    failed_attempts: int = 0
    locked_until: Optional[datetime] = None
    recovery_ready: bool = False


class AnswerItem(BaseModel):
    question_key: str
    answer: str = Field(min_length=1, max_length=64)


class QuestionsSetup(BaseModel):
    """设置密保问题需要再验一次登录密码，避免 token 被盗后直接改密保。"""

    password: str = Field(min_length=1, max_length=64)
    answers: List[AnswerItem] = Field(min_length=2, max_length=2)


class CodeSetup(BaseModel):
    password: str = Field(min_length=1, max_length=64)


class RecoveryOptions(BaseModel):
    methods: List[str] = Field(default_factory=list)
    questions: List[SecurityQuestionOut] = Field(default_factory=list)
    locked_until: Optional[datetime] = None


class RecoveryVerify(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    method: str = Field(pattern="^(questions|code)$")
    answers: List[AnswerItem] = Field(default_factory=list, max_length=2)
    code: Optional[str] = Field(default=None, max_length=32)


class ResetTicket(BaseModel):
    reset_token: str
    expires_in: int
    method: str


class PasswordReset(BaseModel):
    reset_token: str = Field(min_length=10, max_length=128)
    new_password: str = Field(min_length=6, max_length=64)


class ProfileUpdate(BaseModel):
    """账号资料修改：只允许改展示用字段，用户名与密码走各自接口。"""

    nickname: Optional[str] = Field(default=None, max_length=32)
    school: Optional[str] = Field(default=None, max_length=64)


class PasswordChange(BaseModel):
    old_password: str = Field(min_length=1, max_length=64)
    new_password: str = Field(min_length=6, max_length=64)


class GoalCreate(BaseModel):
    exam_name: str = Field(min_length=1, max_length=60)
    exam_date: date
    daily_minutes: int = Field(default=90, ge=20, le=600)
    force_mode: bool = False
    min_daily_minutes: int = Field(default=30, ge=10, le=300)
    camera_required: bool = False

    @field_validator("exam_date")
    @classmethod
    def exam_date_not_past(cls, v: date) -> date:
        if v < date.today():
            raise ValueError("考试日期不能早于今天")
        return v


class GoalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    exam_name: str
    exam_date: date
    daily_minutes: int
    force_mode: bool = False
    min_daily_minutes: int = 30
    camera_required: bool = False
    created_at: datetime
    days_left: int = 0
    knowledge_count: int = 0
    avg_mastery: float = 0.0
    completed_rate: float = 0.0


class KnowledgePointCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    parent_id: Optional[int] = None
    weight: float = Field(default=1.0, ge=0.1, le=5.0)


class KnowledgePointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    parent_id: Optional[int] = None
    weight: float
    mastery: float = 0.0
    next_review_at: Optional[date] = None


class MaterialTextIn(BaseModel):
    filename: str = Field(default="粘贴的资料", max_length=120)
    content: str = Field(min_length=1)


class MaterialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    content: str
    created_at: datetime


class TaskOut(BaseModel):
    id: int
    goal_id: int
    day: date
    title: str
    type: str
    duration_min: int
    status: str
    reason: str
    priority: float
    source: str
    kp_id: Optional[int] = None
    kp_name: Optional[str] = None
    skip_reason: Optional[str] = None
    feedback: Optional[str] = None
    tiers: Optional[Dict[str, int]] = None


class TaskStatusIn(BaseModel):
    status: str
    skip_reason: Optional[str] = Field(default=None, max_length=120)
    feedback: Optional[str] = Field(default=None, max_length=16)

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: str) -> str:
        if v not in ("pending", "done", "skipped"):
            raise ValueError("状态只能是 pending / done / skipped")
        return v

    @field_validator("feedback")
    @classmethod
    def valid_feedback(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("easy", "ok", "hard"):
            raise ValueError("反馈只能是 easy / ok / hard")
        return v


class PlanRequest(BaseModel):
    days: int = Field(default=7, ge=1, le=30)
    regenerate: bool = False


class PlanResult(BaseModel):
    tasks: List[TaskOut]
    summary: str
    days: int
    total_minutes: int


class MistakeCreate(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    user_answer: str = Field(default="", max_length=1000)
    correct_answer: str = Field(default="", max_length=1000)
    kp_id: Optional[int] = None
    source: str = Field(default="text", max_length=16)
    image_url: Optional[str] = Field(default=None, max_length=255)

    @field_validator("source")
    @classmethod
    def valid_source(cls, v: str) -> str:
        if v not in ("text", "photo"):
            raise ValueError("来源只能是 text / photo")
        return v


class MistakeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question: str
    user_answer: str
    correct_answer: str
    category: str
    category_label: str
    suggestion: str
    source: str
    created_at: datetime
    kp_id: Optional[int] = None
    kp_name: Optional[str] = None
    image_url: Optional[str] = None


class ReplanChange(BaseModel):
    kind: str
    detail: str
    task_id: Optional[int] = None


class ReplanResult(BaseModel):
    trigger: str
    changes: List[ReplanChange]
    tasks: List[TaskOut]
    disturbance: float = 0.0
    disturbance_ok: bool = True
    disturbance_rule: str = ""


class MasteryOut(BaseModel):
    kp_id: int
    kp_name: str
    value: float
    next_review_at: Optional[date] = None
    delta_7d: float = 0.0


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    week_start: date
    week_end: date
    completion_rate: float
    mastery_delta: float
    focus: str
    content: str
    created_at: datetime


class RhythmPeriodOut(BaseModel):
    code: str
    label: str
    count: int


class RhythmOut(BaseModel):
    window_days: int = 28
    sampled_tasks: int = 0
    completion_rate: float = 0.0
    done_minutes: int = 0
    avg_delay_days: float = 0.0
    on_time_rate: float = 0.0
    skip_rate: float = 0.0
    overdue_pending: int = 0
    peak_period: Optional[str] = None
    peak_period_label: Optional[str] = None
    periods: List[RhythmPeriodOut] = []
    habit: str = ""
    tasks_per_day: int = 3
    suggestion: str = ""


class AutoAdjustOut(BaseModel):
    adjusted: bool = False
    summary: str = ""
    changes: List[ReplanChange] = []
    days_left: int = 0
    force_mode: bool = False
    mandatory_remaining: int = 0
    sprint_mode: bool = False


class DailyReviewIn(BaseModel):
    energy: int = Field(ge=1, le=5)
    hard_note: str = Field(default="", max_length=500)
    extra_learned: str = Field(default="", max_length=500)
    next_pace: str = Field(default="same", max_length=16)
    day: Optional[date] = None

    @field_validator("next_pace")
    @classmethod
    def valid_pace(cls, v: str) -> str:
        if v not in ("lighter", "same", "heavier"):
            raise ValueError("节奏只能是 lighter / same / heavier")
        return v

    @field_validator("hard_note", "extra_learned")
    @classmethod
    def strip_notes(cls, v: str) -> str:
        return (v or "").strip()


class DailyReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    day: date
    energy: int
    hard_note: str = ""
    extra_learned: str = ""
    next_pace: str = "same"
    suggestion: str = ""
    completed_tasks: int = 0
    planned_minutes: int = 0
    done_minutes: int = 0
    updated_at: datetime


class DashboardOut(BaseModel):
    user: UserOut
    goal: Optional[GoalOut] = None
    today_tasks: List[TaskOut] = []
    today_minutes: int = 0
    streak: int = 0
    mastery: List[MasteryOut] = []
    weak_points: List[MasteryOut] = []
    mistake_count_7d: int = 0
    recent_mistakes: List[MistakeOut] = []
    coach_message: str = ""
    latest_changes: List[ReplanChange] = []
    rhythm: Optional[RhythmOut] = None
    auto_adjust: Optional[AutoAdjustOut] = None
    daily_review: Optional[DailyReviewOut] = None
    loop_steps: List["LoopStepOut"] = []
    week_activity: List["WeekMarkOut"] = []
    next_step: str = ""
    assignments: List["AssignmentBrief"] = []
    server_date: date


class LoopStepOut(BaseModel):
    key: str
    label: str
    done: bool = False
    hint: str = ""


class WeekMarkOut(BaseModel):
    day: date
    done: int = 0


class AssignmentBrief(BaseModel):
    id: int
    title: str
    package_name: str
    hint: str = ""


DashboardOut.model_rebuild()


class ClassCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=120)


class ClassJoin(BaseModel):
    invite_code: str = Field(min_length=4, max_length=16)


class ClassMemberProfile(BaseModel):
    user_id: int
    username: str
    nickname: str
    school: Optional[str] = None
    goal_name: Optional[str] = None
    days_left: Optional[int] = None
    streak: int = 0
    completion_rate: float = 0.0
    avg_mastery: float = 0.0
    weakest: Optional[str] = None
    tasks_7d: int = 0
    done_7d: int = 0


class ClassBrief(BaseModel):
    id: int
    name: str
    description: str
    invite_code: str
    owner_id: int


class ClassWeakPoint(BaseModel):
    name: str
    value: float
    sample_count: int


class ClassDashboardOut(BaseModel):
    class_info: ClassBrief
    member_count: int
    active_members: int
    avg_mastery: float
    avg_completion: float
    weak_points: List[ClassWeakPoint] = []
    members: List[ClassMemberProfile] = []


class BuddyAdd(BaseModel):
    username: str = Field(min_length=3, max_length=32)


class BuddyProfile(BaseModel):
    user_id: int
    username: str
    nickname: str
    school: Optional[str] = None
    goal_name: Optional[str] = None
    days_left: Optional[int] = None
    streak: int = 0
    completion_rate: float = 0.0
    avg_mastery: float = 0.0
    weakest: Optional[str] = None
    tasks_7d: int = 0
    done_7d: int = 0
    is_me: bool = False


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    goal_id: Optional[int] = None


class AskOut(BaseModel):
    answer: str
    source: str
    suggestions: List[str] = []


class PackagePointOut(BaseModel):
    name: str
    parent: Optional[str] = None
    weight: float = 1.0
    kp_id: Optional[int] = None
    mastery: Optional[float] = None
    next_review_at: Optional[date] = None


class SkillPackageOut(BaseModel):
    slug: str
    name: str
    subject: str
    description: str
    tags: List[str] = []
    official: bool = True
    status: str = "approved"
    shared: bool = True
    point_count: int = 0
    applied_count: int = 0
    applied: bool = False
    points: List[str] = []
    point_details: List[PackagePointOut] = []


class ApplyPackageIn(BaseModel):
    goal_id: int


class SkillPackagePointIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    parent: Optional[str] = None
    weight: float = 1.0


class SkillPackageCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    subject: str = Field(default="通用", max_length=32)
    description: str = Field(default="", max_length=255)
    tags: List[str] = []
    points: List[SkillPackagePointIn]


class PhotoUploadOut(BaseModel):
    url: str
    filename: str

class FocusStartIn(BaseModel):
    goal_id: int
    task_id: Optional[int] = None
    planned_minutes: int = Field(default=25, ge=5, le=180)
    camera_enabled: bool = False


class FocusHeartbeatIn(BaseModel):
    leaves: int = Field(default=0, ge=0, le=100)


class FocusFinishIn(BaseModel):
    actual_minutes: Optional[int] = Field(default=None, ge=0, le=600)
    note: str = Field(default="", max_length=200)


class FocusAbortIn(BaseModel):
    reason: str = Field(default="提前结束", max_length=200)


class FocusSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    goal_id: int
    task_id: Optional[int] = None
    task_title: Optional[str] = None
    planned_minutes: int
    actual_minutes: int
    camera_enabled: bool
    status: str
    leaves: int
    snapshots: int
    note: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    remaining_seconds: int = 0
    unlocked: bool = False


class ViolationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    day: date
    kind: str
    detail: str
    created_at: datetime

class HeatmapDayOut(BaseModel):
    day: date
    minutes: int = 0
    done: int = 0
    focus_minutes: int = 0
    level: int = 0


class RadarDimensionOut(BaseModel):
    key: str
    label: str
    value: float = 0.0


class FatigueOut(BaseModel):
    score: int = 0
    level: str = "low"
    factors: List[str] = []
    advice: str = ""
    suggested_tasks_per_day: int = 3


class AchievementOut(BaseModel):
    code: str
    name: str
    description: str
    unlocked: bool = False
    progress: int = 0
    target: int = 1
    unit: str = ""


class AIReportOut(BaseModel):
    text: str
    engine: str = "rule"


class InsightsOut(BaseModel):
    heatmap: List[HeatmapDayOut] = []
    radar: List[RadarDimensionOut] = []
    radar_score: float = 0.0
    fatigue: FatigueOut
    achievements: List[AchievementOut] = []
    streak: int = 0
    total_minutes: int = 0
    active_days: int = 0
    ai_report: Optional[AIReportOut] = None


class ForecastPointOut(BaseModel):
    day: date
    mastery: float


class ForecastScenarioOut(BaseModel):
    label: str
    daily_minutes: int
    projected_mastery: float
    feasible: bool = True


class ForecastOut(BaseModel):
    current_mastery: float = 0.0
    projected_mastery: float = 0.0
    days_left: int = 0
    target_mastery: float = 0.0
    required_daily_minutes: Optional[int] = None
    recommendation: str = ""
    curve: List[ForecastPointOut] = []
    scenarios: List[ForecastScenarioOut] = []
    ai_strategy: str = ""
    ai_engine: str = "rule"


class ApplyForecastIn(BaseModel):
    daily_minutes: int = Field(ge=20, le=600)


class FlashcardOut(BaseModel):
    kp_id: int
    kp_name: str
    parent: Optional[str] = None
    weight: float = 1.0
    mastery: float = 0.0
    next_review_at: Optional[date] = None
    due: bool = False
    reason: str = ""
    retention_now: float = 0.0
    stability_days: float = 1.0
    days_to_target: int = 0


class FlashcardDeckOut(BaseModel):
    cards: List[FlashcardOut] = []
    total: int = 0
    due_count: int = 0


class FlashcardReviewIn(BaseModel):
    remembered: bool


class FlashcardReviewOut(BaseModel):
    kp_id: int
    mastery: float = 0.0
    next_review_at: Optional[date] = None
    stage: int = 0
    remaining_due: int = 0


class FlashcardExplainOut(BaseModel):
    kp_id: int
    explanation: str
    memory_tip: str = ""
    misconception: str = ""
    engine: str = "rule"
    external: Optional[Dict[str, Any]] = None


class QuizGenerateIn(BaseModel):
    kp_id: Optional[int] = None
    count: int = Field(default=3, ge=1, le=6)


class QuizMaterialOut(BaseModel):
    """材料题的材料：阅读正文 / 听力音频脚本。"""

    id: Optional[str] = None
    kind: str = "passage"
    title: Optional[str] = None
    content: Optional[str] = None
    audio_script: Optional[str] = None
    transcript: Optional[str] = None
    word_count: Optional[int] = None


class QuizQuestionOut(BaseModel):
    index: int
    question: str
    options: List[str]
    kp_id: Optional[int] = None
    kp_name: Optional[str] = None
    source: Optional[str] = None
    # 难度 1-4（基础概念 → 直接计算 → 综合应用 → 易错变式），用于展示梯度
    difficulty: Optional[int] = None
    # 阅读/听力题共享的材料；没有材料时为空
    material: Optional[QuizMaterialOut] = None


class QuizGenerateOut(BaseModel):
    quiz_id: str
    engine: str = "rule"
    questions: List[QuizQuestionOut] = []


class QuizSubmitIn(BaseModel):
    quiz_id: str
    answers: List[int] = []


class QuizWrongOut(BaseModel):
    index: int
    question: str
    chosen: str
    correct: str
    explanation: str
    kp_id: Optional[int] = None
    kp_name: Optional[str] = None
    category: str = "concept"
    category_label: str = "概念不清"
    misconception: str = ""
    # 详细解析配套字段：解题步骤、难度、原选项（供判分结果页复盘）
    solution_steps: List[str] = []
    difficulty: Optional[int] = None
    options: Optional[List[str]] = None
    distractor_cause: str = ""


class QuizResultOut(BaseModel):
    score: int
    total: int
    correct: int
    wrong: List[QuizWrongOut] = []
    # 交卷后放开的材料原文（听力此时才有 transcript）
    materials: List[QuizMaterialOut] = []
    replan_changes: List[ReplanChange] = []
    engine: str = "rule"


class RestOut(BaseModel):
    moved: int
    kept: int
    summary: str

class GraphNodeOut(BaseModel):
    kp_id: int
    name: str
    parent: Optional[str] = None
    weight: float = 1.0
    mastery: float = 0.0
    status: str = "normal"
    mistake_count: int = 0
    next_review_at: Optional[date] = None


class GraphEdgeOut(BaseModel):
    source: int
    target: int
    kind: str = "tree"


class GapOut(BaseModel):
    id: int
    kp_id: int
    kp_name: str
    status: str
    evidence: str
    source: str = "rule"


class KnowledgeGraphOut(BaseModel):
    nodes: List[GraphNodeOut] = []
    edges: List[GraphEdgeOut] = []
    candidates: List[GapOut] = []
    verified: List[GapOut] = []
    fixed_count: int = 0


class RiskOut(BaseModel):
    code: str
    title: str
    level: str
    reason: str
    suggestion: str
    before: str = ""
    after: str = ""
    action: str = ""


class ReadinessOut(BaseModel):
    score: int = 0
    level: str = "critical"
    coverage: float = 0.0
    load_ratio: float = 0.0
    gap_count: int = 0
    today_tasks: int = 0
    today_minutes: int = 0
    factors: List[str] = []


class CockpitOut(BaseModel):
    readiness: ReadinessOut
    risks: List[RiskOut] = []
    critical_tasks: List[TaskOut] = []
    gap_count: int = 0
    verified_gap_count: int = 0
    experiment_count: int = 0


class SimulationPlanOut(BaseModel):
    key: str
    label: str
    daily_minutes: int
    projected_mastery: float
    low: float
    high: float
    load_ratio: float
    risk_level: str
    assumptions: List[str] = []


class SimulationOut(BaseModel):
    current_mastery: float = 0.0
    days_left: int = 0
    target_mastery: float = 0.0
    uncertainty: str = ""
    plans: List[SimulationPlanOut] = []
    recommendation: str = ""


class ExperimentCreateIn(BaseModel):
    strategy: str = Field(min_length=1, max_length=32)
    days: int = Field(default=3, ge=1, le=14)


class ExperimentFinishIn(BaseModel):
    immediate_score: int = Field(ge=0, le=100)
    delayed_score: int = Field(ge=0, le=100)
    note: str = Field(default="", max_length=200)


class ExperimentOut(BaseModel):
    id: int
    strategy: str
    status: str
    days: int
    start_date: date
    end_date: date
    pre_mastery: float = 0.0
    post_mastery: float = 0.0
    immediate_score: Optional[int] = None
    delayed_score: Optional[int] = None
    gain: float = 0.0
    note: str = ""


class TwinKnowledgeOut(BaseModel):
    kp_id: int
    name: str
    parent: Optional[str] = None
    weight: float = 1.0
    mastery: float = 0.0
    mistake_count: int = 0
    status: str = "normal"


class TwinMistakeOut(BaseModel):
    category: str
    label: str
    count: int


class TwinTrendOut(BaseModel):
    week_start: date
    done: int = 0
    minutes: int = 0
    completion_rate: float = 0.0


class TwinStrategyOut(BaseModel):
    strategy: str
    label: str
    avg_gain: float = 0.0
    experiments: int = 0


class TwinOut(BaseModel):
    knowledge_matrix: List[TwinKnowledgeOut] = []
    mistake_distribution: List[TwinMistakeOut] = []
    behavior_trend: List[TwinTrendOut] = []
    strategy_ranking: List[TwinStrategyOut] = []

class ProbeGenerateIn(BaseModel):
    kind: str = Field(default="probe", max_length=16)
    kp_id: Optional[int] = None
    count: int = Field(default=1, ge=1, le=3)


class ProbeOut(BaseModel):
    id: int
    kind: str
    kp_id: Optional[int] = None
    kp_name: Optional[str] = None
    question: str
    options: List[str] = []
    status: str = "pending"
    correct: Optional[bool] = None
    explanation: str = ""
    created_at: datetime


class ProbeSubmitIn(BaseModel):
    chosen: int = Field(ge=0, le=3)


class ProbeSubmitOut(BaseModel):
    correct: bool
    explanation: str = ""
    mastery: Optional[float] = None
    resilience: int = 0
    evidence: str = ""


class ThoughtStepOut(BaseModel):
    index: int
    thought: str
    verdict: str
    issue: str = ""


class ThoughtTraceOut(BaseModel):
    mistake_id: int
    error_step: int = 0
    summary: str = ""
    steps: List[ThoughtStepOut] = []
    engine: str = "rule"


class PanelReviewIn(BaseModel):
    topic: str = Field(default="今日学习计划", max_length=120)


class PanelOpinionOut(BaseModel):
    role: str
    view: str
    concern: str
    suggestion: str


class PanelReviewOut(BaseModel):
    id: int
    topic: str
    opinions: List[PanelOpinionOut] = []
    verdict: str = ""
    votes: List[str] = []
    engine: str = "rule"
    created_at: datetime


class FreshnessItemOut(BaseModel):
    material_id: int
    filename: str
    score: int = 0
    level: str = "unknown"
    issues: List[str] = []
    suggestion: str = ""
    engine: str = "rule"


class FreshnessOut(BaseModel):
    items: List[FreshnessItemOut] = []
    scanned_at: Optional[datetime] = None
    overall: int = 0


class CognitiveLoadOut(BaseModel):
    score: int = 0
    level: str = "optimal"
    factors: List[str] = []
    advice: str = ""
    recommended_tasks: int = 3
    recommended_minutes: int = 90


class CognitiveLoadApplyIn(BaseModel):
    action: str = Field(default="auto", max_length=16)


class EvidenceOut(BaseModel):
    id: int
    kind: str
    subject: str
    payload: Dict[str, Any] = {}
    output: str = ""
    engine: str = "rule"
    created_at: datetime

class RiskFactorOut(BaseModel):
    key: str
    label: str
    value: float = 0.0
    weight: float = 0.0
    contribution: float = 0.0


class RiskItemOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int
    kp_id: int
    kp_name: str = ""
    parent: Optional[str] = None
    weight: float = 1.0
    risk_score: float = 0.0
    level: str = "low"
    factors: List[RiskFactorOut] = []
    evidence: Dict[str, Any] = {}
    confidence: float = 0.0
    sample_size: int = 0
    engine: str = "rule"
    model_version: str = ""
    status: str = "active"
    updated_at: Optional[datetime] = None


class RiskForecastOut(BaseModel):
    items: List[RiskItemOut] = []
    active_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    insufficient_count: int = 0
    thresholds: Dict[str, float] = {}
    model_version: str = ""
    weights: Dict[str, float] = {}


class RiskVerifyIn(BaseModel):
    passed: bool = False


class RiskFeedbackIn(BaseModel):
    verdict: str = Field(default="false_positive", max_length=16)


class DebateOpinionOut(BaseModel):
    agent: str
    role: str
    stance: str = ""
    view: str = ""
    evidence: List[str] = []
    concern: str = ""
    suggestion: str = ""


class DebateArbiterOut(BaseModel):
    decision: str = ""
    score: float = 0.0
    rationale: str = ""
    dissent: List[str] = []
    rule_version: str = "arbiter-v2"


class DebateOut(BaseModel):
    run_id: str = ""
    topic: str = ""
    opinions: List[DebateOpinionOut] = []
    arbiter: Optional[DebateArbiterOut] = None
    engine: str = "rule"
    created_at: Optional[datetime] = None


class AgentRunOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    run_id: str
    agent_name: str
    role_order: int = 0
    status: str = "ok"
    engine: str = "rule"
    model_version: str = ""
    prompt_version: str = ""
    latency_ms: int = 0
    output: Dict[str, Any] = {}
    evidence: List[str] = []
    created_at: Optional[datetime] = None


class TwinForecastPointOut(BaseModel):
    horizon_days: int
    projected_mastery: float = 0.0
    low: float = 0.0
    high: float = 0.0
    confidence: float = 0.0
    assumptions: List[str] = []


class TwinForecastOut(BaseModel):
    horizons: List[TwinForecastPointOut] = []
    current_mastery: float = 0.0
    method: str = "rule-decay-v1"
    uncertainty: str = ""
    data_points: int = 0
    insufficient: bool = False


class ExperimentMetricOut(BaseModel):
    metric: str
    value: float = 0.0
    phase: str = "pre"


class ExperimentReportOut(BaseModel):
    experiment_id: int
    strategy: str = ""
    days: int = 0
    pre_mastery: float = 0.0
    post_mastery: float = 0.0
    mastery_gain: float = 0.0
    sample_size: int = 0
    completion_rate: float = 0.0
    metrics: List[ExperimentMetricOut] = []
    limitations: List[str] = []
    verdict: str = ""
