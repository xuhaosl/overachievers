"""成绩图片上传/清理：图片存 data/uploads，表里只存文件名。

图片本身目前只做存档与展示，后续的试卷分析、错题整理等功能再读取使用。
"""

import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import ScoreImage

UPLOAD_DIR = Path("data/uploads")
ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def save_score_image(db: Session, score_id: int, upload) -> ScoreImage:
    ext = Path(upload.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(422, "仅支持 jpg/png/gif/webp 图片")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / name).write_bytes(upload.file.read())
    img = ScoreImage(score_id=score_id, filename=name, original_name=upload.filename or "")
    db.add(img)
    db.commit()
    return img


def remove_score_image_files(db: Session, score_rows) -> None:
    """把一批成绩关联的图片文件从磁盘删掉（数据库行由 ORM 级联删除）。

    score_rows 可以是成绩对象列表，也可以是查询成绩的 Select 语句。
    """
    if hasattr(score_rows, "all"):  # Select 语句 → 先执行
        score_rows = db.scalars(score_rows).all()
    for score in score_rows:
        for img in score.images:
            try:
                (UPLOAD_DIR / img.filename).unlink(missing_ok=True)
            except OSError:
                pass


def image_out(img: ScoreImage) -> dict:
    return {
        "id": img.id,
        "url": f"/uploads/{img.filename}",
        "original_name": img.original_name,
        "created_at": str(img.created_at or ""),
    }
