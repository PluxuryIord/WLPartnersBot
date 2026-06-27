"""Middleware: count clicks on main-menu buttons (by callback action).

Runs on every callback_query, increments wl_menu_clicks for known main-menu
actions, then passes through. Never blocks or breaks the user flow — any
tracking error is swallowed (it's analytics, not a gate).
"""
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery

from bot.utils import menu_tracker


class MenuClickTracker(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, CallbackQuery) and event.data:
            try:
                await menu_tracker.track(event.data)
            except Exception:
                pass
        return await handler(event, data)
