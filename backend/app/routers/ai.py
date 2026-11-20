"""AI 助手：机器人配置（多 Provider + 加密 Key）、会话历史、流式对话。

- 机器人走 OpenAI 兼容 chat/completions 协议，后端统一代理转发（SSE 流式）
- 出站文本经过 magpie 风格脱敏；模型返回的占位符在流式转发时还原
- 对话时按数据范围（孩子/场次/学科/时间段）从库里组装成绩上下文随消息发给模型
- API key 只以密文存库，接口返回时打码
"""
from __future__ import annotations

import json
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import crypto, providers
from ..auth import AuthDep
from ..database import get_db
from ..models import AgentProfile, AiBot, AiConversation, AiMessage, Child, Exam, Mistake, PrivacyAudit, Score, Subject
from ..privacy import StreamRestorer, default_level, engine_for_db
from ..security import validate_outbound_url

router = APIRouter(prefix="/ai", tags=["ai"], dependencies=[AuthDep])

# 兼容旧引用
PROVIDERS = providers.PROVIDERS
HISTORY_LIMIT = 20
SSE_ERROR = "data: {\"ai_error\": %s}\n\n"
SSE_CHUNK = "data: {\"choices\": [{\"index\": 0, \"delta\": {\"content\": %s}, \"finish_reason\": null}]}\n\n"


# ---------- 请求模型 ----------
class BotIn(BaseModel):
    name: str
    provider: str = "deepseek"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 1600
    timeout: int = 120
    extra_headers: str = "{}"
    enabled: bool = True
    is_default: bool = False
    fallback_bot_id: int | None = None


class ChatIn(BaseModel):
    bot_id: int
    question: str
    conversation_id: int | None = None  # 为空则新建会话
    # 数据范围：孩子必填；场次/学科/时间段可选；focus 指明评语写入目标
    scope: dict = Field(default_factory=dict)
    privacy_level: str = ""


def mask_key(key: str) -> str:
    return crypto.mask_key(key)


def bot_out(b: AiBot) -> dict:
    return providers.bot_out_dict(b)


def _bot_chain(db: Session, bot: AiBot) -> list[AiBot]:
    chain = [bot]
    seen = {bot.id}
    nxt = getattr(bot, "fallback_bot_id", None)
    while nxt and nxt not in seen and len(chain) < 3:
        fallback = db.get(AiBot, int(nxt))
        if not fallback or not getattr(fallback, "enabled", True):
            break
        chain.append(fallback)
        seen.add(fallback.id)
        nxt = getattr(fallback, "fallback_bot_id", None)
    return chain


# ---------- provider 预设 ----------
@router.get("/providers")
def providers_api():
    return providers.provider_list()


@router.get("/status")
def ai_status(db: Session = Depends(get_db)):
    from ..privacy import privacy_status

    return {
        "providers": len(providers.PROVIDERS),
        "bots": db.scalar(select(func.count(AiBot.id))) or 0,
        "enabled_bots": db.scalar(select(func.count(AiBot.id)).where(AiBot.enabled.is_(True))) or 0,
        "default_bot_id": db.scalar(select(AiBot.id).where(AiBot.is_default.is_(True)).limit(1)),
        "secret": crypto.secret_status(),
        "privacy": privacy_status(),
    }


# ---------- 机器人 CRUD ----------
@router.get("/bots")
def list_bots(db: Session = Depends(get_db)):
    return [bot_out(b) for b in db.scalars(select(AiBot).order_by(AiBot.id)).all()]


@router.post("/bots")
def create_bot(body: BotIn, db: Session = Depends(get_db)):
    _validate_bot(body, db)
    data = body.model_dump()
    api_key = (data.pop("api_key") or "").strip()
    bot = AiBot(**data)
    providers.store_api_key(bot, api_key)
    if body.is_default:
        db.query(AiBot).update({AiBot.is_default: False}, synchronize_session=False)
    db.add(bot)
    db.commit()
    db.refresh(bot)
    return bot_out(bot)


class BotTestIn(BaseModel):
    provider: str
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    bot_id: int | None = None  # 编辑时 key 留空则用库里已存的 key 测试


@router.post("/bots/test")
async def test_bot(body: BotTestIn, db: Session = Depends(get_db)):
    """连接测试：发一个极小的对话请求验证配置是否可用。"""
    api_key = body.api_key.strip()
    if not api_key and body.bot_id:
        stored = db.get(AiBot, body.bot_id)
        api_key = providers.bot_api_key(stored) if stored else ""
    if not api_key:
        raise HTTPException(400, "请先填写 API Key")
    model = body.model.strip()
    if not model:
        raise HTTPException(400, "请先填写模型名")
    base_url = providers.resolve_base_url(body.provider, body.base_url)
    validate_outbound_url(base_url, field="接口地址")
    url = providers.chat_url(base_url)
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 16,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            resp = await client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        return {"ok": False, "message": f"连接失败：{exc.__class__.__name__}（网络不通或地址错误）"}
    if resp.status_code == 200:
        return {"ok": True, "message": "连接成功，配置可用"}
    detail = resp.text[:300]
    try:
        detail = resp.json().get("error", {}).get("message") or detail
    except ValueError:
        pass
    hint = {401: "API Key 无效", 403: "无权访问该模型", 404: "接口地址或模型名错误", 429: "限流/欠费"}.get(resp.status_code)
    return {"ok": False, "message": f"失败（{resp.status_code}）：{hint or detail}"}


@router.patch("/bots/{bot_id}")
def update_bot(bot_id: int, body: BotIn, db: Session = Depends(get_db)):
    bot = db.get(AiBot, bot_id)
    if not bot:
        raise HTTPException(404, "机器人不存在")
    _validate_bot(body, db, bot_id=bot_id)
    data = body.model_dump()
    api_key = (data.pop("api_key") or "").strip()
    if api_key:
        providers.store_api_key(bot, api_key)
    for key, value in data.items():
        setattr(bot, key, value)
    if body.is_default:
        db.query(AiBot).filter(AiBot.id != bot_id).update(
            {AiBot.is_default: False}, synchronize_session=False
        )
    db.commit()
    db.refresh(bot)
    return bot_out(bot)


@router.delete("/bots/{bot_id}")
def delete_bot(bot_id: int, confirm: bool = Query(False), db: Session = Depends(get_db)):
    bot = db.get(AiBot, bot_id)
    if not bot:
        raise HTTPException(404, "机器人不存在")
    n = db.scalar(select(func.count(AiMessage.id)).where(AiMessage.bot_id == bot_id)) or 0
    if n and not confirm:
        raise HTTPException(409, f"该机器人有 {n} 条会话记录，删除将一并清除")
    db.query(AiMessage).filter(AiMessage.bot_id == bot_id).delete()
    db.query(AiConversation).filter(AiConversation.bot_id == bot_id).delete()
    db.query(AiBot).filter(AiBot.fallback_bot_id == bot_id).update(
        {AiBot.fallback_bot_id: None}, synchronize_session=False
    )
    db.query(AgentProfile).filter(AgentProfile.bot_id == bot_id).update(
        {AgentProfile.bot_id: None}, synchronize_session=False
    )
    db.delete(bot)
    db.commit()
    return {"ok": True}


def _validate_bot(body: BotIn, db: Session, bot_id: int | None = None):
    if not body.name.strip():
        raise HTTPException(400, "机器人名称不能为空")
    if body.provider not in providers.PROVIDERS:
        raise HTTPException(400, "不支持的 provider")
    if not body.model.strip():
        raise HTTPException(400, "模型名不能为空")
    if not 0 <= body.temperature <= 2:
        raise HTTPException(400, "temperature 需在 0~2 之间")
    if not 1 <= body.max_tokens <= 200000:
        raise HTTPException(400, "max_tokens 需在 1~200000 之间")
    if not 5 <= body.timeout <= 600:
        raise HTTPException(400, "timeout 需在 5~600 秒之间")
    base_url = providers.resolve_base_url(body.provider, body.base_url)
    validate_outbound_url(base_url, field="接口地址")
    if body.fallback_bot_id:
        if bot_id and body.fallback_bot_id == bot_id:
            raise HTTPException(400, "故障回退不能指向自己")
        if not db.get(AiBot, body.fallback_bot_id):
            raise HTTPException(404, "回退机器人不存在")
    if body.extra_headers.strip():
        try:
            parsed = json.loads(body.extra_headers)
        except ValueError:
            raise HTTPException(400, "额外请求头必须是合法 JSON 对象")
        if not isinstance(parsed, dict):
            raise HTTPException(400, "额外请求头必须是 JSON 对象")


# ---------- 会话（conversation）管理 ----------
def _conv_out(c: AiConversation, msg_count: int = 0) -> dict:
    # 无标题的旧会话不主动消耗 token 补题，显示日期占位；继续聊出新消息时才由 AI 总结命名
    placeholder = f"{c.created_at.strftime('%Y-%m-%d') if c.created_at else '未命名'} 的会话"
    return {
        "id": c.id,
        "bot_id": c.bot_id,
        "title": c.title or placeholder,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
        "msg_count": msg_count,
        "mode": getattr(c, "mode", "chat"),
        "privacy_level": getattr(c, "privacy_level", ""),
    }


@router.get("/bots/{bot_id}/conversations")
def list_conversations(bot_id: int, db: Session = Depends(get_db)):
    """会话列表（按最近活跃倒序），过滤空会话。"""
    convs = db.scalars(
        select(AiConversation)
        .where(AiConversation.bot_id == bot_id, AiConversation.mode == "chat")
        .order_by(AiConversation.updated_at.desc())
    ).all()
    counts = dict(db.execute(
        select(AiMessage.conversation_id, func.count(AiMessage.id))
        .where(AiMessage.bot_id == bot_id).group_by(AiMessage.conversation_id)
    ).all())
    return [_conv_out(c, counts.get(c.id, 0)) for c in convs if counts.get(c.id, 0) > 0]


@router.post("/bots/{bot_id}/conversations")
def create_conversation(bot_id: int, db: Session = Depends(get_db)):
    if not db.get(AiBot, bot_id):
        raise HTTPException(404, "机器人不存在")
    c = AiConversation(bot_id=bot_id, mode="chat")
    db.add(c)
    db.commit()
    return _conv_out(c)


@router.get("/conversations/{conv_id}/messages")
def conversation_messages(conv_id: int, db: Session = Depends(get_db)):
    msgs = db.scalars(
        select(AiMessage).where(AiMessage.conversation_id == conv_id).order_by(AiMessage.id)
    ).all()
    return [{"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at} for m in msgs]


@router.patch("/conversations/{conv_id}")
def rename_conversation(conv_id: int, body: dict, db: Session = Depends(get_db)):
    """手动修改会话命名。"""
    title = (body.get("title") or "").strip()[:60]
    if not title:
        raise HTTPException(400, "会话名称不能为空")
    c = db.get(AiConversation, conv_id)
    if not c:
        raise HTTPException(404, "会话不存在")
    c.title = title
    db.commit()
    return {"ok": True, "title": title}


@router.delete("/conversations/{conv_id}")
def delete_conversation(conv_id: int, db: Session = Depends(get_db)):
    c = db.get(AiConversation, conv_id)
    if c:
        db.query(AiMessage).filter(AiMessage.conversation_id == conv_id).delete()
        db.delete(c)
        db.commit()
    return {"ok": True}


@router.get("/bots/{bot_id}/messages")
def list_messages(bot_id: int, db: Session = Depends(get_db)):
    msgs = db.scalars(
        select(AiMessage).where(AiMessage.bot_id == bot_id).order_by(AiMessage.id)
    ).all()
    return [{"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at} for m in msgs]


@router.delete("/bots/{bot_id}/messages")
def clear_messages(bot_id: int, db: Session = Depends(get_db)):
    """清空该机器人全部会话。"""
    db.query(AiMessage).filter(AiMessage.bot_id == bot_id).delete()
    db.query(AiConversation).filter(AiConversation.bot_id == bot_id).delete()
    db.commit()
    return {"ok": True}


# ---------- 成绩上下文组装 ----------
def _fmt_score_row(s: Score) -> str:
    parts = [
        f"日期 {s.date}",
        f"学科 {s.subject.name if s.subject else '?'}",
        f"类型 {s.type}",
        f"学期 {s.term}",
        f"得分 {s.regular_score}/{s.regular_total}",
    ]
    if s.bonus_score is not None:
        parts.append(f"附加 {s.bonus_score}/{s.bonus_total if s.bonus_total is not None else '?'}")
    if s.class_rank is not None:
        parts.append(f"班级名次 {s.class_rank}/{s.class_size or '?'}")
    if s.grade_rank is not None:
        parts.append(f"年级名次 {s.grade_rank}")
    if s.units:
        parts.append("单元 " + "、".join(f"第{u.sort_no}单元{u.name}" if u.name else f"第{u.sort_no}单元" for u in s.units))
    if s.tags:
        parts.append(f"标签 {s.tags}")
    if s.note:
        parts.append(f"备注 {s.note}")
    if s.ai_comment:
        parts.append(f"AI评语 {s.ai_comment}")
    if s.high_score is not None:
        parts.append(f"班级最高分 {s.high_score}（{s.high_scorer or '?'}）")
    return " | ".join(parts)


def _clip(text: str, limit: int = 60) -> str:
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    return t[:limit] + ("…" if len(t) > limit else "")


def _fmt_mistake_rows(db: Session, score_ids: list[int]) -> list[str]:
    """范围内成绩关联的错题：AI 写评语时据此归因、指出具体薄弱点。"""
    if not score_ids:
        return []
    rows = db.scalars(
        select(Mistake).where(Mistake.source_score_id.in_(list(dict.fromkeys(score_ids)))).order_by(Mistake.id).limit(30)
    ).all()
    if not rows:
        return []
    lines = [f"  本范围关联错题（{len(rows)} 道，评语需结合这些错因与知识点）："]
    for m in rows:
        head = " ".join(x for x in (f"第{m.question_no}题" if m.question_no else "", m.title or "") if x).strip() or "错题"
        detail = []
        if m.reason:
            detail.append(f"错因 {_clip(m.reason)}")
        if m.knowledge_tags:
            detail.append(f"知识点 {_clip(m.knowledge_tags, 40)}")
        if m.my_answer:
            detail.append(f"作答 {_clip(m.my_answer, 40)}")
        if m.correct_answer:
            detail.append(f"正确答案 {_clip(m.correct_answer, 40)}")
        lines.append("  - " + head + ("｜" + "｜".join(detail) if detail else ""))
    return lines


def _fmt_exam_row(e: Exam, scores: list[Score], db: Session | None = None) -> str:
    parts = [
        f"日期 {e.date}",
        f"类型 {e.type}",
        f"学期 {e.term}",
        f"年级 {e.grade}",
    ]
    if scores:
        earned = sum(s.regular_score + (s.bonus_score or 0) for s in scores)
        total = sum(s.regular_total + (s.bonus_total or 0) for s in scores)
        parts.append(f"总分 {earned:g}/{total:g}")
    if e.grade_rank is not None:
        parts.append(f"年级名次 {e.grade_rank}")
    if e.class_rank is not None:
        parts.append(f"班级名次 {e.class_rank}/{e.class_size or '?'}")
    if e.tags:
        parts.append(f"标签 {e.tags}")
    if e.note:
        parts.append(f"备注 {e.note}")
    if e.ai_comment:
        parts.append(f"AI评语 {e.ai_comment}")
    lines = ["场次「%s」：" % e.name + " | ".join(parts)]
    lines += ["  " + _fmt_score_row(s) for s in scores]
    if db and scores:
        lines += _fmt_mistake_rows(db, [s.id for s in scores])
    return "\n".join(lines)


def _child_full_rows(db: Session, child_id: int) -> list[str]:
    """某孩子全部成绩行：场次汇总 + 独立成绩，按时间排序。"""
    all_scores = db.scalars(
        select(Score).where(Score.child_id == child_id).order_by(Score.date, Score.id).limit(120)
    ).all()
    exams = db.scalars(select(Exam).where(Exam.child_id == child_id).order_by(Exam.date).limit(50)).all()
    extra = []
    for e in exams:
        es = [s for s in all_scores if s.exam_id == e.id]
        extra.append(_fmt_exam_row(e, es) if es else None)
    extra.extend(_fmt_score_row(s) for s in all_scores if not s.exam_id)
    return [x for x in extra if x]


def build_context(db: Session, scope: dict) -> str:
    """按数据范围组装成绩文本。核心兜底：未选孩子时自动带全部孩子的完整数据；
    范围内明细太少（≤5 条）时附加该孩子全历史，供 AI 做跨学期/趋势对比。"""
    child_id = scope.get("child_id")
    exam_id = scope.get("exam_id")
    subject_id = scope.get("subject_id")
    date_from = scope.get("date_from") or ""
    date_to = scope.get("date_to") or ""
    has_filter = bool(child_id or exam_id or subject_id or date_from or date_to)

    children = ([db.get(Child, child_id)] if child_id else db.scalars(select(Child)).all())
    children = [c for c in children if c]
    if not children:
        return "系统中还没有录入任何孩子。"

    blocks = []
    for child in children:
        lines: list[str] = []
        mistake_lines: list[str] = []
        if exam_id:
            e = db.get(Exam, exam_id)
            if e and e.child_id == child.id:
                scores = db.scalars(select(Score).where(Score.exam_id == exam_id).order_by(Score.id)).all()
                lines.append(_fmt_exam_row(e, scores, db))
        else:
            q = select(Score).where(Score.child_id == child.id)
            if subject_id:
                q = q.where(Score.subject_id == subject_id)
            if date_from:
                q = q.where(Score.date >= date_from)
            if date_to:
                q = q.where(Score.date <= date_to)
            scores_in_range = list(db.scalars(q.order_by(Score.date, Score.id).limit(100)).all())
            lines = [_fmt_score_row(s) for s in scores_in_range]
            mistake_lines = _fmt_mistake_rows(db, [s.id for s in scores_in_range])

        full = None if exam_id else _child_full_rows(db, child.id)
        detail = "\n".join(lines + mistake_lines)
        # 未选孩子（家长可能问任一学期/科目）或范围内明细太少 → 都必须给全历史
        need_full = (not child_id) or (full and len(lines) <= 5)

        if full and need_full and len(full) > len(lines):
            if lines and has_filter:
                blocks.append(
                    f"【孩子「{child.name}」·当前范围明细】（{len(lines)} 条）：\n" + detail
                    + f"\n【孩子「{child.name}」·全历史成绩概览】（全部 {len(full)} 条，每条带学期/日期，可据此理解\"本学期\"等说法）：\n"
                    + "\n".join(full)
                )
            else:
                blocks.append(
                    f"【孩子「{child.name}」成绩】（全部 {len(full)} 条，每条带学期/日期，可据此理解\"本学期/上学期\"等说法）：\n"
                    + "\n".join(full)
                )
        else:
            body = detail if (lines or mistake_lines) else "（该范围内无成绩记录）"
            blocks.append(f"【孩子「{child.name}」成绩】（{len(lines)} 条）：\n" + body)

    # 选定了某个孩子时，附加其他孩子的成绩概览：AI 才能回答"和 XX 相比"这类跨孩子问题
    if child_id:
        others = [c for c in db.scalars(select(Child)).all() if c and c.id != child_id]
        for other in others:
            rows = _child_full_rows(db, other.id)[:60]
            if rows:
                blocks.append(
                    f"【其他孩子「{other.name}」成绩概览】（供跨孩子对比，全部 {len(rows)} 条）：\n" + "\n".join(rows)
                )
    return "\n\n".join(blocks)


SYSTEM_PROMPT = (
    "你是一个小学生的家长配置的成绩分析助手，熟悉中国中小学教育。"
    "用户会提供孩子的成绩数据，请基于数据回答：可做趋势分析、诊断强弱科、给出具体可执行的学习建议。"
    "数据可能分块：当前范围明细 + 全历史成绩概览，每条记录都带「学期」和「日期」。"
    "当用户问趋势、进步、对比类问题时，务必结合全历史概览一起分析，而不是只盯着明细范围说数据不足；"
    "当用户说\"本学期/上学期/最近\"等时间词时，根据记录里的学期和日期自行划定范围再分析。"
    "数据按孩子分块给出：当前范围明细/全历史概览 + 可能存在的【其他孩子成绩概览】。"
    "未指定孩子时对所有孩子的数据综合分析；用户提到其他孩子名字（对比、询问）时，"
    "从对应孩子的数据块中查找，找不到再如实说明（注意：班里同学的成绩系统不录入，只有最高得分者姓名）。"
    "回答要求：使用简体中文；直接给结论和建议，不要复述问题、不要客套；篇幅尽量精炼（一般 200 字以内，"
    "用户明确要求详细分析时才展开）；可用少量短列表和加粗突出重点，不要堆砌标题和嵌套结构；数据不足时如实说明。"
    "当用户要求为某条成绩/某场考试写评语时，用一段 50 字以内、鼓励为主且指出改进方向的评语，"
    "并用 <comment></comment> 标签把评语正文包裹起来，评语正文里不要有换行。"
    "若数据中出现「本范围关联错题」，评语必须结合其中的具体错因/知识点（指出薄弱点），不要只写空泛鼓励。"
    "文本中的 {{KIND_xxxxxxxx}} 是本地脱敏占位符，代表真实姓名/学校等；请当作普通文本使用，不要猜测或改写。"
)


def _extract_reply(raw: str) -> str:
    """从转发的 SSE 原始文本中拼接出 assistant 完整回复（兼容旧测试）。"""
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            obj = json.loads(data)
            delta = obj["choices"][0].get("delta", {})
            if delta.get("content"):
                out.append(delta["content"])
        except (ValueError, KeyError, IndexError):
            continue
    return "".join(out)


def _save_history(bot_id: int, conv_id: int, question: str, reply: str, privacy: dict | None = None):
    """保存本轮消息；刷新会话活跃时间；空标题会话用问题前缀命名。"""
    from datetime import datetime as _dt

    from ..database import SessionLocal

    with SessionLocal() as ses:
        ses.add(AiMessage(bot_id=bot_id, conversation_id=conv_id, role="user", content=question,
                          meta=json.dumps({"privacy": privacy or {}}, ensure_ascii=False)))
        ses.add(AiMessage(bot_id=bot_id, conversation_id=conv_id, role="assistant", content=reply,
                          meta=json.dumps({"privacy": privacy or {}}, ensure_ascii=False)))
        conv = ses.get(AiConversation, conv_id)
        if conv:
            conv.updated_at = _dt.now()
            if not conv.title:
                conv.title = re.sub(r"\s+", " ", question).strip()[:40] or "会话"
        ses.commit()


# ---------- 流式对话 ----------
@router.post("/chat")
async def chat(body: ChatIn, db: Session = Depends(get_db)):
    bot = db.get(AiBot, body.bot_id)
    if not bot:
        raise HTTPException(404, "机器人不存在")
    if not getattr(bot, "enabled", True):
        raise HTTPException(400, "该机器人已停用")
    if not providers.bot_api_key(bot):
        raise HTTPException(400, "该机器人未配置 API key")
    question = body.question.strip()
    if not question:
        raise HTTPException(400, "问题不能为空")
    level = (body.privacy_level or "").strip().lower()
    if level and level not in ("off", "standard", "strict"):
        raise HTTPException(400, "privacy_level 只能是 off/standard/strict")
    level = level or default_level()

    # 会话：无 id 则新建；有 id 则校验归属该机器人
    conv = None
    if body.conversation_id:
        conv = db.get(AiConversation, body.conversation_id)
        if not conv or conv.bot_id != bot.id:
            raise HTTPException(404, "会话不存在")
    else:
        conv = AiConversation(bot_id=bot.id, mode="chat", privacy_level=level)
        db.add(conv)
        db.commit()
        db.refresh(conv)
    conv_id = conv.id

    # 出站脱敏：系统提示、历史、数据上下文、本轮问题全部经过同一引擎
    engine = engine_for_db(db, level=level)
    restorer = StreamRestorer(engine)
    history = db.scalars(
        select(AiMessage).where(AiMessage.conversation_id == conv_id).order_by(AiMessage.id.desc()).limit(HISTORY_LIMIT)
    ).all()
    msgs = [{"role": "system", "content": engine.redact(SYSTEM_PROMPT)}]
    for m in reversed(history):
        if m.role in ("user", "assistant"):
            msgs.append({"role": m.role, "content": engine.redact(m.content or "")})
    ctx = engine.redact(build_context(db, body.scope))
    safe_question = engine.redact(question)
    msgs.append({"role": "user", "content": f"{ctx}\n\n我的问题：{safe_question}"})

    chain = _bot_chain(db, bot)
    bot_id, user_question = bot.id, question

    async def gen():
        raw_parts: list[str] = []
        sent_done = False
        last_error = ""
        for candidate in chain:
            payload = providers.bot_payload(candidate, msgs, stream=True)
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(float(getattr(candidate, "timeout", 120) or 120), connect=15.0)
                ) as client:
                    url = providers.chat_url(providers.validate_provider_url(candidate.provider, candidate.base_url))
                    async with client.stream(
                        "POST", url, headers=providers.headers_for(candidate), json=payload,
                    ) as resp:
                        if resp.status_code != 200:
                            detail = (await resp.aread()).decode("utf-8", "ignore")[:300]
                            try:
                                detail = json.loads(detail).get("error", {}).get("message") or detail
                            except ValueError:
                                pass
                            last_error = detail
                            if not raw_parts and candidate is not chain[-1]:
                                continue
                            yield SSE_ERROR % json.dumps(detail, ensure_ascii=False)
                            return
                        async for line in resp.aiter_lines():
                            line = (line or "").strip()
                            if not line or not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if data == "[DONE]":
                                tail = restorer.flush()
                                if tail:
                                    yield SSE_CHUNK % json.dumps(tail, ensure_ascii=False)
                                yield "data: [DONE]\n\n"
                                sent_done = True
                                break
                            try:
                                obj = json.loads(data)
                            except ValueError:
                                continue
                            if obj.get("error"):
                                yield SSE_ERROR % json.dumps(
                                    str(obj["error"].get("message") or obj["error"]), ensure_ascii=False
                                )
                                return
                            try:
                                delta = obj["choices"][0].get("delta", {})
                            except (KeyError, IndexError):
                                delta = {}
                            content = delta.get("content")
                            if content:
                                raw_parts.append(content)
                                safe = restorer.feed(content)
                                if safe:
                                    delta["content"] = safe
                                    yield "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"
                            else:
                                yield "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"
                        break
            except httpx.HTTPError as exc:
                last_error = f"请求模型服务失败：{exc.__class__.__name__}: {exc}"
                if not raw_parts and candidate is not chain[-1]:
                    continue
                yield SSE_ERROR % json.dumps(last_error, ensure_ascii=False)
                return
        if not sent_done:
            tail = restorer.flush()
            if tail:
                yield SSE_CHUNK % json.dumps(tail, ensure_ascii=False)
            yield "data: [DONE]\n\n"

        reply = engine.restore("".join(raw_parts))
        if reply:
            privacy = engine.snapshot()
            _save_history(bot_id, conv_id, user_question, reply, privacy)
            try:
                from ..database import SessionLocal

                with SessionLocal() as ses:
                    ses.add(PrivacyAudit(
                        conversation_id=conv_id, direction="out", level=level,
                        counts=json.dumps(privacy.get("counts", {}), ensure_ascii=False),
                        placeholders=int(privacy.get("placeholders", 0)),
                        chars=int(privacy.get("chars", 0)),
                    ))
                    ses.commit()
            except Exception:
                pass
        elif last_error:
            yield SSE_ERROR % json.dumps(last_error, ensure_ascii=False)

    return StreamingResponse(
        gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
