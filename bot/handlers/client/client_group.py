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


# ── Bot membership tracking ──────────────────────────────────────────────────

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


async def bot_removed_from_group(event: ChatMemberUpdated):
    """Auto-track when bot is removed from a group."""
    new_status = event.new_chat_member.status

    if new_status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
        existing = DB.GroupChat.select(mark=event.chat.id)
        if existing:
            DB.GroupChat.update(mark=event.chat.id, is_active=False)


# ── Group chat commands ───────────────────────────────────────────────────────

async def group_menu(message: Message):
    """Main support menu — list of commands."""
    await message.reply(
        '<b>📋 Меню поддержки WL Partners</b>\n\n'
        '/promo — Актуальные промо материалы\n'
        '/calendar — Календарь\n'
        '/landings — Актуальные лендинги\n'
        '/kb — База знаний')


async def group_promo_cmd(message: Message):
    """Актуальные промо материалы."""
    await message.reply(
        '<b>📢 Актуальные промо материалы</b>\n\n'
        'Перейдите по ссылке для просмотра актуальных баннеров и промо материалов.',
        reply_markup=kb_client_group.promo_menu)


async def group_calendar_cmd(message: Message):
    """Календарь."""
    await message.reply(
        '<b>📅 Календарь</b>\n\n'
        'Перейдите по ссылке для просмотра актуального календаря.',
        reply_markup=kb_client_group.calendar_menu)


async def group_landings_cmd(message: Message):
    """Актуальные лендинги."""
    await message.reply(
        '<b>🌐 Список актуальных лендингов</b>\n\n'
        '<i>Контент будет добавлен позднее.</i>')


async def group_kb_cmd(message: Message):
    """База знаний — список подтем."""
    await message.reply(
        '<b>📚 База знаний</b>\n\n'
        '<i>Выберите интересующую тему:</i>',
        reply_markup=kb_client_group.knowledge_base_menu)


# ── Knowledge base subtopics ─────────────────────────────────────────────────

# Mapping: callback_data -> key in bot_texts.knowledge_base
KB_KEYS = {
    'group_kb_lk_overview': 'lk_overview',
    'group_kb_offer_info': 'offer_info',
    'group_kb_ref_link': 'ref_link',
    'group_kb_postback': 'postback',
    'group_kb_download_report': 'download_report',
}


async def group_kb_subtopic(call: CallbackQuery):
    """Handle individual knowledge base subtopic."""
    key = call.data
    kb = bot_texts.knowledge_base
    text_key = KB_KEYS.get(key)
    text = kb.get(text_key, '<b>Информация не найдена</b>') if text_key else '<b>Информация не найдена</b>'

    photo_postback = kb.get('postback_photo') or None
    photo_report = kb.get('report_photo') or None
    photo_report_2 = kb.get('report_photo_2') or None

    chat_id = call.message.chat.id
    sent_ids = []  # collect all message IDs for back button

    # Topics with photos: send photo first, then text as separate message
    if key == 'group_kb_postback' and photo_postback:
        await call.message.delete()
        msg1 = await bot.send_photo(chat_id=chat_id, photo=photo_postback)
        sent_ids.append(msg1.message_id)
        msg2 = await bot.send_message(
            chat_id=chat_id, text=text,
            reply_markup=kb_client_group.back_to_kb_with_ids(sent_ids))
        sent_ids.append(msg2.message_id)
    elif key == 'group_kb_download_report':
        await call.message.delete()
        text_2 = kb.get('download_report_2', '')
        # Message 1: photo1 + text1
        if photo_report:
            msg1 = await bot.send_photo(chat_id=chat_id, photo=photo_report)
            sent_ids.append(msg1.message_id)
        msg2 = await bot.send_message(chat_id=chat_id, text=text)
        sent_ids.append(msg2.message_id)
        # Message 2: photo2 + text2 (with back button)
        if text_2:
            if photo_report_2:
                msg3 = await bot.send_photo(chat_id=chat_id, photo=photo_report_2)
                sent_ids.append(msg3.message_id)
            msg4 = await bot.send_message(
                chat_id=chat_id, text=text_2,
                reply_markup=kb_client_group.back_to_kb_with_ids(sent_ids))
            sent_ids.append(msg4.message_id)
        else:
            # No text_2 — add back button to msg2 (rewrite not possible, send separate)
            msg_back = await bot.send_message(
                chat_id=chat_id, text='⬇️',
                reply_markup=kb_client_group.back_to_kb_with_ids(sent_ids))
            sent_ids.append(msg_back.message_id)
    else:
        await call.message.edit_text(
            text, reply_markup=kb_client_group.back_to_knowledge_base)
    await call.answer()


async def group_kb_cmd_callback(call: CallbackQuery):
    """Return to knowledge base menu from subtopic."""
    await call.message.edit_text(
        '<b>📚 База знаний</b>\n\n'
        '<i>Выберите интересующую тему:</i>',
        reply_markup=kb_client_group.knowledge_base_menu)
    await call.answer()


async def group_kb_back(call: CallbackQuery):
    """Back button from multi-part KB topic — delete all sent messages, show KB menu."""
    # Parse message IDs from callback data: group_kb_back:123,456,789
    ids_part = call.data.split(':', 1)[1] if ':' in call.data else ''
    message_ids = []
    for mid_str in ids_part.split(','):
        try:
            message_ids.append(int(mid_str.strip()))
        except ValueError:
            pass

    chat_id = call.message.chat.id

    # Delete all tracked messages (including this one)
    for mid in message_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass
    # Also delete the current message if not in the list
    if call.message.message_id not in message_ids:
        try:
            await call.message.delete()
        except Exception:
            pass

    # Send KB menu
    await bot.send_message(
        chat_id=chat_id,
        text='<b>📚 База знаний</b>\n\n<i>Выберите интересующую тему:</i>',
        reply_markup=kb_client_group.knowledge_base_menu)
    await call.answer()


# ── Registration ─────────────────────────────────────────────────────────────

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

    # Knowledge base callbacks
    dp.callback_query.register(group_kb_cmd_callback, F.data == 'group_knowledge_base')
    dp.callback_query.register(group_kb_back, F.data.startswith('group_kb_back:'))
    dp.callback_query.register(group_kb_subtopic, F.data.startswith('group_kb_'))
