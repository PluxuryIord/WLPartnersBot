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
from bot.states.wait_question import FsmRegistration
from bot.utils.qr_code import generate_qr_on_template

if TYPE_CHECKING:
    from aiogram import Dispatcher
    from aiogram.fsm.context import FSMContext
    from aiogram.types import Message, CallbackQuery, User

    from typing import Union

from aiogram import F
from aiogram.filters.command import Command
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
import json


async def start_message(first_name, user_id):
    link_user = generate_user_hlink(user_id=user_id, text_link=first_name)
    return bot_texts.menu['main_menu'].format(first_name=link_user)


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
        if DB.Settings.select().event_starts:
            kb = kb_client_menu.event_menu
            caption_text = '<b>Приветственный текст для мероприятия\n\nЧтобы продолжить, пожалуйста, заполните небольшую анкету</b>'
        else:
            kb = kb_client_menu.start_menu
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
            auth_data = DB.UserAuth.select(user.id)
            if auth_data:
                email_text = f'\n\n📧 <b>Email:</b> {auth_data.email}' if auth_data.email else ''
                new_menu_id = await bot.send_photo(
                    chat_id=user.id,
                    caption=f'<b>✅ Вы авторизованы</b>{email_text}',
                    photo='AgACAgIAAxkBAAJ1zWhdevQQMSnK7IPyyuQVbD13znboAAJI9jEbyLfpSung7LZvwELaAQADAgADeAADNgQ',
                    reply_markup=kb_client_menu.authorized_menu)
            elif user_data.registered:
                if user_data.role != 'Рекламодатель':
                    text = await start_message(update.from_user.first_name, user.id)
                else:
                    text = '<b>Отлично! Теперь ты можешь получить мерч на стенде Winline Partners с помощью персонального QR кода</b>'
                new_menu_id = await bot.send_message(
                    user.id, text,
                    reply_markup=kb_client_menu.main_menu(DB.Admin.select(where=(DB.Admin.admin_id == user.id))))
            else:
                yesterday = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=3)
                if user_data.date_reg <= yesterday:
                    DB.User.update(update.from_user.id, registered=True)
                    await new_user(str(update.from_user.id), str(update.from_user.full_name),
                                   str(update.from_user.username),
                                   user_data.role, user_data.graph, user_data.rl_full_name, user_data.phone_number)
                    qr_id = DB.QRCode.add(update.from_user.id, "Мерч")
                    await generate_qr_on_template(
                        template_path="merch.png",
                        qr_data=f"{qr_id}",
                        output_path=f"files/{update.from_user.id}.png",
                        qr_size=450,
                        qr_position=(43, 130),
                        qr_color="#FF6914"
                    )
                    await new_prize(str(update.from_user.id), 'Мерч', str(qr_id))
                    if DB.Settings.select().event_starts:
                        new_menu_id = await bot.send_photo(
                            chat_id=user.id,
                            photo=FSInputFile(f"files/{update.from_user.id}.png"),
                            caption='<b>Вот ваш QR для получения подарка!</b>'
                        )
                    elif user_data.role == 'Рекламодатель':
                        user_data = DB.User.select(update.from_user.id)
                        return await main_menu(update, update.from_user, user_data, state)
                    else:
                        link = hlink('@winline_affiliate', 'https://t.me/m/hcj7_tDRMmEy')
                        new_menu_id = await bot.send_message(
                            chat_id=user.id, text=f'<b>Это - {link}, наш Affiliate менеджер. Напиши ему!)</b>',
                            reply_markup=kb_client_menu.pm)
                else:
                    if DB.Settings.select().event_starts:
                        kb = kb_client_menu.event_menu
                        caption_text = '<b>Приветственный текст для мероприятия\n\nЧтобы продолжить, пожалуйста, заполните небольшую анкету</b>'
                    else:
                        kb = kb_client_menu.start_menu
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
    await telegram.edit_text(
        call.message,
        await start_message(call.from_user.full_name, call.from_user.id),
        reply_markup=kb_client_menu.main_menu(DB.Admin.select(where=(DB.Admin.admin_id == call.from_user.id))))
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
        caption='<b>Чтобы стать партнёром — необходимо пройти регистрацию на '
                '<a href="https://partners.winline.ru">платформе</a>. '
                'Бот поможет пройти все необходимые шаги</b>',
        reply_markup=kb_client_menu.registration_partners_menu)
    await call.answer()


async def already_registered(call: CallbackQuery):
    await show_auth_screen(call)


async def authorized_stub(call: CallbackQuery):
    await call.answer('🔧 Функционал в разработке', show_alert=True)


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


async def on_webapp_auth(message: Message):
    """Handle WebApp sendData after successful auth"""
    try:
        data = json.loads(message.web_app_data.data)
    except Exception:
        return

    if not data.get('ok'):
        return

    email = data.get('email', '')
    user_id = message.from_user.id

    # Delete the old menu message
    user_data = DB.User.select(user_id)
    if user_data:
        await telegram.delete_message(chat_id=user_id, message_id=user_data.menu_id)

    text = f'<b>✅ Вы авторизованы</b>\n\n📧 <b>Email:</b> {email}' if email else '<b>✅ Вы авторизованы</b>'

    new_menu = await bot.send_photo(
        chat_id=user_id,
        caption=text,
        photo='AgACAgIAAxkBAAJ1zWhdevQQMSnK7IPyyuQVbD13znboAAJI9jEbyLfpSung7LZvwELaAQADAgADeAADNgQ',
        reply_markup=kb_client_menu.authorized_menu)
    DB.User.update(mark=user_id, menu_id=new_menu.message_id)


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


async def reg_help(call: CallbackQuery):
    await call.answer('🔧 Функционал в разработке', show_alert=True)


async def wait_about_role(message: Message, state: FSMContext):
    await message.delete()
    data = await state.get_data()
    await state.update_data(role=message.text)
    menu: Message = data['menu_message']
    await menu.edit_text('<b>Отлично! Осталось подписаться на канал '
                         '@WinlinePartners и можно приходить на стенд Winline Partners, '
                         'чтобы получить мерч!</b>', reply_markup=kb_client_menu.subscribe)
    DB.User.update(message.from_user.id, role=message.text)


def register_handlers_client_main(dp: Dispatcher):
    dp.message.register(main_menu, Command(commands="start"), F.chat.type == 'private')
    dp.callback_query.register(telegram.delete_message, F.data == 'client_delete_message')
    dp.callback_query.register(back_menu, F.data == 'client_back_menu')
    dp.callback_query.register(back_to_start, F.data == 'client_back_to_start')
    dp.callback_query.register(existing_partner, F.data == 'client_existing_partner')
    dp.callback_query.register(new_partner, F.data == 'client_new_partner')
    dp.callback_query.register(already_registered, F.data == 'client_already_registered')
    dp.callback_query.register(authorized_stub, F.data == 'client_knowledge_base')
    dp.callback_query.register(authorized_stub, F.data == 'client_offers')
    dp.callback_query.register(authorized_stub, F.data == 'client_socials')
    dp.callback_query.register(authorized_stub, F.data == 'client_promo')
    dp.callback_query.register(authorized_stub, F.data == 'client_chat_manager')
    dp.callback_query.register(at_event, F.data == 'client_at_event')
    dp.callback_query.register(logout, F.data == 'client_logout')
    dp.callback_query.register(reg_help, F.data == 'client_reg_help')
    dp.message.register(on_webapp_auth, F.content_type == ContentType.WEB_APP_DATA)
    dp.callback_query.register(registration, F.data == 'client_registration')
    dp.callback_query.register(subscribe, F.data == 'client_check_subscribe')
    dp.message.register(wait_rl_name, FsmRegistration.wait_rl_name)
    dp.message.register(wait_phone, FsmRegistration.wait_phone)
    dp.callback_query.register(pick_role, F.data.startswith('pick:role'))
    dp.message.register(wait_about_role, FsmRegistration.wait_about_role)
    dp.callback_query.register(wait_traff, F.data.startswith('pick:traff'))
    dp.callback_query.register(pm, F.data == 'client_pm')
