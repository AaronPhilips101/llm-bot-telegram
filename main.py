from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import defaultdict, deque
from typing import Deque, DefaultDict, Optional

import httpx
from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatAction, ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message

from config import AppConfig, load_config


class RateLimiter:
    def __init__(self, per_user_per_minute: int, per_chat_per_minute: int) -> None:
        self.per_user = per_user_per_minute
        self.per_chat = per_chat_per_minute
        self.user_events: DefaultDict[int, Deque[float]] = defaultdict(deque)
        self.chat_events: DefaultDict[int, Deque[float]] = defaultdict(deque)

    def _prune(self, events: Deque[float], now: float, window: float) -> None:
        while events and now - events[0] > window:
            events.popleft()

    def _check(self, events: Deque[float], limit: int, now: float) -> bool:
        if limit <= 0:
            return True
        self._prune(events, now, 60.0)
        return len(events) < limit

    def allow(self, user_id: int, chat_id: int) -> bool:
        now = time.monotonic()
        user_ok = self._check(self.user_events[user_id], self.per_user, now)
        chat_ok = self._check(self.chat_events[chat_id], self.per_chat, now)
        if not (user_ok and chat_ok):
            return False
        if self.per_user > 0:
            self.user_events[user_id].append(now)
        if self.per_chat > 0:
            self.chat_events[chat_id].append(now)
        return True


class OpenAICompatibleClient:
    def __init__(self, config: AppConfig) -> None:
        self.base_url = config.ai.base_url.rstrip("/")
        self.api_key = config.ai.api_key
        self.model = config.ai.model
        self.temperature = config.ai.temperature
        self.max_tokens = config.ai.max_tokens
        self.timeout_seconds = config.ai.timeout_seconds
        self.system_prompt = config.ai.system_prompt
        self._client = httpx.AsyncClient(timeout=self.timeout_seconds)

    def _chat_url(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        if self.base_url.endswith("/v1"):
            return f"{self.base_url}/chat/completions"
        return f"{self.base_url}/v1/chat/completions"

    async def close(self) -> None:
        await self._client.aclose()

    async def chat(self, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": self.system_prompt}] + messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = self._chat_url()
        response = await self._client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        if not content:
            raise ValueError("AI response was empty")
        return str(content).strip()


def _text_from_message(message: Message) -> Optional[str]:
    if message.text:
        return message.text
    if message.caption:
        return message.caption
    return None


def build_reply_chain(message: Message, bot_id: int, max_depth: int) -> list[dict[str, str]]:
    chain: list[dict[str, str]] = []
    current: Optional[Message] = message
    depth = 0
    while current and depth < max_depth:
        content = _text_from_message(current)
        if content:
            role = "assistant" if current.from_user and current.from_user.id == bot_id else "user"
            chain.append({"role": role, "content": content})
        current = current.reply_to_message
        depth += 1
    chain.reverse()
    return chain


async def _send_typing(bot: Bot, chat_id: int) -> None:
    try:
        while True:
            await bot.send_chat_action(chat_id, ChatAction.TYPING)
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass


async def create_app(config_path: str = "config.yaml") -> tuple[Dispatcher, Bot]:
    config = load_config(config_path)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    bot = Bot(token=config.telegram.bot_token)
    bot_info = await bot.get_me()
    bot_username = (bot_info.username or "").lower()
    bot_id = bot_info.id

    limiter = RateLimiter(
        per_user_per_minute=config.rate_limits.per_user_per_minute,
        per_chat_per_minute=config.rate_limits.per_chat_per_minute,
    )
    client = OpenAICompatibleClient(config)

    router = Router()

    def is_allowed_chat(message: Message) -> bool:
        if message.chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}:
            if config.telegram.allow_all_groups:
                return True
            return message.chat.id in config.telegram.allowed_group_ids
        if message.chat.type == ChatType.PRIVATE:
            return config.telegram.allow_private_chats
        return True

    def is_mention(message: Message) -> bool:
        text = message.text or message.caption or ""
        if not text or not bot_username:
            return False
        return f"@{bot_username}" in text.lower()

    def is_reply_to_bot(message: Message) -> bool:
        if not message.reply_to_message or not message.reply_to_message.from_user:
            return False
        return message.reply_to_message.from_user.id == bot_id

    @router.message(F.text | F.caption)
    async def handle_message(message: Message) -> None:
        text_preview = (message.text or message.caption or "").replace("\n", " ")
        logging.info(
            "Incoming message chat_id=%s type=%s text=%s",
            message.chat.id,
            message.chat.type,
            text_preview[:120],
        )
        if not is_allowed_chat(message):
            logging.info("Blocked by group/private allowlist chat_id=%s", message.chat.id)
            return

        if message.chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}:
            mentioned = is_mention(message)
            replied = is_reply_to_bot(message)
            if not (mentioned or replied):
                logging.info(
                    "Ignoring group message (no mention/reply) chat_id=%s",
                    message.chat.id,
                )
                return

        if not message.from_user:
            return

        if not limiter.allow(message.from_user.id, message.chat.id):
            if config.rate_limits.exceeded_message:
                await message.reply(config.rate_limits.exceeded_message)
            return

        typing_task = asyncio.create_task(
            _send_typing(bot, message.chat.id),
        )
        try:
            logging.info(
                "Handling message chat_id=%s user_id=%s",
                message.chat.id,
                message.from_user.id,
            )
            context_messages = build_reply_chain(
                message, bot_id=bot_id, max_depth=config.context.max_reply_chain
            )
            if not context_messages:
                return
            response = await client.chat(context_messages)
            if response:
                try:
                    await message.reply(response, allow_sending_without_reply=True)
                except TelegramAPIError:
                    await message.answer(response)
        except httpx.HTTPError as exc:
            logging.exception("AI API request failed: %s", exc)
            if config.ai.error_reply:
                await message.reply(config.ai.error_reply)
        except Exception as exc:
            logging.exception("Unhandled error: %s", exc)
            if config.ai.error_reply:
                await message.reply(config.ai.error_reply)
        finally:
            typing_task.cancel()

    dp = Dispatcher()
    dp.include_router(router)

    async def on_shutdown() -> None:
        await client.close()
        await bot.session.close()

    dp.shutdown.register(on_shutdown)
    return dp, bot


async def main() -> None:
    config_path = os.getenv("CONFIG_PATH", "config.yaml")
    dp, bot = await create_app(config_path)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
