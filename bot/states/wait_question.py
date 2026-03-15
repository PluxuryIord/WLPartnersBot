"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from aiogram.fsm.state import State, StatesGroup


class FsmWaitQuestion(StatesGroup):
    wait_text = State()

class FsmRegistration(StatesGroup):
    wait_text = State()
    wait_rl_name = State()
    wait_phone = State()
    wait_about_role = State()
    wait_traff = State()

class FsmAuth(StatesGroup):
    wait_email = State()
    wait_password = State()

class FsmEventAnketa(StatesGroup):
    answering = State()

class FsmAddQuestion(StatesGroup):
    wait_text = State()
    wait_type = State()
    wait_options = State()

class FsmEditQuestion(StatesGroup):
    wait_text = State()
    wait_options = State()