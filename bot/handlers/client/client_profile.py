"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""
# Site Company: buy-bot.ru

from aiogram import Dispatcher, F
from aiogram.types import CallbackQuery

from bot.integrations import DB
from bot.keyboards.client import kb_client_profile


async def profile(call: CallbackQuery, alert: bool = False):
    user_data = DB.User.select(mark=call.from_user.id)
    await call.message.edit_text(f'<b>📅Дата регистрации:</b> <code>{user_data.date_reg}</code>',
                                 reply_markup=kb_client_profile.main)
    if not alert:
        await call.answer()


def register_handlers_client_profile(dp: Dispatcher):
    dp.callback_query.register(profile, F.data == 'client_profile')
