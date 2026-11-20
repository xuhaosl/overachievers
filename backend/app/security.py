"""出站请求安全校验。

所有由服务端主动发起的 HTTP 请求（AI Provider、连接测试等）都必须先经过
`validate_outbound_url()`：

- 仅允许 http / https；
- 拒绝 URL 内嵌用户名密码；
- 拒绝 localhost、回环、私有、链路本地、保留、组播、未指定地址；
- 域名先做 DNS 解析，任一解析结果命中上述网段即拒绝。

这可以挡住最常见的 SSRF / 内网探测路径。DNS 重绑定无法在纯应用层完全消除，
因此调用方应尽量复用校验后的 URL，并避免把用户可控的响应内容当作新 URL 请求。
"""
from __future__ import annotations

import ipaddress
import socket
import time
from urllib.parse import urlsplit

from fastapi import HTTPException

# 明确拒绝的本地域名后缀（DNS 解析前先挡一层）
_BLOCKED_SUFFIXES = (
    ".localhost",
    ".local",
    ".localdomain",
    ".internal",
    ".intranet",
    ".lan",
    ".home",
    ".corp",
    ".home.arpa",
)
_BLOCKED_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
    "metadata",
    "metadata.google.internal",
    "instance-data",
}

# 某些 Python 版本不会把以下网段算进 is_private，单独列出
_BLOCKED_NETWORKS = tuple(
    ipaddress.ip_network(n)
    for n in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",  # CGNAT
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "192.168.0.0/16",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "255.255.255.255/32",
        "::/128",
        "::1/128",
        "64:ff9b::/96",
        "100::/64",
        "2001:db8::/32",
        "fc00::/7",
        "fe80::/10",
        "ff00::/8",
    )
)

# 简单的 DNS 结果缓存：配置校验会被频繁调用，避免每次请求都阻塞在解析上
_DNS_CACHE: dict[str, tuple[float, tuple[str, ...]]] = {}
_DNS_TTL = 60.0


def _is_blocked_ip(raw: str) -> bool:
    try:
        ip = ipaddress.ip_address(raw.split("%", 1)[0])
    except ValueError:
        return True
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True
    return any(ip in net for net in _BLOCKED_NETWORKS)


def _resolve(host: str, port: int) -> tuple[str, ...]:
    now = time.monotonic()
    hit = _DNS_CACHE.get(host)
    if hit and now - hit[0] < _DNS_TTL:
        return hit[1]
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, OSError) as exc:
        raise HTTPException(400, f"接口地址无法解析：{host}（{exc.__class__.__name__}）") from exc
    addrs = tuple(dict.fromkeys(info[4][0] for info in infos if info[4]))
    if not addrs:
        raise HTTPException(400, f"接口地址无法解析：{host}")
    _DNS_CACHE[host] = (now, addrs)
    return addrs


def validate_outbound_url(url: str, *, field: str = "接口地址") -> str:
    """校验并返回去掉首尾空白的 URL；不合法时抛 400。"""
    value = (url or "").strip()
    if not value:
        raise HTTPException(400, f"{field}不能为空")

    try:
        parts = urlsplit(value)
    except ValueError as exc:
        raise HTTPException(400, f"{field}不合法") from exc

    if parts.scheme.lower() not in ("http", "https"):
        raise HTTPException(400, f"{field}只允许 http/https")
    if parts.username or parts.password:
        raise HTTPException(400, f"{field}不能包含用户名或密码")
    host = (parts.hostname or "").strip().lower().rstrip(".")
    if not host:
        raise HTTPException(400, f"{field}缺少域名")
    if any(ord(ch) < 32 or ch.isspace() for ch in host):
        raise HTTPException(400, f"{field}包含非法字符")
    if host in _BLOCKED_HOSTS or any(host.endswith(s) for s in _BLOCKED_SUFFIXES):
        raise HTTPException(400, f"{field}不允许指向本机或内网地址")

    try:
        port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
    except ValueError as exc:
        raise HTTPException(400, f"{field}端口不合法") from exc

    # 域名/IP 都要解析后校验；IP 字面量也会经过 getaddrinfo，保持路径一致
    for addr in _resolve(host, port):
        if _is_blocked_ip(addr):
            raise HTTPException(400, f"{field}不允许指向本机、内网或保留地址")
    return value


def is_private_host(host: str) -> bool:
    """给状态展示用：不做 DNS，仅判断字面量或明显本地域名。"""
    h = (host or "").strip().lower().rstrip(".")
    if not h:
        return True
    if h in _BLOCKED_HOSTS or any(h.endswith(s) for s in _BLOCKED_SUFFIXES):
        return True
    try:
        return _is_blocked_ip(h)
    except Exception:
        return False
