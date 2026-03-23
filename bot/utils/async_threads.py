"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

import asyncio
import threading
import time


class AsyncThreads:

    def __init__(self):
        self.threads = []
        self.async_tasks = []
        self.lock = threading.Lock()
        self.loop = asyncio.get_event_loop()

    async def _start_threading(self):
        time_start = time.time()
        [thread.start() for thread in self.threads]
        [thread.join() for thread in self.threads]
        if len(self.async_tasks) > 0:
            await asyncio.wait(self.async_tasks)
        return str(round(time.time() - time_start, 2))
