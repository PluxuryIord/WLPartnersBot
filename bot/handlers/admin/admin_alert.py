"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from __future__ import annotations

import threading
import time
from asyncio import AbstractEventLoop

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram import Dispatcher
    from aiogram.fsm.context import FSMContext
    from aiogram.types import InlineQuery

    from typing import Union

import asyncio
import os
import subprocess

from threading import Thread

from aiogram import F
from aiogram.filters import StateFilter
from aiogram.types import Message
from aiogram.exceptions import TelegramAPIError

from bot.initialization import bot_texts
from bot.initialization import config
from bot.integrations import DB
from bot.keyboards.admin import kb_admin_alert
from bot.states.alert import FsmNewAlert, FsmSearchHistory
from bot.utils import telegram as telegram
from bot.utils import dt as datetime
from bot.utils import files
from bot.utils.text_ending import users_counter_ending, files_counter_ending, once_ending, last_number

# Alert buttons:
from aiogram.types import CallbackQuery
from bot.handlers.client.client_main import main_menu

null_files_counter = {'all': 0,
                      'photo': 0,
                      'video': 0,
                      'document': 0,
                      'animation': 0,
                      'sticker': False,
                      'video_note': False,
                      'voice': False}
support_buttons = {
    'read': ['✅Прочитано', 'call', 'client_delete_message'],
    'buy-bot': ['Сайт разработчика', 'url', 'https://buy-bot.ru/'],
}
support_buttons_keys = [button for button in support_buttons]
search_picture_url = 'https://encrypted-tbn0.gstatic.com/images?' \
                     'q=tbn:ANd9GcQSFtAI877PUIR3krULmlOH-gM9MLyKiofp1JIFNmXF3yI3y0RwPZHmV_oQaLaZYTCq830&usqp=CAU'
alert_status_codes = {
    0: '🗑Ещё не создана',
    1: '⏳В процессе...',
    201: '✅Завершена'
}
# Local directory
if os.name == 'nt':
    run_path = f'{os.getcwd()}\\venv\\Scripts\\python.exe -m background_alert'
else:
    run_path = f'{os.getcwd()}/venv/bin/python3 -m background_alert'


class ThreadAlert:
    def __init__(self, alert_id: int, users: list):
        self.alert_id = alert_id
        self.users = users
        self._alert_data = DB.Alert.select(mark=self.alert_id)
        self._alert_body = self._alert_data.data
        self._lock = threading.Lock()
        self._async_tasks = []
        self._dispatch_log = self._alert_data.dispatch_log
        self._successfully_sent = 0
        self._error_sent = 0
        self._last_db_update = [self._dispatch_log, 0, 0]
        self._task_active = True
        self._recipients = {}

    async def start_sending(self):
        DB.Alert.update(mark=self.alert_id, status_code=1, date_sent=datetime.now('datetime'))
        self._dispatch_log += f'[{datetime.now(2)}] ⏳Рассылаю сообщения...\n\n'
        threads = []
        loop = asyncio.get_running_loop()
        task_number = 0
        for user in self.users:
            if task_number % 500 == 0:
                await asyncio.sleep(5)
            threads.append(threading.Thread(self._coroutine_send_message(user, loop)))
            task_number += 1
        [thread.start() for thread in threads]
        [thread.join() for thread in threads]
        await asyncio.wait(self._async_tasks)
        self._task_active = False
        self._dispatch_log += f'\n[{datetime.now(2)}] ✅Рассылка завершена'
        DB.Alert.update(mark=self.alert_id, status_code=201, dispatch_log=self._dispatch_log,
                        successfully_sent=self._successfully_sent, error_sent=self._error_sent,
                        recipients=self._recipients)

    async def _send_message(self, user_id: int):
        result = await telegram.message_constructor(user_id, self._alert_body)
        if result:
            self._dispatch_log += f'[{datetime.now(2)}] Успешно отправлено: {user_id}\n'
            self._successfully_sent += 1
            ids = [message.message_id for message in result]
            self._recipients[user_id] = ids
        else:
            self._dispatch_log += f'[{datetime.now(2)}] Не удалось доставить сообщение: {user_id}\n'
            self._error_sent += 1
            self._recipients[user_id] = None

    def _coroutine_send_message(self, user_id: int, loop: AbstractEventLoop):
        self._async_tasks.append(loop.create_task(self._send_message(user_id)))

    def _update_log(self):
        while self._task_active:
            time.sleep(5)
            if self._last_db_update != [self._dispatch_log, self._successfully_sent, self._error_sent]:
                DB.Alert.update(mark=self.alert_id, dispatch_log=self._dispatch_log,
                                successfully_sent=self._successfully_sent, error_send=self._error_sent)
                self._last_db_update = [self._dispatch_log, self._successfully_sent, self._error_sent]


async def remove_preload(state: FSMContext):
    storage = await state.get_data()
    if storage and 'preload' in storage and storage['preload']:
        for message in storage['preload']:
            try:
                await message.delete()
            except TelegramAPIError:
                ...
        del storage['preload']
        await state.set_data(storage)


async def alert_menu(call: CallbackQuery, state: FSMContext):
    if await state.get_state():
        await remove_preload(state)
        await state.clear()
    await telegram.edit_text(call.message, bot_texts.alert['main_menu'], reply_markup=kb_admin_alert.menu)
    await call.answer()


async def new_alert(call: CallbackQuery, state: FSMContext):
    DB.Alert.remove(where=[DB.Alert.status_code == 0, DB.Alert.admin_id == call.from_user.id])
    await telegram.edit_text(call.message, bot_texts.alert['new'], reply_markup=kb_admin_alert.cancel_new_alert)
    alert_id = DB.Alert.add(call.from_user.id)
    await state.set_state(FsmNewAlert.message)
    await state.update_data(alert_id=alert_id, menu=call.message, activate_buttons=[])
    await call.answer()


def bool_to_str(param: bool):
    return 'Да' if param else 'Нет'


def generate_files_text(db_data: dict):
    return bot_texts.alert['load_files'].format(
        all_counter=db_data['files_counter']['all'],
        ending=files_counter_ending[last_number(db_data['files_counter']['all'])],
        photo_counter=db_data['files_counter']['photo'],
        video_counter=db_data['files_counter']['video'],
        animation_counter=db_data['files_counter']['animation'],
        document_counter=db_data['files_counter']['document'],
        have_sticker=bool_to_str(db_data['files_counter']['sticker']),
        have_video_note=bool_to_str(db_data['files_counter']['video_note']),
        have_voice=bool_to_str(db_data['files_counter']['voice']))


async def input_message(message: Message, state: FSMContext, menu: Message, album: list[Message] = False):
    storage = await state.get_data()
    await telegram.edit_text(menu, 'Вложения загружаются...\n█▒▒▒▒▒▒▒▒▒')
    alert_id = storage['alert_id']
    db_data: dict = DB.Alert.select(alert_id).data
    input_files = []
    if album:
        for msg in album:
            input_files.append(msg)
            await msg.delete()
    else:
        await message.delete()
        if message.text:
            db_data['alert_type'], db_data['text'] = 'text', message.html_text
            db_data['files'], db_data['files_counter'] = [], null_files_counter
            DB.Alert.update(mark=alert_id, data=db_data)
            await telegram.edit_text(menu, bot_texts.alert['text'], reply_markup=kb_admin_alert.preload_text)
            return
        input_files.append(message)
    if db_data['alert_type'] and db_data['alert_type'] == 'text':
        db_data['text'] = None
    await telegram.edit_text(menu, 'Вложения загружаются...\n███▒▒▒▒▒▒▒')
    db_data['alert_type'] = 'files'
    for file in input_files:
        if db_data['files_counter']['all'] == 10:
            await message.answer('<b>❌Невозможно загрузить более 10-ти вложений</b>',
                                 reply_markup=telegram.kb_delete_message)
            break
        if file.photo or file.document or file.video or file.animation or file.sticker or file.video_note or file.voice:
            db_data['files_counter']['all'] += 1
            if file.photo:
                db_data['files'].append(['photo', file.photo[-1].file_id])
                db_data['files_counter']['photo'] += 1
            elif file.document:
                db_data['files'].append(['document', file.document.file_id])
                db_data['files_counter']['document'] += 1
            elif file.video:
                db_data['files'].append(['video', file.video.file_id])
                db_data['files_counter']['video'] += 1
            elif file.animation:
                db_data['files'].append(['animation', file.animation.file_id])
                db_data['files_counter']['animation'] += 1
            elif file.sticker:
                db_data['files'].append(['sticker', file.sticker.file_id])
                db_data['files_counter']['sticker'] = True
                db_data['alert_type'] = 'sticker'
            elif file.video_note:
                db_data['files'].append(['video_note', file.video_note.file_id])
                db_data['files_counter']['video_note'] = True
                db_data['alert_type'] = 'video_note'
            elif file.voice:
                db_data['files'].append(['voice', file.voice.file_id])
                db_data['files_counter']['voice'] = True
                db_data['alert_type'] = 'voice'
        else:
            await message.answer(
                '<b>❌Пропущен неожидаемый тип вложения, '
                'поддерживаемые типы: фото, видео, файл, гиф, стикер, голосовое сообщение, видео-кружочки!</b>',
                reply_markup=telegram.kb_delete_message)
            return
        if message.caption:
            if len(message.html_text) < 1025:
                db_data['text'] = message.html_text
            else:
                db_data['text'] = message.html_text[0:1020]
                await message.answer(
                    f'<b>❌ Обрезана подпись под вложением по причине превышения лимита символов</b>\n\n'
                    f'<i>Отправлено: <code>{len(message.html_text)}</code>/<code>1024</code> символов</i>',
                    reply_markup=telegram.kb_delete_message)
    '''
    if (db_data['files_counter']['all'] > 1 or db_data['files_counter']['sticker'] or
            db_data['files_counter']['video_note'] or db_data['files_counter']['voice']):
    '''
    if db_data['files_counter']['all'] > 1:
        db_data['buttons'] = []
    DB.Alert.update(mark=alert_id, data=db_data)
    await telegram.edit_text(menu, 'Вложения загружаются...\n███████▒▒▒')
    file_types = {'photo': 1, 'video': 1, 'document': 2, 'animation': 3, 'sticker': 4, 'video_note': 5, 'voice': 6}
    last_file = file_types[db_data['files'][0][0]]
    for file in db_data['files']:
        if file_types[file[0]] != last_file:
            await telegram.edit_text(menu, bot_texts.alert['type_error'], reply_markup=kb_admin_alert.back_to_files)
            db_data['files'], db_data['text'], db_data['files_counter'] = [], None, null_files_counter
            DB.Alert.update(mark=alert_id, data=db_data)
            return
        last_file = file_types[file[0]]
    await telegram.edit_text(menu, generate_files_text(db_data), reply_markup=kb_admin_alert.preload_files)


async def preload(call: CallbackQuery, state: FSMContext, alert_id: int):
    alert_data = DB.Alert.select(alert_id).data
    await asyncio.sleep(1)
    messages = await telegram.message_constructor(call.from_user.id, alert_data)
    await state.update_data(preload=messages)
    await call.answer()


async def alert_constructor_preload(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(bot_texts.alert['preload'],
                                 reply_markup=kb_admin_alert.cancel_constructor_preload)
    storage = await state.get_data()
    await state.set_state(FsmNewAlert.preload)
    await preload(call, state, storage['alert_id'])


async def alert_history_preload(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(bot_texts.alert['history_preload'],
                                 reply_markup=kb_admin_alert.cancel_history_preload(int(call.data.split('|')[1])))
    await preload(call, state, int(call.data.split('|')[1]))


async def alert_constructor(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text('⏳')
    storage = await state.get_data()
    await remove_preload(state)
    db_data = DB.Alert.select(storage['alert_id']).data
    if db_data['alert_type'] == 'files':
        if db_data['files_counter']['all'] == 0:
            await call.message.edit_text(generate_files_text(db_data), reply_markup=kb_admin_alert.clear_preload_files)
        else:
            await call.message.edit_text(generate_files_text(db_data), reply_markup=kb_admin_alert.preload_files)
    else:
        await call.message.edit_text(bot_texts.alert['text'], reply_markup=kb_admin_alert.preload_text)
    await state.set_state(FsmNewAlert.message)
    await call.answer()


async def clear_files(call: CallbackQuery, state: FSMContext):
    storage = await state.get_data()
    db_data = DB.Alert.select(storage['alert_id']).data
    if len(db_data['files']) > 0:
        db_data['files'], db_data['text'], db_data['files_counter'] = [], None, null_files_counter
        DB.Alert.update(mark=storage['alert_id'], data=db_data)
        await alert_constructor(call, state)
    else:
        await call.answer("❌Вложения отсутствуют", show_alert=True)


async def select_buttons(call: CallbackQuery, state: FSMContext):
    storage = await state.get_data()
    db_data = DB.Alert.select(storage['alert_id']).data
    url_buttons = []
    await state.set_state(FsmNewAlert.buttons)
    if db_data['alert_type'] == 'text' or len(db_data['files']) == 1:
        if not db_data['buttons']:
            str_buttons = 'Нет прикрепленных кнопок'
        else:
            str_buttons, counter = '', 0
            for button in db_data['buttons']:
                if button[1] == 'url':
                    url_buttons.append([counter, button])
                counter += 1
                str_buttons += f'{counter}: {button[0]}\n'
        if url_buttons:
            kb = kb_admin_alert.generate_buttons(url_buttons)
        else:
            kb = kb_admin_alert.select_buttons
        await call.message.edit_text(bot_texts.alert['select_buttons'].format(buttons=str_buttons),
                                     reply_markup=kb)
        await call.answer()
    else:
        await call.answer('❗️Вы загрузили более одного вложения, поэтому добавление кнопок недоступно', show_alert=True)
        await alert_filter(call, state)


async def bot_buttons(call: CallbackQuery):
    if len(support_buttons_keys) == 2:
        await call.answer('❗️Кнопки бота не поддерживаются\n\nОбратитесь к разработку для добавления', show_alert=True)
    else:
        buttons = []
        for button in support_buttons:
            if button in ['read']:
                continue
            buttons.append([support_buttons[button][0], 'call', f'alert_button|{button}'])
        buttons.append(['🔙Назад', 'call', 'alert_buttons'])
        await call.message.edit_text(bot_texts.alert['select_bot_buttons'],
                                     reply_markup=telegram.create_inline(buttons, 1))
    await call.answer()


async def bot_button(call: CallbackQuery, state: FSMContext):
    storage = await state.get_data()
    button_key = call.data.split('|')[1]
    db_data = DB.Alert.select(storage['alert_id']).data
    activate_buttons = storage['activate_buttons']
    if button_key in activate_buttons:
        activate_buttons.remove(button_key)
        db_data['buttons'].remove(support_buttons[button_key])
        await call.answer(f'📌Вы открепили кнопку "{support_buttons[button_key][0]}"', show_alert=True)
    else:
        activate_buttons.append(button_key)
        db_data['buttons'].append(support_buttons[button_key])
        await call.answer(f'📌Вы прикрепили кнопку "{support_buttons[button_key][0]}"', show_alert=True)
    DB.Alert.update(mark=storage['alert_id'], data=db_data)
    await state.update_data(activate_buttons=activate_buttons)
    await select_buttons(call, state)


async def add_url_button(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(bot_texts.alert['add_button_name'], reply_markup=kb_admin_alert.back_to_buttons)
    await call.answer()
    await state.set_state(FsmNewAlert.button_name)


async def input_button_name(message: Message, state: FSMContext, menu: Message):
    await telegram.delete_message(message)
    await telegram.edit_text(menu, '⏳')
    if not message.text:
        await telegram.edit_text(menu, '<b>❌Ошибка! Я ожидаю текст кнопки!</b>',
                                 reply_markup=kb_admin_alert.back_to_buttons)
    await state.update_data(button_name=message.text[:31])
    await telegram.edit_text(menu, bot_texts.alert['add_url_button'],
                             reply_markup=kb_admin_alert.back_to_buttons)
    await state.set_state(FsmNewAlert.button_url)


async def input_button_url(message: Message, state: FSMContext, menu: Message):
    await telegram.delete_message(message)
    await telegram.edit_text(menu, '⏳')
    if not message.text:
        await telegram.edit_text(menu, '<b>❌Ошибка! Я ожидаю текст (ссылку для кнопки)!</b>',
                                 reply_markup=kb_admin_alert.back_to_buttons)
    url = message.text
    if 'https' not in url:
        await telegram.edit_text(
            menu,
            '<b>❌Ошибка, некорректная ссылка, пример ссылки:</b>\n'
            'https://t.me/durov',
            reply_markup=kb_admin_alert.back_to_buttons)
    else:
        await state.update_data(new_button_url=url)
        storage = await state.get_data()
        kb = [
            [storage['button_name'], 'url', url],
            ['✔️ Продолжить', 'call', 'alert_accept_url'],
            ['🔙 К кнопкам', 'call', 'alert_buttons']
        ]
        await menu.edit_text('<b>Проверьте правильность кнопки, затем нажмите "Продолжить"</b>',
                             reply_markup=telegram.create_inline(kb, 1))


async def accept_button_url(call: CallbackQuery, state: FSMContext):
    await call.answer('✔️Кнопка успешно добавлена, '
                      'для удаления нажмите крестик рядом с ней.', show_alert=True)
    storage = await state.get_data()
    db_data = DB.Alert.select(storage['alert_id']).data
    db_data['buttons'].append([storage['button_name'], 'url', storage['new_button_url']])
    DB.Alert.update(mark=storage['alert_id'], data=db_data)
    await select_buttons(call, state)


async def remove_url_button(call: CallbackQuery, state: FSMContext):
    index = int(call.data.split("|")[1])
    storage = await state.get_data()
    db_data = DB.Alert.select(storage['alert_id']).data
    db_data['buttons'].pop(index)
    DB.Alert.update(mark=storage['alert_id'], data=db_data)
    await call.answer('✔️ Кнопка удалена', show_alert=True)
    await select_buttons(call, state)


async def alert_filter(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(bot_texts.alert['users_filter'], reply_markup=kb_admin_alert.select_users)
    await state.set_state(FsmNewAlert.filter)
    await call.answer()


async def register_filters(call: CallbackQuery):
    await call.message.edit_text(bot_texts.alert['register_filter'], reply_markup=kb_admin_alert.register_filter)
    await call.answer()


async def input_users_guid(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(bot_texts.alert['input_users'], reply_markup=kb_admin_alert.back_to_filters)
    await state.set_state(FsmNewAlert.input_users)
    await call.answer()


async def input_users(message: Message, state: FSMContext):
    result = await telegram.get_input_file(message, state)

    if not result:
        return

    lines, menu = result
    try:
        await state.update_data(input_users=[int(line) for line in lines])
        await telegram.edit_text(menu, '<b>ID пользователей успешно подгружены из файла, продолжить?</b>',
                                 reply_markup=kb_admin_alert.input_users)
    except ValueError:
        await telegram.edit_text(menu, '<b>❌Ошибка! В файле должны быть только числа (ID пользователей)</b>',
                                 reply_markup=kb_admin_alert.back_to_filters)


async def get_users(call: CallbackQuery, state: FSMContext):
    storage = await state.get_data()
    filter_type = call.data.split('|')[1]
    match filter_type:
        case 'input_users':
            users = storage['input_users']
        case 'all':
            users = [user.user_id for user in DB.User.select(all_scalars=True)]
        case 'admins':
            users = [admin.admin_id for admin in DB.Admin.select(all_scalars=True)]
        case 'me':
            users = [call.from_user.id]
        case 'groups':
            groups = DB.GroupChat.select(where=(DB.GroupChat.is_active == True), all_scalars=True)
            users = [g.chat_id for g in groups] if groups else []
        case 'reg_today' | 'reg_7days' | 'reg_30days':
            users = []
            for user in DB.User.select(all_scalars=True):
                difference_days = (datetime.now('datetime') - user.date_reg).days
                if filter_type == 'reg_today' and difference_days < 1:
                    users.append(user.user_id)
                elif filter_type == 'reg_7days' and difference_days < 7:
                    users.append(user.user_id)
                elif filter_type == 'reg_30days' and difference_days < 30:
                    users.append(user.user_id)
        case _:
            users = []
    if len(users) > 0:
        await call.message.edit_text(
            bot_texts.alert['send_alert'].format(count_users=len(users),
                                                 ending=users_counter_ending[last_number(len(users))]),
            reply_markup=kb_admin_alert.send_alert)
        await state.update_data(users=users)
        await call.answer()
    else:
        await call.answer('❌По данном фильтру пользователей не найдено', show_alert=True)


def background_thread(alert_id: int):
    shell_command = f'{run_path} {alert_id}'
    subprocess.run(shell_command, shell=True, check=False)


async def send_alert(call: CallbackQuery, state: FSMContext):
    storage = await state.get_data()
    await call.message.edit_text(bot_texts.alert['alert_started'], reply_markup=kb_admin_alert.alert_started)
    await call.answer()
    await state.clear()
    users_dict = {}
    for user in storage['users']:
        users_dict[user] = 0
    alert_id = storage['alert_id']
    DB.Alert.update(mark=alert_id, recipients=users_dict)
    thread = Thread(target=background_thread, args=[alert_id])
    thread.start()


async def alert_menu_button(call: CallbackQuery, user_data: DB.User | None, state: FSMContext = None):
    button_key = call.data.split('|')[1]
    new_menu = await main_menu(call, call.from_user, user_data, state, True)
    await call.answer()
    call = CallbackQuery(id=call.id, from_user=call.from_user, chat_instance=call.chat_instance, message=new_menu,
                         inline_message_id=call.inline_message_id, data=call.data, game_short_name=call.game_short_name)


async def alert_history_type(call: CallbackQuery):
    await call.message.edit_text(bot_texts.alert['alert_history_type'], reply_markup=kb_admin_alert.history_type)
    await call.answer()


async def alert_history(call: CallbackQuery, state: FSMContext):
    history_type = call.data.split('|')[1]
    await state.set_state(FsmSearchHistory.search)
    await state.update_data(history_type=history_type, menu=call.message)
    await call.message.edit_text(bot_texts.alert['alert_history'],
                                 reply_markup=kb_admin_alert.history)
    await call.answer()


async def search_alerts(query: InlineQuery, state: FSMContext):
    storage = await state.get_data()
    if storage['history_type'] == 'my':
        alerts = DB.Alert.select(where=DB.Alert.admin_id == query.from_user.id, all_scalars=True)
    else:
        alerts = DB.Alert.select(all_scalars=True)
    results = []
    for alert in alerts:
        if alert.status_code != 0:
            if query.query:
                if alert.data['text'] and query.query.lower() in alert.data['text']:
                    results.append(alert)
            else:
                results.append(alert)
    results = [
        [datetime.to_str(alert.date_sent),
         f'Администратор: {alert.admin_id if alert.admin_id != query.from_user.id else "вы"}\n'
         f'Текст: {alert.data["text"][0:10] if alert.data["text"] else "без текста"}',
         search_picture_url, f'admin_alert_info|{alert.id}'] for alert in results]
    results.reverse()
    await telegram.inline_helper(query, results)


async def view_alert_data(update: Union[Message, CallbackQuery], state: FSMContext, menu: Message):
    await remove_preload(state)
    if isinstance(update, Message):
        await update.delete()
        alert_id = int(update.text.split('|')[1])
    else:
        alert_id = int(update.data.split('|')[1])
        await update.answer()
    await state.update_data(alert_id=alert_id)
    alert_data = DB.Alert.select(mark=alert_id)
    admin_data = DB.User.select(mark=alert_data.admin_id)
    kb = kb_admin_alert.history_task(alert_id, True if alert_data.status_code == 201 else False)
    alert_data = {
        'date': datetime.to_str(alert_data.date_sent),
        'admin_id': alert_data.admin_id,
        'admin_full_name': admin_data.full_name,
        'admin_username': admin_data.username if admin_data.username else 'отсутствует',
        'alert_type': 'с вложениями' if alert_data.data['alert_type'] == 'files' else 'текстовая',
        'count_buttons': len(alert_data.data['buttons']),
        'successfully_sent': alert_data.successfully_sent,
        'successfully_ending': once_ending[last_number(alert_data.successfully_sent)],
        'error_sent': alert_data.error_sent,
        'error_ending': once_ending[last_number(alert_data.error_sent)],
        'status_code': alert_status_codes[alert_data.status_code]
    }
    await telegram.edit_text(menu, bot_texts.alert['alert_data'].format(**alert_data), reply_markup=kb)


async def alert_log(call: CallbackQuery):
    alert_data = DB.Alert.select(mark=int(call.data.split('|')[1]))
    file, path = files.create_txt(alert_data.dispatch_log, True, datetime.to_str(alert_data.date_sent, 'path'))
    await telegram.bot.send_document(chat_id=call.from_user.id, document=file, reply_markup=telegram.kb_delete_message)
    await call.answer()
    files.remove_file(path)


def register_handlers_admin_alert(dp: Dispatcher):
    dp.callback_query.register(alert_menu, F.data == "admin_alert", config.admin_filter)
    # Alert constructor
    dp.callback_query.register(new_alert, F.data == 'admin_new_alert', config.admin_filter)
    dp.message.register(input_message, FsmNewAlert.message, config.admin_filter)
    dp.callback_query.register(alert_constructor_preload, F.data == 'alert_preload',
                               FsmNewAlert.message, config.admin_filter)
    dp.callback_query.register(alert_history_preload, F.data.startswith('alert_history_preload|'), config.admin_filter,
                               FsmSearchHistory.search, config.admin_filter)
    dp.callback_query.register(alert_constructor, F.data == 'alert_constructor_preload_cancel',
                               FsmNewAlert.preload, config.admin_filter)
    dp.callback_query.register(alert_constructor, F.data == 'alert_back_to_constructor', config.admin_filter,
                               StateFilter(FsmNewAlert.message, FsmNewAlert.buttons, FsmNewAlert.filter))
    dp.callback_query.register(clear_files, F.data == 'alert_clear_files', FsmNewAlert.message, config.admin_filter)
    dp.callback_query.register(select_buttons, F.data == 'alert_buttons',
                               StateFilter(
                                   FsmNewAlert.message, FsmNewAlert.buttons,
                                   FsmNewAlert.button_url, FsmNewAlert.button_name
                               ), config.admin_filter)
    dp.callback_query.register(bot_buttons, F.data == 'alert_bot_buttons', FsmNewAlert.buttons, config.admin_filter)
    dp.callback_query.register(bot_button, F.data.startswith('alert_button|'), FsmNewAlert.buttons, config.admin_filter)

    dp.callback_query.register(add_url_button, F.data == 'alert_new_url_button', FsmNewAlert.buttons)
    dp.message.register(input_button_name, FsmNewAlert.button_name)
    dp.message.register(input_button_url, FsmNewAlert.button_url)
    dp.callback_query.register(accept_button_url, F.data == 'alert_accept_url', FsmNewAlert.button_url)
    dp.callback_query.register(remove_url_button, F.data.startswith('alert_remove_url|'), FsmNewAlert.buttons)

    dp.callback_query.register(alert_filter, F.data == 'alert_go_filters', config.admin_filter,
                               StateFilter(FsmNewAlert.buttons, FsmNewAlert.filter, FsmNewAlert.input_users))
    dp.callback_query.register(register_filters, F.data == 'alert_registration_filter',
                               FsmNewAlert.filter, config.admin_filter)
    dp.callback_query.register(input_users_guid, F.data == 'alert_input_users',
                               FsmNewAlert.filter, config.admin_filter)
    dp.message.register(input_users, FsmNewAlert.input_users, config.admin_filter)
    dp.callback_query.register(get_users, F.data.startswith('alert_filter|'), config.admin_filter,
                               StateFilter(FsmNewAlert.filter, FsmNewAlert.input_users))
    dp.callback_query.register(send_alert, F.data == 'alert_send',
                               StateFilter(FsmNewAlert.filter, FsmNewAlert.input_users), config.admin_filter)
    # Alert button
    dp.callback_query.register(alert_menu_button, F.data.startswith('alert_button|'))
    # Alert history
    dp.callback_query.register(alert_history_type, F.data == 'admin_alerts', config.admin_filter)
    dp.callback_query.register(alert_history, F.data.startswith('admin_alerts_search|'), config.admin_filter)
    dp.inline_query.register(search_alerts, FsmSearchHistory.search, config.admin_filter)
    dp.message.register(view_alert_data, F.text.startswith('admin_alert_info|'),
                        FsmSearchHistory.search, config.admin_filter)
    dp.callback_query.register(view_alert_data, F.data.startswith('admin_alert_info|'),
                               FsmSearchHistory.search, config.admin_filter)
    dp.callback_query.register(alert_log, F.data.startswith('alert_sent_log|'),
                               FsmSearchHistory.search, config.admin_filter)
