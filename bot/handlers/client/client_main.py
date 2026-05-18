"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

import os
import hashlib
import hmac
import qrcode
import aiohttp
import time
import json as json_mod
import asyncio
import logging

logger = logging.getLogger('wl_bot')
import mysql.connector
from io import BytesIO
from aiogram.types import BufferedInputFile

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Union, Optional

from aiogram.utils.markdown import hlink
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, User

import bot.keyboards.admin.kb_admin_topic
from bot.integrations.google.spreadsheets.google_sheets import new_user, new_prize, new_answers
from bot.integrations.ai.knowledge_assistant import (
    ask as ai_ask,
    get_remaining_questions as ai_remaining,
    is_user_allowed as ai_is_allowed,
    MAX_DAILY_QUESTIONS as AI_MAX_DAILY,
)
from bot.integrations.winline.api import get_user_by_email, get_user_websites, get_user_stats, get_period_range
from bot.states.wait_question import FsmRegistration, FsmEventAnketa, FsmAuth, FsmAskAi
from bot.utils.qr_code import generate_qr_on_template
from bot.utils.resend_mailer import send_otp_email, is_configured as mailer_is_configured
import secrets as _secrets
import time as _time

from aiogram import Dispatcher

if TYPE_CHECKING:
    pass

from aiogram import F
from aiogram.filters.command import Command, CommandObject
from aiogram.exceptions import TelegramRetryAfter, TelegramAPIError

from bot.utils import telegram as telegram, files
from bot.utils.announce_bot import bot
from bot.utils.telegram import generate_user_hlink
from bot.handlers.admin import admin_notifications
from bot.keyboards.client import kb_client_menu
from bot.keyboards.admin import kb_admin_topic
from bot.integrations import DB
from bot.initialization import admin_access, config
from bot.initialization import bot_texts
from bot.utils.scenario_texts import get_text, send_screen_message
from bot.utils.settings_cache import get_settings_cached
from bot.utils.qr_with_text import generate_qr_with_text
from aiogram.types import FSInputFile
from aiogram.enums import ContentType, ChatMemberStatus


input_data = {
    1: ['ФИО', 'rl_full_name'],
    2: ['Номер телефона', 'phone_number'],
    3: ['Роль в компании', 'role'],
    4: ['Тип трафика', 'graph'],
}

IAP_API_URL = os.getenv('IAP_API_URL', 'https://p.winline.ru/api/graphql')
IAP_TOKEN = os.getenv('IAP_ADMIN_TOKEN', '')

# Deep-link payload, ведущий в S3 (event flow). Зашивается в QR на стенде:
#   t.me/<bot_username>?start=<EVENT_DEEPLINK_TOKEN>
# По умолчанию 'event'. Можно поменять через .env, чтобы старые QR перестали работать.
EVENT_DEEPLINK_TOKEN = os.getenv('EVENT_DEEPLINK_TOKEN', 'event')


async def check_email_in_iap(email: str) -> dict:
    """Check if email exists in IAP platform.
    Returns dict: {'found': bool, 'status': int|None, 'id': int|None, 'name': str|None}.
    Делегируем в bot.integrations.winline.api.get_user_by_email — там запрос в формате,
    который IAP принимает (наш собственный $email-вариант возвращает HTTP 400).
    """
    NEG = {'found': False, 'status': None, 'id': None, 'name': None}
    try:
        info = await get_user_by_email(email)
    except Exception as e:
        logger.warning(f'[IAP] Check failed: {e}')
        return NEG
    if not info or not info.get('id'):
        return NEG
    name = ' '.join(filter(None, [info.get('firstName'), info.get('lastName')])) or None
    return {'found': True, 'status': info.get('status'), 'id': info.get('id'), 'name': name}


async def main_menu(update: Union[Message, CallbackQuery],
                    user: User,
                    user_data: DB.User | None,
                    state: FSMContext = None,
                    alert: bool = False) -> Message | bool:
    if state and await state.get_state():
        await state.clear()
    if not user_data:
        await bot.send_message(user.id, '👋')
        wait_registration = await bot.send_message(user.id, '⌛️ Загрузка...')
        try:
            thread_id = await telegram.topic_manager.create_user_topic(update.from_user.first_name)
        except TelegramRetryAfter:
            await wait_registration.edit_text('<b>😥 Приносим свои извинения, бот перегружен, '
                                              'пожалуйста повторите ваш запрос через минуту.</b>')
            await telegram.topic_manager.send_message(telegram.topic_manager.alert,
                                                      '<b>‼️ БОТ НЕ СПРАВЛЯЕТСЯ С НАГРУЗКОЙ!!!\n\n'
                                                      'Срочно подключите резервного бота!</b>')
            return False
        DB.User.add(user.id, update.from_user.full_name, user.username, thread_id)
        if config.admin_filter.is_system(user.id):
            config.admin_filter.add_admin(user.id, 0, admin_access.full_admin_access)
        is_admin = config.admin_filter.is_admin(user.id)
        # Авто-редирект в S3 убран. В S3 попадают ТОЛЬКО юзеры пришедшие по
        # deep-link (t.me/<bot>?start=event), это обрабатывается в start_command.
        kb = kb_client_menu.get_start_menu(is_admin)
        caption_text = get_text('start_menu', 'welcome', name=update.from_user.first_name) or (
            f'<b>Привет, {update.from_user.first_name}! '
            'Этот бот поможет тебе зарегистрироваться в качестве партнёра '
            'в нашей партнерской программе WINLINE PARTNERS, даст возможность получать '
            'актуальные новости и предложения, а также участвовать в мероприятиях!</b>')
        await wait_registration.delete()
        new_menu_id = await wait_registration.answer_photo(
            caption=caption_text,
            photo='AgACAgIAAxkBAALAumm79aB6UEyMKSwO7Y4CIuK0V2GvAALrGWsbCkPgSa2z0SVvYvJsAQADAgADeQADOgQ',
            reply_markup=kb)
        count_users = len(DB.User.select(all_scalars=True))
        link_user = generate_user_hlink(user_id=user.id, text_link=update.from_user.full_name)
        registration_alert = f'<b>🔔 Зарегистрировался пользователь №</b><code>{count_users}</code><b>:</b>\n\n' \
                             f'<b>ID пользователя:</b> <code>{user.id}</code>\n' \
                             f'<b>Отображаемое имя:</b> {link_user}\n' \
                             f'<b>Никнейм</b>: {"@" + user.username if user.username else "<code>отсутствует</code>"}'
        await admin_notifications.registration_notification(registration_alert)
        await telegram.topic_manager.send_message(
            thread_id, registration_alert, main_bot=True,
            reply_markup=kb_admin_topic.topic_management(user.id))
    else:
        # menu_id may be None/0 if the previous bot message was a "permanent"
        # one (raffle congrats, merch QR) that we explicitly do NOT want to
        # erase from the chat — see _show_congrats / _send_event_qr.
        if user_data.menu_id:
            await telegram.delete_message(chat_id=user.id, message_id=user_data.menu_id)
        if alert:
            new_menu_id = await bot.send_message(user.id, '<b>ℹ️Открыто меню из рассылки</b>',
                                                 reply_markup=kb_client_menu.back_menu)
        else:
            is_admin = config.admin_filter.is_admin(user.id)
            auth_data = DB.UserAuth.select(user.id)
            if auth_data:
                email_text = f'\n\n📧 <b>Email:</b> {auth_data.email}' if auth_data.email else ''
                kb = kb_client_menu.get_authorized_menu(is_admin, event_active=get_settings_cached().event_starts, user_id=user.id)
                new_menu_id = await bot.send_photo(
                    chat_id=user.id,
                    caption=get_text('auth_flow', 'auth_success', email=auth_data.email) or f'<b>✅ Вы авторизованы</b>{email_text}',
                    photo='AgACAgIAAxkBAALAumm79aB6UEyMKSwO7Y4CIuK0V2GvAALrGWsbCkPgSa2z0SVvYvJsAQADAgADeQADOgQ',
                    reply_markup=kb)
            else:
                # Not authorized → show start menu (event flow only via deep-link)
                kb = kb_client_menu.get_start_menu(is_admin)
                caption_text = get_text('start_menu', 'welcome', name=user.first_name) or (
                    f'<b>Привет, {user.first_name}! '
                    'Этот бот поможет тебе зарегистрироваться в качестве партнёра '
                    'в нашей партнерской программе WINLINE PARTNERS, даст возможность получать '
                    'актуальные новости и предложения, а также участвовать в мероприятиях!</b>')
                new_menu_id = await bot.send_photo(
                    chat_id=user.id,
                    caption=caption_text,
                    photo='AgACAgIAAxkBAALAumm79aB6UEyMKSwO7Y4CIuK0V2GvAALrGWsbCkPgSa2z0SVvYvJsAQADAgADeQADOgQ',
                    reply_markup=kb)
    if not alert:
        await telegram.delete_message(update)
    DB.User.update(mark=update.from_user.id, menu_id=new_menu_id.message_id)
    return new_menu_id


async def start_command(message: Message, command: CommandObject, state: FSMContext, user_data=None):
    """/start dispatcher.
    Если команда пришла с deep-link payload-ом, совпадающим с EVENT_DEEPLINK_TOKEN,
    юзер сразу попадает в S3 (event_partner_check). Все остальные — обычное меню.
    """
    args = (command.args or '').strip() if command else ''
    if args == EVENT_DEEPLINK_TOKEN:
        if not get_settings_cached().event_starts:
            try:
                await message.answer(
                    get_text('event_flow', 'no_event') or 'Сейчас нет активных мероприятий.'
                )
            except Exception:
                pass
            return await main_menu(message, message.from_user, user_data, state)
        # Гарантируем, что юзер заведён в БД (создаст запись + topic + покажет меню).
        if not user_data:
            await main_menu(message, message.from_user, user_data, state)
            user_data = DB.User.select(message.from_user.id)
        if state and await state.get_state():
            await state.clear()
        from bot.handlers.client.client_event_v2 import _show_screen
        # PERF: пока юзер смотрит intro и проходит анкету (~30-60 секунд),
        # параллельно выдаём ему event_code и рендерим QR-карточку в кэш.
        # К моменту _send_event_qr — pop_qr_card вернёт готовые байты,
        # рендер = 0 мс. Идемпотентно: если код уже был — issue_event_code
        # вернёт existing, и мы рендерим под него.
        asyncio.create_task(_pregenerate_for_user(message.from_user.id))
        # Тег только в дни мероприятия (26.05 → MAC 26, 27.05 → MAC 27).
        # В остальные дни таг не вешается — get_today_event_tag вернёт None.
        _today_tag = get_today_event_tag()
        if _today_tag:
            asyncio.create_task(add_user_tag(message.from_user.id, _today_tag))

        # Сначала показываем приветственный экран event_intro с баннером и
        # кнопкой «Далее». По нажатию пользователь попадёт в event_partner_check.
        await _show_screen(
            message.from_user.id, 'event_intro',
            fallback=(
                '<b>Хочешь получить эксклюзивный мерч, стать партнёром и зарабатывать '
                'вместе с WINLINE PARTNERS?</b>\n\n'
                'Регистрируйся и заполняй анкету! После регистрации, с тобой свяжется '
                'наш Affiliate-менеджер @winline_affiliate и расскажет об условиях.'
            ),
            message_key='welcome',
        )
        return
    return await main_menu(message, message.from_user, user_data, state)


async def back_menu(call: CallbackQuery, state: FSMContext):
    if await state.get_state():
        await state.clear()
    user_data = DB.User.select(call.from_user.id)
    is_admin = config.admin_filter.is_admin(call.from_user.id)
    auth_data = DB.UserAuth.select(call.from_user.id)
    if auth_data:
        email_text = f'\n\n📧 <b>Email:</b> {auth_data.email}' if auth_data.email else ''
        kb = kb_client_menu.get_authorized_menu(is_admin, event_active=get_settings_cached().event_starts, user_id=call.from_user.id)
        try:
            await call.message.delete()
        except TelegramAPIError:
            ...
        new_menu = await bot.send_photo(
            chat_id=call.from_user.id,
            caption=get_text('auth_flow', 'auth_success', email=auth_data.email) or f'<b>✅ Вы авторизованы</b>{email_text}',
            photo='AgACAgIAAxkBAALAumm79aB6UEyMKSwO7Y4CIuK0V2GvAALrGWsbCkPgSa2z0SVvYvJsAQADAgADeQADOgQ',
            reply_markup=kb)
        DB.User.update(mark=call.from_user.id, menu_id=new_menu.message_id)
    else:
        try:
            await call.message.delete()
        except TelegramAPIError:
            ...
        kb = kb_client_menu.get_start_menu(is_admin)
        caption_text = get_text('start_menu', 'welcome') or (
            '<b>Привет! Этот бот поможет тебе зарегистрироваться в качестве партнёра, '
            'предоставит быстрый доступ к порталу WINLINE PARTNERS, даст возможность получать '
            'актуальные новости и предложения, а также участвовать в мероприятиях!</b>')
        new_menu = await bot.send_photo(
            chat_id=call.from_user.id,
            caption=caption_text,
            photo='AgACAgIAAxkBAALAumm79aB6UEyMKSwO7Y4CIuK0V2GvAALrGWsbCkPgSa2z0SVvYvJsAQADAgADeQADOgQ',
            reply_markup=kb)
        DB.User.update(mark=call.from_user.id, menu_id=new_menu.message_id)
    await call.answer()


async def registration(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except TelegramAPIError as _e:
        ...
    menu = await call.message.answer(
        '<b>Чтобы зарегистрироваться - введи своё ФИО</b>'
    )
    DB.User.update(call.from_user.id, menu_id=menu.message_id)
    await state.set_state(FsmRegistration.wait_rl_name)
    await state.update_data(
        menu_message=menu,
    )


async def subscribe(call: CallbackQuery, user_data: DB.User, state: FSMContext):
    member = await bot.get_chat_member(
        -1002066039310,
        call.from_user.id
    )
    if member.status not in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus]:
        return await call.answer('Не получилось проверить подписку. Ты точно подписан(а) на канал @WinlinePartners?')

    if not user_data.registered:
        DB.User.update(call.from_user.id, registered=True)
    user_data = DB.User.select(call.from_user.id)
    await new_user(str(call.from_user.id), str(call.from_user.full_name), str(call.from_user.username),
                   user_data.role, user_data.graph, user_data.rl_full_name, user_data.phone_number)
    qr_id = DB.QRCode.add(call.from_user.id, "Мерч")
    await generate_qr_on_template(
        template_path="merch.png",
        qr_data=f"{qr_id}",
        output_path=f"files/{call.from_user.id}.png",
        qr_size=450,
        qr_position=(43, 130),
        qr_color="#FF6914"
    )
    await new_prize(str(call.from_user.id), 'Мерч', str(qr_id))

    if get_settings_cached().event_starts:
        try:
            await call.message.delete()
        except TelegramAPIError:
            ...
        new_menu = await bot.send_photo(
            chat_id=call.from_user.id,
            photo=FSInputFile(f"files/{call.from_user.id}.png"),
            caption='<b>Вот ваш QR для получения подарка!</b>'
        )
        DB.User.update(mark=call.from_user.id, menu_id=new_menu.message_id)
        return

    if user_data.role == 'Рекламодатель':
        return await main_menu(call, call.from_user, user_data, state)

    link = hlink('@winline_affiliate', 'https://t.me/m/hcj7_tDRMmEy')
    return await call.message.edit_text(f'<b>Это - {link}, наш Affiliate менеджер. Напиши ему!)</b>',
                                        reply_markup=kb_client_menu.pm)


async def pm(call: CallbackQuery, user_data: DB.User, state: FSMContext):
    if not user_data.registered:
        DB.User.update(call.from_user.id, registered=True)
    user_data = DB.User.select(call.from_user.id)
    return await main_menu(call, call.from_user, user_data, state)


def _sanitize_text(s: str | None, max_len: int = 100) -> str:
    """Strip control chars, collapse whitespace, cap length. Used for free-form
    user input that flows into Telegram captions / Google Sheets."""
    if not s:
        return ''
    cleaned = ''.join(ch for ch in s if ch == ' ' or ch.isprintable())
    cleaned = ' '.join(cleaned.split())
    return cleaned[:max_len].strip()


async def wait_rl_name(message: Message, state: FSMContext):
    await message.delete()
    data = await state.get_data()
    name = _sanitize_text(message.text, max_len=100)
    if not name:
        return
    await state.update_data(rl_full_name=name)
    menu: Message = data['menu_message']
    await menu.edit_text('<b>Введи твой номер телефона</b>')
    await state.set_state(FsmRegistration.wait_phone)
    DB.User.update(message.from_user.id, rl_full_name=name)


async def wait_phone(message: Message, state: FSMContext):
    await message.delete()
    data = await state.get_data()
    import re as _re
    raw = (message.text or '').strip()
    digits = _re.sub(r'\D', '', raw)
    if not (10 <= len(digits) <= 15):
        menu: Message = data.get('menu_message')
        if menu:
            try:
                await menu.edit_text('<b>📱 Введи корректный номер телефона (10–15 цифр).</b>')
            except TelegramAPIError:
                pass
        return
    phone = ('+' + digits) if not raw.startswith('+') else ('+' + digits)
    await state.update_data(phone_number=phone)
    menu: Message = data['menu_message']
    await menu.edit_text('<b>Выбери свою роль в компании</b>', reply_markup=kb_client_menu.user_role)
    await state.set_state(FsmRegistration.wait_phone)
    DB.User.update(message.from_user.id, phone_number=phone)


async def pick_role(call: CallbackQuery, state: FSMContext):
    role = call.data.split(':')[-1]
    DB.User.update(call.from_user.id, role=role)

    if role == 'Другое':
        await call.message.edit_text('<b>Расскажи о своей роли в компании</b>')
        await state.set_state(FsmRegistration.wait_about_role)
        DB.User.update(call.from_user.id, graph='Нет')
    elif role == 'Рекламодатель':
        await call.message.edit_text('<b>Отлично! Осталось подписаться на канал '
                                     '@WinlinePartners и можно приходить на стенд Winline Partners, '
                                     'чтобы получить мерч!</b>', reply_markup=kb_client_menu.subscribe)
        DB.User.update(call.from_user.id, graph='Нет')
    else:
        await call.message.edit_text('<b>Какой у тебя тип трафика?</b>', reply_markup=kb_client_menu.user_traff)
        await state.set_state(FsmRegistration.wait_traff)


async def wait_traff(call: CallbackQuery, state: FSMContext):
    traff = call.data.split(':')[-1]
    DB.User.update(call.from_user.id, graph=traff)
    await call.message.edit_text('<b>Отлично! Осталось подписаться на канал '
                                 '@WinlinePartners и можно приходить на стенд Winline Partners, '
                                 'чтобы получить мерч!</b>', reply_markup=kb_client_menu.subscribe)


async def back_to_start(call: CallbackQuery):
    await call.message.edit_caption(
        caption=get_text('start_menu', 'welcome', name=call.from_user.first_name) or (
            f'<b>Привет, {call.from_user.first_name}! '
            'Этот бот поможет тебе зарегистрироваться в качестве партнёра '
            'в нашей партнерской программе WINLINE PARTNERS, даст возможность получать '
            'актуальные новости и предложения, а также участвовать в мероприятиях!</b>'),
        reply_markup=kb_client_menu.get_start_menu())
    await call.answer()


async def show_auth_screen(call: CallbackQuery):
    await call.message.edit_caption(
        caption=get_text('auth_flow', 'auth_screen') or '<b>Для доступа к функционалу бота необходимо авторизоваться с помощью почты, указанной при регистрации на платформе</b>',
        reply_markup=kb_client_menu.get_auth_menu())
    await call.answer()


async def existing_partner(call: CallbackQuery):
    await show_auth_screen(call)


async def new_partner(call: CallbackQuery):
    reg_fallback = (
        '<b>Чтобы стать партнёром WINLINE PARTNERS, Вам нужно перейти на '
        '<a href="https://partners.winline.ru">официальный сайт партнерской программы</a> '
        'и зарегистрироваться.</b>\n\n'
        'При регистрации укажите следующую информацию:\n'
        '• имя и фамилию;\n'
        '• свой email;\n'
        '• пароль.\n\n'
        'После заполнения заявки нажмите кнопку «Регистрация» и подтвердите '
        'регистрацию аккаунта по email.'
    )
    await call.message.edit_caption(
        caption=get_text('registration_flow', 'instructions') or reg_fallback,
        reply_markup=kb_client_menu.get_registration_partners_menu())
    await call.answer()


async def already_registered(call: CallbackQuery):
    await show_auth_screen(call)


# ── Email auth flow ──────────────────────────────────────────────────────────

async def start_auth_email(call: CallbackQuery, state: FSMContext):
    """User clicked 'Авторизоваться' → ask for email input."""
    try:
        await call.message.delete()
    except TelegramAPIError:
        ...
    menu = await bot.send_message(
        call.from_user.id,
        get_text('auth_flow', 'email_prompt') or '<b>📧 Введите email, указанный при регистрации на платформе</b>')
    DB.User.update(mark=call.from_user.id, menu_id=menu.message_id)
    await state.set_state(FsmAuth.wait_email)
    await state.update_data(auth_menu_message=menu)
    await call.answer()


AUTH_OTP_RESEND_COOLDOWN_SEC = 60


def _auth_otp_keyboard(can_resend: bool = True):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    rows = []
    if can_resend:
        rows.append([InlineKeyboardButton(text='📧 Отправить код повторно', callback_data='auth_otp_resend')])
    rows.append([InlineKeyboardButton(text='✏️ Изменить email', callback_data='auth_otp_change_email')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _auth_otp_prompt_text(email: str) -> str:
    base = (get_text('auth_flow', 'otp_prompt', email=email)
            or f'<b>📬 Код отправлен на {email}</b>\n\nВведите 6-значный код из письма. Код действителен 10 минут.')
    return base + '\n\n<i>Письмо может прийти в течение 1–2 минут. Проверьте папку «Спам».</i>'


async def process_auth_email(message: Message, state: FSMContext):
    """Process email input — validate format, save auth."""
    import re
    await message.delete()
    data = await state.get_data()
    menu_msg = data.get('auth_menu_message')

    email = message.text.strip().lower()

    # Basic email validation
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        if menu_msg:
            try:
                await menu_msg.edit_text(
                    get_text('auth_flow', 'email_error') or '<b>❌ Некорректный формат email\n\n📧 Введите email, указанный при регистрации на платформе</b>')
            except TelegramAPIError:
                ...
        return

    # Check email in IAP platform
    user_id = message.from_user.id
    iap = await check_email_in_iap(email)

    if not iap['found']:
        if menu_msg:
            try:
                await menu_msg.edit_text(
                    get_text('auth_flow', 'email_not_found') or
                    '<b>❌ Email не найден</b>\n\n'
                    'Этот email не зарегистрирован на платформе.\n'
                    'Зарегистрируйтесь как партнёр и попробуйте снова.\n\n'
                    '📧 Или введите другой email:')
            except TelegramAPIError:
                ...
        return  # Stay in wait_email state

    if iap['status'] is not None and iap['status'] != 1:
        if menu_msg:
            try:
                await menu_msg.edit_text(
                    get_text('auth_flow', 'email_blocked') or
                    '<b>🚫 Аккаунт заблокирован</b>\n\n'
                    'Ваш аккаунт на платформе заблокирован.\n'
                    'Обратитесь в поддержку для разблокировки.')
            except TelegramAPIError:
                ...
        await state.clear()
        return

    # IAP passed — if Resend configured, send OTP and wait for code. Otherwise авторизуем сразу (fallback).
    if mailer_is_configured():
        code = f'{_secrets.randbelow(1_000_000):06d}'
        sent = await send_otp_email(email, code)
        if sent:
            await state.update_data(
                auth_email=email,
                auth_otp=code,
                auth_otp_expires=int(_time.time()) + 600,  # 10 минут
                auth_otp_attempts=0,
                auth_otp_resend_at=int(_time.time()) + AUTH_OTP_RESEND_COOLDOWN_SEC,
            )
            await state.set_state(FsmAuth.wait_otp)
            if menu_msg:
                try:
                    await menu_msg.edit_text(_auth_otp_prompt_text(email),
                                             reply_markup=_auth_otp_keyboard())
                except TelegramAPIError:
                    ...
            return
        else:
            logger.warning(f'[auth] Resend send failed for {email}, fallback: авторизуем без OTP')

    await _finalize_auth(user_id, email, menu_msg, state)


async def auth_otp_resend(call: CallbackQuery, state: FSMContext):
    """«Отправить код повторно» в обычном auth-flow."""
    data = await state.get_data()
    email = data.get('auth_email')
    menu_msg = data.get('auth_menu_message')
    resend_at = int(data.get('auth_otp_resend_at') or 0)

    if not email:
        await call.answer('Сессия истекла, начните сначала', show_alert=True)
        return

    now = int(_time.time())
    if now < resend_at:
        await call.answer(f'Подождите ещё {resend_at - now} сек.', show_alert=False)
        return

    code = f'{_secrets.randbelow(1_000_000):06d}'
    sent = await send_otp_email(email, code)
    if not sent:
        await call.answer('Не удалось отправить, попробуйте позже', show_alert=True)
        return
    await state.update_data(
        auth_otp=code,
        auth_otp_expires=now + 600,
        auth_otp_attempts=0,
        auth_otp_resend_at=now + AUTH_OTP_RESEND_COOLDOWN_SEC,
    )
    if menu_msg:
        try:
            await menu_msg.edit_text(_auth_otp_prompt_text(email),
                                     reply_markup=_auth_otp_keyboard())
        except TelegramAPIError:
            ...
    await call.answer('Код отправлен повторно')


async def auth_otp_change_email(call: CallbackQuery, state: FSMContext):
    """«Изменить email» — возврат к вводу email."""
    data = await state.get_data()
    menu_msg = data.get('auth_menu_message')
    await state.set_state(FsmAuth.wait_email)
    await state.update_data(
        auth_otp=None, auth_otp_expires=None,
        auth_otp_attempts=0, auth_otp_resend_at=None,
        auth_email=None,
    )
    if menu_msg:
        try:
            await menu_msg.edit_text(
                get_text('auth_flow', 'email_prompt')
                or '<b>📧 Введите email, указанный при регистрации на платформе</b>'
            )
        except TelegramAPIError:
            ...
    await call.answer()


async def _finalize_auth(user_id: int, email: str, menu_msg, state: FSMContext):
    """Завершить авторизацию: сохранить UserAuth, проставить теги, показать авторизованное меню."""
    existing = DB.UserAuth.select(user_id)
    if existing:
        DB.UserAuth.update(user_id, email=email, token=None)
        DB.User.update(user_id, registered=True)
    else:
        DB.UserAuth.add(user_id, email, token=None)
    DB.User.update(user_id, registered=True)

    # Auto-assign "Партнёр" tag + remove "Старый пользователь" in admin panel (non-blocking)
    try:
        def _update_partner_tags(uid):
            _cfg = {
                'host': os.getenv('MYSQL_HOST', ''), 'port': int(os.getenv('MYSQL_PORT', 3306)),
                'user': os.getenv('MYSQL_USER', ''), 'password': os.getenv('MYSQL_PASSWORD', ''),
                'database': os.getenv('MYSQL_DATABASE', ''),
            }
            c = mysql.connector.connect(**_cfg)
            try:
                cur = c.cursor()
                cur.execute(
                    'INSERT IGNORE INTO wl_admin_user_tags (user_id, tag) VALUES (%s, %s)',
                    (uid, 'Партнёр'),
                )
                cur.execute(
                    'DELETE FROM wl_admin_user_tags WHERE user_id = %s AND tag = %s',
                    (uid, 'Старый пользователь'),
                )
                c.commit()
            finally:
                try: c.close()
                except Exception: pass
        await asyncio.to_thread(_update_partner_tags, user_id)
    except Exception as _e:
        logger.warning(f'[partner_tag] Failed for user {user_id}: {_e}')

    await state.clear()

    if menu_msg:
        try:
            await menu_msg.delete()
        except TelegramAPIError:
            ...

    is_admin = config.admin_filter.is_admin(user_id)
    kb = kb_client_menu.get_authorized_menu(is_admin, event_active=get_settings_cached().event_starts, user_id=user_id)
    new_menu = await bot.send_photo(
        chat_id=user_id,
        caption=get_text('auth_flow', 'auth_success', email=email) or f'<b>✅ Вы авторизованы</b>\n\n📧 <b>Email:</b> {email}',
        photo='AgACAgIAAxkBAALAumm79aB6UEyMKSwO7Y4CIuK0V2GvAALrGWsbCkPgSa2z0SVvYvJsAQADAgADeQADOgQ',
        reply_markup=kb)
    DB.User.update(mark=user_id, menu_id=new_menu.message_id)


async def process_auth_otp(message: Message, state: FSMContext):
    """Проверка 6-значного OTP-кода, присланного на email."""
    try:
        await message.delete()
    except TelegramAPIError:
        ...
    data = await state.get_data()
    menu_msg = data.get('auth_menu_message')
    email = data.get('auth_email')
    expected = data.get('auth_otp')
    expires = int(data.get('auth_otp_expires') or 0)
    attempts = int(data.get('auth_otp_attempts') or 0)

    if not expected or not email:
        await state.clear()
        return

    if int(_time.time()) > expires:
        if menu_msg:
            try:
                await menu_msg.edit_text(
                    '<b>⏰ Код истёк</b>\n\nЗапросите новый вход: /start')
            except TelegramAPIError:
                ...
        await state.clear()
        return

    entered = (message.text or '').strip()
    # нормализуем: оставим только цифры
    entered_digits = ''.join(ch for ch in entered if ch.isdigit())

    import hmac as _hmac
    if not _hmac.compare_digest(entered_digits, str(expected)):
        attempts += 1
        if attempts >= 5:
            if menu_msg:
                try:
                    await menu_msg.edit_text(
                        '<b>🚫 Слишком много попыток</b>\n\nЗапросите новый код: /start')
                except TelegramAPIError:
                    ...
            await state.clear()
            return
        await state.update_data(auth_otp_attempts=attempts)
        if menu_msg:
            try:
                await menu_msg.edit_text(
                    f'<b>❌ Неверный код</b>\n\nОсталось попыток: {5 - attempts}\n\n'
                    f'Введите 6-значный код из письма, отправленного на {email}:')
            except TelegramAPIError:
                ...
        return

    # OK — финализируем авторизацию
    await _finalize_auth(message.from_user.id, email, menu_msg, state)


# ── PM: Моя статистика ─────────────────────────────────────────────────────

_WEBSITE_STATUS_LABELS = {
    1: '✅ активна',
    2: '⏳ на модерации',
    3: '❌ отклонена',
}

_ROLE_LABELS = {
    'partner': 'Партнёр',
    'admin': 'Администратор',
    'manager': 'Менеджер',
    'owner': 'Владелец',
}


def _fmt_ts_ms(ts) -> str:
    """Format a millisecond timestamp (string or int) as 'YYYY-MM-DD HH:MM'."""
    if ts is None or ts == '':
        return '—'
    try:
        ts_int = int(ts)
    except (TypeError, ValueError):
        return '—'
    # API timestamps appear to be in milliseconds
    if ts_int > 10**12:
        ts_int //= 1000
    try:
        return datetime.fromtimestamp(ts_int).strftime('%Y-%m-%d %H:%M')
    except (OSError, ValueError):
        return '—'


def _fmt_money(v) -> str:
    try:
        return f'{float(v):.2f}'
    except (TypeError, ValueError):
        return '0.00'


def _build_stats_text(user: dict, sites: list[dict]) -> str:
    full_name = ' '.join(filter(None, [user.get('lastName'), user.get('firstName'), user.get('middleName')])).strip()
    # try several possible organization-name fields (schema varies)
    org_candidates = [
        user.get('organizationName'),
        user.get('companyName'),
        user.get('orgName'),
        user.get('legalName'),
        user.get('fullName'),
        user.get('shortName'),
    ]
    for obj_key in ('organization', 'company', 'org', 'legal', 'juridical', 'entity'):
        v = user.get(obj_key)
        if isinstance(v, dict):
            org_candidates.append(v.get('name'))
    org_name = next((o for o in org_candidates if o), None)

    if full_name:
        ident_label = 'ФИО'
        ident_value = full_name
    elif org_name:
        ident_label = 'Организация'
        ident_value = org_name
    else:
        ident_label = 'ФИО'
        ident_value = '—'

    email = user.get('email') or '—'
    tg = user.get('telegram') or '—'
    email_conf = '✅' if user.get('emailConfirmed') else '⚠️ не подтверждён'
    status_label = '🟢 активен' if user.get('status') == 1 else '🔴 заблокирован'
    role_raw = user.get('role') or ''
    role_label = _ROLE_LABELS.get(role_raw, role_raw or '—')

    # debit = earnings balance, credit = withdrawn (interpretation pending real data)
    earned = _fmt_rub(user.get('debit'))
    withdrawn = _fmt_rub(user.get('credit'))

    parts = [
        '<b>📊 Моя статистика</b>\n',
        f'<b>{ident_label}:</b> {ident_value}',
        f'<b>Email:</b> {email} {email_conf}',
        f'<b>Telegram:</b> {tg}',
        f'<b>Роль:</b> {role_label}',
        f'<b>Статус:</b> {status_label}',
        f'<b>Регистрация:</b> {_fmt_ts_ms(user.get("created"))}',
        f'<b>Последний вход:</b> {_fmt_ts_ms(user.get("lastLogin"))}',
        '',
        f'💰 <b>Заработано:</b> {earned} ₽',
        f'💸 <b>Выведено:</b> {withdrawn} ₽',
        '',
    ]

    # Websites
    if not sites:
        parts.append(
            '<b>🌐 Площадки:</b> <i>нет</i>\n\n'
            '⚠️ Без одобренной площадки конверсии не будут засчитываться.\n'
            'Добавьте площадку в личном кабинете на '
            '<a href="https://partners.winline.ru">partners.winline.ru</a>.'
        )
    else:
        active = [s for s in sites if s.get('status') == 1]
        moderating = [s for s in sites if s.get('status') == 2]
        rejected = [s for s in sites if s.get('status') == 3]
        parts.append(
            f'<b>🌐 Площадки:</b> {len(sites)} '
            f'(активных: {len(active)}, на модерации: {len(moderating)}, отклонённых: {len(rejected)})'
        )
        # Show first 10 sites to keep caption under Telegram limits
        for s in sites[:10]:
            status = _WEBSITE_STATUS_LABELS.get(s.get('status'), '—')
            nm = s.get('name') or '—'
            alias = s.get('alias') or '—'
            parts.append(f'• <code>{alias}</code> · {nm} · {status}')
        if len(sites) > 10:
            parts.append(f'<i>…и ещё {len(sites) - 10} площадок</i>')
        if not active:
            parts.append(
                '\n⚠️ Ни одной активной площадки. '
                'Пока все площадки не одобрены — конверсии не засчитываются.'
            )

    return '\n'.join(parts)


def _fmt_rub(v) -> str:
    """Format a ruble amount with thin-space thousand separators and 2 decimals."""
    try:
        f = float(v or 0)
    except (TypeError, ValueError):
        f = 0.0
    whole, frac = f'{f:,.2f}'.split('.')
    return whole.replace(',', '\u2009') + '.' + frac


def _build_period_block(period_label: str, totals: dict) -> str:
    reg = int(totals.get('goal11Quantity') or 0)
    dep = int(totals.get('goal12Quantity') or 0)
    dep2 = int(totals.get('goal13Quantity') or 0)
    clicks = int(totals.get('clicks') or 0)
    conf = totals.get('rewardConfirmed') or 0
    proc = totals.get('rewardCreated') or 0
    canc = totals.get('rewardCanceled') or 0
    return '\n'.join([
        f'<b>📈 Показатели {period_label}</b>',
        '',
        f'👁 <b>Клики:</b> {clicks}',
        f'📝 <b>РЕГ:</b> {reg}   •   💵 <b>ДЕП:</b> {dep}   •   🔁 <b>ДЕП2:</b> {dep2}',
        '',
        '💰 <b>Комиссия:</b>',
        f'├ Подтверждена: <b>{_fmt_rub(conf)} ₽</b>',
        f'├ В обработке: <b>{_fmt_rub(proc)} ₽</b>',
        f'└ Аннулирована: <b>{_fmt_rub(canc)} ₽</b>',
    ])


async def pm_my_stats(call: CallbackQuery):
    """Show period selector for stats."""
    user_id = call.from_user.id
    try:
        await call.message.delete()
    except TelegramAPIError:
        ...

    auth_data = DB.UserAuth.select(user_id)
    if not auth_data or not getattr(auth_data, 'email', None):
        is_admin = config.admin_filter.is_admin(user_id)
        await bot.send_message(
            user_id,
            '<b>❌ Не найден email авторизации</b>\n\nПожалуйста, авторизуйтесь заново.',
            reply_markup=kb_client_menu.get_authorized_menu(
                is_admin, event_active=get_settings_cached().event_starts, user_id=user_id,
            ),
        )
        await call.answer()
        return

    email = auth_data.email
    loader = await bot.send_message(user_id, '⌛️ Загружаю статистику...')
    try:
        user_info = await get_user_by_email(email)
        if not user_info:
            await loader.edit_text(
                '<b>❌ Не удалось получить данные</b>\n\n'
                f'Email <code>{email}</code> не найден на платформе или сервис недоступен.',
                reply_markup=kb_client_menu.back_menu,
            )
            DB.User.update(mark=user_id, menu_id=loader.message_id)
            await call.answer()
            return
        sites = []
        uid = user_info.get('id')
        if uid:
            try:
                sites = await get_user_websites(int(uid), user_info.get('email'))
            except Exception as e:
                logger.warning(f'[stats] websites fetch failed: {e}')
        text = _build_stats_text(user_info, sites) + '\n\n━━━━━━━━━━━━━━━\nВыберите период для детальных цифр:'
        try:
            await loader.edit_text(text, reply_markup=kb_client_menu.stats_periods, disable_web_page_preview=True)
            new_menu = loader
        except TelegramAPIError:
            new_menu = await bot.send_message(
                user_id, text, reply_markup=kb_client_menu.stats_periods, disable_web_page_preview=True,
            )
        DB.User.update(mark=user_id, menu_id=new_menu.message_id)
    except Exception as e:
        logger.exception(f'[stats] unexpected error: {e}')
        try:
            await loader.edit_text(
                '<b>❌ Ошибка загрузки статистики</b>\n\nПопробуйте позже.',
                reply_markup=kb_client_menu.back_menu,
            )
            DB.User.update(mark=user_id, menu_id=loader.message_id)
        except TelegramAPIError:
            pass
    await call.answer()


async def pm_stats_period(call: CallbackQuery):
    """Fetch and render stats for selected period."""
    user_id = call.from_user.id
    payload = (call.data or '').split(':', 1)
    period = payload[1] if len(payload) == 2 else 'yesterday'
    if period not in ('yesterday', 'week', 'month'):
        period = 'yesterday'

    try:
        await call.message.delete()
    except TelegramAPIError:
        ...

    auth_data = DB.UserAuth.select(user_id)
    if not auth_data or not getattr(auth_data, 'email', None):
        await bot.send_message(
            user_id,
            '<b>❌ Не найден email авторизации</b>\n\nПожалуйста, авторизуйтесь заново.',
            reply_markup=kb_client_menu.back_menu,
        )
        await call.answer()
        return

    email = auth_data.email
    loader = await bot.send_message(user_id, '⌛️ Загружаю статистику...')

    try:
        user_info = await get_user_by_email(email)
        if not user_info:
            await loader.edit_text(
                '<b>❌ Не удалось получить данные</b>\n\n'
                f'Email <code>{email}</code> не найден на платформе или сервис недоступен.',
                reply_markup=kb_client_menu.stats_back_to_periods,
            )
            DB.User.update(mark=user_id, menu_id=loader.message_id)
            await call.answer()
            return

        uid = user_info.get('id')
        sites: list[dict] = []
        if uid:
            try:
                sites = await get_user_websites(int(uid), user_info.get('email'))
            except Exception as e:
                logger.warning(f'[stats] websites fetch failed: {e}')

        start_iso, end_iso, label = get_period_range(period)
        totals = None
        if uid:
            try:
                totals = await get_user_stats(int(uid), start_iso, end_iso)
            except Exception as e:
                logger.warning(f'[stats] period stats fetch failed: {e}')

        if totals is None:
            await loader.edit_text(
                '<b>❌ Не удалось получить статистику</b>\n\nСервис недоступен, попробуйте позже.',
                reply_markup=kb_client_menu.stats_back_to_periods,
            )
            DB.User.update(mark=user_id, menu_id=loader.message_id)
            await call.answer()
            return

        text = _build_stats_text(user_info, sites) + '\n\n━━━━━━━━━━━━━━━\n' + _build_period_block(label, totals)
        try:
            await loader.edit_text(
                text, reply_markup=kb_client_menu.stats_back_to_periods, disable_web_page_preview=True,
            )
            new_menu = loader
        except TelegramAPIError:
            new_menu = await bot.send_message(
                user_id, text,
                reply_markup=kb_client_menu.stats_back_to_periods, disable_web_page_preview=True,
            )
        DB.User.update(mark=user_id, menu_id=new_menu.message_id)
    except Exception as e:
        logger.exception(f'[stats] unexpected error: {e}')
        try:
            await loader.edit_text(
                '<b>❌ Ошибка загрузки статистики</b>\n\nПопробуйте позже.',
                reply_markup=kb_client_menu.stats_back_to_periods,
            )
            DB.User.update(mark=user_id, menu_id=loader.message_id)
        except TelegramAPIError:
            pass
    await call.answer()


async def pm_offers(call: CallbackQuery):
    """Show offer info in PM."""
    try:
        await call.message.delete()
    except TelegramAPIError:
        ...
    offer_fallback = (
        '<b>📚 Информация по офферу</b>\n\n'
        '<tg-emoji emoji-id="5249137793120107984">🔥</tg-emoji> <b>Тестовая капа для оценки качества трафика:</b> 20 FTD (для новых партнеров)\n\n'
        '<b>Оплачиваемая цель:</b> новый пользователь, который внес депозит от 500 рублей единым платежом (FTD)\n'
        'Baseline \u2013 500 р\n'
        'Мин.деп \u2013 100 р\n'
        'Целевая аудитория: мужчины, женщины 18+\n'
        'Атрибуция \u2013 по Last Click\n'
        'Hold (проверка трафика) \u2013 30 дней\n'
        'Выплата средств \u2013 1 раз в месяц (после сверки)\n\n'
        'Минимальная сумма для вывода средств от 100 000р\n\n'
        '<tg-emoji emoji-id="5249137793120107984">🔥</tg-emoji> <b>ВАЖНО!</b>\n'
        'WINLINE осуществляет анализ качества приведенного трафика, который учитывает множество факторов:\n'
        '\u2014 Оценка трафика от службы безопасности (мошенник, вилочник, бонусхантер и др.)\n'
        '\u2014 Проверка на фрод\n'
        '\u2014 Паттерн поведения игроков, которых привел партнер\n'
        '\u2014 Сумма вводов/ставок и т.д\n'
        'Строго запрещено: фрод, мультиаккаунтинг, бонусхантинг, мотивированный, схемный трафик.\n\n'
        'Запрещённые тематики: adult контент, оружие, насилие, политика, детский контент и фигурирование детей рядом с брендом, трансляция лёгкого заработка, шокирующий контент, треш контент.\n\n'
        '<tg-emoji emoji-id="5249137793120107984">🔥</tg-emoji> <b>Рекламодатель имеет право пересмотреть условия оплаты или не оплатить трафик в случае обнаружения нарушений.</b>'
    )
    offer_text = get_text('offer_page', 'offer_text') or offer_fallback
    from bot.utils.dynamic_kb import get_screen_kb
    offer_kb = get_screen_kb('offer_page') or kb_client_group.create_inline([
        ['🔙 Меню', 'call', 'client_back_menu'],
    ], 1)
    new_menu = await send_screen_message(
        bot, call.from_user.id, 'offer_page',
        text=offer_text,
        reply_markup=offer_kb)
    DB.User.update(mark=call.from_user.id, menu_id=new_menu.message_id)
    await call.answer()


# ── PM: База знаний & Промо ─────────────────────────────────────────────────

from bot.keyboards.client import kb_client_group
from bot.keyboards.client import kb_client_group


async def pm_knowledge_base(call: CallbackQuery):
    """Show dynamic knowledge base menu in PM."""
    try:
        await call.message.delete()
    except TelegramAPIError:
        ...
    kb_row = DB.Text.select(where=DB.Text.category == 'knowledge_base')
    kb = kb_row.data if kb_row else {}
    new_menu = await bot.send_message(
        chat_id=call.from_user.id,
        text='<b>📚 База знаний</b>\n\n<i>Выберите интересующую тему:</i>',
        reply_markup=kb_client_group.build_kb_menu(kb, 'pm_kb_', 'client_back_menu'))
    DB.User.update(mark=call.from_user.id, menu_id=new_menu.message_id)
    await call.answer()


async def pm_kb_subtopic(call: CallbackQuery):
    """Handle KB topic / subtopic / back-to-parent in PM."""
    data = call.data

    # Возврат к родительской теме (приходит из подтемы с фото — нужно подчистить)
    if data.startswith('pm_kb_back_parent:'):
        rest = data[len('pm_kb_back_parent:'):]
        try:
            parent_key, ids_str = rest.split(':', 1)
        except ValueError:
            parent_key, ids_str = rest, ''
        chat_id = call.from_user.id
        for mid_str in ids_str.split(','):
            try:
                await bot.delete_message(chat_id=chat_id, message_id=int(mid_str))
            except Exception:
                pass
        # Эмулируем повторный клик по родительской теме: подменим data и упадём ниже
        call_data_emulated = f'pm_kb_{parent_key}'
        return await _pm_kb_show(call, call_data_emulated, fresh_send=True)

    return await _pm_kb_show(call, data, fresh_send=False)


async def _pm_kb_show(call: CallbackQuery, callback_data: str, fresh_send: bool):
    """Render KB topic or subtopic. If fresh_send — отправляем новое сообщение,
    иначе пытаемся edit_text текущего."""
    text_key = callback_data.replace('pm_kb_', '', 1)
    kb_row = DB.Text.select(where=DB.Text.category == 'knowledge_base')
    kb = kb_row.data if kb_row else {}

    is_subtopic = '__' in text_key
    parent_key = text_key.split('__', 1)[0] if is_subtopic else text_key
    sub_meta = kb.get('_meta', {}).get('subtopics', {}).get(parent_key)
    has_subs = bool(sub_meta and sub_meta.get('order'))

    text = kb.get(text_key, '<b>Информация не найдена</b>')
    photo_key = f'{text_key}_photo'
    photo_id = kb.get(photo_key) or None
    chat_id = call.from_user.id

    # Выбор клавиатуры
    if is_subtopic:
        # Подтема — обратно к родителю
        kb_no_photo = kb_client_group.back_to_parent_topic('pm_kb_', parent_key)
    elif has_subs:
        # Тема с подтемами — список подтем + back to KB
        kb_no_photo = kb_client_group.build_kb_subtopics_menu(kb, parent_key, 'pm_kb_', 'pm_knowledge_base')
    else:
        # Простая тема
        kb_no_photo = kb_client_group.pm_back_to_knowledge_base

    sent_ids = []
    if photo_id:
        if not fresh_send:
            try: await call.message.delete()
            except Exception: pass
        msg1 = await bot.send_photo(chat_id=chat_id, photo=photo_id)
        sent_ids.append(msg1.message_id)
        if is_subtopic:
            kb_with_ids = kb_client_group.back_to_parent_topic_with_ids('pm_kb_', parent_key, sent_ids)
        elif has_subs:
            # При фото у темы с подтемами — кнопки подтем после контента, но «к базе знаний»
            # должно подчистить фото; используем обычное back_to_kb с ids нет — оставим как есть
            kb_with_ids = kb_client_group.build_kb_subtopics_menu(kb, parent_key, 'pm_kb_', 'pm_knowledge_base')
        else:
            kb_with_ids = kb_client_group.pm_back_to_kb_with_ids(sent_ids)
        msg2 = await bot.send_message(chat_id=chat_id, text=text, reply_markup=kb_with_ids)
        sent_ids.append(msg2.message_id)
    else:
        if fresh_send:
            await bot.send_message(chat_id=chat_id, text=text, reply_markup=kb_no_photo)
        else:
            try:
                await call.message.edit_text(text, reply_markup=kb_no_photo)
            except TelegramAPIError:
                await bot.send_message(chat_id=chat_id, text=text, reply_markup=kb_no_photo)
    await call.answer()


async def pm_kb_back_to_menu(call: CallbackQuery):
    """Return to dynamic KB menu from subtopic in PM."""
    kb_row = DB.Text.select(where=DB.Text.category == 'knowledge_base')
    kb = kb_row.data if kb_row else {}
    await call.message.edit_text(
        '<b>📚 База знаний</b>\n\n<i>Выберите интересующую тему:</i>',
        reply_markup=kb_client_group.build_kb_menu(kb, 'pm_kb_', 'client_back_menu'))
    await call.answer()


async def pm_kb_back(call: CallbackQuery):
    """Back from multi-part KB topic in PM — delete all, show dynamic KB menu."""
    ids_part = call.data.split(':', 1)[1] if ':' in call.data else ''
    message_ids = []
    for mid_str in ids_part.split(','):
        try:
            message_ids.append(int(mid_str.strip()))
        except ValueError:
            pass
    chat_id = call.from_user.id
    for mid in message_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass
    if call.message.message_id not in message_ids:
        try:
            await call.message.delete()
        except Exception:
            pass
    kb_row = DB.Text.select(where=DB.Text.category == 'knowledge_base')
    kb = kb_row.data if kb_row else {}
    new_menu = await bot.send_message(
        chat_id=chat_id,
        text='<b>📚 База знаний</b>\n\n<i>Выберите интересующую тему:</i>',
        reply_markup=kb_client_group.build_kb_menu(kb, 'pm_kb_', 'client_back_menu'))
    DB.User.update(mark=call.from_user.id, menu_id=new_menu.message_id)
    await call.answer()



async def pm_calendar(call: CallbackQuery):
    """Show event calendar in PM. Reuses the text from group_calendar scenario,
    but replaces back-to-group navigation with PM back."""
    try:
        await call.message.delete()
    except TelegramAPIError:
        ...
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    from bot.utils.dynamic_kb import get_screen_kb

    # Take only URL buttons from group_calendar scenario; drop any group-callback
    # buttons (like "🔙 Меню → group_main_menu") and add our PM back instead.
    pm_rows = []
    src_kb = get_screen_kb('group_calendar')
    if src_kb is not None:
        for row in (src_kb.inline_keyboard or []):
            keep = [btn for btn in row if btn.url]
            if keep:
                pm_rows.append(keep)
    if not pm_rows:
        pm_rows.append([InlineKeyboardButton(
            text='Открыть календарь',
            url='https://docs.google.com/spreadsheets/d/1zMg4sJlUUD2I-SPEUc7MRC6rRkbZHWpBju0vGlzNeIo/edit?gid=0#gid=0',
        )])
    pm_rows.append([InlineKeyboardButton(text='🔙 Меню', callback_data='client_back_menu')])
    calendar_kb = InlineKeyboardMarkup(inline_keyboard=pm_rows)

    new_menu = await send_screen_message(
        bot, call.from_user.id, 'group_calendar',
        message_key='main_text',
        text=get_text('group_calendar', 'main_text')
             or '<b>📅 Календарь</b>\n\nПерейдите по ссылке для просмотра актуального календаря.',
        reply_markup=calendar_kb)
    DB.User.update(mark=call.from_user.id, menu_id=new_menu.message_id)
    await call.answer()


async def pm_socials(call: CallbackQuery):
    """Show social networks in PM."""
    try:
        await call.message.delete()
    except TelegramAPIError:
        ...
    from bot.utils.dynamic_kb import get_screen_kb
    socials_menu = get_screen_kb('socials_page') or kb_client_group.create_inline([
        ['@WinlinePartners', 'url', 'https://t.me/WinlinePartners'],
        ['🔙 Меню', 'call', 'client_back_menu'],
    ], 1)
    new_menu = await send_screen_message(
        bot, call.from_user.id, 'socials_page',
        message_key='socials_text',
        text=get_text('socials_page', 'socials_text') or '<b>📱 Наши соц. сети</b>\n\nСкорее подписывайся на наш официальный канал в Telegram, чтобы быть в курсе новостей 👇',
        reply_markup=socials_menu)
    DB.User.update(mark=call.from_user.id, menu_id=new_menu.message_id)
    await call.answer()


async def pm_promo(call: CallbackQuery):
    """Show promo in PM."""
    try:
        await call.message.delete()
    except TelegramAPIError:
        ...
    promo_fallback = (
        '<b>🎨 Актуальные крео и лендинги</b>\n\n'
        '🌐 <b>Список актуальных лендингов</b>\n\n'
        'Здесь представлены лендинги, на которые вы можете вести трафик.\n\n'
        'Для получения ссылки с вашими партнерскими метками, нужно зайти в карточку оффера в раздел "Генератор ссылок".\n\n'
        '📋 <b>Регистрация:</b>\n'
        '• <a href="https://winline.ru/registration/">Страница регистрации</a>\n'
        '• <a href="https://winline.ru/registration?utm=cyber">Страница регистрации CYBER</a>\n'
        '• <a href="https://winline.ru/freebet/">Фрибет 3 000 руб.</a>\n'
        '• <a href="https://winline.ru/programloyalty">Новая Программа Лояльности</a>\n\n'
        '🎰 <b>Лотереи и игры:</b>\n'
        '• <a href="https://winline.ru/lottery">Лотереи</a>\n'
        '• <a href="https://winline.ru/games/lottery">Лотереи (Регистрация)</a>\n'
        '• <a href="https://winline.ru/games">Быстрые игры</a>\n\n'
        '📱 <b>Мобильные:</b>\n'
        '• <a href="https://m.winline.ru/auth/registration">Мобильная страница регистрации</a>\n'
        '• <a href="https://m.winline.ru/registration?v=1">Мобильная регистрация (фрибет)</a>\n'
        '• <a href="https://m.winline.ru/registration?v=4">Регистрация без лого 1</a>\n'
        '• <a href="https://m.winline.ru/registration?v=5">Регистрация без лого 2</a>\n'
        '• <a href="https://m.winline.ru/registration?v=6">Регистрация без лого 3</a>\n\n'
        '📺 <b>Видеотрансляции:</b>\n'
        '• <a href="https://winline.ru/video/">Все трансляции</a>\n'
        '• <a href="https://winline.ru/video/football/">Футбол</a>\n'
        '• <a href="https://winline.ru/video/tennis/">Теннис</a>\n'
        '• <a href="https://winline.ru/video/xokkej/">Хоккей</a>\n'
        '• <a href="https://winline.ru/video/basketball/">Баскетбол</a>\n'
        '• <a href="https://winline.ru/video/rpl/">РПЛ</a>\n\n'
        '———————————————\n\n'
        '<b>Актуальные промо-материалы</b>\n\n'
        'Перейдите по ссылке для просмотра актуальных баннеров и креативов 👇'
    )
    promo_text = get_text('promo_page', 'promo_text') or promo_fallback
    from bot.utils.dynamic_kb import get_screen_kb
    promo_kb = get_screen_kb('promo_page') or kb_client_group.pm_promo_menu
    new_menu = await send_screen_message(
        bot, call.from_user.id, 'promo_page',
        text=promo_text,
        reply_markup=promo_kb)
    DB.User.update(mark=call.from_user.id, menu_id=new_menu.message_id)
    await call.answer()


def _sync_issue_event_code(user_id, label='', kind='merch'):
    """Atomically issue an event code with limit protection.

    Uses a MySQL advisory lock (GET_LOCK) to serialize concurrent requests
    so the (count → check limit → insert) sequence is race-free.

    Counts only ACTIVE codes toward the limit (cancelled codes free slots).
    Guarantees one active code per user.

    Returns a tuple (status, code):
      ('existing', 'EVT-xxx')     — user already had an active code
      ('created',  'EVT-xxx')     — new code issued
      ('limit_reached', None)     — all slots taken
      ('error', None)             — DB/lock failure
    """
    _db_cfg = {
        'host': os.getenv('MYSQL_HOST', ''), 'port': int(os.getenv('MYSQL_PORT', 3306)),
        'user': os.getenv('MYSQL_USER', ''), 'password': os.getenv('MYSQL_PASSWORD', ''),
        'database': os.getenv('MYSQL_DATABASE', ''),
    }
    conn = None
    try:
        conn = mysql.connector.connect(**_db_cfg)
        cur = conn.cursor(dictionary=True)

        # Acquire advisory lock (max wait 5s). Serializes concurrent issuers.
        cur.execute("SELECT GET_LOCK('wl_event_code_issue', 5) AS ok")
        got_lock = cur.fetchone()
        if not got_lock or not got_lock['ok']:
            return ('error', None)

        try:
            # 1. Existing code for this user of the SAME kind (один юзер — один QR per kind).
            # merch и raffle_only коды независимы: «Работаю» юзер не должен получить
            # старый merch-код, и наоборот.
            cur.execute(
                "SELECT c.code FROM wl_event_codes c "
                "LEFT JOIN wl_event_code_meta m ON m.code = c.code "
                "WHERE c.user_id = %s AND COALESCE(m.kind, 'merch') = %s "
                "ORDER BY c.id DESC LIMIT 1",
                (user_id, kind),
            )
            existing = cur.fetchone()
            if existing:
                return ('existing', existing['code'])

            # 2. Read limit from event_settings
            cur.execute("SELECT data FROM texts WHERE category = 'event_settings' LIMIT 1")
            row = cur.fetchone()
            code_limit = 0
            if row:
                _data = row['data']
                _s = json_mod.loads(_data) if isinstance(_data, str) else _data
                code_limit = int(_s.get('code_limit', 0))

            # 3. Count only ACTIVE codes — cancelled/used codes free slots back
            if code_limit > 0:
                cur.execute("SELECT COUNT(*) AS cnt FROM wl_event_codes WHERE status = 'active'")
                total = cur.fetchone()['cnt']
                if total >= code_limit:
                    return ('limit_reached', None)

            # 4. Generate and insert
            event_code = 'EVT-' + _secrets.token_hex(4).upper()
            cur.execute(
                'INSERT INTO wl_event_codes (code, label, user_id, status) VALUES (%s, %s, %s, %s)',
                (event_code, label or str(user_id), user_id, 'active'),
            )
            # Side-table metadata (env disallows ALTER on wl_event_codes).
            try:
                cur.execute(
                    "INSERT INTO wl_event_code_meta (code, kind) VALUES (%s, %s) "
                    "ON DUPLICATE KEY UPDATE kind=VALUES(kind)",
                    (event_code, kind),
                )
            except Exception as _e:
                logger.warning(f'[event_code] meta insert skipped: {_e}')
            conn.commit()
            return ('created', event_code)
        finally:
            try:
                cur.execute("SELECT RELEASE_LOCK('wl_event_code_issue')")
                cur.fetchone()
            except Exception:
                pass
    except Exception as e:
        logger.error(f'[event_code] issue error: {e}')
        return ('error', None)
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


async def _warmup_qr_card(event_code: str) -> None:
    """Fire-and-forget GET to the admin panel's qr-card endpoint right after a
    new code is issued. The admin process renders the card and the HTTP layer
    caches the PNG (Cache-Control public, max-age=300), so when the user a
    second later actually requests the QR the heavy sharp+QRCode pipeline is
    already done. Cuts the user-perceived first-show latency from ~1.5s to
    ~300ms in the typical anketa → QR flow.

    Never raises — warm-up is opportunistic. If admin is unreachable, the
    on-demand path in _send_event_qr just does the work as usual.
    """
    base = (config.admin_panel_webhook or '').rstrip('/').rsplit('/api/', 1)[0]
    if not base:
        base = 'https://winlinepartners.ru'
    url = f'{base}/api/events/codes/{event_code}/qr-card'
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(url) as r:
                # Drain body so the HTTP response is fully cached upstream;
                # we don't need the bytes here.
                await r.read()
    except Exception as e:
        logger.debug(f'[qr-warmup] {event_code}: {e}')


async def issue_event_code(user_id, label='', kind='merch'):
    """Async wrapper for atomic event code issuing.

    On successful new-code issuance triggers a background warm-up of the
    qr-card endpoint — by the time the bot actually wants to send the QR,
    the heavy image pipeline on the admin panel is already done.
    """
    status, event_code = await asyncio.to_thread(_sync_issue_event_code, user_id, label, kind)
    if status == 'created' and event_code:
        asyncio.create_task(_warmup_qr_card(event_code))
    return status, event_code


def _sync_add_user_tag(user_id: int, tag: str) -> None:
    """Append a tag to wl_admin_user_tags. Idempotent — INSERT IGNORE."""
    _cfg = {
        'host': os.getenv('MYSQL_HOST', ''), 'port': int(os.getenv('MYSQL_PORT', 3306)),
        'user': os.getenv('MYSQL_USER', ''), 'password': os.getenv('MYSQL_PASSWORD', ''),
        'database': os.getenv('MYSQL_DATABASE', ''),
    }
    c = None
    try:
        c = mysql.connector.connect(**_cfg)
        cur = c.cursor()
        cur.execute(
            'INSERT IGNORE INTO wl_admin_user_tags (user_id, tag) VALUES (%s, %s)',
            (user_id, tag),
        )
        c.commit()
    finally:
        try:
            if c: c.close()
        except Exception:
            pass


async def add_user_tag(user_id: int, tag: str) -> None:
    """Async, non-blocking. Use as `asyncio.create_task(add_user_tag(...))`."""
    try:
        await asyncio.to_thread(_sync_add_user_tag, user_id, tag)
    except Exception as e:
        logger.warning(f'[user_tag] add {tag!r} for {user_id} failed: {e}')


# Теги мероприятия по датам. Применяются ТОЛЬКО если сегодня одна из этих
# дат (МСК). В остальные дни сценарий 3 проходится молча, без тегов.
EVENT_TAGS_BY_DATE = {
    '2026-05-26': 'MAC 26',
    '2026-05-27': 'MAC 27',
}


def get_today_event_tag() -> Optional[str]:
    """Вернуть тег для сегодняшнего дня или None если сегодня не ивент."""
    msk = datetime.now(timezone(timedelta(hours=3))).date().isoformat()
    return EVENT_TAGS_BY_DATE.get(msk)


# Backward-compat — оставляем константу-импорт, чтобы старые места не падали.
EVENT_TAG = 'MAC 26'


async def _pregenerate_for_user(user_id: int) -> None:
    """Полный pre-flight для merch-QR: выдаём код + рендерим карточку в кэш.

    Запускается, как только юзер открывает deep-link мероприятия — пока
    он смотрит интро и заполняет анкету (~30-60 сек), бот успевает всё
    приготовить. В _send_event_qr остаётся только TG-upload.

    Безопасна к ошибкам — если что-то отвалится, _send_event_qr сделает
    on-demand рендер как обычно.
    """
    from bot.utils.qr_card import pregenerate_qr_card  # type: ignore
    try:
        user_data = DB.User.select(user_id)
        label = user_data.full_name if user_data else str(user_id)
        status, code = await issue_event_code(user_id, label, 'merch')
        if not code:
            return
        caption = _get_qr_caption() or ''
        await pregenerate_qr_card(code, caption)
    except Exception as e:
        logger.warning(f'[qr-pregenerate] user={user_id}: {e}')


def _sync_get_user_merch_code(user_id):
    """Return user's existing merch event_code (or None). Read-only, no allocation."""
    _db_cfg = {
        'host': os.getenv('MYSQL_HOST', ''), 'port': int(os.getenv('MYSQL_PORT', 3306)),
        'user': os.getenv('MYSQL_USER', ''), 'password': os.getenv('MYSQL_PASSWORD', ''),
        'database': os.getenv('MYSQL_DATABASE', ''),
    }
    conn = None
    try:
        conn = mysql.connector.connect(**_db_cfg)
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT c.code FROM wl_event_codes c "
            "LEFT JOIN wl_event_code_meta m ON m.code = c.code "
            "WHERE c.user_id = %s AND COALESCE(m.kind, 'merch') = 'merch' "
            "ORDER BY c.id DESC LIMIT 1",
            (user_id,),
        )
        row = cur.fetchone()
        return row['code'] if row else None
    except Exception as e:
        logger.warning(f'[event_code] lookup error: {e}')
        return None
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


async def get_user_merch_code(user_id):
    return await asyncio.to_thread(_sync_get_user_merch_code, user_id)


# Backward-compat shim for existing callers that expect `code | None`
async def get_or_create_event_code(user_id, full_name=''):
    status, code = await issue_event_code(user_id, full_name)
    return code  # None if limit reached / error


async def at_event(call: CallbackQuery):
    settings = get_settings_cached()
    if not settings.event_starts:
        return await call.answer(
            get_text('event_flow', 'no_event') or 'Сейчас нет активных мероприятий',
            show_alert=True,
        )

    user_id = call.from_user.id

    # Atomic: issue or get existing code (race-free, counts only active)
    status, event_code = await issue_event_code(user_id, call.from_user.full_name)

    # Limit reached — edit the message to a dedicated "sold out" screen
    if status == 'limit_reached':
        try:
            await call.message.delete()
        except TelegramAPIError:
            ...
        sold_out_text = get_text('event_flow', 'limit_reached') or (
            '<b>😔 К сожалению, все призы уже разобраны</b>\n\n'
            'Спасибо за интерес к нашему мероприятию! '
            'Следите за анонсами — скоро будут новые акции.'
        )
        from bot.utils.dynamic_kb import get_screen_kb as _gsk
        event_kb = _gsk('event_flow') or kb_client_menu.back_menu
        new_menu = await bot.send_message(
            chat_id=user_id,
            text=sold_out_text,
            reply_markup=event_kb,
        )
        DB.User.update(mark=user_id, menu_id=new_menu.message_id)
        return await call.answer()

    if status == 'error' or not event_code:
        return await call.answer(
            '⚠️ Временная ошибка, попробуйте ещё раз через пару секунд',
            show_alert=True,
        )

    # Download QR card from panel server (with local fallback)
    qr_card_url = f'https://winlinepartners.ru/api/events/codes/{event_code}/qr-card'
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as _sess:
            async with _sess.get(qr_card_url) as _resp:
                if _resp.status == 200:
                    _card_data = await _resp.read()
                    photo = BufferedInputFile(_card_data, filename=f'qr_{user_id}.png')
                else:
                    raise Exception(f'HTTP {_resp.status}')
    except Exception as _e:
        logger.warning(f'[QR-CARD at_event] Fallback: {_e}')
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
        qr.add_data(event_code)
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white')
        buf = BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        photo = BufferedInputFile(buf.read(), filename=f'qr_{user_id}.png')

    try:
        await call.message.delete()
    except TelegramAPIError:
        ...
    qr_caption = get_text('event_flow', 'qr_caption') or '<b>Вот ваш QR для получения подарка!</b>'
    from bot.utils.dynamic_kb import get_screen_kb as _gsk2
    event_kb = _gsk2('event_flow') or kb_client_menu.back_menu
    new_menu = await bot.send_photo(
        chat_id=user_id,
        photo=photo,
        caption=f'{qr_caption}\n\nКод: <code>{event_code}</code>',
        reply_markup=event_kb,
    )
    DB.User.update(mark=user_id, menu_id=new_menu.message_id)
    await call.answer()

async def logout(call: CallbackQuery):
    """Logout: delete auth data and show start menu"""
    DB.UserAuth.remove(call.from_user.id)

    await call.message.edit_caption(
        caption='<b>Вы вышли из аккаунта.\n\n'
                'Привет! Этот бот поможет тебе зарегистрироваться в качестве партнёра, '
                'предоставит быстрый доступ к порталу WINLINE PARTNERS, даст возможность получать '
                'актуальные новости и предложения, а также участвовать в мероприятиях!</b>',
        reply_markup=kb_client_menu.get_start_menu())
    await call.answer('Вы вышли из аккаунта')


async def get_file_id(message: Message):
    """Temp handler: admin sends photo in PM → bot replies with file_id."""
    if message.photo:
        file_id = message.photo[-1].file_id
        await message.reply(f'<b>Photo file_id:</b>\n<code>{file_id}</code>')


async def reg_help(call: CallbackQuery):
    await call.answer('🔧 Функционал в разработке', show_alert=True)


# ==================== Сценарий 3: Мероприятие (deep link + анкета) ====================


# Module-level TTL cache for qr_caption_text. Был холодный путь: каждый
# показ QR открывал свежий MySQL connect к удалённой db.buy-bot.ru —
# auth + query + close ≈ 400 мс, что давало ~55% всего времени _send_event_qr
# (см. [QR-TIMING] лог). Caption меняется в админке от силы раз в день,
# 60 секунд TTL абсолютно безопасны и снимают всю эту задержку.
_QR_CAPTION_CACHE: dict = {'value': None, 'expires_at': 0.0}
_QR_CAPTION_TTL_SEC = 60


def _get_qr_caption() -> str:
    """Get QR caption text from event_settings in DB, with 60s in-memory cache."""
    import time as _t
    now = _t.monotonic()
    if _QR_CAPTION_CACHE['value'] is not None and now < _QR_CAPTION_CACHE['expires_at']:
        return _QR_CAPTION_CACHE['value']
    try:
        _db_cfg = {
            'host': os.getenv('MYSQL_HOST', ''), 'port': int(os.getenv('MYSQL_PORT', 3306)),
            'user': os.getenv('MYSQL_USER', ''), 'password': os.getenv('MYSQL_PASSWORD', ''),
            'database': os.getenv('MYSQL_DATABASE', ''),
        }
        conn = mysql.connector.connect(**_db_cfg)
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT data FROM texts WHERE category = 'event_settings' LIMIT 1")
        row = cur.fetchone()
        conn.close()
        if row:
            _data = row['data']
            _s = json_mod.loads(_data) if isinstance(_data, str) else _data
            caption = _s.get('qr_caption_text', '') or ''
            _QR_CAPTION_CACHE['value'] = caption
            _QR_CAPTION_CACHE['expires_at'] = now + _QR_CAPTION_TTL_SEC
            return caption
    except Exception as e:
        logger.debug(f"Suppressed: {e}")
    # Кэшируем даже пустой ответ — чтобы при ошибках БД не лезть туда снова.
    _QR_CAPTION_CACHE['value'] = ''
    _QR_CAPTION_CACHE['expires_at'] = now + _QR_CAPTION_TTL_SEC
    return ''

async def _generate_event_qr(user_id: int) -> str:
    """Generate QR for event using wl_event_codes, return path or None if limit reached."""
    user_data = DB.User.select(user_id)
    label = user_data.full_name if user_data else str(user_id)

    status, event_code = await issue_event_code(user_id, label)
    if status in ('limit_reached', 'error') or not event_code:
        return None

    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
    qr.add_data(event_code)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    qr_path = f"files/{user_id}_evt.png"
    img.save(qr_path)
    return qr_path

async def _send_event_qr(user_id: int, is_partner: bool = False) -> Message:
    """Send QR photo with code in caption."""
    qr_path = await _generate_event_qr(user_id)
    if qr_path is None:
        # Limit reached or error
        sold_out_text = get_text('event_flow', 'limit_reached') or (
            '<b>😔 К сожалению, все призы уже разобраны</b>\n\n'
            'Спасибо за интерес к нашему мероприятию! '
            'Следите за анонсами — скоро будут новые акции.'
        )
        from bot.utils.dynamic_kb import get_screen_kb as _gsk
        event_kb = _gsk('event_flow') or kb_client_menu.back_menu
        new_menu = await bot.send_message(
            chat_id=user_id,
            text=sold_out_text,
            reply_markup=event_kb,
        )
        DB.User.update(mark=user_id, menu_id=new_menu.message_id)
        return new_menu

    # Get event code (reuse helper)
    event_code = await get_or_create_event_code(user_id) or ''

    # Без клавиатуры — иначе при back/menu-кликах QR удалится из чата.
    # Промо регистрации придёт отдельным сообщением после скана QR хостес.
    reply_markup = None

    # Three-tier fast path:
    #   1) file_id из storage-чата (мгновенно, без upload файла) — лучший случай
    #   2) PNG bytes из memory cache (нужен upload, но без рендера)
    #   3) on-demand render + upload (fallback, как было раньше)
    import time as _t
    from bot.utils.qr_card import generate_qr_card_bytes, pop_qr_card
    from bot.utils.qr_storage import get_cached_file_id
    from aiogram.types import BufferedInputFile

    _t0 = _t.monotonic()
    _from_cache = 'miss'
    photo_payload = None
    _size_kb = -1
    _render_ms = -1

    # Tier 1: file_id
    try:
        file_id = await get_cached_file_id(event_code)
        if file_id:
            photo_payload = file_id  # aiogram принимает строку как file_id
            _from_cache = 'file_id'
    except Exception as _e:
        logger.debug(f'[QR-CARD] file_id lookup failed: {_e}')

    _t1 = _t.monotonic()
    # Tier 2 + 3: bytes (cache или on-demand)
    if photo_payload is None:
        try:
            card_bytes = pop_qr_card(event_code)
            if card_bytes is not None:
                _from_cache = 'bytes'
            else:
                qr_caption_overlay = _get_qr_caption() or ''
                card_bytes = await generate_qr_card_bytes(event_code, qr_caption_overlay)
                _from_cache = 'on_demand'
            _t2 = _t.monotonic()
            photo_payload = BufferedInputFile(card_bytes, filename=f'{event_code}.png')
            _render_ms = int((_t2 - _t1) * 1000)
            _size_kb = len(card_bytes) // 1024
        except Exception as _e:
            # Last-ditch fallback: bare QR via FSInputFile, matches previous behavior.
            logger.warning(f'[QR-CARD] local render failed, falling back to bare QR: {_e}')
            qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
            qr.add_data(event_code)
            qr.make(fit=True)
            img = qr.make_image(fill_color='black', back_color='white')
            qr_path = f"files/{user_id}_card.png"
            img.save(qr_path)
            photo_payload = FSInputFile(qr_path)
            _from_cache = 'fallback_bare'
            _render_ms = -1
            _size_kb = -1

    caption = f'<b>Вот ваш QR для получения подарка!</b>'
    if event_code:
        caption += f'\n\nКод: <code>{event_code}</code>'

    _t3 = _t.monotonic()
    new_menu = await bot.send_photo(
        chat_id=user_id,
        photo=photo_payload,
        caption=caption,
        reply_markup=reply_markup,
    )
    _t4 = _t.monotonic()
    logger.info(
        f'[QR-TIMING] user={user_id} code={event_code} '
        f'cache_hit={_from_cache} '
        f'lookup_or_render={int((_t1-_t0)*1000)}ms '
        f'render={_render_ms}ms ({_size_kb}KB) '
        f'tg_send={int((_t4-_t3)*1000)}ms '
        f'total={int((_t4-_t0)*1000)}ms'
    )
    # IMPORTANT: do NOT store the merch-QR message id as menu_id. Future
    # menu-replacements (start, back-to-menu, etc.) wipe out whatever
    # menu_id points to — and the QR with the partner's code must stay
    # in the chat permanently. Setting menu_id=None makes the next menu
    # come up as a fresh message instead.
    DB.User.update(mark=user_id, menu_id=None)
    return new_menu

async def start_event(message: Message, state: FSMContext):
    """Deep link handler: /start event"""
    user_id = message.from_user.id
    user_data = DB.User.select(user_id)

    # Create user if new
    if not user_data:
        await bot.send_message(user_id, '👋')
        wait_msg = await bot.send_message(user_id, '⌛️ Загрузка...')
        try:
            thread_id = await telegram.topic_manager.create_user_topic(message.from_user.first_name)
        except TelegramRetryAfter:
            await wait_msg.edit_text('<b>😥 Бот перегружен, повторите через минуту.</b>')
            return
        DB.User.add(user_id, message.from_user.full_name, message.from_user.username, thread_id)
        if config.admin_filter.is_system(user_id):
            config.admin_filter.add_admin(user_id, 0, admin_access.full_admin_access)
        await wait_msg.delete()

        count_users = len(DB.User.select(all_scalars=True))
        link_user = generate_user_hlink(user_id=user_id, text_link=message.from_user.full_name)
        registration_alert = (
            f'<b>🔔 Зарегистрировался пользователь №</b><code>{count_users}</code><b>:</b>\n\n'
            f'<b>ID пользователя:</b> <code>{user_id}</code>\n'
            f'<b>Отображаемое имя:</b> {link_user}\n'
            f'<b>Никнейм</b>: {"@" + message.from_user.username if message.from_user.username else "<code>отсутствует</code>"}'
        )
        await admin_notifications.registration_notification(registration_alert)
        user_data = DB.User.select(user_id)

    # If authorized partner → QR immediately
    auth_data = DB.UserAuth.select(user_id)
    if auth_data:
        await telegram.delete_message(chat_id=user_id, message_id=user_data.menu_id)
        await _send_event_qr(user_id, is_partner=True)
        return

    # Not authorized → start anketa
    await telegram.delete_message(chat_id=user_id, message_id=user_data.menu_id)
    await _start_event_anketa(message, user_id, state)


async def _start_event_anketa(message: Message, user_id: int, state: FSMContext):
    """Start anketa using scenario flow (scenario:5 screens)."""
    from bot.utils.dynamic_kb import find_first_anketa_screen, reload as reload_scenarios
    reload_scenarios()  # fresh data

    first_screen_id = find_first_anketa_screen()
    if not first_screen_id:
        # No anketa screens configured → fallback to old DB questions
        await _start_event_anketa_legacy(message, user_id, state)
        return

    await state.set_state(FsmEventAnketa.answering)
    await state.update_data(
        anketa_answers={},  # answerKey → answer_text
        anketa_screen_path=[],  # list of screen_ids visited (for sheets order)
    )
    await _send_anketa_screen(user_id, first_screen_id, state)


async def _send_anketa_screen(user_id: int, screen_id: str, state: FSMContext):
    """Send an anketa flow screen to the user."""
    from bot.utils.dynamic_kb import get_screen, get_screen_kb, get_screen_text, reload as reload_scenarios
    from bot.utils.scenario_texts import send_screen_message

    screen = get_screen(screen_id)
    if not screen or screen.get('scenario') != 5:
        # Try reload in case new screens were added
        reload_scenarios()
        screen = get_screen(screen_id)
    if not screen or screen.get('scenario') != 5:
        logger.error(f'[anketa] Screen not found or not scenario:5: {screen_id}')
        await _anketa_finish(user_id, state)
        return

    text = get_screen_text(screen_id)
    if not text:
        text = f'<b>{screen.get("title", "Вопрос")}</b>'

    step_type = screen.get('stepType', 'choice')
    kb = None

    if step_type == 'choice':
        # Use screen buttons — store mapping in FSM state to keep callback_data short
        buttons_def = screen.get('buttons', {})
        order = buttons_def.get('_order', [])
        buttons = []
        btn_map = {}  # index -> {key, target, screen_id}
        for i, key in enumerate(order):
            btn = buttons_def.get(key)
            if not btn:
                continue
            label = btn.get('label', '???')
            target = btn.get('targetScreen', '')
            btn_map[str(i)] = {'key': key, 'target': target, 'screen_id': screen_id}
            buttons.append([label, 'call', f'af:{i}'])
        if buttons:
            from bot.utils.telegram import create_inline
            kb = create_inline(buttons, 1)
            await state.update_data(anketa_btn_map=btn_map)

    elif step_type == 'subscription_check':
        # Show check_text message with "Подписка есть!" button
        messages = screen.get('messages', {})
        check_msg = messages.get('check_text', {})
        if check_msg and check_msg.get('text'):
            text = check_msg['text']
        next_screen = screen.get('nextScreen', '')
        from bot.utils.telegram import create_inline
        # Store sub check info in FSM state
        await state.update_data(anketa_sub_info={'screen_id': screen_id, 'next_screen': next_screen})
        kb = create_inline([
            [screen.get('buttons', {}).get('btn_check_sub', {}).get('label', 'Подписка есть!'),
             'call', 'as:0']
        ], 1)

    elif step_type == 'finish':
        # Show final text then send QR
        messages = screen.get('messages', {})
        final_msg = messages.get('final_text', {})
        if final_msg and final_msg.get('text'):
            text = final_msg['text']
        menu = await send_screen_message(bot, user_id, screen_id, text, reply_markup=None)
        DB.User.update(mark=user_id, menu_id=menu.message_id)
        # Add to screen path then finish
        data = await state.get_data()
        screen_path = data.get('anketa_screen_path', [])
        if screen_id not in screen_path:
            screen_path.append(screen_id)
        await state.update_data(anketa_screen_path=screen_path)
        await _anketa_finish(user_id, state)
        return

    # Send the message
    menu = await send_screen_message(bot, user_id, screen_id, text, reply_markup=kb)
    DB.User.update(mark=user_id, menu_id=menu.message_id)

    # Save current screen in state
    await state.update_data(
        anketa_current_screen=screen_id,
        anketa_menu_message=menu,
    )


async def _anketa_finish(user_id: int, state: FSMContext):
    """Finish anketa: send QR ASAP, write Google Sheets in background.

    Ранее: ждали Google Sheets (1-3 сек sync gspread) ДО отправки QR.
    После клика «Подписка есть» юзер видел QR только через 5-6 секунд.
    Теперь: Sheets-запись фоном через asyncio.create_task, QR улетает сразу.
    Ошибки записи логируются, но не блокируют флоу.
    """
    import time as _t
    _t_start = _t.monotonic()

    data = await state.get_data()
    answers = data.get('anketa_answers', {})
    screen_path = data.get('anketa_screen_path', [])

    if answers:
        user = DB.User.select(user_id)
        full_name = user.full_name if user else ''
        username = user.username if user else ''

        async def _bg_sheets():
            try:
                await new_answers(
                    user_id=str(user_id),
                    full_name=full_name,
                    username=username,
                    answers=answers,
                )
            except Exception as e:
                logger.error(f'[anketa-flow] Ошибка отправки в Google Sheets: {e}')
        asyncio.create_task(_bg_sheets())

    # Сохраняем флаг до очистки state — он мог быть выставлен при входе
    # в анкету через event_v2_want_merch (партнёр уже получил раффл-билет
    # и пришёл за мерчем, второй раз про раффл писать не нужно).
    flow_data = await state.get_data()
    skip_promo = bool(flow_data.get('skip_raffle_promo'))
    await state.clear()

    _t_pre_qr = _t.monotonic()
    await _send_event_qr(user_id, is_partner=False)
    _t_post_qr = _t.monotonic()

    if not skip_promo:
        # UX-пауза: даём юзеру 3 секунды рассмотреть QR-карточку, прежде чем
        # выскочит следующее сообщение (раффл-промо) и сдвинет её наверх.
        await asyncio.sleep(3)
        # И отправляем промо регистрации (раффл мячей).
        # Раньше оно слалось только после фактического сканирования QR хостесом
        # на стенде, но юзеру нужно видеть оффер сразу, чтобы успеть поучаствовать.
        await _send_event_registration_promo(user_id)
    _t_done = _t.monotonic()

    logger.info(
        f'[ANKETA-FINISH] user={user_id} '
        f'pre_qr={int((_t_pre_qr - _t_start) * 1000)}ms '
        f'qr_send={int((_t_post_qr - _t_pre_qr) * 1000)}ms '
        f'promo={int((_t_done - _t_post_qr) * 1000)}ms '
        f'total={int((_t_done - _t_start) * 1000)}ms'
    )


async def _send_event_registration_promo(user_id: int):
    """Отправляет экран event_registration_promo (раффл-промо)."""
    from bot.utils.dynamic_kb import get_screen_kb
    text = get_text('event_registration_promo', 'promo') or (
        '<b>Хочешь выиграть 1 из 10 мячей, подписанным легендой '
        'футбола и амбассадором WINLINE, Роналдиньо?</b>\n\n'
        'Пройди регистрацию на сайте WINLINE PARTNERS'
    )
    kb = get_screen_kb('event_registration_promo')
    try:
        new_msg = await send_screen_message(
            bot, user_id, 'event_registration_promo',
            text=text, reply_markup=kb, message_key='promo',
        )
        try:
            DB.User.update(mark=user_id, menu_id=new_msg.message_id)
        except Exception:
            pass
    except Exception as e:
        logger.warning(f'[event_registration_promo] failed for {user_id}: {e}')


async def _start_event_anketa_legacy(message: Message, user_id: int, state: FSMContext):
    """Legacy: load questions from DB (flat list) when no scenario:5 screens exist."""
    questions = DB.EventQuestion.select(
        where=(DB.EventQuestion.is_active == True),
        all_scalars=True,
    )
    if not questions:
        await _send_event_qr(user_id, is_partner=False)
        await _send_event_registration_promo(user_id)
        return

    questions = sorted(questions, key=lambda q: q.order)
    questions_data = [
        {'id': q.id, 'text': q.question_text, 'type': q.question_type, 'options': q.options}
        for q in questions
    ]

    await state.set_state(FsmEventAnketa.answering)
    await state.update_data(
        anketa_questions=questions_data,
        anketa_index=0,
        anketa_legacy=True,
    )
    await _send_anketa_question_legacy(user_id, questions_data[0], state)


async def _send_anketa_question_legacy(user_id: int, question: dict, state: FSMContext):
    """Legacy: send a flat anketa question."""
    text = f'<b>{question["text"]}</b>'
    if question['type'] == 'choice' and question.get('options'):
        buttons = [
            [opt, 'call', f'anketa_choice:{i}']
            for i, opt in enumerate(question['options'])
        ]
        from bot.utils.telegram import create_inline
        kb = create_inline(buttons, 1)
        menu = await bot.send_message(user_id, text, reply_markup=kb)
    else:
        menu = await bot.send_message(user_id, text)
    DB.User.update(mark=user_id, menu_id=menu.message_id)
    await state.update_data(anketa_menu_message=menu)


async def _anketa_next_or_finish_legacy(user_id: int, state: FSMContext):
    """Legacy: move to next question or finish."""
    data = await state.get_data()
    questions = data['anketa_questions']
    index = data['anketa_index'] + 1

    if index >= len(questions):
        try:
            answers = DB.EventAnswer.select(
                where=(DB.EventAnswer.user_id == user_id),
                all_scalars=True,
            )
            answer_map = {}
            for a in (answers or []):
                answer_map[a.question_id] = a.answer_text

            qa_pairs = []
            for q in questions:
                qa_pairs.append({
                    'question': q['text'],
                    'answer': answer_map.get(q['id'], ''),
                })

            user = DB.User.select(user_id)
            full_name = user.full_name if user else ''
            username = user.username if user else ''

            await new_answers(
                user_id=str(user_id),
                full_name=full_name,
                username=username,
                questions_answers=qa_pairs,
            )
        except Exception as e:
            print(f'[anketa] Ошибка отправки в Google Sheets: {e}')

        flow_data = await state.get_data()
        skip_promo = bool(flow_data.get('skip_raffle_promo'))
        await state.clear()
        await _send_event_qr(user_id, is_partner=False)
        if not skip_promo:
            await _send_event_registration_promo(user_id)
        return

    await state.update_data(anketa_index=index)
    await _send_anketa_question_legacy(user_id, questions[index], state)


async def process_anketa_text(message: Message, state: FSMContext):
    """Handle text answer in event anketa (both flow and legacy)."""
    try:
        await message.delete()
    except TelegramAPIError:
        ...
    data = await state.get_data()

    # Legacy mode
    if data.get('anketa_legacy'):
        questions = data['anketa_questions']
        index = data['anketa_index']
        question = questions[index]
        DB.EventAnswer.add(
            user_id=message.from_user.id,
            question_id=question['id'],
            answer_text=message.text,
        )
        menu_msg = data.get('anketa_menu_message')
        if menu_msg:
            try:
                await menu_msg.delete()
            except TelegramAPIError:
                ...
        await _anketa_next_or_finish_legacy(message.from_user.id, state)
        return

    # Flow mode: text_input screen
    from bot.utils.dynamic_kb import get_screen
    current_screen_id = data.get('anketa_current_screen')
    if not current_screen_id:
        await _anketa_finish(message.from_user.id, state)
        return

    screen = get_screen(current_screen_id)
    answer_key = screen.get('answerKey', '') if screen else ''

    # Save answer in state
    answers = data.get('anketa_answers', {})
    if answer_key:
        answers[answer_key] = message.text
    screen_path = data.get('anketa_screen_path', [])
    if current_screen_id not in screen_path:
        screen_path.append(current_screen_id)

    await state.update_data(anketa_answers=answers, anketa_screen_path=screen_path)

    # Delete previous message
    menu_msg = data.get('anketa_menu_message')
    if menu_msg:
        try:
            await menu_msg.delete()
        except TelegramAPIError:
            ...

    # Navigate to nextScreen
    next_screen = screen.get('nextScreen', '') if screen else ''
    if next_screen:
        await _send_anketa_screen(message.from_user.id, next_screen, state)
    else:
        await _anketa_finish(message.from_user.id, state)


async def process_anketa_choice(call: CallbackQuery, state: FSMContext):
    """Handle choice button press in event anketa (legacy mode)."""
    data = await state.get_data()

    # Legacy mode only — flow mode uses process_anketa_flow_choice
    if not data.get('anketa_legacy'):
        await call.answer()
        return

    questions = data['anketa_questions']
    index = data['anketa_index']
    question = questions[index]

    choice_index = int(call.data.split(':')[1])
    answer_text = question['options'][choice_index]

    DB.EventAnswer.add(
        user_id=call.from_user.id,
        question_id=question['id'],
        answer_text=answer_text,
    )

    try:
        await call.message.delete()
    except TelegramAPIError:
        ...

    await call.answer()
    await _anketa_next_or_finish_legacy(call.from_user.id, state)


async def process_anketa_flow_choice(call: CallbackQuery, state: FSMContext):
    """Handle choice button press in anketa flow (scenario:5 screens)."""
    # callback format: af:{index} — mapping stored in FSM state
    parts = call.data.split(':')
    if len(parts) < 2:
        await call.answer()
        return

    idx = parts[1]
    data = await state.get_data()
    btn_map = data.get('anketa_btn_map', {})
    mapping = btn_map.get(idx)
    if not mapping:
        await call.answer('Ошибка, попробуйте снова')
        return

    screen_id = mapping['screen_id']
    btn_key = mapping['key']
    target_screen = mapping.get('target', '')

    from bot.utils.dynamic_kb import get_screen
    screen = get_screen(screen_id)
    answer_key = screen.get('answerKey', '') if screen else ''

    # Get the button label as answer
    btn = screen.get('buttons', {}).get(btn_key, {}) if screen else {}
    answer_text = btn.get('label', '')

    data = await state.get_data()
    answers = data.get('anketa_answers', {})
    if answer_key:
        answers[answer_key] = answer_text
    screen_path = data.get('anketa_screen_path', [])
    if screen_id not in screen_path:
        screen_path.append(screen_id)

    await state.update_data(anketa_answers=answers, anketa_screen_path=screen_path)

    try:
        await call.message.delete()
    except TelegramAPIError:
        ...
    await call.answer()

    if target_screen:
        await _send_anketa_screen(call.from_user.id, target_screen, state)
    else:
        await _anketa_finish(call.from_user.id, state)


async def process_anketa_sub_check(call: CallbackQuery, state: FSMContext):
    """Handle subscription check button in anketa flow."""
    # callback format: as:0 — mapping stored in FSM state
    data = await state.get_data()
    sub_info = data.get('anketa_sub_info', {})
    screen_id = sub_info.get('screen_id', '')
    next_screen = sub_info.get('next_screen', '')

    from bot.utils.dynamic_kb import get_screen

    # Check subscription to @WinlinePartners channel
    try:
        member = await bot.get_chat_member(-1002066039310, call.from_user.id)
        is_subscribed = member.status in [
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR,
        ]
    except Exception as e:
        logger.error(f'[anketa-sub-check] Error checking subscription: {e}')
        is_subscribed = False

    if not is_subscribed:
        # Show failure text as popup alert + inline text
        screen = get_screen(screen_id)
        fail_text = ''
        fail_alert = ''
        if screen:
            messages = screen.get('messages', {})
            fail_msg = messages.get('fail_text', {})
            fail_text = fail_msg.get('text', '') if fail_msg else ''
            alert_msg = messages.get('fail_alert', {})
            fail_alert = alert_msg.get('text', '') if alert_msg else ''

        # Show alert popup
        popup = fail_alert or fail_text or 'Не получилось проверить подписку. Ты точно подписан(а) на канал @WinlinePartners?'
        await call.answer(popup, show_alert=True)
        return

    # Subscription confirmed — proceed
    await call.answer()

    # Add screen to path
    data = await state.get_data()
    screen_path = data.get('anketa_screen_path', [])
    if screen_id not in screen_path:
        screen_path.append(screen_id)
    await state.update_data(anketa_screen_path=screen_path)

    try:
        await call.message.delete()
    except TelegramAPIError:
        ...

    if next_screen:
        await _send_anketa_screen(call.from_user.id, next_screen, state)
    else:
        await _anketa_finish(call.from_user.id, state)


async def start_event_anketa_callback(call: CallbackQuery, state: FSMContext):
    """Start event anketa from the 'Заполнить анкету' button."""
    user_id = call.from_user.id

    # Check if already authorized
    auth_data = DB.UserAuth.select(user_id)
    if auth_data:
        try:
            await call.message.delete()
        except TelegramAPIError:
            ...
        await _send_event_qr(user_id, is_partner=True)
        await call.answer()
        return

    try:
        await call.message.delete()
    except TelegramAPIError:
        ...
    await call.answer()
    await _start_event_anketa(call.message, user_id, state)


# ==================== End Сценарий 3 ====================


async def wait_about_role(message: Message, state: FSMContext):
    await message.delete()
    data = await state.get_data()
    await state.update_data(role=message.text)
    menu: Message = data['menu_message']
    await menu.edit_text('<b>Отлично! Осталось подписаться на канал '
                         '@WinlinePartners и можно приходить на стенд Winline Partners, '
                         'чтобы получить мерч!</b>', reply_markup=kb_client_menu.subscribe)
    DB.User.update(message.from_user.id, role=message.text)


def _is_event_deeplink(message: Message) -> bool:
    """Filter: /start event deep link."""
    if message.text and message.text.strip().lower() == '/start event':
        return True
    return False



async def dynamic_screen_handler(call: CallbackQuery, state: FSMContext):
    """Universal handler for custom screens (sc_custom_xxx callbacks)."""
    if state and await state.get_state():
        await state.clear()
    screen_id = call.data[3:]  # remove 'sc_' prefix
    
    # If target is a system screen, redirect to its handler
    SYSTEM_REDIRECTS = {
        'main_menu': 'client_back_menu',
        'start_menu': 'client_back_to_start',
        'auth_flow': 'client_existing_partner',
        'registration_flow': 'client_new_partner',
        'offer_page': 'client_offers',
        'promo_page': 'client_promo',
        'socials_page': 'client_socials',
        'event_flow': 'client_at_event',
        'logout_screen': 'client_logout',
        'knowledge_base': 'client_knowledge_base',
    }
    if screen_id in SYSTEM_REDIRECTS:
        # Call the system handler directly (CallbackQuery is frozen in pydantic v2)
        handler_map = {
            'client_back_menu': back_menu,
            'client_back_to_start': back_to_start,
            'client_existing_partner': existing_partner,
            'client_new_partner': new_partner,
            'client_offers': pm_offers,
            'client_promo': pm_promo,
            'client_socials': pm_socials,
            'client_at_event': at_event,
            'client_logout': logout,
            'client_knowledge_base': pm_knowledge_base,
        }
        handler = handler_map.get(SYSTEM_REDIRECTS[screen_id])
        if handler:
            return await handler(call, state) if 'state' in handler.__code__.co_varnames else await handler(call)
        return await call.answer()
    
    text = get_text(screen_id, 'main_text')
    if not text:
        text = '<b>Экран не найден</b>'

    from bot.utils.dynamic_kb import get_screen_kb
    kb = get_screen_kb(screen_id)
    if not kb:
        from bot.keyboards.client import kb_client_menu
        kb = kb_client_menu.back_menu

    try:
        await call.message.delete()
    except Exception as e:
        logger.debug(f"Suppressed: {e}")

    new_menu = await send_screen_message(bot, call.from_user.id, screen_id, text, reply_markup=kb)
    DB.User.update(mark=call.from_user.id, menu_id=new_menu.message_id)
    await call.answer()



async def poll_vote_handler(call: CallbackQuery):
    parts = call.data.split(":")
    if len(parts) != 3:
        return await call.answer("Ошибка")
    _, poll_id, option_index = parts
    try:
        base_url = config.admin_panel_webhook.rstrip('/').rsplit('/api/', 1)[0] if config.admin_panel_webhook else "https://winlinepartners.ru"
        url = f"{base_url}/api/broadcasts/poll-vote"
        payload = {"poll_id": int(poll_id), "user_id": call.from_user.id, "option_index": int(option_index)}
        body_bytes = json_mod.dumps(payload, separators=(',', ':')).encode('utf-8')
        sig = hmac.new(config.admin_webhook_secret.encode(), body_bytes, hashlib.sha256).hexdigest() if config.admin_webhook_secret else ""
        headers = {"Content-Type": "application/json"}
        if sig:
            headers["x-webhook-signature"] = sig
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, data=body_bytes, headers=headers) as resp:
                if resp.status != 200:
                    logger.error(f"[poll_vote] API returned {resp.status}")
                    return await call.answer("Ошибка", show_alert=False)
                data = await resp.json()
        if data.get("already_voted"):
            await call.answer("Vы уже голосовали", show_alert=False)
            return
        correct = data.get("correct")
        if correct is True:
            await call.answer("Правильный ответ", show_alert=False)
        elif correct is False:
            await call.answer("Неправильный ответ", show_alert=False)
        else:
            await call.answer("Голос принят", show_alert=False)
        result_text = data.get("resultText")
        if result_text:
            try:
                await call.message.edit_text(result_text, parse_mode="HTML")
            except Exception:
                pass
    except Exception as e:
        logger.error(f"[poll_vote] {e}")
        await call.answer("Ошибка", show_alert=False)


# ─── AI assistant ───────────────────────────────────────────────────────────
async def ask_ai_start(call: CallbackQuery, state: FSMContext):
    """Show prompt for AI question, set FSM state."""
    user_id = call.from_user.id
    if not ai_is_allowed(user_id):
        await call.answer(
            'Функция временно доступна только тестировщикам.',
            show_alert=True,
        )
        return
    remaining = ai_remaining(user_id)
    if remaining <= 0:
        await call.answer(
            f'Лимит {AI_MAX_DAILY} вопросов в сутки исчерпан. Попробуйте завтра.',
            show_alert=True,
        )
        return

    await state.set_state(FsmAskAi.wait_question)
    try:
        await call.message.delete()
    except TelegramAPIError:
        ...
    text = (
        '<b>❓ Спросите ИИ-ассистента</b>\n\n'
        'Напишите ваш вопрос — я постараюсь ответить на основе базы знаний '
        'партнёрской программы Winline.\n\n'
        f'<i>Осталось вопросов сегодня: {remaining}/{AI_MAX_DAILY}</i>'
    )
    new_menu = await bot.send_message(
        chat_id=user_id, text=text, reply_markup=kb_client_menu.back_menu,
    )
    DB.User.update(mark=user_id, menu_id=new_menu.message_id)
    await call.answer()


async def ask_ai_process(message: Message, state: FSMContext):
    """User typed a question — fetch answer from Claude and reply."""
    user_id = message.from_user.id
    question = (message.text or '').strip()

    if not ai_is_allowed(user_id):
        await state.clear()
        await message.answer('Функция временно доступна только тестировщикам.')
        return

    if not question:
        await message.answer('Пожалуйста, отправьте текст вопроса.')
        return

    remaining = ai_remaining(user_id)
    if remaining <= 0:
        await state.clear()
        await message.answer(
            f'⚠️ Лимит {AI_MAX_DAILY} вопросов в сутки исчерпан. Попробуйте завтра.',
            reply_markup=kb_client_menu.back_menu,
        )
        return

    # Show typing indicator while waiting for Claude
    typing_task = asyncio.create_task(_keep_typing(user_id))
    try:
        ok, answer = await ai_ask(user_id, question)
    finally:
        typing_task.cancel()

    # Telegram message limit is 4096; trim safely
    if len(answer) > 3800:
        answer = answer[:3800] + '\n\n<i>(ответ обрезан)</i>'

    footer = ''
    if ok:
        new_remaining = max(0, remaining - 1)
        footer = f'\n\n<i>Осталось вопросов сегодня: {new_remaining}/{AI_MAX_DAILY}</i>'

    await state.clear()
    try:
        await message.answer(
            answer + footer,
            reply_markup=kb_client_menu.ask_ai_actions,
            parse_mode='HTML',
        )
    except TelegramAPIError:
        # If HTML failed (e.g. bad tags from model), retry as plain text
        import re as _re
        plain = _re.sub(r'<[^>]+>', '', answer)
        await message.answer(plain + footer, reply_markup=kb_client_menu.ask_ai_actions)


async def _keep_typing(chat_id: int):
    """Send 'typing' chat action every 4s while AI is thinking."""
    try:
        while True:
            try:
                await bot.send_chat_action(chat_id=chat_id, action='typing')
            except TelegramAPIError:
                pass
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass


def register_handlers_client_main(dp: Dispatcher):
    # Сценарий 3 v2 — должен регистрироваться ДО старого at_event, иначе old wins
    from bot.handlers.client import client_event_v2 as _ev2
    _ev2.register(dp)
    # Старый start_event (мерч-QR сразу авторизованным) отключён — deep-link
    # `/start event` теперь полностью обрабатывается start_command, который
    # ведёт в S3 v2 (event_partner_check). Сам хендлер оставлен в файле на
    # случай отката.
    # dp.message.register(start_event, _is_event_deeplink, F.chat.type == 'private')
    dp.message.register(start_command, Command(commands="start"), F.chat.type == 'private')
    dp.callback_query.register(poll_vote_handler, F.data.startswith('poll_vote:'))
    dp.callback_query.register(dynamic_screen_handler, F.data.startswith('sc_'))
    dp.callback_query.register(telegram.delete_message, F.data == 'client_delete_message')
    dp.callback_query.register(back_menu, F.data == 'client_back_menu')
    dp.callback_query.register(back_to_start, F.data == 'client_back_to_start')
    dp.callback_query.register(existing_partner, F.data == 'client_existing_partner')
    dp.callback_query.register(new_partner, F.data == 'client_new_partner')
    dp.callback_query.register(already_registered, F.data == 'client_already_registered')
    dp.callback_query.register(start_auth_email, F.data == 'client_auth_email')
    dp.callback_query.register(pm_knowledge_base, F.data == 'client_knowledge_base')
    dp.callback_query.register(pm_kb_back_to_menu, F.data == 'pm_knowledge_base')
    dp.callback_query.register(pm_kb_back, F.data.startswith('pm_kb_back:'))
    dp.callback_query.register(pm_kb_subtopic, F.data.startswith('pm_kb_'))
    dp.callback_query.register(pm_my_stats, F.data == 'client_my_stats')
    dp.callback_query.register(pm_stats_period, F.data.startswith('client_stats_period:'))
    dp.callback_query.register(pm_offers, F.data == 'client_offers')
    dp.callback_query.register(pm_socials, F.data == 'client_socials')
    dp.callback_query.register(pm_calendar, F.data == 'client_calendar')
    dp.callback_query.register(pm_promo, F.data == 'client_promo')
    # старый at_event заменён на event_v2_start (см. register выше)
    dp.callback_query.register(logout, F.data == 'client_logout')
    dp.callback_query.register(reg_help, F.data == 'client_reg_help')
    dp.callback_query.register(registration, F.data == 'client_registration')
    dp.callback_query.register(start_event_anketa_callback, F.data == 'client_event_anketa')
    dp.callback_query.register(ask_ai_start, F.data == 'client_ask_ai')
    dp.message.register(ask_ai_process, FsmAskAi.wait_question, F.chat.type == 'private')
    dp.callback_query.register(subscribe, F.data == 'client_check_subscribe')
    dp.message.register(process_auth_email, FsmAuth.wait_email, F.chat.type == 'private')
    dp.message.register(process_auth_otp, FsmAuth.wait_otp, F.chat.type == 'private')
    dp.callback_query.register(auth_otp_resend,        F.data == 'auth_otp_resend')
    dp.callback_query.register(auth_otp_change_email,  F.data == 'auth_otp_change_email')
    dp.message.register(process_anketa_text, FsmEventAnketa.answering, F.chat.type == 'private')
    dp.callback_query.register(process_anketa_flow_choice, F.data.startswith('af:'), FsmEventAnketa.answering)
    dp.callback_query.register(process_anketa_sub_check, F.data.startswith('as:'), FsmEventAnketa.answering)
    dp.callback_query.register(process_anketa_choice, F.data.startswith('anketa_choice:'), FsmEventAnketa.answering)
    dp.message.register(wait_rl_name, FsmRegistration.wait_rl_name)
    dp.message.register(wait_phone, FsmRegistration.wait_phone)
    dp.callback_query.register(pick_role, F.data.startswith('pick:role'))
    dp.message.register(wait_about_role, FsmRegistration.wait_about_role)
    dp.callback_query.register(wait_traff, F.data.startswith('pick:traff'))
    dp.callback_query.register(pm, F.data == 'client_pm')
