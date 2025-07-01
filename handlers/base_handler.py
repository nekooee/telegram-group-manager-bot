from abc import ABC, abstractmethod
from telegram import Update
from telegram.ext import ContextTypes


class BaseHandler(ABC):
    """Base class for all handlers"""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Main method that must be implemented in each handler"""
        pass

    @abstractmethod
    def get_command_name(self) -> str:
        """Command name related to this handler"""
        pass

    async def validate_input(self, update: Update) -> bool:
        """Validate input (optional)"""
        return True

    async def send_error_message(self, update: Update, message: str):
        """Send error message"""
        error_msg = await update.message.reply_text(f"❗ {message}")
        # Delete error message after 10 seconds
        import asyncio
        await asyncio.sleep(10)
        try:
            await error_msg.delete()
        except:
            pass
