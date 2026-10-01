"""数据备份：全量导出为 JSON 备份文件，导入时整体替换现有数据。"""
import json
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import Date, DateTime, MetaData, Table, delete, insert, select
from sqlalchemy.orm import Session

from ..auth import AuthDep
from ..database import get_db
from ..models import Child, Exam, SchoolClass, Score, ScoreImage, Subject, SubjectTerm, Unit

router = APIRouter(prefix="/backup", tags=["backup"], dependencies=[AuthDep])

# 导出/导入的表及顺序（依赖顺序：被引用的表在前）
TABLES = [
    ("children", Child),
    ("classes", SchoolClass),
    ("subjects", Subject),
    ("subject_terms", SubjectTerm),
    ("units", Unit),
    ("exams", Exam),
    ("scores", Score),
    ("score_images", ScoreImage),
]


def _row_dict(model, row) -> dict:
    return {c.name: getattr(row, c.name) for c in model.__table__.columns}


@router.get("/export")
def export_data(db: Session = Depends(get_db)):
    data = {
        "app": "studentassistant",
        "version": 1,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "tables": {},
    }
    for name, model in TABLES:
        rows = db.scalars(select(model)).all()
        data["tables"][name] = [_row_dict(model, r) for r in rows]
    # 成绩↔单元 多对多关联表
    data["tables"]["score_units"] = [
        {"score_id": r[0], "unit_id": r[1]}
        for r in db.execute(select(Table("score_units", MetaData(), autoload_with=db.connection())))
    ]
    fname = f"backup_{datetime.now():%Y%m%d_%H%M%S}.json"
    content = json.dumps(data, ensure_ascii=False, default=str)
    return Response(
        content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


def _coerce(model, row: dict) -> dict:
    """JSON 里的日期是字符串，还原成 date/datetime；忽略模型里不存在的键。"""
    cols = {c.name: c for c in model.__table__.columns}
    clean = {}
    for k, v in row.items():
        if k not in cols or v is None:
            continue
        if isinstance(v, str) and isinstance(cols[k].type, Date):
            try:
                v = date.fromisoformat(v[:10])
            except ValueError:
                pass
        elif isinstance(v, str) and isinstance(cols[k].type, DateTime):
            try:
                v = datetime.fromisoformat(v.replace("T", " "))
            except ValueError:
                pass
        clean[k] = v
    return clean


@router.post("/import")
async def import_data(file: UploadFile = File(...), db: Session = Depends(get_db)):
    raw = await file.read()
    try:
        data = json.loads(raw)
    except Exception:
        raise HTTPException(400, "文件不是有效的 JSON")
    tables = data.get("tables") if isinstance(data, dict) else None
    if not isinstance(tables, dict) or "children" not in tables or "scores" not in tables:
        raise HTTPException(400, "文件格式不对：不是本系统导出的备份文件")

    # 清空现有数据（先删关联表和被引用表）
    db.execute(delete(Table("score_units", MetaData(), autoload_with=db.connection())))
    for _, model in reversed(TABLES):
        db.execute(delete(model))

    # 按依赖顺序写入
    for name, model in TABLES:
        for row in tables.get(name, []):
            db.add(model(**_coerce(model, row)))
    su = Table("score_units", MetaData(), autoload_with=db.connection())
    for row in tables.get("score_units", []):
        db.execute(insert(su).values(score_id=row.get("score_id"), unit_id=row.get("unit_id")))
    db.commit()

    counts = {name: len(tables.get(name, [])) for name, _ in TABLES}
    counts["score_units"] = len(tables.get("score_units", []))
    return {"ok": True, "counts": counts}
