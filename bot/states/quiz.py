
from aiogram.fsm.state import State, StatesGroup

class QuizCreation(StatesGroup):
    title = State()
    description = State()
    question_text = State()
    answers = State()
    correct_feedback = State()
    incorrect_feedback = State()
    add_another_question = State()
    correct_index = State()
    question_image = State()


class QuizEdit(StatesGroup):
    choosing_quiz = State()
    choosing_action = State()
    editing_title = State()
    editing_description = State()
    choosing_question = State()
    editing_question_text = State()
    editing_answers = State()
    editing_correct_index = State()
    editing_correct_feedback = State()
    editing_incorrect_feedback = State()
    editing_question_answers = State()

class QuizRun(StatesGroup):
    answering = State()