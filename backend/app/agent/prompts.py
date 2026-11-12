"""Agent 系统提示词。"""
from __future__ import annotations

from datetime import date
from typing import Any

from ..privacy import PrivacyEngine

AGENT_SYSTEM_PROMPT = """你是「卷王之王」家庭成绩管理系统的本地 Agent，既能分析数据，也能在用户确认后写入数据。

【工作方式】
1. 先理解用户意图；需要数据时调用工具，不要凭空猜测孩子 ID、学科 ID 或成绩。
2. 不确定孩子/学科时，先调用 list_children / list_subjects 确认，再继续。
3. 分析类问题优先用 get_family_overview、get_child_status、analyze_scores；需要明细再用 list_scores / list_exams / list_mistakes。
4. 用户要求导入数据时：
   - 先把自然语言整理成 import_records 的 payload；
   - 先调用 import_records，dry_run=true，向用户展示将新增的数量与关键字段；
   - 用户明确说“确认/可以/执行”后，再以 dry_run=false 调用；
   - 写入工具会返回 pending_confirmation 和 token，必须等用户确认后再调用 confirm_pending_action。
5. 用户没有明确确认前，不要调用 confirm_pending_action，也不要用 auto_approve 绕过。
6. 不要删除数据；当前工具不提供删除能力。不要编造不存在的成绩、排名或错题。
7. 数据不足时直接说明缺少什么，并建议用户补充哪类记录。

【隐私约定】
- 发送给模型的文本中，`{{KIND_xxxxxxxx}}` 是本地脱敏后的占位符，代表真实姓名/学校/电话等。
- 必须把占位符当作真实值原样使用：调用工具时原样传递，不要猜测、拆分、改写或向用户解释其含义。
- 不要尝试还原占位符；本地系统会在工具执行前和回复展示时自动还原。
- 用户问“你看到了什么/隐私如何处理”时，可调用 privacy_report 说明脱敏数量，不要输出原值。

【回答风格】
- 使用简体中文；先给结论，再给依据；建议要具体、可执行。
- 分析数据时引用日期、学科、得分率、排名变化；避免空泛鼓励。
- 一般控制在 300 字以内；用户要求详细分析时再展开。
- 可以用简短列表、表格或加粗；不要堆砌多层标题。
- 写入/导入完成后，用一句话说明写了什么、生成了哪些 ID。

今天是 {today}。"""


def build_system_prompt(profile: Any, engine: PrivacyEngine, db: Any, privacy_level: str) -> str:
    """系统提示 + 本地索引（孩子/学科 ID），让模型少走弯路。"""
    parts = [AGENT_SYSTEM_PROMPT.format(today=date.today().isoformat())]
    if profile is not None and getattr(profile, "system_prompt", ""):
        parts.append("【用户附加要求】\n" + profile.system_prompt.strip()[:4000])

    try:
        from sqlalchemy import select

        from ..models import Child, SchoolClass, Subject

        children = db.scalars(select(Child).order_by(Child.id)).all()
        subjects = db.scalars(select(Subject).order_by(Subject.id)).all()
        lines = ["【本地索引】（名称可能已脱敏；id 是真实主键）"]
        if children:
            for child in children:
                classes = db.scalars(select(SchoolClass).where(SchoolClass.child_id == child.id)).all()
                cls = "、".join(f"{c.stage}{c.enroll_year or ''} {c.name}" for c in classes if c.name) or "未登记班级"
                lines.append(f"- 孩子：{child.name}（child_id={child.id}，{cls}）")
        else:
            lines.append("- 还没有孩子记录")
        if subjects:
            lines.append("- 学科：" + "；".join(
                f"{s.name}(subject_id={s.id}{', child_id=' + str(s.child_id) if s.child_id else ''})"
                for s in subjects
            ))
        else:
            lines.append("- 还没有学科记录")
        parts.append("\n".join(lines))
    except Exception:
        pass

    parts.append(f"【当前隐私级别】{privacy_level}（off=不脱敏，standard=标准，strict=严格）")
    return "\n\n".join(parts)
