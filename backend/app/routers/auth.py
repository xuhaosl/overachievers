from fastapi import APIRouter

from ..auth import APP_PASSWORD, auth_enabled, make_token
from ..schemas import LoginIn, LoginOut, MetaOut

router = APIRouter()


@router.get("/meta", response_model=MetaOut)
def meta():
    return MetaOut(auth_required=auth_enabled())


@router.post("/auth/login", response_model=LoginOut)
def login(body: LoginIn):
    if not auth_enabled():
        return LoginOut(token="")
    if body.password != APP_PASSWORD:
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="密码错误")
    return LoginOut(token=make_token())
