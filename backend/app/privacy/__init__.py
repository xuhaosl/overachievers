"""儿童隐私脱敏：magpie 风格的可逆占位符 + AstrLink Guard 本地模型适配。"""
from .astrlink import AstrLinkGuard
from .engine import (
    KIND_LABELS,
    LEVELS,
    PLACEHOLDER_RE,
    Finding,
    PrivacyEngine,
    PrivacyStats,
    StreamRestorer,
    build_lexicon,
    default_level,
    engine_for_db,
    privacy_status,
    zh_name_findings,
)

__all__ = [
    "AstrLinkGuard",
    "KIND_LABELS",
    "LEVELS",
    "PLACEHOLDER_RE",
    "Finding",
    "PrivacyEngine",
    "PrivacyStats",
    "StreamRestorer",
    "build_lexicon",
    "default_level",
    "engine_for_db",
    "privacy_status",
    "zh_name_findings",
]
