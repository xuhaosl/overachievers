from __future__ import annotations

from datetime import date as Date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- 孩子 ----------
class ChildIn(BaseModel):
    """孩子只录最小信息：首次入学时间 + 姓名；学校/年级/班级/学号等从归属班级自动提取。"""

    name: str = Field(min_length=1, max_length=50)
    first_enroll_year: int | None = Field(default=None, ge=1990, le=2100)  # 首次入学时间（小学入学年份）
    note: str = ""


class ChildOut(ORMModel):
    id: int
    name: str
    first_enroll_year: int | None = None  # 首次入学时间
    student_no: str = ""  # 从当前班级提取
    enroll_year: int | None = None  # 当前班级的入学年份（提取）
    class_name: str = ""  # 当前班级名称（提取）
    stage: str = ""  # 当前班级阶段（提取）
    grade: int = 1  # 当前年级（按班级入学时间推算）
    school: str = ""  # 当前班级学校（提取）
    note: str = ""
    created_at: datetime


class ChildWithCount(ChildOut):
    score_count: int = 0
    exam_count: int = 0


# ---------- 学科 ----------
class SubjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    color: str = "#409EFF"
    version: str = ""  # 主要版本（教材版本）
    child_id: int | None = None  # 归属孩子；None=通用


class SubjectOut(ORMModel):
    id: int
    name: str
    color: str
    version: str = ""
    child_id: int | None = None
    child_name: str = ""


class SubjectCopyIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    color: str = "#409EFF"
    version: str = ""
    child_id: int | None = None


class SubjectWithCount(SubjectOut):
    unit_count: int = 0
    score_count: int = 0


# ---------- 单元 ----------
class UnitIn(BaseModel):
    name: str = Field(default="", max_length=50)  # 单元名称，用户录入
    sort_no: int | None = None  # 单元序号；不传则自动接在末尾
    term: str | None = None  # 所属学期（短名，如 四上）


class ClassIn(BaseModel):
    child_id: int | None = None  # 归属孩子
    stage: str = "小学"  # 小学/初中/高中
    enroll_year: int | None = Field(default=None, ge=1990, le=2100)  # 该阶段入学年份
    school: str = ""
    name: str = ""  # 班级名称
    size: int = 0
    student_no: str = ""  # 该阶段学号
    rivals: str = ""  # 主要竞争对手，顿号分隔
    note: str = ""


class ClassOut(ORMModel):
    id: int
    child_id: int | None = None
    stage: str = "小学"
    enroll_year: int | None = None
    school: str = ""
    name: str = ""
    size: int = 0
    student_no: str = ""
    rivals: str = ""
    note: str = ""
    # 关联展示字段
    child_name: str = ""  # 归属孩子姓名
    grade: int | None = None  # 按入学时间推算的当前年级；None=未入学或已毕业
    graduated: bool = False  # 该阶段是否已毕业


class UnitOut(ORMModel):
    id: int
    subject_id: int
    sort_no: int = 0
    name: str = ""
    term: str | None


class UnitGenerateIn(BaseModel):
    count: int = Field(ge=1, le=50)
    term: str | None = None  # 生成的单元挂到该学期；空=不限学期
    confirm: bool = False  # 有多余单元需删除时，需二次确认


class ExamAttachIn(BaseModel):
    exam_id: int


# ---------- 考试场次 ----------
# 名次值：数字（3）或文字（"前5"）；曲线/比较时取其中的数字
RankValue = int | str | None


class RankInMixin(BaseModel):
    grade_rank: RankValue = None
    class_rank: RankValue = None
    class_size: int | None = None
    high_score: float | None = None  # 班级最高分
    high_scorer: str = ""  # 最高分的同学


class ExamIn(RankInMixin):
    child_id: int
    name: str = Field(min_length=1, max_length=100)
    date: Date
    type: str = "期中考试"
    grade: int | None = Field(default=None, ge=1, le=9)
    term: str | None = None
    year_rank: RankValue = None  # 年级排名（学年），手动录入
    tags: str = ""  # 标签，顿号分隔
    starred: bool = False  # 标星
    note: str = ""


class ExamOut(ORMModel):
    id: int
    child_id: int
    name: str
    date: Date
    type: str
    grade: int
    term: str
    grade_rank: RankValue
    class_rank: RankValue
    class_size: int | None
    year_rank: RankValue = None  # 年级排名（学年）
    stage: str = ""  # 就读阶段（小学/初中/高中），按孩子班级+日期推算
    term_short: str = ""  # 短学期名（如"五上"），用于成长曲线横坐标简写
    tags: str = ""
    starred: bool = False
    high_score: float | None = None
    high_scorer: str = ""
    note: str
    created_at: datetime


class ExamSummary(ExamOut):
    score_count: int = 0
    child_name: str = ""
    subject_names: list[str] = []  # 场内各科成绩的学科名列表
    earned_sum: float = 0
    total_sum: float = 0
    rate: float | None = None  # 得分率 0~1
    regular_earned: float = 0  # 常规得分合计
    bonus_earned: float = 0  # 附加得分合计
    regular_total_sum: float = 0  # 常规总分合计
    bonus_total_sum: float = 0  # 附加总分合计


class ExamDetail(ExamSummary):
    scores: list["ScoreOut"] = []


# ---------- 成绩 ----------
class ScoreIn(RankInMixin):
    child_id: int
    subject_id: int
    exam_id: int | None = None
    unit_ids: list[int] = []  # 覆盖的单元（可多个）
    tags: str = ""  # 标签，顿号分隔
    starred: bool = False  # 标星
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
    date: Date
    grade: int
    term: str
    type: str
    regular_score: float
    regular_total: float
    bonus_score: float | None
    bonus_total: float | None
    grade_rank: RankValue
    class_rank: RankValue
    class_size: int | None
    tags: str = ""
    starred: bool = False
    high_score: float | None = None
    high_scorer: str = ""
    note: str
    # 关联展示字段
    child_name: str = ""
    subject_name: str = ""
    subject_color: str = "#409EFF"
    stage: str = ""  # 就读阶段（小学/初中/高中），按孩子班级与日期推算
    term_short: str = ""  # 短学期名（如"五上"），用于跳转学科详情定位学期TAB
    unit_ids: list[int] = []
    unit_names: str = ""  # 多个单元用顿号连接
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
    latest_display: str = ""  # 如 "得分（附加分）/总分"
    title: str = ""  # 学科单元，如"某学科第N单元"
    meta: str = ""  # 阶段年级学期，如"某年级第N学期"
    class_rank: RankValue = None
    grade_rank: RankValue = None
    tags: str = ""
    starred: bool = False
    note: str = ""


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
