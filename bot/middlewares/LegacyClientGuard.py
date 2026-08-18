"""Middleware: seal off legacy client buttons in Mini-App-only mode.

When MINIAPP_URL is set the bot funnels everyone into the Web App, but old
menu messages still linger in chats with LIVE inline buttons (the callback
handlers are still registered). Intercept those legacy `client_`/`pick:`
callbacks so tapping them no longer runs the old flow: show a redirect alert
and refresh that message's keyboard to just «Открыть приложение».

Admin (`admin_*`), group (`group_*`), event (`event_v2_*`) and other callbacks
pass through untouched. No-op when MINIAPP_URL is empty (old menus still work).
"""
import os
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery

from bot.initialization import config

_LEGACY_PREFIXES = ('client_', 'pick:')


class LegacyClientGuard(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if (isinstance(event, CallbackQuery) and event.data
                and event.data.startswith(_LEGACY_PREFIXES)
                and os.getenv('MINIAPP_URL', '').strip()):
            await event.answer(
                'Этот раздел переехал в приложение. Нажмите «🚀 Открыть приложение».',
                show_alert=True)
            try:
                from bot.keyboards.client.kb_client_menu import get_miniapp_only_menu
                is_admin = config.admin_filter.is_admin(event.from_user.id)
                await event.message.edit_reply_markup(
                    reply_markup=get_miniapp_only_menu(is_admin))
            except Exception:
                pass
            return  # block the legacy handler downstream
        return await handler(event, data)
