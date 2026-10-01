from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..auth import AuthDep
from ..database import get_db
from ..models import Child, Exam, SchoolClass, Score, rank_num, rival_names
from ..schemas import ExamDetail, ExamIn, ExamSummary
from ..term import grade_at_date, infer_term, resolve_stage_grade, short_term_from_long

router = APIRouter(prefix="/exams", tags=["exams"], dependencies=[AuthDep])


def _summary(db: Session, exam: Exam) -> ExamSummary:
    item = ExamSummary.model_validate(exam)
    item.score_count = len(exam.scores)
    item.child_name = exam.child.name if exam.child else ""
    item.subject_names = [s.subject.name for s in exam.scores if s.subject]
    # 就读阶段 + 竞争对手名单：按孩子班级（就读经历）+ 场次日期推算
    valid_scorers = set()
    if exam.child:
        classes = db.scalars(select(SchoolClass).where(SchoolClass.child_id == exam.child_id)).all()
        valid_scorers = {exam.child.name}
        for cls in classes:
            valid_scorers |= rival_names(cls.rivals)
        start_year = exam.date.year if exam.date.month >= 8 else exam.date.year - 1
        hit = resolve_stage_grade(classes, start_year)
        item.stage = hit[0] if hit else ""
        # 短学期名（如"五上"）：用于成长曲线横坐标简写
        item.term_short = short_term_from_long(classes, exam.term) or ""
    earned = sum(s.regular_score + (s.bonus_score or 0) for s in exam.scores)
    total = sum(s.regular_total + (s.bonus_total or 0) for s in exam.scores)
    item.earned_sum = round(earned, 2)
    item.total_sum = round(total, 2)
    item.rate = round(earned / total, 4) if total > 0 else None
    # 全科第一自动推导：场内所有单科成绩的班级名次都是第1时（"前1"也算），
    # 场次班级排名=1、班级最高分=全科总分、最高得分者=孩子本人
    if exam.scores and all(rank_num(s.class_rank) == 1 for s in exam.scores):
        item.class_rank = 1
        item.high_score = item.earned_sum
        item.high_scorer = item.child_name
    # 最高得分者校验：只能来自班级主要竞争对手（含本人），
    # 不在名单的名字剔除；全部无效则为空（详情页显示"—"）
    if item.high_scorer:
        item.high_scorer = "、".join(n for n in item.high_scorer.split("、") if n in valid_scorers)
    item.regular_earned = round(sum(s.regular_score for s in exam.scores), 2)
    item.bonus_earned = round(sum(s.bonus_score or 0 for s in exam.scores), 2)
    item.regular_total_sum = round(sum(s.regular_total for s in exam.scores), 2)
    item.bonus_total_sum = round(sum(s.bonus_total or 0 for s in exam.scores), 2)
    return item


@router.get("", response_model=list[ExamSummary])
def list_exams(child_id: int | None = None, db: Session = Depends(get_db)):
    q = select(Exam).options(joinedload(Exam.scores)).order_by(Exam.date.desc(), Exam.id.desc())
    if child_id:
        q = q.where(Exam.child_id == child_id)
    exams = db.scalars(q).unique().all()
    return [_summary(db, e) for e in exams]


@router.get("/{exam_id}", response_model=ExamDetail)
def get_exam(exam_id: int, db: Session = Depends(get_db)):
    exam = db.get(Exam, exam_id)
    if not exam:
        raise HTTPException(404, "考试场次不存在")
    detail = ExamDetail.model_validate(_summary(db, exam))
    from .scores import score_to_out

    detail.scores = [score_to_out(db, s) for s in sorted(exam.scores, key=lambda s: s.id)]
    return detail


@router.post("", response_model=ExamSummary)
def create_exam(body: ExamIn, db: Session = Depends(get_db)):
    child = db.get(Child, body.child_id)
    if not child:
        raise HTTPException(404, "孩子不存在")
    data = body.model_dump()
    # 年级按场次日期推算（当时读几年级）；无入学年份才用传入值/孩子当前年级兜底
    g = grade_at_date(child.enroll_year, body.date)
    if g is not None:
        data["grade"] = g
    elif data.get("grade") is None:
        data["grade"] = child.grade
    if not data.get("term"):
        data["term"] = infer_term(body.date)
    exam = Exam(**data)
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return _summary(db, exam)


@router.put("/{exam_id}", response_model=ExamSummary)
def update_exam(exam_id: int, body: ExamIn, db: Session = Depends(get_db)):
    exam = db.get(Exam, exam_id)
    if not exam:
        raise HTTPException(404, "考试场次不存在")
    data = body.model_dump()
    child = db.get(Child, data["child_id"])
    if not child:
        raise HTTPException(404, "孩子不存在")
    # 有入学年份时年级始终按场次日期推算（改日期自动跟随）
    g = grade_at_date(child.enroll_year, body.date)
    if g is not None:
        data["grade"] = g
    elif data.get("grade") is None:
        data["grade"] = exam.grade
    if not data.get("term"):
        data["term"] = infer_term(body.date)
    # 已挂成绩的场次不允许换孩子（场内成绩属于原孩子，换了会不一致）
    if data.get("child_id") != exam.child_id and exam.scores:
        raise HTTPException(422, "场次下已挂有成绩，不能修改孩子；请先在场次详情中移出成绩")
    for k, v in data.items():
        setattr(exam, k, v)
    # 场次日期/年级/学期变了，同步其下成绩
    if exam.scores:
        for s in exam.scores:
            s.date = data["date"]
            s.grade = data["grade"]
            s.term = data["term"]
    # 学年排名联动：同孩子、同年级、同学年的期末考试共用学年排名
    # （如四下期末的年级排名改为13，同学年四上期末的年级排名同步为13）
    if data["type"] == "期末考试":
        sy = data["date"].year if data["date"].month >= 8 else data["date"].year - 1
        for other in db.scalars(
            select(Exam).where(
                Exam.child_id == data["child_id"],
                Exam.grade == data["grade"],
                Exam.type == "期末考试",
                Exam.id != exam.id,
            )
        ).all():
            other_sy = other.date.year if other.date.month >= 8 else other.date.year - 1
            if other_sy == sy:
                other.year_rank = data.get("year_rank")
    db.commit()
    db.refresh(exam)
    return _summary(db, exam)


@router.delete("/{exam_id}")
def delete_exam(
    exam_id: int,
    confirm: bool = Query(False),
    db: Session = Depends(get_db),
):
    exam = db.get(Exam, exam_id)
    if not exam:
        raise HTTPException(404, "考试场次不存在")
    score_n = len(exam.scores)
    if score_n and not confirm:
        raise HTTPException(409, f"该场次下有 {score_n} 条成绩，删除将一并清除")
    db.delete(exam)
    db.commit()
    return {"ok": True, "deleted_scores": score_n}
