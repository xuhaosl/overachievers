from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..auth import AuthDep
from ..database import get_db
from ..models import Exam, Score, Subject
from ..schemas import ExamSummary, OverviewOut, SubjectLatest
from .exams import _summary

router = APIRouter(prefix="/stats", tags=["stats"], dependencies=[AuthDep])


@router.get("/overview", response_model=OverviewOut)
def overview(child_id: int | None = None, db: Session = Depends(get_db)):
    # 最近考试（最多 5 场）
    q = select(Exam).options(joinedload(Exam.scores)).order_by(Exam.date.desc(), Exam.id.desc()).limit(5)
    if child_id:
        q = q.where(Exam.child_id == child_id)
    recent = [_summary(e) for e in db.scalars(q).unique().all()]

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
        latest.append(
            SubjectLatest(
                subject_id=s.subject_id,
                subject_name=s.subject.name,
                subject_color=s.subject.color,
                latest_date=s.date,
                latest_rate=round(earned / total, 4) if total else None,
                latest_display=display,
            )
        )
    # 按学科排序
    subjects = db.scalars(select(Subject).order_by(Subject.sort, Subject.id)).all()
    order = {s.id: i for i, s in enumerate(subjects)}
    latest.sort(key=lambda x: order.get(x.subject_id, 999))
    return OverviewOut(recent_exams=recent, subject_latest=latest)
