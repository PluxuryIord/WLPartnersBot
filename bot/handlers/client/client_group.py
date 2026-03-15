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


# ── Group chat menu ──────────────────────────────────────────────────────────

async def group_menu(message: Message):
    """Main support menu in group chat."""
    await message.reply(
        '<b>Меню поддержки WL Partners</b>\n\n'
        '<i>Выберите интересующий раздел:</i>',
        reply_markup=kb_client_group.group_main_menu)


async def group_menu_callback(call: CallbackQuery):
    """Return to main group menu via callback."""
    await call.message.edit_text(
        '<b>Меню поддержки WL Partners</b>\n\n'
        '<i>Выберите интересующий раздел:</i>',
        reply_markup=kb_client_group.group_main_menu)
    await call.answer()


# ── Sections ─────────────────────────────────────────────────────────────────

async def group_promo(call: CallbackQuery):
    """Актуальные промо материалы."""
    await call.message.edit_text(
        '<b>📢 Актуальные промо материалы</b>\n\n'
        'Перейдите по ссылке для просмотра актуальных баннеров и промо материалов.',
        reply_markup=kb_client_group.promo_menu)
    await call.answer()


async def group_calendar(call: CallbackQuery):
    """Календарь."""
    await call.message.edit_text(
        '<b>📅 Календарь</b>\n\n'
        'Перейдите по ссылке для просмотра актуального календаря.',
        reply_markup=kb_client_group.calendar_menu)
    await call.answer()


async def group_landings(call: CallbackQuery):
    """Список актуальных лендингов."""
    await call.message.edit_text(
        '<b>🌐 Список актуальных лендингов</b>\n\n'
        '<i>Контент будет добавлен позднее.</i>',
        reply_markup=kb_client_group.back_to_group_menu)
    await call.answer()


async def group_knowledge_base(call: CallbackQuery):
    """База знаний — список подтем."""
    await call.message.edit_text(
        '<b>📚 База знаний</b>\n\n'
        '<i>Выберите интересующую тему:</i>',
        reply_markup=kb_client_group.knowledge_base_menu)
    await call.answer()


# ── Knowledge base subtopics ─────────────────────────────────────────────────

KB_TEXTS = {
    'group_kb_lk_overview': '<b>Обзор личного кабинета</b>\n\n<i>Текст будет добавлен позднее.</i>',
    'group_kb_offer_info': '<b>Информация по офферу</b>\n\n<i>Текст будет добавлен позднее.</i>',
    'group_kb_ref_link': '<b>Генерация реф.ссылки</b>\n\n<i>Текст будет добавлен позднее.</i>',
    'group_kb_postback': '<b>Настройка постбэка</b>\n\n<i>Текст будет добавлен позднее.</i>',
    'group_kb_download_report': '<b>Скачивание отчета</b>\n\n<i>Текст будет добавлен позднее.</i>',
}


async def group_kb_subtopic(call: CallbackQuery):
    """Handle individual knowledge base subtopic."""
    text = KB_TEXTS.get(call.data, '<b>Информация не найдена</b>')
    await call.message.edit_text(
        text,
        reply_markup=kb_client_group.back_to_knowledge_base)
    await call.answer()


# ── Registration ─────────────────────────────────────────────────────────────

def register_handlers_client_group(dp: Dispatcher):
    # Bot membership tracking
    dp.my_chat_member.register(bot_added_to_group)
    dp.my_chat_member.register(bot_removed_from_group)

    # Group chat commands
    group_filter = F.chat.type.in_({'group', 'supergroup'})
    dp.message.register(group_menu, Command(commands=['menu']), group_filter)

    # Group callbacks (all prefixed with group_)
    dp.callback_query.register(group_menu_callback, F.data == 'group_back_menu')
    dp.callback_query.register(group_promo, F.data == 'group_promo')
    dp.callback_query.register(group_calendar, F.data == 'group_calendar')
    dp.callback_query.register(group_landings, F.data == 'group_landings')
    dp.callback_query.register(group_knowledge_base, F.data == 'group_knowledge_base')
    dp.callback_query.register(group_kb_subtopic, F.data.startswith('group_kb_'))
