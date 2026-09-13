import asyncio
import logging
from datetime import datetime, timezone
from telegram.ext import ContextTypes
from database.db_manager import get_all_pending_messages, delete_message_record
from config import ADMIN_USER_ID, TIMEZONE
import pytz

class AdminReporter:
    def __init__(self):
        self.failed_reasons = {}

    def _get_local_time(self, utc_datetime):
        """تبدیل UTC به زمان محلی با استفاده از TIMEZONE"""
        local_tz = pytz.timezone(TIMEZONE)
        local_time = utc_datetime.astimezone(local_tz)
        return local_time

    def _format_local_time(self, utc_datetime):
        """فرمت زمان محلی به صورت HH:MM YYYY/MM/DD"""
        local_time = self._get_local_time(utc_datetime)
        return local_time.strftime('%H:%M %Y/%m/%d')

    def _create_message_link(self, chat_id, message_id, username):
        """Create text link for message"""
        # If username exists, it means it's a public channel or group
        if username:
            return f"https://t.me/{username}/{message_id}"

        # If chat_id is negative, it means it's a private group or channel
        elif chat_id < 0:
            # Remove -100 prefix from chat_id
            # For example, -1001234567890 becomes 1234567890
            chat_id_str = str(chat_id)
            if chat_id_str.startswith('-100'):
                chat_id_without_prefix = chat_id_str[4:]  # Remove '-100'
            else:
                chat_id_without_prefix = chat_id_str[1:]  # Remove only '-'
            return f"https://t.me/c/{chat_id_without_prefix}/{message_id}"

        # For other rare cases, return null link
        return None

    async def send_deletion_report(self, context: ContextTypes.DEFAULT_TYPE):
        """ارسال گزارش کامل پیام‌های حذف نشده به ادمین"""
        if not ADMIN_USER_ID:
            logging.warning("ADMIN_USER_ID not set, skipping report")
            return

        try:
            pending_messages = await get_all_pending_messages()

            if not pending_messages:
                await context.bot.send_message(
                    chat_id=ADMIN_USER_ID,
                    text="✅ هیچ پیام pending برای حذف وجود ندارد."
                )
                return

            # ساخت گزارش
            report = self._build_report(pending_messages)

            # ارسال گزارش
            await self._send_report_chunks(context, report)

        except Exception as e:
            logging.error(f"Error sending admin report: {e}")
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=f"❌ خطا در ایجاد گزارش: {e}"
            )

    def _build_report(self, pending_messages):
        """ساخت گزارش کامل"""
        report = f"📊 **گزارش پیام‌های Pending**\n\n"

        for record in pending_messages:
            id_, chat_id, message_id, username, delete_at_str, handler_name, created_at, error_message = record

            try:
                delete_at = datetime.fromisoformat(delete_at_str.replace('Z', '+00:00'))
                delete_at_local = self._format_local_time(delete_at)
                info_message = f"chat\\_id: {chat_id}, message\\_id: {message_id}"
                message_link = self._create_message_link(chat_id, message_id, username)

                report += f"  **ساعت حذف:** `{delete_at_local}`\n"
                report += f"** {info_message}\n"
                report += f"  **لینک:** {message_link}\n"
                if error_message:
                    report += f"  **خطا:** `{error_message}`\n"
                report += "\n"

            except Exception as e:
                logging.error(f"Error processing record {record}: {e}")
                report += f"• **ID:** `{message_id}` - خطا در پردازش: `{e}`\n\n"

        return report

    async def _send_report_chunks(self, context, report):
        """ارسال گزارش به صورت chunk (به دلیل محدودیت طول پیام)"""
        max_length = 4000

        if len(report) <= max_length:
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=report,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
        else:
            # تقسیم به چندین پیام
            chunks = [report[i:i + max_length] for i in range(0, len(report), max_length)]

            for i, chunk in enumerate(chunks):
                header = f"📄 **بخش {i + 1}/{len(chunks)}**\n\n" if i > 0 else ""
                await context.bot.send_message(
                    chat_id=ADMIN_USER_ID,
                    text=header + chunk,
                    parse_mode='Markdown',
                    disable_web_page_preview=True
                )
                await asyncio.sleep(1)  # تاخیر برای جلوگیری از rate limit

    async def test_specific_message(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
        """تست حذف کردن یک پیام خاص و گزارش نتیجه"""
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            result = f"✅ پیام {message_id} از چت {chat_id} با موفقیت حذف شد"
        except Exception as e:
            error_str = str(e).lower()
            if "message can't be deleted" in error_str or "too old" in error_str:
                result = f"🚫 پیام {message_id} از چت {chat_id} خیلی قدیمی است (محدودیت 48h تلگرام)\n`{str(e)}`"
            elif "message to delete not found" in error_str:
                result = f"❓ پیام {message_id} از چت {chat_id} پیدا نشد (شاید قبلاً حذف شده)\n`{str(e)}`"
            else:
                result = f"❌ خطا در حذف پیام {message_id} از چت {chat_id}:\n`{str(e)}`"

        await context.bot.send_message(
            chat_id=ADMIN_USER_ID,
            text=result,
            parse_mode='Markdown'
        )
        return result

    async def cleanup_old_records(self, context: ContextTypes.DEFAULT_TYPE):
        """حذف همه رکوردهای موجود در دیتابیس"""
        try:
            pending_messages = await get_all_pending_messages()
            cleaned_count = 0

            for record in pending_messages:
                id_, chat_id, message_id, username, delete_at_str, handler_name, created_at, error_message = record
                await delete_message_record(id_)
                cleaned_count += 1
                logging.info(f"Cleaned record: chat_id={chat_id}, message_id={message_id}")

            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=f"🧹 **تمیز کاری انجام شد**\n{cleaned_count} رکورد حذف شد."
            )

        except Exception as e:
            logging.error(f"Error in cleanup: {e}")
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=f"❌ خطا در تمیز کاری: {e}"
            )

# اضافه کردن به job scheduler
async def generate_admin_report(context: ContextTypes.DEFAULT_TYPE):
    """Job function برای ارسال گزارش دوره‌ای به ادمین"""
    reporter = AdminReporter()
    await reporter.send_deletion_report(context)

# کامندهای ادمین
async def admin_report_cmd(update, context):
    """کامند دستی برای درخواست گزارش"""
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ شما ادمین نیستید!")
        return

    reporter = AdminReporter()
    await reporter.send_deletion_report(context)
    await update.message.reply_text("📊 گزارش ارسال شد!")

async def admin_test_msg_cmd(update, context):
    """تست حذف کردن یک پیام خاص"""
    if update.effective_user.id != ADMIN_USER_ID:
        return

    if len(context.args) != 2:
        await update.message.reply_text("استفاده: /test_msg chat_id message_id")
        return

    try:
        chat_id = int(context.args[0])
        message_id = int(context.args[1])

        reporter = AdminReporter()
        await reporter.test_specific_message(context, chat_id, message_id)

    except ValueError:
        await update.message.reply_text("❌ chat_id و message_id باید عدد باشد!")

async def admin_cleanup_cmd(update, context):
    """حذف همه رکوردهای دیتابیس"""
    if update.effective_user.id != ADMIN_USER_ID:
        return

    reporter = AdminReporter()
    await reporter.cleanup_old_records(context)