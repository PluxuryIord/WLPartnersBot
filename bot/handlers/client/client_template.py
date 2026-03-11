"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""
# Site Company: buy-bot.ru

from aiogram import Dispatcher, F
from aiogram.types import CallbackQuery

from bot.keyboards.client import *


async def main(call: CallbackQuery):
    ...


def register_handlers_client_profile(dp: Dispatcher):
    dp.callback_query.register(main, F.data == 'template')
