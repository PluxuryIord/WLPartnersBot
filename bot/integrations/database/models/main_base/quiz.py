from typing import Union, Optional

from sqlalchemy import Text, BOOLEAN
from sqlalchemy.orm import Mapped, mapped_column

from bot.integrations.database.models.main_base import Base
from bot.utils.models import Question, AnswerFeedback
from bot.utils.decorators import QuestionListType


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    questions: Mapped[list[Question]] = mapped_column(QuestionListType(), default=[
        Question(
            question="Вопрос номер 1",
            answers=["Ответ 1", "Ответ 2", "Ответ 3"],
            correct_answer=AnswerFeedback(id=0, text="Это верный ответ!"),
            incorrect_answer=AnswerFeedback(id=0, text="Это неверный ответ!")
        )
    ])
    page_number: Mapped[int] = mapped_column(default=0)
    status: Mapped[bool] = mapped_column(BOOLEAN, default=True)
    quiz_method: Mapped[str] = mapped_column(Text, default=None, nullable=True)


    @staticmethod
    def _check_mark(mark: int = False) -> Optional['Base']:
        return Quiz._base_check_mark(Quiz.id, mark, 0)

    @staticmethod
    def add(title: str, questions: list[Question], page_number: int, description: str, quiz_method: str = '0') -> bool:
        new_quiz = Quiz(title=title, questions=questions,
                        page_number=page_number, description=description,
                        quiz_method=quiz_method)
        return Quiz._db_add(new_quiz)

    @staticmethod
    def select(mark: int = False, where=False, all_scalars: bool = False) -> Union[list['Quiz'], 'Quiz']:
        return Quiz._db_select(Quiz, Quiz._check_mark(mark), where, all_scalars)

    @staticmethod
    def update(mark: int = False, where=False, **kwargs) -> bool:
        return Quiz._db_update(Quiz, Quiz._check_mark(mark), where, **kwargs)

    @staticmethod
    def remove(mark: int = False, where=False) -> bool:
        return Quiz._db_remove(Quiz, Quiz._check_mark(mark), where)
