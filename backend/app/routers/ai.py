"""AI 助手：机器人配置（provider 预设 + API key）、会话历史、流式对话。

- 机器人走 OpenAI 兼容 chat/completions 协议，后端统一代理转发（SSE 流式）
- 对话时按数据范围（孩子/场次/学科/时间段）从库里组装成绩上下文随消息发给模型
- API key 只存本地库，接口返回时打码
"""
from __future__ import annotations

import json

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import AuthDep
from ..database import get_db
from ..models import AiBot, AiConversation, AiMessage, Child, Exam, Score, Subject

router = APIRouter(prefix="/ai", tags=["ai"], dependencies=[AuthDep])

# 主流厂商预设：OpenAI 兼容接口地址 + 默认模型列表（custom 由用户自填）
# 依据 2026-10 各厂商官方文档核对：DeepSeek api-docs.deepseek.com、
# 通义百炼 help.aliyun.com/zh/model-studio/base-url、
# Kimi platform.kimi.com/docs/api/overview、智谱 docs.bigmodel.cn/cn/api/introduction
PROVIDERS = {
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "models": ["deepseek-flash", "deepseek-v4-pro"],
    },
    "qwen": {
        "label": "通义千问",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen3.8-max", "qwen3.8-flash", "qwen-plus"],
    },
    "kimi": {
        "label": "Kimi（月之暗面）",
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["kimi-k3", "kimi-k2.6"],
    },
    "zhipu": {
        "label": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-5.3", "glm-5-turbo"],
    },
    "custom": {
        "label": "OpenAI 兼容自定义",
        "base_url": "",
        "models": [],
    },
}

# 发给模型的历史上下文轮数上限（控制 token 消耗）
HISTORY_LIMIT = 20


# ---------- 请求模型 ----------
class BotIn(BaseModel):
    name: str
    provider: str = "deepseek"
    base_url: str = ""
    api_key: str = ""
    model: str = ""


class ChatIn(BaseModel):
    bot_id: int
    question: str
    conversation_id: int | None = None  # 为空则新建会话
    # 数据范围：孩子必填；场次/学科/时间段可选；focus 指明评语写入目标
    scope: dict = {}


def mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]


def bot_out(b: AiBot) -> dict:
    return {
        "id": b.id,
        "name": b.name,
        "provider": b.provider,
        "provider_label": PROVIDERS.get(b.provider, {}).get("label", b.provider),
        "base_url": b.base_url,
        "api_key_masked": mask_key(b.api_key),
        "has_key": bool(b.api_key),
        "model": b.model,
    }


# ---------- provider 预设 ----------
@router.get("/providers")
def providers():
    return [{"key": k, **v} for k, v in PROVIDERS.items()]


# ---------- 机器人 CRUD ----------
@router.get("/bots")
def list_bots(db: Session = Depends(get_db)):
    return [bot_out(b) for b in db.scalars(select(AiBot).order_by(AiBot.id)).all()]


@router.post("/bots")
def create_bot(body: BotIn, db: Session = Depends(get_db)):
    _validate_bot(body)
    b = AiBot(**body.model_dump())
    db.add(b)
    db.commit()
    return bot_out(b)


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
        b = db.get(AiBot, body.bot_id)
        api_key = b.api_key if b else ""
    if not api_key:
        raise HTTPException(400, "请先填写 API Key")
    model = body.model.strip()
    if not model:
        raise HTTPException(400, "请先填写模型名")
    base_url = body.base_url.strip() or PROVIDERS.get(body.provider, {}).get("base_url", "")
    if not base_url.startswith("http"):
        raise HTTPException(400, "接口地址不合法")
    url = base_url.rstrip("/") + "/chat/completions"
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
    except httpx.HTTPError as e:
        return {"ok": False, "message": f"连接失败：{e.__class__.__name__}（网络不通或地址错误）"}
    if resp.status_code == 200:
        return {"ok": True, "message": "连接成功，配置可用"}
    detail = resp.text[:300]
    try:
        detail = resp.json().get("error", {}).get("message") or detail
    except ValueError:
        pass
    hint = {401: "API Key 无效", 404: "接口地址或模型名错误", 429: "限流/欠费"}.get(resp.status_code)
    return {"ok": False, "message": f"失败（{resp.status_code}）：{hint or detail}"}


@router.patch("/bots/{bot_id}")
def update_bot(bot_id: int, body: BotIn, db: Session = Depends(get_db)):
    b = db.get(AiBot, bot_id)
    if not b:
        raise HTTPException(404, "机器人不存在")
    _validate_bot(body)
    data = body.model_dump()
    # key 留空 = 保留原 key（编辑时不重复输入）
    if not data["api_key"]:
        del data["api_key"]
    for k, v in data.items():
        setattr(b, k, v)
    db.commit()
    return bot_out(b)


@router.delete("/bots/{bot_id}")
def delete_bot(bot_id: int, confirm: bool = Query(False), db: Session = Depends(get_db)):
    b = db.get(AiBot, bot_id)
    if not b:
        raise HTTPException(404, "机器人不存在")
    n = db.scalar(select(func.count()).where(AiMessage.bot_id == bot_id)) or 0
    if n and not confirm:
        raise HTTPException(409, f"该机器人有 {n} 条会话记录，删除将一并清除")
    db.query(AiMessage).filter(AiMessage.bot_id == bot_id).delete()
    db.delete(b)
    db.commit()
    return {"ok": True}


def _validate_bot(body: BotIn):
    if not body.name.strip():
        raise HTTPException(400, "机器人名称不能为空")
    if body.provider not in PROVIDERS:
        raise HTTPException(400, "不支持的 provider")
    base_url = body.base_url.strip() or PROVIDERS[body.provider]["base_url"]
    if not base_url.startswith("http"):
        raise HTTPException(400, "接口地址不合法")
    if not body.model.strip():
        raise HTTPException(400, "模型名不能为空")


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
    }


@router.get("/bots/{bot_id}/conversations")
def list_conversations(bot_id: int, db: Session = Depends(get_db)):
    """会话列表（按最近活跃倒序），过滤空会话。"""
    convs = db.scalars(
        select(AiConversation).where(AiConversation.bot_id == bot_id).order_by(AiConversation.updated_at.desc())
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
    c = AiConversation(bot_id=bot_id)
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
    if s.high_score is not None:
        parts.append(f"班级最高分 {s.high_score}（{s.high_scorer or '?'}）")
    return " | ".join(parts)


def _fmt_exam_row(e: Exam, scores: list[Score]) -> str:
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
    lines = ["场次「%s」：" % e.name + " | ".join(parts)]
    lines += ["  " + _fmt_score_row(s) for s in scores]
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
        if exam_id:
            e = db.get(Exam, exam_id)
            if e and e.child_id == child.id:
                scores = db.scalars(select(Score).where(Score.exam_id == exam_id).order_by(Score.id)).all()
                lines.append(_fmt_exam_row(e, scores))
        else:
            q = select(Score).where(Score.child_id == child.id)
            if subject_id:
                q = q.where(Score.subject_id == subject_id)
            if date_from:
                q = q.where(Score.date >= date_from)
            if date_to:
                q = q.where(Score.date <= date_to)
            lines = [_fmt_score_row(s) for s in db.scalars(q.order_by(Score.date, Score.id).limit(100)).all()]

        full = None if exam_id else _child_full_rows(db, child.id)
        # 未选孩子（家长可能问任一学期/科目）或范围内明细太少 → 都必须给全历史
        need_full = (not child_id) or (full and len(lines) <= 5)

        if full and need_full and len(full) > len(lines):
            if lines and has_filter:
                blocks.append(
                    f"【孩子「{child.name}」·当前范围明细】（{len(lines)} 条）：\n" + "\n".join(lines)
                    + f"\n【孩子「{child.name}」·全历史成绩概览】（全部 {len(full)} 条，每条带学期/日期，可据此理解\"本学期\"等说法）：\n"
                    + "\n".join(full)
                )
            else:
                blocks.append(
                    f"【孩子「{child.name}」成绩】（全部 {len(full)} 条，每条带学期/日期，可据此理解\"本学期/上学期\"等说法）：\n"
                    + "\n".join(full)
                )
        else:
            body = "\n".join(lines) if lines else "（该范围内无成绩记录）"
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
)

SSE_ERROR = "data: {\"ai_error\": \"%s\"}\n\n"


# ---------- 流式对话 ----------
@router.post("/chat")
async def chat(body: ChatIn, db: Session = Depends(get_db)):
    bot = db.get(AiBot, body.bot_id)
    if not bot:
        raise HTTPException(404, "机器人不存在")
    if not bot.api_key:
        raise HTTPException(400, "该机器人未配置 API key")
    question = body.question.strip()
    if not question:
        raise HTTPException(400, "问题不能为空")

    # 会话：无 id 则新建；有 id 则校验归属该机器人
    conv = None
    if body.conversation_id:
        conv = db.get(AiConversation, body.conversation_id)
        if not conv or conv.bot_id != bot.id:
            raise HTTPException(404, "会话不存在")
    else:
        conv = AiConversation(bot_id=bot.id)
        db.add(conv)
        db.commit()
        db.refresh(conv)
    conv_id = conv.id

    # 组装消息：系统提示 + 本会话最近历史 + 数据上下文 + 本轮问题
    history = db.scalars(
        select(AiMessage).where(AiMessage.conversation_id == conv_id).order_by(AiMessage.id.desc()).limit(HISTORY_LIMIT)
    ).all()
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in reversed(history):
        msgs.append({"role": m.role, "content": m.content})
    ctx = build_context(db, body.scope)
    msgs.append({"role": "user", "content": f"{ctx}\n\n我的问题：{question}"})

    base_url = (bot.base_url or PROVIDERS.get(bot.provider, {}).get("base_url", "")).rstrip("/")
    url = f"{base_url}/chat/completions"
    payload = {
        "model": bot.model,
        "messages": msgs,
        "stream": True,
    }
    headers = {"Authorization": f"Bearer {bot.api_key}", "Content-Type": "application/json"}

    bot_id, user_question = bot.id, question

    async def gen():
        reply_parts: list[str] = []
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0)) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as resp:
                    if resp.status_code != 200:
                        detail = (await resp.aread()).decode("utf-8", "ignore")[:300]
                        try:
                            detail = json.loads(detail).get("error", {}).get("message") or detail
                        except ValueError:
                            pass
                        yield SSE_ERROR % json.dumps(detail, ensure_ascii=False)
                        return
                    async for chunk in resp.aiter_bytes():
                        reply_parts.append(chunk.decode("utf-8", "ignore"))
                        yield chunk
        except httpx.HTTPError as e:
            yield SSE_ERROR % json.dumps(f"请求模型服务失败：{e.__class__.__name__}: {e}", ensure_ascii=False)
            return
        # 流结束：从累积的原始 SSE 文本解析出完整回复并存历史
        reply = _extract_reply("".join(reply_parts))
        if reply:
            _save_history(bot_id, conv_id, user_question, reply)

    return StreamingResponse(gen(), media_type="text/event-stream")


def _extract_reply(raw: str) -> str:
    """从转发的 SSE 原始文本中拼接出 assistant 完整回复。"""
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


def _save_history(bot_id: int, conv_id: int, question: str, reply: str):
    """保存本轮消息；刷新会话活跃时间；空标题会话用模型生成一句话标题。"""
    from datetime import datetime as _dt

    from ..database import SessionLocal

    with SessionLocal() as ses:
        ses.add(AiMessage(bot_id=bot_id, conversation_id=conv_id, role="user", content=question))
        ses.add(AiMessage(bot_id=bot_id, conversation_id=conv_id, role="assistant", content=reply))
        conv = ses.get(AiConversation, conv_id)
        if conv:
            conv.updated_at = _dt.now()
            if not conv.title:
                conv.title = _gen_title(bot_id, question)[:60]
        ses.commit()


def _gen_title(bot_id: int, question: str) -> str:
    """让模型把本轮问答总结成一句话标题；失败时降级为问题前缀。"""
    from ..database import SessionLocal

    try:
        with SessionLocal() as ses:
            bot = ses.get(AiBot, bot_id)
            if not bot or not bot.api_key:
                return question
            base_url = (bot.base_url or PROVIDERS.get(bot.provider, {}).get("base_url", "")).rstrip("/")
            resp = httpx.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {bot.api_key}", "Content-Type": "application/json"},
                json={
                    "model": bot.model,
                    "messages": [
                        {"role": "system", "content": "用不超过20个字概括用户的问题主题，只输出这句话，不要标点结尾。"},
                        {"role": "user", "content": question[:500]},
                    ],
                    "max_tokens": 40,
                    "temperature": 0.3,
                },
                timeout=30,
            )
            obj = resp.json()
            title = (obj["choices"][0]["message"]["content"] or "").strip().strip('"「」')
            return title or question
    except Exception:
        return question
