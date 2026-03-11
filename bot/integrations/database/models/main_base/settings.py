"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from datetime import datetime

from sqlalchemy import Text, Boolean, BigInteger, Integer
from sqlalchemy.orm import Mapped, mapped_column

from . import Base


class Settings(Base):
    __tablename__ = 'settings'
    engineering_works: Mapped[bool] = mapped_column(Boolean, primary_key=True, default=False)
    last_start: Mapped[datetime]
    last_update: Mapped[datetime]
    bot_version: Mapped[str] = mapped_column(Text)
    bot_group: Mapped[int] = mapped_column(BigInteger, nullable=True, default=None)
    alert_thread: Mapped[int] = mapped_column(nullable=True, default=None)
    event_starts: Mapped[bool] = mapped_column(Boolean)
    count_for_hrs: Mapped[int] = mapped_column(Integer)

    @staticmethod
    def select() -> 'Settings':
        return Settings._db_select(Settings)

    @staticmethod
    def update(**kwargs) -> bool:
        return Settings._db_update(Settings, **kwargs)

    @staticmethod
    def startup():
        now = datetime.now()
        result = Settings._db_select(Settings)
        if not result:
            Settings._db_add(Settings(engineering_works=0, last_start=now, last_update=now, bot_version='1.0b'))
        else:
            Settings.update(last_start=now)
