from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..auth import AuthDep
from ..database import get_db
from ..models import Child, Exam, Score, Subject, Unit
from ..schemas import ScoreIn, ScoreOut
from ..term import infer_term

router = APIRouter(prefix="/scores", tags=["scores"], dependencies=[AuthDep])


def score_to_out(s: Score) -> ScoreOut:
    out = ScoreOut.model_validate(s)
    out.child_name = s.child.name if s.child else ""
    out.subject_name = s.subject.name if s.subject else ""
    out.subject_color = s.subject.color if s.subject else "#409EFF"
    out.unit_name = s.unit.name if s.unit else None
    out.exam_name = s.exam.name if s.exam else None
    earned = s.regular_score + (s.bonus_score or 0)
    total = s.regular_total + (s.bonus_total or 0)
    out.earned = round(earned, 2)
    out.total = round(total, 2)
    out.rate = round(earned / total, 4) if total > 0 else 0
    return out


def _apply_exam_defaults(db: Session, data: dict) -> None:
    """挂场次的成绩：日期/年级/学期继承场次。独立成绩：按日期推断学期。"""
    if data.get("exam_id"):
        exam = db.get(Exam, data["exam_id"])
        if not exam:
            raise HTTPException(404, "考试场次不存在")
        data["date"] = exam.date
        data["grade"] = exam.grade
        data["term"] = exam.term
    else:
        if data.get("date") is None:
            raise HTTPException(422, "独立录入的成绩必须填日期")
        if data.get("grade") is None:
            child = db.get(Child, data["child_id"])
            if not child:
                raise HTTPException(404, "孩子不存在")
            data["grade"] = child.grade
        if not data.get("term"):
            data["term"] = infer_term(data["date"])
    # 附加分一致性：一半有一半无时补齐
    if data.get("bonus_score") is not None and data.get("bonus_total") is None:
        raise HTTPException(422, "填了附加得分必须同时填附加总分")
    if data.get("bonus_total") is not None and data.get("bonus_score") is None:
        raise HTTPException(422, "填了附加总分必须同时填附加得分")
    if data.get("unit_id"):
        unit = db.get(Unit, data["unit_id"])
        if unit and data.get("subject_id") != unit.subject_id:
            raise HTTPException(422, "所选单元不属于该学科")


@router.get("", response_model=list[ScoreOut])
def list_scores(
    child_id: int | None = None,
    subject_id: int | None = None,
    exam_id: int | None = None,
    type: str | None = None,
    grade: int | None = None,
    term: str | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
    db: Session = Depends(get_db),
):
    q = (
        select(Score)
        .options(joinedload(Score.child), joinedload(Score.subject), joinedload(Score.unit), joinedload(Score.exam))
        .order_by(Score.date.desc(), Score.id.desc())
    )
    if child_id:
        q = q.where(Score.child_id == child_id)
    if subject_id:
        q = q.where(Score.subject_id == subject_id)
    if exam_id:
        q = q.where(Score.exam_id == exam_id)
    if type:
        q = q.where(Score.type == type)
    if grade:
        q = q.where(Score.grade == grade)
    if term:
        q = q.where(Score.term == term)
    if date_from:
        q = q.where(Score.date >= date_from)
    if date_to:
        q = q.where(Score.date <= date_to)
    return [score_to_out(s) for s in db.scalars(q).unique().all()]


@router.post("", response_model=ScoreOut)
def create_score(body: ScoreIn, db: Session = Depends(get_db)):
    subject = db.get(Subject, body.subject_id)
    if not subject:
        raise HTTPException(404, "学科不存在")
    data = body.model_dump()
    _apply_exam_defaults(db, data)
    score = Score(**data)
    db.add(score)
    db.commit()
    db.refresh(score)
    return score_to_out(score)


@router.put("/{score_id}", response_model=ScoreOut)
def update_score(score_id: int, body: ScoreIn, db: Session = Depends(get_db)):
    score = db.get(Score, score_id)
    if not score:
        raise HTTPException(404, "成绩不存在")
    data = body.model_dump()
    _apply_exam_defaults(db, data)
    for k, v in data.items():
        setattr(score, k, v)
    db.commit()
    db.refresh(score)
    return score_to_out(score)


@router.delete("/{score_id}")
def delete_score(score_id: int, db: Session = Depends(get_db)):
    score = db.get(Score, score_id)
    if not score:
        raise HTTPException(404, "成绩不存在")
    db.delete(score)
    db.commit()
    return {"ok": True}
