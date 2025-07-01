import asyncio
from telegram import Message


async def delete_message_after_delay(message: Message, delay_seconds: int = 10):
    """حذف پیام بعد از مدت زمان مشخص"""
    await asyncio.sleep(delay_seconds)
    try:
        await message.delete()
    except Exception:
        pass


def format_file_size(size_bytes: int) -> str:
    """تبدیل سایز فایل به فرمت قابل خواندن"""
    if size_bytes == 0:
        return "0B"

    size_names = ["B", "KB", "MB", "GB"]
    import math
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"


def is_image_file(filename: str) -> bool:
    """بررسی اینکه فایل تصویر است یا نه"""
    if not filename:
        return False

    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.svg'}
    import os
    file_ext = os.path.splitext(filename.lower())[1]
    return file_ext in image_extensions
