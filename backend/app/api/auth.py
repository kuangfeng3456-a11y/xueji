import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from ..cache import cache
from ..database import get_db
from ..deps import current_session, get_current_user
from ..models import (
    AuthSession,
    Goal,
    KnowledgePoint,
    Mastery,
    MasteryHistory,
    Material,
    Mistake,
    PasswordResetTicket,
    QuizAttempt,
    RecoveryCode,
    RecoveryProfile,
    ReplanLog,
    Report,
    Task,
    User,
)
from ..schemas import (
    CodeSetup,
    PasswordChange,
    PasswordReset,
    ProfileUpdate,
    QuestionsSetup,
    RecoveryOptions,
    RecoveryVerify,
    ResetTicket,
    SecurityOverview,
    SessionOut,
    Token,
    UserCreate,
    UserLogin,
    UserOut,
)
from ..security import hash_password, verify_password
from ..services import account_security as guard

router = APIRouter(prefix="/auth", tags=["认证与数据隐私"])


def _throttle(request: Request, bucket: str, limit: int, window: int) -> None:
    """按 IP 限流，避免找回接口被用来批量枚举账号。"""
    ip = guard.client_ip(request) or "unknown"
    count = cache.incr(f"throttle:{bucket}:{ip}", ttl=window)
    if count > limit:
        raise HTTPException(status_code=429, detail="操作过于频繁，请稍后再试")


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(
    payload: UserCreate, request: Request, db: OrmSession = Depends(get_db)
) -> Token:
    exists = db.scalar(select(User).where(User.username == payload.username))
    if exists:
        raise HTTPException(status_code=400, detail="该用户名已被注册")
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        nickname=payload.nickname or payload.username,
        school=payload.school,
        role=payload.role or "student",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token, session = guard.open_session(db, user, request)
    return Token(
        access_token=token, user=UserOut.model_validate(user), session_id=session.id
    )


@router.post("/login", response_model=Token)
def login(payload: UserLogin, request: Request, db: OrmSession = Depends(get_db)) -> Token:
    user = db.scalar(select(User).where(User.username == payload.username))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=400, detail="用户名或密码错误")
    token, session = guard.open_session(db, user, request)
    return Token(
        access_token=token, user=UserOut.model_validate(user), session_id=session.id
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(user: User = Depends(get_current_user), db: OrmSession = Depends(get_db)) -> None:
    """退出当前设备：服务端撤销会话，token 立刻作废而不只是前端删除。"""
    session = current_session(user)
    if session is not None:
        guard.revoke_session(db, session, "logout")
        db.commit()


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut)
def update_me(
    payload: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
) -> UserOut:
    """修改昵称与学校。用户名不可改，密码走 /auth/me/password。"""
    if payload.nickname is not None:
        nickname = payload.nickname.strip()
        if not nickname:
            raise HTTPException(status_code=400, detail="昵称不能为空")
        user.nickname = nickname
    if payload.school is not None:
        user.school = payload.school.strip() or None
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    user: User = Depends(get_current_user), db: OrmSession = Depends(get_db)
) -> list[SessionOut]:
    """当前账号在所有设备上的登录状态，用于「哪些设备还登着」。"""
    guard.purge_expired_sessions(db, user.id)
    mine = current_session(user)
    rows = guard.active_sessions(db, user.id)
    return [
        SessionOut(
            id=row.id,
            device=row.device,
            platform=row.platform,
            ip=row.ip,
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
            current=bool(mine and row.id == mine.id),
        )
        for row in rows
    ]


@router.delete("/sessions/{session_id}")
def revoke_session_by_id(
    session_id: int,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
) -> dict:
    row = db.get(AuthSession, session_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="该登录设备不存在")
    mine = current_session(user)
    guard.revoke_session(db, row, "user_revoked")
    db.commit()
    return {"revoked": 1, "current": bool(mine and mine.id == row.id)}


@router.post("/sessions/revoke-others")
def revoke_others(
    user: User = Depends(get_current_user), db: OrmSession = Depends(get_db)
) -> dict:
    mine = current_session(user)
    keep = mine.jti if mine else ""
    count = guard.revoke_other_sessions(db, user.id, keep, reason="revoke_others")
    return {"revoked": count}


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChange,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
) -> None:
    """改密码：校验原密码，并让其他设备立刻掉线，只保留当前设备。"""
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="原密码不正确")
    if payload.old_password == payload.new_password:
        raise HTTPException(status_code=400, detail="新密码不能与原密码相同")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    mine = current_session(user)
    guard.revoke_other_sessions(db, user.id, mine.jti if mine else "", reason="password_changed")


# ===== 账号找回配置（登录后） =====


def _profile_of(db: OrmSession, user_id: int) -> Optional[RecoveryProfile]:
    return db.scalar(select(RecoveryProfile).where(RecoveryProfile.user_id == user_id))


def _overview(db: OrmSession, user: User) -> SecurityOverview:
    profile = _profile_of(db, user.id)
    codes = db.scalars(select(RecoveryCode).where(RecoveryCode.user_id == user.id)).all()
    unused = [code for code in codes if code.used_at is None]
    questions = []
    if profile:
        for key in (profile.question1_key, profile.question2_key):
            questions.append({"key": key, "text": guard.QUESTION_TEXT.get(key, key)})
    return SecurityOverview(
        has_questions=bool(profile),
        questions=questions,
        codes_total=len(codes),
        codes_unused=len(unused),
        failed_attempts=profile.fail_count if profile else 0,
        locked_until=profile.locked_until if profile else None,
        recovery_ready=bool(profile) or bool(unused),
    )


@router.get("/security", response_model=SecurityOverview)
def security_overview(
    user: User = Depends(get_current_user), db: OrmSession = Depends(get_db)
) -> SecurityOverview:
    return _overview(db, user)


@router.get("/security/questions", response_model=list[dict])
def question_bank() -> list[dict]:
    return guard.QUESTIONS


@router.put("/security/questions", response_model=SecurityOverview)
def set_questions(
    payload: QuestionsSetup,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
) -> SecurityOverview:
    """设置/重置两个密保问题。必须再验一次密码，防止 token 被盗后被永久锁号。"""
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=400, detail="登录密码不正确")
    keys = [item.question_key for item in payload.answers]
    if len(set(keys)) != 2:
        raise HTTPException(status_code=400, detail="请选择两个不同的问题")
    if any(key not in guard.QUESTION_TEXT for key in keys):
        raise HTTPException(status_code=400, detail="问题选项不存在")
    normalized = [guard.hash_recovery_answer(item.answer) for item in payload.answers]
    if any(guard.normalize_answer(item.answer) == "" for item in payload.answers):
        raise HTTPException(status_code=400, detail="答案不能为空")

    profile = _profile_of(db, user.id)
    if profile is None:
        profile = RecoveryProfile(user_id=user.id)
        db.add(profile)
    profile.question1_key, profile.question2_key = keys[0], keys[1]
    profile.answer1_hash, profile.answer2_hash = normalized[0], normalized[1]
    profile.fail_count = 0
    profile.locked_until = None
    profile.updated_at = datetime.utcnow()
    db.commit()
    return _overview(db, user)


@router.post("/security/codes")
def issue_codes(
    payload: CodeSetup,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
) -> dict:
    """生成一批新的恢复码：旧的未使用码全部作废，明文只在这里返回一次。"""
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=400, detail="登录密码不正确")
    for row in db.scalars(select(RecoveryCode).where(RecoveryCode.user_id == user.id)).all():
        db.delete(row)
    plain = guard.generate_recovery_codes()
    for code in plain:
        db.add(RecoveryCode(user_id=user.id, code_hash=guard.hash_code(guard.normalize_code(code))))
    db.commit()
    return {
        "codes": plain,
        "total": len(plain),
        "note": "每枚恢复码只能使用一次，请立即保存到安全的地方；离开本页后将无法再次查看。",
    }


# ===== 自助找回（未登录） =====


@router.get("/recovery/options", response_model=RecoveryOptions)
def recovery_options(username: str, request: Request, db: OrmSession = Depends(get_db)) -> RecoveryOptions:
    """返回该账号可用的找回方式与密保问题题面。

    无邮件/短信通道时，题面必须给到前端才能作答，这是密保方案的固有取舍；
    因此按 IP 限流，避免被批量枚举。
    """
    _throttle(request, "recovery_options", limit=120, window=300)
    user = db.scalar(select(User).where(User.username == username.strip()))
    if not user:
        return RecoveryOptions(methods=[], questions=[])
    profile = _profile_of(db, user.id)
    methods: list[str] = []
    questions: list[dict] = []
    locked_until = None
    if profile:
        methods.append("questions")
        questions = [
            {"key": key, "text": guard.QUESTION_TEXT.get(key, key)}
            for key in (profile.question1_key, profile.question2_key)
        ]
        if profile.locked_until and profile.locked_until > datetime.utcnow():
            locked_until = profile.locked_until
    has_codes = db.scalar(
        select(RecoveryCode.id).where(
            RecoveryCode.user_id == user.id, RecoveryCode.used_at.is_(None)
        )
    )
    if has_codes:
        methods.append("code")
    return RecoveryOptions(methods=methods, questions=questions, locked_until=locked_until)


@router.post("/recovery/verify", response_model=ResetTicket)
def recovery_verify(
    payload: RecoveryVerify, request: Request, db: OrmSession = Depends(get_db)
) -> ResetTicket:
    _throttle(request, "recovery_verify", limit=100, window=600)
    user = db.scalar(select(User).where(User.username == payload.username.strip()))
    if not user:
        # 不暴露账号是否存在：与「答案错误」返回同一句提示
        raise HTTPException(status_code=400, detail="验证信息不正确")

    profile = _profile_of(db, user.id)
    now = datetime.utcnow()
    if profile and profile.locked_until and profile.locked_until > now:
        minutes = max(1, int((profile.locked_until - now).total_seconds() // 60) + 1)
        raise HTTPException(status_code=429, detail=f"验证失败次数过多，请 {minutes} 分钟后再试")

    passed = False
    if payload.method == "questions":
        if not profile:
            raise HTTPException(status_code=400, detail="该账号未设置密保问题，请改用恢复码")
        submitted = {item.question_key: item.answer for item in payload.answers}
        expected = {profile.question1_key: profile.answer1_hash, profile.question2_key: profile.answer2_hash}
        passed = len(submitted) == 2 and all(
            key in submitted and guard.verify_recovery_answer(submitted[key], digest)
            for key, digest in expected.items()
        )
    else:
        normalized = guard.normalize_code(payload.code)
        if normalized:
            row = db.scalar(
                select(RecoveryCode).where(
                    RecoveryCode.user_id == user.id,
                    RecoveryCode.code_hash == guard.hash_code(normalized),
                    RecoveryCode.used_at.is_(None),
                )
            )
            passed = row is not None
            if row is not None:
                row.used_at = now

    if not passed:
        if profile is not None:
            profile.fail_count = (profile.fail_count or 0) + 1
            if profile.fail_count >= guard.MAX_FAIL_COUNT:
                profile.locked_until = now + timedelta(minutes=guard.LOCK_MINUTES)
                profile.fail_count = 0
            db.commit()
        raise HTTPException(status_code=400, detail="验证信息不正确")

    if profile is not None:
        profile.fail_count = 0
        profile.locked_until = None

    # 作废该用户此前未使用的票据，保证同一时间只有一枚有效
    for old in db.scalars(
        select(PasswordResetTicket).where(
            PasswordResetTicket.user_id == user.id, PasswordResetTicket.used_at.is_(None)
        )
    ).all():
        old.used_at = now

    token, digest = guard.new_reset_ticket()
    db.add(
        PasswordResetTicket(
            user_id=user.id,
            token_hash=digest,
            method=payload.method,
            expires_at=now + timedelta(minutes=guard.RESET_TICKET_MINUTES),
        )
    )
    db.commit()
    return ResetTicket(
        reset_token=token, expires_in=guard.RESET_TICKET_MINUTES * 60, method=payload.method
    )


@router.post("/recovery/reset", status_code=status.HTTP_204_NO_CONTENT)
def recovery_reset(payload: PasswordReset, db: OrmSession = Depends(get_db)) -> None:
    """凭票据重设密码；重设后所有设备退出登录，包括发起找回的这台。"""
    digest = guard.hash_ticket(payload.reset_token)
    ticket = db.scalar(select(PasswordResetTicket).where(PasswordResetTicket.token_hash == digest))
    now = datetime.utcnow()
    if not ticket or ticket.used_at is not None or ticket.expires_at <= now:
        raise HTTPException(status_code=400, detail="重置凭据已失效，请重新验证")
    user = db.get(User, ticket.user_id)
    if not user:
        raise HTTPException(status_code=400, detail="重置凭据已失效，请重新验证")
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(status_code=400, detail="新密码不能与原密码相同")

    user.password_hash = hash_password(payload.new_password)
    ticket.used_at = now
    db.commit()
    guard.revoke_all_sessions(db, user.id, reason="password_reset")


def _goal_ids(db: OrmSession, user_id: int) -> list:
    return list(db.scalars(select(Goal.id).where(Goal.user_id == user_id)).all())


@router.get("/me/export")
def export_me(
    user: User = Depends(get_current_user), db: OrmSession = Depends(get_db)
) -> JSONResponse:
    """导出当前用户的全部学习数据，满足隐私要求中的「可带走」。"""
    goal_ids = _goal_ids(db, user.id)
    points = (
        db.scalars(select(KnowledgePoint).where(KnowledgePoint.goal_id.in_(goal_ids))).all()
        if goal_ids
        else []
    )
    payload = {
        "exported_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "user": UserOut.model_validate(user).model_dump(mode="json"),
        "goals": [
            {
                "id": goal.id,
                "exam_name": goal.exam_name,
                "exam_date": goal.exam_date,
                "daily_minutes": goal.daily_minutes,
                "created_at": goal.created_at,
            }
            for goal in db.scalars(select(Goal).where(Goal.user_id == user.id)).all()
        ],
        "knowledge_points": [
            {"id": p.id, "goal_id": p.goal_id, "name": p.name, "parent_id": p.parent_id, "weight": p.weight}
            for p in points
        ],
        "mastery": [
            {
                "kp_id": row.kp_id,
                "value": row.value,
                "review_stage": row.review_stage,
                "next_review_at": row.next_review_at,
            }
            for row in db.scalars(select(Mastery).where(Mastery.user_id == user.id)).all()
        ],
        "mastery_history": [
            {"kp_id": row.kp_id, "day": row.day, "value": row.value}
            for row in db.scalars(select(MasteryHistory).where(MasteryHistory.user_id == user.id)).all()
        ],
        "tasks": [
            {
                "id": t.id,
                "goal_id": t.goal_id,
                "kp_id": t.kp_id,
                "day": t.day,
                "title": t.title,
                "type": t.type,
                "duration_min": t.duration_min,
                "status": t.status,
                "reason": t.reason,
                "priority": t.priority,
                "source": t.source,
                "done_at": t.done_at,
            }
            for t in db.scalars(select(Task).where(Task.user_id == user.id)).all()
        ],
        "mistakes": [
            {
                "id": m.id,
                "goal_id": m.goal_id,
                "kp_id": m.kp_id,
                "question": m.question,
                "user_answer": m.user_answer,
                "correct_answer": m.correct_answer,
                "category": m.category,
                "category_label": m.category_label,
                "suggestion": m.suggestion,
                "source": m.source,
                "created_at": m.created_at,
            }
            for m in db.scalars(select(Mistake).where(Mistake.user_id == user.id)).all()
        ],
        "materials": [
            {"id": row.id, "goal_id": row.goal_id, "filename": row.filename, "created_at": row.created_at}
            for row in db.scalars(select(Material).where(Material.user_id == user.id)).all()
        ],
        "reports": [
            {
                "id": r.id,
                "goal_id": r.goal_id,
                "week_start": r.week_start,
                "week_end": r.week_end,
                "completion_rate": r.completion_rate,
                "mastery_delta": r.mastery_delta,
                "focus": r.focus,
                "content": r.content,
            }
            for r in db.scalars(select(Report).where(Report.user_id == user.id)).all()
        ],
        "quiz_attempts": [
            {
                "id": row.id,
                "goal_id": row.goal_id,
                "score": row.score,
                "correct": row.correct,
                "total": row.total,
                "wrong_count": row.wrong_count,
                "engine": row.engine,
                "created_at": row.created_at,
            }
            for row in db.scalars(
                select(QuizAttempt).where(QuizAttempt.user_id == user.id)
            ).all()
        ],
        "replan_logs": [
            {"id": log.id, "goal_id": log.goal_id, "trigger": log.trigger, "changes": log.changes}
            for log in db.scalars(select(ReplanLog).where(ReplanLog.user_id == user.id)).all()
        ],
        "sessions": [
            {
                "id": row.id,
                "device": row.device,
                "platform": row.platform,
                "ip": row.ip,
                "created_at": row.created_at,
                "last_seen_at": row.last_seen_at,
                "revoked_at": row.revoked_at,
            }
            for row in db.scalars(select(AuthSession).where(AuthSession.user_id == user.id)).all()
        ],
    }
    # 文档 9.4 / E3：导出文件带隐式标识（属性信息 + 服务提供者 + 内容编号）
    content_id = f"xueji-export-{uuid.uuid4().hex[:12]}"
    payload["ai_disclosure"] = {
        "generated": True,
        "contains_ai_generated_content": True,
        "service_provider": "学迹 · 自适应 AI 学习教练",
        "provider_code": "xueji",
        "content_id": content_id,
        "label": "AI 辅助生成",
        "note": "本文件包含 AI 辅助生成的内容（周报、诊断与建议），仅供参考，不构成承诺或诊断。",
        "exported_at": payload["exported_at"],
    }
    return JSONResponse(
        content=jsonable_encoder(payload),
        headers={
            "Content-Disposition": 'attachment; filename="xueji-export.json"',
            "X-AI-Generated": "true",
            "X-AI-Provider": "xueji",
            "X-AI-Content-Id": content_id,
            "X-Content-Disclosure": "AI-assisted",
        },
    )


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(user: User = Depends(get_current_user), db: OrmSession = Depends(get_db)) -> None:
    """删除账号与其全部学习数据，满足隐私要求中的「可删除」。

    会话、密保与恢复码一并清除：账号注销后不应残留任何可用于登录的凭据。
    """
    goal_ids = _goal_ids(db, user.id)
    for model in (
        MasteryHistory,
        Mastery,
        Task,
        Mistake,
        Report,
        QuizAttempt,
        Material,
        ReplanLog,
        AuthSession,
        RecoveryCode,
        PasswordResetTicket,
    ):
        db.query(model).filter(model.user_id == user.id).delete(synchronize_session=False)
    db.query(RecoveryProfile).filter(RecoveryProfile.user_id == user.id).delete(
        synchronize_session=False
    )
    if goal_ids:
        db.query(KnowledgePoint).filter(KnowledgePoint.goal_id.in_(goal_ids)).delete(
            synchronize_session=False
        )
    db.delete(user)
    db.commit()
