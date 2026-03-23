from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from . import Base

if TYPE_CHECKING:
    from typing import Union, Optional


class UserAuth(Base):
    __tablename__ = 'user_auth'

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    token: Mapped[str] = mapped_column(Text, nullable=True, default=None)
    auth_date: Mapped[datetime]

    @staticmethod
    def _check_mark(mark: int = False) -> Optional['Base']:
        return UserAuth._base_check_mark(UserAuth.user_id, mark, 0)

    @staticmethod
    def add(user_id: int, email: str, token: str = None) -> bool:
        new_auth = UserAuth(user_id=user_id, email=email, token=token, auth_date=datetime.now())
        return UserAuth._db_add(new_auth)

    @staticmethod
    def select(mark: int = False, where=False, all_scalars: bool = False) -> Union[list['UserAuth'], 'UserAuth']:
        return UserAuth._db_select(UserAuth, UserAuth._check_mark(mark), where, all_scalars)

    @staticmethod
    def update(mark: int = False, where=False, **kwargs) -> bool:
        return UserAuth._db_update(UserAuth, UserAuth._check_mark(mark), where, **kwargs)

    @staticmethod
    def remove(mark: int = False, where=False) -> bool:
        return UserAuth._db_remove(UserAuth, UserAuth._check_mark(mark), where)
