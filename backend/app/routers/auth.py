import hmac
import time

from fastapi import APIRouter, HTTPException, Request

from ..auth import APP_PASSWORD, auth_enabled, make_token
from ..schemas import LoginIn, LoginOut, MetaOut

router = APIRouter()

# 登录失败限流：同一 IP 5 分钟内失败 5 次后，锁定到最早一次失败过窗为止
FAIL_WINDOW = 300.0
FAIL_LIMIT = 5
_fails: dict[str, list[float]] = {}


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def login_retry_after(ip: str) -> int:
    """返回还需等待的秒数，0 表示未锁定。"""
    now = time.monotonic()
    stamps = [t for t in _fails.get(ip, []) if now - t < FAIL_WINDOW]
    if stamps:
        _fails[ip] = stamps
    else:
        _fails.pop(ip, None)
    if len(stamps) < FAIL_LIMIT:
        return 0
    return int(FAIL_WINDOW - (now - stamps[0])) + 1


def _record_failure(ip: str) -> None:
    _fails.setdefault(ip, []).append(time.monotonic())


@router.get("/meta", response_model=MetaOut)
def meta():
    return MetaOut(auth_required=auth_enabled())


@router.post("/auth/login", response_model=LoginOut)
def login(body: LoginIn, request: Request):
    if not auth_enabled():
        return LoginOut(token="")
    ip = _client_ip(request)
    wait = login_retry_after(ip)
    if wait:
        raise HTTPException(status_code=429, detail=f"尝试过于频繁，请 {wait} 秒后再试")
    if not hmac.compare_digest(body.password, APP_PASSWORD):
        _record_failure(ip)
        raise HTTPException(status_code=401, detail="密码错误")
    _fails.pop(ip, None)
    return LoginOut(token=make_token())
