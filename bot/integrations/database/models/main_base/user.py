"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import Base

if TYPE_CHECKING:
    from .admin import Admin
    from .alert import Alert
    from typing import Optional, Union


class User(Base):
    __tablename__ = 'users'
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    full_name: Mapped[str] = mapped_column(Text)
    username: Mapped[str] = mapped_column(Text, nullable=True)
    date_reg: Mapped[datetime]
    menu_id: Mapped[int] = mapped_column(nullable=True, default=0)
    thread_id: Mapped[int] = mapped_column(nullable=True)
    banned: Mapped[bool] = mapped_column(default=False)
    rl_full_name: Mapped[str] = mapped_column(Text, nullable=True, default=None)
    role: Mapped[str] = mapped_column(Text, nullable=True, default=None)
    graph: Mapped[str] = mapped_column(Text, nullable=True, default=None)
    phone_number: Mapped[str] = mapped_column(Text, nullable=True, default=None)
    registered: Mapped[bool] = mapped_column(default=False)
    email: Mapped[str] = mapped_column(Text, nullable=True, default=None)
    personal_label: Mapped[bool] = mapped_column(default=False)
    show_qr: Mapped[bool] = mapped_column(default=False)

    admin: Mapped['Admin'] = relationship(back_populates='user', cascade='all, delete-orphan')
    alert: Mapped['Alert'] = relationship(back_populates='user', cascade='all, delete-orphan')

    @staticmethod
    def _check_mark(mark: int = False) -> Optional['Base']:
        return User._base_check_mark(User.user_id, mark, 0)

    @staticmethod
    def add(user_id: int, full_name: str, username: str, thread_id: int) -> bool:
        new_user = User(user_id=user_id, full_name=full_name, username=username,
                        date_reg=datetime.now(), thread_id=thread_id)
        return User._db_add(new_user)

    @staticmethod
    def select(mark: int = False, where=False, all_scalars: bool = False) -> Union[list['User'], 'User']:
        return User._db_select(User, User._check_mark(mark), where, all_scalars)

    @staticmethod
    def update(mark: int = False, where=False, **kwargs) -> bool:
        return User._db_update(User, User._check_mark(mark), where, **kwargs)

    @staticmethod
    def remove(mark: int = False, where=False) -> bool:
        return User._db_remove(User, User._check_mark(mark), where)
