"""多 Provider 注册表与 OpenAI 兼容请求构造。

项目里的所有厂商都通过 OpenAI 兼容的 `/chat/completions` 协议接入：
DeepSeek、通义千问、Kimi、智谱、OpenAI、OpenRouter、SiliconFlow、Groq、
Mistral，以及用户自填的 OpenAI 兼容服务。

每个机器人（AiBot）可以独立配置 base_url / model / temperature / max_tokens /
超时 / 额外请求头 / 故障回退机器人。API Key 只以密文存库，读取时解密。
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException

from . import crypto
from .security import validate_outbound_url

# 2026-10 各厂商 OpenAI 兼容入口；模型名只是候选项，界面允许直接输入任意模型名
PROVIDERS: dict[str, dict[str, Any]] = {
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "models": ["deepseek-flash", "deepseek-v4-pro"],
        "docs": "https://api-docs.deepseek.com",
        "supports_tools": True,
    },
    "qwen": {
        "label": "通义千问（阿里百炼）",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen3.8-max", "qwen3.8-flash", "qwen-plus"],
        "docs": "https://help.aliyun.com/zh/model-studio/base-url",
        "supports_tools": True,
    },
    "kimi": {
        "label": "Kimi（月之暗面）",
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["kimi-k3", "kimi-k2.6"],
        "docs": "https://platform.kimi.com/docs/api/overview",
        "supports_tools": True,
    },
    "zhipu": {
        "label": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-5.3", "glm-5-turbo"],
        "docs": "https://docs.bigmodel.cn/cn/api/introduction",
        "supports_tools": True,
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-5.2", "gpt-5.2-mini", "o4-mini"],
        "docs": "https://platform.openai.com/docs/api-reference",
        "supports_tools": True,
    },
    "openrouter": {
        "label": "OpenRouter（聚合）",
        "base_url": "https://openrouter.ai/api/v1",
        "models": [
            "openai/gpt-5.2",
            "anthropic/claude-sonnet-4.6",
            "google/gemini-3-pro",
            "deepseek/deepseek-v4",
        ],
        "docs": "https://openrouter.ai/docs",
        "supports_tools": True,
    },
    "siliconflow": {
        "label": "SiliconFlow（硅基流动）",
        "base_url": "https://api.siliconflow.cn/v1",
        "models": ["deepseek-ai/DeepSeek-V4", "Qwen/Qwen3.8-72B", "zai-org/GLM-5.3"],
        "docs": "https://docs.siliconflow.cn",
        "supports_tools": True,
    },
    "groq": {
        "label": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "models": ["llama-4.1-70b-versatile", "qwen-3.8-32b"],
        "docs": "https://console.groq.com/docs",
        "supports_tools": True,
    },
    "mistral": {
        "label": "Mistral",
        "base_url": "https://api.mistral.ai/v1",
        "models": ["mistral-large-3", "mistral-small-3"],
        "docs": "https://docs.mistral.ai",
        "supports_tools": True,
    },
    "custom": {
        "label": "OpenAI 兼容自定义",
        "base_url": "",
        "models": [],
        "docs": "",
        "supports_tools": True,
    },
}

PROVIDER_KEYS = tuple(PROVIDERS)


def provider_info(key: str) -> dict[str, Any]:
    return PROVIDERS.get(key, {})


def provider_list() -> list[dict[str, Any]]:
    return [{"key": key, **value} for key, value in PROVIDERS.items()]


def resolve_base_url(provider: str, base_url: str | None) -> str:
    value = (base_url or "").strip() or PROVIDERS.get(provider, {}).get("base_url", "")
    if not value:
        raise HTTPException(400, "接口地址不能为空")
    return value.rstrip("/")


def chat_url(base_url: str) -> str:
    base = (base_url or "").rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def validate_provider_url(provider: str, base_url: str | None, *, field: str = "接口地址") -> str:
    value = resolve_base_url(provider, base_url)
    return validate_outbound_url(value, field=field)


def bot_api_key(bot: Any) -> str:
    """读取机器人明文 Key：优先 api_key_enc，兼容旧库的 api_key 明文。"""
    enc = getattr(bot, "api_key_enc", "") or ""
    if enc:
        try:
            return crypto.decrypt_secret(enc)
        except crypto.SecretDecryptError:
            return ""
    legacy = getattr(bot, "api_key", "") or ""
    return crypto.maybe_decrypt(legacy) if crypto.is_encrypted(legacy) else legacy


def store_api_key(bot: Any, api_key: str) -> None:
    """把明文 Key 加密写入 bot.api_key_enc，并清空旧明文列。空值表示保留。"""
    if not api_key:
        return
    bot.api_key_enc = crypto.encrypt_secret(api_key)
    bot.api_key = ""


def parse_extra_headers(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    try:
        obj = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return {}
    if not isinstance(obj, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in obj.items():
        key = str(k).strip()
        if not key or not key.isascii():
            continue
        val = str(v).strip()
        if len(key) > 64 or len(val) > 512:
            continue
        out[key] = val
    return out


def headers_for(bot: Any, api_key: str | None = None) -> dict[str, str]:
    key = api_key if api_key is not None else bot_api_key(bot)
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    headers.update(parse_extra_headers(getattr(bot, "extra_headers", "")))
    return headers


def bot_payload(
    bot: Any,
    messages: list[dict[str, Any]],
    *,
    stream: bool,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": (getattr(bot, "model", "") or "").strip(),
        "messages": messages,
        "stream": bool(stream),
        "temperature": float(
            temperature if temperature is not None else getattr(bot, "temperature", 0.7) or 0.7
        ),
        "max_tokens": int(
            max_tokens if max_tokens is not None else getattr(bot, "max_tokens", 1600) or 1600
        ),
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice or "auto"
    return payload


def bot_out_dict(bot: Any) -> dict[str, Any]:
    key = bot_api_key(bot)
    return {
        "id": bot.id,
        "name": bot.name,
        "provider": bot.provider,
        "provider_label": provider_info(bot.provider).get("label", bot.provider),
        "base_url": bot.base_url,
        "api_key_masked": crypto.mask_key(key),
        "has_key": bool(key),
        "model": bot.model,
        "temperature": getattr(bot, "temperature", 0.7),
        "max_tokens": getattr(bot, "max_tokens", 1600),
        "timeout": getattr(bot, "timeout", 120),
        "extra_headers": getattr(bot, "extra_headers", "") or "",
        "enabled": bool(getattr(bot, "enabled", True)),
        "is_default": bool(getattr(bot, "is_default", False)),
        "fallback_bot_id": getattr(bot, "fallback_bot_id", None),
        "supports_tools": bool(provider_info(bot.provider).get("supports_tools", True)),
    }
