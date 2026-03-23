from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Integer, BigInteger, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from . import Base

if TYPE_CHECKING:
    from typing import Union, Optional


class EventAnswer(Base):
    __tablename__ = 'event_answers'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    question_id: Mapped[int] = mapped_column(Integer, ForeignKey('event_questions.id'), nullable=False)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

    @staticmethod
    def _check_mark(mark: int = False) -> Optional['Base']:
        return EventAnswer._base_check_mark(EventAnswer.id, mark, 0)

    @staticmethod
    def add(user_id: int, question_id: int, answer_text: str) -> int:
        new_a = EventAnswer(
            user_id=user_id,
            question_id=question_id,
            answer_text=answer_text,
            created_at=datetime.now(),
        )
        return EventAnswer._db_add(new_a, True)

    @staticmethod
    def select(mark: int = False, where=False,
               all_scalars: bool = False) -> Union[list['EventAnswer'], 'EventAnswer']:
        return EventAnswer._db_select(EventAnswer, EventAnswer._check_mark(mark), where, all_scalars)

    @staticmethod
    def update(mark: int = False, where=False, **kwargs) -> bool:
        return EventAnswer._db_update(EventAnswer, EventAnswer._check_mark(mark), where, **kwargs)

    @staticmethod
    def remove(mark: int = False, where=False) -> bool:
        return EventAnswer._db_remove(EventAnswer, EventAnswer._check_mark(mark), where)
