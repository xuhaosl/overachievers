"""按阶段/入学时间推算年级。

规则：8 月起算新学年；年级 = 学年起始年 - 入学年份 + 1；
小学 6 年、初中 3 年、高中 3 年，超出阶段年数即"已毕业"（返回 None）。
"""

from __future__ import annotations

from datetime import date

STAGE_YEARS = {"小学": 6, "初中": 3, "高中": 3}
STAGES = ["小学", "初中", "高中"]


def stage_grade_at(enroll_year: int | None, stage: str, d: date | None = None) -> int | None:
    """推算某班级记录在日期 d（默认今天）对应的年级。

    返回 None 表示该记录在 d 时无效（尚未入学或已毕业、未填入学年份）。
    """
    if not enroll_year:
        return None
    d = d or date.today()
    start = d.year if d.month >= 8 else d.year - 1
    g = start - int(enroll_year) + 1
    if g < 1 or g > STAGE_YEARS.get(stage, 6):
        return None
    return g
