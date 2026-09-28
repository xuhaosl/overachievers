from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..auth import AuthDep
from ..database import get_db
from ..models import Child, Exam, Score
from ..schemas import ExamDetail, ExamIn, ExamSummary
from ..term import infer_term

router = APIRouter(prefix="/exams", tags=["exams"], dependencies=[AuthDep])


def _summary(exam: Exam) -> ExamSummary:
    item = ExamSummary.model_validate(exam)
    item.score_count = len(exam.scores)
    earned = sum(s.regular_score + (s.bonus_score or 0) for s in exam.scores)
    total = sum(s.regular_total + (s.bonus_total or 0) for s in exam.scores)
    item.earned_sum = round(earned, 2)
    item.total_sum = round(total, 2)
    item.rate = round(earned / total, 4) if total > 0 else None
    return item


@router.get("", response_model=list[ExamSummary])
def list_exams(child_id: int | None = None, db: Session = Depends(get_db)):
    q = select(Exam).options(joinedload(Exam.scores)).order_by(Exam.date.desc(), Exam.id.desc())
    if child_id:
        q = q.where(Exam.child_id == child_id)
    exams = db.scalars(q).unique().all()
    return [_summary(e) for e in exams]


@router.get("/{exam_id}", response_model=ExamDetail)
def get_exam(exam_id: int, db: Session = Depends(get_db)):
    exam = db.get(Exam, exam_id)
    if not exam:
        raise HTTPException(404, "考试场次不存在")
    detail = ExamDetail.model_validate(_summary(exam))
    from .scores import score_to_out

    detail.scores = [score_to_out(s) for s in sorted(exam.scores, key=lambda s: s.id)]
    return detail


@router.post("", response_model=ExamSummary)
def create_exam(body: ExamIn, db: Session = Depends(get_db)):
    child = db.get(Child, body.child_id)
    if not child:
        raise HTTPException(404, "孩子不存在")
    data = body.model_dump()
    if data.get("grade") is None:
        data["grade"] = child.grade
    if not data.get("term"):
        data["term"] = infer_term(body.date)
    exam = Exam(**data)
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return _summary(exam)


@router.put("/{exam_id}", response_model=ExamSummary)
def update_exam(exam_id: int, body: ExamIn, db: Session = Depends(get_db)):
    exam = db.get(Exam, exam_id)
    if not exam:
        raise HTTPException(404, "考试场次不存在")
    data = body.model_dump()
    if data.get("grade") is None:
        data["grade"] = exam.grade
    if not data.get("term"):
        data["term"] = infer_term(body.date)
    for k, v in data.items():
        setattr(exam, k, v)
    # 场次日期变了，同步其下成绩的日期
    if exam.scores and "date" in data:
        for s in exam.scores:
            s.date = data["date"]
    db.commit()
    db.refresh(exam)
    return _summary(exam)


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
