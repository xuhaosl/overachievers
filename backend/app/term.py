"""学期划分：第一学期为 8月~次年1月，第二学期为 2月~7月。"""
import re
from datetime import date

CN_NUM = {1: '一', 2: '二', 3: '三', 4: '四', 5: '五', 6: '六'}
STAGE_LEN = {'小学': 6, '初中': 3, '高中': 3}


def infer_term(d: date) -> str:
    if d.month >= 8:  # 秋季入学：8~12月属新学年第一学期
        return f"{d.year}-{d.year + 1} 第1学期"
    if d.month <= 1:  # 1月属上学年第一学期（第一学期期末在1月）
        return f"{d.year - 1}-{d.year} 第1学期"
    return f"{d.year - 1}-{d.year} 第2学期"  # 2~7月为第二学期


def grade_at_date(enroll_year, d: date):
    """按成绩/场次的日期推算当时读的年级（而非当前年级）。无入学年份返回 None。"""
    if not enroll_year:
        return None
    start = d.year if d.month >= 8 else d.year - 1  # 学年起始年：8月起算新学年
    return min(9, max(1, start - enroll_year + 1))


def short_name(stage: str, grade: int, sem: int) -> str:
    """短学期名：小学"四上/五下"，初中"初一上"，高中"高二下"。sem: 1=上 2=下。"""
    g = CN_NUM.get(grade, str(grade))
    suffix = '上' if sem == 1 else '下'
    if stage == '初中':
        return f'初{g}{suffix}'
    if stage == '高中':
        return f'高{g}{suffix}'
    return f'{g}{suffix}'


def resolve_stage_grade(classes, start_year: int):
    """按孩子就读经历（classes）找学年起始年 start_year（9月）所在阶段与年级。"""
    for c in classes:
        n = STAGE_LEN.get(c.stage)
        if not n or not c.enroll_year:
            continue
        g = start_year - c.enroll_year + 1
        if 1 <= g <= n:
            return c.stage, g
    return None


def short_term_for_date(classes, d: date) -> str | None:
    """按孩子就读经历 + 日期推算短学期名（四上/初一上）。无命中返回 None。"""
    start_year = d.year if d.month >= 8 else d.year - 1
    sem = 1 if (d.month >= 8 or d.month <= 1) else 2
    hit = resolve_stage_grade(classes, start_year)
    if not hit:
        return None
    return short_name(hit[0], hit[1], sem)


def short_term_from_long(classes, long_term: str) -> str | None:
    """把"2023-2024 第1学期"这类长学期名，按孩子就读经历换算成短名（兼容旧的"第一/第二学期"写法）。"""
    m = re.match(r'(\d{4})-\d{4} (第[一二12]学期)', long_term or '')
    if not m:
        return None
    start_year = int(m.group(1))
    # group(2) 是"第2学期/第二学期"整体（含"学期"二字），只判断学期序号部分
    sem = 2 if m.group(2) in ('第二学期', '第2学期') else 1
    hit = resolve_stage_grade(classes, start_year)
    if not hit:
        return None
    return short_name(hit[0], hit[1], sem)
