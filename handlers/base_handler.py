from abc import ABC, abstractmethod

from telegram import Update
from telegram.ext import ContextTypes

from utils.ephemeral import reply_ephemeral_or_text


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
        """Send error message (ephemeral in groups)."""
        await reply_ephemeral_or_text(update, f"❗ {message}")
