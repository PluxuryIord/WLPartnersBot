"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from aiogram.fsm.state import State, StatesGroup


class FsmAdminList(StatesGroup):
    search = State()


class FsmAddAdmin(StatesGroup):
    access = State()
