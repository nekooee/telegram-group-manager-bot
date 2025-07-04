import logging
from googletrans import Translator, LANGUAGES
from telegram import Update
from telegram.ext import ContextTypes
from config import DEFAULT_TRANSLATE_TO, TRANSLATE_FROM
from translations import t


class TranslateHandler:
    def __init__(self):
        self.name = t("translate.handler_name")

    def get_command_name(self):
        return "translate"

    def _get_language_code(self, lang_input):
        """Convert language input to valid language code"""
        if not lang_input:
            return None

        lang_input = lang_input.lower().strip()

        # If it's already a valid language code
        if lang_input in LANGUAGES:
            return lang_input

        # Search in language names
        for code, name in LANGUAGES.items():
            if name.lower() == lang_input:
                return code

        return None

    def _get_language_name(self, lang_code):
        """Get language name from code"""
        return LANGUAGES.get(lang_code, lang_code)

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle translate command"""
        try:
            # Check if command is a reply to a message
            if not update.message.reply_to_message:
                await update.message.reply_text(t("translate.reply_required"))
                return

            # Get the text to translate
            target_message = update.message.reply_to_message

            # Extract text from different message types
            text_to_translate = None
            if target_message.text:
                text_to_translate = target_message.text
            elif target_message.caption:
                text_to_translate = target_message.caption
            else:
                await update.message.reply_text(t("translate.no_text"))
                return

            # Get target language from command arguments
            target_language = DEFAULT_TRANSLATE_TO
            if context.args:
                provided_lang = context.args[0]
                lang_code = self._get_language_code(provided_lang)
                if lang_code:
                    target_language = lang_code
                else:
                    available_langs = ", ".join(list(LANGUAGES.keys())[:20])  # Show first 20 languages
                    await update.message.reply_text(
                        t("translate.invalid_language",
                          language=provided_lang,
                          examples=available_langs)
                    )
                    return

            # Send "translating..." message
            status_message = await update.message.reply_text(t("translate.translating"))

            # Perform translation and detection in single session
            try:
                async with Translator() as translator:
                    # Detect source language if auto-detect is enabled
                    source_language = TRANSLATE_FROM
                    detected_lang = None
                    confidence = 0

                    if source_language == "auto":
                        try:
                            detected = await translator.detect(text_to_translate)
                            detected_lang = detected.lang
                            confidence = detected.confidence
                            source_language = detected_lang
                        except Exception as e:
                            logging.error(f"Error detecting language: {e}")
                            source_language = "auto"  # Let translate handle it

                    # Check if source and target languages are the same
                    if source_language == target_language:
                        await status_message.edit_text(
                            t("translate.same_language",
                              language=self._get_language_name(target_language))
                        )
                        return

                    # Perform translation
                    translation = await translator.translate(
                        text_to_translate,
                        src=source_language,
                        dest=target_language
                    )

                    # Prepare response
                    source_lang_name = self._get_language_name(translation.src)
                    target_lang_name = self._get_language_name(translation.dest)

                    # Edit the status message with only the translated text
                    await status_message.edit_text(translation.text)

            except Exception as e:
                logging.error(f"Translation error: {e}")
                await status_message.edit_text(
                    t("translate.translation_error", error=str(e))
                )

        except Exception as e:
            logging.error(f"Error in translate handler: {e}")
            await update.message.reply_text(
                t("translate.general_error", error=str(e))
            )