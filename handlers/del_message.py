import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from telegram import Update
from telegram.ext import ContextTypes
from .base_handler import BaseHandler
from config import DELETE_AFTER_HOURS
from database.db_manager import save_message_for_deletion, get_expired_messages, delete_message_record
from translations import t


class DelMessageHandler(BaseHandler):
    def __init__(self):
        super().__init__(t("del_message.handler_name"))

    def get_command_name(self) -> str:
        return "del"

    def _extract_hours_from_text(self, message_text: str) -> float:
        """Extract hours from message text based on different units (d=day, h=hour, m=minute)"""
        # Split text into parts
        parts = message_text.strip().split()

        # If only "/del", return default from config
        if len(parts) == 1:
            return DELETE_AFTER_HOURS

        # If second parameter exists
        if len(parts) >= 2:
            time_param = parts[1]

            # Different patterns for time units
            patterns = [
                (r'^(\d*\.?\d+)d$', 24),  # day - multiply by 24
                (r'^(\d*\.?\d+)h$', 1),   # hour - multiply by 1
                (r'^(\d*\.?\d+)m$', 1 / 60),  # minute - divide by 60
            ]

            for pattern, multiplier in patterns:
                match = re.match(pattern, time_param)
                if match:
                    try:
                        value = float(match.group(1))
                        hours = value * multiplier

                        # Security limits - max 10 days
                        if 0 < hours <= 240:  # max 10 days (10 * 24 = 240 hours)
                            return hours
                        else:
                            return DELETE_AFTER_HOURS
                    except ValueError:
                        continue

        # If no pattern matched, return default from config
        return DELETE_AFTER_HOURS

    async def validate_input(self, update: Update) -> tuple[bool, float]:
        """Validate input and return validity status + hours"""
        if not update.message.reply_to_message:
            await self.send_error_message(
                update,
                t("del_message.reply_required")
            )
            return False, 0

        # Extract hours from message text
        hours = self._extract_hours_from_text(update.message.text)

        return True, hours

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        is_valid, hours = await self.validate_input(update)
        if not is_valid:
            return

        chat_id = update.message.chat_id
        message_id = update.message.reply_to_message.message_id
        delete_at = datetime.now(timezone.utc) + timedelta(hours=hours)

        # Save in database
        await save_message_for_deletion(chat_id, message_id, delete_at.isoformat(), f'del_after_{hours}h')

        # Delete the command message
        try:
            await update.message.delete()
        except Exception as e:
            logging.error(t("del_message.command_delete_error", error=e))

        # Send confirmation message
        await self._send_confirmation(context, chat_id, message_id, hours)

    async def _send_confirmation(self, context, chat_id: int, message_id: int, hours: float):
        time_text = self._format_time_text(hours)
        try:
            notification = await context.bot.send_message(
                chat_id=chat_id,
                text=t("del_message.scheduled_confirmation", time_text=time_text),
                reply_to_message_id=message_id
            )

            await asyncio.sleep(10)
            await notification.delete()
        except Exception as e:
            logging.error(t("del_message.notification_error", error=e))

    def _format_time_text(self, hours: float) -> str:
        """Format time text based on hours value"""
        if hours >= 24:
            days = int(hours // 24)
            remaining_hours = hours % 24
            if remaining_hours > 0:
                return t("del_message.time_format.days_hours",
                        days=days, hours=f"{remaining_hours:.1f}")
            else:
                return t("del_message.time_format.days", days=days)
        elif hours >= 1:
            return t("del_message.time_format.hours", hours=f"{hours:.1f}")
        elif hours >= 1 / 60:  # more than one minute
            minutes = int(hours * 60)
            return t("del_message.time_format.minutes", minutes=minutes)
        else:
            seconds = int(hours * 3600)
            return t("del_message.time_format.seconds", seconds=seconds)


# Job function to delete expired messages
async def check_and_delete_expired_messages(context: ContextTypes.DEFAULT_TYPE):
    """Check and delete expired messages"""
    app = context.application
    now = datetime.now(timezone.utc).isoformat()

    try:
        expired_messages = await get_expired_messages(now)

        for id_, chat_id, message_id in expired_messages:
            try:
                await app.bot.delete_message(chat_id=chat_id, message_id=message_id)
                logging.info(t("del_message.deletion_success",
                              message_id=message_id, chat_id=chat_id))
            except Exception as e:
                logging.error(t("del_message.deletion_error",
                               message_id=message_id, error=e))

            # Delete record from database
            await delete_message_record(id_)

    except Exception as e:
        logging.error(t("del_message.check_error", error=e))