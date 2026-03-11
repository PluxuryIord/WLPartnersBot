"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Boolean, BigInteger
from sqlalchemy.orm import Mapped, mapped_column

from . import Base

if TYPE_CHECKING:
    from typing import Optional, Union


class Randomizer(Base):
    __tablename__ = 'randomizer'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.user_id'), primary_key=True)
    is_winner: Mapped[bool] = mapped_column(Boolean, default=False)
    random_key: Mapped[int] = mapped_column(BigInteger)
    date_reg: Mapped[datetime]

    @staticmethod
    def _check_mark(mark: int = False) -> Optional['Base']:
        return Randomizer._base_check_mark(Randomizer.user_id, mark, 0)

    @staticmethod
    def add(user_id: int, random_key: int) -> bool:
        new_randomizer = Randomizer(user_id=user_id, date_reg=datetime.now(), random_key=random_key)
        return Randomizer._db_add(new_randomizer)

    @staticmethod
    def select(mark: int = False, where=False, all_scalars: bool = False) -> Union[list['Randomizer'], 'Randomizer']:
        return Randomizer._db_select(Randomizer, Randomizer._check_mark(mark), where, all_scalars)

    @staticmethod
    def update(mark: int = False, where=False, **kwargs) -> bool:
        return Randomizer._db_update(Randomizer, Randomizer._check_mark(mark), where, **kwargs)

    @staticmethod
    def remove(mark: int = False, where=False) -> bool:
        return Randomizer._db_remove(Randomizer, Randomizer._check_mark(mark), where)
