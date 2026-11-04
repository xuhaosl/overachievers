"""错题整理：错题本 → 错题集 → 错题，以及 AI 识别/自组织。

- 错题本归属孩子，名称由用户自建；集在本下；一道错题必须至少属于一个集（可多集）
- 题目来源：成绩试卷图片（AI 识别，或直接加入）与独立上传/纯文字录入
- AI 识别复用「智能助手」里已配置的机器人（需模型支持看图）
- 原题联网检索本期只预留配置与接口，未配置时直接走 AI 自组织
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import re
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import MetaData, Table, func, select
from sqlalchemy.orm import Session

from ..auth import AuthDep
from ..database import get_db
from ..models import (
    AiBot,
    Child,
    Mistake,
    MistakeNotebook,
    MistakeSearchConfig,
    MistakeSet,
    Score,
    ScoreImage,
    Subject,
    Unit,
)
from ..uploads import ALLOWED_EXTS, UPLOAD_DIR

router = APIRouter(prefix="/mistakes", tags=["mistakes"], dependencies=[AuthDep])

MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}


# ---------- 请求模型 ----------
class NotebookIn(BaseModel):
    child_id: int
    name: str


class SetIn(BaseModel):
    name: str


class MistakeIn(BaseModel):
    child_id: int
    set_ids: list[int]
    question_no: str = ""
    title: str = ""
    stem: str = ""
    my_answer: str = ""
    correct_answer: str = ""
    explanation: str = ""
    reason: str = ""
    knowledge_tags: str = ""
    unit_ids: list[int] = []
    source_type: str = "manual"  # manual / score / ai
    source_score_id: int | None = None
    source_image_id: int | None = None
    image_filename: str | None = None  # 引用已有成绩图片
    clear_image: bool = False  # 编辑时移除已有图片
    figure_filename: str | None = None  # AI 裁出的题目配图
    clear_figure: bool = False  # 编辑时移除配图
    mastered: bool = False


class SearchConfigIn(BaseModel):
    provider: str = "tavily"
    api_key: str = ""


class AttachScoreIn(BaseModel):
    score_id: int
    mistake_ids: list[int] = []


class DetachScoreIn(BaseModel):
    mistake_ids: list[int] = []


# ---------- 工具 ----------
def _notebook_out(nb: MistakeNotebook, set_count: int, mistake_count: int) -> dict:
    return {
        "id": nb.id,
        "child_id": nb.child_id,
        "name": nb.name,
        "sort_no": nb.sort_no,
        "set_count": set_count,
        "mistake_count": mistake_count,
        "created_at": str(nb.created_at or ""),
    }


def _set_out(s: MistakeSet, mistake_count: int = 0) -> dict:
    return {
        "id": s.id,
        "notebook_id": s.notebook_id,
        "name": s.name,
        "sort_no": s.sort_no,
        "mistake_count": mistake_count,
        "created_at": str(s.created_at or ""),
    }


def _mistake_out(m: Mistake, unit_map: dict[int, Unit] | None = None) -> dict:
    unit_ids = []
    try:
        unit_ids = [int(x) for x in json.loads(m.unit_ids or "[]")]
    except (ValueError, TypeError):
        unit_ids = []
    names = []
    if unit_map:
        names = [f"第{unit_map[i].sort_no}单元{f'（{unit_map[i].name}）' if unit_map[i].name else ''}" for i in unit_ids if i in unit_map]
    return {
        "id": m.id,
        "child_id": m.child_id,
        "question_no": m.question_no,
        "title": m.title,
        "stem": m.stem,
        "my_answer": m.my_answer,
        "correct_answer": m.correct_answer,
        "explanation": m.explanation,
        "reason": m.reason,
        "knowledge_tags": m.knowledge_tags,
        "unit_ids": unit_ids,
        "unit_names": "、".join(names),
        "image_url": f"/uploads/{m.image_filename}" if m.image_filename else "",
        "figure_url": f"/uploads/{m.figure_filename}" if m.figure_filename else "",
        "source_type": m.source_type,
        "source_score_id": m.source_score_id,
        "source_image_id": m.source_image_id,
        "mastered": m.mastered,
        "set_ids": [s.id for s in m.sets],
        "sets": [{"id": s.id, "notebook_id": s.notebook_id, "name": s.name} for s in m.sets],
        "created_at": str(m.created_at or ""),
        "updated_at": str(m.updated_at or ""),
    }


def _units_of(db: Session, unit_ids: list[int]) -> dict[int, Unit]:
    if not unit_ids:
        return {}
    rows = db.scalars(select(Unit).where(Unit.id.in_(unit_ids))).all()
    return {u.id: u for u in rows}


def _child_or_404(db: Session, child_id: int) -> Child:
    c = db.get(Child, child_id)
    if not c:
        raise HTTPException(404, "孩子不存在")
    return c


def _validate_sets(db: Session, child_id: int, set_ids: list[int]) -> list[MistakeSet]:
    uniq = list(dict.fromkeys(set_ids or []))
    if not uniq:
        raise HTTPException(400, "请至少选择一个错题集")
    rows = db.scalars(select(MistakeSet).where(MistakeSet.id.in_(uniq))).all()
    if len(rows) != len(uniq):
        raise HTTPException(404, "部分错题集不存在")
    for s in rows:
        if s.notebook.child_id != child_id:
            raise HTTPException(400, "错题集不属于该孩子")
    return rows


def _save_upload(upload: UploadFile) -> str:
    ext = Path(upload.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(422, "仅支持 jpg/png/gif/webp 图片")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    name = f"mistake_{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / name).write_bytes(upload.file.read())
    return name


def _safe_filename(name: str | None) -> str | None:
    """只接受纯文件名，避免通过 image_filename 做路径穿越。"""
    if not name:
        return None
    return Path(name).name


def _unlink(filename: str | None):
    if not filename:
        return
    try:
        (UPLOAD_DIR / filename).unlink(missing_ok=True)
    except OSError:
        pass


def _delete_own_image(m: Mistake):
    """只清理错题自己上传的原始截图。"""
    if m.image_owned:
        _unlink(m.image_filename)


def _delete_own_figure(m: Mistake):
    """只清理 AI 裁出的题目配图。"""
    if m.figure_owned:
        _unlink(m.figure_filename)


def _delete_own_files(m: Mistake):
    _delete_own_image(m)
    _delete_own_figure(m)


def _apply_mistake(m: Mistake, body: MistakeIn, sets: list[MistakeSet]):
    m.question_no = body.question_no.strip()[:20]
    m.title = body.title.strip()[:120]
    m.stem = body.stem.strip()
    m.my_answer = body.my_answer.strip()
    m.correct_answer = body.correct_answer.strip()
    m.explanation = body.explanation.strip()
    m.reason = body.reason.strip()
    m.knowledge_tags = body.knowledge_tags.strip()[:300]
    m.unit_ids = json.dumps(list(dict.fromkeys(body.unit_ids)))
    m.source_type = body.source_type
    m.source_score_id = body.source_score_id
    m.source_image_id = body.source_image_id
    m.mastered = body.mastered
    m.sets = sets


# ---------- 错题本 ----------
@router.get("/notebooks")
def list_notebooks(child_id: int = Query(...), db: Session = Depends(get_db)):
    _child_or_404(db, child_id)
    nbs = db.scalars(
        select(MistakeNotebook).where(MistakeNotebook.child_id == child_id)
        .order_by(MistakeNotebook.sort_no, MistakeNotebook.id)
    ).all()
    set_counts = dict(db.execute(
        select(MistakeSet.notebook_id, func.count(MistakeSet.id))
        .join(MistakeNotebook, MistakeSet.notebook_id == MistakeNotebook.id)
        .where(MistakeNotebook.child_id == child_id)
        .group_by(MistakeSet.notebook_id)
    ).all())
    # 每本错题数：按本下所有集的错题去重
    links = Table("mistake_set_links", MetaData(), autoload_with=db.connection())
    mistake_counts = dict(db.execute(
        select(MistakeSet.notebook_id, func.count(func.distinct(links.c.mistake_id)))
        .select_from(MistakeSet.__table__.join(links, links.c.set_id == MistakeSet.id))
        .join(MistakeNotebook, MistakeSet.notebook_id == MistakeNotebook.id)
        .where(MistakeNotebook.child_id == child_id)
        .group_by(MistakeSet.notebook_id)
    ).all())
    return [
        _notebook_out(nb, set_counts.get(nb.id, 0), mistake_counts.get(nb.id, 0)) for nb in nbs
    ]


@router.post("/notebooks")
def create_notebook(body: NotebookIn, db: Session = Depends(get_db)):
    _child_or_404(db, body.child_id)
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "错题本名称不能为空")
    max_no = db.scalar(select(func.max(MistakeNotebook.sort_no)).where(MistakeNotebook.child_id == body.child_id)) or 0
    nb = MistakeNotebook(child_id=body.child_id, name=name[:100], sort_no=max_no + 1)
    db.add(nb)
    db.commit()
    return _notebook_out(nb, 0, 0)


@router.patch("/notebooks/{notebook_id}")
def rename_notebook(notebook_id: int, body: SetIn, db: Session = Depends(get_db)):
    nb = db.get(MistakeNotebook, notebook_id)
    if not nb:
        raise HTTPException(404, "错题本不存在")
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "错题本名称不能为空")
    nb.name = name[:100]
    db.commit()
    return _notebook_out(nb, len(nb.sets), 0)


@router.delete("/notebooks/{notebook_id}")
def delete_notebook(notebook_id: int, confirm: bool = Query(False), db: Session = Depends(get_db)):
    nb = db.get(MistakeNotebook, notebook_id)
    if not nb:
        raise HTTPException(404, "错题本不存在")
    set_ids = [s.id for s in nb.sets]
    mistakes: dict[int, Mistake] = {}
    if set_ids:
        for m in db.scalars(
            select(Mistake).join(Mistake.sets).where(MistakeSet.id.in_(set_ids)).distinct()
        ).all():
            mistakes[m.id] = m
    if mistakes and not confirm:
        raise HTTPException(409, f"该错题本下有 {len(mistakes)} 道错题，删除将一并清除")
    for m in mistakes.values():
        _delete_own_files(m)
        db.delete(m)
    if mistakes:
        db.flush()
    for s in nb.sets:
        db.delete(s)
    db.delete(nb)
    db.commit()
    return {"ok": True}


# ---------- 错题集 ----------
@router.get("/notebooks/{notebook_id}/sets")
def list_sets(notebook_id: int, db: Session = Depends(get_db)):
    nb = db.get(MistakeNotebook, notebook_id)
    if not nb:
        raise HTTPException(404, "错题本不存在")
    rows = db.scalars(
        select(MistakeSet).where(MistakeSet.notebook_id == notebook_id).order_by(MistakeSet.sort_no, MistakeSet.id)
    ).all()
    links = Table("mistake_set_links", MetaData(), autoload_with=db.connection())
    counts = dict(db.execute(
        select(links.c.set_id, func.count(links.c.mistake_id))
        .where(links.c.set_id.in_([s.id for s in rows] or [0]))
    ).all())
    return [_set_out(s, counts.get(s.id, 0)) for s in rows]


@router.post("/notebooks/{notebook_id}/sets")
def create_set(notebook_id: int, body: SetIn, db: Session = Depends(get_db)):
    nb = db.get(MistakeNotebook, notebook_id)
    if not nb:
        raise HTTPException(404, "错题本不存在")
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "错题集名称不能为空")
    max_no = db.scalar(select(func.max(MistakeSet.sort_no)).where(MistakeSet.notebook_id == notebook_id)) or 0
    s = MistakeSet(notebook_id=notebook_id, name=name[:100], sort_no=max_no + 1)
    db.add(s)
    db.commit()
    return _set_out(s, 0)


@router.patch("/sets/{set_id}")
def rename_set(set_id: int, body: SetIn, db: Session = Depends(get_db)):
    s = db.get(MistakeSet, set_id)
    if not s:
        raise HTTPException(404, "错题集不存在")
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "错题集名称不能为空")
    s.name = name[:100]
    db.commit()
    return _set_out(s)


@router.delete("/sets/{set_id}")
def delete_set(set_id: int, confirm: bool = Query(False), db: Session = Depends(get_db)):
    s = db.get(MistakeSet, set_id)
    if not s:
        raise HTTPException(404, "错题集不存在")
    ms = db.scalars(select(Mistake).join(Mistake.sets).where(MistakeSet.id == set_id).distinct()).all()
    if ms and not confirm:
        raise HTTPException(409, f"该错题集下有 {len(ms)} 道错题，删除后不在其他集的错题也会一并清除")
    for m in ms:
        if len(m.sets) <= 1:  # 只属于这一集 → 一并删除
            _delete_own_files(m)
            db.delete(m)
    if ms:
        db.flush()
    db.delete(s)
    db.commit()
    return {"ok": True}


# ---------- 单元候选（知识点优先选现有单元） ----------
@router.get("/units")
def list_unit_options(child_id: int = Query(...), db: Session = Depends(get_db)):
    _child_or_404(db, child_id)
    subjects = db.scalars(
        select(Subject).where((Subject.child_id == child_id) | (Subject.child_id.is_(None))).order_by(Subject.id)
    ).all()
    out = []
    for sub in subjects:
        units = db.scalars(select(Unit).where(Unit.subject_id == sub.id).order_by(Unit.sort_no, Unit.id)).all()
        out.append({
            "subject_id": sub.id,
            "subject_name": sub.name,
            "units": [
                {"id": u.id, "sort_no": u.sort_no, "name": u.name, "term": u.term or ""}
                for u in units
            ],
        })
    return out


@router.get("/set-options")
def set_options(child_id: int = Query(...), db: Session = Depends(get_db)):
    """该孩子全部错题集（扁平列表），供录入时多选。"""
    _child_or_404(db, child_id)
    rows = db.execute(
        select(MistakeSet, MistakeNotebook.name)
        .join(MistakeNotebook, MistakeSet.notebook_id == MistakeNotebook.id)
        .where(MistakeNotebook.child_id == child_id)
        .order_by(MistakeNotebook.sort_no, MistakeSet.sort_no, MistakeSet.id)
    ).all()
    return [
        {"id": s.id, "notebook_id": s.notebook_id, "notebook_name": nb_name, "name": s.name}
        for s, nb_name in rows
    ]


# ---------- 原题检索配置（预留，必须先于 /{mistake_id} 注册） ----------
def _mask_key(key: str) -> str:
    if not key:
        return ""
    return key[:4] + "****" + key[-4:] if len(key) > 8 else "****"


@router.get("/search-config")
def get_search_config(db: Session = Depends(get_db)):
    cfg = db.get(MistakeSearchConfig, 1)
    if not cfg:
        return {"provider": "tavily", "api_key_masked": "", "configured": False}
    return {"provider": cfg.provider, "api_key_masked": _mask_key(cfg.api_key), "configured": bool(cfg.api_key)}


@router.put("/search-config")
def put_search_config(body: SearchConfigIn, db: Session = Depends(get_db)):
    cfg = db.get(MistakeSearchConfig, 1)
    if not cfg:
        cfg = MistakeSearchConfig(id=1)
        db.add(cfg)
    cfg.provider = body.provider
    if body.api_key.strip():
        cfg.api_key = body.api_key.strip()
    db.commit()
    return {"ok": True}


# ---------- 错题 ----------
@router.get("")
def list_mistakes(
    child_id: int | None = Query(None),
    notebook_id: int | None = Query(None),
    set_id: int | None = Query(None),
    unit_id: int | None = Query(None),
    mastered: bool | None = Query(None),
    keyword: str | None = Query(None),
    source_score_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    q = select(Mistake)
    if child_id:
        q = q.where(Mistake.child_id == child_id)
    if notebook_id:
        q = q.where(Mistake.sets.any(MistakeSet.notebook_id == notebook_id))
    if set_id:
        q = q.where(Mistake.sets.any(MistakeSet.id == set_id))
    if source_score_id:
        q = q.where(Mistake.source_score_id == source_score_id)
    if mastered is not None:
        q = q.where(Mistake.mastered == mastered)
    if keyword:
        kw = keyword.strip()
        q = q.where(
            (Mistake.stem.contains(kw)) | (Mistake.knowledge_tags.contains(kw)) | (Mistake.reason.contains(kw))
        )
    rows = db.scalars(q.order_by(Mistake.id.desc()).limit(500)).all()
    if unit_id:
        rows = [
            m for m in rows
            if unit_id in [int(x) for x in (json.loads(m.unit_ids or "[]") or [])]
        ]
    all_unit_ids = []
    for m in rows:
        try:
            all_unit_ids += [int(x) for x in json.loads(m.unit_ids or "[]")]
        except (ValueError, TypeError):
            pass
    unit_map = _units_of(db, all_unit_ids)
    return [_mistake_out(m, unit_map) for m in rows]


@router.post("/attach-score")
def attach_score(body: AttachScoreIn, db: Session = Depends(get_db)):
    """把已有错题挂到某场成绩下（不新增错题，只建立来源关联）。"""
    score = db.get(Score, body.score_id)
    if not score:
        raise HTTPException(404, "成绩不存在")
    rows = db.scalars(
        select(Mistake).where(
            Mistake.id.in_(body.mistake_ids or []),
            Mistake.child_id == score.child_id,
        )
    ).all()
    for m in rows:
        m.source_score_id = score.id
    db.commit()
    return {"ok": True, "count": len(rows)}


@router.post("/detach-score")
def detach_score(body: DetachScoreIn, db: Session = Depends(get_db)):
    """取消错题与成绩的来源关联，错题本身保留。"""
    rows = db.scalars(select(Mistake).where(Mistake.id.in_(body.mistake_ids or []))).all()
    for m in rows:
        m.source_score_id = None
    db.commit()
    return {"ok": True, "count": len(rows)}


@router.post("")
async def create_mistake(
    payload: str = Form(...),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    try:
        body = MistakeIn(**json.loads(payload))
    except (ValueError, TypeError) as e:
        raise HTTPException(400, f"参数格式错误：{e}")
    _child_or_404(db, body.child_id)
    sets = _validate_sets(db, body.child_id, body.set_ids)
    if not body.stem.strip() and not file and not body.image_filename:
        raise HTTPException(400, "题干或图片至少需要一项")
    m = Mistake(child_id=body.child_id)
    _apply_mistake(m, body, sets)
    if file:
        m.image_filename = _save_upload(file)
        m.image_owned = True
    elif body.image_filename:
        m.image_filename = _safe_filename(body.image_filename)
        m.image_owned = False
    fig = _safe_filename(body.figure_filename)
    if fig and (UPLOAD_DIR / fig).is_file():
        m.figure_filename = fig
        m.figure_owned = True
    db.add(m)
    db.commit()
    db.refresh(m)
    return _mistake_out(m, _units_of(db, json.loads(m.unit_ids or "[]")))


@router.post("/from-score-image")
def create_from_score_image(body: dict, db: Session = Depends(get_db)):
    """成绩图片直接加入错题集（不做识别）。"""
    child_id = body.get("child_id")
    set_ids = body.get("set_ids") or []
    image_id = body.get("source_image_id")
    _child_or_404(db, child_id)
    sets = _validate_sets(db, child_id, set_ids)
    img = db.get(ScoreImage, image_id) if image_id else None
    if not img:
        raise HTTPException(404, "试卷图片不存在")
    if img.score.child_id != child_id:
        raise HTTPException(400, "图片不属于该孩子")
    m = Mistake(
        child_id=child_id,
        image_filename=img.filename,
        image_owned=False,
        source_type="score",
        source_score_id=img.score_id,
        source_image_id=img.id,
    )
    m.sets = sets
    db.add(m)
    db.commit()
    db.refresh(m)
    return _mistake_out(m)


@router.post("/{mistake_id}/image")
async def upload_mistake_image(mistake_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    m = db.get(Mistake, mistake_id)
    if not m:
        raise HTTPException(404, "错题不存在")
    _delete_own_image(m)
    m.image_filename = _save_upload(file)
    m.image_owned = True
    db.commit()
    return _mistake_out(m)


@router.get("/{mistake_id}")
def get_mistake(mistake_id: int, db: Session = Depends(get_db)):
    m = db.get(Mistake, mistake_id)
    if not m:
        raise HTTPException(404, "错题不存在")
    try:
        ids = [int(x) for x in json.loads(m.unit_ids or "[]")]
    except (ValueError, TypeError):
        ids = []
    return _mistake_out(m, _units_of(db, ids))


@router.patch("/{mistake_id}")
def update_mistake(mistake_id: int, body: MistakeIn, db: Session = Depends(get_db)):
    m = db.get(Mistake, mistake_id)
    if not m:
        raise HTTPException(404, "错题不存在")
    _child_or_404(db, body.child_id)
    sets = _validate_sets(db, body.child_id, body.set_ids)
    has_image = bool(body.image_filename) or bool(m.image_filename and not body.clear_image)
    if not body.stem.strip() and not has_image:
        raise HTTPException(400, "题干或图片至少需要一项")
    _apply_mistake(m, body, sets)
    if body.image_filename:
        safe = _safe_filename(body.image_filename)
        if safe != m.image_filename:
            _delete_own_image(m)
            m.image_filename = safe
            m.image_owned = False
    elif body.clear_image:
        _delete_own_image(m)
        m.image_filename = None
        m.image_owned = False
    if body.figure_filename:
        safe_fig = _safe_filename(body.figure_filename)
        if safe_fig and safe_fig != m.figure_filename and (UPLOAD_DIR / safe_fig).is_file():
            if m.figure_owned and m.figure_filename:
                try:
                    (UPLOAD_DIR / m.figure_filename).unlink(missing_ok=True)
                except OSError:
                    pass
            m.figure_filename = safe_fig
            m.figure_owned = True
    elif body.clear_figure and m.figure_filename:
        if m.figure_owned:
            try:
                (UPLOAD_DIR / m.figure_filename).unlink(missing_ok=True)
            except OSError:
                pass
        m.figure_filename = None
        m.figure_owned = False
    db.commit()
    return _mistake_out(m)


@router.patch("/{mistake_id}/mastered")
def set_mastered(mistake_id: int, body: dict, db: Session = Depends(get_db)):
    m = db.get(Mistake, mistake_id)
    if not m:
        raise HTTPException(404, "错题不存在")
    m.mastered = bool(body.get("mastered"))
    db.commit()
    return {"ok": True, "mastered": m.mastered}


@router.delete("/{mistake_id}")
def delete_mistake(mistake_id: int, db: Session = Depends(get_db)):
    m = db.get(Mistake, mistake_id)
    if not m:
        raise HTTPException(404, "错题不存在")
    _delete_own_files(m)
    db.delete(m)
    db.commit()
    return {"ok": True}


# ---------- AI ----------
def _get_bot(db: Session, bot_id: int | None) -> AiBot:
    if bot_id:
        bot = db.get(AiBot, bot_id)
    else:
        bot = db.scalars(select(AiBot).where(AiBot.api_key != "").order_by(AiBot.id)).first()
    if not bot:
        raise HTTPException(400, "请先在「设置 → 智能助手」里配置一个机器人")
    if not bot.api_key:
        raise HTTPException(400, "该机器人未配置 API key")
    return bot


def _chat_url(bot: AiBot) -> str:
    from .ai import PROVIDERS
    base = (bot.base_url or PROVIDERS.get(bot.provider, {}).get("base_url", "")).strip()
    if not base.startswith("http"):
        raise HTTPException(400, "机器人接口地址不合法")
    return base.rstrip("/") + "/chat/completions"


async def _call_model(bot: AiBot, messages: list, max_tokens: int = 4000) -> str:
    url = _chat_url(bot)
    headers = {"Authorization": f"Bearer {bot.api_key}", "Content-Type": "application/json"}
    payload = {
        "model": bot.model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "stream": False,
    }
    # DeepSeek 等推理型模型会先输出大段 reasoning，长图识别时容易把 token 全耗在
    # 思考上、content 为空；识别/整理类任务直接关闭思考，稳定输出 JSON。
    if bot.provider == "deepseek" or "deepseek" in (bot.base_url or "").lower():
        payload["thinking"] = {"type": "disabled"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=15.0)) as client:
            resp = await client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"模型请求失败：{e.__class__.__name__}（网络不通或地址错误）")
    if resp.status_code != 200:
        detail = resp.text[:300]
        try:
            detail = resp.json().get("error", {}).get("message") or detail
        except ValueError:
            pass
        hint = {401: "API Key 无效", 404: "接口地址或模型名错误", 429: "限流/欠费"}.get(resp.status_code)
        raise HTTPException(502, f"模型返回失败（{resp.status_code}）：{hint or detail}")
    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"] or ""
    except (ValueError, KeyError, IndexError):
        raise HTTPException(502, "模型返回内容无法解析")
    if not content.strip():
        raise HTTPException(502, "模型没有返回识别结果（可能思考过长被截断），请重试")
    return content


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise HTTPException(502, "模型没有返回 JSON，请换一个支持识别的模型重试")
    try:
        obj = json.loads(text[start:end + 1])
    except ValueError:
        raise HTTPException(502, "模型返回的 JSON 无法解析，请重试")
    return obj if isinstance(obj, dict) else {}


def _score_context(db: Session, score: Score | None, subject_id: int | None, child_id: int | None) -> str:
    lines = []
    child = score.child if score else (db.get(Child, child_id) if child_id else None)
    if child:
        lines.append(f"孩子：{child.name}，{child.grade}年级")
    sub = score.subject if score else (db.get(Subject, subject_id) if subject_id else None)
    if sub:
        lines.append(f"学科：{sub.name}")
    if score:
        lines.append(f"学期：{score.term}；测试类型：{score.type}；成绩：{score.regular_score}/{score.regular_total}")
    if sub:
        units = db.scalars(select(Unit).where(Unit.subject_id == sub.id).order_by(Unit.sort_no, Unit.id)).all()
        if units:
            lines.append(
                "已有单元（知识点优先从这里选）："
                + "、".join(f"第{u.sort_no}单元{f'（{u.name}）' if u.name else ''}" for u in units)
            )
    return "\n".join(lines)


def _match_units(db: Session, subject_id: int | None, names: list[str]) -> list[int]:
    """把 AI 给出的知识点名匹配到系统单元；匹配不上则保留为自由标签。"""
    if not subject_id or not names:
        return []
    units = db.scalars(select(Unit).where(Unit.subject_id == subject_id)).all()
    hit = []
    for name in names:
        name = (name or "").strip()
        if not name:
            continue
        for u in units:
            label = u.name or f"第{u.sort_no}单元"
            if name == label or name in label or label in name:
                hit.append(u.id)
                break
    return list(dict.fromkeys(hit))


RECOGNIZE_PROMPT = (
    "你是试卷错题整理助手。图片可能是整卷、单题或题目局部。只输出一个 JSON 对象，不要解释或 Markdown。"
    "格式：{\"has_marks\": true/false, \"questions\": [{"
    "\"no\": \"题号（多小题时用原小题号）\", \"title\": \"本题一句话标题（12字内，如：阅读理解《故乡》人物形象）\", "
    "\"stem\": \"按原题排版的题干\", "
    "\"my_answer\": \"学生作答\", \"correct_answer\": \"正确答案\", "
    "\"explanation\": \"解析\", \"reason\": \"错因\", \"knowledge\": [\"知识点\"], "
    "\"is_wrong\": true/false, \"wrong_mark\": \"判错依据\", \"has_figure\": true/false, "
    "\"figure_box\": [x, y, w, h] 或 null, \"figure_desc\": \"配图简述\", \"box\": [x, y, w, h] 或 null, "
    "\"group_no\": \"大题号（同一大题的小题填相同值，独立题留空）\", "
    "\"group_title\": \"大题标题（同一大题填相同值，独立题留空）\", "
    "\"group_stem\": \"该大题的公共材料或题干（独立题留空）\"}]}。"
    "规则："
    "1) 有红笔批改痕迹（红叉、红笔画掉、扣分、写「错」）时 has_marks=true；没有时 has_marks=false。"
    "2) has_marks=true 时：同一道大题下的所有小题都要列出，并明确 is_wrong（红笔判错 true、答对 false）；"
    "其他与错题无关的答对题目不要输出；wrong_mark 只对判错的题写具体依据"
    "（如「第2题旁红叉」「第5题扣2分」），写不出依据的题判为 false；"
    "3) 同一大题含多个小题时按小题拆分，no 用原小题号（1、2、(3)）；"
    "每条的 group_no 必须是父级大题号（如「二」「二、阅读理解」），同一大题的所有小题必须填完全相同的值，禁止填小题号；"
    "group_stem 填该大题公共材料/题干，每条都重复填同一内容；stem 只写该小题题干，不要重复整篇阅读材料；"
    "独立题 group_no 和 group_stem 留空；"
    "示例：阅读理解「二、阅读短文」下第 1、2、3 小题都错，返回 3 条，三条的 group_no 都是「二」，group_stem 都是同一段短文；"
    "4) 题干按原题排版：要作答的位置用「______」占位，不填答案；选择题保留 A/B/C/D 选项；看不清的字用 □ 代替；"
    "5) 答案字段只针对错处，答对的空不要出现；my_answer 原文照抄（含错别字），correct_answer 必须给出标准答案，即使不确定；"
    "例如 4 个空只有第 3 空错：my_answer 写「第3空：学生原文」，correct_answer 写「第3空：标准答案」，第1、2、4 空不要出现；"
    "6) 无法分辨具体错处时：my_answer 写「整题被判错，具体错处待核对」，correct_answer 仍给标准答案，解析/错因可留空；"
    "7) 没有批改痕迹时，列出图片中所有题，is_wrong 一律 false，给全部作答供用户勾选；"
    "8) 有几何图形、电路图、函数图像、表格时 has_figure=true，figure_box 用归一化 [x, y, w, h] 只框图形本身；"
    "9) 学生作答看不清可留空，但不要编造学生作答；"
    "10) has_marks=true 且同一大题有多个小题时，必须给每条 box：该小题在原图中的归一化区域"
    "（包含题干、作答和红笔痕迹），只框这一小题；看不清位置时 box 写 null；"
    "11) title 必须是概括性标题，禁止只写「第几题」；同一大题的 group_title 填相同的标题，独立题 group_title 留空。"
)

VERIFY_WRONG_PROMPT = (
    "你是批改判定助手。图片是刚才识别的那张试卷。下面列出已识别出的若干小题。"
    "请只对照图片上的红笔批改痕迹，逐题判断哪些小题被老师判错。"
    "只输出 JSON：{\"wrong\": [\"题号\", ...]}，不要解释。"
    "判定规则：1) 该小题旁有红叉、红笔画掉/圈出错处、扣分（如 -1、-2）、写「错」才判错；"
    "2) 红勾、满分、没有红笔痕迹的题都判为对；"
    "3) 不要因为整页或整道大题有批改就把所有小题都判错；"
    "4) 题号必须与下面清单一致；5) 全部正确时输出空数组。"
)

CROP_VERIFY_PROMPT = (
    "这是一道小题的局部截图。请只判断这道小题是否被老师用红笔判错。"
    "只输出 JSON：{\"wrong\": true} 或 {\"wrong\": false}，不要解释。"
    "判错依据：图中有红叉、红笔划掉或圈出错处、扣分（如 -1、-2）、写「错」。"
    "红勾、满分、没有红笔痕迹，都算没有判错。"
)

TARGET_PROMPT = (
    "你是试卷错题识别助手。图片可能是一道大题（含多个小题）或整页。"
    "请只识别下面指定题号的那道小题，其他小题全部忽略；即使这道小题没有红笔批改痕迹也要输出。"
    "只输出 JSON：{\"questions\": [{\"no\": \"题号\", \"title\": \"本题一句话标题\", \"stem\": \"题干\", "
    "\"my_answer\": \"学生作答\", "
    "\"correct_answer\": \"正确答案\", \"explanation\": \"解析\", \"reason\": \"错因\", "
    "\"knowledge\": [\"知识点\"], \"is_wrong\": true, \"has_figure\": false, "
    "\"figure_box\": null, \"figure_desc\": \"\", \"group_no\": \"\", "
    "\"group_title\": \"\", \"group_stem\": \"\"}]}，不要解释。"
    "规则：1) no 固定为指定题号，is_wrong 固定为 true；"
    "2) 题干按原题排版，作答处用「______」占位，只写该小题，不重复整篇材料；"
    "3) my_answer 原文照抄，correct_answer 必须给出标准答案；"
    "4) 有配图时 has_figure=true 并给归一化 figure_box；"
    "5) 该小题属于某道大题时，group_no 填大题号、group_stem 填公共材料或题干；独立题留空；"
    "6) 图片里找不到该题号时输出 {\"questions\": []}。"
)


def _question_out(
    q: dict,
    i: int,
    image_bytes: bytes,
    db: Session,
    unit_subject_id: int | None,
    has_marks: bool,
    force_wrong: bool = False,
) -> dict:
    """把模型返回的一道题整理成接口输出格式。"""
    knowledge = [str(x).strip() for x in (q.get("knowledge") or []) if str(x).strip()]
    figure_file = _crop_figure(image_bytes, q.get("figure_box")) if q.get("has_figure") else None
    my_answer = str(q.get("my_answer") or "").strip()
    correct_answer = str(q.get("correct_answer") or "").strip()
    explanation = str(q.get("explanation") or "").strip()
    reason = str(q.get("reason") or "").strip()
    if has_marks:
        my_answer, correct_answer = _filter_wrong_parts(my_answer, correct_answer)
        if my_answer == WRONG_PENDING:
            # 分辨不出具体错处时，解析/错因也不强行编造，避免误导读题人
            explanation = ""
            reason = ""
    stem = str(q.get("stem") or "").strip()
    title = str(q.get("title") or "").strip()[:120] or re.sub(r"\s+", " ", stem)[:30]
    return {
        "no": str(q.get("no") or "").strip(),
        "title": title,
        "group_title": str(q.get("group_title") or "").strip()[:120],
        "stem": stem,
        "my_answer": my_answer,
        "correct_answer": correct_answer,
        "explanation": explanation,
        "reason": reason,
        "knowledge": knowledge,
        "unit_ids": _match_units(db, unit_subject_id, knowledge),
        "is_wrong": force_wrong or (bool(q.get("is_wrong")) if has_marks else False),
        "has_figure": bool(q.get("has_figure")),
        "figure_desc": str(q.get("figure_desc") or "").strip(),
        "figure_filename": figure_file,
        "figure_url": f"/uploads/{figure_file}" if figure_file else "",
        "order": i,
        "group_no": str(q.get("group_no") or "").strip(),
        "group_stem": str(q.get("group_stem") or "").strip(),
        "_box": q.get("box"),
    }


def _norm_no(text: str) -> str:
    """题号归一化：第2题、(3)、2. 都转成 2。"""
    return re.sub(r"[第题()（）\s.、]", "", str(text or ""))


def _fill_group_info(questions: list[dict]) -> None:
    """同一大题的 group_no 与 group_stem 互相补齐，避免模型只填了其中一项。"""
    stem_by_no: dict[str, str] = {}
    no_by_stem: dict[str, str] = {}
    title_by_no: dict[str, str] = {}
    for q in questions:
        no = _norm_no(q.get("group_no"))
        stem = str(q.get("group_stem") or "").strip()
        if no and stem:
            stem_by_no.setdefault(no, stem)
            no_by_stem.setdefault(stem, q["group_no"].strip())
        if no and str(q.get("group_title") or "").strip():
            title_by_no.setdefault(no, q["group_title"].strip())
    for q in questions:
        no = _norm_no(q.get("group_no"))
        stem = str(q.get("group_stem") or "").strip()
        if no and not stem and no in stem_by_no:
            q["group_stem"] = stem_by_no[no]
        elif stem and not no and stem in no_by_stem:
            q["group_no"] = no_by_stem[stem]
        if no and not str(q.get("group_title") or "").strip() and no in title_by_no:
            q["group_title"] = title_by_no[no]


async def _verify_wrong_questions(
    bot: AiBot, image_bytes: bytes, mime: str, questions: list[dict]
) -> set[str] | None:
    """二次核对：只看红笔痕迹判断哪些小题真的被判错。

    返回 None 表示核对不可用，调用方保留第一次识别结果。
    """
    numbered = [q for q in questions if _norm_no(q.get("no"))]
    if len(numbered) < 2:
        return None
    lines = []
    for q in numbered:
        lines.append(
            f"题号：{q['no']}\n题干：{q['stem'][:200]}\n学生答案：{q['my_answer'][:150]}"
        )
    content = [
        {
            "type": "text",
            "text": VERIFY_WRONG_PROMPT + "\n\n候选小题：\n" + "\n---\n".join(lines),
        },
        {
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"},
        },
    ]
    try:
        raw = await _call_model(bot, [{"role": "user", "content": content}], max_tokens=1000)
        obj = _parse_json(raw)
    except HTTPException:
        return None
    wrong = obj.get("wrong")
    if not isinstance(wrong, list):
        return None
    wanted = {_norm_no(x) for x in wrong if _norm_no(x)}
    matched = {_norm_no(q["no"]) for q in numbered if _norm_no(q["no"]) in wanted}
    # 返回空或匹配不上，说明核对结果不可靠，保留第一次识别的标注
    return matched or None


WRONG_PENDING = "整题被判错，具体错处待核对"


def _norm_answer(text: str) -> str:
    """去掉标点空白后比较，避免只差标点被当成错处。"""
    return re.sub(r"[\s，。！？、,.!?;；:：“”\"'（）()]", "", text or "")


def _filter_wrong_parts(my: str, correct: str) -> tuple[str, str]:
    """一道题多个空时，只保留学生答案与正确答案确实不同的错处。"""
    if not my or not correct:
        return my, correct
    if _norm_answer(my) == _norm_answer(correct):
        # 仍保留模型给出的正确答案，供用户调整
        return WRONG_PENDING, correct
    parts_my = re.split(r"[；;]\s*", my)
    parts_co = re.split(r"[；;]\s*", correct)
    if len(parts_my) == len(parts_co) and len(parts_my) > 1:
        kept = [
            (a.strip(), b.strip())
            for a, b in zip(parts_my, parts_co)
            if _norm_answer(a) != _norm_answer(b)
        ]
        if kept:
            return "；".join(a for a, _ in kept), "；".join(b for _, b in kept)
        return WRONG_PENDING, correct
    return my, correct


def _crop_figure(image_bytes: bytes, box) -> str | None:
    """按归一化 [x, y, w, h] 从原图裁出题目配图，返回文件名；无效范围返回 None。"""
    if not box:
        return None
    if isinstance(box, dict):
        box = [box.get("x"), box.get("y"), box.get("w"), box.get("h")]
    try:
        x, y, w, h = (float(v) for v in box)
    except (TypeError, ValueError):
        return None
    if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1):
        return None
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return None
    W, H = img.size
    left = max(0, int(x * W))
    top = max(0, int(y * H))
    right = min(W, int((x + w) * W))
    bottom = min(H, int((y + h) * H))
    if right - left < 40 or bottom - top < 40:
        return None
    # 四周留一点余量，避免图形边缘被切
    pad_x = int((right - left) * 0.04)
    pad_y = int((bottom - top) * 0.04)
    crop = img.crop((max(0, left - pad_x), max(0, top - pad_y), min(W, right + pad_x), min(H, bottom + pad_y)))
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    name = f"figure_{uuid.uuid4().hex}.jpg"
    crop.save(UPLOAD_DIR / name, format="JPEG", quality=90)
    return name


def _crop_region_bytes(image_bytes: bytes, box) -> bytes | None:
    """按归一化 [x, y, w, h] 裁出小题局部图，用于逐题核对红笔痕迹。"""
    if not box:
        return None
    if isinstance(box, dict):
        box = [box.get("x"), box.get("y"), box.get("w"), box.get("h")]
    try:
        x, y, w, h = (float(v) for v in box)
    except (TypeError, ValueError):
        return None
    if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1):
        return None
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return None
    W, H = img.size
    left = max(0, int(x * W))
    top = max(0, int(y * H))
    right = min(W, int((x + w) * W))
    bottom = min(H, int((y + h) * H))
    if right - left < 60 or bottom - top < 40:
        return None
    # 多留余量，确保红笔批改和作答都在裁剪范围内
    pad_x = int((right - left) * 0.08)
    pad_y = int((bottom - top) * 0.08)
    crop = img.crop((max(0, left - pad_x), max(0, top - pad_y), min(W, right + pad_x), min(H, bottom + pad_y)))
    buf = io.BytesIO()
    crop.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


async def _verify_by_crops(
    bot: AiBot, image_bytes: bytes, questions: list[dict]
) -> dict[str, bool] | None:
    """逐题裁图核对：每道小题只看自己的局部图，判断是否被红笔判错。"""
    numbered = [q for q in questions if _norm_no(q.get("no")) and q.get("_box")]
    if len(numbered) < 2:
        return None
    sem = asyncio.Semaphore(3)

    async def judge(q: dict) -> tuple[str, bool | None]:
        crop = _crop_region_bytes(image_bytes, q.get("_box"))
        if not crop:
            return _norm_no(q["no"]), None
        content = [
            {
                "type": "text",
                "text": f"题号：{q['no']}\n题干：{q['stem'][:150]}\n\n{CROP_VERIFY_PROMPT}",
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{base64.b64encode(crop).decode()}"},
            },
        ]
        async with sem:
            try:
                raw = await _call_model(bot, [{"role": "user", "content": content}], max_tokens=300)
                obj = _parse_json(raw)
            except HTTPException:
                return _norm_no(q["no"]), None
        value = obj.get("wrong")
        if not isinstance(value, bool):
            return _norm_no(q["no"]), None
        return _norm_no(q["no"]), value

    results = await asyncio.gather(*[judge(q) for q in numbered])
    verdicts = {no: value for no, value in results if value is not None}
    return verdicts or None


@router.post("/ai/recognize")
async def ai_recognize(
    score_image_id: int | None = Form(None),
    score_id: int | None = Form(None),
    child_id: int | None = Form(None),
    subject_id: int | None = Form(None),
    bot_id: int | None = Form(None),
    target_no: str | None = Form(None),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    bot = _get_bot(db, bot_id)
    score: Score | None = None
    image_bytes: bytes | None = None
    mime = "image/jpeg"
    if score_image_id:
        img = db.get(ScoreImage, score_image_id)
        if not img:
            raise HTTPException(404, "试卷图片不存在")
        path = UPLOAD_DIR / img.filename
        if not path.is_file():
            raise HTTPException(404, "图片文件不存在，请重新上传")
        image_bytes = path.read_bytes()
        mime = MIME.get(path.suffix.lower(), "image/jpeg")
        score = img.score
    elif score_id:
        score = db.get(Score, score_id)
        if not score:
            raise HTTPException(404, "成绩不存在")
    if file:
        image_bytes = await file.read()
        mime = file.content_type or "image/jpeg"
    if not image_bytes:
        raise HTTPException(400, "请提供图片")
    if len(image_bytes) > 20 * 1024 * 1024:
        raise HTTPException(413, "图片太大（上限 20MB），请压缩后再试")

    ctx = _score_context(db, score, subject_id, child_id)
    base_info = {
        "source_score_id": score.id if score else None,
        "source_image_id": score_image_id,
        "child_id": score.child_id if score else child_id,
        "subject_id": score.subject_id if score else subject_id,
    }
    # 手动补识别：用户指定题号，只识别这一道小题
    target = (target_no or "").strip()
    if target:
        prompt = TARGET_PROMPT + f"\n目标题号：{target}"
        content = [
            {"type": "text", "text": (ctx + "\n\n" if ctx else "") + prompt},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"}},
        ]
        raw = await _call_model(bot, [{"role": "user", "content": content}], max_tokens=4000)
        obj = _parse_json(raw)
        first = next((x for x in (obj.get("questions") or []) if isinstance(x, dict)), None)
        if not first:
            return {"has_marks": True, "questions": [], **base_info}
        out = _question_out(
            first, 0, image_bytes, db,
            score.subject_id if score else subject_id, True, force_wrong=True,
        )
        out["no"] = target
        out.pop("_box", None)
        return {"has_marks": True, "questions": [out], **base_info}
    content = [
        {"type": "text", "text": (ctx + "\n\n" if ctx else "") + RECOGNIZE_PROMPT},
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"}},
    ]
    raw = await _call_model(bot, [{"role": "user", "content": content}], max_tokens=8000)
    obj = _parse_json(raw)
    has_marks = bool(obj.get("has_marks"))
    questions = []
    for i, q in enumerate(obj.get("questions") or []):
        if not isinstance(q, dict):
            continue
        questions.append(_question_out(
            q, i, image_bytes, db,
            score.subject_id if score else subject_id, has_marks,
        ))
    _fill_group_info(questions)
    # 多小题时优先逐题裁图核对红笔痕迹，裁图不可用时退回整图核对
    if has_marks and len(questions) >= 2:
        verdicts = await _verify_by_crops(bot, image_bytes, questions)
        if verdicts:
            for q in questions:
                value = verdicts.get(_norm_no(q["no"]))
                if value is not None:
                    q["is_wrong"] = value
        else:
            verified = await _verify_wrong_questions(bot, image_bytes, mime, questions)
            if verified is not None:
                for q in questions:
                    q["is_wrong"] = _norm_no(q["no"]) in verified
    for q in questions:
        q.pop("_box", None)
    return {
        "has_marks": has_marks,
        "questions": questions,
        **base_info,
    }


class OrganizeIn(BaseModel):
    stem: str
    my_answer: str = ""
    correct_answer: str = ""
    child_id: int | None = None
    subject_id: int | None = None
    bot_id: int | None = None


@router.post("/ai/organize")
async def ai_organize(body: OrganizeIn, db: Session = Depends(get_db)):
    """手动录入时让 AI 补齐答案/解析/错因/知识点。"""
    bot = _get_bot(db, body.bot_id)
    if not body.stem.strip():
        raise HTTPException(400, "请先填写题干")
    ctx = _score_context(db, None, body.subject_id, body.child_id)
    prompt = (
        (ctx + "\n\n" if ctx else "")
        + "请把下面这道错题整理成 JSON（只输出 JSON，不要 Markdown）："
        "{\"stem\":\"整理后的题干\",\"my_answer\":\"学生答案\",\"correct_answer\":\"正确答案\","
        "\"explanation\":\"解析\",\"reason\":\"错因\",\"knowledge\":[\"知识点\"]}。"
        "题干要还原成原题的版式：填空题、默写题凡是需要作答的位置用「______」占位，"
        "不要把学生答案或正确答案填进题干；选择题保留 A/B/C/D 选项；不要概括或改写成总结。"
        "my_answer 和 correct_answer 只针对学生答错的部分，答对的空不要重复列出；"
        "有多处错误时按「第1空：…；第2空：…」标注位置；学生答案和正确答案若用户已给，原样保留；"
        "correct_answer 必须给出你判断的标准答案，即使不确定也要给，用户会自行调整；"
        "学生作答看不清可以留空，但不要编造。\n\n"
        f"题干：{body.stem}\n学生答案：{body.my_answer}\n已知正确答案：{body.correct_answer}"
    )
    raw = await _call_model(bot, [{"role": "user", "content": prompt}])
    obj = _parse_json(raw)
    knowledge = [str(x).strip() for x in (obj.get("knowledge") or []) if str(x).strip()]
    return {
        "stem": str(obj.get("stem") or body.stem).strip(),
        "my_answer": str(obj.get("my_answer") or body.my_answer).strip(),
        "correct_answer": str(obj.get("correct_answer") or body.correct_answer).strip(),
        "explanation": str(obj.get("explanation") or "").strip(),
        "reason": str(obj.get("reason") or "").strip(),
        "knowledge": knowledge,
        "unit_ids": _match_units(db, body.subject_id, knowledge),
    }


# ---------- 原题检索（预留） ----------
def search_original_question(question: str, config: MistakeSearchConfig | None) -> list[dict]:
    """预留：按题干联网检索原题，返回候选列表 [{title, url, content, image_url}]。

    本期未接入任何搜索服务：未配置时直接返回空列表，上层流程自动落到 AI 自组织。
    """
    if not config or not config.api_key:
        return []
    return []
