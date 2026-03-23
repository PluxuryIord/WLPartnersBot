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
import logging
import aiohttp
from bot.initialization import config


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
        await _notify_panel_membership(chat.id, chat.title or '', chat.type, 'removed')

# ── Group chat commands ───────────────────────────────────────────────────────

async def group_menu(message: Message):
    """Main support menu — inline buttons."""
    await message.reply(
        '<b>📋 Меню поддержки WINLINE PARTNERS</b>',
        reply_markup=kb_client_group.group_main_menu)


async def group_main_menu_callback(call: CallbackQuery):
    """Return to main group menu from any section."""
    await call.message.edit_text(
        '<b>📋 Меню поддержки WINLINE PARTNERS</b>',
        reply_markup=kb_client_group.group_main_menu)
    await call.answer()


async def group_promo_cmd(message: Message):
    """Актуальные промо материалы."""
    await message.reply(
        '<b>📢 Актуальные промо материалы</b>\n\n'
        'Перейдите по ссылке для просмотра актуальных баннеров и промо материалов.',
        reply_markup=kb_client_group.promo_menu)


async def group_promo_callback(call: CallbackQuery):
    """Промо через callback."""
    await call.message.edit_text(
        '<b>📢 Актуальные промо материалы</b>\n\n'
        'Перейдите по ссылке для просмотра актуальных баннеров и промо материалов.',
        reply_markup=kb_client_group.promo_menu)
    await call.answer()


async def group_calendar_cmd(message: Message):
    """Календарь."""
    await message.reply(
        '<b>📅 Календарь</b>\n\n'
        'Перейдите по ссылке для просмотра актуального календаря.',
        reply_markup=kb_client_group.calendar_menu)


async def group_calendar_callback(call: CallbackQuery):
    """Календарь через callback."""
    await call.message.edit_text(
        '<b>📅 Календарь</b>\n\n'
        'Перейдите по ссылке для просмотра актуального календаря.',
        reply_markup=kb_client_group.calendar_menu)
    await call.answer()


async def group_landings_cmd(message: Message):
    """Актуальные лендинги."""
    text = bot_texts.landings.get('landings_text', '<b>🌐 Список актуальных лендингов</b>')
    await message.reply(text, disable_web_page_preview=True)


async def group_landings_callback(call: CallbackQuery):
    """Лендинги через callback."""
    text = bot_texts.landings.get('landings_text', '<b>🌐 Список актуальных лендингов</b>')
    try:
        await call.message.edit_text(
            text, disable_web_page_preview=True,
            reply_markup=kb_client_group.landings_menu)
    except Exception:
        await call.message.delete()
        await bot.send_message(
            chat_id=call.message.chat.id, text=text,
            disable_web_page_preview=True,
            reply_markup=kb_client_group.landings_menu)
    await call.answer()


async def group_kb_cmd(message: Message):
    """База знаний — динамический список подтем."""
    kb_row = DB.Text.select(where=DB.Text.category == 'knowledge_base')
    kb = kb_row.data if kb_row else {}
    await message.reply(
        '<b>📚 База знаний</b>\n\n'
        '<i>Выберите интересующую тему:</i>',
        reply_markup=kb_client_group.build_kb_menu(kb, 'group_kb_', 'group_main_menu'))


# ── Knowledge base subtopics ─────────────────────────────────────────────────

async def group_kb_subtopic(call: CallbackQuery):
    """Handle individual knowledge base subtopic (dynamic)."""
    key = call.data  # e.g. group_kb_lk_overview
    text_key = key.replace('group_kb_', '', 1)  # e.g. lk_overview

    kb_row = DB.Text.select(where=DB.Text.category == 'knowledge_base')
    kb = kb_row.data if kb_row else {}
    text = kb.get(text_key, '<b>Информация не найдена</b>')

    chat_id = call.message.chat.id
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
            reply_markup=kb_client_group.back_to_kb_with_ids(sent_ids))
        sent_ids.append(msg2.message_id)
    else:
        await call.message.edit_text(
            text, reply_markup=kb_client_group.back_to_knowledge_base)
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
