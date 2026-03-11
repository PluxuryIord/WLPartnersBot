"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from aiogram import Dispatcher, BaseMiddleware

from bot.handlers import initialization_handlers
from bot.initialization import config
from bot.middlewares import ThrottlingMiddleware, IsBanned, ServiceFilter, IsHaveGroup, TechnicalWorks
from bot.middlewares import UserData, AlbumMiddleware


def register_middleware(dp: Dispatcher, middleware: BaseMiddleware, message: bool = False,
                        callback_query: bool = False, inline: bool = False) -> None:
    if message:
        dp.message.middleware.register(middleware)
    if callback_query:
        dp.callback_query.middleware.register(middleware)
    if inline:
        dp.inline_query.middleware.register(middleware)


def dispatcher_register_modules(dp: Dispatcher):
    register_middleware(dp, ServiceFilter(), True)
    register_middleware(dp, ThrottlingMiddleware(config.throttling, config.admin_filter), True, True)
    register_middleware(dp, IsBanned(), True, True, True)
    register_middleware(dp, IsHaveGroup(), True, True)
    register_middleware(dp, TechnicalWorks(), True, True)
    register_middleware(dp, UserData(), True, True, True)
    register_middleware(dp, AlbumMiddleware(config.album), True)

    initialization_handlers(dp)
