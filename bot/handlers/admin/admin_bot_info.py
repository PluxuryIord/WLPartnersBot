"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram import Dispatcher
    from aiogram.types import CallbackQuery

import threading
import asyncio
import os
import pandas as pd
from datetime import datetime

from aiogram import F
from aiogram.utils.markdown import hlink
from aiogram.types import FSInputFile
from aiogram.exceptions import TelegramRetryAfter, TelegramAPIError

from bot.keyboards.admin import kb_admin_menu
from bot.integrations import DB, DBStats
from bot.initialization import config, bot_texts
from bot.utils.announce_bot import bot
from bot.utils import files
from bot.utils import telegram as telegram
from bot.utils.text_ending import users_counter_ending, once_ending, last_number


async def admin_bot_info(call: CallbackQuery):
    settings = DB.Settings.select()
    users = DB.User.select(all_scalars=True)
    date = datetime.now()
    params = {
        'date': date.strftime("%d.%m %H:%M"),
        'tech_work_status': 'Включены' if settings.engineering_works else 'Выключены',
        'last_start': settings.last_start.strftime("%d.%m.%y"),
        'bot_version': settings.bot_version,
        'last_update': settings.last_update.strftime("%d.%m.%y"),
        'all_user_count': len(users),
        'today_user_count': len([user for user in users if date.day == user.date_reg.day]),
        'link_developer': hlink(f'Buy-Bot', f'https://buy-bot.ru/')
    }
    await telegram.edit_text(call.message, bot_texts.bot_info['info'].format(**params),
                             reply_markup=kb_admin_menu.bot_info)
    await call.answer()


async def export_users(call: CallbackQuery):
    await call.message.edit_text(bot_texts.bot_info['export'], reply_markup=kb_admin_menu.export_users)
    await call.answer()


async def export_to_txt(call: CallbackQuery):
    await call.message.edit_text('⌛️Загрузка...')
    users = DB.User.select(all_scalars=True)
    users_to_text = ''
    for user in users:
        username = 'Отсутствует' if not user.username else '@' + user.username
        admin = 'Да' if DB.Admin.select(where=(DB.Admin.user == user)) else 'Нет'
        users_to_text += f'User ID: {user.user_id} | ' \
                         f'Отображаемое имя: {user.full_name} | ' \
                         f'Никнейм: {username} | ' \
                         f'Дата регистрации: {user.date_reg} | ' \
                         f'Админ: {admin}\n'
    file, path_remove = files.create_txt(users_to_text, True)
    base = FSInputFile(path_remove, filename="пользователи.txt")
    await call.message.edit_text(call.message.text, reply_markup=call.message.reply_markup)
    await bot.send_document(chat_id=call.from_user.id,
                            document=base,
                            reply_markup=telegram.kb_delete_message,
                            caption='✔️База успешно выгружена!', )
    os.remove(path_remove)
    await call.answer()


async def export_to_excel(call: CallbackQuery):
    await call.message.edit_text('⌛️Загрузка...')
    users = DB.User.select(all_scalars=True)
    ids = [user.user_id for user in users]
    full_names = [user.full_name for user in users]
    usernames = ['@' + user.username if user.username else 'Отсутствует' for user in users]
    reg_dates = [user.date_reg for user in users]
    admins_data = ['Да' if DB.Admin.select(where=(DB.Admin.user == user)) else 'Нет' for user in users]
    df = pd.DataFrame({'ID пользователя': ids,
                       'Никнейм': usernames,
                       'Отображаемое имя': full_names,
                       'Дата регистрации': reg_dates,
                       'Админ': admins_data})
    temp_path = files.get_random_path('xlsx')
    df.to_excel(temp_path)
    base = FSInputFile(temp_path, filename="пользователи.xlsx")
    await call.message.edit_text(call.message.text, reply_markup=call.message.reply_markup)
    try:
        await bot.send_document(chat_id=call.from_user.id,
                                document=base,
                                caption='✔️База успешно выгружена!',
                                reply_markup=telegram.kb_delete_message)
    except TelegramAPIError:
        ...
    os.remove(temp_path)
    await call.answer()


class ThreadCheckBan:
    def __init__(self):
        self.banned = 0
        self.unbanned = 0
        self.lock = threading.Lock()
        self.async_tasks = []
        self.is_end = []

    async def is_banned(self, user_id: int, end_index: int):
        try:
            await bot.send_chat_action(user_id, 'typing')
            with self.lock:
                self.unbanned += 1
                self.is_end[end_index] = True
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
            return await self.is_banned(user_id, end_index)
        except TelegramAPIError:
            with self.lock:
                self.banned += 1
                self.is_end[end_index] = True

    def coroutine_start(self, user_id: int, loop: asyncio.events.AbstractEventLoop, end_number: int):
        with self.lock:
            self.async_tasks.append(loop.create_task(self.is_banned(user_id, end_number)))

    async def start_check(self):
        users = DB.User.select(all_scalars=True)
        loop = asyncio.get_running_loop()
        threads = []
        task_number = 0
        for user in users:
            if task_number % 500 == 0:
                await asyncio.sleep(5)
            threads.append(threading.Thread(self.coroutine_start(user.user_id, loop, task_number)))
            self.is_end.append(False)
            task_number += 1
        [thread.start() for thread in threads]
        [thread.join() for thread in threads]
        await asyncio.wait(self.async_tasks)
        while True:
            await asyncio.sleep(2)
            if all(self.is_end):
                break
        return self.banned, self.unbanned


async def ban_count(call: CallbackQuery):
    await call.message.edit_text('⏳')
    await call.answer('⏳Начался подсчет блокировок, пожалуйста ожидайте...', show_alert=True)
    banned, unbanned = await ThreadCheckBan().start_check()
    answer_args = {
        'banned': banned,
        'unbanned': unbanned,
        'ban_ending': users_counter_ending[last_number(banned)],
        'unban_ending': users_counter_ending[last_number(unbanned)]
    }
    await call.message.edit_text(bot_texts.bot_info['block_info'].format(**answer_args),
                                 reply_markup=kb_admin_menu.back_to_bot_info)


async def admin_events(call: CallbackQuery):
    await call.message.edit_text('⏳')
    await call.answer()
    now = datetime.now().strftime('%d.%m.%Y')
    today_events = {'message': 0, 'callback': 0, 'inline': 0}
    all_events = {'message': 0, 'callback': 0, 'inline': 0}
    for event in DBStats.Events.select(all_scalars=True):
        if event.time.strftime('%d.%m.%Y') == now:
            today_events[event.type] += 1
        all_events[event.type] += 1
    stats_params = {
        'today_message': today_events['message'],
        'today_callback': today_events['callback'],
        'today_inline': today_events['inline'],
        'today_inline_ending': once_ending[last_number(today_events['inline'])],
        'all_message': all_events['message'],
        'all_callback': all_events['callback'],
        'all_inline': all_events['inline'],
        'all_inline_ending': once_ending[last_number(all_events['inline'])]
    }
    await call.message.edit_text(bot_texts.bot_info['events'].format(**stats_params),
                                 reply_markup=kb_admin_menu.back_to_bot_info)


def register_handlers_admin_bot_info(dp: Dispatcher):
    dp.callback_query.register(export_users, F.data == "admin_export_users", config.admin_filter)
    dp.callback_query.register(export_to_txt, F.data == "admin_users_to_txt", config.admin_filter)
    dp.callback_query.register(export_to_excel, F.data == "admin_users_to_excel", config.admin_filter)
    dp.callback_query.register(admin_bot_info, F.data == "admin_bot_info", config.admin_filter)
    dp.callback_query.register(ban_count, F.data == "admin_ban_count", config.admin_filter)
    dp.callback_query.register(admin_events, F.data == "admin_today_events", config.admin_filter)
