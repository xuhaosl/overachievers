"""Agent 工具定义与执行器。

设计原则：
- 读工具直接查库并返回“结构化数据 + 一段可读摘要”；
- 写工具默认不直接落库：先生成 `AgentPendingAction`，用户在界面确认后才执行；
- 导入工具支持 `dry_run`，模型可以先给用户看计划，再请求确认；
- 工具结果会由运行时统一脱敏后再交给模型，原始值只在本机使用。
"""
from __future__ import annotations

import json
import secrets
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from ..grading import STAGE_YEARS, stage_grade_at
from ..models import (
    AgentPendingAction,
    Child,
    Exam,
    Mistake,
    MistakeNotebook,
    MistakeSet,
    SchoolClass,
    Score,
    Subject,
)
from ..term import grade_at_date, infer_term

WRITE_TOOLS = {
    "create_child",
    "create_class",
    "create_subject",
    "create_exam",
    "add_score",
    "create_mistake",
    "import_records",
}


class ToolError(ValueError):
    pass


# ---------------------------------------------------------------------------
# 工具 schema（OpenAI function calling）
# ---------------------------------------------------------------------------

def _fn(name: str, desc: str, props: dict[str, Any] | None = None, required: list[str] | None = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {
                "type": "object",
                "properties": props or {},
                "required": required or [],
                "additionalProperties": False,
            },
        },
    }


TOOL_SPECS: list[dict] = [
    _fn("list_children", "列出所有孩子及其 child_id、当前年级/班级。调用其他工具前先用它确认 child_id。"),
    _fn("list_subjects", "列出学科及 subject_id，可按孩子过滤。", {
        "child_id": {"type": "integer", "description": "孩子 ID；不传=全部"},
    }),
    _fn("list_exams", "列出考试场次（按日期倒序）。", {
        "child_id": {"type": "integer"},
        "limit": {"type": "integer", "description": "默认 10，最多 50"},
    }),
    _fn("list_scores", "按条件查询成绩明细。", {
        "child_id": {"type": "integer"},
        "subject_id": {"type": "integer"},
        "exam_id": {"type": "integer"},
        "date_from": {"type": "string", "description": "YYYY-MM-DD"},
        "date_to": {"type": "string", "description": "YYYY-MM-DD"},
        "limit": {"type": "integer", "description": "默认 50，最多 200"},
    }),
    _fn("list_mistakes", "查询错题，可按孩子/掌握状态过滤。", {
        "child_id": {"type": "integer"},
        "mastered": {"type": "boolean", "description": "true=已掌握；false=未掌握；不传=全部"},
        "limit": {"type": "integer", "description": "默认 50，最多 200"},
    }),
    _fn("get_family_overview", "所有孩子的近期概览：最近成绩、平均得分率、薄弱学科、未掌握错题数。用于回答“孩子最近怎么样”。"),
    _fn("get_child_status", "单个孩子的近期近况：最近考试、各科平均/最新得分率、趋势、薄弱学科、错题知识点。", {
        "child_id": {"type": "integer"},
        "child_name": {"type": "string", "description": "孩子姓名；与 child_id 二选一"},
        "days": {"type": "integer", "description": "回看天数，默认 120，范围 7~730"},
    }),
    _fn("analyze_scores", "对成绩做统计与趋势分析：均分/得分率、波动、分科对比、分学期对比、名次变化、异常低分。", {
        "child_id": {"type": "integer"},
        "subject_id": {"type": "integer"},
        "date_from": {"type": "string", "description": "YYYY-MM-DD"},
        "date_to": {"type": "string", "description": "YYYY-MM-DD"},
    }),
    _fn("privacy_report", "返回本轮对话已脱敏的实体数量与类型（不含原值），用于向用户说明隐私处理。"),
    _fn("create_child", "新增孩子。写操作：默认需要用户确认。", {
        "name": {"type": "string"},
        "first_enroll_year": {"type": "integer", "description": "小学入学年份，可空"},
        "note": {"type": "string"},
    }, ["name"]),
    _fn("create_class", "新增孩子的就读经历/班级。写操作：默认需要用户确认。", {
        "child_id": {"type": "integer"},
        "stage": {"type": "string", "enum": list(STAGE_YEARS)},
        "enroll_year": {"type": "integer"},
        "school": {"type": "string"},
        "name": {"type": "string", "description": "班级名，如 3班"},
        "size": {"type": "integer"},
        "student_no": {"type": "string"},
        "rivals": {"type": "string", "description": "主要竞争对手，顿号分隔"},
        "note": {"type": "string"},
    }, ["child_id", "stage"]),
    _fn("create_subject", "新增学科。写操作：默认需要用户确认。", {
        "name": {"type": "string"},
        "color": {"type": "string"},
        "child_id": {"type": "integer", "description": "归属孩子；空=通用"},
    }, ["name"]),
    _fn("create_exam", "新增考试场次（期中/期末等全科考试）。写操作：默认需要用户确认。", {
        "child_id": {"type": "integer"},
        "name": {"type": "string"},
        "date": {"type": "string", "description": "YYYY-MM-DD"},
        "type": {"type": "string", "description": "单元测试/期中考试/期末考试"},
        "grade": {"type": "integer"},
    }, ["child_id", "name", "date"]),
    _fn("add_score", "新增一条成绩。挂到 exam_id 时日期/年级/学期继承场次；否则必须给日期。写操作：默认需要用户确认。", {
        "child_id": {"type": "integer"},
        "subject_id": {"type": "integer"},
        "exam_id": {"type": "integer"},
        "date": {"type": "string", "description": "YYYY-MM-DD"},
        "type": {"type": "string"},
        "regular_score": {"type": "number"},
        "regular_total": {"type": "number"},
        "bonus_score": {"type": "number"},
        "bonus_total": {"type": "number"},
        "class_rank": {"type": "integer"},
        "grade_rank": {"type": "integer"},
        "class_size": {"type": "integer"},
        "tags": {"type": "string"},
        "note": {"type": "string"},
    }, ["child_id", "subject_id", "regular_score", "regular_total"]),
    _fn("create_mistake", "新增错题；错题本/错题集不存在时自动创建。写操作：默认需要用户确认。", {
        "child_id": {"type": "integer"},
        "notebook": {"type": "string", "description": "错题本名称，默认“默认错题本”"},
        "set": {"type": "string", "description": "错题集名称，默认“未分类”"},
        "question_no": {"type": "string"},
        "title": {"type": "string"},
        "stem": {"type": "string"},
        "my_answer": {"type": "string"},
        "correct_answer": {"type": "string"},
        "explanation": {"type": "string"},
        "reason": {"type": "string"},
        "knowledge_tags": {"type": "string"},
    }, ["child_id"]),
    _fn("import_records", "批量导入：孩子/班级/学科/场次/成绩/错题。先用 dry_run=true 校验并展示计划，用户确认后再 dry_run=false。", {
        "dry_run": {"type": "boolean", "description": "默认 true；只校验不落库"},
        "create_missing": {"type": "boolean", "description": "缺少孩子/学科/场次时自动创建，默认 true"},
        "payload": {
            "type": "object",
            "description": "导入数据；数组元素可用 child/subject/exam 名称或 id 引用",
            "properties": {
                "children": {"type": "array", "items": {"type": "object"}},
                "classes": {"type": "array", "items": {"type": "object"}},
                "subjects": {"type": "array", "items": {"type": "object"}},
                "exams": {"type": "array", "items": {"type": "object"}},
                "scores": {"type": "array", "items": {"type": "object"}},
                "mistakes": {"type": "array", "items": {"type": "object"}},
            },
            "additionalProperties": False,
        },
    }, ["payload"]),
    _fn("confirm_pending_action", "确认并执行一个待确认写操作。只在用户明确说“确认/可以/执行”后调用。", {
        "token": {"type": "string"},
    }, ["token"]),
    _fn("cancel_pending_action", "取消一个待确认写操作。", {
        "token": {"type": "string"},
    }, ["token"]),
]

TOOL_NAMES = [spec["function"]["name"] for spec in TOOL_SPECS]
READ_TOOLS = [n for n in TOOL_NAMES if n not in WRITE_TOOLS and n not in
              ("confirm_pending_action", "cancel_pending_action")]


# ---------------------------------------------------------------------------
# 运行时上下文
# ---------------------------------------------------------------------------

@dataclass
class ToolContext:
    db: Session
    profile: Any
    conversation_id: int
    bot_id: int
    auto_approve: bool = False
    allow_write: bool = True
    engine: Any = None
    # 本轮用户是否明确表达“确认执行”；confirm_pending_action 只在这时为真才放行
    user_confirmed: bool = False

    def pending(self, tool: str, args: dict, summary: str) -> dict:
        token = secrets.token_urlsafe(18)
        row = AgentPendingAction(
            token=token,
            conversation_id=self.conversation_id,
            bot_id=self.bot_id,
            tool=tool,
            args=json.dumps(args, ensure_ascii=False, default=str),
            summary=summary[:2000],
            status="pending",
            expires_at=datetime.now() + timedelta(minutes=30),
        )
        self.db.add(row)
        self.db.commit()
        return {
            "ok": True,
            "status": "pending_confirmation",
            "token": token,
            "summary": summary,
            "message": "已生成待确认操作。请向用户说明将写入的内容，并等待用户确认；用户确认后再调用 confirm_pending_action。",
        }


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

def _rate(s: Score) -> float | None:
    earned = (s.regular_score or 0) + (s.bonus_score or 0)
    total = (s.regular_total or 0) + (s.bonus_total or 0)
    return round(earned / total, 4) if total > 0 else None


def _score_row(s: Score) -> dict:
    return {
        "score_id": s.id,
        "date": s.date.isoformat() if s.date else None,
        "subject": s.subject.name if s.subject else None,
        "subject_id": s.subject_id,
        "type": s.type,
        "regular_score": s.regular_score,
        "regular_total": s.regular_total,
        "bonus_score": s.bonus_score,
        "bonus_total": s.bonus_total,
        "rate": _rate(s),
        "class_rank": s.class_rank,
        "grade_rank": s.grade_rank,
        "class_size": s.class_size,
        "exam_id": s.exam_id,
        "exam_name": s.exam.name if s.exam else None,
        "units": [f"第{u.sort_no}单元" for u in sorted(s.units, key=lambda u: (u.sort_no, u.id))],
        "tags": s.tags or "",
        "note": s.note or "",
        "starred": bool(s.starred),
    }


def _exam_row(e: Exam) -> dict:
    scores = list(e.scores)
    earned = sum((s.regular_score or 0) + (s.bonus_score or 0) for s in scores)
    total = sum((s.regular_total or 0) + (s.bonus_total or 0) for s in scores)
    return {
        "exam_id": e.id,
        "name": e.name,
        "date": e.date.isoformat() if e.date else None,
        "type": e.type,
        "grade": e.grade,
        "term": e.term,
        "earned": round(earned, 2),
        "total": round(total, 2),
        "rate": round(earned / total, 4) if total > 0 else None,
        "class_rank": e.class_rank,
        "grade_rank": e.grade_rank,
        "year_rank": e.year_rank,
        "tags": e.tags or "",
        "note": e.note or "",
    }


def _current_class(db: Session, child: Child) -> tuple[SchoolClass | None, int | None]:
    classes = db.scalars(select(SchoolClass).where(SchoolClass.child_id == child.id)).all()
    for rec in sorted(classes, key=lambda c: c.enroll_year or 0, reverse=True):
        grade = stage_grade_at(rec.enroll_year, rec.stage)
        if grade is not None:
            return rec, grade
    return (classes[0] if classes else None), None


def _child_row(db: Session, child: Child) -> dict:
    rec, grade = _current_class(db, child)
    return {
        "child_id": child.id,
        "name": child.name,
        "first_enroll_year": child.first_enroll_year,
        "grade": grade,
        "stage": rec.stage if rec else "",
        "class_name": rec.name if rec else "",
        "school": rec.school if rec else "",
        "student_no": rec.student_no if rec else "",
    }


def _find_child(db: Session, child_id: int | None = None, child_name: str | None = None) -> Child:
    if child_id:
        child = db.get(Child, int(child_id))
        if not child:
            raise ToolError(f"child_id={child_id} 不存在")
        return child
    if child_name:
        rows = db.scalars(select(Child).where(Child.name == child_name.strip())).all()
        if len(rows) == 1:
            return rows[0]
        if len(rows) > 1:
            raise ToolError("存在同名孩子，请改用 child_id")
        raise ToolError(f"找不到孩子：{child_name}")
    children = db.scalars(select(Child).order_by(Child.id)).all()
    if len(children) == 1:
        return children[0]
    if not children:
        raise ToolError("系统中还没有孩子")
    raise ToolError("请提供 child_id；可用 list_children 查询")


def _find_subject(db: Session, subject_id: int | None = None, name: str | None = None,
                  child_id: int | None = None) -> Subject:
    if subject_id:
        subject = db.get(Subject, int(subject_id))
        if not subject:
            raise ToolError(f"subject_id={subject_id} 不存在")
        return subject
    if not name:
        raise ToolError("请提供 subject_id 或学科名称")
    q = select(Subject).where(Subject.name == name.strip())
    if child_id:
        q = q.where((Subject.child_id == child_id) | (Subject.child_id.is_(None)))
    rows = db.scalars(q.order_by(Subject.child_id.is_(None), Subject.id)).all()
    if not rows:
        raise ToolError(f"找不到学科：{name}")
    return rows[0]


def _parse_date(value: Any, field: str = "date", required: bool = False) -> date | None:
    if value in (None, ""):
        if required:
            raise ToolError(f"缺少 {field}")
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise ToolError(f"{field} 不是合法日期：{value}") from exc


def _num(value: Any, field: str, required: bool = False) -> float | None:
    if value in (None, ""):
        if required:
            raise ToolError(f"缺少 {field}")
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ToolError(f"{field} 不是数字：{value}") from exc


def _text(value: Any, field: str, *, required: bool = False, max_len: int = 500) -> str:
    text = str(value).strip() if value is not None else ""
    if required and not text:
        raise ToolError(f"缺少 {field}")
    return text[:max_len]


# ---------------------------------------------------------------------------
# 读工具
# ---------------------------------------------------------------------------

def list_children(ctx: ToolContext) -> dict:
    children = ctx.db.scalars(select(Child).order_by(Child.id)).all()
    rows = [_child_row(ctx.db, c) for c in children]
    return {"ok": True, "count": len(rows), "children": rows,
            "summary": "；".join(f"{r['name']}(id={r['child_id']}, {r['grade'] or '?'}年级)" for r in rows) or "还没有孩子"}


def list_subjects(ctx: ToolContext, args: dict) -> dict:
    q = select(Subject).order_by(Subject.id)
    child_id = args.get("child_id")
    if child_id:
        q = q.where((Subject.child_id == int(child_id)) | (Subject.child_id.is_(None)))
    rows = ctx.db.scalars(q).all()
    items = [{"subject_id": s.id, "name": s.name, "color": s.color, "child_id": s.child_id} for s in rows]
    return {"ok": True, "count": len(items), "subjects": items,
            "summary": "；".join(f"{s['name']}(id={s['subject_id']})" for s in items) or "还没有学科"}


def list_exams(ctx: ToolContext, args: dict) -> dict:
    limit = max(1, min(int(args.get("limit") or 10), 50))
    q = select(Exam).options(joinedload(Exam.scores)).order_by(Exam.date.desc(), Exam.id.desc()).limit(limit)
    if args.get("child_id"):
        q = q.where(Exam.child_id == int(args["child_id"]))
    rows = [_exam_row(e) for e in ctx.db.scalars(q).unique().all()]
    return {"ok": True, "count": len(rows), "exams": rows,
            "summary": "；".join(f"{x['date']} {x['name']} {x['earned']}/{x['total']}" for x in rows) or "没有场次"}


def list_scores(ctx: ToolContext, args: dict) -> dict:
    limit = max(1, min(int(args.get("limit") or 50), 200))
    q = (select(Score).options(joinedload(Score.subject), joinedload(Score.exam))
         .order_by(Score.date.desc(), Score.id.desc()).limit(limit))
    if args.get("child_id"):
        q = q.where(Score.child_id == int(args["child_id"]))
    if args.get("subject_id"):
        q = q.where(Score.subject_id == int(args["subject_id"]))
    if args.get("exam_id"):
        q = q.where(Score.exam_id == int(args["exam_id"]))
    d1 = _parse_date(args.get("date_from"))
    d2 = _parse_date(args.get("date_to"))
    if d1:
        q = q.where(Score.date >= d1)
    if d2:
        q = q.where(Score.date <= d2)
    rows = [_score_row(s) for s in ctx.db.scalars(q).unique().all()]
    return {"ok": True, "count": len(rows), "scores": rows,
            "summary": "；".join(f"{x['date']} {x['subject']} {x['rate']}" for x in rows[:8]) or "没有成绩"}


def list_mistakes(ctx: ToolContext, args: dict) -> dict:
    limit = max(1, min(int(args.get("limit") or 50), 200))
    q = select(Mistake).order_by(Mistake.id.desc()).limit(limit)
    if args.get("child_id"):
        q = q.where(Mistake.child_id == int(args["child_id"]))
    if isinstance(args.get("mastered"), bool):
        q = q.where(Mistake.mastered.is_(args["mastered"]))
    rows = []
    for m in ctx.db.scalars(q).all():
        rows.append({
            "mistake_id": m.id,
            "child_id": m.child_id,
            "title": m.title or (m.stem or "")[:40],
            "question_no": m.question_no,
            "reason": m.reason,
            "knowledge_tags": m.knowledge_tags,
            "mastered": bool(m.mastered),
            "sets": [st.name for st in m.sets],
            "created_at": m.created_at.isoformat() if m.created_at else None,
        })
    return {"ok": True, "count": len(rows), "mistakes": rows,
            "summary": f"{len(rows)} 道错题" + ("；" + "、".join(r["knowledge_tags"] for r in rows[:5] if r["knowledge_tags"]) if rows else "")}


def _trend(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    n = len(values)
    mean_x = (n - 1) / 2
    mean_y = sum(values) / n
    denom = sum((i - mean_x) ** 2 for i in range(n))
    if denom == 0:
        return None
    return round(sum((i - mean_x) * (v - mean_y) for i, v in enumerate(values)) / denom, 4)


def _top_tags(mistakes: list[Mistake], limit: int = 5) -> list[dict]:
    counts: dict[str, int] = {}
    for m in mistakes:
        for tag in (m.knowledge_tags or "").replace("，", "、").replace(",", "、").replace(";", "、").split("、"):
            tag = tag.strip()
            if tag:
                counts[tag] = counts.get(tag, 0) + 1
    return [{"tag": k, "count": v} for k, v in sorted(counts.items(), key=lambda kv: -kv[1])[:limit]]


def _child_status(ctx: ToolContext, args: dict) -> dict:
    child = _find_child(ctx.db, args.get("child_id"), args.get("child_name"))
    days = max(7, min(int(args.get("days") or 120), 730))
    since = date.today() - timedelta(days=days)
    all_scores = ctx.db.scalars(
        select(Score).options(joinedload(Score.subject), joinedload(Score.exam))
        .where(Score.child_id == child.id).order_by(Score.date.desc(), Score.id.desc()).limit(300)
    ).unique().all()
    recent = [s for s in all_scores if s.date and s.date >= since]
    if not recent:
        recent = all_scores[:20]

    by_subject: dict[str, list[Score]] = {}
    for s in recent:
        name = s.subject.name if s.subject else "未知"
        by_subject.setdefault(name, []).append(s)
    subjects = []
    for name, rows in by_subject.items():
        rows = sorted(rows, key=lambda s: (s.date, s.id))
        rates = [r for r in (_rate(s) for s in rows) if r is not None]
        if not rates:
            continue
        subjects.append({
            "subject": name,
            "count": len(rows),
            "avg_rate": round(statistics.mean(rates), 4),
            "latest_rate": rates[-1],
            "delta": round(rates[-1] - rates[0], 4),
            "latest_date": rows[-1].date.isoformat(),
            "latest_class_rank": rows[-1].class_rank,
            "trend": _trend(rates),
        })
    subjects.sort(key=lambda x: x["avg_rate"])

    exams = ctx.db.scalars(
        select(Exam).options(joinedload(Exam.scores))
        .where(Exam.child_id == child.id).order_by(Exam.date.desc(), Exam.id.desc()).limit(3)
    ).unique().all()
    mistakes = ctx.db.scalars(
        select(Mistake).where(Mistake.child_id == child.id, Mistake.mastered.is_(False))
        .order_by(Mistake.id.desc()).limit(200)
    ).all()
    all_rates = [r for r in (_rate(s) for s in recent) if r is not None]

    data = {
        "child": _child_row(ctx.db, child),
        "window_days": days,
        "score_count": len(recent),
        "avg_rate": round(statistics.mean(all_rates), 4) if all_rates else None,
        "subjects": subjects,
        "weak_subjects": subjects[:3],
        "recent_exams": [_exam_row(e) for e in exams],
        "unmastered_mistakes": len(mistakes),
        "top_knowledge_tags": _top_tags(mistakes),
        "recent_scores": [_score_row(s) for s in recent[:12]],
    }
    parts = [f"{child.name} 近 {days} 天共有 {len(recent)} 条成绩"]
    if data["avg_rate"] is not None:
        parts.append(f"平均得分率 {data['avg_rate'] * 100:.1f}%")
    if subjects:
        parts.append("各科：" + "；".join(
            f"{s['subject']} {s['avg_rate'] * 100:.1f}%（最新 {s['latest_rate'] * 100:.1f}%）" for s in subjects
        ))
        weak = subjects[0]
        parts.append(f"相对薄弱：{weak['subject']}")
    if exams:
        e = _exam_row(exams[0])
        parts.append(f"最近场次：{e['date']} {e['name']} {e['earned']}/{e['total']}")
    if mistakes:
        parts.append(f"未掌握错题 {len(mistakes)} 道" + (
            "，高频知识点：" + "、".join(x["tag"] for x in data["top_knowledge_tags"]) if data["top_knowledge_tags"] else ""
        ))
    return {"ok": True, "summary": "；".join(parts) + "。", "data": data}


def _family_overview(ctx: ToolContext) -> dict:
    children = ctx.db.scalars(select(Child).order_by(Child.id)).all()
    items = []
    for child in children:
        scores = ctx.db.scalars(
            select(Score).options(joinedload(Score.subject))
            .where(Score.child_id == child.id).order_by(Score.date.desc(), Score.id.desc()).limit(30)
        ).unique().all()
        rates = [r for r in (_rate(s) for s in scores) if r is not None]
        by_subject: dict[str, list[float]] = {}
        for s in scores:
            r = _rate(s)
            if r is not None and s.subject:
                by_subject.setdefault(s.subject.name, []).append(r)
        weak = sorted(by_subject.items(), key=lambda kv: statistics.mean(kv[1]))[:2] if by_subject else []
        unmastered = ctx.db.scalar(
            select(func.count(Mistake.id)).where(Mistake.child_id == child.id, Mistake.mastered.is_(False))
        ) or 0
        last_exam = ctx.db.scalars(
            select(Exam).options(joinedload(Exam.scores))
            .where(Exam.child_id == child.id).order_by(Exam.date.desc(), Exam.id.desc()).limit(1)
        ).unique().first()
        items.append({
            "child_id": child.id,
            "name": child.name,
            "grade": _child_row(ctx.db, child)["grade"],
            "recent_score_count": len(scores),
            "avg_rate": round(statistics.mean(rates), 4) if rates else None,
            "weak_subjects": [{"subject": k, "avg_rate": round(statistics.mean(v), 4)} for k, v in weak],
            "unmastered_mistakes": unmastered,
            "last_exam": _exam_row(last_exam) if last_exam else None,
            "latest_scores": [_score_row(s) for s in scores[:5]],
        })
    summary = "；".join(
        f"{x['name']}（{x['grade'] or '?'}年级）" +
        (f" 平均 {x['avg_rate'] * 100:.1f}%" if x['avg_rate'] is not None else " 暂无成绩") +
        (f"，薄弱 {x['weak_subjects'][0]['subject']}" if x['weak_subjects'] else "") +
        f"，未掌握错题 {x['unmastered_mistakes']} 道"
        for x in items
    ) or "还没有孩子"
    return {"ok": True, "summary": summary + "。", "children": items}


def _analyze_scores(ctx: ToolContext, args: dict) -> dict:
    q = (select(Score).options(joinedload(Score.subject), joinedload(Score.exam))
         .order_by(Score.date, Score.id))
    if args.get("child_id"):
        q = q.where(Score.child_id == int(args["child_id"]))
    if args.get("subject_id"):
        q = q.where(Score.subject_id == int(args["subject_id"]))
    d1 = _parse_date(args.get("date_from"))
    d2 = _parse_date(args.get("date_to"))
    if d1:
        q = q.where(Score.date >= d1)
    if d2:
        q = q.where(Score.date <= d2)
    rows = ctx.db.scalars(q).unique().all()
    if not rows:
        return {"ok": True, "summary": "该范围内没有成绩数据。", "data": {"count": 0}}

    enriched = [(s, _rate(s)) for s in rows if _rate(s) is not None]
    rates = [r for _, r in enriched]
    by_subject: dict[str, list[tuple[Score, float]]] = {}
    by_term: dict[str, list[float]] = {}
    for s, r in enriched:
        by_subject.setdefault(s.subject.name if s.subject else "未知", []).append((s, r))
        by_term.setdefault(s.term or "未知", []).append(r)
    subject_stats = []
    for name, items in by_subject.items():
        items = sorted(items, key=lambda x: (x[0].date, x[0].id))
        rs = [r for _, r in items]
        subject_stats.append({
            "subject": name,
            "count": len(rs),
            "avg_rate": round(statistics.mean(rs), 4),
            "min_rate": round(min(rs), 4),
            "max_rate": round(max(rs), 4),
            "volatility": round(statistics.pstdev(rs), 4) if len(rs) > 1 else 0,
            "trend": _trend(rs),
            "first_date": items[0][0].date.isoformat(),
            "last_date": items[-1][0].date.isoformat(),
            "latest_class_rank": items[-1][0].class_rank,
            "first_class_rank": items[0][0].class_rank,
        })
    subject_stats.sort(key=lambda x: x["avg_rate"])
    term_stats = [
        {"term": term, "count": len(rs), "avg_rate": round(statistics.mean(rs), 4),
         "trend": _trend(rs)}
        for term, rs in sorted(by_term.items(), key=lambda kv: kv[0])
    ]
    low = [
        {"date": s.date.isoformat(), "subject": s.subject.name if s.subject else "", "rate": r,
         "exam": s.exam.name if s.exam else None}
        for s, r in enriched if r < 0.6
    ][:20]
    data = {
        "count": len(enriched),
        "avg_rate": round(statistics.mean(rates), 4),
        "min_rate": round(min(rates), 4),
        "max_rate": round(max(rates), 4),
        "volatility": round(statistics.pstdev(rates), 4) if len(rates) > 1 else 0,
        "trend": _trend(rates),
        "subjects": subject_stats,
        "terms": term_stats,
        "low_scores": low,
        "date_from": d1.isoformat() if d1 else None,
        "date_to": d2.isoformat() if d2 else None,
    }
    parts = [f"共 {len(enriched)} 条成绩，平均得分率 {data['avg_rate'] * 100:.1f}%"]
    if subject_stats:
        parts.append("分科：" + "；".join(
            f"{x['subject']} {x['avg_rate'] * 100:.1f}%（波动 {x['volatility'] * 100:.1f}%）"
            for x in subject_stats
        ))
    if len(term_stats) > 1:
        parts.append("分学期：" + "；".join(f"{x['term']} {x['avg_rate'] * 100:.1f}%" for x in term_stats))
    if low:
        parts.append(f"低于 60% 的记录 {len(low)} 条")
    return {"ok": True, "summary": "；".join(parts) + "。", "data": data}


# ---------------------------------------------------------------------------
# 写工具
# ---------------------------------------------------------------------------

def _create_child(ctx: ToolContext, args: dict) -> dict:
    name = _text(args.get("name"), "name", required=True, max_len=50)
    if ctx.db.scalar(select(Child).where(Child.name == name)):
        raise ToolError(f"孩子已存在：{name}")
    child = Child(name=name, first_enroll_year=args.get("first_enroll_year"),
                  note=_text(args.get("note"), "note", max_len=500))
    ctx.db.add(child)
    ctx.db.commit()
    ctx.db.refresh(child)
    return {"ok": True, "summary": f"已新增孩子 {name}（child_id={child.id}）", "child_id": child.id}


def _create_class(ctx: ToolContext, args: dict) -> dict:
    child = _find_child(ctx.db, args.get("child_id"), args.get("child_name"))
    stage = _text(args.get("stage"), "stage", required=True, max_len=10)
    if stage not in STAGE_YEARS:
        raise ToolError("stage 只能是 小学/初中/高中")
    rec = SchoolClass(
        child_id=child.id,
        stage=stage,
        enroll_year=args.get("enroll_year"),
        school=_text(args.get("school"), "school", max_len=100),
        name=_text(args.get("name"), "name", max_len=50),
        size=int(args.get("size") or 0),
        student_no=_text(args.get("student_no"), "student_no", max_len=50),
        rivals=_text(args.get("rivals"), "rivals", max_len=200),
        note=_text(args.get("note"), "note", max_len=500),
    )
    ctx.db.add(rec)
    ctx.db.commit()
    ctx.db.refresh(rec)
    return {"ok": True, "summary": f"已为 {child.name} 新增{stage}就读经历 {rec.name or ''}（class_id={rec.id}）",
            "class_id": rec.id}


def _create_subject(ctx: ToolContext, args: dict) -> dict:
    name = _text(args.get("name"), "name", required=True, max_len=50)
    child_id = args.get("child_id")
    q = select(Subject).where(Subject.name == name)
    q = q.where(Subject.child_id == int(child_id)) if child_id else q.where(Subject.child_id.is_(None))
    if ctx.db.scalar(q):
        raise ToolError(f"学科已存在：{name}")
    subject = Subject(name=name, color=_text(args.get("color"), "color", max_len=20) or "#409EFF",
                      child_id=int(child_id) if child_id else None)
    ctx.db.add(subject)
    ctx.db.commit()
    ctx.db.refresh(subject)
    return {"ok": True, "summary": f"已新增学科 {name}（subject_id={subject.id}）", "subject_id": subject.id}


def _create_exam(ctx: ToolContext, args: dict) -> dict:
    child = _find_child(ctx.db, args.get("child_id"), args.get("child_name"))
    name = _text(args.get("name"), "name", required=True, max_len=100)
    d = _parse_date(args.get("date"), required=True)
    grade = args.get("grade") or grade_at_date(child.enroll_year, d) or child.grade
    exam = Exam(
        child_id=child.id, name=name, date=d, type=_text(args.get("type"), "type", max_len=50) or "期中考试",
        grade=int(grade), term=infer_term(d),
    )
    ctx.db.add(exam)
    ctx.db.commit()
    ctx.db.refresh(exam)
    return {"ok": True, "summary": f"已新增场次 {name}（{d}，exam_id={exam.id}）", "exam_id": exam.id}


def _add_score(ctx: ToolContext, args: dict) -> dict:
    child = _find_child(ctx.db, args.get("child_id"), args.get("child_name"))
    subject = _find_subject(ctx.db, args.get("subject_id"), args.get("subject"), child.id)
    exam = ctx.db.get(Exam, int(args["exam_id"])) if args.get("exam_id") else None
    if args.get("exam_id") and not exam:
        raise ToolError(f"exam_id={args['exam_id']} 不存在")
    if exam:
        d, grade, term = exam.date, exam.grade, exam.term
    else:
        d = _parse_date(args.get("date"), required=True)
        grade = args.get("grade") or grade_at_date(child.enroll_year, d) or child.grade
        term = _text(args.get("term"), "term", max_len=50) or infer_term(d)
    regular_score = _num(args.get("regular_score"), "regular_score", required=True)
    regular_total = _num(args.get("regular_total"), "regular_total", required=True)
    bonus_score = _num(args.get("bonus_score"), "bonus_score")
    bonus_total = _num(args.get("bonus_total"), "bonus_total")
    if (bonus_score is None) != (bonus_total is None):
        raise ToolError("bonus_score 与 bonus_total 必须同时提供")
    score = Score(
        child_id=child.id, subject_id=subject.id, exam_id=exam.id if exam else None,
        date=d, grade=int(grade), term=term,
        type=_text(args.get("type"), "type", max_len=50) or (exam.type if exam else "单元测试"),
        regular_score=regular_score, regular_total=regular_total,
        bonus_score=bonus_score, bonus_total=bonus_total,
        class_rank=args.get("class_rank"), grade_rank=args.get("grade_rank"),
        class_size=args.get("class_size"),
        tags=_text(args.get("tags"), "tags", max_len=200),
        note=_text(args.get("note"), "note", max_len=500),
    )
    ctx.db.add(score)
    ctx.db.commit()
    ctx.db.refresh(score)
    return {"ok": True, "summary": f"已为 {child.name} 新增 {subject.name} 成绩 {regular_score}/{regular_total}（{d}，score_id={score.id}）",
            "score_id": score.id}


def _get_or_create_notebook(db: Session, child: Child, name: str) -> MistakeNotebook:
    nb = db.scalar(select(MistakeNotebook).where(
        MistakeNotebook.child_id == child.id, MistakeNotebook.name == name))
    if nb:
        return nb
    nb = MistakeNotebook(child_id=child.id, name=name)
    db.add(nb)
    db.flush()
    return nb


def _get_or_create_set(db: Session, notebook: MistakeNotebook, name: str) -> MistakeSet:
    st = db.scalar(select(MistakeSet).where(
        MistakeSet.notebook_id == notebook.id, MistakeSet.name == name))
    if st:
        return st
    st = MistakeSet(notebook_id=notebook.id, name=name)
    db.add(st)
    db.flush()
    return st


def _create_mistake(ctx: ToolContext, args: dict) -> dict:
    child = _find_child(ctx.db, args.get("child_id"), args.get("child_name"))
    notebook = _get_or_create_notebook(ctx.db, child, _text(args.get("notebook"), "notebook", max_len=100) or "默认错题本")
    mset = _get_or_create_set(ctx.db, notebook, _text(args.get("set"), "set", max_len=100) or "未分类")
    m = Mistake(
        child_id=child.id,
        question_no=_text(args.get("question_no"), "question_no", max_len=20),
        title=_text(args.get("title"), "title", max_len=120),
        stem=_text(args.get("stem"), "stem", max_len=4000),
        my_answer=_text(args.get("my_answer"), "my_answer", max_len=4000),
        correct_answer=_text(args.get("correct_answer"), "correct_answer", max_len=4000),
        explanation=_text(args.get("explanation"), "explanation", max_len=4000),
        reason=_text(args.get("reason"), "reason", max_len=4000),
        knowledge_tags=_text(args.get("knowledge_tags"), "knowledge_tags", max_len=300),
        source_type="manual",
        sets=[mset],
    )
    ctx.db.add(m)
    ctx.db.commit()
    ctx.db.refresh(m)
    return {"ok": True, "summary": f"已为 {child.name} 新增错题 {m.title or m.question_no or m.id}（mistake_id={m.id}）",
            "mistake_id": m.id}


# ---------------------------------------------------------------------------
# 批量导入
# ---------------------------------------------------------------------------

def _import_records(ctx: ToolContext, args: dict) -> dict:
    dry_run = bool(args.get("dry_run", True))
    create_missing = bool(args.get("create_missing", True))
    payload = args.get("payload") or {}
    if not isinstance(payload, dict):
        raise ToolError("payload 必须是对象")

    arrays = {k: payload.get(k) or [] for k in ("children", "classes", "subjects", "exams", "scores", "mistakes")}
    for key, value in arrays.items():
        if not isinstance(value, list):
            raise ToolError(f"payload.{key} 必须是数组")
    if len(arrays["scores"]) > 500:
        raise ToolError("一次最多导入 500 条成绩")

    errors: list[str] = []
    counts = {k: 0 for k in arrays}

    children = {c.name: c for c in ctx.db.scalars(select(Child)).all()}
    created_children: dict[str, Child] = {}

    def resolve_child(value: Any, where: str) -> Child | None:
        if value in (None, ""):
            if len(children) == 1:
                return next(iter(children.values()))
            errors.append(f"{where}: 缺少 child")
            return None
        if isinstance(value, int) or str(value).isdigit():
            child = ctx.db.get(Child, int(value))
            if not child:
                errors.append(f"{where}: child_id={value} 不存在")
            return child
        name = str(value).strip()
        if name in children:
            return children[name]
        if name in created_children:
            return created_children[name]
        if create_missing:
            child = Child(name=name)
            ctx.db.add(child)
            ctx.db.flush()
            children[name] = child
            created_children[name] = child
            counts["children"] += 1
            return child
        errors.append(f"{where}: 孩子不存在：{name}")
        return None

    # 先显式 children
    for idx, row in enumerate(arrays["children"], 1):
        if not isinstance(row, dict):
            errors.append(f"children[{idx}] 不是对象")
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            errors.append(f"children[{idx}] 缺少 name")
            continue
        if name in children:
            continue
        child = Child(name=name, first_enroll_year=row.get("first_enroll_year"),
                      note=str(row.get("note") or "")[:500])
        ctx.db.add(child)
        ctx.db.flush()
        children[name] = child
        created_children[name] = child
        counts["children"] += 1

    # classes
    for idx, row in enumerate(arrays["classes"], 1):
        if not isinstance(row, dict):
            errors.append(f"classes[{idx}] 不是对象")
            continue
        child = resolve_child(row.get("child") or row.get("child_id"), f"classes[{idx}]")
        if not child:
            continue
        stage = str(row.get("stage") or "小学").strip()
        if stage not in STAGE_YEARS:
            errors.append(f"classes[{idx}] stage 只能是 小学/初中/高中")
            continue
        rec = SchoolClass(
            child_id=child.id, stage=stage, enroll_year=row.get("enroll_year"),
            school=str(row.get("school") or "")[:100], name=str(row.get("name") or "")[:50],
            size=int(row.get("size") or 0), student_no=str(row.get("student_no") or "")[:50],
            rivals=str(row.get("rivals") or "")[:200], note=str(row.get("note") or "")[:500],
        )
        ctx.db.add(rec)
        ctx.db.flush()
        counts["classes"] += 1

    # subjects
    subjects = {(s.name, s.child_id): s for s in ctx.db.scalars(select(Subject)).all()}

    def resolve_subject(value: Any, child_id: int | None, where: str) -> Subject | None:
        if value in (None, ""):
            errors.append(f"{where}: 缺少 subject")
            return None
        if isinstance(value, int) or str(value).isdigit():
            subject = ctx.db.get(Subject, int(value))
            if not subject:
                errors.append(f"{where}: subject_id={value} 不存在")
            return subject
        name = str(value).strip()
        if (name, child_id) in subjects:
            return subjects[(name, child_id)]
        if (name, None) in subjects:
            return subjects[(name, None)]
        if create_missing:
            subject = Subject(name=name, child_id=child_id)
            ctx.db.add(subject)
            ctx.db.flush()
            subjects[(name, child_id)] = subject
            counts["subjects"] += 1
            return subject
        errors.append(f"{where}: 学科不存在：{name}")
        return None

    for idx, row in enumerate(arrays["subjects"], 1):
        if not isinstance(row, dict):
            errors.append(f"subjects[{idx}] 不是对象")
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            errors.append(f"subjects[{idx}] 缺少 name")
            continue
        child_id = row.get("child_id")
        if child_id in (None, "") and row.get("child"):
            child = resolve_child(row.get("child"), f"subjects[{idx}]")
            child_id = child.id if child else None
        if (name, child_id) in subjects:
            continue
        subject = Subject(name=name, color=str(row.get("color") or "#409EFF")[:20],
                          child_id=int(child_id) if child_id not in (None, "") else None)
        ctx.db.add(subject)
        ctx.db.flush()
        subjects[(name, subject.child_id)] = subject
        counts["subjects"] += 1

    # exams
    exams = {(e.child_id, e.name, e.date): e for e in ctx.db.scalars(select(Exam)).all()}

    def resolve_exam(value: Any, child: Child | None, where: str) -> Exam | None:
        if value in (None, ""):
            return None
        if isinstance(value, int) or str(value).isdigit():
            exam = ctx.db.get(Exam, int(value))
            if not exam:
                errors.append(f"{where}: exam_id={value} 不存在")
            return exam
        if not child:
            errors.append(f"{where}: 用名称引用场次时必须提供 child")
            return None
        name = str(value).strip()
        candidates = [e for e in exams.values() if e.child_id == child.id and e.name == name]
        if len(candidates) == 1:
            return candidates[0]
        errors.append(f"{where}: 找不到场次 {name}（请改用 exam_id 或同时提供日期）")
        return None

    for idx, row in enumerate(arrays["exams"], 1):
        if not isinstance(row, dict):
            errors.append(f"exams[{idx}] 不是对象")
            continue
        child = resolve_child(row.get("child") or row.get("child_id"), f"exams[{idx}]")
        if not child:
            continue
        name = str(row.get("name") or "").strip()
        try:
            d = _parse_date(row.get("date"), required=True)
        except ToolError as exc:
            errors.append(f"exams[{idx}]: {exc}")
            continue
        if not name:
            errors.append(f"exams[{idx}] 缺少 name")
            continue
        key = (child.id, name, d)
        if key in exams:
            continue
        grade = row.get("grade") or grade_at_date(child.enroll_year, d) or child.grade
        exam = Exam(child_id=child.id, name=name, date=d,
                    type=str(row.get("type") or "期中考试")[:50], grade=int(grade), term=infer_term(d))
        ctx.db.add(exam)
        ctx.db.flush()
        exams[key] = exam
        counts["exams"] += 1

    # scores
    for idx, row in enumerate(arrays["scores"], 1):
        if not isinstance(row, dict):
            errors.append(f"scores[{idx}] 不是对象")
            continue
        where = f"scores[{idx}]"
        child = resolve_child(row.get("child") or row.get("child_id"), where)
        if not child:
            continue
        subject = resolve_subject(row.get("subject") or row.get("subject_id"), child.id, where)
        if not subject:
            continue
        exam = resolve_exam(row.get("exam") or row.get("exam_id"), child, where)
        if exam:
            d, grade, term, typ = exam.date, exam.grade, exam.term, exam.type
        else:
            try:
                d = _parse_date(row.get("date"), required=True)
            except ToolError as exc:
                errors.append(f"{where}: {exc}")
                continue
            grade = row.get("grade") or grade_at_date(child.enroll_year, d) or child.grade
            term = str(row.get("term") or infer_term(d))
            typ = str(row.get("type") or "单元测试")[:50]
        try:
            regular_score = _num(row.get("regular_score"), "regular_score", required=True)
            regular_total = _num(row.get("regular_total"), "regular_total", required=True)
            bonus_score = _num(row.get("bonus_score"), "bonus_score")
            bonus_total = _num(row.get("bonus_total"), "bonus_total")
        except ToolError as exc:
            errors.append(f"{where}: {exc}")
            continue
        if (bonus_score is None) != (bonus_total is None):
            errors.append(f"{where}: bonus_score 与 bonus_total 必须同时提供")
            continue
        score = Score(
            child_id=child.id, subject_id=subject.id, exam_id=exam.id if exam else None,
            date=d, grade=int(grade), term=term, type=typ,
            regular_score=regular_score, regular_total=regular_total,
            bonus_score=bonus_score, bonus_total=bonus_total,
            class_rank=row.get("class_rank"), grade_rank=row.get("grade_rank"),
            class_size=row.get("class_size"),
            tags=str(row.get("tags") or "")[:200], note=str(row.get("note") or "")[:500],
        )
        ctx.db.add(score)
        ctx.db.flush()
        counts["scores"] += 1

    # mistakes
    for idx, row in enumerate(arrays["mistakes"], 1):
        if not isinstance(row, dict):
            errors.append(f"mistakes[{idx}] 不是对象")
            continue
        where = f"mistakes[{idx}]"
        child = resolve_child(row.get("child") or row.get("child_id"), where)
        if not child:
            continue
        notebook = _get_or_create_notebook(ctx.db, child, str(row.get("notebook") or "默认错题本")[:100])
        mset = _get_or_create_set(ctx.db, notebook, str(row.get("set") or "未分类")[:100])
        m = Mistake(
            child_id=child.id,
            question_no=str(row.get("question_no") or "")[:20],
            title=str(row.get("title") or "")[:120],
            stem=str(row.get("stem") or "")[:4000],
            my_answer=str(row.get("my_answer") or "")[:4000],
            correct_answer=str(row.get("correct_answer") or "")[:4000],
            explanation=str(row.get("explanation") or "")[:4000],
            reason=str(row.get("reason") or "")[:4000],
            knowledge_tags=str(row.get("knowledge_tags") or "")[:300],
            source_type="manual", sets=[mset],
        )
        ctx.db.add(m)
        ctx.db.flush()
        counts["mistakes"] += 1

    if errors:
        ctx.db.rollback()
        return {"ok": False, "error": "导入数据校验失败", "errors": errors[:50], "counts": counts}

    if dry_run:
        ctx.db.rollback()
        return {"ok": True, "dry_run": True, "status": "validated", "counts": counts,
                "summary": "导入计划校验通过（未写入）：" + "、".join(f"{k} {v}" for k, v in counts.items() if v),
                "message": "请向用户展示导入计划；用户确认后再以 dry_run=false 调用。"}

    ctx.db.commit()
    return {"ok": True, "dry_run": False, "counts": counts,
            "summary": "已导入：" + "、".join(f"{k} {v}" for k, v in counts.items() if v),
            "created_child_ids": [c.id for c in created_children.values()]}


# ---------------------------------------------------------------------------
# 待确认动作
# ---------------------------------------------------------------------------

def _summary_for(name: str, args: dict) -> str:
    if name == "create_child":
        return f"新增孩子：{args.get('name')}"
    if name == "create_class":
        return f"新增就读经历：孩子 id={args.get('child_id')}，{args.get('stage')} {args.get('name') or ''}"
    if name == "create_subject":
        return f"新增学科：{args.get('name')}"
    if name == "create_exam":
        return f"新增场次：{args.get('name')}（{args.get('date')}）"
    if name == "add_score":
        return (f"新增成绩：孩子 id={args.get('child_id')}，学科 id={args.get('subject_id')}，"
                f"{args.get('regular_score')}/{args.get('regular_total')}")
    if name == "create_mistake":
        return f"新增错题：{args.get('title') or args.get('question_no') or '未命名'}"
    if name == "import_records":
        payload = args.get("payload") or {}
        parts = [f"{k} {len(v)}" for k, v in payload.items() if isinstance(v, list) and v]
        return "批量导入：" + ("、".join(parts) or "空")
    return f"执行 {name}"


def confirm_pending(ctx: ToolContext, token: str) -> dict:
    token = str(token or "").strip()
    row = ctx.db.scalar(select(AgentPendingAction).where(AgentPendingAction.token == token))
    if not row:
        raise ToolError("待确认操作不存在")
    if row.conversation_id != ctx.conversation_id:
        raise ToolError("该操作不属于当前会话")
    if row.status != "pending":
        raise ToolError(f"该操作状态为 {row.status}，不能重复确认")
    if row.expires_at and row.expires_at < datetime.now():
        row.status = "expired"
        ctx.db.commit()
        raise ToolError("该操作已过期，请重新发起")
    try:
        args = json.loads(row.args or "{}")
    except ValueError:
        raise ToolError("待确认操作参数损坏")
    row.status = "confirmed"
    ctx.db.commit()
    try:
        result = _perform(row.tool, args, ctx, force=True)
        row.result = json.dumps(result, ensure_ascii=False, default=str)[:4000]
        ctx.db.commit()
        return result
    except Exception as exc:
        row.status = "failed"
        row.result = str(exc)[:1000]
        ctx.db.commit()
        if isinstance(exc, ToolError):
            raise
        raise ToolError(f"执行失败：{exc.__class__.__name__}: {exc}") from exc


def cancel_pending(ctx: ToolContext, token: str) -> dict:
    row = ctx.db.scalar(select(AgentPendingAction).where(AgentPendingAction.token == str(token or "")))
    if not row or row.conversation_id != ctx.conversation_id:
        raise ToolError("待确认操作不存在")
    if row.status != "pending":
        raise ToolError(f"该操作状态为 {row.status}")
    row.status = "cancelled"
    ctx.db.commit()
    return {"ok": True, "summary": "已取消待确认操作"}


# ---------------------------------------------------------------------------
# 分发
# ---------------------------------------------------------------------------

def _perform(name: str, args: dict, ctx: ToolContext, force: bool = False) -> dict:
    if name == "list_children":
        return list_children(ctx)
    if name == "list_subjects":
        return list_subjects(ctx, args)
    if name == "list_exams":
        return list_exams(ctx, args)
    if name == "list_scores":
        return list_scores(ctx, args)
    if name == "list_mistakes":
        return list_mistakes(ctx, args)
    if name == "get_family_overview":
        return _family_overview(ctx)
    if name == "get_child_status":
        return _child_status(ctx, args)
    if name == "analyze_scores":
        return _analyze_scores(ctx, args)
    if name == "privacy_report":
        return {"ok": True, "privacy": ctx.engine.snapshot() if ctx.engine else {},
                "summary": "本轮脱敏统计已返回"}
    if name == "create_child":
        return _create_child(ctx, args)
    if name == "create_class":
        return _create_class(ctx, args)
    if name == "create_subject":
        return _create_subject(ctx, args)
    if name == "create_exam":
        return _create_exam(ctx, args)
    if name == "add_score":
        return _add_score(ctx, args)
    if name == "create_mistake":
        return _create_mistake(ctx, args)
    if name == "import_records":
        return _import_records(ctx, args)
    if name == "confirm_pending_action":
        # 必须由用户本轮明确确认，防止模型“自问自答”绕过人工审批
        if not ctx.user_confirmed:
            raise ToolError("用户尚未确认。请先把待确认内容展示给用户，等用户回复“确认/执行”后再调用。")
        return confirm_pending(ctx, args.get("token", ""))
    if name == "cancel_pending_action":
        return cancel_pending(ctx, args.get("token", ""))
    raise ToolError(f"未知工具：{name}")


def execute_tool(name: str, args: dict | None, ctx: ToolContext) -> dict:
    args = args or {}
    try:
        if name in WRITE_TOOLS:
            if not ctx.allow_write:
                return {"ok": False, "error": "当前 Agent 配置为只读，不能写入数据。请让用户在 Agent 设置中开启“允许写入”。"}
            if name == "import_records" and args.get("dry_run", True):
                return _import_records(ctx, args)
            if not ctx.auto_approve and name != "import_records":
                return ctx.pending(name, args, _summary_for(name, args))
            if not ctx.auto_approve and name == "import_records" and args.get("dry_run") is False:
                return ctx.pending(name, args, _summary_for(name, args))
            return _perform(name, args, ctx, force=True)
        return _perform(name, args, ctx)
    except ToolError as exc:
        try:
            ctx.db.rollback()
        except Exception:
            pass
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        try:
            ctx.db.rollback()
        except Exception:
            pass
        return {"ok": False, "error": f"工具执行失败：{exc.__class__.__name__}: {exc}"}


def tool_specs_for(profile: Any) -> list[dict]:
    allowed = None
    if profile is not None and getattr(profile, "tools", ""):
        try:
            allowed = set(json.loads(profile.tools))
        except (ValueError, TypeError):
            allowed = None
    if allowed:
        return [s for s in TOOL_SPECS if s["function"]["name"] in allowed or s["function"]["name"] in
                ("confirm_pending_action", "cancel_pending_action")]
    return TOOL_SPECS
