from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import AuthDep
from ..database import get_db
from ..grading import stage_grade_at
from ..models import Child, Exam, SchoolClass, Score
from ..schemas import ChildIn, ChildWithCount, ScoreIds
from ..uploads import remove_score_image_files

router = APIRouter(prefix="/children", tags=["children"], dependencies=[AuthDep])


def enrich_children(items: list[ChildWithCount], db: Session) -> list[ChildWithCount]:
    """孩子详情从归属的班级自动提取：取"当前在读"的班级（按时间推算）；
    全部已毕业时取最新一条做历史展示；没有班级记录则保留孩子自身旧值。"""
    recs_by_child: dict[int, list[SchoolClass]] = {}
    for c in db.scalars(select(SchoolClass).where(SchoolClass.child_id.isnot(None))).all():
        recs_by_child.setdefault(c.child_id, []).append(c)
    for item in items:
        recs = sorted(recs_by_child.get(item.id, []), key=lambda x: x.enroll_year or 0, reverse=True)
        current = next((r for r in recs if stage_grade_at(r.enroll_year, r.stage) is not None), None)
        if current is None and recs:
            current = recs[0]
        if current:
            g = stage_grade_at(current.enroll_year, current.stage)
            item.class_name = current.name or ""
            item.stage = current.stage or ""
            item.school = current.school or ""
            item.student_no = current.student_no or ""
            item.enroll_year = current.enroll_year
            if g is not None:
                item.grade = g
    return items


@router.get("", response_model=list[ChildWithCount])
def list_children(db: Session = Depends(get_db)):
    children = db.scalars(select(Child).order_by(Child.id)).all()
    score_counts = dict(db.execute(select(Score.child_id, func.count(Score.id)).group_by(Score.child_id)).all())
    exam_counts = dict(db.execute(select(Exam.child_id, func.count(Exam.id)).group_by(Exam.child_id)).all())
    items = []
    for c in children:
        item = ChildWithCount.model_validate(c)
        item.score_count = score_counts.get(c.id, 0)
        item.exam_count = exam_counts.get(c.id, 0)
        items.append(item)
    return enrich_children(items, db)


@router.post("", response_model=ChildWithCount)
def create_child(body: ChildIn, db: Session = Depends(get_db)):
    child = Child(**body.model_dump())
    db.add(child)
    db.commit()
    db.refresh(child)
    item = ChildWithCount.model_validate(child)
    return enrich_children([item], db)[0]


@router.get("/{child_id}", response_model=ChildWithCount)
def get_child(child_id: int, db: Session = Depends(get_db)):
    child = db.get(Child, child_id)
    if not child:
        raise HTTPException(404, "孩子不存在")
    item = ChildWithCount.model_validate(child)
    item.score_count = db.scalar(select(func.count(Score.id)).where(Score.child_id == child_id)) or 0
    return enrich_children([item], db)[0]


@router.put("/{child_id}", response_model=ChildWithCount)
def update_child(child_id: int, body: ChildIn, db: Session = Depends(get_db)):
    child = db.get(Child, child_id)
    if not child:
        raise HTTPException(404, "孩子不存在")
    for k, v in body.model_dump().items():
        setattr(child, k, v)
    db.commit()
    item = ChildWithCount.model_validate(child)
    return enrich_children([item], db)[0]


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
    remove_score_image_files(db, db.scalars(select(Score).where(Score.child_id == child_id)).all())
    # 级联删除孩子的班级记录（就读经历），避免留下归属为空的孤儿记录
    for c in db.scalars(select(SchoolClass).where(SchoolClass.child_id == child_id)).all():
        db.delete(c)
    db.delete(child)
    db.commit()
    return {"ok": True, "deleted_scores": score_n}


@router.post("/{child_id}/scores/batch-delete", response_model=ScoreIds)
def batch_delete_scores(child_id: int, body: ScoreIds, db: Session = Depends(get_db)):
    """备用接口：批量删除某孩子下的成绩。"""
    targets = []
    for sid in body.ids:
        s = db.get(Score, sid)
        if s and s.child_id == child_id:
            targets.append(s)
    remove_score_image_files(db, targets)
    for s in targets:
        db.delete(s)
    db.commit()
    return body
