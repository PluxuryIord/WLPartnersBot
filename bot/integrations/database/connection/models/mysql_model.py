"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from dataclasses import dataclass

from environs import Env
from sqlalchemy import URL


@dataclass
class MysqlConfig:
    DRIVER: str
    HOST: str
    PORT: int
    USERNAME: str
    PASSWORD: str
    DATABASE: str
    QUERY = {'charset': 'utf8mb4'}


def get_config():
    config = Env()
    config.read_env()
    mysql = MysqlConfig(
        'mysql+pymysql',
        config.str('MYSQL_HOST'),
        config.int('MYSQL_PORT'),
        config.str('MYSQL_USER'),
        config.str('MYSQL_PASSWORD'),
        config.str('MYSQL_DATABASE')
    )
    return mysql


def get_mysql_url():
    config = get_config()
    engine_url = URL(
        drivername=config.DRIVER,
        host=config.HOST,
        port=config.PORT,
        username=config.USERNAME,
        password=config.PASSWORD,
        database=config.DATABASE,
        query=config.QUERY
    )
    return engine_url
