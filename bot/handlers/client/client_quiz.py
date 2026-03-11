"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""
import logging

from aiogram import Dispatcher, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.integrations import DB
from bot.integrations.google.spreadsheets.google_sheets import new_answers
from bot.keyboards.client import kb_client_quiz
from bot.states.quiz import QuizRun
from bot.utils.models import Question
import asyncio

async def main(call: CallbackQuery, state: FSMContext):
    quiz_id = int(call.data.split(":")[1])
    user_id = call.from_user.id

    quiz = DB.Quiz.select(quiz_id)
    if not quiz:
        await call.message.edit_text("❌ Квиз не найден.")
        return

    if not quiz.status:
        await call.message.edit_text("❌ Квиз завершён!")
        return

    # Проверка — проходил ли пользователь этот квиз
    passed = DB.QuizResult.select(where=[DB.QuizResult.user_id == user_id, DB.QuizResult.quiz_id == quiz_id])
    if passed:
        await call.answer("📌 Вы уже проходили этот квиз!", show_alert=True)
        return

    await state.set_state(QuizRun.answering)
    await state.update_data(
        quiz_id=quiz_id,
        questions=quiz.questions,
        current_index=0,
        correct=0,
        answers=[]
    )
    await call.message.delete()
    await send_quiz_question(call.message, quiz.questions[0], 0)

# Пример исправленного кода
async def send_quiz_question(message: Message, question: Question, index: int):
    if question.image_path:
        await message.answer_photo(
            photo=question.image_path,
            caption=f"❓ <b>{question.question}</b>" if question.question else "",
            reply_markup=await kb_client_quiz.send_quiz_question(question, index),
            parse_mode="HTML"
        )
    else:
        await message.answer(
            f"❓ <b>{question.question}</b>",
            reply_markup=await kb_client_quiz.send_quiz_question(question, index),
            parse_mode="HTML"
        )

async def handle_quiz_answer(callback: CallbackQuery, state: FSMContext):
    _, q_idx, selected = callback.data.split(":")
    q_idx = int(q_idx)
    selected = int(selected)

    data = await state.get_data()
    questions = data["questions"]
    current_question = questions[q_idx]

    correct = data["correct"]
    if selected == current_question.correct_answer.id:
        correct += 1

    data["answers"].append(str(selected))
    await state.update_data(correct=correct, answers=data["answers"])
    await callback.message.delete()
    await callback.answer(f"💬 Ответ засчитан!")

    if q_idx + 1 < len(questions):
        await state.update_data(current_index=q_idx + 1)
        await send_quiz_question(callback.message, questions[q_idx + 1], q_idx + 1)
    else:
        await finish_quiz_run(callback, state)

async def finish_quiz_run(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    DB.QuizResult.add(
        user_id=callback.from_user.id,
        quiz_id=data["quiz_id"],
        correct_answers=data["correct"],
        total_questions=len(data["questions"]),
        answers=data["answers"])
    await callback.message.answer(
        '<b>Спасибо за участие, твои ответы засчитаны! Теперь ты участвуешь в розыгрыше челленджа! Жди сообщения от бота</b>'
    )
    try:
        await new_answers(str(callback.from_user.id), ','.join(data["answers"]), str(data["quiz_id"]))
    except Exception as _e:
        logging.warning(_e)
    await state.clear()

def register_handlers_client_quiz(dp: Dispatcher):
    dp.callback_query.register(main, F.data.startswith('client_quiz'))
    dp.callback_query.register(handle_quiz_answer, F.data.startswith("answer:"))