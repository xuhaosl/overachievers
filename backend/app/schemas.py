from __future__ import annotations

from datetime import date as Date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- 孩子 ----------
class ChildIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    gender: str = ""
    birth_date: Date | None = None
    grade: int = Field(ge=1, le=9)
    school: str = ""
    note: str = ""


class ChildOut(ORMModel):
    id: int
    name: str
    gender: str
    birth_date: Date | None
    grade: int
    school: str
    note: str
    created_at: datetime


class ChildWithCount(ChildOut):
    score_count: int = 0
    exam_count: int = 0


# ---------- 学科 ----------
class SubjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    color: str = "#409EFF"
    sort: int = 0
    default_total: float | None = None


class SubjectOut(ORMModel):
    id: int
    name: str
    color: str
    sort: int
    default_total: float | None


class SubjectWithCount(SubjectOut):
    unit_count: int = 0
    score_count: int = 0


# ---------- 单元 ----------
class UnitIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    sort: int = 0


class UnitOut(ORMModel):
    id: int
    subject_id: int
    name: str
    sort: int


class UnitGenerateIn(BaseModel):
    count: int = Field(ge=1, le=50)


# ---------- 考试场次 ----------
class RankInMixin(BaseModel):
    grade_rank: int | None = None
    class_rank: int | None = None
    class_size: int | None = None


class ExamIn(RankInMixin):
    child_id: int
    name: str = Field(min_length=1, max_length=100)
    date: Date
    type: str = "期中测试"
    grade: int | None = Field(default=None, ge=1, le=9)
    term: str | None = None
    note: str = ""


class ExamOut(ORMModel):
    id: int
    child_id: int
    name: str
    date: Date
    type: str
    grade: int
    term: str
    grade_rank: int | None
    class_rank: int | None
    class_size: int | None
    note: str
    created_at: datetime


class ExamSummary(ExamOut):
    score_count: int = 0
    earned_sum: float = 0
    total_sum: float = 0
    rate: float | None = None  # 得分率 0~1


class ExamDetail(ExamSummary):
    scores: list["ScoreOut"] = []


# ---------- 成绩 ----------
class ScoreIn(RankInMixin):
    child_id: int
    subject_id: int
    exam_id: int | None = None
    unit_id: int | None = None
    date: Date | None = None
    grade: int | None = Field(default=None, ge=1, le=9)
    term: str | None = None
    type: str = "单元测试"
    regular_score: float = Field(ge=0)
    regular_total: float = Field(gt=0)
    bonus_score: float | None = Field(default=None, ge=0)
    bonus_total: float | None = Field(default=None, ge=0)
    note: str = ""


class ScoreOut(ORMModel):
    id: int
    child_id: int
    subject_id: int
    exam_id: int | None
    unit_id: int | None
    date: Date
    grade: int
    term: str
    type: str
    regular_score: float
    regular_total: float
    bonus_score: float | None
    bonus_total: float | None
    grade_rank: int | None
    class_rank: int | None
    class_size: int | None
    note: str
    # 关联展示字段
    child_name: str = ""
    subject_name: str = ""
    subject_color: str = "#409EFF"
    unit_name: str | None = None
    exam_name: str | None = None
    earned: float = 0
    total: float = 0
    rate: float = 0


class ScoreIds(BaseModel):
    ids: list[int]


# ---------- 统计 ----------
class SubjectLatest(ORMModel):
    subject_id: int
    subject_name: str
    subject_color: str
    latest_date: Date | None = None
    latest_rate: float | None = None
    latest_display: str = ""  # 如 "85（10）/110"


class OverviewOut(BaseModel):
    recent_exams: list[ExamSummary] = []
    subject_latest: list[SubjectLatest] = []


# ---------- 认证 ----------
class LoginIn(BaseModel):
    password: str


class LoginOut(BaseModel):
    token: str


class MetaOut(BaseModel):
    auth_required: bool
    version: str = "0.1.0"
