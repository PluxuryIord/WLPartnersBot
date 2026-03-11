from aiogram import Dispatcher, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.integrations import DB
from bot.keyboards.admin import kb_admin_quiz
from bot.states.quiz import QuizCreation, QuizEdit
from bot.utils.models import Question, AnswerFeedback


async def quiz_menu(call: CallbackQuery, state: FSMContext):
    menu = await call.message.edit_text(
        '<b>🧩 Меню управления квизами:</b>\nВыберите действие:',
        reply_markup=kb_admin_quiz.menu
    )
    await state.update_data(menu=menu)


async def start_quiz_creation(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    menu = await callback.message.edit_text("📝 <b>Давай создадим новый квиз!</b>\n\n🔤 Введите название квиза:")
    await state.set_state(QuizCreation.title)
    await state.update_data(menu=menu)

async def set_quiz_title(message: Message, state: FSMContext):
    await message.delete()
    await state.update_data(title=message.text)
    data = await state.get_data()
    await data['menu'].edit_text(
        f"📌 <b>Название сохранено!</b>\n\n🗒 Теперь введите <b>описание квиза</b> — оно будет отображаться в превью перед началом:"
    )
    await state.set_state(QuizCreation.description)


async def set_quiz_description(message: Message, state: FSMContext):
    await message.delete()
    await state.update_data(description=message.text)
    data = await state.get_data()
    await data['menu'].edit_text(
        "❓ <b>Начнём добавление вопросов!</b>\n\n✍ Введите текст первого вопроса:"
    )
    await state.set_state(QuizCreation.question_text)


async def set_question_text(message: Message, state: FSMContext):
    await message.delete()
    await state.update_data(current_question_text=message.text)
    data = await state.get_data()

    await data['menu'].edit_text(
        "🖼 <b>Хотите прикрепить изображение к вопросу?</b>\n\n"
        "Отправьте изображение или нажмите 'Пропустить'.",
        reply_markup=kb_admin_quiz.skip_image_kb  # кнопка "Пропустить"
    )
    await state.set_state(QuizCreation.question_image)


async def set_question_answers(message: Message, state: FSMContext):
    await message.delete()
    answers = [ans.strip() for ans in message.text.split(',')]
    await state.update_data(current_answers=answers)
    data = await state.get_data()
    options = "\n".join([f"{i + 1}. {a}" for i, a in enumerate(answers)])
    await data['menu'].edit_text(
        f"📊 <b>Ответы:</b>\n{options}\n\n✅ <b>Укажите номер правильного ответа:</b>"
    )
    await state.set_state(QuizCreation.correct_index)

async def set_correct_feedback(message: Message, state: FSMContext):
    await message.delete()
    await state.update_data(correct_feedback=message.text)
    data = await state.get_data()
    await data['menu'].edit_text("🔴 <b>Введите текст для фидбека при неправильном ответе:</b>")
    await state.set_state(QuizCreation.incorrect_feedback)


async def set_incorrect_feedback(message: Message, state: FSMContext):
    await message.delete()
    data = await state.get_data()

    correct_idx = data['correct_index']
    correct_text = data['current_answers'][correct_idx]

    question = Question(
        question=data['current_question_text'],
        answers=data['current_answers'],
        correct_answer=AnswerFeedback(id=correct_idx, text=data['correct_feedback']),
        incorrect_answer=AnswerFeedback(id=correct_idx, text=message.text),
        image_path=data['question_image_id'] if data.get('question_image_id') else None
    )

    questions = data.get("questions", [])
    questions.append(question)
    await state.update_data(questions=questions)

    # 🧾 Составляем превью текущих вопросов
    preview = "<b>📚 Список вопросов в квизе:</b>\n\n"
    for i, q in enumerate(questions, start=1):
        answers_list = "\n".join([
            f"{'✅' if idx == q.correct_answer.id else '▫️'} {ans}"
            for idx, ans in enumerate(q.answers)
        ])
        preview += f"<b>{i}) {q.question}</b>\n{answers_list}\n\n"

    await data['menu'].edit_text(
        f"{preview}<b>➕ Вопрос добавлен.</b>\nХотите добавить ещё один?",
        reply_markup=kb_admin_quiz.confirm_add_more_question_kb
    )
    await state.set_state(QuizCreation.add_another_question)

async def add_another_question(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("<b>Введите текст следующего вопроса:</b>")
    await state.set_state(QuizCreation.question_text)

async def finish_quiz(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()

    DB.Quiz.add(
        title=data['title'],
        description=data['description'],
        questions=data['questions'],
        page_number=0
    )

    await callback.message.edit_text(
        "🎉 <b>Квиз успешно создан!</b>\n\n"
        "📝 <b>Название:</b> {title}\n"
        "📄 <b>Описание:</b> {description}\n"
        "❓ <b>Количество вопросов:</b> {count}\n\n"
        "Вы можете перейти к списку квизов или отредактировать созданный квиз.".format(
            title=data['title'],
            description=data['description'],
            count=len(data['questions'])
        ),
        reply_markup=kb_admin_quiz.back_to_quiz
    )
    await state.clear()

async def view_quizzes(callback: CallbackQuery):
    quizzes = DB.Quiz.select(all_scalars=True, where=DB.Quiz.status == True)
    if not quizzes:
        await callback.message.edit_text(
            "⚠️ <b>Нет доступных квизов.</b>\nСоздайте первый квиз, чтобы начать!",
            reply_markup=kb_admin_quiz.back_to_quiz
        )
    else:
        await callback.message.edit_text(
            "📋 <b>Список квизов:</b>\nВыберите один для просмотра:",
            reply_markup=await kb_admin_quiz.quiz_list_kb(quizzes)
        )


async def show_quiz_detail(callback: CallbackQuery):
    quiz_id = int(callback.data.split(":")[1])
    quiz = DB.Quiz.select(quiz_id)
    if not quiz:
        await callback.message.edit_text("❌ <i>Квиз не найден.</i>", reply_markup=kb_admin_quiz.back_to_quiz)
        return

    text = (
        f"📌 <b>Название:</b> {quiz.title}\n"
        f"📝 <b>Описание:</b> {quiz.description}\n"
        f"❓ <b>Количество вопросов:</b> {len(quiz.questions)}"
    )
    await callback.message.edit_text(text, reply_markup=await kb_admin_quiz.quiz_detail_actions_kb(quiz_id))


async def set_correct_index(message: Message, state: FSMContext):
    await message.delete()
    try:
        idx = int(message.text.strip()) - 1
        data = await state.get_data()
        if idx < 0 or idx >= len(data["current_answers"]):
            raise ValueError
        await state.update_data(correct_index=idx)
        await data['menu'].edit_text("🟢 <b>Теперь введите текст для фидбека при правильном ответе:</b>")
        await state.set_state(QuizCreation.correct_feedback)
    except ValueError:
        data = await state.get_data()
        await data['menu'].edit_text("⚠️ <b>Неверный номер ответа!</b>\nВведите корректное число из списка выше.")

async def view_quiz_questions(callback: CallbackQuery, state: FSMContext):
    quiz_id = int(callback.data.split(":")[1])
    quiz = DB.Quiz.select(quiz_id)
    if not quiz:
        await callback.message.edit_text("❌ <i>Квиз не найден.</i>", reply_markup=kb_admin_quiz.back_to_quiz)
        return

    questions = quiz.questions
    if not questions:
        await callback.message.edit_text("🕳️ В этом квизе пока нет вопросов.", reply_markup=kb_admin_quiz.back_to_quiz)
        return

    text = "📖 <b>Вопросы квиза:</b>\n\n"
    for idx, q in enumerate(questions, start=1):
        text += f"📌 {idx}. {q.question}\n"
    await callback.message.edit_text(text, reply_markup=await kb_admin_quiz.quiz_questions_kb(quiz_id, questions))


async def edit_quiz(callback: CallbackQuery, state: FSMContext):
    quiz_id = int(callback.data.split(":")[1])
    quiz = DB.Quiz.select(quiz_id)
    if not quiz:
        await callback.message.edit_text("❌ <i>Квиз не найден.</i>", reply_markup=kb_admin_quiz.back_to_quiz)
        return

    await state.set_state(QuizEdit.choosing_action)
    await state.update_data(quiz_id=quiz_id)
    await callback.message.edit_text(
        f"🛠 <b>Редактирование квиза:</b>\n\n"
        f"📌 <b>Название:</b> {quiz.title}\n"
        f"📝 <b>Описание:</b> {quiz.description}",
        reply_markup=kb_admin_quiz.edit_quiz_kb
    )


async def edit_quiz_title(callback: CallbackQuery, state: FSMContext):
    await state.set_state(QuizEdit.editing_title)
    await callback.message.edit_text("✏️ <b>Введите новое название квиза:</b>")


async def set_new_quiz_title(message: Message, state: FSMContext):
    await message.delete()
    data = await state.get_data()
    DB.Quiz.update(mark=int(data['quiz_id']), title=message.text)
    await data['menu'].edit_text(
        "✅ <b>Название квиза обновлено!</b>",
        reply_markup=kb_admin_quiz.back_to_quiz
    )
    await state.clear()


async def delete_quiz(callback: CallbackQuery):
    quiz_id = int(callback.data.split(":")[1])
    DB.Quiz.update(quiz_id, status=False)
    await callback.message.edit_text("🗑️ <b>Квиз был успешно удалён.</b>", reply_markup=kb_admin_quiz.back_to_quiz)

async def edit_question(callback: CallbackQuery, state: FSMContext):
    quiz_id, question_index = map(int, callback.data.split(":")[1:])

    quiz = DB.Quiz.select(quiz_id)
    if not quiz or question_index >= len(quiz.questions):
        await callback.message.edit_text("❌ <i>Вопрос не найден.</i>", reply_markup=kb_admin_quiz.back_to_quiz)
        return

    question = quiz.questions[question_index]

    await state.set_state(QuizEdit.editing_question_text)
    await state.update_data(quiz_id=quiz_id, question_index=question_index)

    await callback.message.edit_text(
        f"✍ <b>Редактирование вопроса:</b>\n\n"
        f"📌 <b>Текущий текст:</b> {question.question}\n\n"
        f"📝 Введите <b>новый текст</b> вопроса:",
        reply_markup=kb_admin_quiz.cancel_edit_kb
    )

async def set_editing_question_text(message: Message, state: FSMContext):
    await message.delete()
    data = await state.get_data()

    new_text = message.text
    quiz = DB.Quiz.select(data['quiz_id'])
    question = quiz.questions[data['question_index']]
    question.question = new_text

    await state.set_state(QuizEdit.editing_question_answers)
    await state.update_data(edited_question=question)

    await data['menu'].edit_text(
        "📋 <b>Теперь введите новые варианты ответов:</b>\n\n"
        "<code>пример: Один, Два, Три, Четыре</code>"
    )

async def set_editing_question_answers(message: Message, state: FSMContext):
    await message.delete()
    data = await state.get_data()

    answers = [ans.strip() for ans in message.text.split(',')]
    if len(answers) < 2:
        await data['menu'].edit_text("⚠️ <b>Введите как минимум два варианта ответа.</b>")
        return

    question = data['edited_question']
    question.answers = answers
    question.correct_answer.id = 0  # Сброс правильного, нужно выбрать заново

    quiz = DB.Quiz.select(data['quiz_id'])
    quiz.questions[data['question_index']] = question
    DB.Quiz.update(data['quiz_id'], questions=quiz.questions)

    await data['menu'].edit_text(
        f"✅ <b>Вопрос обновлён!</b>\n\n"
        f"💬 Новый текст: {question.question}\n"
        f"📌 Ответы:\n" +
        "\n".join([f"{i + 1}. {a}" for i, a in enumerate(answers)]),
        reply_markup=kb_admin_quiz.back_to_quiz
    )
    await state.clear()

async def delete_question(callback: CallbackQuery):
    quiz_id, question_index = map(int, callback.data.split(":")[1:])
    quiz = DB.Quiz.select(quiz_id)

    if not quiz or question_index >= len(quiz.questions):
        await callback.message.edit_text("❌ <i>Вопрос не найден.</i>", reply_markup=kb_admin_quiz.back_to_quiz)
        return

    updated_questions = quiz.questions[:question_index] + quiz.questions[question_index + 1:]
    DB.Quiz.update(quiz_id, questions=updated_questions)

    await callback.message.edit_text(
        "🗑️ <b>Вопрос удалён!</b>",
        reply_markup=await kb_admin_quiz.quiz_questions_kb(quiz_id, updated_questions)
    )

async def cancel_edit_question(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    quiz_id = data.get("quiz_id")
    quiz = DB.Quiz.select(quiz_id)

    if not quiz:
        await callback.message.edit_text("❌ Квиз не найден.", reply_markup=kb_admin_quiz.back_to_quiz)
        return

    await callback.message.edit_text(
        "✏️ <b>Редактирование отменено.</b>",
        reply_markup=await kb_admin_quiz.quiz_questions_kb(quiz_id, quiz.questions)
    )
    await state.clear()

async def set_question_image(message: Message, state: FSMContext):
    file_id = None
    if message.photo:
        file_id = message.photo[-1].file_id
    else:
        await message.answer("❌ Пожалуйста, отправьте изображение как фото (без сжатия)")
        return

    # Тут можешь сохранить file_id в БД или FSM
    await state.update_data(question_image_id=file_id)
    data = await state.get_data()
    await data['menu'].edit_text(text="✅ Изображение сохранено.", reply_markup=kb_admin_quiz.skip_image_kb)
    await message.delete()


async def skip_question_image(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📋 <b>Теперь введите варианты ответа</b>\n\n📌 Укажите все варианты через запятую:\n<code>пример: Красный, Зелёный</code>"
    )
    await state.set_state(QuizCreation.answers)

def register_handlers_admin_quiz(dp: Dispatcher):
    dp.callback_query.register(finish_quiz, F.data == 'finish_quiz')
    dp.callback_query.register(add_another_question, F.data == 'add_question')
    dp.message.register(set_incorrect_feedback, QuizCreation.incorrect_feedback)
    dp.message.register(set_correct_feedback, QuizCreation.correct_feedback)
    dp.message.register(set_question_answers, QuizCreation.answers)
    dp.message.register(set_question_text, QuizCreation.question_text)
    dp.message.register(set_quiz_description, QuizCreation.description)
    dp.message.register(set_quiz_title, QuizCreation.title)
    dp.callback_query.register(start_quiz_creation, F.data == 'create_quiz')
    dp.callback_query.register(quiz_menu, F.data == 'admin_quiz')
    dp.callback_query.register(view_quizzes, F.data == 'view_quizzes')
    dp.callback_query.register(show_quiz_detail, F.data.startswith('quiz_detail'))
    dp.message.register(set_correct_index, QuizCreation.correct_index)
    dp.callback_query.register(view_quiz_questions, F.data.startswith('quiz_questions:'))
    dp.callback_query.register(edit_quiz, F.data.startswith('edit_quiz:'))
    dp.callback_query.register(edit_quiz_title, F.data == 'edit_quiz_title')
    dp.message.register(set_new_quiz_title, QuizEdit.editing_title)
    dp.callback_query.register(delete_quiz, F.data.startswith('delete_quiz:'))
    dp.callback_query.register(edit_question, F.data.startswith("edit_question:"))
    dp.message.register(set_editing_question_text, QuizEdit.editing_question_text)
    dp.message.register(set_editing_question_answers, QuizEdit.editing_question_answers)
    dp.callback_query.register(delete_question, F.data.startswith("delete_question:"))
    dp.callback_query.register(cancel_edit_question, F.data == "cancel_edit_question")
    dp.message.register(set_question_image, QuizCreation.question_image)
    dp.callback_query.register(skip_question_image, F.data == "skip_image")

