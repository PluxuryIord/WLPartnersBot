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

from bot.integrations import DB
from bot.initialization import config
from bot.utils import telegram as telegram
from bot.keyboards.admin.kb_admin_topic import topic_management

from aiogram.types import CallbackQuery
from aiogram import BaseMiddleware


class IsBanned(BaseMiddleware):
    def __init__(self):
        self._banned = []
        for user in DB.User.select(all_scalars=True):
            if user.banned:
                self._banned.append(user.user_id)

    async def __call__(
            self,
            handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
            event: Union[Message, CallbackQuery],
            data: Dict[str, Any]
    ) -> Any:
        if event.from_user.id in self._banned:
            return False
        else:
            if isinstance(event, CallbackQuery):
                if 'topic_block_user|' in event.data or 'topic_unblock_user|' in event.data:
                    if not config.admin_filter:
                        await event.answer('❌Недостаточно прав!', show_alert=True)
                        return False
                    else:
                        target_user_id = int(event.data.split('|')[1])
                        if target_user_id == event.from_user.id:
                            await event.answer('❌Нельзя применить на самого себя', show_alert=True)
                            return False
                        elif config.admin_filter.is_admin(target_user_id):
                            await event.answer('❌Нельзя заблокировать администратора', show_alert=True)
                            return False
                    if 'topic_block_user|' in event.data:
                        DB.User.update(mark=target_user_id, banned=True)
                        await event.answer('✅Пользователь заблокирован', show_alert=True)
                        await telegram.edit_text(event.message, event.message.html_text,
                                                 reply_markup=topic_management(target_user_id, True))
                        self._banned.append(target_user_id)
                    else:
                        DB.User.update(mark=target_user_id, banned=False)
                        await event.answer('✅Пользователь разблокирован', show_alert=True)
                        await telegram.edit_text(event.message, event.message.html_text,
                                                 reply_markup=topic_management(target_user_id, False))
                        self._banned.remove(target_user_id)
                    return False
            return await handler(event, data)
