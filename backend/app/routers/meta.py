"""健康检查与运行时元信息。"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from .. import crypto
from ..database import DB_PATH
from ..privacy import privacy_status

router = APIRouter(tags=["meta"])

VERSION_FILE = Path(__file__).resolve().parents[2] / "VERSION"


def app_version() -> str:
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


@router.get("/health")
def health():
    """无需认证的健康检查：只暴露版本与能力开关，不返回任何用户数据。"""
    guard = privacy_status().get("guard", {})
    return {
        "ok": True,
        "app": "overachievers",
        "version": app_version(),
        "db_present": DB_PATH.exists(),
        "secret": {
            "scheme": crypto.secret_status().get("scheme"),
            "roundtrip_ok": crypto.check_secret_roundtrip(),
        },
        "privacy": {
            "guard_installed": bool(guard.get("installed")),
            "guard_available": bool(guard.get("available")),
        },
    }
