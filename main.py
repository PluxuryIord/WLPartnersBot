"""
AUTHOR CODE - DEAD_MATRIX
TG: @DEAD_MATRIX
KWORK: kwork.ru/user/dead_matrix
Site Company: buy-bot.ru
"""

import asyncio
import json as _json
import logging

from aiogram.methods.delete_webhook import DeleteWebhook

from bot.filters import set_logging_filter
from bot.initialization import config, dispatcher_register_modules
from bot.initialization import set_menu_commands
from bot.utils import dt
from bot.utils.announce_bot import bot, dp
from bot.initialization.bot_texts.load_texts import bot_texts as _bot_texts
from bot.utils.apschedule_tasks import start_scheduler_tasks


async def _handle_reload_client(reader, writer):
    """Async TCP handler for /reload-texts endpoint."""
    try:
        data = await asyncio.wait_for(reader.read(4096), timeout=5.0)
        request_line = data.decode('utf-8', errors='ignore').split('\r\n')[0]

        if 'GET /reload-texts' in request_line:
            try:
                _bot_texts.load_db_texts()
                body = _json.dumps({"ok": True, "reloaded": True})
                status = "200 OK"
            except Exception as e:
                body = _json.dumps({"ok": False, "error": str(e)})
                status = "500 Internal Server Error"
        else:
            body = '{"error":"not found"}'
            status = "404 Not Found"

        response = (
            f"HTTP/1.1 {status}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
            f"{body}"
        )
        writer.write(response.encode())
        await writer.drain()
    except Exception:
        pass
    finally:
        writer.close()


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

    # Start reload-texts HTTP server on the same event loop
    reload_server = await asyncio.start_server(_handle_reload_client, '0.0.0.0', 5050)
    print('Reload-texts server started on port 5050')

    print(f'Telegram bot: Бот успешно запущен | Bot launched successfully')

    # Bot Startup
    await bot(DeleteWebhook(drop_pending_updates=True))

    # Run polling and reload HTTP server concurrently
    async def _run_polling():
        await dp.start_polling(bot)

    async def _run_reload_server():
        async with reload_server:
            await reload_server.serve_forever()

    await asyncio.gather(_run_polling(), _run_reload_server())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.error("Exit")
        print(f'Telegram bot: Ошибка при запуске | Error at startup')
