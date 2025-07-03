# translations.py
import json
import os


class Translator:
    def __init__(self, language="en"):
        self.language = language
        self.translations = {}
        self.load_translations()

    def load_translations(self):
        """Load translations from JSON file"""
        file_path = f"translations/{self.language}.json"

        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                self.translations = json.load(f)
        else:
            print(f"Translation file {file_path} not found")
            self.translations = {}

    def get(self, key, **kwargs):
        """Get translated text with optional formatting"""
        keys = key.split('.')
        value = self.translations

        try:
            for k in keys:
                value = value[k]
            return value.format(**kwargs) if kwargs else value
        except (KeyError, AttributeError):
            return key  # Return key if translation not found


# Global translator instance
_translator = None


def init_translator(language="en"):
    """Initialize translator"""
    global _translator
    _translator = Translator(language)


def t(key, **kwargs):
    """Get translation"""
    if _translator is None:
        init_translator()
    return _translator.get(key, **kwargs)