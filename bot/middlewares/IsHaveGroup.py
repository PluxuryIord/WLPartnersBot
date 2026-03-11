"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Callable, Dict, Any, Awaitable, Union

    from aiogram.types import CallbackQuery

import logging

from aiogram import BaseMiddleware

from aiogram.types import Message
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest

from bot.utils import telegram as helper
from bot.initialization import config
from bot.integrations import DB


class IsHaveGroup(BaseMiddleware):
    def __init__(self):
        self.bot_group = DB.Settings.select().bot_group

    async def __call__(
            self,
            handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
            event: Union[Message, CallbackQuery],
            data: Dict[str, Any]
    ) -> Any:
        if not self.bot_group and not DB.Settings.select().bot_group:
            if (
                    isinstance(event, Message) and event.text == '/register' and
                    config.admin_filter.is_system(event.from_user.id)
            ):
                if not event.chat.is_forum:
                    await event.answer('❌Не включены топики', show_alert=True)
                else:
                    try:
                        helper.topic_manager.bot_group = event.chat.id
                        alert_thread = await helper.topic_manager.create_topic('Уведомления', 5309984423003823246)
                        try:
                            await helper.topic_manager.edit_topic(name='Команды/Service', general=True)
                        except TelegramBadRequest:
                            logging.debug('TOPIC_NOT_MODIFIED')
                        await helper.send_message(
                            chat_id=event.chat.id,
                            text='<b>Для отправки сообщения пользователю - найдите диалог с его именем '
                                 'и просто отправьте сообщение, чтобы оставить заметку в топике и '
                                 'сообщение не ушло пользователю - '
                                 'поставьте восклицательный знак(!) в начале сообщения</b>')
                        await helper.send_message(
                            chat_id=event.chat.id,
                            message_thread_id=alert_thread,
                            text='<b>Данный топик создан для важных уведомлений внутри бота.</b>')
                        helper.topic_manager.alert = alert_thread
                        DB.Settings.update(bot_group=event.chat.id, alert_thread=alert_thread)
                    except TelegramAPIError as err:
                        helper.topic_manager.bot_group = None
                        logging.error(f'No created new admin chat: {err}')
                        await event.reply('❌Ошибка при прикрепление, выдайте права администратора и повторите попытку')
                return False
            await event.answer('❌Не установлена группа для бота', show_alert=True)
        else:
            return await handler(event, data)
