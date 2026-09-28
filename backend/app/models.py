from __future__ import annotations

from datetime import date as PyDate, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Child(Base):
    __tablename__ = "children"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50))
    gender: Mapped[str] = mapped_column(String(10), default="")  # 男/女/空
    birth_date: Mapped[PyDate | None] = mapped_column(Date, nullable=True)
    grade: Mapped[int] = mapped_column(Integer, default=1)  # 1~9 年级
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
    sort: Mapped[int] = mapped_column(Integer, default=0)
    default_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    units: Mapped[list["Unit"]] = relationship(
        back_populates="subject", cascade="all, delete-orphan", order_by="Unit.sort"
    )
    scores: Mapped[list["Score"]] = relationship(back_populates="subject")


class Unit(Base):
    __tablename__ = "units"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"))
    name: Mapped[str] = mapped_column(String(50))
    sort: Mapped[int] = mapped_column(Integer, default=0)

    subject: Mapped["Subject"] = relationship(back_populates="units")


class Exam(Base):
    """考试场次：期中/期末/模拟等全科考试。单元测试不建场次。"""

    __tablename__ = "exams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("children.id"))
    name: Mapped[str] = mapped_column(String(100))
    date: Mapped[PyDate] = mapped_column(Date)
    type: Mapped[str] = mapped_column(String(50), default="期中测试")
    grade: Mapped[int] = mapped_column(Integer)
    term: Mapped[str] = mapped_column(String(50))
    grade_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 总分年级名次
    class_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 总分班级名次
    class_size: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 班级总人数
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
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"), nullable=True)
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
    note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    child: Mapped["Child"] = relationship(back_populates="scores")
    subject: Mapped["Subject"] = relationship(back_populates="scores")
    exam: Mapped["Exam"] = relationship(back_populates="scores")
    unit: Mapped["Unit"] = relationship()
