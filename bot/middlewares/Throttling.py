"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.types import Message

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from typing import Any

    from aiogram.types import TelegramObject, User

    from bot.initialization import ThrottlingConfig
    from bot.filters.admin_filters import AdminFilter

import logging

from dataclasses import dataclass
from aiogram import BaseMiddleware
from cachetools import TTLCache


@dataclass(kw_only=True, slots=True)
class ThrottlingData:
    rate: int = 0
    sent_warning: bool = False


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, throttling_config: ThrottlingConfig, admin_filter: AdminFilter) -> None:
        self._throttling_config = throttling_config
        self._admin_filter = admin_filter
        self._cache: TTLCache[int, ThrottlingData] = TTLCache(
            maxsize=10_000,
            ttl=self._throttling_config.period,
        )

    async def __call__(
            self,
            handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: dict[str, Any],
    ) -> Any | None:
        event_user: User | None = data.get("event_from_user")

        if not event_user:
            return False
        elif self._admin_filter and self._admin_filter.is_admin(event_user.id):
            return await handler(event, data)
        elif isinstance(handler, Message) and handler.media_group_id:
            return await handler(event, data)

        if event_user.id not in self._cache:
            self._cache[event_user.id] = ThrottlingData()

        throttling_data = self._cache[event_user.id]

        if throttling_data.rate == self._throttling_config.max_rate:
            self._cache[event_user.id] = throttling_data

            if not throttling_data.sent_warning:
                throttling_data.sent_warning = True
                logging.error(f'Throttling: {event_user.id} max rate')

            return False

        throttling_data.rate += 1

        return await handler(event, data)
