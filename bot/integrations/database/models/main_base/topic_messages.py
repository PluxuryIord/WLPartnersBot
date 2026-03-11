"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, JSON
from sqlalchemy.orm import Mapped, mapped_column

from . import Base

if TYPE_CHECKING:
    from typing import Optional, Union


class TopicMessages(Base):
    __tablename__ = 'topic_messages'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    messages: Mapped[dict] = mapped_column(JSON)
    admin_id: Mapped[int] = mapped_column(BigInteger)

    @staticmethod
    def _check_mark(mark: int = False) -> Optional['Base']:
        return TopicMessages._base_check_mark(TopicMessages.id, mark, 0)

    @staticmethod
    def add(user_id: int, caption: bool, messages: dict, admin_id: int) -> int:
        new_message = TopicMessages(chat_id=user_id, messages={'ids': messages, 'caption': caption}, admin_id=admin_id)
        return TopicMessages._db_add(new_message, autoincrement_id=True)

    @staticmethod
    def select(mark: int = False, where=False, all_scalars: bool = False
               ) -> Union[list['TopicMessages'], 'TopicMessages']:
        return TopicMessages._db_select(TopicMessages, TopicMessages._check_mark(mark), where, all_scalars)

    @staticmethod
    def update(mark: int = False, where=False, **kwargs) -> bool:
        return TopicMessages._db_update(TopicMessages, TopicMessages._check_mark(mark), where, **kwargs)

    @staticmethod
    def remove(mark: int = False, where=False) -> bool:
        return TopicMessages._db_remove(TopicMessages, TopicMessages._check_mark(mark), where)
