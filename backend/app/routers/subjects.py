import re
from datetime import date as Date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import AuthDep
from ..database import get_db
from ..models import Child, SchoolClass, Score, Subject, SubjectTerm, Unit, score_units
from ..schemas import SubjectCopyIn, SubjectIn, SubjectWithCount, UnitGenerateIn, UnitIn, UnitOut
from ..term import short_term_for_date

router = APIRouter(prefix="/subjects", tags=["subjects"], dependencies=[AuthDep])

_CN_NUM = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6}


def _with_child_name(subject: Subject, out: SubjectWithCount) -> SubjectWithCount:
    out.child_name = subject.child.name if subject.child_id else ""
    return out


def _term_sort_key(t: str):
    """短学期名语义排序：一上 < 一下 < 二上 < ... < 初一上 < ...；不认识的排最后。"""
    m = re.match(r'(初|高)?([一二三四五六])(上|下)$', (t or '').strip())
    if not m:
        return (9, 0, 0, t or '')
    stage = {'初': 2, '高': 3}.get(m.group(1), 1)
    num = _CN_NUM.get(m.group(2), 0)
    sem = 1 if m.group(3) == '上' else 2
    return (stage, num, sem, t or '')


@router.get("", response_model=list[SubjectWithCount])
def list_subjects(db: Session = Depends(get_db)):
    subjects = db.scalars(select(Subject).order_by(Subject.id)).all()
    score_counts = dict(db.execute(select(Score.subject_id, func.count(Score.id)).group_by(Score.subject_id)).all())
    out = []
    for s in subjects:
        item = SubjectWithCount.model_validate(s)
        item.score_count = score_counts.get(s.id, 0)
        _with_child_name(s, item)
        out.append(item)
    return out


@router.get("/{subject_id}", response_model=SubjectWithCount)
def get_subject(subject_id: int, db: Session = Depends(get_db)):
    subject = db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(404, "学科不存在")
    score_n = db.scalar(select(func.count(Score.id)).where(Score.subject_id == subject_id)) or 0
    out = SubjectWithCount.model_validate(subject)
    out.score_count = score_n
    _with_child_name(subject, out)
    return out


@router.post("", response_model=SubjectWithCount)
def create_subject(body: SubjectIn, db: Session = Depends(get_db)):
    if body.child_id is not None and not db.get(Child, body.child_id):
        raise HTTPException(422, "归属孩子不存在")
    subject = Subject(**body.model_dump())
    db.add(subject)
    db.commit()
    db.refresh(subject)
    return SubjectWithCount.model_validate(subject)


@router.post("/{subject_id}/copy", response_model=SubjectWithCount)
def copy_subject(subject_id: int, body: SubjectCopyIn, db: Session = Depends(get_db)):
    """复制学科：详情按传入内容创建，并原样复制全部课程（学期 TAB + 各学期单元）。"""
    src = db.get(Subject, subject_id)
    if not src:
        raise HTTPException(404, "学科不存在")
    if body.child_id is not None and not db.get(Child, body.child_id):
        raise HTTPException(422, "归属孩子不存在")
    new = Subject(name=body.name, color=body.color, version=body.version, child_id=body.child_id)
    db.add(new)
    db.flush()
    for u in db.scalars(select(Unit).where(Unit.subject_id == subject_id).order_by(Unit.id)).all():
        db.add(Unit(subject_id=new.id, sort_no=u.sort_no, name=u.name, term=u.term))
    for st in db.scalars(select(SubjectTerm).where(SubjectTerm.subject_id == subject_id)).all():
        db.add(SubjectTerm(subject_id=new.id, term=st.term))
    db.commit()
    db.refresh(new)
    out = SubjectWithCount.model_validate(new)
    out.score_count = 0
    _with_child_name(new, out)
    return out


@router.put("/{subject_id}", response_model=SubjectWithCount)
def update_subject(subject_id: int, body: SubjectIn, db: Session = Depends(get_db)):
    subject = db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(404, "学科不存在")
    if body.child_id is not None and not db.get(Child, body.child_id):
        raise HTTPException(422, "归属孩子不存在")
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


# ---------- 学科学期（课程 TAB） ----------
@router.get("/{subject_id}/terms")
def list_subject_terms(subject_id: int, db: Session = Depends(get_db)):
    names = {t.term for t in db.scalars(select(SubjectTerm).where(SubjectTerm.subject_id == subject_id)).all()}
    for u in db.scalars(select(Unit.term).where(Unit.subject_id == subject_id, Unit.term.is_not(None))).all():
        names.add(u)
    return sorted(names, key=_term_sort_key)


@router.post("/{subject_id}/terms")
def add_subject_term(subject_id: int, body: dict, db: Session = Depends(get_db)):
    term = (body.get("term") or "").strip()
    if not term:
        raise HTTPException(422, "学期名称不能为空")
    subject = db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(404, "学科不存在")
    exists = db.scalar(select(SubjectTerm).where(SubjectTerm.subject_id == subject_id, SubjectTerm.term == term))
    if exists or db.scalar(select(Unit.id).where(Unit.subject_id == subject_id, Unit.term == term).limit(1)):
        raise HTTPException(409, f"该学科已存在学期「{term}」，不能重复添加")
    db.add(SubjectTerm(subject_id=subject_id, term=term))
    db.commit()
    return {"ok": True, "term": term}


@router.delete("/{subject_id}/terms")
def delete_subject_term(subject_id: int, term: str = Query(...), db: Session = Depends(get_db)):
    """删除学科学期：该学期下的单元一并删除（成绩保留、仅断开单元关联）。"""
    for st in db.scalars(select(SubjectTerm).where(SubjectTerm.subject_id == subject_id, SubjectTerm.term == term)).all():
        db.delete(st)
    units = db.scalars(select(Unit).where(Unit.subject_id == subject_id, Unit.term == term)).all()
    for u in units:
        db.execute(score_units.delete().where(score_units.c.unit_id == u.id))
        db.delete(u)
    db.commit()
    return {"ok": True}


# ---------- 学科候选学期（按归属孩子推算，如 四上/初一上） ----------
@router.get("/{subject_id}/term-suggestions")
def term_suggestions(subject_id: int, db: Session = Depends(get_db)):
    """按归属孩子的就读经历，生成可选短学期名列表（一上~高三下）。"""
    subject = db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(404, "学科不存在")
    if not subject.child_id:
        return []
    classes = db.scalars(select(SchoolClass).where(SchoolClass.child_id == subject.child_id)).all()
    if not classes:
        return []
    out = set()
    for c in classes:
        if not c.enroll_year or c.stage not in ("小学", "初中", "高中"):
            continue
        n = {"小学": 6, "初中": 3, "高中": 3}[c.stage]
        for g in range(1, n + 1):
            for sem in (1, 2):
                from ..term import short_name

                out.add(short_name(c.stage, g, sem))
    return sorted(out, key=_term_sort_key)


# ---------- 单元 ----------
def _resolve_term(db: Session, subject: Subject, child_id: int | None, d: Date | None) -> str | None:
    """录成绩联动：按孩子+日期推算短学期名（四上/初一上）。"""
    if not child_id or not d:
        return None
    classes = db.scalars(select(SchoolClass).where(SchoolClass.child_id == child_id)).all()
    return short_term_for_date(classes, d)


@router.get("/{subject_id}/units", response_model=list[UnitOut])
def list_units(
    subject_id: int,
    term: str | None = Query(None),
    child_id: int | None = Query(None),  # 录成绩联动：传孩子+日期则按日期推算学期
    date: Date | None = Query(None),
    db: Session = Depends(get_db),
):
    """列出单元；传 term（或 child_id+date 推算）时返回该学期＋不限学期的单元。"""
    subject = db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(404, "学科不存在")
    if child_id and date:
        term = _resolve_term(db, subject, child_id, date) or term
    q = select(Unit).where(Unit.subject_id == subject_id)
    if term:
        q = q.where((Unit.term == term) | (Unit.term.is_(None)))
    q = q.order_by(Unit.sort_no, Unit.id)
    return db.scalars(q).all()


@router.post("/{subject_id}/units", response_model=UnitOut)
def create_unit(subject_id: int, body: UnitIn, db: Session = Depends(get_db)):
    subject = db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(404, "学科不存在")
    data = body.model_dump()
    if data.get("sort_no") is None:
        max_no = db.scalar(
            select(func.max(Unit.sort_no)).where(Unit.subject_id == subject_id, Unit.term == (data.get("term") or None))
        )
        data["sort_no"] = (max_no or 0) + 1
    unit = Unit(subject_id=subject_id, **data)
    db.add(unit)
    db.commit()
    db.refresh(unit)
    return unit


@router.post("/{subject_id}/units/generate", response_model=list[UnitOut])
def generate_units(subject_id: int, body: UnitGenerateIn, db: Session = Depends(get_db)):
    """生成"第1~第N单元"：按序号补齐缺失；超出 N 的多余单元删除（需 confirm，成绩保留、仅断开单元关联）。"""
    subject = db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(404, "学科不存在")
    if body.term:
        legacy = db.scalars(
            select(Unit).where(Unit.subject_id == subject_id, Unit.term.is_(None))
        ).all()
        for u in legacy:
            u.term = body.term
        db.flush()
    q = select(Unit).where(Unit.subject_id == subject_id)
    q = q.where(Unit.term == body.term) if body.term else q.where(Unit.term.is_(None))
    units = db.scalars(q.order_by(Unit.sort_no, Unit.id)).all()
    nos = {u.sort_no for u in units}
    missing = [i for i in range(1, body.count + 1) if i not in nos]
    extras = [u for u in units if u.sort_no > body.count]
    if extras and not body.confirm:
        sample = "、".join(_unit_label(u) for u in extras[:10])
        raise HTTPException(
            409,
            f"当前学期已有 {len(units)} 个单元，超出 {body.count} 的部分将被删除：{sample}。"
            "关联的成绩会保留，只是不再标注单元。确定继续吗？",
        )
    created = []
    for i in missing:
        unit = Unit(subject_id=subject_id, sort_no=i, name="", term=body.term)
        db.add(unit)
        created.append(unit)
    for u in extras:
        db.execute(score_units.delete().where(score_units.c.unit_id == u.id))
        db.delete(u)
    db.commit()
    for u in created:
        db.refresh(u)
    return created


def _unit_label(u: Unit) -> str:
    return f"第{u.sort_no}单元{f'（{u.name}）' if u.name else ''}"


@router.put("/units/{unit_id}", response_model=UnitOut)
def update_unit(unit_id: int, body: UnitIn, db: Session = Depends(get_db)):
    unit = db.get(Unit, unit_id)
    if not unit:
        raise HTTPException(404, "单元不存在")
    unit.name = body.name or ""
    if body.sort_no is not None:
        unit.sort_no = body.sort_no
    db.commit()
    return unit


@router.delete("/units/{unit_id}")
def delete_unit(unit_id: int, db: Session = Depends(get_db)):
    unit = db.get(Unit, unit_id)
    if not unit:
        raise HTTPException(404, "单元不存在")
    # 引用该单元的成绩断开关联（成绩本身保留）
    db.execute(score_units.delete().where(score_units.c.unit_id == unit_id))
    db.delete(unit)
    db.commit()
    return {"ok": True}
