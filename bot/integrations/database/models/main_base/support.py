"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from . import Base

if TYPE_CHECKING:
    from typing import Optional, Union


class Support(Base):
    __tablename__ = 'support'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.user_id'))
    topic_id: Mapped[int]
    status: Mapped[str] = mapped_column(Text, default='Открыто')
    status_open: Mapped[bool] = mapped_column(default=True)
    message: Mapped[str] = mapped_column(Text)
    date: Mapped[datetime]

    @staticmethod
    def _check_mark(mark: int = False) -> Optional['Base']:
        return Support._base_check_mark(Support.id, mark, 0)

    @staticmethod
    def add(user_id: int, topic_id: int, message: str) -> int:
        new_message = Support(user_id=user_id,
                              topic_id=topic_id,
                              message=message,
                              date=datetime.now())
        return Support._db_add(new_message, autoincrement_id=True)

    @staticmethod
    def select(mark: int = False, where=False, all_scalars: bool = False) -> Union[list['Support'], 'Support']:
        return Support._db_select(Support, Support._check_mark(mark), where, all_scalars)

    @staticmethod
    def update(mark: int = False, where=False, **kwargs) -> bool:
        return Support._db_update(Support, Support._check_mark(mark), where, **kwargs)

    @staticmethod
    def remove(mark: int = False, where=False) -> bool:
        return Support._db_remove(Support, Support._check_mark(mark), where)
