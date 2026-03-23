"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Callable, Dict, Any, Awaitable, Union

    from aiogram.types import Message

import asyncio

from bot.handlers.admin.admin_bot_info import admin_bot_info
from bot.integrations import DB
from bot.initialization import config

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery


class TechnicalWorks(BaseMiddleware):
    def __init__(self):
        self.technical_works_state = DB.Settings.select().engineering_works

    async def __call__(
            self,
            handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
            event: Union[Message, CallbackQuery],
            data: Dict[str, Any]
    ) -> Any:
        if isinstance(event, CallbackQuery) and event.data == 'admin_tech_work':
            status = await self.update_status()
            if status:
                await event.answer('🛠Тех.работы были включены.', show_alert=True)
            else:
                await event.answer('🛠Тех.работы были отключены.', show_alert=True)
            await admin_bot_info(event)
        elif self.technical_works_state:
            if not config.admin_filter.is_system(event.from_user.id):
                if isinstance(event, Message):
                    temp = await event.reply(
                        '⛔️Приносим свои извинения, ведутся технические работы, '
                        'постараемся возобновить работу как можно скорее!')
                    await asyncio.sleep(5)
                    await temp.delete()
                    await event.delete()
                elif isinstance(event, CallbackQuery):
                    await event.answer(
                        '⛔️Приносим свои извинения, ведутся технические работы, '
                        'постараемся возобновить работу как можно скорее!',
                        show_alert=True)
                return False
            else:
                return await handler(event, data)
        else:
            return await handler(event, data)

    async def update_status(self):
        self.technical_works_state = not self.technical_works_state
        DB.Settings.update(engineering_works=self.technical_works_state)
        return self.technical_works_state
