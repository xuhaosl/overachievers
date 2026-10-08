"""版本检查与应用内一键升级。

升级链路：应用后端对比「当前镜像构建号」与 GitHub 仓库 main 最新提交，
有新版时由后端调用同一 Compose 网络里的 watchtower（HTTP API），
watchtower 拉取 ghcr.io 最新镜像并重建容器；数据在挂载卷里不受影响。

环境变量：
- APP_VERSION       构建时注入的 git 提交号（本地开发为 dev）
- WATCHTOWER_URL    watchtower 地址（默认 http://watchtower:8080）
- WATCHTOWER_TOKEN  与 watchtower HTTP API 一致的令牌，未配置则无法触发升级
"""
import base64
import json
import os
import time
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException

from ..auth import AuthDep

router = APIRouter(dependencies=[AuthDep])

APP_VERSION = (os.environ.get("APP_VERSION", "") or "dev").strip()
REPO = os.environ.get("UPGRADE_REPO", "xuhaosl/overachievers")
WATCHTOWER_URL = (os.environ.get("WATCHTOWER_URL", "") or "http://watchtower:8080").rstrip("/")
WATCHTOWER_TOKEN = os.environ.get("WATCHTOWER_TOKEN", "")


@router.get("/update/version")
def app_version():
    """本机版本号（不访问外网），供前端升级等待时轮询。"""
    return {"version": APP_VERSION}


def _fetch_latest_version():
    """依次尝试 GitHub contents API 与 raw 直连，返回 (版本号, 错误信息)。

    优先 contents API：国内网络对 api.github.com 可达性好；
    raw.githubusercontent.com 国内经常超时，仅作境外网络兜底。
    匿名 API 限额 60 次/小时（按 IP），手动检查足够。
    """
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{REPO}/contents/VERSION?ref=main",
            headers={"User-Agent": "overachievers", "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = base64.b64decode(data.get("content", "")).decode("utf-8").strip()
        if content:
            return content, ""
        return "", "仓库 VERSION 文件为空"
    except urllib.error.HTTPError as e:
        api_err = "GitHub API 限流，约 10 分钟后自动恢复" if e.code == 403 else f"GitHub API 错误 {e.code}"
    except Exception as e:
        api_err = f"无法连接 GitHub：{e}"
    # raw 兜底
    try:
        url = f"https://raw.githubusercontent.com/{REPO}/main/VERSION?t={int(time.time())}"
        req = urllib.request.Request(url, headers={"User-Agent": "overachievers"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.read().decode("utf-8").strip(), ""
    except Exception:
        return "", api_err


@router.get("/update/check")
def check_update():
    """当前版本 vs 仓库 main 上的 VERSION 文件。"""
    current = "dev" if APP_VERSION == "dev" else APP_VERSION
    latest, error = ("", "") if current == "dev" else _fetch_latest_version()
    update_available = bool(latest) and current != "dev" and current != latest
    return {
        "current": current,
        "latest": latest,
        "update_available": update_available,
        "can_upgrade": bool(WATCHTOWER_TOKEN),
        "error": error,
    }


@router.post("/update")
def trigger_update():
    """触发 watchtower 立即更新（拉新镜像并重建本容器）。"""
    if not WATCHTOWER_TOKEN:
        raise HTTPException(status_code=400, detail="未配置升级通道（缺少 WATCHTOWER_TOKEN 环境变量）")
    req = urllib.request.Request(
        f"{WATCHTOWER_URL}/v1/update",
        headers={"Authorization": f"Bearer {WATCHTOWER_TOKEN}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            resp.read()
    except Exception as e:
        # watchtower 完成更新会重建本容器，本请求随之被掐断——这是升级成功的正常表现；
        # 只有「连接被拒绝」说明 watchtower 根本没起来，才算真失败
        if isinstance(getattr(e, "__cause__", None), ConnectionRefusedError) or "Refused" in str(e):
            raise HTTPException(status_code=502, detail="无法连接升级通道（watchtower 未运行？）")
    return {"ok": True, "message": "升级指令已发出，容器将在约 1 分钟内完成重建"}
