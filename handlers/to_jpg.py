import io
import os
import tempfile
import shutil
from PIL import Image
from telegram import Update
from telegram.ext import ContextTypes
from .base_handler import BaseHandler
from config import SUPPORTED_IMAGE_FORMATS

# برای پشتیبانی از HEIC
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIC_SUPPORTED = True
except ImportError:
    HEIC_SUPPORTED = False


class ToJpgHandler(BaseHandler):
    def __init__(self):
        super().__init__("Convert to JPG")

    def get_command_name(self) -> str:
        return "tojpg"

    async def validate_input(self, update: Update) -> bool:
        if not update.message.reply_to_message:
            await self.send_error_message(
                update,
                "لطفاً این دستور را در پاسخ (Reply) به یک پیام حاوی فایل تصویر ارسال کنید."
            )
            return False

        reply_msg = update.message.reply_to_message

        # بررسی وجود document یا photo
        if not reply_msg.document and not reply_msg.photo:
            await self.send_error_message(
                update,
                "پیام انتخاب شده حاوی فایل تصویر نیست. فقط فایل‌های تصویری پذیرفته می‌شوند."
            )
            return False

        # اگر document است، بررسی کنیم که تصویری باشد
        if reply_msg.document and not self._is_image_document(reply_msg.document):
            await self.send_error_message(
                update,
                "فایل انتخاب شده یک تصویر نیست."
            )
            return False

        return True

    def _create_temp_directory(self, message_id: int) -> str:
        """ایجاد پوشه موقت برای پیام"""
        temp_dir = tempfile.mkdtemp(prefix=f"tojpg_{message_id}_")
        return temp_dir

    def _cleanup_temp_directory(self, temp_dir: str):
        """حذف پوشه موقت"""
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except Exception as e:
            print(f"خطا در حذف پوشه موقت {temp_dir}: {e}")

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.validate_input(update):
            return

        # حذف پیام کامند
        try:
            await update.message.delete()
        except:
            pass

        # بررسی پارامتر photo در متن دستور
        command_text = update.message.text or ""
        send_as_photo = "photo" in command_text.lower()

        reply_msg = update.message.reply_to_message

        # پردازش فایل
        temp_dir = self._create_temp_directory(reply_msg.message_id)
        try:
            status_message = await reply_msg.reply_text("🔄 در حال تبدیل فایل...")
            try:
                await self._convert_single_message(reply_msg, context, send_as_photo, status_message, temp_dir)
            finally:
                try:
                    await status_message.delete()
                except:
                    pass
        finally:
            self._cleanup_temp_directory(temp_dir)

    def _is_image_document(self, document) -> bool:
        if not document.file_name:
            return False

        file_ext = os.path.splitext(document.file_name.lower())[1]
        supported_formats = [fmt.lower() for fmt in SUPPORTED_IMAGE_FORMATS]

        # اضافه کردن پشتیبانی از HEIC
        if HEIC_SUPPORTED:
            supported_formats.extend(['.heic', '.heif'])

        return file_ext.lower() in supported_formats

    async def _convert_single_message(self, message, context, send_as_photo=False, status_message=None, temp_dir=None):
        """تبدیل یک پیام (document یا photo)"""
        try:
            # تشخیص نوع فایل
            if message.document:
                file = await context.bot.get_file(message.document.file_id)
                original_name = message.document.file_name
            else:  # photo
                file = await context.bot.get_file(message.photo[-1].file_id)  # بزرگترین سایز
                original_name = f"photo_{message.message_id}.jpg"

            image_bytes = await file.download_as_bytearray()

            # ذخیره فایل اصلی موقت (برای HEIC)
            temp_original_path = os.path.join(temp_dir, original_name)
            with open(temp_original_path, 'wb') as f:
                f.write(image_bytes)

            jpg_bytes = await self._convert_to_jpg(image_bytes, temp_original_path)

            # نام فایل جدید
            new_name = os.path.splitext(original_name)[0] + ".jpg"

            # آپدیت وضعیت برای آپلود
            if status_message:
                await status_message.edit_text("⬆️ در حال آپلود...")

            if send_as_photo:
                await message.reply_photo(
                    photo=io.BytesIO(jpg_bytes)
                )
            else:
                await message.reply_document(
                    document=io.BytesIO(jpg_bytes),
                    filename=new_name
                )

            # حذف پیام وضعیت
            if status_message:
                try:
                    await status_message.delete()
                except:
                    pass

        except Exception as e:
            if status_message:
                try:
                    await status_message.edit_text(f"❌ خطا در تبدیل فایل: {str(e)}")
                except:
                    await message.reply_text(f"❌ خطا در تبدیل فایل: {str(e)}")
            else:
                await message.reply_text(f"❌ خطا در تبدیل فایل: {str(e)}")

    async def _convert_to_jpg(self, image_bytes: bytearray, temp_file_path: str = None) -> bytes:
        """تبدیل bytes تصویر به JPG با کیفیت بهینه"""
        try:
            # برای فایل‌های HEIC از مسیر فایل استفاده کن
            if temp_file_path and temp_file_path.lower().endswith(('.heic', '.heif')):
                if not HEIC_SUPPORTED:
                    raise Exception("فرمت HEIC پشتیبانی نمی‌شود. لطفاً pillow-heif را نصب کنید.")
                image = Image.open(temp_file_path)
            else:
                # باز کردن تصویر از bytes
                image = Image.open(io.BytesIO(image_bytes))

            # تبدیل به RGB در صورت نیاز
            if image.mode in ('RGBA', 'LA', 'P'):
                # ایجاد پس‌زمینه سفید
                rgb_image = Image.new('RGB', image.size, (255, 255, 255))

                if image.mode == 'P':
                    # تبدیل palette به RGBA
                    image = image.convert('RGBA')

                # اگر آلفا چنل داره، اون رو به عنوان ماسک استفاده کن
                if image.mode in ('RGBA', 'LA'):
                    rgb_image.paste(image, mask=image.split()[-1])
                else:
                    rgb_image.paste(image)

                image = rgb_image
            elif image.mode not in ('RGB', 'L'):
                # سایر فرمت‌ها رو به RGB تبدیل کن
                image = image.convert('RGB')

            # ذخیره به عنوان JPG با کیفیت متعادل (کمتر از 95)
            output = io.BytesIO()
            image.save(output, format='JPEG', quality=90, optimize=True)
            return output.getvalue()

        except Exception as e:
            raise Exception(f"خطا در تبدیل تصویر: {str(e)}")