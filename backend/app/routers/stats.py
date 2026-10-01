from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..auth import AuthDep
from ..database import get_db
from ..models import Exam, Score, SchoolClass, Subject
from ..schemas import ExamSummary, OverviewOut, SubjectLatest
from ..term import resolve_stage_grade
from .exams import _summary

router = APIRouter(prefix="/stats", tags=["stats"], dependencies=[AuthDep])


@router.get("/overview", response_model=OverviewOut)
def overview(child_id: int | None = None, db: Session = Depends(get_db)):
    # 最近考试（最多 2 场）
    q = select(Exam).options(joinedload(Exam.scores)).order_by(Exam.date.desc(), Exam.id.desc()).limit(2)
    if child_id:
        q = q.where(Exam.child_id == child_id)
    recent = [_summary(db, e) for e in db.scalars(q).unique().all()]

    # 各科最新成绩
    sq = (
        select(Score)
        .options(joinedload(Score.subject))
        .order_by(Score.date.desc(), Score.id.desc())
    )
    if child_id:
        sq = sq.where(Score.child_id == child_id)
    seen: set[int] = set()
    latest: list[SubjectLatest] = []
    for s in db.scalars(sq).unique().all():
        if s.subject_id in seen:
            continue
        seen.add(s.subject_id)
        earned = s.regular_score + (s.bonus_score or 0)
        total = s.regular_total + (s.bonus_total or 0)
        display = f"{s.regular_score:g}"
        if s.bonus_score is not None:
            display = f"{s.regular_score:g}（{s.bonus_score:g}）"
        display += f"/{total:g}"
        # 就读阶段：按孩子班级（就读经历）+ 成绩日期推算
        stage = ""
        if s.child:
            classes = db.scalars(select(SchoolClass).where(SchoolClass.child_id == s.child_id)).all()
            start_year = s.date.year if s.date.month >= 8 else s.date.year - 1
            hit = resolve_stage_grade(classes, start_year)
            stage = hit[0] if hit else ""
        # 标题：学科单元，如"数学第1单元"；meta：阶段年级学期，如"小学5年级第1学期"
        unit_part = "、".join(f"第{u.sort_no}单元" for u in sorted(s.units, key=lambda u: (u.sort_no, u.id)))
        term_part = (s.term or "").split(" ")[-1] if s.term else ""
        title = f"{s.subject.name if s.subject else ''}{unit_part}"
        meta = "".join([stage, f"{s.grade}年级" if s.grade else "", term_part])
        latest.append(
            SubjectLatest(
                subject_id=s.subject_id,
                subject_name=s.subject.name,
                subject_color=s.subject.color,
                latest_date=s.date,
                latest_rate=round(earned / total, 4) if total else None,
                latest_display=display,
                title=title,
                meta=meta,
                class_rank=s.class_rank,
                grade_rank=s.grade_rank,
                tags=s.tags or "",
                starred=bool(s.starred),
                note=s.note or "",
            )
        )
    # 按学科排序
    subjects = db.scalars(select(Subject).order_by(Subject.id)).all()
    order = {s.id: i for i, s in enumerate(subjects)}
    latest.sort(key=lambda x: order.get(x.subject_id, 999))
    return OverviewOut(recent_exams=recent, subject_latest=latest)
