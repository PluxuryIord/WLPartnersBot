from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Integer, Text, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column

from . import Base

if TYPE_CHECKING:
    from typing import Union, Optional


class EventQuestion(Base):
    __tablename__ = 'event_questions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str] = mapped_column(Text, nullable=False, default='text')
    options: Mapped[dict] = mapped_column(JSON, nullable=True, default=None)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    @staticmethod
    def _check_mark(mark: int = False) -> Optional['Base']:
        return EventQuestion._base_check_mark(EventQuestion.id, mark, 0)

    @staticmethod
    def add(question_text: str, question_type: str = 'text',
            options: list = None, order: int = 0) -> int:
        new_q = EventQuestion(
            question_text=question_text,
            question_type=question_type,
            options=options,
            order=order,
        )
        return EventQuestion._db_add(new_q, True)

    @staticmethod
    def select(mark: int = False, where=False,
               all_scalars: bool = False) -> Union[list['EventQuestion'], 'EventQuestion']:
        return EventQuestion._db_select(EventQuestion, EventQuestion._check_mark(mark), where, all_scalars)

    @staticmethod
    def update(mark: int = False, where=False, **kwargs) -> bool:
        return EventQuestion._db_update(EventQuestion, EventQuestion._check_mark(mark), where, **kwargs)

    @staticmethod
    def remove(mark: int = False, where=False) -> bool:
        return EventQuestion._db_remove(EventQuestion, EventQuestion._check_mark(mark), where)
