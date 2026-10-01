from __future__ import annotations

import json
import re

from datetime import date as PyDate, datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Table, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Child(Base):
    __tablename__ = "children"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50))
    first_enroll_year: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 首次入学时间（小学入学年份）
    gender: Mapped[str] = mapped_column(String(10), default="")  # 男/女/空（已弃用，仅保留历史列）
    student_no: Mapped[str] = mapped_column(String(50), default="")  # 学号（已弃用，从班级提取）
    enroll_year: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 入学年份，填了则自动推算年级
    class_name: Mapped[str] = mapped_column(String(50), default="")  # 班级，如 "3班"
    grade: Mapped[int] = mapped_column(Integer, default=1)  # 1~9 年级；有入学年份时由前端自动推算写入
    school: Mapped[str] = mapped_column(String(100), default="")
    note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    exams: Mapped[list["Exam"]] = relationship(back_populates="child", cascade="all, delete-orphan")
    scores: Mapped[list["Score"]] = relationship(back_populates="child", cascade="all, delete-orphan")


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50))
    color: Mapped[str] = mapped_column(String(20), default="#409EFF")
    version: Mapped[str] = mapped_column(String(50), default="")  # 主要版本（教材版本），如 人教版
    child_id: Mapped[int | None] = mapped_column(ForeignKey("children.id"), nullable=True)  # 归属孩子；NULL=通用
    child: Mapped["Child"] = relationship()
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    units: Mapped[list["Unit"]] = relationship(
        back_populates="subject", cascade="all, delete-orphan", order_by="Unit.id"
    )
    scores: Mapped[list["Score"]] = relationship(back_populates="subject")


class Unit(Base):
    __tablename__ = "units"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"))
    sort_no: Mapped[int] = mapped_column(Integer, default=0)  # 单元序号：第 N 单元
    name: Mapped[str] = mapped_column(String(50), default="")  # 单元名称，用户录入
    term: Mapped[str | None] = mapped_column(String(50), nullable=True)  # 所属学期（短名，如 四上）；NULL=不限学期

    subject: Mapped["Subject"] = relationship(back_populates="units")


class SubjectTerm(Base):
    """学科的学期集合（课程板块 TAB 用），term 为短名（四上/初一下...）。"""

    __tablename__ = "subject_terms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"))
    term: Mapped[str] = mapped_column(String(50))


class SchoolClass(Base):
    """班级 = 孩子的就读经历：归属孩子、阶段、入学时间等都在这里录入，
    孩子管理页的学校/年级/学号等信息自动从这里提取（按时间推算）。"""

    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    child_id: Mapped[int | None] = mapped_column(ForeignKey("children.id"), nullable=True)  # 归属孩子
    stage: Mapped[str] = mapped_column(String(10), default="小学")  # 小学/初中/高中
    enroll_year: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 该阶段入学年份
    school: Mapped[str] = mapped_column(String(100), default="")  # 该阶段就读学校
    name: Mapped[str] = mapped_column(String(50), default="")  # 班级名称，如 "6班"
    size: Mapped[int] = mapped_column(Integer, default=0)  # 班级人数
    student_no: Mapped[str] = mapped_column(String(50), default="")  # 该阶段的学号（各阶段可不同）
    rivals: Mapped[str] = mapped_column(String(200), default="")  # 主要竞争对手，JSON [{no, name}]
    note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def rival_names(rivals: str) -> set:
    """班级竞争对手姓名集合：rivals 存 JSON [{no, name}]，顿号分隔字符串兜底。"""
    names = set()
    if not rivals:
        return names
    try:
        names.update(r.get("name") for r in json.loads(rivals) if isinstance(r, dict) and r.get("name"))
    except (ValueError, TypeError):
        names.update(s.strip() for s in rivals.split("、") if s.strip())
    return names


def rank_num(v) -> float | None:
    """名次值取数字：3 → 3，"前5" → 5，无数字返回 None。"""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return v
    m = re.search(r"\d+(?:\.\d+)?", str(v))
    return float(m.group()) if m else None


# 成绩↔单元 多对多：一条成绩可覆盖多个单元（如一场考试考第一、第二单元）
score_units = Table(
    "score_units",
    Base.metadata,
    Column("score_id", ForeignKey("scores.id"), primary_key=True),
    Column("unit_id", ForeignKey("units.id"), primary_key=True),
)


class Exam(Base):
    """考试场次：期中/期末/模拟等全科考试。单元测试不建场次。"""

    __tablename__ = "exams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("children.id"))
    name: Mapped[str] = mapped_column(String(100))
    date: Mapped[PyDate] = mapped_column(Date)
    type: Mapped[str] = mapped_column(String(50), default="期中考试")
    grade: Mapped[int] = mapped_column(Integer)
    term: Mapped[str] = mapped_column(String(50))
    grade_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 总分年级名次
    class_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 总分班级名次
    class_size: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 班级总人数
    year_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 全科总排名（学年），手动录入
    tags: Mapped[str] = mapped_column(String(200), default="")  # 标签，顿号分隔
    starred: Mapped[bool] = mapped_column(Boolean, default=False)  # 标星：重点场次
    high_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 班级最高分
    high_scorer: Mapped[str] = mapped_column(String(50), default="")  # 最高分的同学
    note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    child: Mapped["Child"] = relationship(back_populates="exams")
    scores: Mapped[list["Score"]] = relationship(
        back_populates="exam", cascade="all, delete-orphan"
    )


class Score(Base):
    __tablename__ = "scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("children.id"))
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"))
    exam_id: Mapped[int | None] = mapped_column(ForeignKey("exams.id"), nullable=True)
    date: Mapped[PyDate] = mapped_column(Date)
    grade: Mapped[int] = mapped_column(Integer)
    term: Mapped[str] = mapped_column(String(50))
    type: Mapped[str] = mapped_column(String(50), default="单元测试")
    regular_score: Mapped[float] = mapped_column(Float)
    regular_total: Mapped[float] = mapped_column(Float)
    bonus_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    bonus_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    grade_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    class_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    class_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tags: Mapped[str] = mapped_column(String(200), default="")  # 标签，顿号分隔，如"粗心、难题"
    starred: Mapped[bool] = mapped_column(Boolean, default=False)  # 标星：重点成绩
    high_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 班级最高分
    high_scorer: Mapped[str] = mapped_column(String(50), default="")  # 最高分的同学
    note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    child: Mapped["Child"] = relationship(back_populates="scores")
    subject: Mapped["Subject"] = relationship(back_populates="scores")
    exam: Mapped["Exam"] = relationship(back_populates="scores")
    units: Mapped[list["Unit"]] = relationship(
        secondary=score_units, lazy="selectin", order_by="Unit.id"
    )
    images: Mapped[list["ScoreImage"]] = relationship(
        back_populates="score", cascade="all, delete-orphan"
    )


class ScoreImage(Base):
    __tablename__ = "score_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    score_id: Mapped[int] = mapped_column(ForeignKey("scores.id"))
    filename: Mapped[str] = mapped_column(String(200))  # data/uploads 下的文件名
    original_name: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    score: Mapped["Score"] = relationship(back_populates="images")
