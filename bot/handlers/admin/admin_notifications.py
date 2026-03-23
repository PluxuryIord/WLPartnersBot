"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram import Dispatcher
    from aiogram.types import CallbackQuery, Message

from aiogram.filters.command import Command
from aiogram import F

from sqlalchemy.sql.expression import true

from bot.keyboards.admin import kb_admin_notifications
from bot.integrations import DB
from bot.initialization import config, bot_texts
from bot.utils.announce_bot import bot
from bot.utils import dt as datetime
from bot.utils import telegram as telegram


async def notifications_menu(call: CallbackQuery):
    await call.message.edit_text(bot_texts.admin_alert['alert_menu'],
                                 reply_markup=kb_admin_notifications.notifications_buttons)
    await call.answer()


async def change_upgrade_notification(call: CallbackQuery):
    notification = not DB.AdminNotification.select(mark=call.from_user.id).upgrade
    DB.AdminNotification.update(mark=call.from_user.id, upgrade=notification)
    if notification:
        await call.answer('✅Вы успешно включили уведомления о обновлениях.', show_alert=True)
    else:
        await call.answer('✅Вы успешно отключили уведомления о обновлениях.', show_alert=True)


async def upgrade_notification(message: Message):
    await message.delete()
    version = message.text.split(' ', 1)[1]
    admins = DB.AdminNotification.select(where=(DB.AdminNotification.upgrade == true()), all_scalars=True)
    for admin in admins:
        await bot.send_message(admin.admin_id, f'<b>🔔Бот был обновлен до версии {version}.</b>',
                               reply_markup=telegram.kb_delete_message)
    DB.Settings.update(bot_version=version, last_update=datetime.now('datetime'))


async def change_registration_notification(call: CallbackQuery):
    notification = not DB.AdminNotification.select(mark=call.from_user.id).registration
    DB.AdminNotification.update(mark=call.from_user.id, registration=notification)
    if notification == 1:
        await call.answer('✅Вы успешно включили уведомления о регистрациях.', show_alert=True)
    else:
        await call.answer('✅Вы успешно отключили уведомления о регистрациях.', show_alert=True)


async def registration_notification(text: str):
    admins = DB.AdminNotification.select(where=(DB.AdminNotification.registration == true()), all_scalars=True)
    for admin in admins:
        await bot.send_message(admin.admin_id,
                               text,
                               reply_markup=telegram.kb_delete_message)


async def change_support_notification(call: CallbackQuery):
    notification = not DB.AdminNotification.select(mark=call.from_user.id).support
    DB.AdminNotification.update(mark=call.from_user.id, support=notification)
    if notification == 1:
        await call.answer('✅Вы успешно включили уведомления в топиках.', show_alert=True)
    else:
        await call.answer('✅Вы успешно отключили уведомления в топиках.', show_alert=True)


def register_handlers_admin_notifications(dp: Dispatcher):
    dp.callback_query.register(notifications_menu, F.data == "admin_notifications", config.admin_filter)
    dp.callback_query.register(change_upgrade_notification, F.data == "bot_upgrade_notification", config.admin_filter)
    dp.callback_query.register(change_support_notification, F.data == "bot_support_notification", config.admin_filter)
    dp.callback_query.register(change_registration_notification, F.data == "bot_registration_notification",
                               config.admin_filter)
    dp.message.register(upgrade_notification, Command(commands="version"), config.admin_filter)
