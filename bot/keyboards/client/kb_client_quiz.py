from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.utils.telegram import create_inline


async def start_quiz(quiz_id: int):
    return create_inline(
        [
            ['📋 Пройти квиз', 'call', f'start_quiz:{quiz_id}'],
            ['🔙 Меню', 'call', 'client_back_menu'],
        ], 1
    )

async def send_quiz_question(question, index):
    buttons = [
        [InlineKeyboardButton(text=ans, callback_data=f"answer:{index}:{i}")]
        for i, ans in enumerate(question.answers)
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
