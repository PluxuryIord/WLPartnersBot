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
    from aiogram.types import CallbackQuery, InlineQuery, Message

from aiogram import F

from bot.utils import telegram as telegram
from bot.utils.announce_bot import bot
from bot.keyboards.admin import kb_admin_admins
from bot.integrations import DB
from bot.states.admin_admins import FsmAdminList, FsmAddAdmin
from bot.initialization import admin_access, config
from bot.initialization import bot_texts


async def admins_menu(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(bot_texts.admins['main_menu'],
                                 reply_markup=kb_admin_admins.admins_menu)
    await call.answer()
    await state.set_state(FsmAdminList.search)


async def admins_list(call: CallbackQuery):
    await call.message.edit_text(bot_texts.admins['admin_list'],
                                 reply_markup=kb_admin_admins.admins_list(DB.Admin.select(all_scalars=True)))
    await call.answer()


async def info_for_admin(call: CallbackQuery):
    admin_id = int(call.data.split('|')[1])
    admin = DB.Admin.select(where=(DB.Admin.admin_id == admin_id))
    user_data = DB.User.select(where=(DB.User.user_id == admin_id))
    if admin.appointment != 0:
        appointment_admin = DB.User.select(mark=admin.appointment)
        appointment = f'{admin.appointment} ({appointment_admin.full_name})'
    else:
        appointment = 'Система'
    accesses = '\n'.join(f'{admin_access.admin_accesses[access][0].split("|")[1]}: '
                         f'{"Да" if admin.access[access] else "Нет"}' for access in admin.access)
    await call.message.edit_text(
        bot_texts.admins['admin_info'].format(
            admin_id=admin_id,
            full_name=user_data.full_name,
            username='<code>Отсутствует</code>' if not user_data.username else '@' + user_data.username,
            date_reg=user_data.date_reg,
            appointment_date=admin.appointment_date,
            appointment=appointment,
            accesses=accesses),
        reply_markup=kb_admin_admins.back_to_admins_menu)
    await call.answer()


async def remove_admin(call: CallbackQuery):
    admin_id = int(call.data.split('|')[1])
    if admin_id == call.from_user.id:
        await call.answer('❌Вы не можете удалить самого себя', show_alert=True)
        return
    if config.admin_filter.remove_admin(call.from_user.id, admin_id):
        await call.answer(f'✅Администратор ID{admin_id} успешно удален!', show_alert=True)
        await admins_list(call)
    else:
        await call.answer('❌Нельзя удалить главного администратора!', show_alert=True)


async def add_administrator(call: CallbackQuery, state: FSMContext):
    if await state.get_state():
        await state.clear()
    await call.message.edit_text(bot_texts.admins['search'], reply_markup=kb_admin_admins.add_admin)
    await state.set_state(FsmAdminList.search)
    await call.answer()


async def search_user(query: InlineQuery):
    users = DB.User.select(all_scalars=True)
    if query.query:
        results = []
        for user in users:
            if query.query in f'{user.user_id} {user.full_name} | @{user.username}':
                if not config.admin_filter.is_admin(user.user_id):
                    results.append(user)
    else:
        results = [user for user in users if not config.admin_filter.is_admin(user.user_id)]
    results = [[user.full_name, f'{user.user_id} | {user.username if user.username else "Без ника"}',
                None, f'add_new_admin|{user.user_id}'] for user in results]
    await telegram.inline_helper(query, results)


async def add_new_admin(message: Message, state: FSMContext, user_data: DB.User):
    await message.delete()
    new_admin = int(message.text.split('|')[1])
    access = admin_access.null_admin_access.copy()
    await state.update_data(new_admin=new_admin, access=access)
    await state.set_state(FsmAddAdmin.access)
    await bot.edit_message_text(text=bot_texts.admins['access'], chat_id=message.from_user.id,
                                message_id=user_data.menu_id, reply_markup=kb_admin_admins.select_access(access))


async def switch_access(call: CallbackQuery, state: FSMContext):
    access_key = call.data.split('|')[1]
    storage = await state.get_data()
    access = storage.get('access')
    access[access_key] = not access[access_key]
    await telegram.edit_text(call.message, bot_texts.admins['access'],
                             reply_markup=kb_admin_admins.select_access(access))
    await state.update_data(access=access)
    await call.answer()


async def accept_access(call: CallbackQuery, state: FSMContext):
    storage = await state.get_data()
    new_admin = storage.get('new_admin')
    access = storage.get('access')
    if True not in [access[elem] for elem in access]:
        await call.answer('❌Необходимо выбрать хотя бы одну привилегию!', show_alert=True)
        return
    config.admin_filter.add_admin(new_admin, call.from_user.id, access)
    await state.clear()
    await call.answer(f'✅Администратор {new_admin} был успешно добавлен!', show_alert=True)
    await admins_list(call)
    await telegram.send_message(new_admin, bot_texts.admins['new_admin_alert'],
                                reply_markup=telegram.kb_delete_message)


def register_handlers_admin_admins(dp: Dispatcher):
    dp.callback_query.register(admins_menu, F.data == 'admin_admins', config.admin_filter)
    dp.callback_query.register(admins_list, F.data == 'admin_list_admins', config.admin_filter)
    dp.callback_query.register(remove_admin, F.data.startswith('remove_admin|'), config.admin_filter)
    dp.callback_query.register(info_for_admin, F.data.startswith('info_for_admin|'), config.admin_filter)
    dp.callback_query.register(add_administrator, F.data == 'admin_add_admin', config.admin_filter)
    dp.inline_query.register(search_user, FsmAdminList.search, config.admin_filter)
    dp.message.register(add_new_admin, F.text.startswith('add_new_admin|'), config.admin_filter)
    dp.callback_query.register(switch_access, FsmAddAdmin.access, F.data.startswith('admin_switch_access|'))
    dp.callback_query.register(accept_access, FsmAddAdmin.access, F.data == 'admin_accept_access')
