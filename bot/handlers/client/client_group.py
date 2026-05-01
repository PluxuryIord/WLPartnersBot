"""
Scenario 4 — Group chat support bot handlers.
Bot works in partner group chats providing commands, knowledge base, and promo materials.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram import Dispatcher
    from aiogram.types import ChatMemberUpdated

from aiogram import F
from aiogram.filters.command import Command
from aiogram.types import Message, CallbackQuery
from aiogram.enums import ChatMemberStatus

from bot.integrations import DB
from bot.initialization import bot_texts
from bot.utils.announce_bot import bot
from bot.keyboards.client import kb_client_group
from bot.utils.scenario_texts import get_text, send_screen_message
from bot.utils.dynamic_kb import get_screen_kb, get_screen_text, reload as reload_scenarios
import logging
import time
import aiohttp
from bot.initialization import config

# ── Group approval cache ─────────────────────────────────────────────────────

_approved_cache: dict[int, tuple[bool, float]] = {}  # chat_id -> (approved, timestamp)
_CACHE_TTL = 60  # seconds


async def is_group_approved(chat_id: int) -> bool:
    """Check if group is approved in admin panel. Cached for 60s."""
    now = time.time()
    cached = _approved_cache.get(chat_id)
    if cached and now - cached[1] < _CACHE_TTL:
        return cached[0]
    try:
        base = (config.admin_panel_webhook or '').rsplit('/api/', 1)[0]
        if not base:
            logging.warning(f'[group_approved] no base URL configured')
            return True
        url = f"{base}/api/broadcasts/groups/check-approved/{chat_id}"
        logging.info(f'[group_approved] checking {url}')
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                logging.info(f'[group_approved] response: {resp.status}')
                if resp.status == 200:
                    data = await resp.json()
                    approved = data.get('approved', True)
                    logging.info(f'[group_approved] chat_id={chat_id} approved={approved}')
                    _approved_cache[chat_id] = (approved, now)
                    return approved
                else:
                    body = await resp.text()
                    logging.warning(f'[group_approved] {resp.status}: {body[:200]}')
    except Exception as e:
        logging.warning(f'[group_approved] check failed: {e}')
    return True  # fallback: allow if panel unavailable


# ── Bot membership tracking ──────────────────────────────────────────────────

async def _notify_panel_membership(chat_id: int, title: str, chat_type: str, action: str):
    """POST membership change to admin panel."""
    url = config.admin_panel_webhook
    secret = config.admin_panel_webhook_secret
    if not url:
        return
    base = url.rsplit('/api/', 1)[0]
    membership_url = f"{base}/api/broadcasts/bot-membership"
    payload = {'chat_id': chat_id, 'title': title or '', 'chat_type': chat_type, 'action': action}
    headers = {'Content-Type': 'application/json'}
    if secret:
        headers['x-webhook-secret'] = secret
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(membership_url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logging.warning(f'[membership_webhook] {resp.status}: {body[:200]}')
                else:
                    logging.info(f'[membership_webhook] OK: {action} {chat_type} {chat_id}')
    except Exception as e:
        logging.warning(f'[membership_webhook] Failed: {e}')



async def bot_added_to_group(event: ChatMemberUpdated):
    """Auto-track when bot is added to a group."""
    chat = event.chat
    new_status = event.new_chat_member.status

    if new_status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR):
        existing = DB.GroupChat.select(mark=chat.id)
        if existing:
            DB.GroupChat.update(mark=chat.id, is_active=True, title=chat.title or '')
        else:
            DB.GroupChat.add(chat_id=chat.id, title=chat.title or '')
        await _notify_panel_membership(chat.id, chat.title or '', chat.type, 'added')


async def bot_removed_from_group(event: ChatMemberUpdated):
    """Auto-track when bot is removed from a group."""
    new_status = event.new_chat_member.status

    if new_status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
        existing = DB.GroupChat.select(mark=event.chat.id)
        if existing:
            DB.GroupChat.update(mark=event.chat.id, is_active=False)
        await _notify_panel_membership(event.chat.id, event.chat.title or '', event.chat.type, 'removed')

# ── Group chat commands ───────────────────────────────────────────────────────

def _get_kb(screen_id, fallback_kb):
    """Get keyboard from scenarios, fallback to hardcoded."""
    kb = get_screen_kb(screen_id)
    return kb or fallback_kb


def _get_txt(screen_id, fallback):
    """Get first message text from scenarios, fallback to provided."""
    t = get_screen_text(screen_id)
    return t if t else fallback


async def group_menu(message: Message):
    """Main support menu — inline buttons."""
    if not await is_group_approved(message.chat.id):
        return
    reload_scenarios()
    text = _get_txt('group_menu', '<b>📋 Меню поддержки WINLINE PARTNERS</b>')
    await message.reply(text, reply_markup=_get_kb('group_menu', kb_client_group.group_main_menu))


async def group_main_menu_callback(call: CallbackQuery):
    """Return to main group menu from any section."""
    if not await is_group_approved(call.message.chat.id):
        return await call.answer()
    text = _get_txt('group_menu', '<b>📋 Меню поддержки WINLINE PARTNERS</b>')
    await call.message.edit_text(text, reply_markup=_get_kb('group_menu', kb_client_group.group_main_menu))
    await call.answer()


async def group_promo_cmd(message: Message):
    """Актуальные промо материалы."""
    if not await is_group_approved(message.chat.id):
        return
    text = _get_txt('group_promo', '<b>📢 Актуальные промо материалы</b>\n\nПерейдите по ссылке для просмотра актуальных баннеров и промо материалов.')
    await message.reply(text, reply_markup=_get_kb('group_promo', kb_client_group.promo_menu))


async def group_promo_callback(call: CallbackQuery):
    """Промо через callback."""
    text = _get_txt('group_promo', '<b>📢 Актуальные промо материалы</b>\n\nПерейдите по ссылке для просмотра актуальных баннеров и промо материалов.')
    await call.message.edit_text(text, reply_markup=_get_kb('group_promo', kb_client_group.promo_menu))
    await call.answer()


async def group_calendar_cmd(message: Message):
    """Календарь."""
    if not await is_group_approved(message.chat.id):
        return
    text = _get_txt('group_calendar', '<b>📅 Календарь</b>\n\nПерейдите по ссылке для просмотра актуального календаря.')
    await message.reply(text, reply_markup=_get_kb('group_calendar', kb_client_group.calendar_menu))


async def group_calendar_callback(call: CallbackQuery):
    """Календарь через callback."""
    text = _get_txt('group_calendar', '<b>📅 Календарь</b>\n\nПерейдите по ссылке для просмотра актуального календаря.')
    await call.message.edit_text(text, reply_markup=_get_kb('group_calendar', kb_client_group.calendar_menu))
    await call.answer()


async def group_landings_cmd(message: Message):
    """Актуальные лендинги."""
    if not await is_group_approved(message.chat.id):
        return
    text = _get_txt('group_landings', bot_texts.landings.get('landings_text', '<b>🌐 Список актуальных лендингов</b>'))
    await message.reply(text, disable_web_page_preview=True, reply_markup=_get_kb('group_landings', kb_client_group.landings_menu))


async def group_landings_callback(call: CallbackQuery):
    """Лендинги через callback."""
    text = _get_txt('group_landings', bot_texts.landings.get('landings_text', '<b>🌐 Список актуальных лендингов</b>'))
    try:
        await call.message.edit_text(
            text, disable_web_page_preview=True,
            reply_markup=_get_kb('group_landings', kb_client_group.landings_menu))
    except Exception:
        await call.message.delete()
        await bot.send_message(
            chat_id=call.message.chat.id, text=text,
            disable_web_page_preview=True,
            reply_markup=_get_kb('group_landings', kb_client_group.landings_menu))
    await call.answer()


async def group_kb_cmd(message: Message):
    """База знаний — динамический список подтем."""
    if not await is_group_approved(message.chat.id):
        return
    kb_row = DB.Text.select(where=DB.Text.category == 'knowledge_base')
    kb = kb_row.data if kb_row else {}
    await message.reply(
        '<b>📚 База знаний</b>\n\n'
        '<i>Выберите интересующую тему:</i>',
        reply_markup=kb_client_group.build_kb_menu(kb, 'group_kb_', 'group_main_menu'))


# ── Knowledge base subtopics ─────────────────────────────────────────────────

async def group_kb_subtopic(call: CallbackQuery):
    """Handle KB topic / subtopic / back-to-parent in group chats."""
    data = call.data

    if data.startswith('group_kb_back_parent:'):
        rest = data[len('group_kb_back_parent:'):]
        try:
            parent_key, ids_str = rest.split(':', 1)
        except ValueError:
            parent_key, ids_str = rest, ''
        chat_id = call.message.chat.id
        for mid_str in ids_str.split(','):
            try:
                await bot.delete_message(chat_id=chat_id, message_id=int(mid_str))
            except Exception:
                pass
        return await _group_kb_show(call, f'group_kb_{parent_key}', fresh_send=True)

    return await _group_kb_show(call, data, fresh_send=False)


async def _group_kb_show(call: CallbackQuery, callback_data: str, fresh_send: bool):
    text_key = callback_data.replace('group_kb_', '', 1)
    kb_row = DB.Text.select(where=DB.Text.category == 'knowledge_base')
    kb = kb_row.data if kb_row else {}

    is_subtopic = '__' in text_key
    parent_key = text_key.split('__', 1)[0] if is_subtopic else text_key
    sub_meta = kb.get('_meta', {}).get('subtopics', {}).get(parent_key)
    has_subs = bool(sub_meta and sub_meta.get('order'))

    text = kb.get(text_key, '<b>Информация не найдена</b>')
    photo_key = f'{text_key}_photo'
    photo_id = kb.get(photo_key) or None
    chat_id = call.message.chat.id

    if is_subtopic:
        kb_no_photo = kb_client_group.back_to_parent_topic('group_kb_', parent_key)
    elif has_subs:
        kb_no_photo = kb_client_group.build_kb_subtopics_menu(kb, parent_key, 'group_kb_', 'group_knowledge_base')
    else:
        kb_no_photo = kb_client_group.back_to_knowledge_base

    sent_ids = []
    if photo_id:
        if not fresh_send:
            try: await call.message.delete()
            except Exception: pass
        msg1 = await bot.send_photo(chat_id=chat_id, photo=photo_id)
        sent_ids.append(msg1.message_id)
        if is_subtopic:
            kb_with_ids = kb_client_group.back_to_parent_topic_with_ids('group_kb_', parent_key, sent_ids)
        elif has_subs:
            kb_with_ids = kb_client_group.build_kb_subtopics_menu(kb, parent_key, 'group_kb_', 'group_knowledge_base')
        else:
            kb_with_ids = kb_client_group.back_to_kb_with_ids(sent_ids)
        msg2 = await bot.send_message(chat_id=chat_id, text=text, reply_markup=kb_with_ids)
        sent_ids.append(msg2.message_id)
    else:
        if fresh_send:
            await bot.send_message(chat_id=chat_id, text=text, reply_markup=kb_no_photo)
        else:
            try:
                await call.message.edit_text(text, reply_markup=kb_no_photo)
            except Exception:
                await bot.send_message(chat_id=chat_id, text=text, reply_markup=kb_no_photo)
    await call.answer()


async def group_kb_cmd_callback(call: CallbackQuery):
    """Return to knowledge base menu from subtopic (dynamic)."""
    kb_row = DB.Text.select(where=DB.Text.category == 'knowledge_base')
    kb = kb_row.data if kb_row else {}
    await call.message.edit_text(
        '<b>📚 База знаний</b>\n\n'
        '<i>Выберите интересующую тему:</i>',
        reply_markup=kb_client_group.build_kb_menu(kb, 'group_kb_', 'group_main_menu'))
    await call.answer()


async def group_kb_back(call: CallbackQuery):
    """Back from multi-part KB topic — delete all, show dynamic KB menu."""
    # Parse message IDs from callback data: group_kb_back:123,456,789
    ids_part = call.data.split(':', 1)[1] if ':' in call.data else ''
    message_ids = []
    for mid_str in ids_part.split(','):
        try:
            message_ids.append(int(mid_str.strip()))
        except ValueError:
            pass

    chat_id = call.message.chat.id
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
    await bot.send_message(
        chat_id=chat_id,
        text='<b>📚 База знаний</b>\n\n<i>Выберите интересующую тему:</i>',
        reply_markup=kb_client_group.build_kb_menu(kb, 'group_kb_', 'group_main_menu'))
    await call.answer()



def register_handlers_client_group(dp: Dispatcher):
    # Bot membership tracking
    dp.my_chat_member.register(bot_added_to_group)
    dp.my_chat_member.register(bot_removed_from_group)

    # Group chat commands
    group_filter = F.chat.type.in_({'group', 'supergroup'})
    dp.message.register(group_menu, Command(commands=['menu']), group_filter)
    dp.message.register(group_promo_cmd, Command(commands=['promo']), group_filter)
    dp.message.register(group_calendar_cmd, Command(commands=['calendar']), group_filter)
    dp.message.register(group_landings_cmd, Command(commands=['landings']), group_filter)
    dp.message.register(group_kb_cmd, Command(commands=['kb']), group_filter)

    # Group menu callbacks
    dp.callback_query.register(group_main_menu_callback, F.data == 'group_main_menu')
    dp.callback_query.register(group_promo_callback, F.data == 'group_promo')
    dp.callback_query.register(group_calendar_callback, F.data == 'group_calendar')
    dp.callback_query.register(group_landings_callback, F.data == 'group_landings')

    # Knowledge base callbacks
    dp.callback_query.register(group_kb_cmd_callback, F.data == 'group_knowledge_base')
    dp.callback_query.register(group_kb_back, F.data.startswith('group_kb_back:'))
    dp.callback_query.register(group_kb_subtopic, F.data.startswith('group_kb_'))
