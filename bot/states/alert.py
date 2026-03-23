"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from aiogram.fsm.state import State, StatesGroup


class FsmNewAlert(StatesGroup):
    message = State()
    preload = State()
    buttons = State()
    button_url = State()
    button_name = State()
    filter = State()
    input_users = State()


class FsmSearchHistory(StatesGroup):
    search = State()
