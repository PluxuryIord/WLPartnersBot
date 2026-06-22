"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.initialization.bot_texts import bot_texts
from bot.utils import dynamic_kb
from bot.utils import alarms


async def start_scheduler_tasks():
    schedulers = AsyncIOScheduler()
    schedulers.add_job(bot_texts.load_db_texts, 'interval', seconds=3)
    schedulers.add_job(dynamic_kb.reload, 'interval', seconds=3)
    # Trigger-alarms pass — only scheduled when the master switch is on, so a
    # disabled deployment never wakes the engine. See bot/utils/alarms.py.
    if alarms.ALARMS_ENABLED:
        schedulers.add_job(alarms.scheduled_pass, 'interval',
                           seconds=alarms.ALARM_INTERVAL_SEC)
        logging.warning(f'[alarms] scheduled every {alarms.ALARM_INTERVAL_SEC}s '
                        f'(dry_run={alarms.ALARMS_DRY_RUN}, test_chat={alarms.ALARM_TEST_CHAT_ID or None})')
    schedulers.start()
