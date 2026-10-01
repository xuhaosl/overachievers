from datetime import date as date_type

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from ..auth import AuthDep
from ..database import get_db
from ..models import Child, Exam, Score, ScoreImage, SchoolClass, Subject, Unit, rival_names
from ..schemas import ExamAttachIn, ScoreIds, ScoreIn, ScoreOut
from ..uploads import UPLOAD_DIR, image_out, remove_score_image_files, save_score_image
from ..term import grade_at_date, infer_term, resolve_stage_grade, short_term_from_long

router = APIRouter(prefix="/scores", tags=["scores"], dependencies=[AuthDep])


def score_to_out(db: Session, s: Score) -> ScoreOut:
    out = ScoreOut.model_validate(s)
    out.child_name = s.child.name if s.child else ""
    out.subject_name = s.subject.name if s.subject else ""
    out.subject_color = s.subject.color if s.subject else "#409EFF"
    out.unit_ids = [u.id for u in s.units]
    ordered = sorted(s.units, key=lambda u: (u.sort_no, u.id))
    out.unit_names = "、".join(f"第{u.sort_no}单元{f'（{u.name}）' if u.name else ''}" for u in ordered)
    out.exam_name = s.exam.name if s.exam else None
    # 就读阶段 + 竞争对手名单：按孩子班级（就读经历）+ 成绩日期推算（小学/初中/高中）
    valid_scorers = set()
    if s.child:
        classes = db.scalars(select(SchoolClass).where(SchoolClass.child_id == s.child_id)).all()
        valid_scorers = {s.child.name}
        for cls in classes:
            valid_scorers |= rival_names(cls.rivals)
        start_year = s.date.year if s.date.month >= 8 else s.date.year - 1
        hit = resolve_stage_grade(classes, start_year)
        out.stage = hit[0] if hit else ""
        # 短学期名（如"五上"）：用于前端跳转学科详情并定位学期TAB
        out.term_short = short_term_from_long(classes, s.term) or ""
        # 最高得分者校验：只能来自班级主要竞争对手（含本人），
        # 不在名单的名字剔除；全部无效则为空（详情页显示"—"）
        if out.high_scorer:
            out.high_scorer = "、".join(n for n in out.high_scorer.split("、") if n in valid_scorers)
    # 班级人数：成绩没单独填时，按孩子的班级名从班级管理自动带出
    if s.class_size is None and s.child and s.child.class_name:
        cls = db.scalar(select(SchoolClass).where(SchoolClass.name == s.child.class_name))
        if cls and cls.size > 0:
            out.class_size = cls.size
    earned = s.regular_score + (s.bonus_score or 0)
    total = s.regular_total + (s.bonus_total or 0)
    out.earned = round(earned, 2)
    out.total = round(total, 2)
    out.rate = round(earned / total, 4) if total > 0 else 0
    return out


def _apply_exam_defaults(db: Session, data: dict) -> None:
    """挂场次的成绩：日期/年级/学期继承场次。独立成绩：按日期推断学期。"""
    child = db.get(Child, data["child_id"])
    if not child:
        raise HTTPException(404, "孩子不存在")
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
        # 年级按成绩日期推算（当时读几年级）；无入学年份才用传入值/孩子当前年级兜底
        g = grade_at_date(child.enroll_year, data["date"])
        if g is not None:
            data["grade"] = g
        elif data.get("grade") is None:
            data["grade"] = child.grade
        if not data.get("term"):
            data["term"] = infer_term(data["date"])
    # 附加分一致性：一半有一半无时补齐
    if data.get("bonus_score") is not None and data.get("bonus_total") is None:
        raise HTTPException(422, "填了附加得分必须同时填附加总分")
    if data.get("bonus_total") is not None and data.get("bonus_score") is None:
        raise HTTPException(422, "填了附加总分必须同时填附加得分")


def _apply_units(db: Session, score: Score, unit_ids: list[int]) -> None:
    """替换成绩关联的单元，并校验单元属于该学科。"""
    units = []
    for uid in unit_ids or []:
        unit = db.get(Unit, uid)
        if not unit:
            raise HTTPException(404, "单元不存在")
        if unit.subject_id != score.subject_id:
            raise HTTPException(422, "所选单元不属于该学科")
        units.append(unit)
    score.units = units


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
        .options(joinedload(Score.child), joinedload(Score.subject), joinedload(Score.exam))
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
    return [score_to_out(db, s) for s in db.scalars(q).unique().all()]


@router.post("", response_model=ScoreOut)
def create_score(body: ScoreIn, db: Session = Depends(get_db)):
    subject = db.get(Subject, body.subject_id)
    if not subject:
        raise HTTPException(404, "学科不存在")
    data = body.model_dump()
    _apply_exam_defaults(db, data)
    data.pop("unit_ids", None)
    score = Score(**data)
    _apply_units(db, score, body.unit_ids)
    db.add(score)
    db.commit()
    db.refresh(score)
    return score_to_out(db, score)


@router.put("/{score_id}", response_model=ScoreOut)
def update_score(score_id: int, body: ScoreIn, db: Session = Depends(get_db)):
    score = db.get(Score, score_id)
    if not score:
        raise HTTPException(404, "成绩不存在")
    data = body.model_dump()
    _apply_exam_defaults(db, data)
    data.pop("unit_ids", None)
    for k, v in data.items():
        setattr(score, k, v)
    _apply_units(db, score, body.unit_ids)
    db.commit()
    db.refresh(score)
    return score_to_out(db, score)


@router.post("/{score_id}/attach")
def attach_score(score_id: int, body: ExamAttachIn, db: Session = Depends(get_db)):
    """把独立录入的成绩拉进考试场次：日期/年级/学期继承场次。"""
    score = db.get(Score, score_id)
    if not score:
        raise HTTPException(404, "成绩不存在")
    exam = db.get(Exam, body.exam_id)
    if not exam:
        raise HTTPException(404, "考试场次不存在")
    if score.child_id != exam.child_id:
        raise HTTPException(422, "该成绩属于另一个孩子，无法挂到该场次")
    if score.exam_id != exam.id:
        score.exam_id = exam.id
        score.date = exam.date
        score.grade = exam.grade
        score.term = exam.term
        db.commit()
    return {"ok": True}


@router.post("/{score_id}/detach")
def detach_score(score_id: int, db: Session = Depends(get_db)):
    """把成绩移出场次，退回独立成绩（成绩本身保留）。"""
    score = db.get(Score, score_id)
    if not score:
        raise HTTPException(404, "成绩不存在")
    score.exam_id = None
    db.commit()
    return {"ok": True}


@router.get("/{score_id}", response_model=ScoreOut)
def get_score(score_id: int, db: Session = Depends(get_db)):
    score = db.get(Score, score_id)
    if not score:
        raise HTTPException(404, "成绩不存在")
    return score_to_out(db, score)


@router.post("/{score_id}/images")
async def upload_score_image(score_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    score = db.get(Score, score_id)
    if not score:
        raise HTTPException(404, "成绩不存在")
    return image_out(save_score_image(db, score_id, file))


@router.get("/{score_id}/images")
def list_score_images(score_id: int, db: Session = Depends(get_db)):
    if not db.get(Score, score_id):
        raise HTTPException(404, "成绩不存在")
    rows = db.scalars(select(ScoreImage).where(ScoreImage.score_id == score_id).order_by(ScoreImage.id)).all()
    return [image_out(i) for i in rows]


@router.delete("/images/{image_id}")
def delete_score_image(image_id: int, db: Session = Depends(get_db)):
    img = db.get(ScoreImage, image_id)
    if not img:
        raise HTTPException(404, "图片不存在")
    (UPLOAD_DIR / img.filename).unlink(missing_ok=True)
    db.delete(img)
    db.commit()
    return {"ok": True}


@router.delete("/{score_id}")
def delete_score(score_id: int, db: Session = Depends(get_db)):
    score = db.get(Score, score_id)
    if not score:
        raise HTTPException(404, "成绩不存在")
    remove_score_image_files(db, [score])
    score.units = []  # 先断开单元关联，再删成绩
    db.delete(score)
    db.commit()
    return {"ok": True}
