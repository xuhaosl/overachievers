from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .database import Base, engine
from .routers import auth as auth_router
from .routers import children, exams, scores, stats, subjects

# 首次启动自动建表
Base.metadata.create_all(bind=engine)

app = FastAPI(title="学生成绩助手", version="0.1.0")

# 开发模式下前端 vite 跨域用
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router, prefix="/api")
app.include_router(children.router, prefix="/api")
app.include_router(subjects.router, prefix="/api")
app.include_router(exams.router, prefix="/api")
app.include_router(scores.router, prefix="/api")
app.include_router(stats.router, prefix="/api")

# 生产模式：服务前端打包产物
STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        # index.html 不缓存：发版后浏览器必须拿到新 hash 的资源引用；
        # /assets 下带 hash 的文件可以长期缓存
        file = STATIC_DIR / full_path
        if full_path and file.is_file():
            return FileResponse(file)
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})
