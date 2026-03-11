"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from environs import Env

env = Env()
env.read_env()

# Bot Object
bot = Bot(
    token=env.str("TG_TOKEN"),
    default=DefaultBotProperties(parse_mode='HTML', link_preview_is_disabled=True)
)
# Bot Dispatcher
dp = Dispatcher()
