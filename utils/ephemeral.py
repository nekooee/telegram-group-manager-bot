"""Helpers for Telegram Bot API 10.2 ephemeral messages via PTB api_kwargs."""

import asyncio
import logging
from typing import Any, Optional

from telegram import Bot, InlineKeyboardMarkup, Message, Update
from telegram.constants import ChatType

from config import EPHEMERAL_MESSAGE_TTL_SECONDS

logger = logging.getLogger(__name__)


def ephemeral_ttl_enabled() -> bool:
    return EPHEMERAL_MESSAGE_TTL_SECONDS > 0


def is_group_chat(chat) -> bool:
    return chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)


def get_ephemeral_message_id(message: Message) -> Optional[str]:
    if message is None:
        return None
    eid = message.api_kwargs.get("ephemeral_message_id")
    if eid is not None:
        return str(eid)
    return None


def _serialize_reply_markup(reply_markup: Optional[InlineKeyboardMarkup]) -> Optional[dict[str, Any]]:
    if reply_markup is None:
        return None
    if hasattr(reply_markup, "to_dict"):
        return reply_markup.to_dict()
    return reply_markup  # type: ignore[return-value]


async def send_ephemeral_message(
    bot: Bot,
    chat_id: int,
    user_id: int,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: Optional[str] = None,
    reply_to_ephemeral_id: Optional[str | int] = None,
) -> Message:
    api_kwargs: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "ephemeral_message_parameters": {"receiver_user_id": user_id},
    }
    if parse_mode is not None:
        api_kwargs["parse_mode"] = parse_mode
    markup = _serialize_reply_markup(reply_markup)
    if markup is not None:
        api_kwargs["reply_markup"] = markup
    if reply_to_ephemeral_id is not None:
        api_kwargs["reply_parameters"] = {
            "ephemeral_message_id": int(reply_to_ephemeral_id),
        }

    result = await bot.do_api_request("sendMessage", api_kwargs=api_kwargs)
    if isinstance(result, Message):
        return result
    return Message.de_json(result, bot)


async def edit_ephemeral_message(
    bot: Bot,
    chat_id: int,
    receiver_user_id: int,
    ephemeral_message_id: str | int,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> bool:
    api_kwargs: dict[str, Any] = {
        "chat_id": chat_id,
        "receiver_user_id": receiver_user_id,
        "ephemeral_message_id": int(ephemeral_message_id),
        "text": text,
    }
    if reply_markup is not None:
        api_kwargs["reply_markup"] = reply_markup
    return await bot.do_api_request("editEphemeralMessageText", api_kwargs=api_kwargs)


async def delete_ephemeral_message(
    bot: Bot,
    chat_id: int,
    receiver_user_id: int,
    ephemeral_message_id: str | int,
) -> bool:
    return await bot.do_api_request(
        "deleteEphemeralMessage",
        api_kwargs={
            "chat_id": chat_id,
            "receiver_user_id": receiver_user_id,
            "ephemeral_message_id": int(ephemeral_message_id),
        },
    )


def schedule_ephemeral_delete(
    bot: Bot,
    chat_id: int,
    receiver_user_id: int,
    ephemeral_message_id: str | int,
    delay_seconds: Optional[float] = None,
) -> None:
    if not ephemeral_ttl_enabled():
        return

    delay = delay_seconds if delay_seconds is not None else EPHEMERAL_MESSAGE_TTL_SECONDS

    async def _delete_later() -> None:
        await asyncio.sleep(delay)
        try:
            await delete_ephemeral_message(
                bot,
                chat_id,
                receiver_user_id,
                ephemeral_message_id,
            )
        except Exception as exc:
            logger.error("scheduled ephemeral delete failed: %s", exc)

    asyncio.create_task(_delete_later())


def schedule_message_delete(
    bot: Bot,
    chat_id: int,
    message_id: int,
    delay_seconds: Optional[float] = None,
) -> None:
    """Delete a normal chat message (requires bot delete permission in groups)."""
    if not ephemeral_ttl_enabled() or not message_id or message_id <= 0:
        return

    delay = delay_seconds if delay_seconds is not None else EPHEMERAL_MESSAGE_TTL_SECONDS

    async def _delete_later() -> None:
        await asyncio.sleep(delay)
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as exc:
            logger.error("scheduled message delete failed mid=%s: %s", message_id, exc)

    asyncio.create_task(_delete_later())


def schedule_user_message_cleanup(
    bot: Bot,
    chat_id: int,
    user_id: int,
    message: Message,
    delay_seconds: Optional[float] = None,
) -> None:
    """Auto-delete a normal user message after TTL (not ephemeral slash commands)."""
    del user_id  # reserved for callers; deleteMessage addresses by message_id
    if message is None:
        return
    schedule_message_delete(bot, chat_id, message.message_id, delay_seconds)


def resolve_ephemeral_message_id(flow: Optional[dict], update: Update) -> Optional[str]:
    if flow and flow.get("ephemeral_message_id"):
        return str(flow["ephemeral_message_id"])

    query = update.callback_query
    if query and query.message:
        eid = get_ephemeral_message_id(query.message)
        if eid:
            return eid

    return None


async def reply_ephemeral_or_text(
    update: Update,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: Optional[str] = None,
    reply_to_ephemeral_id: Optional[str | int] = None,
) -> Message:
    chat = update.effective_chat
    user = update.effective_user
    bot = update.get_bot()

    if is_group_chat(chat):
        return await send_ephemeral_message(
            bot,
            chat.id,
            user.id,
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            reply_to_ephemeral_id=reply_to_ephemeral_id,
        )

    return await update.message.reply_text(
        text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
    )


async def answer_callback(callback_query, text: Optional[str] = None) -> None:
    await callback_query.answer(text=text, show_alert=bool(text))
