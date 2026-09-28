"""学期推断：8 月及以后归入新学年上学期，1~7 月归入上一学年的下学期。"""
from datetime import date


def infer_term(d: date) -> str:
    if d.month >= 8:
        return f"{d.year}-{d.year + 1} 上学期"
    return f"{d.year - 1}-{d.year} 下学期"
