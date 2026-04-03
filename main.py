"""
AUTHOR CODE - DEAD_MATRIX
TG: @DEAD_MATRIX
KWORK: kwork.ru/user/dead_matrix
Site Company: buy-bot.ru
"""

import asyncio
import logging

from aiogram.methods.delete_webhook import DeleteWebhook

from bot.filters import set_logging_filter
from bot.initialization import config, dispatcher_register_modules
from bot.initialization import set_menu_commands
from bot.utils import dt
from bot.utils.announce_bot import bot, dp
from bot.utils.apschedule_tasks import start_scheduler_tasks


async def main() -> None:
    print('Бот разработан командой buy-bot.ru | The bot was developed by the buy-bot.ru team')
    print('Telegram bot: Бот загружается... | Bot loading...')

    # Start Logging
    if config.logging_debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        )
        set_logging_filter(logging)
    else:
        logging.basicConfig(
            filename=f'logs/{dt.now("path")}.txt', filemode='a',
            format='%(asctime)s | %(levelname)s | %(name)s | [ %(filename)s-%(module)s-%(lineno)d ] | %(message)s',
            datefmt='%d.%m %H:%M:%S',
            level=logging.ERROR)

    # Initialization handlers and middlewares
    dispatcher_register_modules(dp)

    # Set Bot Default Commands
    await set_menu_commands(bot)

    # Scheduler Tasks
    await start_scheduler_tasks()

    print(f'Telegram bot: Бот успешно запущен | Bot launched successfully')

    # Bot Startup — texts auto-reload every 3s via apscheduler (see apschedule_tasks.py)
    await bot(DeleteWebhook(drop_pending_updates=True))
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.error("Exit")
        print(f'Telegram bot: Ошибка при запуске | Error at startup')
