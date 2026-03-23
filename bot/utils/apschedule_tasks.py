"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.initialization.bot_texts import bot_texts


async def start_scheduler_tasks():
    schedulers = AsyncIOScheduler()
    schedulers.add_job(bot_texts.load_db_texts, 'interval', seconds=3)
    schedulers.start()
