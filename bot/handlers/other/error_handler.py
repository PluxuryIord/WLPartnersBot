"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

import logging

from aiogram import Dispatcher


async def errors_handler(update) -> bool:
    """
    Exceptions handler. Catches all exceptions within task factory tasks.
    :param update:
    :return: stdout logging
    """
    exception = update.exception
    logging.error('⛔️START⛔️')
    logging.exception(f'{exception} \nUpdate: {update}')
    logging.error('⛔️END⛔️')
    return True


def register_error_handlers(dp: Dispatcher):
    dp.errors.register(errors_handler)
