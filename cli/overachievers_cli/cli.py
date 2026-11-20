"""CLI 入口：孩子 / 成绩 / 场次 / 错题 / 分析 / Agent / Provider / 隐私。"""
from __future__ import annotations

import json
import sys
from typing import Any

import click

from . import __version__
from .client import CliError, Client

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"], "max_content_width": 110}


def emit(data: Any, as_json: bool, human: str = "") -> None:
    if as_json:
        click.echo(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    elif human:
        click.echo(human)
    else:
        click.echo(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _client(ctx: click.Context) -> Client:
    return ctx.obj["client"]


@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option(__version__, "-V", "--version", prog_name="oa")
@click.option("--base-url", envvar="OA_BASE_URL", default=None, help="服务地址，默认 http://127.0.0.1:8100")
@click.option("--token", envvar="OA_TOKEN", default=None, help="APP_PASSWORD 对应的登录 token")
@click.option("--json", "as_json", is_flag=True, help="输出 JSON（Agent 首选）")
@click.pass_context
def main(ctx: click.Context, base_url: str | None, token: str | None, as_json: bool) -> None:
    """卷王之王 CLI —— 用命令行/Agent 管理成绩、错题与分析。

    \b
    快速开始：
      oa health
      oa children list
      oa status child --name 小明
      oa agent chat "分析一下最近的数学成绩"
    """
    ctx.ensure_object(dict)
    ctx.obj["client"] = Client(base_url=base_url, token=token)
    ctx.obj["json"] = as_json


# ---------------------------------------------------------------------------
# 基础
# ---------------------------------------------------------------------------

@main.command("health")
@click.pass_context
def health(ctx: click.Context) -> None:
    """检查服务连通性与版本。"""
    data = _client(ctx).get("/health")
    emit(data, ctx.obj["json"], f"服务正常：{data}")


@main.group("providers")
def providers_group() -> None:
    """Provider 注册表与机器人配置。"""


@providers_group.command("list")
@click.pass_context
def providers_list(ctx: click.Context) -> None:
    """列出内置 Provider。"""
    rows = _client(ctx).get("/ai/providers")
    lines = [f"{r['key']:<14} {r['label']:<22} {r.get('base_url') or '(自填)'}" for r in rows]
    emit(rows, ctx.obj["json"], "\n".join(lines))


@providers_group.command("bots")
@click.pass_context
def providers_bots(ctx: click.Context) -> None:
    """列出已配置的机器人（Key 已打码）。"""
    rows = _client(ctx).get("/ai/bots")
    lines = [
        f"#{r['id']:<3} {r['name']:<18} {r['provider_label']:<20} model={r['model']:<24} "
        f"key={r['api_key_masked'] or '未配置'} default={'Y' if r.get('is_default') else 'N'}"
        for r in rows
    ]
    emit(rows, ctx.obj["json"], "\n".join(lines) or "还没有机器人")


# ---------------------------------------------------------------------------
# 孩子
# ---------------------------------------------------------------------------

@main.group("children")
def children_group() -> None:
    """孩子管理。"""


@children_group.command("list")
@click.pass_context
def children_list(ctx: click.Context) -> None:
    rows = _client(ctx).get("/children")
    lines = [
        f"#{r['id']:<3} {r['name']:<10} {r.get('stage') or ''}{r.get('grade') or ''}年级 "
        f"{r.get('school') or ''} {r.get('class_name') or ''} 成绩 {r.get('score_count', 0)} 条"
        for r in rows
    ]
    emit(rows, ctx.obj["json"], "\n".join(lines) or "还没有孩子")


@children_group.command("add")
@click.option("--name", required=True, help="孩子姓名")
@click.option("--first-enroll-year", type=int, default=None, help="小学入学年份")
@click.option("--note", default="", help="备注")
@click.pass_context
def children_add(ctx: click.Context, name: str, first_enroll_year: int | None, note: str) -> None:
    data = _client(ctx).post("/children", {
        "name": name, "first_enroll_year": first_enroll_year, "note": note,
    })
    emit(data, ctx.obj["json"], f"已新增孩子 #{data['id']} {data['name']}")


# ---------------------------------------------------------------------------
# 成绩 / 场次
# ---------------------------------------------------------------------------

@main.group("scores")
def scores_group() -> None:
    """成绩查询与录入。"""


@scores_group.command("list")
@click.option("--child-id", type=int, default=None)
@click.option("--subject-id", type=int, default=None)
@click.option("--exam-id", type=int, default=None)
@click.option("--date-from", default=None)
@click.option("--date-to", default=None)
@click.option("--limit", type=int, default=30, show_default=True)
@click.pass_context
def scores_list(ctx: click.Context, child_id: int | None, subject_id: int | None,
                exam_id: int | None, date_from: str | None, date_to: str | None, limit: int) -> None:
    rows = _client(ctx).get(
        "/scores", child_id=child_id, subject_id=subject_id, exam_id=exam_id,
        date_from=date_from, date_to=date_to,
    )
    rows = (rows or [])[:limit]
    lines = [
        f"{r['date']} {r.get('child_name', ''):<8} {r.get('subject_name', ''):<6} "
        f"{r.get('regular_score')}/{r.get('regular_total')} "
        f"({round((r.get('rate') or 0) * 100, 1)}%) 班名次={r.get('class_rank') or '-'} "
        f"年名次={r.get('grade_rank') or '-'} {r.get('tags') or ''}"
        for r in rows
    ]
    emit(rows, ctx.obj["json"], "\n".join(lines) or "没有成绩")


@scores_group.command("add")
@click.option("--child-id", type=int, required=True)
@click.option("--subject-id", type=int, required=True)
@click.option("--score", "regular_score", type=float, required=True)
@click.option("--total", "regular_total", type=float, required=True)
@click.option("--date", "date_str", default=None, help="YYYY-MM-DD；挂场次时可省略")
@click.option("--exam-id", type=int, default=None)
@click.option("--type", "type_", default="单元测试", show_default=True)
@click.option("--class-rank", type=int, default=None)
@click.option("--grade-rank", type=int, default=None)
@click.option("--tags", default="")
@click.option("--note", default="")
@click.pass_context
def scores_add(ctx: click.Context, **kwargs: Any) -> None:
    payload = {k: v for k, v in kwargs.items() if v is not None}
    payload["type"] = payload.pop("type_")
    data = _client(ctx).post("/scores", payload)
    emit(data, ctx.obj["json"], f"已新增成绩 #{data['id']}：{data.get('subject_name')} "
                                f"{data.get('regular_score')}/{data.get('regular_total')}")


@main.group("exams")
def exams_group() -> None:
    """考试场次。"""


@exams_group.command("list")
@click.option("--child-id", type=int, default=None)
@click.option("--limit", type=int, default=10, show_default=True)
@click.pass_context
def exams_list(ctx: click.Context, child_id: int | None, limit: int) -> None:
    rows = _client(ctx).get("/exams", child_id=child_id) or []
    rows = rows[:limit]
    lines = [
        f"#{r['id']:<3} {r['date']} {r.get('child_name', ''):<8} {r['name']:<18} "
        f"{r.get('earned_sum')}/{r.get('total_sum')} 班名次={r.get('class_rank') or '-'} "
        f"年名次={r.get('grade_rank') or '-'}"
        for r in rows
    ]
    emit(rows, ctx.obj["json"], "\n".join(lines) or "没有场次")


# ---------------------------------------------------------------------------
# 错题
# ---------------------------------------------------------------------------

@main.group("mistakes")
def mistakes_group() -> None:
    """错题本。"""


@mistakes_group.command("list")
@click.option("--child-id", type=int, default=None)
@click.option("--limit", type=int, default=20, show_default=True)
@click.pass_context
def mistakes_list(ctx: click.Context, child_id: int | None, limit: int) -> None:
    rows = _client(ctx).get("/mistakes", child_id=child_id) or []
    rows = rows[:limit]
    lines = [
        f"#{r.get('id')} {r.get('question_no') or ''} {(r.get('title') or r.get('stem') or '')[:28]:<30} "
        f"错因={(r.get('reason') or '')[:16]:<18} 知识点={(r.get('knowledge_tags') or '')[:20]:<22} "
        f"{'已掌握' if r.get('mastered') else '未掌握'}"
        for r in rows
    ]
    emit(rows, ctx.obj["json"], "\n".join(lines) or "没有错题")


# ---------------------------------------------------------------------------
# 分析
# ---------------------------------------------------------------------------

@main.group("status")
def status_group() -> None:
    """近况与数据分析。"""


@status_group.command("family")
@click.pass_context
def status_family(ctx: click.Context) -> None:
    """所有孩子的近期概览。"""
    data = _client(ctx).post("/agent/tools/get_family_overview", {})
    emit(data, ctx.obj["json"], json.dumps(data, ensure_ascii=False, indent=2))


@status_group.command("child")
@click.option("--child-id", type=int, default=None)
@click.option("--name", "child_name", default=None, help="孩子姓名")
@click.option("--days", type=int, default=120, show_default=True)
@click.pass_context
def status_child(ctx: click.Context, child_id: int | None, child_name: str | None, days: int) -> None:
    """单个孩子的近况。"""
    data = _client(ctx).post("/agent/tools/get_child_status", {
        "child_id": child_id, "child_name": child_name, "days": days,
    })
    emit(data, ctx.obj["json"], data.get("summary") or json.dumps(data, ensure_ascii=False, indent=2))


@status_group.command("analyze")
@click.option("--child-id", type=int, default=None)
@click.option("--subject-id", type=int, default=None)
@click.option("--date-from", default=None)
@click.option("--date-to", default=None)
@click.pass_context
def status_analyze(ctx: click.Context, child_id: int | None, subject_id: int | None,
                   date_from: str | None, date_to: str | None) -> None:
    """成绩统计与趋势分析。"""
    data = _client(ctx).post("/agent/tools/analyze_scores", {
        "child_id": child_id, "subject_id": subject_id,
        "date_from": date_from, "date_to": date_to,
    })
    emit(data, ctx.obj["json"], data.get("summary") or json.dumps(data, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

@main.group("agent")
def agent_group() -> None:
    """Agent 对话与配置。"""


@agent_group.command("profiles")
@click.pass_context
def agent_profiles(ctx: click.Context) -> None:
    rows = _client(ctx).get("/agent/profiles")
    lines = [
        f"#{r['id']:<3} {r['name']:<14} bot={r.get('bot_id') or '-':<4} "
        f"privacy={r.get('privacy_level') or '默认':<8} write={'Y' if r['allow_write'] else 'N'} "
        f"auto={'Y' if r['auto_approve'] else 'N'} tools={len(r.get('tools') or []) or '全部'}"
        for r in rows
    ]
    emit(rows, ctx.obj["json"], "\n".join(lines) or "还没有 Agent 配置")


@agent_group.command("tools")
@click.pass_context
def agent_tools(ctx: click.Context) -> None:
    data = _client(ctx).get("/agent/tools")
    lines = [f"{t['function']['name']:<24} {t['function']['description'][:70]}" for t in data["tools"]]
    emit(data, ctx.obj["json"], "\n".join(lines))


@agent_group.command("chat")
@click.argument("question")
@click.option("--bot-id", type=int, required=True, help="使用的机器人 ID")
@click.option("--profile-id", type=int, default=None)
@click.option("--conversation-id", type=int, default=None)
@click.option("--privacy-level", type=click.Choice(["off", "standard", "strict"]), default=None)
@click.option("--show-steps", is_flag=True, help="显示工具调用步骤")
@click.pass_context
def agent_chat(ctx: click.Context, question: str, bot_id: int, profile_id: int | None,
               conversation_id: int | None, privacy_level: str | None, show_steps: bool) -> None:
    """与 Agent 对话（流式）。"""
    client = _client(ctx)
    payload = {
        "bot_id": bot_id,
        "profile_id": profile_id,
        "conversation_id": conversation_id,
        "question": question,
        "privacy_level": privacy_level or "",
    }
    as_json = ctx.obj["json"]
    for event in client.stream_sse("/agent/chat", payload):
        kind = event.get("type")
        if kind == "delta":
            if as_json:
                click.echo(json.dumps({"type": "delta", "text": event.get("text", "")}, ensure_ascii=False))
            else:
                click.echo(event.get("text", ""), nl=False)
        elif kind == "tool_call":
            if not as_json and show_steps:
                click.echo(f"\n[tool] {event.get('name')} {json.dumps(event.get('args'), ensure_ascii=False)[:200]}")
        elif kind == "tool_result":
            if as_json:
                click.echo(json.dumps(event, ensure_ascii=False, default=str))
            elif show_steps:
                click.echo(f"[tool] {event.get('name')} -> {'ok' if event.get('ok') else 'error'} "
                           f"{event.get('summary') or ''}")
        elif kind == "pending_action":
            if as_json:
                click.echo(json.dumps(event, ensure_ascii=False))
            else:
                click.echo(f"\n待确认：{event.get('summary')}\ntoken: {event.get('token')}")
        elif kind == "error":
            click.echo(f"\n错误：{event.get('error')}", err=True)
            raise SystemExit(1)
        elif kind == "done":
            if as_json:
                click.echo(json.dumps(event, ensure_ascii=False, default=str))
            break
    if not as_json:
        click.echo()


@agent_group.command("confirm")
@click.argument("token")
@click.pass_context
def agent_confirm(ctx: click.Context, token: str) -> None:
    """确认待执行的写操作。"""
    data = _client(ctx).post(f"/agent/pending/{token}/confirm")
    emit(data, ctx.obj["json"], json.dumps(data, ensure_ascii=False, indent=2))


@agent_group.command("cancel")
@click.argument("token")
@click.pass_context
def agent_cancel(ctx: click.Context, token: str) -> None:
    """取消待执行的写操作。"""
    data = _client(ctx).post(f"/agent/pending/{token}/cancel")
    emit(data, ctx.obj["json"], json.dumps(data, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# 隐私
# ---------------------------------------------------------------------------

@main.group("privacy")
def privacy_group() -> None:
    """儿童隐私脱敏。"""


@privacy_group.command("status")
@click.pass_context
def privacy_status_cmd(ctx: click.Context) -> None:
    data = _client(ctx).get("/agent/privacy/status")
    guard = data["privacy"]["guard"]
    lines = [
        f"默认级别：{data['privacy']['default_level']}",
        f"可选级别：{', '.join(data['privacy']['levels'])}",
        f"AstrLink Guard：installed={guard['installed']} available={guard['available']} {guard.get('reason') or ''}",
        f"密钥加密：{data['secret']['scheme']}（来源 {data['secret']['key_source']}）",
    ]
    emit(data, ctx.obj["json"], "\n".join(lines))


@privacy_group.command("preview")
@click.argument("text")
@click.option("--level", type=click.Choice(["off", "standard", "strict"]), default="standard")
@click.pass_context
def privacy_preview_cmd(ctx: click.Context, text: str, level: str) -> None:
    """预览脱敏结果（含还原校验）。"""
    data = _client(ctx).post("/agent/privacy/preview", {"text": text, "level": level})
    human = (
        f"脱敏后：{data['redacted']}\n"
        f"还原一致：{data['roundtrip_ok']}\n"
        f"实体统计：{json.dumps(data['stats']['counts'], ensure_ascii=False)}"
    )
    emit(data, ctx.obj["json"], human)


@privacy_group.command("audits")
@click.option("--conversation-id", type=int, default=None)
@click.pass_context
def privacy_audits_cmd(ctx: click.Context, conversation_id: int | None) -> None:
    """脱敏审计（只有数量与类型，无原值）。"""
    rows = _client(ctx).get("/agent/privacy/audits", conversation_id=conversation_id)
    lines = [
        f"{r['created_at']} conv={r['conversation_id']} level={r['level']} "
        f"占位符={r['placeholders']} 类型={json.dumps(r['counts'], ensure_ascii=False)}"
        for r in rows
    ]
    emit(rows, ctx.obj["json"], "\n".join(lines) or "暂无审计记录")


def _run() -> None:
    try:
        main(standalone_mode=False)
    except CliError as exc:
        click.echo(f"错误：{exc}", err=True)
        raise SystemExit(exc.code)
    except click.ClickException as exc:
        exc.show()
        raise SystemExit(2)


if __name__ == "__main__":
    _run()
