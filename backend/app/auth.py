"""可选密码认证：设置环境变量 APP_PASSWORD 后启用。

- POST /api/auth/login 校验密码，返回 token = sha256(APP_PASSWORD)
- 之后所有 /api 请求需带请求头 X-Auth-Token
"""
import hashlib
import os

from fastapi import Depends, HTTPException, Request

APP_PASSWORD = os.environ.get("APP_PASSWORD", "").strip()


def auth_enabled() -> bool:
    return bool(APP_PASSWORD)


def make_token() -> str:
    return hashlib.sha256(f"overachievers:{APP_PASSWORD}".encode()).hexdigest()


def require_auth(request: Request) -> None:
    if not auth_enabled():
        return
    token = request.headers.get("X-Auth-Token", "")
    if token != make_token():
        raise HTTPException(status_code=401, detail="未登录或密码已更改")


AuthDep = Depends(require_auth)
