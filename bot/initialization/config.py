"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

import sys

from environs import Env, EnvError

from bot.filters import AdminFilter


class ThrottlingConfig:
    def __init__(self, max_rate: int, period: float):
        self.max_rate = max_rate
        self.period = period


class AlbumConfig:
    def __init__(self, latency: float, auto_delete: float):
        self.latency = latency
        self.auto_delete = auto_delete


class BotConfig:
    def __init__(self):
        try:
            env = Env()
            env.read_env()
            self.throttling = ThrottlingConfig(env.int('THROTTLING_MAX_RATE'), env.float('THROTTLING_PERIOD'))
            self.album = AlbumConfig(env.float('ALBUM_LATENCY'), env.float('ALBUM_AUTO_DELETE'))
            self.logging_debug = env.bool("PROJECT_DEBUG")
            self.reset_texts = env.bool("RESET_TEXTS")
            system_admins = [int(elem) for elem in env.str("DEFAULT_ADMINS").split(',')]
            self.admin_filter = AdminFilter(system_admins)
            self.alert_bots = env.str('ALERT_BOTS').replace(' ', '').split(',') if env.str('ALERT_BOTS') != 'False' \
                else [env.str("TG_TOKEN")]
        except EnvError:
            print('Ошибка в файле .env / Error in .env file')
            sys.exit(1)


config = BotConfig()
