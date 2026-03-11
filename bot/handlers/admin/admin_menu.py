"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.exceptions import TelegramAPIError
from aiogram.utils.markdown import hlink
from openpyxl.styles.builtins import comma

from bot.utils import telegram
from bot.utils.telegram import generate_user_hlink, create_inline

if TYPE_CHECKING:
    from aiogram import Dispatcher
    from aiogram.fsm.context import FSMContext
    from aiogram.types import CallbackQuery, Message

from aiogram.filters import Command, CommandObject
from aiogram import F

from bot.handlers.client import client_main
from bot.integrations import DB
from bot.keyboards.admin import kb_admin_menu
from bot.initialization import config, admin_accesses


async def admin_menu(call: CallbackQuery, state: FSMContext):
    if await state.get_state():
        await state.clear()
    if config.admin_filter:
        admin_role = 'Гл.Администратор' if config.admin_filter.is_system(call.from_user.id) else 'Администратор'
        await call.message.edit_text(
            f'<b>✅Вы успешно авторизовались как {admin_role}</b>\n\n'
            '<i>Открыты доступные инструменты бота.</i>',
            reply_markup=kb_admin_menu.main_menu(DB.Admin.select(mark=call.from_user.id).access, admin_accesses))
    else:
        await client_main.back_menu(call=call, state=state)
    await call.answer()


async def group_id(message: Message):
    other_info = f'\n<b>Message Thread ID:</b> <code>{message.message_thread_id}</code>' \
        if message.message_thread_id else ''

    await message.answer(f'<b>Chat ID:</b> <code>{message.chat.id}</code>{other_info}')
    await message.delete()


async def remove_kb(message: Message):
    await message.delete()
    temp_message = await message.answer('⏳', reply_markup=kb_admin_menu.remove_reply_kb)
    await temp_message.delete()

async def user(message: Message, command: CommandObject):
    if command:
        if command.args:
            url_link = f'tg://user?id={command.args}'
            link_user = hlink('Пользователь', url_link)
            user_data = DB.User.select(mark=int(command.args))
            if user_data:
                text = (f'👀 <b>{link_user} найден!\n\n'
                        f'ID пользователя: <code>{command.args}</code>\n'
                        f'Никнейм: {"@" + user_data.username if user_data.username else "Не установлен"}\n'
                        f'Отображаемое имя: {user_data.full_name if user_data.full_name else "Не установлено"}</b>')
                kb = create_inline([
                        ['О пользователе', 'url', url_link],
                        ['⤴️Открыть диалог', 'url', telegram.topic_manager.topic_url(user_data.thread_id)]
                    ], 1
                )
            else:
                text = f'👀 {link_user} найден!'
                kb = create_inline([
                        ['О пользователе', 'url', url_link]
                    ], 1)
            try:
                await message.reply(
                    text,
                    reply_markup=kb
                )
            except TelegramAPIError:
                await message.reply(
                    '❌ <b>Не смог найти данного пользователя!</b>'
                )
        else:
            await message.delete()
            await message.answer(
                '❌ <b>Не указан ID пользователя для поиска!</b>'
            )

def register_handlers_admin_main(dp: Dispatcher):
    dp.callback_query.register(admin_menu, F.data == "admin_menu")
    dp.message.register(group_id, Command(commands="id"), config.admin_filter)
    dp.message.register(remove_kb, Command(commands="remove_kb"), config.admin_filter)
    dp.message.register(user, Command(commands="user"), config.admin_filter)