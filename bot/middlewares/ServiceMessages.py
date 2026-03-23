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
    from aiogram.types import Message

import logging

from aiogram import BaseMiddleware
from aiogram.types import ContentType


class ServiceFilter(BaseMiddleware):
    def __init__(self):
        self.ignored_types = [
            ContentType.UNKNOWN, ContentType.NEW_CHAT_MEMBERS, ContentType.LEFT_CHAT_MEMBER,
            ContentType.NEW_CHAT_TITLE, ContentType.NEW_CHAT_TITLE, ContentType.NEW_CHAT_PHOTO,
            ContentType.DELETE_CHAT_PHOTO, ContentType.GROUP_CHAT_CREATED, ContentType.SUPERGROUP_CHAT_CREATED,
            ContentType.CHANNEL_CHAT_CREATED, ContentType.MESSAGE_AUTO_DELETE_TIMER_CHANGED,
            ContentType.MIGRATE_FROM_CHAT_ID, ContentType.PINNED_MESSAGE, ContentType.CONNECTED_WEBSITE,
            ContentType.PROXIMITY_ALERT_TRIGGERED, ContentType.FORUM_TOPIC_CLOSED, ContentType.FORUM_TOPIC_CREATED,
            ContentType.FORUM_TOPIC_EDITED, ContentType.FORUM_TOPIC_REOPENED, ContentType.GENERAL_FORUM_TOPIC_HIDDEN,
            ContentType.GENERAL_FORUM_TOPIC_UNHIDDEN, ContentType.VIDEO_CHAT_ENDED, ContentType.VIDEO_CHAT_SCHEDULED,
            ContentType.VIDEO_CHAT_STARTED, ContentType.VIDEO_CHAT_PARTICIPANTS_INVITED
        ]

    async def __call__(
            self,
            handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
            event: Union[Message, CallbackQuery],
            data: Dict[str, Any]
    ) -> Any:
        if event.content_type in self.ignored_types:
            return False
        elif event.content_type == ContentType.MIGRATE_TO_CHAT_ID:
            logging.error(f'SERVICE EVENT: {event.chat.full_name} MIGRATE TO {event.chat.id}')
        else:
            return await handler(event, data)
