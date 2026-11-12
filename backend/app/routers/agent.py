"""Agent API：配置、会话、SSE 对话、待确认动作、隐私预览与审计。"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import crypto
from ..agent.runtime import agent_event_stream, list_pending
from ..agent.tools import (
    READ_TOOLS,
    TOOL_NAMES,
    TOOL_SPECS,
    WRITE_TOOLS,
    ToolContext,
    ToolError,
    cancel_pending,
    confirm_pending,
    execute_tool,
)
from ..auth import AuthDep
from ..database import get_db
from ..models import AgentPendingAction, AgentProfile, AgentRun, AiBot, AiConversation, AiMessage, PrivacyAudit
from ..privacy import LEVELS, engine_for_db, privacy_status
from ..providers import PROVIDERS, bot_api_key, provider_list

router = APIRouter(prefix="/agent", tags=["agent"], dependencies=[AuthDep])


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    bot_id: int | None = None
    system_prompt: str = ""
    tools: list[str] = Field(default_factory=list)
    privacy_level: str = ""
    allow_write: bool = True
    auto_approve: bool = False


class ChatIn(BaseModel):
    bot_id: int
    profile_id: int | None = None
    conversation_id: int | None = None
    question: str = Field(min_length=1, max_length=8000)
    privacy_level: str = ""


class ConversationIn(BaseModel):
    bot_id: int
    profile_id: int | None = None
    title: str = ""
    privacy_level: str = ""


class RenameIn(BaseModel):
    title: str = ""
    privacy_level: str | None = None


class PreviewIn(BaseModel):
    text: str
    level: str = ""


def _profile_out(p: AgentProfile) -> dict:
    try:
        tools = json.loads(p.tools or "[]")
    except ValueError:
        tools = []
    return {
        "id": p.id,
        "name": p.name,
        "bot_id": p.bot_id,
        "system_prompt": p.system_prompt,
        "tools": tools,
        "privacy_level": p.privacy_level,
        "allow_write": bool(p.allow_write),
        "auto_approve": bool(p.auto_approve),
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


def _conv_out(db: Session, c: AiConversation) -> dict:
    count = db.scalar(select(func.count(AiMessage.id)).where(AiMessage.conversation_id == c.id)) or 0
    title = c.title or (f"{c.created_at:%Y-%m-%d} 的 Agent 会话" if c.created_at else "Agent 会话")
    return {
        "id": c.id,
        "bot_id": c.bot_id,
        "title": title,
        "mode": c.mode,
        "profile_id": c.profile_id,
        "privacy_level": c.privacy_level,
        "msg_count": count,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
    }


def _validate_level(level: str) -> str:
    value = (level or "").strip().lower()
    if value and value not in LEVELS:
        raise HTTPException(400, "privacy_level 只能是 off/standard/strict 或留空")
    return value


def _validate_profile(body: ProfileIn) -> list[str]:
    _validate_level(body.privacy_level)
    unknown = [t for t in body.tools if t not in TOOL_NAMES]
    if unknown:
        raise HTTPException(400, "未知工具：" + "、".join(unknown[:5]))
    return list(dict.fromkeys(body.tools))


# ---------- 元信息 ----------
@router.get("/tools")
def tools():
    return {
        "tools": TOOL_SPECS,
        "names": TOOL_NAMES,
        "read_tools": READ_TOOLS,
        "write_tools": sorted(WRITE_TOOLS),
    }


class ToolInvokeIn(BaseModel):
    args: dict = Field(default_factory=dict)
    conversation_id: int | None = None
    bot_id: int | None = None
    profile_id: int | None = None
    privacy_level: str = ""


@router.post("/tools/{tool_name}")
def invoke_tool(tool_name: str, body: ToolInvokeIn, db: Session = Depends(get_db)):
    """只读工具的 HTTP 入口（给 CLI / 外部 Agent 用）。

    写工具不在此暴露：写入必须经过对话确认流程，避免绕过审批。
    """
    if tool_name not in TOOL_NAMES:
        raise HTTPException(404, "未知工具")
    if tool_name in WRITE_TOOLS or tool_name in ("confirm_pending_action", "cancel_pending_action"):
        raise HTTPException(403, "写工具只能通过 Agent 对话确认流程执行")
    profile = db.get(AgentProfile, body.profile_id) if body.profile_id else None
    if profile is not None and profile.tools:
        try:
            allowed = set(json.loads(profile.tools))
        except ValueError:
            allowed = set()
        if allowed and tool_name not in allowed:
            raise HTTPException(403, "该 Agent 配置未启用此工具")
    level = _validate_level(body.privacy_level) or (
        profile.privacy_level if profile else ""
    ) or "standard"
    engine = engine_for_db(db, level=level)
    ctx = ToolContext(
        db=db,
        profile=profile,
        conversation_id=body.conversation_id or 0,
        bot_id=body.bot_id or 0,
        auto_approve=False,
        allow_write=False,
        engine=engine,
    )
    result = execute_tool(tool_name, body.args, ctx)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error") or "工具执行失败")
    return result


@router.get("/status")
def status(db: Session = Depends(get_db)):
    return {
        "bots": db.scalar(select(func.count(AiBot.id))) or 0,
        "enabled_bots": db.scalar(select(func.count(AiBot.id)).where(AiBot.enabled.is_(True))) or 0,
        "profiles": db.scalar(select(func.count(AgentProfile.id))) or 0,
        "providers": len(PROVIDERS),
        "tools": len(TOOL_NAMES),
        "write_tools": sorted(WRITE_TOOLS),
        "privacy": privacy_status(),
        "secret": crypto.secret_status(),
        "roundtrip_ok": crypto.check_secret_roundtrip(),
    }


@router.get("/providers")
def providers():
    return provider_list()


# ---------- Agent 配置 ----------
@router.get("/profiles")
def list_profiles(db: Session = Depends(get_db)):
    rows = db.scalars(select(AgentProfile).order_by(AgentProfile.id)).all()
    return [_profile_out(p) for p in rows]


@router.post("/profiles")
def create_profile(body: ProfileIn, db: Session = Depends(get_db)):
    tools = _validate_profile(body)
    if body.bot_id and not db.get(AiBot, body.bot_id):
        raise HTTPException(404, "机器人不存在")
    p = AgentProfile(
        name=body.name.strip(),
        bot_id=body.bot_id,
        system_prompt=body.system_prompt[:8000],
        tools=json.dumps(tools, ensure_ascii=False),
        privacy_level=body.privacy_level,
        allow_write=body.allow_write,
        auto_approve=body.auto_approve,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _profile_out(p)


@router.patch("/profiles/{profile_id}")
def update_profile(profile_id: int, body: ProfileIn, db: Session = Depends(get_db)):
    p = db.get(AgentProfile, profile_id)
    if not p:
        raise HTTPException(404, "Agent 配置不存在")
    tools = _validate_profile(body)
    if body.bot_id and not db.get(AiBot, body.bot_id):
        raise HTTPException(404, "机器人不存在")
    p.name = body.name.strip()
    p.bot_id = body.bot_id
    p.system_prompt = body.system_prompt[:8000]
    p.tools = json.dumps(tools, ensure_ascii=False)
    p.privacy_level = body.privacy_level
    p.allow_write = body.allow_write
    p.auto_approve = body.auto_approve
    db.commit()
    db.refresh(p)
    return _profile_out(p)


@router.delete("/profiles/{profile_id}")
def delete_profile(profile_id: int, db: Session = Depends(get_db)):
    p = db.get(AgentProfile, profile_id)
    if not p:
        raise HTTPException(404, "Agent 配置不存在")
    db.query(AiConversation).filter(AiConversation.profile_id == profile_id).update(
        {AiConversation.profile_id: None}, synchronize_session=False
    )
    db.delete(p)
    db.commit()
    return {"ok": True}


# ---------- 会话 ----------
@router.get("/conversations")
def list_conversations(
    bot_id: int | None = None,
    profile_id: int | None = None,
    db: Session = Depends(get_db),
):
    q = select(AiConversation).where(AiConversation.mode == "agent").order_by(AiConversation.updated_at.desc())
    if bot_id:
        q = q.where(AiConversation.bot_id == bot_id)
    if profile_id:
        q = q.where(AiConversation.profile_id == profile_id)
    return [_conv_out(db, c) for c in db.scalars(q).all()]


@router.post("/conversations")
def create_conversation(body: ConversationIn, db: Session = Depends(get_db)):
    if not db.get(AiBot, body.bot_id):
        raise HTTPException(404, "机器人不存在")
    if body.profile_id and not db.get(AgentProfile, body.profile_id):
        raise HTTPException(404, "Agent 配置不存在")
    _validate_level(body.privacy_level)
    c = AiConversation(
        bot_id=body.bot_id,
        mode="agent",
        profile_id=body.profile_id,
        title=body.title.strip()[:100],
        privacy_level=body.privacy_level,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return _conv_out(db, c)


@router.get("/conversations/{conv_id}/messages")
def messages(conv_id: int, db: Session = Depends(get_db)):
    conv = db.get(AiConversation, conv_id)
    if not conv or conv.mode != "agent":
        raise HTTPException(404, "Agent 会话不存在")
    rows = db.scalars(
        select(AiMessage).where(AiMessage.conversation_id == conv_id).order_by(AiMessage.id)
    ).all()
    out = []
    for m in rows:
        try:
            meta = json.loads(m.meta or "{}")
        except ValueError:
            meta = {}
        out.append({
            "id": m.id, "role": m.role, "content": m.content,
            "meta": meta, "created_at": m.created_at,
        })
    return out


@router.patch("/conversations/{conv_id}")
def rename_conversation(conv_id: int, body: RenameIn, db: Session = Depends(get_db)):
    conv = db.get(AiConversation, conv_id)
    if not conv or conv.mode != "agent":
        raise HTTPException(404, "Agent 会话不存在")
    if body.title.strip():
        conv.title = body.title.strip()[:100]
    if body.privacy_level is not None:
        conv.privacy_level = _validate_level(body.privacy_level)
    db.commit()
    return _conv_out(db, conv)


@router.delete("/conversations/{conv_id}")
def delete_conversation(conv_id: int, db: Session = Depends(get_db)):
    conv = db.get(AiConversation, conv_id)
    if conv:
        db.query(AiMessage).filter(AiMessage.conversation_id == conv_id).delete()
        db.query(AgentPendingAction).filter(AgentPendingAction.conversation_id == conv_id).delete()
        db.query(AgentRun).filter(AgentRun.conversation_id == conv_id).delete()
        db.delete(conv)
        db.commit()
    return {"ok": True}


# ---------- 对话 ----------
@router.post("/chat")
async def chat(body: ChatIn, db: Session = Depends(get_db)):
    bot = db.get(AiBot, body.bot_id)
    if not bot:
        raise HTTPException(404, "机器人不存在")
    if not getattr(bot, "enabled", True):
        raise HTTPException(400, "该机器人已停用")
    if not bot_api_key(bot):
        raise HTTPException(400, "该机器人未配置 API Key")
    _validate_level(body.privacy_level)
    if body.profile_id and not db.get(AgentProfile, body.profile_id):
        raise HTTPException(404, "Agent 配置不存在")

    conv = None
    if body.conversation_id:
        conv = db.get(AiConversation, body.conversation_id)
        if not conv:
            raise HTTPException(404, "会话不存在")
        if conv.mode != "agent":
            raise HTTPException(400, "该会话不是 Agent 会话")
    else:
        conv = AiConversation(
            bot_id=bot.id,
            mode="agent",
            profile_id=body.profile_id,
            privacy_level=body.privacy_level,
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)

    conv_id = conv.id
    stream = agent_event_stream(
        conversation_id=conv_id,
        bot_id=bot.id,
        profile_id=body.profile_id or conv.profile_id,
        question=body.question.strip(),
        privacy_level=body.privacy_level or conv.privacy_level,
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------- 待确认动作 ----------
@router.get("/conversations/{conv_id}/pending")
def pending_actions(conv_id: int, db: Session = Depends(get_db)):
    if not db.get(AiConversation, conv_id):
        raise HTTPException(404, "会话不存在")
    return list_pending(db, conv_id)


def _pending_context(db: Session, token: str) -> tuple[AgentPendingAction, ToolContext, AiConversation]:
    row = db.scalar(select(AgentPendingAction).where(AgentPendingAction.token == token))
    if not row:
        raise HTTPException(404, "待确认操作不存在")
    conv = db.get(AiConversation, row.conversation_id)
    bot = db.get(AiBot, row.bot_id)
    if not conv or not bot:
        raise HTTPException(404, "会话或机器人不存在")
    profile = db.get(AgentProfile, conv.profile_id) if conv.profile_id else None
    level = (conv.privacy_level or (profile.privacy_level if profile else "") or "standard")
    engine = engine_for_db(db, level=level)
    ctx = ToolContext(
        db=db,
        profile=profile,
        conversation_id=conv.id,
        bot_id=bot.id,
        auto_approve=True,
        allow_write=True if profile is None else bool(profile.allow_write),
        engine=engine,
        user_confirmed=True,  # 这是用户在界面点“确认执行”触发的独立请求
    )
    return row, ctx, conv


@router.post("/pending/{token}/confirm")
def confirm_action(token: str, db: Session = Depends(get_db)):
    row, ctx, conv = _pending_context(db, token)
    try:
        result = confirm_pending(ctx, token)
    except ToolError as exc:
        raise HTTPException(400, str(exc)) from exc
    # 把确认结果写入会话，下一轮 Agent 能接着上下文
    summary = result.get("summary") or result.get("error") or "操作已执行"
    db.add(AiMessage(
        bot_id=ctx.bot_id,
        conversation_id=conv.id,
        role="assistant",
        content=f"（已确认执行）{summary}",
        meta=json.dumps({"type": "confirmation", "tool": row.tool, "result": result},
                        ensure_ascii=False, default=str),
    ))
    conv.updated_at = datetime.now()
    db.commit()
    return {"ok": True, "result": result}


@router.post("/pending/{token}/cancel")
def cancel_action(token: str, db: Session = Depends(get_db)):
    _, ctx, _ = _pending_context(db, token)
    try:
        return cancel_pending(ctx, token)
    except ToolError as exc:
        raise HTTPException(400, str(exc)) from exc


# ---------- 运行记录 ----------
@router.get("/runs")
def runs(conversation_id: int | None = None, limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    q = select(AgentRun).order_by(AgentRun.id.desc()).limit(limit)
    if conversation_id:
        q = q.where(AgentRun.conversation_id == conversation_id)
    out = []
    for r in db.scalars(q).all():
        try:
            steps = json.loads(r.steps or "[]")
        except ValueError:
            steps = []
        out.append({
            "id": r.id, "conversation_id": r.conversation_id, "bot_id": r.bot_id,
            "profile_id": r.profile_id, "status": r.status, "error": r.error,
            "steps": steps, "created_at": r.created_at, "finished_at": r.finished_at,
        })
    return out


# ---------- 隐私 ----------
@router.get("/privacy/status")
def privacy_status_api():
    return {
        "privacy": privacy_status(),
        "secret": crypto.secret_status(),
        "levels": list(LEVELS),
    }


@router.post("/privacy/preview")
def privacy_preview(body: PreviewIn, db: Session = Depends(get_db)):
    level = _validate_level(body.level) or "standard"
    engine = engine_for_db(db, level=level)
    redacted = engine.redact(body.text)
    return {
        "level": level,
        "original_length": len(body.text),
        "redacted": redacted,
        "restored": engine.restore(redacted),
        "roundtrip_ok": engine.restore(redacted) == body.text,
        "stats": engine.snapshot(),
        "guard": engine.status().get("guard"),
    }


@router.get("/privacy/audits")
def privacy_audits(
    conversation_id: int | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = select(PrivacyAudit).order_by(PrivacyAudit.id.desc()).limit(limit)
    if conversation_id:
        q = q.where(PrivacyAudit.conversation_id == conversation_id)
    out = []
    for a in db.scalars(q).all():
        try:
            counts = json.loads(a.counts or "{}")
        except ValueError:
            counts = {}
        out.append({
            "id": a.id, "conversation_id": a.conversation_id, "direction": a.direction,
            "level": a.level, "counts": counts, "placeholders": a.placeholders,
            "chars": a.chars, "created_at": a.created_at,
        })
    return out
