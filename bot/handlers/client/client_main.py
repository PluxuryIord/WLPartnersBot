"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from __future__ import annotations

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
from aiogram.types import FSInputFile
from aiogram.enums import ContentType, ChatMemberStatus
import os


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
        if DB.Settings.select().event_starts:
            kb = kb_client_menu.event_menu_admin if is_admin else kb_client_menu.event_menu
            caption_text = '<b>Приветственный текст для мероприятия\n\nЧтобы продолжить, пожалуйста, заполните небольшую анкету</b>'
        else:
            kb = kb_client_menu.start_menu_admin if is_admin else kb_client_menu.start_menu
            caption_text = ('<b>Привет! Этот бот поможет тебе зарегистрироваться в качестве партнёра, '
                           'предоставит быстрый доступ к порталу WINLINE PARTNERS, даст возможность получать '
                           'актуальные новости и предложения, а также участвовать в мероприятиях!</b>')
        await wait_registration.delete()
        new_menu_id = await wait_registration.answer_photo(
            caption=caption_text,
            photo='AgACAgIAAxkBAAJ1zWhdevQQMSnK7IPyyuQVbD13znboAAJI9jEbyLfpSung7LZvwELaAQADAgADeAADNgQ',
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
                kb = kb_client_menu.authorized_menu_admin if is_admin else kb_client_menu.authorized_menu
                new_menu_id = await bot.send_photo(
                    chat_id=user.id,
                    caption=f'<b>✅ Вы авторизованы</b>{email_text}',
                    photo='AgACAgIAAxkBAAJ1zWhdevQQMSnK7IPyyuQVbD13znboAAJI9jEbyLfpSung7LZvwELaAQADAgADeAADNgQ',
                    reply_markup=kb)
            else:
                # Not authorized → show start menu or event menu
                if DB.Settings.select().event_starts:
                    kb = kb_client_menu.event_menu_admin if is_admin else kb_client_menu.event_menu
                    caption_text = '<b>Приветственный текст для мероприятия\n\nЧтобы продолжить, пожалуйста, заполните небольшую анкету</b>'
                else:
                    kb = kb_client_menu.start_menu_admin if is_admin else kb_client_menu.start_menu
                    caption_text = ('<b>Привет! Этот бот поможет тебе зарегистрироваться в качестве партнёра, '
                                   'предоставит быстрый доступ к порталу WINLINE PARTNERS, даст возможность получать '
                                   'актуальные новости и предложения, а также участвовать в мероприятиях!</b>')
                new_menu_id = await bot.send_photo(
                    chat_id=user.id,
                    caption=caption_text,
                    photo='AgACAgIAAxkBAAJ1zWhdevQQMSnK7IPyyuQVbD13znboAAJI9jEbyLfpSung7LZvwELaAQADAgADeAADNgQ',
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
        kb = kb_client_menu.authorized_menu_admin if is_admin else kb_client_menu.authorized_menu
        try:
            await call.message.delete()
        except TelegramAPIError:
            ...
        new_menu = await bot.send_photo(
            chat_id=call.from_user.id,
            caption=f'<b>✅ Вы авторизованы</b>{email_text}',
            photo='AgACAgIAAxkBAAJ1zWhdevQQMSnK7IPyyuQVbD13znboAAJI9jEbyLfpSung7LZvwELaAQADAgADeAADNgQ',
            reply_markup=kb)
        DB.User.update(mark=call.from_user.id, menu_id=new_menu.message_id)
    else:
        try:
            await call.message.delete()
        except TelegramAPIError:
            ...
        if DB.Settings.select().event_starts:
            kb = kb_client_menu.event_menu_admin if is_admin else kb_client_menu.event_menu
            caption_text = '<b>Приветственный текст для мероприятия\n\nЧтобы продолжить, пожалуйста, заполните небольшую анкету</b>'
        else:
            kb = kb_client_menu.start_menu_admin if is_admin else kb_client_menu.start_menu
            caption_text = ('<b>Привет! Этот бот поможет тебе зарегистрироваться в качестве партнёра, '
                           'предоставит быстрый доступ к порталу WINLINE PARTNERS, даст возможность получать '
                           'актуальные новости и предложения, а также участвовать в мероприятиях!</b>')
        new_menu = await bot.send_photo(
            chat_id=call.from_user.id,
            caption=caption_text,
            photo='AgACAgIAAxkBAAJ1zWhdevQQMSnK7IPyyuQVbD13znboAAJI9jEbyLfpSung7LZvwELaAQADAgADeAADNgQ',
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

    if DB.Settings.select().event_starts:
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
        caption='<b>Привет! Этот бот поможет тебе зарегистрироваться в качестве партнёра, '
                'предоставит быстрый доступ к порталу WINLINE PARTNERS, даст возможность получать '
                'актуальные новости и предложения, а также участвовать в мероприятиях!</b>',
        reply_markup=kb_client_menu.start_menu)
    await call.answer()


async def show_auth_screen(call: CallbackQuery):
    await call.message.edit_caption(
        caption='<b>Для доступа к функционалу бота необходимо авторизоваться '
                'с помощью почты, указанной при регистрации на платформе</b>',
        reply_markup=kb_client_menu.auth_menu)
    await call.answer()


async def existing_partner(call: CallbackQuery):
    await show_auth_screen(call)


async def new_partner(call: CallbackQuery):
    await call.message.edit_caption(
        caption=(
            '<b>Чтобы начать сотрудничество с WINLINE Partners, Вам нужно перейти на '
            '<a href="https://partners.winline.ru">официальный сайт партнерской программы</a> '
            'и зарегистрироваться.</b>\n\n'
            'При регистрации укажите следующую информацию:\n'
            '• имя и фамилию;\n'
            '• свой email;\n'
            '• пароль.\n\n'
            'После заполнения заявки нажмите кнопку «Регистрация» и подтвердите '
            'регистрацию аккаунта по email.'
        ),
        reply_markup=kb_client_menu.registration_partners_menu)
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
        '<b>📧 Введите email, указанный при регистрации на платформе</b>')
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
                    '<b>❌ Некорректный формат email\n\n'
                    '📧 Введите email, указанный при регистрации на платформе</b>')
            except TelegramAPIError:
                ...
        return

    # Save auth
    user_id = message.from_user.id
    existing = DB.UserAuth.select(user_id)
    if existing:
        DB.UserAuth.update(user_id, email=email, token=None)
    else:
        DB.UserAuth.add(user_id, email, token=None)

    await state.clear()

    # Delete old message and show authorized menu
    if menu_msg:
        try:
            await menu_msg.delete()
        except TelegramAPIError:
            ...

    is_admin = config.admin_filter.is_admin(user_id)
    kb = kb_client_menu.authorized_menu_admin if is_admin else kb_client_menu.authorized_menu
    new_menu = await bot.send_photo(
        chat_id=user_id,
        caption=f'<b>✅ Вы авторизованы</b>\n\n📧 <b>Email:</b> {email}',
        photo='AgACAgIAAxkBAAJ1zWhdevQQMSnK7IPyyuQVbD13znboAAJI9jEbyLfpSung7LZvwELaAQADAgADeAADNgQ',
        reply_markup=kb)
    DB.User.update(mark=user_id, menu_id=new_menu.message_id)


async def authorized_stub(call: CallbackQuery):
    await call.answer('🔧 Функционал в разработке', show_alert=True)


# ── PM: База знаний & Промо ─────────────────────────────────────────────────

from bot.keyboards.client import kb_client_group

PM_KB_KEYS = {
    'pm_kb_lk_overview': 'lk_overview',
    'pm_kb_offer_info': 'offer_info',
    'pm_kb_ref_link': 'ref_link',
    'pm_kb_postback': 'postback',
    'pm_kb_download_report': 'download_report',
}


async def pm_knowledge_base(call: CallbackQuery):
    """Show knowledge base menu in PM."""
    try:
        await call.message.delete()
    except TelegramAPIError:
        ...
    new_menu = await bot.send_message(
        chat_id=call.from_user.id,
        text='<b>📚 База знаний</b>\n\n<i>Выберите интересующую тему:</i>',
        reply_markup=kb_client_group.pm_knowledge_base_menu)
    DB.User.update(mark=call.from_user.id, menu_id=new_menu.message_id)
    await call.answer()


async def pm_kb_subtopic(call: CallbackQuery):
    """Handle individual KB subtopic in PM."""
    key = call.data
    kb = bot_texts.knowledge_base
    text_key = PM_KB_KEYS.get(key)
    text = kb.get(text_key, '<b>Информация не найдена</b>') if text_key else '<b>Информация не найдена</b>'

    photo_postback = kb.get('postback_photo') or None
    photo_report = kb.get('report_photo') or None
    photo_report_2 = kb.get('report_photo_2') or None

    chat_id = call.from_user.id
    sent_ids = []

    if key == 'pm_kb_postback' and photo_postback:
        await call.message.delete()
        msg1 = await bot.send_photo(chat_id=chat_id, photo=photo_postback)
        sent_ids.append(msg1.message_id)
        msg2 = await bot.send_message(
            chat_id=chat_id, text=text,
            reply_markup=kb_client_group.pm_back_to_kb_with_ids(sent_ids))
        sent_ids.append(msg2.message_id)
    elif key == 'pm_kb_download_report':
        await call.message.delete()
        text_2 = kb.get('download_report_2', '')
        if photo_report:
            msg1 = await bot.send_photo(chat_id=chat_id, photo=photo_report)
            sent_ids.append(msg1.message_id)
        msg2 = await bot.send_message(chat_id=chat_id, text=text)
        sent_ids.append(msg2.message_id)
        if text_2:
            if photo_report_2:
                msg3 = await bot.send_photo(chat_id=chat_id, photo=photo_report_2)
                sent_ids.append(msg3.message_id)
            msg4 = await bot.send_message(
                chat_id=chat_id, text=text_2,
                reply_markup=kb_client_group.pm_back_to_kb_with_ids(sent_ids))
            sent_ids.append(msg4.message_id)
        else:
            msg_back = await bot.send_message(
                chat_id=chat_id, text='⬇️',
                reply_markup=kb_client_group.pm_back_to_kb_with_ids(sent_ids))
            sent_ids.append(msg_back.message_id)
    else:
        await call.message.edit_text(
            text, reply_markup=kb_client_group.pm_back_to_knowledge_base)
    await call.answer()


async def pm_kb_back_to_menu(call: CallbackQuery):
    """Return to KB menu from subtopic in PM."""
    await call.message.edit_text(
        '<b>📚 База знаний</b>\n\n<i>Выберите интересующую тему:</i>',
        reply_markup=kb_client_group.pm_knowledge_base_menu)
    await call.answer()


async def pm_kb_back(call: CallbackQuery):
    """Back from multi-part KB topic in PM — delete all, show KB menu."""
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

    new_menu = await bot.send_message(
        chat_id=chat_id,
        text='<b>📚 База знаний</b>\n\n<i>Выберите интересующую тему:</i>',
        reply_markup=kb_client_group.pm_knowledge_base_menu)
    DB.User.update(mark=call.from_user.id, menu_id=new_menu.message_id)
    await call.answer()


async def pm_promo(call: CallbackQuery):
    """Show promo in PM."""
    try:
        await call.message.delete()
    except TelegramAPIError:
        ...
    new_menu = await bot.send_message(
        chat_id=call.from_user.id,
        text='<b>📢 Актуальные промо материалы</b>\n\n'
             'Перейдите по ссылке для просмотра актуальных баннеров и промо материалов.',
        reply_markup=kb_client_group.pm_promo_menu)
    DB.User.update(mark=call.from_user.id, menu_id=new_menu.message_id)
    await call.answer()


async def at_event(call: CallbackQuery):
    settings = DB.Settings.select()
    if not settings.event_starts:
        return await call.answer('Сейчас нет активных мероприятий', show_alert=True)

    qr_path = f"files/{call.from_user.id}.png"
    if not os.path.exists(qr_path):
        qr_id = DB.QRCode.add(call.from_user.id, "Мерч")
        await generate_qr_on_template(
            template_path="merch.png",
            qr_data=f"{qr_id}",
            output_path=qr_path,
            qr_size=450,
            qr_position=(43, 130),
            qr_color="#FF6914"
        )
        await new_prize(str(call.from_user.id), 'Мерч', str(qr_id))

    try:
        await call.message.delete()
    except TelegramAPIError:
        ...
    new_menu = await bot.send_photo(
        chat_id=call.from_user.id,
        photo=FSInputFile(qr_path),
        caption='<b>Вот ваш QR для получения подарка!</b>'
    )
    DB.User.update(mark=call.from_user.id, menu_id=new_menu.message_id)



async def logout(call: CallbackQuery):
    """Logout: delete auth data and show start menu"""
    DB.UserAuth.remove(call.from_user.id)

    await call.message.edit_caption(
        caption='<b>Вы вышли из аккаунта.\n\n'
                'Привет! Этот бот поможет тебе зарегистрироваться в качестве партнёра, '
                'предоставит быстрый доступ к порталу WINLINE PARTNERS, даст возможность получать '
                'актуальные новости и предложения, а также участвовать в мероприятиях!</b>',
        reply_markup=kb_client_menu.start_menu)
    await call.answer('Вы вышли из аккаунта')


async def get_file_id(message: Message):
    """Temp handler: admin sends photo in PM → bot replies with file_id."""
    if message.photo:
        file_id = message.photo[-1].file_id
        await message.reply(f'<b>Photo file_id:</b>\n<code>{file_id}</code>')


async def reg_help(call: CallbackQuery):
    await call.answer('🔧 Функционал в разработке', show_alert=True)


# ==================== Сценарий 3: Мероприятие (deep link + анкета) ====================

async def _generate_event_qr(user_id: int) -> str:
    """Generate QR for event, return path. Creates QRCode record if needed."""
    qr_path = f"files/{user_id}.png"
    if not os.path.exists(qr_path):
        qr_id = DB.QRCode.add(user_id, "Мерч")
        await generate_qr_on_template(
            template_path="merch.png",
            qr_data=f"{qr_id}",
            output_path=qr_path,
            qr_size=450,
            qr_position=(43, 130),
            qr_color="#FF6914"
        )
        await new_prize(str(user_id), 'Мерч', str(qr_id))
    return qr_path


async def _send_event_qr(user_id: int, is_partner: bool = False) -> Message:
    """Send QR photo with appropriate button underneath."""
    qr_path = await _generate_event_qr(user_id)
    reply_markup = None if is_partner else kb_client_menu.event_qr_new_menu
    new_menu = await bot.send_photo(
        chat_id=user_id,
        photo=FSInputFile(qr_path),
        caption='<b>Вот ваш QR для получения подарка!</b>',
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


def register_handlers_client_main(dp: Dispatcher):
    dp.message.register(get_file_id, F.photo, F.chat.type == 'private', config.admin_filter)
    # Deep link /start event — BEFORE generic /start
    dp.message.register(start_event, _is_event_deeplink, F.chat.type == 'private')
    dp.message.register(main_menu, Command(commands="start"), F.chat.type == 'private')
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
    dp.callback_query.register(authorized_stub, F.data == 'client_offers')
    dp.callback_query.register(authorized_stub, F.data == 'client_socials')
    dp.callback_query.register(pm_promo, F.data == 'client_promo')
    dp.callback_query.register(authorized_stub, F.data == 'client_chat_manager')
    dp.callback_query.register(at_event, F.data == 'client_at_event')
    dp.callback_query.register(logout, F.data == 'client_logout')
    dp.callback_query.register(reg_help, F.data == 'client_reg_help')
    dp.callback_query.register(registration, F.data == 'client_registration')
    dp.callback_query.register(start_event_anketa_callback, F.data == 'client_event_anketa')
    dp.callback_query.register(subscribe, F.data == 'client_check_subscribe')
    # Email auth FSM handler
    dp.message.register(process_auth_email, FsmAuth.wait_email, F.chat.type == 'private')
    # Event anketa FSM handlers
    dp.message.register(process_anketa_text, FsmEventAnketa.answering, F.chat.type == 'private')
    dp.callback_query.register(process_anketa_choice, F.data.startswith('anketa_choice:'), FsmEventAnketa.answering)
    dp.message.register(wait_rl_name, FsmRegistration.wait_rl_name)
    dp.message.register(wait_phone, FsmRegistration.wait_phone)
    dp.callback_query.register(pick_role, F.data.startswith('pick:role'))
    dp.message.register(wait_about_role, FsmRegistration.wait_about_role)
    dp.callback_query.register(wait_traff, F.data.startswith('pick:traff'))
    dp.callback_query.register(pm, F.data == 'client_pm')
