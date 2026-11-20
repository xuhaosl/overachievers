"""Agent 运行时：多轮工具调用 + SSE 流式输出 + 出站脱敏/入站还原。"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, AsyncIterator

import httpx
from sqlalchemy import select

from .. import providers
from ..database import SessionLocal
from ..models import (
    AgentPendingAction,
    AgentProfile,
    AgentRun,
    AiBot,
    AiConversation,
    AiMessage,
    PrivacyAudit,
)
from ..privacy import PrivacyEngine, StreamRestorer, engine_for_db
from ..security import validate_outbound_url
from .prompts import build_system_prompt
from .tools import TOOL_NAMES, ToolContext, execute_tool, tool_specs_for

MAX_STEPS = 6
HISTORY_LIMIT = 16
SSE_DONE = "data: {\"type\": \"done\"}\n\n"

# 用户在本轮明确表达确认意图，才允许模型调用 confirm_pending_action
CONFIRM_RE = __import__("re").compile(
    r"(确认|确定|可以了?|同意|执行吧?|就这样|好的?[，, ]?(执行|保存|写入|导入)|"
    r"^(ok|yes|y|go|do it)$)",
    __import__("re").I,
)


class ProviderError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _sse(obj: dict) -> str:
    return "data: " + json.dumps(obj, ensure_ascii=False, default=str) + "\n\n"


def _truncate(text: str, limit: int = 4000) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


def _parse_tool_arguments(raw: str) -> dict:
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
    except ValueError as exc:
        raise ProviderError(f"工具参数不是合法 JSON：{raw[:120]}") from exc
    if not isinstance(obj, dict):
        raise ProviderError("工具参数必须是 JSON 对象")
    return obj


async def _stream_completion(bot: AiBot, payload: dict) -> AsyncIterator[dict]:
    """调用 OpenAI 兼容接口，逐行解析 SSE。非 200 抛 ProviderError。"""
    api_key = providers.bot_api_key(bot)
    if not api_key:
        raise ProviderError("该机器人没有可用的 API Key，请先在“智能助手”中配置")
    base_url = providers.validate_provider_url(bot.provider, bot.base_url)
    url = providers.chat_url(base_url)
    timeout = float(getattr(bot, "timeout", 120) or 120)
    headers = providers.headers_for(bot, api_key)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=15.0)) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code != 200:
                    body = (await resp.aread()).decode("utf-8", "ignore")[:500]
                    try:
                        body = json.loads(body).get("error", {}).get("message") or body
                    except ValueError:
                        pass
                    hint = {
                        401: "API Key 无效",
                        403: "无权访问该模型",
                        404: "接口地址或模型名错误",
                        429: "限流或余额不足",
                    }.get(resp.status_code, "")
                    raise ProviderError(f"模型服务返回 {resp.status_code}：{hint or body}", resp.status_code)
                async for line in resp.aiter_lines():
                    line = (line or "").strip()
                    if not line or line.startswith(":"):
                        continue
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except ValueError:
                        continue
                    yield obj
    except httpx.HTTPError as exc:
        raise ProviderError(f"请求模型服务失败：{exc.__class__.__name__}: {exc}") from exc


def _merge_tool_call(acc: dict[int, dict], delta: dict) -> None:
    for item in delta.get("tool_calls") or []:
        idx = int(item.get("index", 0))
        slot = acc.setdefault(idx, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
        if item.get("id"):
            slot["id"] = item["id"]
        fn = item.get("function") or {}
        if fn.get("name"):
            slot["function"]["name"] += fn["name"]
        if fn.get("arguments"):
            slot["function"]["arguments"] += fn["arguments"]


def _usage(obj: dict) -> dict:
    u = obj.get("usage") or {}
    return {k: u.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens") if u.get(k) is not None}


async def _call_model(bot: AiBot, messages: list[dict], tools: list[dict]) -> AsyncIterator[dict]:
    payload = providers.bot_payload(bot, messages, stream=True, tools=tools)
    async for event in _stream_completion(bot, payload):
        yield event


def _load_bot_with_fallback(db, bot: AiBot) -> list[AiBot]:
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


async def agent_event_stream(
    conversation_id: int,
    bot_id: int,
    profile_id: int | None,
    question: str,
    privacy_level: str | None = None,
) -> AsyncIterator[str]:
    """SSE 事件：
    delta / tool_call / tool_result / pending_action / error / done
    """
    db = SessionLocal()
    restorer: StreamRestorer | None = None
    engine: PrivacyEngine | None = None
    steps: list[dict] = []
    run: AgentRun | None = None
    try:
        bot = db.get(AiBot, bot_id)
        conv = db.get(AiConversation, conversation_id)
        if not bot or not conv:
            yield _sse({"type": "error", "error": "机器人或会话不存在"})
            return
        profile = db.get(AgentProfile, profile_id) if profile_id else None
        level = (privacy_level or (profile.privacy_level if profile else "") or
                 conv.privacy_level or "").strip() or "standard"
        if level not in ("off", "standard", "strict"):
            level = "standard"
        engine = engine_for_db(db, level=level)
        restorer = StreamRestorer(engine)

        run = AgentRun(conversation_id=conv.id, bot_id=bot.id,
                       profile_id=profile.id if profile else None, status="running")
        db.add(run)
        db.commit()
        db.refresh(run)

        # ---- 组装出站消息（全部脱敏） ----
        system_prompt = build_system_prompt(profile, engine, db, level)
        safe_system = engine.redact(system_prompt)
        history = db.scalars(
            select(AiMessage)
            .where(AiMessage.conversation_id == conv.id, AiMessage.role.in_(("user", "assistant")))
            .order_by(AiMessage.id.desc()).limit(HISTORY_LIMIT)
        ).all()
        messages: list[dict[str, Any]] = [{"role": "system", "content": safe_system}]
        for msg in reversed(history):
            messages.append({"role": msg.role, "content": engine.redact(msg.content or "")})
        safe_question = engine.redact(question)
        messages.append({"role": "user", "content": safe_question})

        tools = tool_specs_for(profile)
        ctx = ToolContext(
            db=db,
            profile=profile,
            conversation_id=conv.id,
            bot_id=bot.id,
            auto_approve=bool(getattr(profile, "auto_approve", False)),
            allow_write=bool(getattr(profile, "allow_write", True)),
            engine=engine,
        )
        # 只有用户本轮明确表达“确认/执行”时才允许模型调用确认工具，避免模型自问自答直接落库
        ctx.user_confirmed = bool(CONFIRM_RE.search(question))

        chain = _load_bot_with_fallback(db, bot)
        final_text = ""
        last_error = ""
        usage_total: dict[str, int] = {}

        for step_no in range(1, MAX_STEPS + 1):
            pending_calls: dict[int, dict] = {}
            raw_content: list[str] = []
            step_usage: dict[str, int] = {}
            called = False

            # 依次尝试主机器人与回退机器人；只有“尚未产生内容”时才回退
            for candidate in chain:
                called = True
                got_any = False
                try:
                    async for obj in _call_model(candidate, messages, tools):
                        if obj.get("error"):
                            raise ProviderError(str(obj["error"].get("message") or obj["error"]))
                        usage = _usage(obj)
                        if usage:
                            step_usage.update({k: (step_usage.get(k) or 0) + int(v) for k, v in usage.items()})
                        choice = (obj.get("choices") or [{}])[0]
                        delta = choice.get("delta") or {}
                        if delta.get("content"):
                            got_any = True
                            raw_content.append(delta["content"])
                            safe_out = restorer.feed(delta["content"])
                            if safe_out:
                                yield _sse({"type": "delta", "text": safe_out})
                        if delta.get("tool_calls"):
                            got_any = True
                            _merge_tool_call(pending_calls, delta)
                        if choice.get("finish_reason"):
                            break
                    break  # 当前机器人成功
                except ProviderError as exc:
                    if got_any or raw_content or pending_calls:
                        last_error = str(exc)
                        yield _sse({"type": "error", "error": str(exc)})
                        break
                    last_error = str(exc)
                    continue
            else:
                if last_error:
                    yield _sse({"type": "error", "error": last_error})
                    return

            tail = restorer.flush()
            if tail:
                yield _sse({"type": "delta", "text": tail})

            calls = [pending_calls[i] for i in sorted(pending_calls)]
            if calls:
                messages.append({
                    "role": "assistant",
                    "content": "".join(raw_content),
                    "tool_calls": calls,
                })
                for call in calls:
                    name = (call.get("function") or {}).get("name") or ""
                    call_id = call.get("id") or f"call_{step_no}"
                    raw_args = (call.get("function") or {}).get("arguments") or "{}"
                    try:
                        args = _parse_tool_arguments(raw_args)
                    except ProviderError as exc:
                        result = {"ok": False, "error": str(exc)}
                        messages.append({"role": "tool", "tool_call_id": call_id,
                                         "name": name, "content": json.dumps(result, ensure_ascii=False)})
                        steps.append({"type": "tool_result", "name": name, "ok": False, "error": str(exc)})
                        yield _sse({"type": "tool_result", "name": name, "ok": False, "error": str(exc)})
                        continue

                    restored_args = engine.restore_obj(args)
                    unresolved = engine.unresolved_placeholders(restored_args)
                    if unresolved:
                        result = {"ok": False, "error": "存在无法还原的占位符：" + "、".join(unresolved[:5])}
                    else:
                        yield _sse({
                            "type": "tool_call",
                            "name": name,
                            "args": restored_args,
                        })
                        steps.append({"type": "tool_call", "name": name, "args": restored_args})
                        if name not in TOOL_NAMES:
                            result = {"ok": False, "error": f"未知工具：{name}"}
                        else:
                            result = execute_tool(name, restored_args, ctx)

                    safe_result = engine.redact_obj(result)
                    content = json.dumps(safe_result, ensure_ascii=False, default=str)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": name,
                        "content": _truncate(content, 12000),
                    })
                    event = {
                        "type": "tool_result",
                        "name": name,
                        "ok": bool(result.get("ok")),
                        "summary": result.get("summary") or result.get("error") or "",
                        "status": result.get("status"),
                        "token": result.get("token"),
                        "counts": result.get("counts"),
                        "errors": result.get("errors"),
                    }
                    steps.append({k: v for k, v in event.items() if k != "type"})
                    yield _sse(event)
                    if result.get("status") == "pending_confirmation":
                        yield _sse({
                            "type": "pending_action",
                            "token": result.get("token"),
                            "summary": result.get("summary"),
                        })
                # 工具执行后继续下一轮模型调用
                for k, v in step_usage.items():
                    usage_total[k] = usage_total.get(k, 0) + v
                continue

            # 没有工具调用 = 最终回答
            # 模型输出的是占位符文本，落库前必须还原成真实值，否则刷新历史会看到占位符
            final_text = engine.restore("".join(raw_content))
            for k, v in step_usage.items():
                usage_total[k] = usage_total.get(k, 0) + v
            break

        if not final_text:
            # 模型只调用了工具但没有给出最终文本：给用户一个可读兜底
            final_text = "已完成本轮操作。如需继续，请告诉我下一步要做什么。"
            yield _sse({"type": "delta", "text": final_text})
        # ---- 落库（本地保存原文；出站始终脱敏） ----
        now = datetime.now()
        db.add(AiMessage(bot_id=bot.id, conversation_id=conv.id, role="user", content=question,
                         meta=json.dumps({"privacy": engine.snapshot()}, ensure_ascii=False)))
        db.add(AiMessage(bot_id=bot.id, conversation_id=conv.id, role="assistant", content=final_text,
                         meta=json.dumps({"steps": steps, "privacy": engine.snapshot(), "usage": usage_total},
                                         ensure_ascii=False, default=str)))
        conv.updated_at = now
        conv.mode = "agent"
        if not conv.title:
            conv.title = question.strip().replace("\n", " ")[:40] or "Agent 会话"
        run.status = "done"
        run.finished_at = now
        run.steps = json.dumps(steps, ensure_ascii=False, default=str)
        audit = engine.snapshot()
        db.add(PrivacyAudit(
            conversation_id=conv.id, direction="out", level=level,
            counts=json.dumps(audit.get("counts", {}), ensure_ascii=False),
            placeholders=int(audit.get("placeholders", 0)),
            chars=int(audit.get("chars", 0)),
        ))
        db.commit()
        yield _sse({
            "type": "done",
            "conversation_id": conv.id,
            "title": conv.title,
            "usage": usage_total,
            "privacy": audit,
            "steps": steps,
        })
    except Exception as exc:  # pragma: no cover - 运行时兜底
        try:
            db.rollback()
        except Exception:
            pass
        if run is not None:
            try:
                run.status = "error"
                run.error = f"{exc.__class__.__name__}: {exc}"
                run.finished_at = datetime.now()
                db.commit()
            except Exception:
                pass
        yield _sse({"type": "error", "error": f"Agent 运行失败：{exc.__class__.__name__}: {exc}"})
    finally:
        db.close()


def list_pending(db, conversation_id: int) -> list[dict]:
    rows = db.scalars(
        select(AgentPendingAction)
        .where(AgentPendingAction.conversation_id == conversation_id,
               AgentPendingAction.status == "pending")
        .order_by(AgentPendingAction.id.desc())
    ).all()
    return [{
        "token": r.token,
        "tool": r.tool,
        "summary": r.summary,
        "status": r.status,
        "created_at": r.created_at,
        "expires_at": r.expires_at,
    } for r in rows]
