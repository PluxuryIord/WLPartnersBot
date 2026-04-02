"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from __future__ import annotations
import os
import hashlib
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

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from aiogram.utils.markdown import hlink

import bot.keyboards.admin.kb_admin_topic
from bot.integrations.google.spreadsheets.google_sheets import new_user, new_prize
from bot.states.wait_question import FsmRegistration, FsmEventAnketa, FsmAuth
from bot.utils.qr_code import generate_qr_on_template

if TYPE_CHECKING:
    from aiogram import Dispatcher
    from aiogram.fsm.context import FSMContext
    from aiogram.types import Message, CallbackQuery, User

    from typing import Union

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
import os
import hashlib
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


input_data = {
    1: ['ФИО', 'rl_full_name'],
    2: ['Номер телефона', 'phone_number'],
    3: ['Роль в компании', 'role'],
    4: ['Тип трафика', 'graph'],
}


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
        if get_settings_cached().event_starts:
            kb = kb_client_menu.event_menu_admin if is_admin else kb_client_menu.event_menu
            caption_text = '<b>Приветственный текст для мероприятия\n\nЧтобы продолжить, пожалуйста, заполните небольшую анкету</b>'
        else:
            kb = kb_client_menu.get_start_menu(is_admin)
            caption_text = (f'<b>Привет, {update.from_user.first_name}! '
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
        await telegram.delete_message(chat_id=user.id, message_id=user_data.menu_id)
        if alert:
            new_menu_id = await bot.send_message(user.id, '<b>ℹ️Открыто меню из рассылки</b>',
                                                 reply_markup=kb_client_menu.back_menu)
        else:
            is_admin = config.admin_filter.is_admin(user.id)
            auth_data = DB.UserAuth.select(user.id)
            if auth_data:
                email_text = f'\n\n📧 <b>Email:</b> {auth_data.email}' if auth_data.email else ''
                kb = kb_client_menu.get_authorized_menu(is_admin, event_active=get_settings_cached().event_starts)
                new_menu_id = await bot.send_photo(
                    chat_id=user.id,
                    caption=get_text('auth_flow', 'auth_success', email=auth_data.email) or f'<b>✅ Вы авторизованы</b>{email_text}',
                    photo='AgACAgIAAxkBAALAumm79aB6UEyMKSwO7Y4CIuK0V2GvAALrGWsbCkPgSa2z0SVvYvJsAQADAgADeQADOgQ',
                    reply_markup=kb)
            else:
                # Not authorized → show start menu or event menu
                if get_settings_cached().event_starts:
                    kb = kb_client_menu.event_menu_admin if is_admin else kb_client_menu.event_menu
                    caption_text = '<b>Приветственный текст для мероприятия\n\nЧтобы продолжить, пожалуйста, заполните небольшую анкету</b>'
                else:
                    kb = kb_client_menu.get_start_menu(is_admin)
                    caption_text = (f'<b>Привет, {user.first_name}! '
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


async def back_menu(call: CallbackQuery, state: FSMContext):
    if await state.get_state():
        await state.clear()
    user_data = DB.User.select(call.from_user.id)
    is_admin = config.admin_filter.is_admin(call.from_user.id)
    auth_data = DB.UserAuth.select(call.from_user.id)
    if auth_data:
        email_text = f'\n\n📧 <b>Email:</b> {auth_data.email}' if auth_data.email else ''
        kb = kb_client_menu.get_authorized_menu(is_admin, event_active=get_settings_cached().event_starts)
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
        if get_settings_cached().event_starts:
            kb = kb_client_menu.event_menu_admin if is_admin else kb_client_menu.event_menu
            caption_text = '<b>Приветственный текст для мероприятия\n\nЧтобы продолжить, пожалуйста, заполните небольшую анкету</b>'
        else:
            kb = kb_client_menu.get_start_menu(is_admin)
            caption_text = ('<b>Привет! Этот бот поможет тебе зарегистрироваться в качестве партнёра, '
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


async def wait_rl_name(message: Message, state: FSMContext):
    await message.delete()
    data = await state.get_data()
    await state.update_data(rl_full_name=message.text)
    menu: Message = data['menu_message']
    await menu.edit_text('<b>Введи твой номер телефона</b>')
    await state.set_state(FsmRegistration.wait_phone)
    DB.User.update(message.from_user.id, rl_full_name=message.text)


async def wait_phone(message: Message, state: FSMContext):
    await message.delete()
    data = await state.get_data()
    await state.update_data(phone_number=message.text)
    menu: Message = data['menu_message']
    await menu.edit_text('<b>Выбери свою роль в компании</b>', reply_markup=kb_client_menu.user_role)
    await state.set_state(FsmRegistration.wait_phone)
    DB.User.update(message.from_user.id, phone_number=message.text)


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
        caption=f'<b>Привет, {call.from_user.first_name}! '
                'Этот бот поможет тебе зарегистрироваться в качестве партнёра '
                'в нашей партнерской программе WINLINE PARTNERS, даст возможность получать '
                'актуальные новости и предложения, а также участвовать в мероприятиях!</b>',
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
    await call.message.edit_caption(
        caption=(
            '<b>Чтобы стать партнёром WINLINE PARTNERS, Вам нужно перейти на '
            '<a href="https://partners.winline.ru">официальный сайт партнерской программы</a> '
            'и зарегистрироваться.</b>\n\n'
            'При регистрации укажите следующую информацию:\n'
            '• имя и фамилию;\n'
            '• свой email;\n'
            '• пароль.\n\n'
            'После заполнения заявки нажмите кнопку «Регистрация» и подтвердите '
            'регистрацию аккаунта по email.'
        ),
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

    # Save auth
    user_id = message.from_user.id
    existing = DB.UserAuth.select(user_id)
    if existing:
        DB.UserAuth.update(user_id, email=email, token=None)
        DB.User.update(user_id, registered=True)
    else:
        DB.UserAuth.add(user_id, email, token=None)
    DB.User.update(user_id, registered=True)

    await state.clear()

    # Delete old message and show authorized menu
    if menu_msg:
        try:
            await menu_msg.delete()
        except TelegramAPIError:
            ...

    is_admin = config.admin_filter.is_admin(user_id)
    kb = kb_client_menu.get_authorized_menu(is_admin, event_active=get_settings_cached().event_starts)
    new_menu = await bot.send_photo(
        chat_id=user_id,
        caption=get_text('auth_flow', 'auth_success', email=email) or f'<b>✅ Вы авторизованы</b>\n\n📧 <b>Email:</b> {email}',
        photo='AgACAgIAAxkBAALAumm79aB6UEyMKSwO7Y4CIuK0V2GvAALrGWsbCkPgSa2z0SVvYvJsAQADAgADeQADOgQ',
        reply_markup=kb)
    DB.User.update(mark=user_id, menu_id=new_menu.message_id)


async def pm_offers(call: CallbackQuery):
    """Show offer info in PM."""
    try:
        await call.message.delete()
    except TelegramAPIError:
        ...
    offer_text = (
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
    new_menu = await send_screen_message(
        bot, call.from_user.id, 'offer_page',
        text=offer_text,
        reply_markup=kb_client_group.create_inline([
            ['🔙 Меню', 'call', 'client_back_menu'],
        ], 1))
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
    """Handle individual KB subtopic in PM (dynamic)."""
    key = call.data  # e.g. pm_kb_lk_overview
    text_key = key.replace('pm_kb_', '', 1)  # e.g. lk_overview

    kb_row = DB.Text.select(where=DB.Text.category == 'knowledge_base')
    kb = kb_row.data if kb_row else {}
    text = kb.get(text_key, '<b>Информация не найдена</b>')

    chat_id = call.from_user.id
    sent_ids = []

    # Photo: standard convention {key}_photo
    photo_key = f'{text_key}_photo'
    photo_id = kb.get(photo_key) or None

    if photo_id:
        await call.message.delete()
        msg1 = await bot.send_photo(chat_id=chat_id, photo=photo_id)
        sent_ids.append(msg1.message_id)
        msg2 = await bot.send_message(
            chat_id=chat_id, text=text,
            reply_markup=kb_client_group.pm_back_to_kb_with_ids(sent_ids))
        sent_ids.append(msg2.message_id)
    else:
        await call.message.edit_text(
            text, reply_markup=kb_client_group.pm_back_to_knowledge_base)
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



async def pm_socials(call: CallbackQuery):
    """Show social networks in PM."""
    try:
        await call.message.delete()
    except TelegramAPIError:
        ...
    socials_menu = kb_client_group.create_inline([
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
    promo_text = (
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
    new_menu = await bot.send_message(
        chat_id=call.from_user.id,
        text=promo_text,
        reply_markup=kb_client_group.pm_promo_menu)
    DB.User.update(mark=call.from_user.id, menu_id=new_menu.message_id)
    await call.answer()


def _sync_get_or_create_event_code(user_id, full_name=''):
    """Sync helper: get existing event code or create new one."""
    _db_cfg = {
        'host': os.getenv('MYSQL_HOST', ''), 'port': int(os.getenv('MYSQL_PORT', 3306)),
        'user': os.getenv('MYSQL_USER', ''), 'password': os.getenv('MYSQL_PASSWORD', ''),
        'database': os.getenv('MYSQL_DATABASE', ''),
    }
    conn = mysql.connector.connect(**_db_cfg)
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute('SELECT code FROM wl_event_codes WHERE user_id = %s AND status = %s LIMIT 1', (user_id, 'active'))
        existing = cur.fetchone()
        if existing:
            return existing['code']

        cur.execute("SELECT data FROM texts WHERE category = 'event_settings' LIMIT 1")
        row = cur.fetchone()
        code_limit = 0
        if row:
            _data = row['data']
            _s = json_mod.loads(_data) if isinstance(_data, str) else _data
            code_limit = int(_s.get('code_limit', 0))
        if code_limit > 0:
            cur.execute('SELECT COUNT(*) as cnt FROM wl_event_codes')
            total = cur.fetchone()['cnt']
            if total >= code_limit:
                return None  # limit reached

        event_code = 'EVT-' + hashlib.md5(f'{user_id}{time.time()}'.encode()).hexdigest()[:8].upper()
        cur.execute(
            'INSERT INTO wl_event_codes (code, label, user_id, status) VALUES (%s, %s, %s, %s)',
            (event_code, full_name or str(user_id), user_id, 'active')
        )
        conn.commit()
        return event_code
    finally:
        try:
            conn.close()
        except Exception:
            pass


async def get_or_create_event_code(user_id, full_name=''):
    """Async wrapper — runs sync MySQL in thread pool."""
    return await asyncio.to_thread(_sync_get_or_create_event_code, user_id, full_name)


async def at_event(call: CallbackQuery):
    settings = get_settings_cached()
    if not settings.event_starts:
        return await call.answer('Сейчас нет активных мероприятий', show_alert=True)

    user_id = call.from_user.id


    _db_cfg = {
        'host': os.getenv('MYSQL_HOST', 'db.buy-bot.ru'), 'port': int(os.getenv('MYSQL_PORT', 3306)),
        'user': os.getenv('MYSQL_USER', ''), 'password': os.getenv('MYSQL_PASSWORD', ''),
        'database': os.getenv('MYSQL_DATABASE', ''),
    }
    conn = mysql.connector.connect(**_db_cfg)
    cur = conn.cursor(dictionary=True)

    try:
        cur.execute('SELECT code FROM wl_event_codes WHERE user_id = %s AND status = %s LIMIT 1', (user_id, 'active'))
        existing = cur.fetchone()

        if existing:
            event_code = existing['code']
        else:
            cur.execute("SELECT data FROM texts WHERE category = 'event_settings' LIMIT 1")
            row = cur.fetchone()
            code_limit = 0
            if row:
                _data = row['data']
                _s = json_mod.loads(_data) if isinstance(_data, str) else _data
                code_limit = int(_s.get('code_limit', 0))

            if code_limit > 0:
                cur.execute('SELECT COUNT(*) as cnt FROM wl_event_codes')
                total = cur.fetchone()['cnt']
                if total >= code_limit:
                    conn.close()
                    return await call.answer('К сожалению, все коды уже разобраны!', show_alert=True)

            event_code = 'EVT-' + hashlib.md5(f'{user_id}{time.time()}'.encode()).hexdigest()[:8].upper()
            cur.execute(
                'INSERT INTO wl_event_codes (code, label, user_id, status) VALUES (%s, %s, %s, %s)',
                (event_code, call.from_user.full_name, user_id, 'active')
            )
            conn.commit()

        # Download QR card from panel server
        qr_card_url = f'https://panel.wl-fdms.tw1.ru/api/events/codes/{event_code}/qr-card'
        try:
            async with aiohttp.ClientSession() as _sess:
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
    finally:
        try:
            conn.close()
        except Exception:
            pass

    try:
        await call.message.delete()
    except TelegramAPIError:
        ...
    new_menu = await bot.send_photo(
        chat_id=user_id,
        photo=photo,
        caption=f'<b>Вот ваш QR для получения подарка!</b>\n\nКод: <code>{event_code}</code>',
        reply_markup=kb_client_menu.back_menu
    )
    DB.User.update(mark=user_id, menu_id=new_menu.message_id)

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


def _get_qr_caption() -> str:
    """Get QR caption text from event_settings in DB."""
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
            return _s.get('qr_caption_text', '')
    except Exception as e:
        logger.debug(f"Suppressed: {e}")
    return ''

async def _generate_event_qr(user_id: int) -> str:
    """Generate QR for event using wl_event_codes, return path."""

    _db_cfg = {
        'host': os.getenv('MYSQL_HOST', 'db.buy-bot.ru'), 'port': int(os.getenv('MYSQL_PORT', 3306)),
        'user': os.getenv('MYSQL_USER', ''), 'password': os.getenv('MYSQL_PASSWORD', ''),
        'database': os.getenv('MYSQL_DATABASE', ''),
    }
    conn = mysql.connector.connect(**_db_cfg)
    cur = conn.cursor(dictionary=True)

    try:
        # Check existing active code
        cur.execute('SELECT code FROM wl_event_codes WHERE user_id = %s AND status = %s LIMIT 1', (user_id, 'active'))
        existing = cur.fetchone()

        if existing:
            event_code = existing['code']
        else:
            # Check code limit
            cur.execute("SELECT data FROM texts WHERE category = 'event_settings' LIMIT 1")
            row = cur.fetchone()
            code_limit = 0
            if row:
                _data = row['data']
                _s = json_mod.loads(_data) if isinstance(_data, str) else _data
                code_limit = int(_s.get('code_limit', 0))

            if code_limit > 0:
                cur.execute('SELECT COUNT(*) as cnt FROM wl_event_codes')
                total = cur.fetchone()['cnt']
                if total >= code_limit:
                    conn.close()
                    return None  # limit reached

            event_code = 'EVT-' + hashlib.md5(f'{user_id}{time.time()}'.encode()).hexdigest()[:8].upper()
            user_data = DB.User.select(user_id)
            label = user_data.full_name if user_data else str(user_id)
            cur.execute(
                'INSERT INTO wl_event_codes (code, label, user_id, status) VALUES (%s, %s, %s, %s)',
                (event_code, label, user_id, 'active')
            )
            conn.commit()

        # Generate QR image and save to file
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
        qr.add_data(event_code)
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white')
        qr_path = f"files/{user_id}_evt.png"
        img.save(qr_path)
        return qr_path
    finally:
        try:
            conn.close()
        except Exception:
            pass

async def _send_event_qr(user_id: int, is_partner: bool = False) -> Message:
    """Send QR photo with code in caption."""
    qr_path = await _generate_event_qr(user_id)
    if qr_path is None:
        # Limit reached
        new_menu = await bot.send_message(
            chat_id=user_id,
            text='К сожалению, все коды уже разобраны!',
            reply_markup=kb_client_menu.back_menu,
        )
        DB.User.update(mark=user_id, menu_id=new_menu.message_id)
        return new_menu

    # Get event code (reuse helper)
    event_code = await get_or_create_event_code(user_id) or ''

    reply_markup = kb_client_menu.back_menu if is_partner else kb_client_menu.event_qr_new_menu
    
    # Download QR card from panel server
    qr_card_url = f'https://panel.wl-fdms.tw1.ru/api/events/codes/{event_code}/qr-card'
    qr_path = f"files/{user_id}_card.png"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(qr_card_url) as resp:
                if resp.status == 200:
                    with open(qr_path, 'wb') as f_out:
                        f_out.write(await resp.read())
                else:
                    raise Exception(f'HTTP {resp.status}')
    except Exception as _e:
        logger.warning(f'[QR-CARD] Fallback: {_e}')
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
        qr.add_data(event_code)
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white')
        img.save(qr_path)
    
    caption = f'<b>Вот ваш QR для получения подарка!</b>'
    if event_code:
        caption += f'\n\nКод: <code>{event_code}</code>'
    new_menu = await bot.send_photo(
        chat_id=user_id,
        photo=FSInputFile(qr_path),
        caption=caption,
        reply_markup=reply_markup,
    )
    DB.User.update(mark=user_id, menu_id=new_menu.message_id)
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
    """Load questions from DB and start the anketa flow."""
    from sqlalchemy import asc
    questions = DB.EventQuestion.select(
        where=(DB.EventQuestion.is_active == True),
        all_scalars=True,
    )
    if not questions:
        # No questions configured → give QR immediately
        await _send_event_qr(user_id, is_partner=False)
        return

    # Sort by order
    questions = sorted(questions, key=lambda q: q.order)
    questions_data = [
        {'id': q.id, 'text': q.question_text, 'type': q.question_type, 'options': q.options}
        for q in questions
    ]

    await state.set_state(FsmEventAnketa.answering)
    await state.update_data(
        anketa_questions=questions_data,
        anketa_index=0,
    )
    await _send_anketa_question(user_id, questions_data[0], state)


async def _send_anketa_question(user_id: int, question: dict, state: FSMContext):
    """Send a single anketa question to the user."""
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


async def _anketa_next_or_finish(user_id: int, state: FSMContext):
    """Move to next question or finish with QR."""
    data = await state.get_data()
    questions = data['anketa_questions']
    index = data['anketa_index'] + 1

    if index >= len(questions):
        # All done → clear state, give QR
        await state.clear()
        await _send_event_qr(user_id, is_partner=False)
        return

    await state.update_data(anketa_index=index)
    await _send_anketa_question(user_id, questions[index], state)


async def process_anketa_text(message: Message, state: FSMContext):
    """Handle text answer in event anketa."""
    await message.delete()
    data = await state.get_data()
    questions = data['anketa_questions']
    index = data['anketa_index']
    question = questions[index]

    # Save answer
    DB.EventAnswer.add(
        user_id=message.from_user.id,
        question_id=question['id'],
        answer_text=message.text,
    )

    # Delete previous question message
    menu_msg = data.get('anketa_menu_message')
    if menu_msg:
        try:
            await menu_msg.delete()
        except TelegramAPIError:
            ...

    await _anketa_next_or_finish(message.from_user.id, state)


async def process_anketa_choice(call: CallbackQuery, state: FSMContext):
    """Handle choice button press in event anketa."""
    data = await state.get_data()
    questions = data['anketa_questions']
    index = data['anketa_index']
    question = questions[index]

    choice_index = int(call.data.split(':')[1])
    answer_text = question['options'][choice_index]

    # Save answer
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
    await _anketa_next_or_finish(call.from_user.id, state)


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
    }
    if screen_id in SYSTEM_REDIRECTS:
        # Rewrite callback data to system callback and let aiogram re-route
        call.data = SYSTEM_REDIRECTS[screen_id]
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
        }
        handler = handler_map.get(SYSTEM_REDIRECTS[screen_id])
        if handler:
            return await handler(call, state) if 'state' in handler.__code__.co_varnames else await handler(call)
        return await call.answer()
    
    # Get text and media from scenarios cache
    text = get_text(screen_id, 'main_text')
    if not text:
        text = '<b>Экран не найден</b>'
    
    # Get media URL if exists
    media_url = None
    try:
        from bot.utils.dynamic_kb import _load
        sc_data = _load()
        screen = sc_data.get('screens', {}).get(screen_id, {})
        msg = screen.get('messages', {}).get('main_text', {})
        media = msg.get('media')
        if media and media.get('url'):
            media_url = media['url']
    except Exception:
        pass
    
    # Get keyboard from scenarios cache
    from bot.utils.dynamic_kb import get_screen_kb
    kb = get_screen_kb(screen_id)
    if not kb:
        from bot.keyboards.client import kb_client_menu
        kb = kb_client_menu.back_menu
    
    try:
        await call.message.delete()
    except Exception as e:
        logger.debug(f"Suppressed: {e}")
    
    if media_url:
        new_menu = await bot.send_photo(
            chat_id=call.from_user.id,
            photo=media_url,
            caption=text,
            reply_markup=kb
        )
    else:
        new_menu = await bot.send_message(
            chat_id=call.from_user.id,
            text=text,
            reply_markup=kb
        )
    DB.User.update(mark=call.from_user.id, menu_id=new_menu.message_id)
    await call.answer()



async def poll_vote_handler(call: CallbackQuery):
    parts = call.data.split(":")
    if len(parts) != 3:
        return await call.answer("Ошибка")
    _, poll_id, option_index = parts
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://panel.wl-fdms.tw1.ru/api/broadcasts/poll-vote",
                json={"poll_id": int(poll_id), "user_id": call.from_user.id, "option_index": int(option_index)}
            ) as resp:
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

def register_handlers_client_main(dp: Dispatcher):
    dp.message.register(start_event, _is_event_deeplink, F.chat.type == 'private')
    dp.message.register(main_menu, Command(commands="start"), F.chat.type == 'private')
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
    dp.callback_query.register(pm_offers, F.data == 'client_offers')
    dp.callback_query.register(pm_socials, F.data == 'client_socials')
    dp.callback_query.register(pm_promo, F.data == 'client_promo')
    dp.callback_query.register(at_event, F.data == 'client_at_event')
    dp.callback_query.register(logout, F.data == 'client_logout')
    dp.callback_query.register(reg_help, F.data == 'client_reg_help')
    dp.callback_query.register(registration, F.data == 'client_registration')
    dp.callback_query.register(start_event_anketa_callback, F.data == 'client_event_anketa')
    dp.callback_query.register(subscribe, F.data == 'client_check_subscribe')
    dp.message.register(process_auth_email, FsmAuth.wait_email, F.chat.type == 'private')
    dp.message.register(process_anketa_text, FsmEventAnketa.answering, F.chat.type == 'private')
    dp.callback_query.register(process_anketa_choice, F.data.startswith('anketa_choice:'), FsmEventAnketa.answering)
    dp.message.register(wait_rl_name, FsmRegistration.wait_rl_name)
    dp.message.register(wait_phone, FsmRegistration.wait_phone)
    dp.callback_query.register(pick_role, F.data.startswith('pick:role'))
    dp.message.register(wait_about_role, FsmRegistration.wait_about_role)
    dp.callback_query.register(wait_traff, F.data.startswith('pick:traff'))
    dp.callback_query.register(pm, F.data == 'client_pm')
