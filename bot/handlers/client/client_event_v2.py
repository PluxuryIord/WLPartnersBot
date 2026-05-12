"""
Сценарий 3 v2: расширенный поток мероприятия.

Поток (ровно как в админ-панели → раздел «Сценарии»):
  start → event_partner_check (выбор: работаю/не работаю)
    ├─ «Работаю»     → event_verify_promo → email → OTP → site check → раффл-билет
    └─ «Не работаю»  → анкета (anketa_role, существующий FsmEventAnketa)
                       → event_registration_promo → site → возврат к email-flow

Тексты и кнопки — целиком из bot_scenarios. Логика залочена в коде.
"""
import asyncio
import hashlib
import hmac
import json as json_mod
import logging
import os
import re
import secrets as _secrets
import time as _time
from typing import Optional

import aiohttp
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.initialization.config import config
from bot.utils.announce_bot import bot
from bot.integrations import DB
from bot.integrations.winline.api import get_user_by_email, get_user_websites
from bot.states.wait_question import FsmEventV2
from bot.utils.dynamic_kb import get_screen_kb
from bot.utils.resend_mailer import is_configured as mailer_is_configured, send_otp_email
from bot.utils.scenario_texts import get_text, send_screen_message

logger = logging.getLogger('wl_bot.event_v2')

OTP_TTL_SEC = 600
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SEC = 60


def _otp_keyboard(can_resend: bool = True):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    rows = []
    if can_resend:
        rows.append([InlineKeyboardButton(text='📧 Отправить код повторно', callback_data='event_v2_otp_resend')])
    rows.append([InlineKeyboardButton(text='✏️ Изменить email', callback_data='event_v2_otp_change_email')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _otp_prompt_text(email: str) -> str:
    base = (get_text('auth_flow', 'otp_prompt', email=email)
            or f'<b>📬 Код отправлен на {email}</b>\n\nВведите 6-значный код. Действителен 10 минут.')
    return base + '\n\n<i>Письмо может прийти в течение 1–2 минут. Проверьте папку «Спам».</i>'


# ─── Helpers ────────────────────────────────────────────────────────────────

async def _show_screen(user_id: int, screen_id: str, fallback: str = '', state: Optional[FSMContext] = None,
                       message_key: str = 'main_text', extra_text: str = '', extra_kb=None):
    """Удалить меню юзера и показать экран сценария: текст + кнопки + опц. фото."""
    user_data = DB.User.select(user_id)
    menu_id = user_data.menu_id if user_data else None
    if menu_id:
        try:
            await bot.delete_message(user_id, menu_id)
        except TelegramAPIError:
            pass

    text = get_text(screen_id, message_key) or fallback
    if extra_text:
        text = f'{text}\n\n{extra_text}' if text else extra_text
    kb = extra_kb or get_screen_kb(screen_id)
    new_menu = await send_screen_message(bot, user_id, screen_id, text, reply_markup=kb, message_key=message_key)
    DB.User.update(mark=user_id, menu_id=new_menu.message_id)
    return new_menu


async def _has_active_site(email: str) -> bool:
    """Проверка: есть ли у юзера хотя бы одна одобренная площадка на платформе."""
    try:
        info = await get_user_by_email(email)
        uid = info.get('id') if info else None
        if not uid:
            return False
        sites = await get_user_websites(int(uid), email) or []
        return any(s.get('status') == 1 for s in sites)
    except Exception as e:
        logger.warning(f'[event_v2] site check failed for {email}: {e}')
        return False


async def _issue_raffle_ticket(user_id: int, email: str, event_id: int = 0, ticket_code: Optional[str] = None) -> dict:
    """Запрос к панели: выдать (или вернуть существующий) билет розыгрыша.

    Возвращает dict {ok, ticket_code|ticket_number, disabled}. {} при ошибке сети.
    """
    base = (config.admin_panel_webhook or '').rstrip('/').rsplit('/api/', 1)[0]
    if not base:
        base = 'https://winlinepartners.ru'
    url = f'{base}/api/internal/event-raffle/issue'
    payload = {'event_id': event_id, 'telegram_id': user_id, 'user_id': user_id, 'email': email}
    if ticket_code:
        payload['ticket_code'] = ticket_code
    body = json_mod.dumps(payload, separators=(',', ':')).encode('utf-8')
    headers = {'Content-Type': 'application/json'}
    secret = config.admin_webhook_secret or ''
    if secret:
        headers['x-webhook-secret'] = secret
        headers['x-webhook-signature'] = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    timeout = aiohttp.ClientTimeout(total=10)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.post(url, data=body, headers=headers) as r:
                if r.status != 200:
                    logger.error(f'[event_v2] raffle issue HTTP {r.status}')
                    return {}
                return await r.json()
    except Exception as e:
        logger.error(f'[event_v2] raffle issue error: {e}')
        return {}


async def _show_congrats(user_id: int, ticket_label: str):
    fallback = (
        f'<b>🎉 Поздравляем! Ты стал участником розыгрыша.\n\n'
        f'Твой номер: №{ticket_label}\n\n'
        f'Информация о победителях придёт 27 мая до 15:00</b>'
    )
    text = (get_text('event_congrats', 'text') or fallback).replace('№******', f'№{ticket_label}')
    text = text.replace('{ticket}', ticket_label)

    # Достаём клавиатуру из сценария и гарантируем что есть кнопка «Хочу мерч».
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    src_kb = get_screen_kb('event_congrats')
    rows = []
    if src_kb is not None and src_kb.inline_keyboard:
        rows = [list(r) for r in src_kb.inline_keyboard]
    has_merch_btn = any(
        (btn.callback_data == 'event_v2_want_merch') for r in rows for btn in r
    )
    if not has_merch_btn:
        rows.insert(0, [InlineKeyboardButton(text='🎁 Хочу мерч', callback_data='event_v2_want_merch')])
    extra_kb = InlineKeyboardMarkup(inline_keyboard=rows)

    await _show_screen(user_id, 'event_congrats', fallback=text, extra_text='', extra_kb=extra_kb)
    # Override text rendered by _show_screen since it pulled raw template.
    # ВАЖНО: явно прокидываем reply_markup, иначе edit_message_* затирает кнопки.
    user_data = DB.User.select(user_id)
    if user_data and user_data.menu_id:
        try:
            from bot.utils.scenario_texts import get_media
            media = get_media('event_congrats', 'text')
            if media and media.get('url'):
                await bot.edit_message_caption(
                    chat_id=user_id, message_id=user_data.menu_id,
                    caption=text, reply_markup=extra_kb,
                )
            else:
                await bot.edit_message_text(
                    text, chat_id=user_id, message_id=user_data.menu_id,
                    reply_markup=extra_kb,
                )
        except TelegramAPIError:
            pass


# ─── Flow: entry point ──────────────────────────────────────────────────────

async def event_v2_start(call: CallbackQuery, state: FSMContext):
    """Замена client_at_event: показывает экран event_partner_check."""
    if state and await state.get_state():
        await state.clear()
    try:
        await call.message.delete()
    except TelegramAPIError:
        pass
    await _show_screen(
        call.from_user.id, 'event_partner_check',
        fallback='<b>Вы уже работаете с WINLINE PARTNERS?</b>',
    )
    await call.answer()


async def event_v2_partner_yes(call: CallbackQuery, state: FSMContext):
    """«Работаю с WINLINE PARTNERS» → промо верификации."""
    if state and await state.get_state():
        await state.clear()
    try:
        await call.message.delete()
    except TelegramAPIError:
        pass
    await _show_screen(
        call.from_user.id, 'event_verify_promo',
        fallback='<b>Верифицируй свой партнёрский аккаунт</b>',
        message_key='promo',
    )
    await call.answer()


async def event_v2_want_merch(call: CallbackQuery, state: FSMContext):
    """«🎁 Хочу мерч» на экране event_congrats у уже-партнёра с раффл-билетом.
    Запускает обычную анкету. Флаг skip_raffle_promo гарантирует, что в конце
    анкеты бот выдаст мерч-QR, но НЕ пришлёт второй раз раффл-промо."""
    from bot.handlers.client.client_main import _start_event_anketa  # type: ignore
    try:
        await call.message.delete()
    except TelegramAPIError:
        pass
    await call.answer()
    try:
        await _start_event_anketa(call.message, call.from_user.id, state)
        # state уже выставлен в _start_event_anketa, дополняем флагом
        await state.update_data(skip_raffle_promo=True)
    except Exception as e:
        logger.error(f'[event_v2] want_merch → anketa failed: {e}')
        try:
            await bot.send_message(call.from_user.id, '⚠️ Не удалось запустить анкету, попробуйте ещё раз.')
        except Exception:
            pass


async def event_v2_partner_no(call: CallbackQuery, state: FSMContext):
    """«Не работаю с WINLINE PARTNERS» → анкета (anketa_role).

    Идём в анкету ВСЕГДА, даже если юзер уже авторизован — он только что
    явно сказал что он не партнёр, значит анкета релевантна. Старый
    обёрточный start_event_anketa_callback в этом случае пропускал бы
    анкету и сразу слал мерч-QR.
    """
    from bot.handlers.client.client_main import _start_event_anketa  # type: ignore
    try:
        await call.message.delete()
    except TelegramAPIError:
        pass
    await call.answer()
    try:
        await _start_event_anketa(call.message, call.from_user.id, state)
    except Exception as e:
        logger.error(f'[event_v2] start_event_anketa failed: {e}')
        try:
            await bot.send_message(call.from_user.id, '⚠️ Не удалось запустить анкету, попробуйте ещё раз.')
        except Exception:
            pass


async def event_v2_verify(call: CallbackQuery, state: FSMContext):
    """«Верифицироваться» → запрос email."""
    try:
        await call.message.delete()
    except TelegramAPIError:
        pass
    menu = await bot.send_message(
        call.from_user.id,
        get_text('event_email_prompt', 'prompt') or '<b>📧 Введите email, указанный при регистрации на платформе</b>',
    )
    DB.User.update(mark=call.from_user.id, menu_id=menu.message_id)
    await state.set_state(FsmEventV2.wait_email)
    await state.update_data(event_v2_menu=menu)
    await call.answer()


async def event_v2_back(call: CallbackQuery, state: FSMContext):
    """«Вернуться назад» из верификации → стартовое меню.

    back_to_start takes only `call` (no state arg) — passing state used to
    raise TypeError, which the outer except silently swallowed and made the
    button look broken.
    """
    if state and await state.get_state():
        await state.clear()
    from bot.handlers.client.client_main import back_to_start
    try:
        await back_to_start(call)
    except Exception as e:
        logger.warning(f'[event_v2] back_to_start failed: {e}')
        await call.answer()


async def event_v2_registered(call: CallbackQuery, state: FSMContext):
    """«Я зарегистрирован» из инструкции по регистрации → переход в email-флоу."""
    await event_v2_verify(call, state)


# ─── Email + OTP ────────────────────────────────────────────────────────────

async def process_event_email(message: Message, state: FSMContext):
    try:
        await message.delete()
    except TelegramAPIError:
        pass
    data = await state.get_data()
    menu_msg = data.get('event_v2_menu')
    email = (message.text or '').strip().lower()

    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        if menu_msg:
            try:
                await menu_msg.edit_text(
                    get_text('auth_flow', 'email_error')
                    or '<b>❌ Некорректный формат email\n\n📧 Введите email ещё раз</b>'
                )
            except TelegramAPIError:
                pass
        return

    # IAP-проверка ДО отправки кода
    info = await get_user_by_email(email)
    if not info or not info.get('id'):
        if menu_msg:
            try:
                await menu_msg.edit_text(
                    '<b>❌ Email не найден на платформе</b>\n\n'
                    'Введите другой email или сначала пройдите регистрацию.'
                )
            except TelegramAPIError:
                pass
        return
    if info.get('status') is not None and info.get('status') != 1:
        if menu_msg:
            try:
                await menu_msg.edit_text('<b>🚫 Аккаунт заблокирован</b>')
            except TelegramAPIError:
                pass
        await state.clear()
        return

    if not mailer_is_configured():
        await state.update_data(event_v2_email=email)
        await _after_email_confirmed(message.from_user.id, email, menu_msg, state)
        return

    code = f'{_secrets.randbelow(1_000_000):06d}'
    await send_otp_email(email, code)  # результат отправки игнорируем — пишем как будто отправили

    await state.update_data(
        event_v2_email=email,
        event_v2_otp=code,
        event_v2_otp_expires=int(_time.time()) + OTP_TTL_SEC,
        event_v2_otp_attempts=0,
        event_v2_otp_resend_at=int(_time.time()) + OTP_RESEND_COOLDOWN_SEC,
    )
    await state.set_state(FsmEventV2.wait_otp)
    if menu_msg:
        try:
            await menu_msg.edit_text(_otp_prompt_text(email), reply_markup=_otp_keyboard())
        except TelegramAPIError:
            pass


async def process_event_otp(message: Message, state: FSMContext):
    try:
        await message.delete()
    except TelegramAPIError:
        pass
    data = await state.get_data()
    menu_msg = data.get('event_v2_menu')
    email = data.get('event_v2_email')
    expected = data.get('event_v2_otp')
    expires = int(data.get('event_v2_otp_expires') or 0)
    attempts = int(data.get('event_v2_otp_attempts') or 0)

    if not expected or not email:
        await state.clear()
        return

    if int(_time.time()) > expires:
        if menu_msg:
            try:
                await menu_msg.edit_text('<b>⏰ Код истёк</b>\n\nЗапросите новый: /start')
            except TelegramAPIError:
                pass
        await state.clear()
        return

    entered_digits = ''.join(ch for ch in (message.text or '') if ch.isdigit())
    if entered_digits != expected:
        attempts += 1
        if attempts >= OTP_MAX_ATTEMPTS:
            if menu_msg:
                try:
                    await menu_msg.edit_text('<b>🚫 Слишком много попыток</b>\n\nЗапросите новый код: /start')
                except TelegramAPIError:
                    pass
            await state.clear()
            return
        await state.update_data(event_v2_otp_attempts=attempts)
        if menu_msg:
            try:
                await menu_msg.edit_text(
                    f'<b>❌ Неверный код</b>\n\nОсталось попыток: {OTP_MAX_ATTEMPTS - attempts}'
                )
            except TelegramAPIError:
                pass
        return

    await _after_email_confirmed(message.from_user.id, email, menu_msg, state)


async def event_v2_otp_resend(call: CallbackQuery, state: FSMContext):
    """Юзер нажал «Отправить код повторно» на экране OTP."""
    data = await state.get_data()
    email = data.get('event_v2_email')
    menu_msg = data.get('event_v2_menu')
    resend_at = int(data.get('event_v2_otp_resend_at') or 0)

    if not email:
        await call.answer('Сессия истекла, начните сначала', show_alert=True)
        return

    now = int(_time.time())
    if now < resend_at:
        left = resend_at - now
        await call.answer(f'Подождите ещё {left} сек.', show_alert=False)
        return

    code = f'{_secrets.randbelow(1_000_000):06d}'
    await send_otp_email(email, code)
    await state.update_data(
        event_v2_otp=code,
        event_v2_otp_expires=now + OTP_TTL_SEC,
        event_v2_otp_attempts=0,
        event_v2_otp_resend_at=now + OTP_RESEND_COOLDOWN_SEC,
    )
    if menu_msg:
        try:
            await menu_msg.edit_text(_otp_prompt_text(email), reply_markup=_otp_keyboard())
        except TelegramAPIError:
            pass
    await call.answer('Код отправлен повторно')


async def event_v2_otp_change_email(call: CallbackQuery, state: FSMContext):
    """Юзер нажал «Изменить email» — возвращаемся к вводу email."""
    data = await state.get_data()
    menu_msg = data.get('event_v2_menu')
    # Чистим OTP-данные, оставляем только меню
    await state.set_state(FsmEventV2.wait_email)
    await state.update_data(
        event_v2_otp=None, event_v2_otp_expires=None,
        event_v2_otp_attempts=0, event_v2_otp_resend_at=None,
        event_v2_email=None,
    )
    if menu_msg:
        try:
            await menu_msg.edit_text(
                get_text('event_email_prompt', 'prompt')
                or '<b>📧 Введите email, указанный при регистрации на платформе</b>'
            )
        except TelegramAPIError:
            pass
    await call.answer()


async def _after_email_confirmed(user_id: int, email: str, menu_msg, state: FSMContext):
    """Email подтверждён → проверка площадки → билет либо ожидание создания."""
    # Save auth like _finalize_auth does (so user стал «Партнёром»)
    try:
        existing = DB.UserAuth.select(user_id)
        if existing:
            DB.UserAuth.update(user_id, email=email, token=None)
        else:
            DB.UserAuth.add(user_id, email, token=None)
        DB.User.update(user_id, registered=True)
    except Exception as e:
        logger.warning(f'[event_v2] save auth failed: {e}')

    if menu_msg:
        try:
            await menu_msg.edit_text(get_text('event_email_confirmed', 'confirmed') or '<b>✅ Почта подтверждена</b>')
        except TelegramAPIError:
            pass
    await asyncio.sleep(0.6)

    has_site = await _has_active_site(email)
    if has_site:
        await _award_ticket(user_id, email, state)
        return

    # Нет активной площадки → показываем event_site_wait
    await state.set_state(FsmEventV2.wait_site_check)
    await state.update_data(event_v2_email=email)
    await _show_screen(
        user_id, 'event_site_wait',
        fallback='<b>Создай площадку и возвращайся</b>\n\nКогда создашь — нажми «Проверить».',
        message_key='text',
    )


async def event_v2_site_check_again(call: CallbackQuery, state: FSMContext):
    """Кнопка «Проверить» — повторная проверка площадки."""
    data = await state.get_data()
    email = data.get('event_v2_email')
    if not email:
        await call.answer('Сессия истекла, начните заново', show_alert=True)
        await state.clear()
        return
    await call.answer('Проверяем…')
    has_site = await _has_active_site(email)
    if not has_site:
        try:
            await call.message.edit_text(
                (get_text('event_site_wait', 'text') or '<b>Создай площадку и возвращайся</b>')
                + '\n\n<i>Площадка пока не найдена.</i>',
                reply_markup=get_screen_kb('event_site_wait'),
            )
        except TelegramAPIError:
            pass
        return
    try:
        await call.message.delete()
    except TelegramAPIError:
        pass
    await _award_ticket(call.from_user.id, email, state)


async def _award_ticket(user_id: int, email: str, state: FSMContext):
    # «Не работаю» юзер уже имеет merch event_code → ticket_code = его суффикс.
    # «Работаю» юзер кода не получает (не учитывается в статистике QR) →
    # генерируем независимый ticket_code локально.
    from bot.handlers.client.client_main import get_user_merch_code
    merch_code = await get_user_merch_code(user_id)
    if merch_code:
        suffix = merch_code.split('EVT-', 1)[-1]
    else:
        # Use cryptographically random suffix — md5(user_id + time.time()) was
        # predictable to a few seconds and known user_id.
        import secrets as _secrets_mod
        suffix = _secrets_mod.token_hex(4).upper()
    resp = await _issue_raffle_ticket(user_id, email, event_id=0, ticket_code=suffix)
    await state.clear()
    if not resp:
        await bot.send_message(user_id, '⚠️ Временная ошибка выдачи билета. Попробуйте ещё раз чуть позже.')
        return
    if resp.get('disabled'):
        await bot.send_message(user_id, get_text('event_congrats', 'disabled') or '<b>✅ Спасибо за участие!</b>')
        return
    label = resp.get('ticket_code') or (f"{resp.get('ticket_number', 0):06d}" if resp.get('ticket_number') is not None else '------')
    await _show_congrats(user_id, label)


# ─── Registration push (для «Не работаю» после анкеты) ──────────────────────

async def show_registration_promo(user_id: int):
    """Показать экран промо регистрации напрямую (без callback).

    Вызывается из _anketa_finish после выдачи QR мерча. Не удаляет
    предыдущее меню — QR мерча должен остаться у юзера в чате.
    """
    fallback = ('<b>Хочешь выиграть 1 из 10 мячей, подписанным легендой '
                'футбола и амбассадором WINLINE, Роналдиньо?</b>\n\n'
                'Пройди регистрацию на сайте WINLINE PARTNERS')
    text = get_text('event_registration_promo', 'promo') or fallback
    kb = get_screen_kb('event_registration_promo')
    new_menu = await send_screen_message(
        bot, user_id, 'event_registration_promo', text,
        reply_markup=kb, message_key='promo',
    )
    DB.User.update(mark=user_id, menu_id=new_menu.message_id)


async def event_v2_registration_promo(call: CallbackQuery, state: FSMContext):
    """Показать экран event_registration_promo (после анкеты + QR мерч)."""
    try:
        await call.message.delete()
    except TelegramAPIError:
        pass
    await _show_screen(
        call.from_user.id, 'event_registration_promo',
        fallback='<b>Пройди регистрацию на сайте WINLINE PARTNERS</b>',
        message_key='promo',
    )
    await call.answer()


async def event_v2_registration_instructions(call: CallbackQuery, state: FSMContext):
    """«Пройти регистрацию» → инструкция."""
    try:
        await call.message.delete()
    except TelegramAPIError:
        pass
    await _show_screen(
        call.from_user.id, 'event_registration_instructions',
        fallback='<b>Перейдите на сайт партнёрской программы и зарегистрируйтесь.</b>',
        message_key='text',
    )
    await call.answer()


# ─── Registration ───────────────────────────────────────────────────────────

def register(dp):
    """Регистрация хендлеров. Вызывается из client_main.register_client_handlers."""
    from aiogram import F
    dp.callback_query.register(event_v2_start,                F.data == 'client_at_event')
    dp.callback_query.register(event_v2_partner_yes,          F.data == 'event_v2_partner_yes')
    dp.callback_query.register(event_v2_partner_no,           F.data == 'event_v2_partner_no')
    dp.callback_query.register(event_v2_want_merch,           F.data == 'event_v2_want_merch')
    dp.callback_query.register(event_v2_verify,               F.data == 'event_v2_verify')
    dp.callback_query.register(event_v2_back,                 F.data == 'event_v2_back')
    dp.callback_query.register(event_v2_registered,           F.data == 'event_v2_registered')
    dp.callback_query.register(event_v2_site_check_again,     F.data == 'event_v2_site_check')
    dp.callback_query.register(event_v2_registration_promo,   F.data == 'event_v2_register_promo')
    dp.callback_query.register(event_v2_registration_instructions, F.data == 'event_v2_register_instructions')

    dp.message.register(process_event_email, FsmEventV2.wait_email, F.chat.type == 'private')
    dp.message.register(process_event_otp,   FsmEventV2.wait_otp,   F.chat.type == 'private')
    dp.callback_query.register(event_v2_otp_resend,        F.data == 'event_v2_otp_resend')
    dp.callback_query.register(event_v2_otp_change_email,  F.data == 'event_v2_otp_change_email')
