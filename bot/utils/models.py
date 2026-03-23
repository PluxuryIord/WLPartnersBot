from dataclasses import dataclass

from pydantic import BaseModel
from typing import List

class AnswerFeedback(BaseModel):
    id: int
    text: str


class Question(BaseModel):
    question: str
    answers: List[str]
    correct_answer: AnswerFeedback
    incorrect_answer: AnswerFeedback
    image_path: str | None = None

class QuizCreateSchema(BaseModel):
    title: str
    questions: List[Question]


class QuizReadSchema(QuizCreateSchema):
    id: int

    model_config = {
        "from_attributes": True
    }

@dataclass
class QuizResult:
    user_id: int
    quiz_id: int
    correct_answers: int
    total_questions: int
    answers: List[int]  # Индексы выбранных ответов