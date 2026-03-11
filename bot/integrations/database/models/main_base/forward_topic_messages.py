"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from . import Base

if TYPE_CHECKING:
    from typing import Optional, Union


class ForwardTopicMessages(Base):
    __tablename__ = 'forward_topic_messages'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int]
    forward_message_id: Mapped[int]
    from_entity: Mapped[str] = mapped_column(Text)

    @staticmethod
    def _check_mark(mark: int = False) -> Optional['Base']:
        return ForwardTopicMessages._base_check_mark(ForwardTopicMessages.id, mark, 0)

    @staticmethod
    def add(user_id: int, message_id: int, forward_message_id: int, from_entity: str) -> int:
        new_message = ForwardTopicMessages(chat_id=user_id, message_id=message_id,
                                           forward_message_id=forward_message_id,
                                           from_entity=from_entity)
        return ForwardTopicMessages._db_add(new_message, autoincrement_id=True)

    @staticmethod
    def select(mark: int = False, where=False, all_scalars: bool = False
               ) -> Union[list['ForwardTopicMessages'], 'ForwardTopicMessages']:
        return ForwardTopicMessages._db_select(ForwardTopicMessages,
                                               ForwardTopicMessages._check_mark(mark), where, all_scalars)

    @staticmethod
    def update(mark: int = False, where=False, **kwargs) -> bool:
        return ForwardTopicMessages._db_update(ForwardTopicMessages,
                                               ForwardTopicMessages._check_mark(mark), where, **kwargs)

    @staticmethod
    def remove(mark: int = False, where=False) -> bool:
        return ForwardTopicMessages._db_remove(ForwardTopicMessages, ForwardTopicMessages._check_mark(mark), where)
