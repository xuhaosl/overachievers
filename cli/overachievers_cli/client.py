"""HTTP 客户端与统一错误处理。"""
from __future__ import annotations

import json
import os
from typing import Any, Iterator

import httpx


class CliError(RuntimeError):
    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


def default_base_url() -> str:
    return (os.environ.get("OA_BASE_URL") or "http://127.0.0.1:8100").rstrip("/")


def default_token() -> str:
    return os.environ.get("OA_TOKEN", "").strip()


class Client:
    def __init__(self, base_url: str | None = None, token: str | None = None, timeout: float = 60.0):
        self.base_url = (base_url or default_base_url()).rstrip("/")
        self.token = default_token() if token is None else token.strip()
        self.timeout = timeout

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["X-Auth-Token"] = self.token
        if extra:
            headers.update(extra)
        return headers

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.base_url}/api{path}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.request(method, url, headers=self._headers(kwargs.pop("headers", None)), **kwargs)
        except httpx.HTTPError as exc:
            raise CliError(f"无法连接 {self.base_url}：{exc.__class__.__name__}（服务是否已启动？）", 3) from exc
        if resp.status_code == 401:
            raise CliError("未授权：请设置 OA_TOKEN 或 --token", 1)
        if resp.status_code >= 400:
            detail = resp.text[:500]
            try:
                detail = resp.json().get("detail") or detail
            except ValueError:
                pass
            raise CliError(f"HTTP {resp.status_code}: {detail}", 1)
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return resp.text

    def get(self, path: str, **params: Any) -> Any:
        clean = {k: v for k, v in params.items() if v is not None and v != ""}
        return self.request("GET", path, params=clean or None)

    def post(self, path: str, payload: Any = None) -> Any:
        return self.request("POST", path, json=payload or {})

    def patch(self, path: str, payload: Any = None) -> Any:
        return self.request("PATCH", path, json=payload or {})

    def put(self, path: str, payload: Any = None) -> Any:
        return self.request("PUT", path, json=payload or {})

    def delete(self, path: str, **params: Any) -> Any:
        clean = {k: v for k, v in params.items() if v is not None}
        return self.request("DELETE", path, params=clean or None)

    # ---------- SSE ----------
    def stream_sse(self, path: str, payload: dict) -> Iterator[dict]:
        url = f"{self.base_url}/api{path}"
        headers = self._headers({"Accept": "text/event-stream", "Content-Type": "application/json"})
        try:
            with httpx.Client(timeout=httpx.Timeout(300.0, connect=15.0)) as client:
                with client.stream("POST", url, headers=headers, json=payload) as resp:
                    if resp.status_code >= 400:
                        body = resp.read().decode("utf-8", "ignore")[:500]
                        try:
                            body = json.loads(body).get("detail") or body
                        except ValueError:
                            pass
                        raise CliError(f"HTTP {resp.status_code}: {body}", 1)
                    for line in resp.iter_lines():
                        line = (line or "").strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            yield {"type": "done"}
                            return
                        try:
                            yield json.loads(data)
                        except ValueError:
                            continue
        except httpx.HTTPError as exc:
            raise CliError(f"流式请求失败：{exc.__class__.__name__}", 3) from exc
