from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from . import Base

if TYPE_CHECKING:
    from typing import Union, Optional


class GroupChat(Base):
    __tablename__ = 'group_chats'

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    date_added: Mapped[datetime]
    is_active: Mapped[bool] = mapped_column(default=True)

    @staticmethod
    def _check_mark(mark: int = False) -> Optional['Base']:
        return GroupChat._base_check_mark(GroupChat.chat_id, mark, 0)

    @staticmethod
    def add(chat_id: int, title: str) -> bool:
        new_group = GroupChat(chat_id=chat_id, title=title, date_added=datetime.now())
        return GroupChat._db_add(new_group)

    @staticmethod
    def select(mark: int = False, where=False, all_scalars: bool = False) -> Union[list['GroupChat'], 'GroupChat']:
        return GroupChat._db_select(GroupChat, GroupChat._check_mark(mark), where, all_scalars)

    @staticmethod
    def update(mark: int = False, where=False, **kwargs) -> bool:
        return GroupChat._db_update(GroupChat, GroupChat._check_mark(mark), where, **kwargs)

    @staticmethod
    def remove(mark: int = False, where=False) -> bool:
        return GroupChat._db_remove(GroupChat, GroupChat._check_mark(mark), where)
