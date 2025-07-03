import asyncio
import logging
import signal
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from config import BOT_TOKEN, DELETE_AFTER_HOURS, ADMIN_USER_ID, ALLOWED_GROUPS, RESTRICT_TO_ALLOWED_GROUPS, LANGUAGE
from database.db_manager import init_db
from handlers.del_message import DelMessageHandler, check_and_delete_expired_messages
from handlers.to_jpg import ToJpgHandler
from translations import init_translator, t

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


class TelegramBot:
    def __init__(self):
        self.app = None
        self.handlers = []
        self.should_stop = False
        self._register_handlers()

    def _register_handlers(self):
        """Register all handlers"""
        self.handlers = [
            DelMessageHandler(),
            ToJpgHandler(),
            # Add other handlers here
        ]

    def _is_group_allowed(self, chat_id):
        """Check if the group is allowed"""
        if not RESTRICT_TO_ALLOWED_GROUPS:
            return True

        # If private chat (positive ID), always allowed for admin
        if chat_id > 0:
            return True

        # For groups, check the allowed list
        return chat_id in ALLOWED_GROUPS

    async def _check_permissions(self, update, context):
        """Check access permissions"""
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id

        # In private chat, only admin is allowed
        if chat_id > 0:
            if user_id != ADMIN_USER_ID:
                await update.message.reply_text(
                    t("permissions.not_authorized_user")
                )
                return False

        # In groups, check the allowed groups list
        elif not self._is_group_allowed(chat_id):
            await update.message.reply_text(
                t("permissions.not_authorized_group", chat_id=chat_id)
            )
            logging.warning(f"Unauthorized request from group {chat_id} by user {user_id}")
            return False

        return True

    async def setup(self):
        """Setup the bot"""
        await init_db()

        self.app = ApplicationBuilder().token(BOT_TOKEN).build()

        # Add start command
        self.app.add_handler(CommandHandler("start", self._start_command))

        # Add command to show group ID
        self.app.add_handler(CommandHandler("groupid", self._groupid_command))

        # Add handlers
        for handler in self.handlers:
            command_handler = CommandHandler(
                handler.get_command_name(),
                self._wrap_handler_with_permission_check(handler.handle)
            )
            self.app.add_handler(command_handler)
            logging.info(f"Handler '{handler.name}' registered for /{handler.get_command_name()}")

        # Setup periodic jobs
        self._setup_jobs()

    def _wrap_handler_with_permission_check(self, original_handler):
        """Wrap handlers with permission check"""

        async def wrapped_handler(update, context):
            # Check permissions
            if not await self._check_permissions(update, context):
                return

            # Execute the original handler
            return await original_handler(update, context)

        return wrapped_handler

    def _setup_jobs(self):
        """Setup periodic jobs"""
        # For delete message handler - if time is less than 1 minute, check every 10 seconds
        check_interval = 10 if DELETE_AFTER_HOURS < 0.0167 else 60
        self.app.job_queue.run_repeating(
            check_and_delete_expired_messages,
            interval=check_interval,
            first=10
        )

    async def _start_command(self, update, context):
        """Start command"""
        # Check permissions
        if not await self._check_permissions(update, context):
            return

        commands = []
        for handler in self.handlers:
            commands.append(f"/{handler.get_command_name()} - {handler.name}")

        command_list = "\n".join(commands)

        chat_type = t("status.group") if update.effective_chat.id < 0 else t("status.private_chat")
        chat_id = update.effective_chat.id

        message = (
            f"{t('bot.greeting')}\n\n"
            f"{t('bot.current_environment', chat_type=chat_type)}\n"
            f"{t('bot.chat_id', chat_id=chat_id)}\n\n"
            f"{t('bot.available_commands')}\n{command_list}\n\n"
            f"{t('bot.usage_hint')}"
        )

        await update.message.reply_text(message)

    async def _groupid_command(self, update, context):
        """Show group or chat ID"""
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id

        # Only admin can see this command
        if user_id != ADMIN_USER_ID:
            await update.message.reply_text(t("permissions.not_authorized_command"))
            return

        chat_type = t("status.group") if chat_id < 0 else t("status.private_chat")
        is_allowed = t("status.allowed") if self._is_group_allowed(chat_id) else t("status.not_allowed")

        message = (
            f"{t('group_info.chat_information')}\n\n"
            f"{t('group_info.type', chat_type=chat_type)}\n"
            f"{t('group_info.id', chat_id=chat_id)}\n"
            f"{t('group_info.status', status=is_allowed)}\n\n"
            f"{t('group_info.add_hint')}"
        )

        await update.message.reply_text(message)

    async def run(self):
        """Run the bot"""
        await self.setup()

        logging.info(t("bot.ready"))

        restriction_status = t("status.enabled") if RESTRICT_TO_ALLOWED_GROUPS else t("status.disabled")
        logging.info(t("bot.group_restrictions", status=restriction_status))

        if RESTRICT_TO_ALLOWED_GROUPS and ALLOWED_GROUPS:
            logging.info(t("bot.allowed_groups", groups=ALLOWED_GROUPS))

        # Initialize the app
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()

        # Wait until we should stop
        while not self.should_stop:
            await asyncio.sleep(1)

        # Clean shutdown
        logging.info(t("bot.stopping"))
        await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()
        logging.info(t("bot.stopped"))

    def stop(self):
        """Stop the bot"""
        self.should_stop = True


def signal_handler(signum, frame, bot):
    """Handle stop signals"""
    logging.info(t("errors.received_signal", signal=signum))
    bot.stop()


async def main():
    # Initialize translator - only once at startup
    init_translator(LANGUAGE)

    bot = TelegramBot()

    # Setup signal handlers
    signal.signal(signal.SIGINT, lambda s, f: signal_handler(s, f, bot))
    signal.signal(signal.SIGTERM, lambda s, f: signal_handler(s, f, bot))

    try:
        await bot.run()
    except KeyboardInterrupt:
        logging.info(t("errors.keyboard_interrupt"))
    except Exception as e:
        logging.error(t("errors.unexpected_error", error=e))
    finally:
        logging.info(t("errors.exiting"))


if __name__ == "__main__":
    asyncio.run(main())