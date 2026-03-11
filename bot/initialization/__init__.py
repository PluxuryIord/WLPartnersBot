from .bot_commands import set_menu_commands
from .config import config, BotConfig, ThrottlingConfig, AlbumConfig
from .admin_access import admin_accesses, full_admin_access
from .bot_texts import bot_texts
from .modules_initialization import dispatcher_register_modules

bot_texts.load_db_texts()
