from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import AuthDep
from ..database import get_db
from ..models import Child, Exam, Score
from ..schemas import ChildIn, ChildWithCount, ScoreIds

router = APIRouter(prefix="/children", tags=["children"], dependencies=[AuthDep])


@router.get("", response_model=list[ChildWithCount])
def list_children(db: Session = Depends(get_db)):
    children = db.scalars(select(Child).order_by(Child.id)).all()
    score_counts = dict(db.execute(select(Score.child_id, func.count(Score.id)).group_by(Score.child_id)).all())
    exam_counts = dict(db.execute(select(Exam.child_id, func.count(Exam.id)).group_by(Exam.child_id)).all())
    out = []
    for c in children:
        item = ChildWithCount.model_validate(c)
        item.score_count = score_counts.get(c.id, 0)
        item.exam_count = exam_counts.get(c.id, 0)
        out.append(item)
    return out


@router.post("", response_model=ChildWithCount)
def create_child(body: ChildIn, db: Session = Depends(get_db)):
    child = Child(**body.model_dump())
    db.add(child)
    db.commit()
    db.refresh(child)
    return ChildWithCount.model_validate(child)


@router.put("/{child_id}", response_model=ChildWithCount)
def update_child(child_id: int, body: ChildIn, db: Session = Depends(get_db)):
    child = db.get(Child, child_id)
    if not child:
        raise HTTPException(404, "孩子不存在")
    for k, v in body.model_dump().items():
        setattr(child, k, v)
    db.commit()
    return ChildWithCount.model_validate(child)


@router.post("/{child_id}/advance-grade", response_model=ChildWithCount)
def advance_grade(child_id: int, db: Session = Depends(get_db)):
    child = db.get(Child, child_id)
    if not child:
        raise HTTPException(404, "孩子不存在")
    if child.grade < 9:
        child.grade += 1
        db.commit()
    return ChildWithCount.model_validate(child)


@router.delete("/{child_id}")
def delete_child(
    child_id: int,
    confirm: bool = Query(False),
    db: Session = Depends(get_db),
):
    child = db.get(Child, child_id)
    if not child:
        raise HTTPException(404, "孩子不存在")
    score_n = db.scalar(select(func.count(Score.id)).where(Score.child_id == child_id)) or 0
    exam_n = db.scalar(select(func.count(Exam.id)).where(Exam.child_id == child_id)) or 0
    if (score_n or exam_n) and not confirm:
        raise HTTPException(409, f"该孩子下有 {exam_n} 场考试、{score_n} 条成绩，删除将一并清除")
    db.delete(child)
    db.commit()
    return {"ok": True, "deleted_scores": score_n}


@router.post("/{child_id}/scores/batch-delete", response_model=ScoreIds)
def batch_delete_scores(child_id: int, body: ScoreIds, db: Session = Depends(get_db)):
    """备用接口：批量删除某孩子下的成绩。"""
    for sid in body.ids:
        s = db.get(Score, sid)
        if s and s.child_id == child_id:
            db.delete(s)
    db.commit()
    return body
