from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.integrations.database.models.main_base import Quiz
from bot.utils.models import Question
from bot.utils.telegram import create_inline


async def quiz_list_kb(quizzes: list[Quiz]) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text=quiz.title, callback_data=f"quiz_detail:{quiz.id}")]
        for quiz in quizzes
    ]
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"client_back_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

async def quiz_detail_actions_kb(quiz_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📖 Вопросы", callback_data=f"quiz_questions:{quiz_id}")],
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_quiz:{quiz_id}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_quiz:{quiz_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"client_back_menu")]
    ])

menu = create_inline(
    [
        ['📋 Просмотр квизов', 'call', 'view_quizzes'],
        ['➕ Создать квиз', 'call', 'create_quiz'],
        ['🔙 Назад', 'call', 'client_back_menu']
    ],
1)

confirm_add_more_question_kb = create_inline(
    [
        ['➕ Ещё вопрос', 'call', 'add_question'],
        ['✅ Завершить', 'call', 'finish_quiz'],
    ],
1)

back_to_quiz = create_inline(
    [['🔙 Назад', 'call', 'admin_quiz']], 1
)

async def quiz_questions_kb(quiz_id: int, questions: list[Question]) -> InlineKeyboardMarkup:
    buttons = []

    for idx, q in enumerate(questions):
        row = [
            InlineKeyboardButton(
                text=f"✏️ {idx + 1}) {q.question[:25]}...",
                callback_data=f"edit_question:{quiz_id}:{idx}"
            ),
            InlineKeyboardButton(
                text="🗑️",
                callback_data=f"delete_question:{quiz_id}:{idx}"
            )
        ]
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="view_quizzes")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

cancel_edit_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="cancel_edit_question")]
    ]
)


edit_quiz_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="✏️ Редактировать название", callback_data="edit_quiz_title")],
    [InlineKeyboardButton(text="🗑️ Удалить квиз", callback_data="delete_quiz")],
    [InlineKeyboardButton(text="🔙 Назад", callback_data="view_quizzes")]
])


skip_image_kb = create_inline(
    [['⏭ Пропустить', 'call', 'skip_image']], 1
)