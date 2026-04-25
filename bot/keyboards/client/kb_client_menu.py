"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from bot.utils.telegram import create_inline, kb_delete_message
from bot.utils.dynamic_kb import get_screen_kb


def _kb_or_fallback(screen_id, fallback_buttons, extra=None, cols=1):
    """Try dynamic KB from DB, fallback to hardcoded."""
    kb = get_screen_kb(screen_id, extra_buttons=extra, cols=cols)
    if kb:
        return kb
    buttons = fallback_buttons[:]
    if extra:
        buttons.extend(extra)
    return create_inline(buttons, cols)


def main_menu(admin: bool, show_qr: bool = False, info: bool = False):
    buttons = []
    if show_qr: buttons.append(['Показать мой QR код', 'call', 'client_show_my_qr'])
    if admin:
        buttons.append(['⚙️ Меню администратора', 'call', 'admin_menu'])
    return create_inline(buttons, 1)


registration_button = create_inline([['Зарегистрироваться', 'call', 'client_registration']], 1)


def get_start_menu(is_admin=False):
    extra = [['⚙️ Меню администратора', 'call', 'admin_menu']] if is_admin else None
    return _kb_or_fallback('start_menu', [
        ['Я уже являюсь партнёром', 'call', 'client_existing_partner'],
        ['Пройти регистрацию', 'call', 'client_new_partner'],
    ], extra=extra)

# Static fallbacks (used at import time, before DB is ready)
start_menu = create_inline([
    ['Я уже являюсь партнёром', 'call', 'client_existing_partner'],
    ['Пройти регистрацию', 'call', 'client_new_partner'],
], 1)
start_menu_admin = create_inline([
    ['Я уже являюсь партнёром', 'call', 'client_existing_partner'],
    ['Пройти регистрацию', 'call', 'client_new_partner'],
    ['⚙️ Меню администратора', 'call', 'admin_menu'],
], 1)


def get_registration_partners_menu():
    return _kb_or_fallback('registration_flow', [
        ['Пройти регистрацию', 'url', 'https://partners.winline.ru'],
        ['Я уже зарегистрирован', 'call', 'client_already_registered'],
        ['🔙 Назад', 'call', 'client_back_to_start'],
    ])

registration_partners_menu = create_inline([
    ['Пройти регистрацию', 'url', 'https://partners.winline.ru'],
    ['Я уже зарегистрирован', 'call', 'client_already_registered'],
    ['🔙 Назад', 'call', 'client_back_to_start'],
], 1)


def get_auth_menu():
    return _kb_or_fallback('auth_flow', [
        ['Авторизоваться', 'call', 'client_auth_email'],
        ['🔙 Назад', 'call', 'client_back_to_start'],
    ])

auth_menu = create_inline([
    ['Авторизоваться', 'call', 'client_auth_email'],
    ['🔙 Назад', 'call', 'client_back_to_start'],
], 1)


def get_authorized_menu(is_admin=False, event_active=False, user_id=None):
    from bot.utils.dynamic_kb import get_screen_kb_filtered
    from bot.integrations.ai.knowledge_assistant import is_user_allowed

    show_ai = user_id is not None and is_user_allowed(user_id)

    extra = [['📊 Моя статистика', 'call', 'client_my_stats']]
    if show_ai:
        extra.append(['❓ Спросить ИИ', 'call', 'client_ask_ai'])
    if is_admin:
        extra.append(['⚙️ Меню администратора', 'call', 'admin_menu'])

    # Try dynamic KB first
    skip_actions = [] if event_active else ['client_at_event']
    kb = get_screen_kb_filtered('main_menu', extra_buttons=extra, skip_actions=skip_actions)
    if kb:
        return kb

    # Fallback
    fallback = [
        ['📊 Моя статистика', 'call', 'client_my_stats'],
        ['База знаний', 'call', 'client_knowledge_base'],
    ]
    if show_ai:
        fallback.append(['❓ Спросить ИИ', 'call', 'client_ask_ai'])
    fallback.extend([
        ['Информация по офферу', 'call', 'client_offers'],
        ['Актуальные крео и лендинги', 'call', 'client_promo'],
        ['Чат с менеджером', 'url', 'https://t.me/winline_affiliate'],
        ['Наши соц. сети', 'call', 'client_socials'],
    ])
    if event_active:
        fallback.append(['Я на мероприятии!', 'call', 'client_at_event'])
    fallback.append(['🚪 Выйти из аккаунта', 'call', 'client_logout'])
    if is_admin:
        fallback.append(['⚙️ Меню администратора', 'call', 'admin_menu'])
    return create_inline(fallback, 1)

authorized_menu = create_inline([
    ['База знаний', 'call', 'client_knowledge_base'],
    ['❓ Спросить ИИ', 'call', 'client_ask_ai'],
    ['Информация по офферу', 'call', 'client_offers'],
    ['Актуальные крео и лендинги', 'call', 'client_promo'],
    ['Чат с менеджером', 'url', 'https://t.me/winline_affiliate'],
    ['Наши соц. сети', 'call', 'client_socials'],
    ['Я на мероприятии!', 'call', 'client_at_event'],
    ['🚪 Выйти из аккаунта', 'call', 'client_logout'],
], 1)
authorized_menu_admin = create_inline([
    ['База знаний', 'call', 'client_knowledge_base'],
    ['❓ Спросить ИИ', 'call', 'client_ask_ai'],
    ['Информация по офферу', 'call', 'client_offers'],
    ['Актуальные крео и лендинги', 'call', 'client_promo'],
    ['Чат с менеджером', 'url', 'https://t.me/winline_affiliate'],
    ['Наши соц. сети', 'call', 'client_socials'],
    ['Я на мероприятии!', 'call', 'client_at_event'],
    ['⚙️ Меню администратора', 'call', 'admin_menu'],
    ['🚪 Выйти из аккаунта', 'call', 'client_logout'],
], 1)

ask_ai_actions = create_inline([
    ['❓ Ещё вопрос', 'call', 'client_ask_ai'],
    ['🔙 В меню', 'call', 'client_back_menu'],
], 1)


event_menu = create_inline([
    ['Работаю с WINLINE PARTNERS', 'call', 'event_v2_partner_yes'],
    ['Не работаю с WINLINE PARTNERS', 'call', 'event_v2_partner_no'],
], 1)
event_menu_admin = create_inline([
    ['Работаю с WINLINE PARTNERS', 'call', 'event_v2_partner_yes'],
    ['Не работаю с WINLINE PARTNERS', 'call', 'event_v2_partner_no'],
    ['⚙️ Меню администратора', 'call', 'admin_menu'],
], 1)
event_qr_new_menu = create_inline([['Стать партнёром', 'call', 'client_new_partner']], 1)

delete_message = kb_delete_message
back_menu = create_inline([['🔙 Меню', 'call', 'client_back_menu']], 1)

stats_periods = create_inline([
    ['📅 За вчера', 'call', 'client_stats_period:yesterday'],
    ['📅 За прошлую неделю', 'call', 'client_stats_period:week'],
    ['📅 За прошлый месяц', 'call', 'client_stats_period:month'],
    ['🔙 Меню', 'call', 'client_back_menu'],
], 1)

stats_back_to_periods = create_inline([
    ['🔄 Другой период', 'call', 'client_my_stats'],
    ['🔙 Меню', 'call', 'client_back_menu'],
], 1)

user_role = create_inline([
    ['СPA сеть', 'call', 'pick:role:СPA сеть'],
    ['Вебмастер', 'call', 'pick:role:Вебмастер'],
    ['Рекламодатель', 'call', 'pick:role:Рекламодатель'],
    ['Другое', 'call', 'pick:role:Другое'],
], 1)

user_traff = create_inline([
    ['аso/seo', 'call', 'pick:traff:аso/seo'],
    ['push/pop', 'call', 'pick:traff:push/pop'],
    ['ppc', 'call', 'pick:traff:ppc'],
    ['social', 'call', 'pick:traff:social'],
    ['in-app', 'call', 'pick:traff:in-app'],
    ['E-mail / SMS', 'call', 'pick:traff:E-mail / SMS'],
    ['other', 'call', 'pick:traff:other'],
], 3)

winner = create_inline([
    ['Я буду на вечеринке', 'call', 'client_come:1'],
    ['Не смогу прийти', 'call', 'client_come:0'],
], 1)

show_my_qr = create_inline([['Показать мой QR код', 'call', 'client_show_my_qr']], 1)

subscribe = create_inline([['Подписка есть!', 'call', 'client_check_subscribe']], 1)
pm = create_inline([['Готово!', 'call', 'client_pm']], 1)


async def kb_phone():
    kb = ReplyKeyboardBuilder()
    kb.button(text='Поделиться', request_contact=True)
    return kb.as_markup(resize_keyboard=True)
