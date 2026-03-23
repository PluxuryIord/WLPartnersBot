import json
from sqlalchemy.types import TypeDecorator

from bot.utils.models import Question, AnswerFeedback
from sqlalchemy import Text


class QuestionListType(TypeDecorator):
    impl = Text

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        # Pydantic объекты → dict → JSON
        return json.dumps([q.dict() for q in value], ensure_ascii=False)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        # JSON → dict → Pydantic объекты
        data = json.loads(value)
        return [Question(**q) for q in data]