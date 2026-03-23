"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from environs import Env
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from bot.integrations.database.connection.models import get_mysql_url, get_sqlite_url

env = Env()
env.read_env()
sql_debug = env.bool("SQL_DEBUG")


def build_engine(engine_url: str) -> Engine:
    eng = create_engine(url=engine_url, echo=sql_debug, pool_pre_ping=False)
    return eng


mysql_engine = build_engine(get_mysql_url())
stats_sqlite_engine = build_engine(get_sqlite_url('local_bases/statistics.db'))
