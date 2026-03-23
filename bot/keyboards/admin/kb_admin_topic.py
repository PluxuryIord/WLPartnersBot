"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""
# Site Company: buy-bot.ru


from aiogram.types import Message

from bot.utils.telegram import create_inline


def topic_management(user_id: int, banned: bool = False):
    if banned:
        banned_button = ['✔️ Разблокировать', 'call', f'topic_unblock_user|{user_id}']
    else:
        banned_button = ['🚫 Заблокировать', 'call', f'topic_block_user|{user_id}']
    return create_inline([
        ['👑 Назначить администратором', 'call', f'topic_add_admin|{user_id}'],
        banned_button], 1)


def topic_message(message: Message, db_message_id: int):
    if (message.text or message.caption) and not (message.sticker or message.video_note or message.voice):
        buttons = [['✏️ Отредактировать текст', 'call', f'topic_redact_text|{db_message_id}']]
    else:
        buttons = []
    buttons.append(['❌ Удалить', 'call', f'topic_delete_message|{db_message_id}'])
    return create_inline(buttons, 1)


edit_cancel = create_inline([['❌ Отменить', 'call', 'topic_edit_cancel']], 1)
