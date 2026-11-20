"""API Key / 密钥的静态加密。

设计目标：不把任何第三方 API Key 以明文写进 SQLite；同时不强制引入新的运行时
依赖。优先使用 `cryptography` 的 AES-256-GCM；若不可用，退化为标准库实现的
HMAC-SHA256 计数器流 + HMAC-SHA256 认证标签（encrypt-then-MAC）。

主密钥来源（按优先级）：
1. 环境变量 `APP_SECRET`（任意长度字符串，经 PBKDF2-HMAC-SHA256 派生）；
2. `APP_SECRET_FILE` 指定的文件；
3. `DATA_DIR/.app_secret`（首次启动自动生成 32 字节随机密钥，权限尽量设为 0600）。

注意：主密钥丢失后，已加密的 API Key 无法恢复，需要在界面中重新填写。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from functools import lru_cache
from pathlib import Path

PREFIX = "enc:v1:"
_AAD = b"overachievers:api-key:v1"
_KDF_SALT = b"overachievers:app-secret:v1"

try:  # pragma: no cover - 取决于运行环境
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    _HAS_AESGCM = True
except Exception:  # pragma: no cover
    AESGCM = None  # type: ignore[assignment]
    _HAS_AESGCM = False


class SecretDecryptError(RuntimeError):
    """密文损坏或主密钥已变化。"""


def _data_dir() -> Path:
    raw = os.environ.get("DATA_DIR")
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parents[2] / "data"


def _read_key_file(path: Path) -> bytes:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SecretDecryptError(f"无法读取主密钥文件：{path}") from exc
    if len(raw) < 16:
        raise SecretDecryptError("主密钥文件内容过短")
    return raw


def _ensure_key_file(path: Path) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError:
        return _read_key_file(path)
    with os.fdopen(fd, "wb") as fh:
        key = secrets.token_bytes(32)
        fh.write(key)
    try:  # POSIX 权限；Windows 上由用户目录 ACL 兜底
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


@lru_cache(maxsize=1)
def _master_key() -> tuple[bytes, str]:
    env = os.environ.get("APP_SECRET", "").strip()
    if env:
        key = hashlib.pbkdf2_hmac("sha256", env.encode("utf-8"), _KDF_SALT, 200_000, dklen=32)
        return key, "APP_SECRET"
    raw_path = os.environ.get("APP_SECRET_FILE", "").strip()
    path = Path(raw_path) if raw_path else (_data_dir() / ".app_secret")
    if path.exists():
        return hashlib.sha256(_read_key_file(path)).digest(), "file"
    return hashlib.sha256(_ensure_key_file(path)).digest(), "generated-file"


def reset_key_cache() -> None:
    """测试或多环境切换时清空主密钥缓存。"""
    _master_key.cache_clear()


def _subkeys() -> tuple[bytes, bytes]:
    master, _ = _master_key()
    enc = hmac.new(master, b"enc", hashlib.sha256).digest()
    mac = hmac.new(master, b"mac", hashlib.sha256).digest()
    return enc, mac


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _hmac_stream(key: bytes, nonce: bytes, data: bytes) -> bytes:
    """HMAC-SHA256 计数器流：同一 (key, nonce) 下与明文异或。"""
    out = bytearray(len(data))
    counter = 0
    pos = 0
    while pos < len(data):
        block = hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        take = min(len(block), len(data) - pos)
        for i in range(take):
            out[pos + i] = data[pos + i] ^ block[i]
        pos += take
        counter += 1
    return bytes(out)


def _encrypt_fallback(plaintext: bytes) -> bytes:
    enc_key, mac_key = _subkeys()
    nonce = secrets.token_bytes(16)
    cipher = _hmac_stream(enc_key, nonce, plaintext)
    tag = hmac.new(mac_key, _AAD + nonce + cipher, hashlib.sha256).digest()[:16]
    return nonce + cipher + tag


def _decrypt_fallback(blob: bytes) -> bytes:
    if len(blob) < 32:
        raise SecretDecryptError("密文长度不足")
    enc_key, mac_key = _subkeys()
    nonce, cipher, tag = blob[:16], blob[16:-16], blob[-16:]
    expect = hmac.new(mac_key, _AAD + nonce + cipher, hashlib.sha256).digest()[:16]
    if not hmac.compare_digest(tag, expect):
        raise SecretDecryptError("密文校验失败：主密钥可能已变化")
    return _hmac_stream(enc_key, nonce, cipher)


def is_encrypted(value: str | None) -> bool:
    return bool(value) and str(value).startswith(PREFIX)


def encrypt_secret(plaintext: str | None) -> str:
    """加密明文；空值返回空串；已加密的原样返回（幂等）。"""
    if not plaintext:
        return ""
    text = str(plaintext)
    if is_encrypted(text):
        return text
    raw = text.encode("utf-8")
    if _HAS_AESGCM:
        master, _ = _master_key()
        nonce = secrets.token_bytes(12)
        blob = AESGCM(master).encrypt(nonce, raw, _AAD)  # type: ignore[union-attr]
        return f"{PREFIX}gcm:{_b64(nonce + blob)}"
    blob = _encrypt_fallback(raw)
    return f"{PREFIX}hmac:{_b64(blob)}"


def decrypt_secret(value: str | None) -> str:
    """解密；非加密格式原样返回（兼容旧库）；失败抛 SecretDecryptError。"""
    if not value:
        return ""
    text = str(value)
    if not is_encrypted(text):
        return text
    body = text[len(PREFIX) :]
    try:
        scheme, payload = body.split(":", 1)
    except ValueError as exc:
        raise SecretDecryptError("密文格式不合法") from exc
    try:
        blob = _unb64(payload)
    except Exception as exc:
        raise SecretDecryptError("密文不是合法 Base64") from exc

    if scheme == "gcm":
        if not _HAS_AESGCM or len(blob) < 13:
            raise SecretDecryptError("当前环境不支持 AES-GCM 解密")
        master, _ = _master_key()
        try:
            return AESGCM(master).decrypt(blob[:12], blob[12:], _AAD).decode("utf-8")  # type: ignore[union-attr]
        except Exception as exc:
            raise SecretDecryptError("密文校验失败：主密钥可能已变化") from exc
    if scheme == "hmac":
        return _decrypt_fallback(blob).decode("utf-8")
    raise SecretDecryptError(f"未知的加密方案：{scheme}")


def maybe_decrypt(value: str | None) -> str:
    try:
        return decrypt_secret(value)
    except SecretDecryptError:
        return ""


def mask_key(key: str | None) -> str:
    if not key:
        return ""
    text = str(key)
    if len(text) <= 8:
        return "****"
    return text[:4] + "****" + text[-4:]


def fingerprint(value: str, kind: str = "") -> bytes:
    """给脱敏占位符用的确定性指纹；不暴露原值。"""
    master, _ = _master_key()
    msg = f"privacy:{kind}:{value}".encode("utf-8")
    return hmac.new(master, msg, hashlib.sha256).digest()


def placeholder_for(kind: str, value: str) -> str:
    """稳定占位符：同一值在同一主密钥下始终得到同一 token。"""
    import base64

    raw = fingerprint(value, kind)
    code = base64.b32encode(raw).decode("ascii").rstrip("=")[:8]
    safe_kind = "".join(ch for ch in kind.upper() if ch.isalnum() or ch == "_") or "PII"
    return "{{" + safe_kind + "_" + code + "}}"


def secret_status() -> dict:
    master, source = _master_key()
    return {
        "encrypted": True,
        "scheme": "aes-256-gcm" if _HAS_AESGCM else "hmac-sha256-stream",
        "key_source": source,
        "key_fingerprint": hashlib.sha256(master).hexdigest()[:12],
    }


def check_secret_roundtrip() -> bool:
    probe = "overachievers-roundtrip-probe"
    try:
        return decrypt_secret(encrypt_secret(probe)) == probe
    except Exception:
        return False
