"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from datetime import datetime
from typing import Union

from sqlalchemy import Text, BigInteger
from sqlalchemy.orm import Mapped, mapped_column

from bot.integrations.database.models.statistics_base.base import Base


class Events(Base):
    __tablename__ = 'Events'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(Text)
    user_id: Mapped[int] = mapped_column(BigInteger)
    data: Mapped[str] = mapped_column(Text)
    time: Mapped[datetime]

    @staticmethod
    def new(event_type: str, user_id: int, data: str) -> bool | int:
        return Events._db_add(Events(type=event_type, user_id=user_id, data=data, time=datetime.now()))

    @staticmethod
    def select(all_scalars: bool = False) -> Union[list['Events'], 'Events']:
        return Events._db_select(Events, all_scalars)

    @staticmethod
    def delete(line_id: int):
        Events._db_remove(Events, line_id)
