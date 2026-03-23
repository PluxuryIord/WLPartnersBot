"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""
# Site Company: buy-bot.ru

from bot.initialization import admin_accesses
from bot.integrations import DB
from bot.utils.telegram import create_inline

admins_menu = create_inline(
    [
        ['📔 Список администраторов', 'call', f'admin_list_admins'],
        ['➕ Добавить нового администратора', 'call', 'admin_add_admin'],
        ['🔙 Назад', 'call', 'admin_menu'],
    ], 1)

back_to_admins_menu = create_inline(
    [
        ['🔙 Назад', 'call', f'admin_list_admins'],
    ], 1)

add_admin = create_inline(
    [
        ['🔎 Поиск пользователя', 'inline', ' '],
        ['🔙 Меню администраторов', 'call', 'admin_admins']
    ], 1)

cancel_add_admin = create_inline(
    [
        ['❌ Отмена', 'call', f'admin_add_admin'],
    ], 1)


async def select_add_admin(user_id: int, adder: int):
    buttons = [['✔️ Назначить администратором', 'call', f'add_new_admin|{user_id}|{adder}'],
               ['❌ Отмена', 'call', f'admin_add_admin']]
    markup = await create_inline(buttons, 1)
    return markup


def admins_list(admins: list[DB.Admin]):
    buttons = []
    for admin in admins:
        user_data = DB.User.select(mark=admin.admin_id)
        name = '@' + user_data.username if user_data.username else user_data.full_name
        buttons += [[name, 'call', f'info_for_admin|{admin.admin_id}'],
                    [f'❌ ', 'call', f'remove_admin|{admin.admin_id}']]
    buttons.append(['🔙 Администраторы', 'call', 'admin_admins'])
    markup = create_inline(buttons, 2)
    return markup


def select_access(accesses: list):
    access_markup = []
    for access in accesses:
        access_data = accesses[access]
        access_info = admin_accesses[access]
        selected = '✔️' if access_data else ''
        access_markup.append([f'{selected}{access_info[0].split("|")[1]}', 'call', f'admin_switch_access|{access}'])
    access_markup += [['✅ Подтвердить выбор', 'call', 'admin_accept_access'],
                      ['🔙 Меню администраторов', 'call', 'admin_admins']]
    return create_inline(access_markup, 1)
