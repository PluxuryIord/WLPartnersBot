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
    from aiogram.fsm.context import FSMContext

from aiogram import F
from aiogram.exceptions import TelegramAPIError

from bot.integrations import DB
from bot.initialization import config
from bot.utils.announce_bot import bot
from bot.utils import telegram as telegram
from bot.initialization import admin_access
from bot.states.admin_admins import FsmAddAdmin
from bot.initialization import bot_texts
from bot.keyboards.admin import kb_admin_topic, kb_admin_admins
from bot.states.topic import FSMRedactText
from bot.utils import dt as datetime


async def add_admin(call: CallbackQuery, user_data: DB.User = None):
    if config.admin_filter:
        target_user_id = int(call.data.split('|')[1])

        if target_user_id == call.from_user.id:
            await call.answer('❌Нельзя применить на самого себя', show_alert=True)
            return
        elif DB.Admin.select(mark=target_user_id):
            await call.answer('❌Пользователь уже администратор', show_alert=True)
            return

        admin_data = DB.Admin.select(mark=call.from_user.id)
        if not admin_data.access['admins']:
            await call.answer('❌У вас нет прав на управление администраторами', show_alert=True)
            return

        if not user_data:
            await call.answer('❌Недостаточно прав!', show_alert=True)
            return

        state = await telegram.get_state(call.from_user.id, call.from_user.id)
        await state.set_state(FsmAddAdmin.access)
        access = admin_access.null_admin_access.copy()
        await state.update_data(new_admin=target_user_id, access=access)
        await telegram.delete_message(chat_id=call.from_user.id, message_id=user_data.menu_id)
        new_menu = await telegram.send_message(chat_id=call.from_user.id, text=bot_texts.admins['access'],
                                               reply_markup=kb_admin_admins.select_access(access))
        DB.User.update(mark=call.from_user.id, menu_id=new_menu.message_id)
        await call.answer('✅Бот написал вам в личные сообщения!', show_alert=True)
    else:
        await call.answer('❌Недостаточно прав!', show_alert=True)


async def delete_message(call: CallbackQuery):
    db_id = int(call.data.split('|')[1])
    message_data = DB.TopicMessages.select(mark=db_id)
    message_ids = message_data.messages['ids']
    for message_id in message_ids:
        deleted = await telegram.delete_message(chat_id=message_data.chat_id, message_id=message_id, try_redact=False)
        if not deleted:
            await call.answer('❌Сообщение устарело или его уже не существует', show_alert=True)
            return
    await call.answer('✅Успешно удалено', show_alert=True)
    await call.message.edit_text(
        f'<b>🚮Удалено администратором: <code>{call.from_user.id}</code> | '
        f'<code>{call.from_user.full_name}</code> | '
        f'<code>{call.from_user.username if call.from_user.username else "без ника"}</code></b>')
    DB.TopicMessages.remove(mark=db_id)


async def redact_text(call: CallbackQuery, state: FSMContext):
    db_id = int(call.data.split('|')[1])
    await state.set_state(FSMRedactText.text)
    temp_message = await call.message.reply(
        text=f'<b>{telegram.generate_user_hlink(call)}, отправьте новый текст для сообщения!</b>',
        reply_markup=kb_admin_topic.edit_cancel
    )
    await call.answer('⬇️')
    await state.update_data(menu=call.message, temp_message=temp_message, db_id=db_id)


async def input_redact_text(message: Message, state: FSMContext, menu_id: Message):
    storage = await state.get_data()
    temp_message: Message = storage['temp_message']
    await telegram.edit_text(temp_message, '⏳')
    if message.text:
        message_data = DB.TopicMessages.select(mark=storage['db_id'])
        message_ids = message_data.messages['ids']
        await telegram.delete_message(chat_id=temp_message.chat.id, message_id=temp_message.message_id,
                                      try_redact=False)
        try:
            if message_data.messages['caption']:
                await bot.edit_message_caption(
                    chat_id=message_data.chat_id, message_id=message_ids[0], caption=message.html_text)
            else:
                await bot.edit_message_text(
                    chat_id=message_data.chat_id, message_id=message_ids[0], text=message.html_text)
            new_text = f'<b>✏️Отредактировано администратором ({datetime.now()}): ' \
                       f'<code>{message.from_user.id}</code> | ' \
                       f'<code>{message.from_user.full_name}</code> | ' \
                       f'<code>{message.from_user.username if message.from_user.username else "без ника"}' \
                       f'</code></b>'
            await menu.edit_text(text=menu.html_text + '\n\n' + new_text, reply_markup=menu.reply_markup)
            await message.reply(f'{telegram.generate_user_hlink(message)}\n\n<b>✅Сообщение отредактировано</b>')
        except TelegramAPIError:
            await message.delete()
            await message.answer(f'{telegram.generate_user_hlink(message)}\n\n'
                                 f'<b>❌Не удалось отредактировать сообщение</b>')
        await state.clear()
    else:
        await message.delete()
        await telegram.edit_text(temp_message, '<b>❌Ошибка!</b>\n\n<i>Я ожидаю текст!</i>',
                                 reply_markup=kb_admin_topic.edit_cancel)


async def edit_cancel(call: CallbackQuery, state: FSMContext):
    storage = await state.get_data()
    temp_message: Message = storage['temp_message']
    await telegram.delete_message(chat_id=temp_message.chat.id, message_id=temp_message.message_id, try_redact=False)
    await state.clear()
    await call.answer('✅Операция отменена', show_alert=True)


def register_handlers_admin_topics(dp: Dispatcher):
    dp.callback_query.register(add_admin, F.data == "topic_add_admin")
    dp.callback_query.register(delete_message, F.data.startswith('topic_delete_message|'))
    dp.callback_query.register(redact_text, F.data.startswith('topic_redact_text|'))
    dp.message.register(input_redact_text, FSMRedactText.text)
    dp.callback_query.register(edit_cancel, F.data == 'topic_edit_cancel', FSMRedactText.text)
