from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..grading import stage_grade_at
from ..models import Child, SchoolClass
from ..schemas import ClassIn, ClassOut

router = APIRouter(prefix="/classes", tags=["classes"])


def enrich_class(c: SchoolClass, out: ClassOut, db: Session) -> ClassOut:
    """补齐展示字段：归属孩子姓名、按入学时间推算的当前年级/毕业状态。"""
    if c.child_id:
        child = db.get(Child, c.child_id)
        out.child_name = child.name if child else ""
    g = stage_grade_at(c.enroll_year, c.stage)
    if g is not None:
        out.grade = g
        out.graduated = False
    else:
        out.graduated = c.enroll_year is not None  # 填了入学年份但已超出阶段年限
    return out


@router.get("", response_model=list[ClassOut])
def list_classes(db: Session = Depends(get_db)):
    out = []
    for c in db.scalars(select(SchoolClass).order_by(SchoolClass.id)).all():
        out.append(enrich_class(c, ClassOut.model_validate(c), db))
    return out


@router.get("/{class_id}", response_model=ClassOut)
def get_class(class_id: int, db: Session = Depends(get_db)):
    c = db.get(SchoolClass, class_id)
    if not c:
        raise HTTPException(404, "班级不存在")
    return enrich_class(c, ClassOut.model_validate(c), db)


@router.post("", response_model=ClassOut)
def create_class(body: ClassIn, db: Session = Depends(get_db)):
    c = SchoolClass(**body.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return enrich_class(c, ClassOut.model_validate(c), db)


@router.put("/{class_id}", response_model=ClassOut)
def update_class(class_id: int, body: ClassIn, db: Session = Depends(get_db)):
    c = db.get(SchoolClass, class_id)
    if not c:
        raise HTTPException(404, "班级不存在")
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    return enrich_class(c, ClassOut.model_validate(c), db)


@router.delete("/{class_id}")
def delete_class(class_id: int, db: Session = Depends(get_db)):
    c = db.get(SchoolClass, class_id)
    if not c:
        raise HTTPException(404, "班级不存在")
    db.delete(c)
    db.commit()
    return {"ok": True}
