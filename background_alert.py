from __future__ import annotations

import sys
import platform
import asyncio

from bot.handlers.admin.admin_alert import ThreadAlert
from bot.integrations import DB


async def background_alert(alert_id: int):
    alert_data = DB.Alert.select(mark=alert_id)
    users = [key for key in alert_data.recipients]
    await ThreadAlert(alert_id, users).start_sending()


if __name__ == '__main__':
    sys_args = sys.argv
    if sys_args and len(sys_args) == 2:
        db_id = int(sys_args[1])
        if platform.system() == 'Windows':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(background_alert(db_id))
