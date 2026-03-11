"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram import Dispatcher
    from aiogram.fsm.context import FSMContext
    from aiogram.types import Message

from aiogram.filters.command import Command

from bot.initialization import config
from bot.keyboards.client import kb_client_menu
from bot.states.message_url import FsmUrl
from bot.utils.announce_bot import bot


async def url_files(message: Message, state: FSMContext):
    if message.chat.type == 'private':
        await message.delete()
        await bot.send_message(message.from_user.id, 'Ожидаю файл/фото/видео!',
                               reply_markup=kb_client_menu.delete_message)
        await state.set_state(FsmUrl.message)


async def answer_url_file(message: Message, state: FSMContext):
    if message.photo:
        answer = message.photo[-1].file_id
    elif message.document:
        answer = message.document.file_id
    elif message.animation:
        answer = message.animation.file_id
    elif message.audio:
        answer = message.audio.file_id
    elif message.video:
        answer = message.video.file_id
    else:
        await message.reply(message.html_text.replace(r'\n', r'\\n'),
                            parse_mode=None,
                            reply_markup=kb_client_menu.delete_message)
        return await state.clear()
    await message.delete()
    await bot.send_message(message.from_user.id, f'{answer}',
                           reply_markup=kb_client_menu.delete_message)
    await state.clear()


def register_handlers_files_fsm(dp: Dispatcher):
    dp.message.register(url_files, Command(commands="debug"), config.admin_filter)
    dp.message.register(answer_url_file, FsmUrl.message)
