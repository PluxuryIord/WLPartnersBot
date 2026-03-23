from typing import Union, Optional
from sqlalchemy import Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from bot.integrations.database.models.main_base import Base


class QuizResult(Base):
    __tablename__ = "quizResults"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    quiz_id: Mapped[int] = mapped_column(Integer, ForeignKey("quizzes.id"), nullable=False)
    correct_answers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    answers: Mapped[str] = mapped_column(Text, nullable=False)  # Список всех ответов пользователя

    @staticmethod
    def _check_mark(mark: int = False) -> Optional['Base']:
        return QuizResult._base_check_mark(QuizResult.id, mark, 0)

    @staticmethod
    def add(user_id: int, quiz_id: int, correct_answers: int, total_questions: int, answers: list[str]) -> bool:
        result = QuizResult(user_id=user_id, quiz_id=quiz_id, correct_answers=correct_answers, total_questions=total_questions, answers=",".join(answers))
        return QuizResult._db_add(result)

    @staticmethod
    def select(mark: int = False, where=False, all_scalars: bool = False) -> Union[list['QuizResult'], 'QuizResult']:
        return QuizResult._db_select(QuizResult, QuizResult._check_mark(mark), where, all_scalars)

    @staticmethod
    def update(mark: int = False, where=False, **kwargs) -> bool:
        return QuizResult._db_update(QuizResult, QuizResult._check_mark(mark), where, **kwargs)

    @staticmethod
    def remove(mark: int = False, where=False) -> bool:
        return QuizResult._db_remove(QuizResult, QuizResult._check_mark(mark), where)
