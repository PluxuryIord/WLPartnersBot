"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Boolean, Text, BigInteger
from sqlalchemy.orm import Mapped, mapped_column

from . import Base

if TYPE_CHECKING:
    from typing import Optional, Union


class Winner(Base):
    __tablename__ = 'winners'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.user_id'), primary_key=True)
    is_mailed: Mapped[bool] = mapped_column(Boolean, default=False)
    prize: Mapped[str] = mapped_column(Text, nullable=True, default=None)
    date_reg: Mapped[datetime]

    @staticmethod
    def _check_mark(mark: int = False) -> Optional['Base']:
        return Winner._base_check_mark(Winner.user_id, mark, 0)

    @staticmethod
    def add(user_id: int, prize: str) -> bool:
        new_winner = Winner(user_id=user_id, date_reg=datetime.now(), prize=prize)
        return Winner._db_add(new_winner)

    @staticmethod
    def select(mark: int = False, where=False, all_scalars: bool = False) -> Union[list['Winner'], 'Winner']:
        return Winner._db_select(Winner, Winner._check_mark(mark), where, all_scalars)

    @staticmethod
    def update(mark: int = False, where=False, **kwargs) -> bool:
        return Winner._db_update(Winner, Winner._check_mark(mark), where, **kwargs)

    @staticmethod
    def remove(mark: int = False, where=False) -> bool:
        return Winner._db_remove(Winner, Winner._check_mark(mark), where)
