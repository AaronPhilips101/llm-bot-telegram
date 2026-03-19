from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class TelegramConfig:
    bot_token: str
    allow_private_chats: bool
    allow_all_groups: bool
    allowed_group_ids: list[int]


@dataclass
class AIConfig:
    base_url: str
    api_key: str
    model: str
    temperature: float
    max_tokens: int
    timeout_seconds: int
    system_prompt: str
    error_reply: str


@dataclass
class RateLimitConfig:
    per_user_per_minute: int
    per_chat_per_minute: int
    exceeded_message: str


@dataclass
class ContextConfig:
    max_reply_chain: int


@dataclass
class AppConfig:
    telegram: TelegramConfig
    ai: AIConfig
    rate_limits: RateLimitConfig
    context: ContextConfig


def _require(data: dict[str, Any], key: str) -> Any:
    if key not in data:
        raise ValueError(f"Missing required config key: {key}")
    return data[key]


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    telegram = _require(raw, "telegram")
    ai = _require(raw, "ai")
    rate_limits = _require(raw, "rate_limits")
    context = raw.get("context", {})

    telegram_cfg = TelegramConfig(
        bot_token=str(_require(telegram, "bot_token")),
        allow_private_chats=bool(telegram.get("allow_private_chats", True)),
        allow_all_groups=bool(telegram.get("allow_all_groups", True)),
        allowed_group_ids=[int(x) for x in telegram.get("allowed_group_ids", [])],
    )

    ai_cfg = AIConfig(
        base_url=str(_require(ai, "base_url")).rstrip("/"),
        api_key=str(_require(ai, "api_key")),
        model=str(_require(ai, "model")),
        temperature=float(ai.get("temperature", 0.2)),
        max_tokens=int(ai.get("max_tokens", 300)),
        timeout_seconds=int(ai.get("timeout_seconds", 30)),
        system_prompt=str(ai.get("system_prompt", "You are a helpful assistant.")),
        error_reply=str(
            ai.get(
                "error_reply",
                "Sorry, I couldn't reach the AI service. Please try again.",
            )
        ),
    )

    rate_cfg = RateLimitConfig(
        per_user_per_minute=int(rate_limits.get("per_user_per_minute", 0)),
        per_chat_per_minute=int(rate_limits.get("per_chat_per_minute", 0)),
        exceeded_message=str(
            rate_limits.get(
                "exceeded_message",
                "You're sending messages too quickly. Please wait a moment.",
            )
        ),
    )

    context_cfg = ContextConfig(
        max_reply_chain=int(context.get("max_reply_chain", 8))
    )

    return AppConfig(
        telegram=telegram_cfg,
        ai=ai_cfg,
        rate_limits=rate_cfg,
        context=context_cfg,
    )
