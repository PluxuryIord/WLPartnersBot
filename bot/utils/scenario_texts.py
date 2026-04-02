from bot.initialization.bot_texts.load_texts import bot_texts

def get_text(screen_id: str, message_key: str, **kwargs) -> str:
    """Get text from in-memory cache (no DB calls)."""
    key = f'{screen_id}.{message_key}'
    text = bot_texts.scenarios.get(key, '')
    if text and kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text


def get_media(screen_id: str, message_key: str = 'main_text'):
    """Get media dict for a screen message if exists."""
    try:
        from bot.integrations import DB
        row = DB.Text.select(where=DB.Text.category == 'bot_scenarios')
        if row and row.data:
            data = row.data if isinstance(row.data, dict) else {}
            screen = data.get('screens', {}).get(screen_id, {})
            msg = screen.get('messages', {}).get(message_key, {})
            media = msg.get('media')
            if media and media.get('url'):
                return media
    except Exception:
        pass
    return None


async def send_screen_message(bot_instance, chat_id, screen_id, text, reply_markup=None, message_key='main_text'):
    """Send message with optional media from scenarios."""
    media = get_media(screen_id, message_key)
    if media and media.get('url'):
        try:
            from aiogram.types import URLInputFile
            photo = URLInputFile(media['url'])
            return await bot_instance.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        except Exception:
            pass
    return await bot_instance.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
