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
