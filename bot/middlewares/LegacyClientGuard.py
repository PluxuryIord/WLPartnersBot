"""Middleware: seal off legacy buttons in Mini-App-only mode.

When MINIAPP_URL is set the bot funnels everyone into the Web App, but old
menu messages still linger in private chats with LIVE inline buttons (the
handlers are still registered, and scenario menus use arbitrary callback data,
so a prefix blocklist is unreliable). So in PRIVATE chats we gate by role:

  • non-admin  → freeze EVERY callback (they have only the Web App);
  • admin      → allow only admin-panel callbacks (admin_/alert_/topic_/bot_),
                 freeze the rest (their old client buttons too).

Frozen taps get a redirect alert and the message keyboard is refreshed to the
new «Открыть приложение» menu. Group/forum chats and the empty-MINIAPP_URL
case are untouched (old behaviour preserved).
"""
import os
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery

from bot.initialization import config

# Admin-panel callbacks that must keep working: admin menu, broadcast
# constructor (alert_*), topic management (topic_*), notification toggles (bot_*).
_ADMIN_PREFIXES = ('admin_', 'alert_', 'topic_', 'bot_')


class LegacyClientGuard(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if (isinstance(event, CallbackQuery) and event.data
                and os.getenv('MINIAPP_URL', '').strip()):
            msg = event.message
            is_private = bool(msg and getattr(msg, 'chat', None)
                              and msg.chat.type == 'private')
            if is_private:
                is_admin = config.admin_filter.is_admin(event.from_user.id)
                allowed = is_admin and event.data.startswith(_ADMIN_PREFIXES)
                if not allowed:
                    await event.answer(
                        'Этот раздел переехал в приложение. '
                        'Нажмите «🚀 Открыть приложение».',
                        show_alert=True)
                    try:
                        from bot.keyboards.client.kb_client_menu import get_miniapp_only_menu
                        await msg.edit_reply_markup(
                            reply_markup=get_miniapp_only_menu(is_admin))
                    except Exception:
                        pass
                    return  # freeze the button
        return await handler(event, data)
