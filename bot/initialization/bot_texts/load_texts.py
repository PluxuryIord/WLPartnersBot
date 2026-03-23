"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""
import json
import os

from bot.initialization import config
from bot.integrations import DB
from . import default_texts

CACHE_FILE = os.path.join(os.path.dirname(__file__), 'texts_cache.json')


class BotTexts:
    def __init__(self):
        self.default_texts = default_texts
        self.menu = {}
        self.alert = {}
        self.admins = {}
        self.bot_info = {}
        self.admin_alert = {}
        self.knowledge_base = {}
        self.landings = {}
        self.scenarios = {}
        self.start_debug = config.reset_texts

    def _save_cache(self, texts: dict):
        try:
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(texts, f, ensure_ascii=False)
        except Exception:
            pass

    def _load_cache(self) -> dict | None:
        try:
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return None

    def _apply_texts(self, texts: dict):
        self.menu = texts.get('menu', {})
        self.alert = texts.get('alert', {})
        self.admins = texts.get('add_admin', {})
        self.bot_info = texts.get('bot_info', {})
        self.admin_alert = texts.get('admin_alert', {})
        self.knowledge_base = texts.get('knowledge_base', {})
        self.landings = texts.get('landings', {})

    def _reload_keyboards(self):
        try:
            from bot.utils.dynamic_kb import reload
            reload()
        except Exception:
            pass

    def _load_scenarios(self):
        try:
            sc_row = DB.Text.select(where=DB.Text.category == 'bot_scenarios')
            if sc_row and sc_row.data:
                sc_data = sc_row.data if isinstance(sc_row.data, dict) else {}
                flat = {}
                for screen_id, screen in sc_data.get('screens', {}).items():
                    for msg_key, msg in screen.get('messages', {}).items():
                        flat[f'{screen_id}.{msg_key}'] = msg.get('text', '')
                self.scenarios = flat
        except Exception:
            pass

    def load_db_texts(self):
        categories = DB.Text.select(all_scalars=True)
        if not categories or self.start_debug:
            if self.start_debug:
                DB.Text.remove()
                self.start_debug = False
            for text in default_texts:
                DB.Text.add(text, default_texts[text][0], default_texts[text][1])
            categories = DB.Text.select(all_scalars=True)

        texts = {}
        for category in categories:
            category_key = category.category
            category_data = category.data
            for text in category_data:
                if category_key not in texts:
                    texts[category_key] = {}
                texts[category_key][text] = category_data[text]

        self._apply_texts(texts)
        self._load_scenarios()
        self._reload_keyboards()
        self._save_cache(texts)

    def load_from_cache(self):
        """Fast startup: load from local JSON, no DB needed."""
        cached = self._load_cache()
        if cached:
            self._apply_texts(cached)
            return True
        return False


bot_texts = BotTexts()
