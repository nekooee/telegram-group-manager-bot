import os
from dotenv import load_dotenv

load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = os.getenv("DB_PATH", "messages.db")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))
ALLOWED_GROUPS = list(map(int, os.getenv("ALLOWED_GROUPS", "").split(","))) if os.getenv("ALLOWED_GROUPS") else []

# Language
LANGUAGE = os.getenv("LANGUAGE", "en")

# Translation Configuration
DEFAULT_TRANSLATE_TO = os.getenv("DEFAULT_TRANSLATE_TO", "en")
TRANSLATE_FROM = os.getenv("TRANSLATE_FROM", "auto")

# If True, the bot will only work in ALLOWED_GROUPS groups
# If False, the bot will work in all groups
RESTRICT_TO_ALLOWED_GROUPS = True

# Handler Configurations
DELETE_AFTER_HOURS = 24 #24H
SUPPORTED_IMAGE_FORMATS = ['.png', '.gif', '.bmp', '.webp', '.tiff', '.heic', '.heif', '.avif', '.jpg']