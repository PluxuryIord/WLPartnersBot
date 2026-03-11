"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""
from aiogram.utils.keyboard import ReplyKeyboardBuilder

# Site Company: buy-bot.ru

from bot.utils.telegram import create_inline, kb_delete_message


def main_menu(admin: bool, show_qr: bool = False, info: bool = False):
    buttons = []
    if show_qr: buttons.append(['Показать мой QR код', 'call', 'client_show_my_qr']),  # после розыгрыша
    #if info: buttons.append(['Информация о вечеринке', 'call', 'client_info'])
    # buttons.append(['Как найти стенд Winline Partners?', 'call', 'client_FAQ']),
    # buttons.append(['Помощь', 'call', 'client_support']),
    if admin:
        buttons.append(['⚙️ Меню администратора', 'call', 'admin_menu'])
    return create_inline(buttons, 1)


registration_button = create_inline([['Зарегистрироваться', 'call', 'client_registration']], 1)

start_menu = create_inline([
    ['Я уже являюсь партнёром', 'call', 'client_existing_partner'],
    ['Регистрация партнёров', 'call', 'client_new_partner'],
], 1)

registration_partners_menu = create_inline([
    ['Пройти регистрацию', 'url', 'https://partners.winline.ru'],
    ['Я уже зарегистрирован', 'call', 'client_already_registered'],
    ['Помощь', 'call', 'client_reg_help'],
    ['🔙 Назад', 'call', 'client_back_to_start'],
], 1)

auth_menu = create_inline([
    ['Авторизоваться по почте', 'call', 'client_auth_email'],
    ['🔙 Назад', 'call', 'client_back_to_start'],
], 1)

authorized_menu = create_inline([
    ['База знаний', 'call', 'client_knowledge_base'],
    ['Офферы', 'call', 'client_offers'],
    ['Социальные сети', 'call', 'client_socials'],
    ['Актуальные промо и ссылки', 'call', 'client_promo'],
    ['Чат с менеджером', 'call', 'client_chat_manager'],
    ['Я на мероприятии!', 'call', 'client_at_event'],
    ['🔙 Назад', 'call', 'client_back_to_start'],
], 1)

delete_message = kb_delete_message

back_menu = create_inline([['🔙 Меню', 'call', 'client_back_menu']], 1)

user_role = create_inline(
    [
        ['СPA сеть', 'call', 'pick:role:СPA сеть'],
        ['Вебмастер', 'call', 'pick:role:Вебмастер'],
        ['Рекламодатель', 'call', 'pick:role:Рекламодатель'],
        ['Другое', 'call', 'pick:role:Другое'],
    ], 1
)

user_traff = create_inline(
    [
        ['аso/seo', 'call', 'pick:traff:аso/seo'],
        ['push/pop', 'call', 'pick:traff:push/pop'],
        ['ppc', 'call', 'pick:traff:ppc'],
        ['social', 'call', 'pick:traff:social'],
        ['in-app', 'call', 'pick:traff:in-app'],
        ['E-mail / SMS', 'call', 'pick:traff:E-mail / SMS'],
        ['other', 'call', 'pick:traff:other'],
    ], 3
)

winner = create_inline([
    ['Я буду на вечеринке', 'call', 'client_come:1'],
    ['Не смогу прийти', 'call', 'client_come:0'],
], 1)

show_my_qr = create_inline([
    ['Показать мой QR код', 'call', 'client_show_my_qr']
], 1)


async def kb_phone():
    kb = ReplyKeyboardBuilder()
    kb.button(text='Поделиться', request_contact=True)
    return kb.as_markup(resize_keyboard=True)

subscribe = create_inline([
    ['Подписка есть!', 'call', 'client_check_subscribe']
], 1)


pm = create_inline([
    ['Готово!', 'call', 'client_pm']
], 1)