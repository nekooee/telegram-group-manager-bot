import io
import os
import tempfile
import shutil
from PIL import Image
from telegram import Update
from telegram.ext import ContextTypes
from .base_handler import BaseHandler
from config import SUPPORTED_IMAGE_FORMATS
from translations import t

# For HEIC support
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIC_SUPPORTED = True
except ImportError:
    HEIC_SUPPORTED = False


class ToJpgHandler(BaseHandler):
    def __init__(self):
        super().__init__(t("to_jpg.handler_name"))

    def get_command_name(self) -> str:
        return "tojpg"

    async def validate_input(self, update: Update) -> bool:
        if not update.message.reply_to_message:
            await self.send_error_message(
                update,
                t("to_jpg.reply_required")
            )
            return False

        reply_msg = update.message.reply_to_message

        # Check for document or photo existence
        if not reply_msg.document and not reply_msg.photo:
            await self.send_error_message(
                update,
                t("to_jpg.no_image")
            )
            return False

        # If it's a document, check if it's an image
        if reply_msg.document and not self._is_image_document(reply_msg.document):
            await self.send_error_message(
                update,
                t("to_jpg.not_image_document")
            )
            return False

        return True

    def _create_temp_directory(self, message_id: int) -> str:
        """Create temporary directory for the message"""
        temp_dir = tempfile.mkdtemp(prefix=f"tojpg_{message_id}_")
        return temp_dir

    def _cleanup_temp_directory(self, temp_dir: str):
        """Delete temporary directory"""
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except Exception as e:
            print(t("to_jpg.temp_cleanup_error", temp_dir=temp_dir, error=e))

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.validate_input(update):
            return

        # Delete command message
        try:
            await update.message.delete()
        except:
            pass

        # Check for photo parameter in command text
        command_text = update.message.text or ""
        send_as_photo = "photo" in command_text.lower()

        reply_msg = update.message.reply_to_message

        # Process file
        temp_dir = self._create_temp_directory(reply_msg.message_id)
        try:
            status_message = await reply_msg.reply_text(t("to_jpg.converting"))
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

        # Add HEIC support
        if HEIC_SUPPORTED:
            supported_formats.extend(['.heic', '.heif'])

        return file_ext.lower() in supported_formats

    async def _convert_single_message(self, message, context, send_as_photo=False, status_message=None, temp_dir=None):
        """Convert a single message (document or photo)"""
        try:
            # Detect file type
            if message.document:
                file = await context.bot.get_file(message.document.file_id)
                original_name = message.document.file_name
            else:  # photo
                file = await context.bot.get_file(message.photo[-1].file_id)  # largest size
                original_name = f"photo_{message.message_id}.jpg"

            image_bytes = await file.download_as_bytearray()

            # Save temporary original file (for HEIC)
            temp_original_path = os.path.join(temp_dir, original_name)
            with open(temp_original_path, 'wb') as f:
                f.write(image_bytes)

            jpg_bytes = await self._convert_to_jpg(image_bytes, temp_original_path)

            # New filename
            new_name = os.path.splitext(original_name)[0] + ".jpg"

            # Update status for upload
            if status_message:
                await status_message.edit_text(t("to_jpg.uploading"))

            if send_as_photo:
                await message.reply_photo(
                    photo=io.BytesIO(jpg_bytes)
                )
            else:
                await message.reply_document(
                    document=io.BytesIO(jpg_bytes),
                    filename=new_name
                )

            # Delete status message
            if status_message:
                try:
                    await status_message.delete()
                except:
                    pass

        except Exception as e:
            error_message = t("to_jpg.conversion_error", error=str(e))
            if status_message:
                try:
                    await status_message.edit_text(error_message)
                except:
                    await message.reply_text(error_message)
            else:
                await message.reply_text(error_message)

    async def _convert_to_jpg(self, image_bytes: bytearray, temp_file_path: str = None) -> bytes:
        """Convert image bytes to JPG with optimal quality"""
        try:
            # For HEIC files, use file path
            if temp_file_path and temp_file_path.lower().endswith(('.heic', '.heif')):
                if not HEIC_SUPPORTED:
                    raise Exception(t("to_jpg.heic_not_supported"))
                image = Image.open(temp_file_path)
            else:
                # Open image from bytes
                image = Image.open(io.BytesIO(image_bytes))

            # Convert to RGB if needed
            if image.mode in ('RGBA', 'LA', 'P'):
                # Create white background
                rgb_image = Image.new('RGB', image.size, (255, 255, 255))

                if image.mode == 'P':
                    # Convert palette to RGBA
                    image = image.convert('RGBA')

                # If it has alpha channel, use it as mask
                if image.mode in ('RGBA', 'LA'):
                    rgb_image.paste(image, mask=image.split()[-1])
                else:
                    rgb_image.paste(image)

                image = rgb_image
            elif image.mode not in ('RGB', 'L'):
                # Convert other formats to RGB
                image = image.convert('RGB')

            # Save as JPG with balanced quality (less than 95)
            output = io.BytesIO()
            image.save(output, format='JPEG', quality=90, optimize=True)
            return output.getvalue()

        except Exception as e:
            raise Exception(t("to_jpg.image_conversion_error", error=str(e)))