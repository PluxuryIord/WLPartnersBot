"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from bot.initialization import config
from bot.integrations import DB
from . import default_texts


class BotTexts:
    def __init__(self):
        self.default_texts = default_texts
        self.menu = {}
        self.alert = {}
        self.admins = {}
        self.bot_info = {}
        self.admin_alert = {}
        self.start_debug = config.reset_texts

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
        self.menu = texts['menu']
        self.alert = texts['alert']
        self.admins = texts['add_admin']
        self.bot_info = texts['bot_info']
        self.admin_alert = texts['admin_alert']


bot_texts = BotTexts()
