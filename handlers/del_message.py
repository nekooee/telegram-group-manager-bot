import logging
from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import MAX_MESSAGE_AGE_HOURS
from database.db_manager import (
    cancel_pending_deletion,
    delete_message_record,
    get_expired_messages,
    get_pending_deletion,
    upsert_message_for_deletion,
    update_message_error,
)
from translations import t
from utils.ephemeral import (
    answer_callback,
    edit_ephemeral_message,
    get_ephemeral_message_id,
    is_group_chat,
    reply_ephemeral_or_text,
    resolve_ephemeral_message_id,
    schedule_ephemeral_delete,
    schedule_message_delete,
    schedule_user_message_cleanup,
)

from .base_handler import BaseHandler

DEL_FLOW_KEY = "del_flow"
MINUTE_PRESETS = (5, 10, 15, 30, 45, 60, 90, 120, 180, 240)
HOUR_PRESETS = (1, 2, 3, 6, 12, 24, 36, 47)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _max_delete_at(message_date: datetime) -> datetime:
    return _ensure_utc(message_date) + timedelta(hours=MAX_MESSAGE_AGE_HOURS)


def _remaining_seconds(message_date: datetime, now: datetime) -> float:
    return (_max_delete_at(message_date) - now).total_seconds()


def _format_time_text(hours: float) -> str:
    total_seconds = max(0, int(hours * 3600))
    days, rem = divmod(total_seconds, 86400)
    hours_part, rem = divmod(rem, 3600)
    minutes_part, seconds_part = divmod(rem, 60)

    if days > 0:
        if hours_part > 0:
            return t(
                "del_message.time_format.days_hours",
                days=days,
                hours=hours_part,
            )
        return t("del_message.time_format.days", days=days)
    if hours_part > 0 and minutes_part > 0:
        return t(
            "del_message.time_format.hours_minutes",
            hours=hours_part,
            minutes=minutes_part,
        )
    if hours_part > 0:
        return t("del_message.time_format.hours", hours=hours_part)
    if minutes_part > 0:
        return t("del_message.time_format.minutes", minutes=minutes_part)
    return t("del_message.time_format.seconds", seconds=seconds_part)


def _cancel_row() -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(
            t("del_message.ui.cancel"),
            callback_data="del:cancel",
        ),
    ]


def _format_time_until_delete(delete_at_str: str) -> str:
    delete_at = datetime.fromisoformat(delete_at_str)
    if delete_at.tzinfo is None:
        delete_at = delete_at.replace(tzinfo=timezone.utc)
    hours = max(0, (delete_at - _utc_now()).total_seconds() / 3600)
    return _format_time_text(hours)


def _unit_keyboard(has_pending: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                t("del_message.ui.minutes"),
                callback_data="del:unit:m",
            ),
            InlineKeyboardButton(
                t("del_message.ui.hours"),
                callback_data="del:unit:h",
            ),
        ],
    ]
    if has_pending:
        rows.append(
            [
                InlineKeyboardButton(
                    t("del_message.ui.unschedule"),
                    callback_data="del:unschedule",
                ),
            ]
        )
    rows.append(_cancel_row())
    return InlineKeyboardMarkup(rows)


def _value_keyboard(unit: str, message_date: datetime) -> InlineKeyboardMarkup:
    now = _utc_now()
    remaining_hours = _remaining_seconds(message_date, now) / 3600
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []

    if unit == "m":
        presets = [m for m in MINUTE_PRESETS if m / 60 <= remaining_hours]
        label_fn = lambda v: t("del_message.ui.minute_label", value=v)
        data_fn = lambda v: f"del:val:m:{v}"
    else:
        presets = [h for h in HOUR_PRESETS if h <= remaining_hours]
        label_fn = lambda v: t("del_message.ui.hour_label", value=v)
        data_fn = lambda v: f"del:val:h:{v}"

    for value in presets:
        row.append(InlineKeyboardButton(label_fn(value), callback_data=data_fn(value)))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    rows.append(
        [
            InlineKeyboardButton(
                t("del_message.ui.custom"),
                callback_data=f"del:custom:{unit}",
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                t("del_message.ui.back"),
                callback_data="del:back:unit",
            ),
        ]
    )
    rows.append(_cancel_row())
    return InlineKeyboardMarkup(rows)


def _clear_flow(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(DEL_FLOW_KEY, None)


def _get_flow(context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    return context.user_data.get(DEL_FLOW_KEY)


def _set_flow(context: ContextTypes.DEFAULT_TYPE, data: dict) -> None:
    context.user_data[DEL_FLOW_KEY] = data


def _schedule_flow_ui_cleanup(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    flow: dict,
) -> None:
    chat_id = update.effective_chat.id
    receiver_user_id = flow.get("initiated_by") or update.effective_user.id
    eid = resolve_ephemeral_message_id(flow, update)

    if eid and is_group_chat(update.effective_chat):
        schedule_ephemeral_delete(context.bot, chat_id, receiver_user_id, eid)
        return

    if update.callback_query and update.callback_query.message:
        schedule_message_delete(
            context.bot,
            chat_id,
            update.callback_query.message.message_id,
        )


async def _cancel_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    flow = _get_flow(context)
    await _edit_flow_ui(
        update,
        context,
        t("del_message.ui.cancelled"),
        reply_markup=InlineKeyboardMarkup([]),
    )
    _schedule_flow_ui_cleanup(update, context, flow)
    _clear_flow(context)


async def _edit_flow_ui(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    flow = _get_flow(context)
    bot = context.bot
    chat_id = update.effective_chat.id
    receiver_user_id = (flow.get("initiated_by") if flow else None) or update.effective_user.id
    eid = resolve_ephemeral_message_id(flow, update)

    if eid and is_group_chat(update.effective_chat):
        if flow is not None:
            flow["ephemeral_message_id"] = eid
            _set_flow(context, flow)
        await edit_ephemeral_message(
            bot,
            chat_id,
            receiver_user_id,
            eid,
            text,
            reply_markup=reply_markup,
        )
        return

    if update.callback_query and update.callback_query.message:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
        return

    msg = await reply_ephemeral_or_text(update, text, reply_markup=reply_markup)
    if flow is not None:
        eid = get_ephemeral_message_id(msg)
        if eid:
            flow["ephemeral_message_id"] = eid
            _set_flow(context, flow)


async def _finalize_schedule(
    context: ContextTypes.DEFAULT_TYPE,
    flow: dict,
    unit: str,
    value: int,
    update: Update,
) -> None:
    now = _utc_now()
    message_date = datetime.fromisoformat(flow["message_date"])
    target_chat_id = flow["target_chat_id"]
    target_message_id = flow["target_message_id"]

    if unit == "m":
        delay = timedelta(minutes=value)
    else:
        delay = timedelta(hours=value)

    max_at = _max_delete_at(message_date)
    requested_at = now + delay
    delete_at = min(requested_at, max_at)
    capped = requested_at > max_at

    if delete_at <= now:
        await _edit_flow_ui(
            update,
            context,
            t("del_message.too_old"),
            reply_markup=InlineKeyboardMarkup([]),
        )
        _schedule_flow_ui_cleanup(update, context, flow)
        _clear_flow(context)
        return

    handler_name = f"del_after_{value}{unit}"
    await upsert_message_for_deletion(
        target_chat_id,
        target_message_id,
        delete_at.isoformat(),
        handler_name,
    )

    actual_hours = (delete_at - now).total_seconds() / 3600
    time_text = _format_time_text(actual_hours)
    text = t("del_message.scheduled_confirmation", time_text=time_text)
    if capped:
        max_hours = max(0, _remaining_seconds(message_date, now) / 3600)
        max_text = _format_time_text(max_hours)
        text += "\n\n" + t("del_message.capped_warning", max_time=max_text)

    await _edit_flow_ui(
        update,
        context,
        text,
        reply_markup=InlineKeyboardMarkup([]),
    )
    _schedule_flow_ui_cleanup(update, context, flow)
    _clear_flow(context)


class DelMessageHandler(BaseHandler):
    def __init__(self):
        super().__init__(t("del_message.handler_name"))

    def get_command_name(self) -> str:
        return "del"

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message.reply_to_message:
            await self.send_error_message(update, t("del_message.reply_required"))
            return

        reply = update.message.reply_to_message
        now = _utc_now()
        remaining = _remaining_seconds(reply.date, now)

        if remaining <= 0:
            await self.send_error_message(update, t("del_message.too_old"))
            return

        if _get_flow(context):
            _clear_flow(context)

        chat_id = update.message.chat_id
        message_id = reply.message_id
        cmd_eid = get_ephemeral_message_id(update.message)
        pending = await get_pending_deletion(chat_id, message_id)
        has_pending = pending is not None
        if has_pending:
            time_text = _format_time_until_delete(pending[4])
            unit_prompt = t("del_message.ui.already_scheduled", time_text=time_text)
        else:
            unit_prompt = t("del_message.ui.choose_unit")

        _set_flow(
            context,
            {
                "target_chat_id": chat_id,
                "target_message_id": message_id,
                "message_date": _ensure_utc(reply.date).isoformat(),
                "ephemeral_message_id": None,
                "awaiting_custom": False,
                "unit": None,
                "initiated_by": update.effective_user.id,
                "has_pending": has_pending,
            },
        )

        msg = await reply_ephemeral_or_text(
            update,
            unit_prompt,
            reply_markup=_unit_keyboard(has_pending),
            reply_to_ephemeral_id=cmd_eid,
        )

        eid = get_ephemeral_message_id(msg)
        if eid:
            flow = _get_flow(context)
            flow["ephemeral_message_id"] = eid
            _set_flow(context, flow)


async def del_flow_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        return

    flow = _get_flow(context)
    if not flow:
        await answer_callback(query, t("del_message.ui.session_expired"))
        return

    if flow.get("initiated_by") and query.from_user.id != flow["initiated_by"]:
        await answer_callback(query)
        return

    cq_msg = query.message
    if cq_msg:
        eid = get_ephemeral_message_id(cq_msg)
        if eid:
            flow["ephemeral_message_id"] = eid
            _set_flow(context, flow)

    data = query.data
    message_date = datetime.fromisoformat(flow["message_date"])

    if data == "del:cancel":
        await answer_callback(query)
        await _cancel_flow(update, context)
        return

    if data == "del:unschedule":
        await answer_callback(query)
        removed = await cancel_pending_deletion(
            flow["target_chat_id"],
            flow["target_message_id"],
        )
        flow["has_pending"] = False
        _set_flow(context, flow)
        text = (
            t("del_message.ui.unscheduled")
            if removed
            else t("del_message.ui.not_scheduled")
        )
        await _edit_flow_ui(
            update,
            context,
            text,
            reply_markup=InlineKeyboardMarkup([]),
        )
        _schedule_flow_ui_cleanup(update, context, flow)
        _clear_flow(context)
        return

    if data == "del:back:unit":
        flow["awaiting_custom"] = False
        flow["unit"] = None
        _set_flow(context, flow)
        await answer_callback(query)
        pending = await get_pending_deletion(flow["target_chat_id"], flow["target_message_id"])
        has_pending = pending is not None
        flow["has_pending"] = has_pending
        _set_flow(context, flow)
        if has_pending:
            prompt = t(
                "del_message.ui.already_scheduled",
                time_text=_format_time_until_delete(pending[4]),
            )
        else:
            prompt = t("del_message.ui.choose_unit")
        await _edit_flow_ui(
            update,
            context,
            prompt,
            reply_markup=_unit_keyboard(has_pending),
        )
        return

    if data.startswith("del:unit:"):
        unit = data.rsplit(":", 1)[1]
        flow["unit"] = unit
        flow["awaiting_custom"] = False
        _set_flow(context, flow)
        await answer_callback(query)
        prompt = (
            t("del_message.ui.choose_minutes")
            if unit == "m"
            else t("del_message.ui.choose_hours")
        )
        await _edit_flow_ui(
            update,
            context,
            prompt,
            reply_markup=_value_keyboard(unit, message_date),
        )
        return

    if data.startswith("del:custom:"):
        unit = data.rsplit(":", 1)[1]
        flow["unit"] = unit
        flow["awaiting_custom"] = True
        _set_flow(context, flow)
        await answer_callback(query)
        await _edit_flow_ui(
            update,
            context,
            t("del_message.ui.type_number"),
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            t("del_message.ui.back"),
                            callback_data=f"del:unit:{unit}",
                        ),
                    ],
                    _cancel_row(),
                ]
            ),
        )
        return

    if data.startswith("del:val:"):
        parts = data.split(":")
        if len(parts) != 4:
            await answer_callback(query)
            return
        unit, value_str = parts[2], parts[3]
        try:
            value = int(value_str)
        except ValueError:
            await answer_callback(query, t("del_message.ui.invalid_number"))
            return
        if value <= 0:
            await answer_callback(query, t("del_message.ui.invalid_number"))
            return
        await answer_callback(query)
        await _finalize_schedule(context, flow, unit, value, update)
        return

    await answer_callback(query)


async def del_flow_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    flow = _get_flow(context)
    if not flow or not flow.get("awaiting_custom"):
        return

    if update.effective_user.id != flow.get("initiated_by"):
        return

    text = (update.message.text or "").strip()
    if text.lower() in ("cancel", "لغو", "/cancel"):
        await _cancel_flow(update, context)
        schedule_user_message_cleanup(
            context.bot,
            update.effective_chat.id,
            update.effective_user.id,
            update.message,
        )
        return

    try:
        value = int(text)
    except ValueError:
        await reply_ephemeral_or_text(update, t("del_message.ui.invalid_number"))
        return

    if value <= 0:
        await reply_ephemeral_or_text(update, t("del_message.ui.invalid_number"))
        return

    unit = flow.get("unit")
    if not unit:
        return

    now = _utc_now()
    message_date = datetime.fromisoformat(flow["message_date"])
    remaining_hours = _remaining_seconds(message_date, now) / 3600
    requested_hours = value / 60 if unit == "m" else value
    if requested_hours > remaining_hours:
        max_text = _format_time_text(remaining_hours)
        await reply_ephemeral_or_text(
            update,
            t("del_message.capped_warning", max_time=max_text),
        )
        return

    schedule_user_message_cleanup(
        context.bot,
        update.effective_chat.id,
        update.effective_user.id,
        update.message,
    )

    await _finalize_schedule(context, flow, unit, value, update)


async def check_and_delete_expired_messages(context: ContextTypes.DEFAULT_TYPE):
    """Check and delete expired messages."""
    app = context.application
    now_utc = _utc_now().isoformat()

    try:
        expired_messages = await get_expired_messages(now_utc)

        for id_, chat_id, message_id, username, error_message in expired_messages:
            try:
                await app.bot.delete_message(chat_id=chat_id, message_id=message_id)
                await delete_message_record(id_)
                logging.info(
                    f"Deleted message {message_id} in chat {chat_id} "
                    f"(user={username or 'unknown'})"
                )
            except Exception as e:
                error_str = str(e).lower()
                if "message can't be deleted" in error_str or "too old" in error_str:
                    error_text = t("del_message.error_too_old_telegram")
                elif "message to delete not found" in error_str:
                    error_text = t("del_message.error_not_found")
                else:
                    error_text = t("del_message.deletion_error", message_id=message_id, error=e)
                await update_message_error(id_, error_text)
                logging.error(f"Delete failed {message_id}: {str(e)[:80]}")

    except Exception as e:
        logging.error(t("del_message.check_error", error=e))
