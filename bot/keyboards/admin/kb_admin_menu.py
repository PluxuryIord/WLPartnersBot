"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""
# Site Company: buy-bot.ru

from aiogram.types import ReplyKeyboardRemove

from bot.utils.telegram import create_inline


def main_menu(admin_access: dict, admin_accesses: dict):
    menu_markup = []
    for access in admin_accesses:
        access_status = admin_access[access]
        if access_status:
            access_data = admin_accesses[access]
            menu_markup.append(
                [access_data[0].replace('|', ' '), 'call', access_data[1]])
    menu_markup.append(['🔙 В основное меню', 'call', 'client_back_menu'])
    return create_inline(menu_markup, 1)


back_menu = create_inline([['🔙 Меню администратора', 'call', 'admin_menu']], 1)

bot_info = create_inline(
    [
        ['⛔️ Количество блокировок', 'call', 'admin_ban_count'],
        ['💬 Количество действий (сегодня)', 'call', 'admin_today_events'],
        ['🕹 Технические работы(вкл/выкл)', 'call', 'admin_tech_work'],
        ['📤 Выгрузить список пользователей', 'call', 'admin_export_users'],
        ['🔙 Меню администратора', 'call', 'admin_menu']
    ], 1)

back_to_bot_info = create_inline(
    [
        ['⬅ О боте', 'call', 'admin_bot_info']
    ], 1)

export_users = create_inline(
    [
        ['📝 Выгрузить в .txt файл(текстовый)', 'call', 'admin_users_to_txt'],
        ['📋 Выгрузить в .xlsx файл(excel)', 'call', 'admin_users_to_excel'],
        ['🔙 Настройки и информация о боте', 'call', 'admin_bot_info']
    ], 1)

remove_reply_kb = ReplyKeyboardRemove()
