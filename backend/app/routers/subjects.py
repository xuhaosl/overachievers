from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import AuthDep
from ..database import get_db
from ..models import Score, Subject, Unit
from ..schemas import SubjectIn, SubjectWithCount, UnitGenerateIn, UnitIn, UnitOut

router = APIRouter(prefix="/subjects", tags=["subjects"], dependencies=[AuthDep])


@router.get("", response_model=list[SubjectWithCount])
def list_subjects(db: Session = Depends(get_db)):
    subjects = db.scalars(select(Subject).order_by(Subject.sort, Subject.id)).all()
    unit_counts = dict(db.execute(select(Unit.subject_id, func.count(Unit.id)).group_by(Unit.subject_id)).all())
    score_counts = dict(db.execute(select(Score.subject_id, func.count(Score.id)).group_by(Score.subject_id)).all())
    out = []
    for s in subjects:
        item = SubjectWithCount.model_validate(s)
        item.unit_count = unit_counts.get(s.id, 0)
        item.score_count = score_counts.get(s.id, 0)
        out.append(item)
    return out


@router.post("", response_model=SubjectWithCount)
def create_subject(body: SubjectIn, db: Session = Depends(get_db)):
    subject = Subject(**body.model_dump())
    db.add(subject)
    db.commit()
    db.refresh(subject)
    return SubjectWithCount.model_validate(subject)


@router.put("/{subject_id}", response_model=SubjectWithCount)
def update_subject(subject_id: int, body: SubjectIn, db: Session = Depends(get_db)):
    subject = db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(404, "学科不存在")
    for k, v in body.model_dump().items():
        setattr(subject, k, v)
    db.commit()
    return SubjectWithCount.model_validate(subject)


@router.delete("/{subject_id}")
def delete_subject(
    subject_id: int,
    confirm: bool = Query(False),
    db: Session = Depends(get_db),
):
    subject = db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(404, "学科不存在")
    score_n = db.scalar(select(func.count(Score.id)).where(Score.subject_id == subject_id)) or 0
    if score_n and not confirm:
        raise HTTPException(409, f"该学科下有 {score_n} 条成绩，删除将一并清除")
    db.delete(subject)
    db.commit()
    return {"ok": True}


# ---------- 单元 ----------
@router.get("/{subject_id}/units", response_model=list[UnitOut])
def list_units(subject_id: int, db: Session = Depends(get_db)):
    return db.scalars(
        select(Unit).where(Unit.subject_id == subject_id).order_by(Unit.sort, Unit.id)
    ).all()


@router.post("/{subject_id}/units", response_model=UnitOut)
def create_unit(subject_id: int, body: UnitIn, db: Session = Depends(get_db)):
    subject = db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(404, "学科不存在")
    unit = Unit(subject_id=subject_id, **body.model_dump())
    db.add(unit)
    db.commit()
    db.refresh(unit)
    return unit


@router.post("/{subject_id}/units/generate", response_model=list[UnitOut])
def generate_units(subject_id: int, body: UnitGenerateIn, db: Session = Depends(get_db)):
    """一键生成“第1单元”~“第N单元”，已存在的编号跳过。"""
    subject = db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(404, "学科不存在")
    existing = {
        u.name for u in db.scalars(select(Unit).where(Unit.subject_id == subject_id)).all()
    }
    start_sort = (db.scalar(select(func.max(Unit.sort)).where(Unit.subject_id == subject_id)) or 0)
    created = []
    for i in range(1, body.count + 1):
        name = f"第{i}单元"
        if name in existing:
            continue
        start_sort += 1
        unit = Unit(subject_id=subject_id, name=name, sort=start_sort)
        db.add(unit)
        created.append(unit)
    db.commit()
    for u in created:
        db.refresh(u)
    return created


@router.put("/units/{unit_id}", response_model=UnitOut)
def update_unit(unit_id: int, body: UnitIn, db: Session = Depends(get_db)):
    unit = db.get(Unit, unit_id)
    if not unit:
        raise HTTPException(404, "单元不存在")
    unit.name = body.name
    unit.sort = body.sort
    db.commit()
    return unit


@router.delete("/units/{unit_id}")
def delete_unit(unit_id: int, db: Session = Depends(get_db)):
    unit = db.get(Unit, unit_id)
    if not unit:
        raise HTTPException(404, "单元不存在")
    # 引用该单元的成绩断开关联（成绩本身保留）
    for s in db.scalars(select(Score).where(Score.unit_id == unit_id)).all():
        s.unit_id = None
    db.delete(unit)
    db.commit()
    return {"ok": True}
