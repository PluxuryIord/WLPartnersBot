"""
Admin handlers for managing event questionnaire (anketa) questions.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram import Dispatcher
    from aiogram.fsm.context import FSMContext
    from aiogram.types import CallbackQuery, Message

from aiogram import F
from aiogram.exceptions import TelegramAPIError

from bot.integrations import DB
from bot.initialization import config
from bot.keyboards.admin import kb_admin_event
from bot.states.wait_question import FsmAddQuestion, FsmEditQuestion


async def admin_event_questions(call: CallbackQuery, state: FSMContext):
    """Show list of all event questions."""
    if await state.get_state():
        await state.clear()
    questions = DB.EventQuestion.select(all_scalars=True)
    questions = sorted(questions, key=lambda q: q.order) if questions else []
    text = '<b>📋 Анкета мероприятия</b>\n\n'
    if questions:
        text += f'Всего вопросов: {len(questions)}'
    else:
        text += 'Вопросов пока нет. Добавьте первый!'
    await call.message.edit_text(text, reply_markup=kb_admin_event.questions_list(questions))
    await call.answer()


async def view_question(call: CallbackQuery):
    """View single question details."""
    qid = int(call.data.split(':')[1])
    q = DB.EventQuestion.select(mark=qid)
    if not q:
        return await call.answer('Вопрос не найден', show_alert=True)
    type_label = 'Выбор из вариантов' if q.question_type == 'choice' else 'Текстовый ответ'
    text = (
        f'<b>Вопрос #{q.id}</b>\n\n'
        f'<b>Текст:</b> {q.question_text}\n'
        f'<b>Тип:</b> {type_label}\n'
        f'<b>Порядок:</b> {q.order}\n'
        f'<b>Статус:</b> {"✅ Активен" if q.is_active else "❌ Выключен"}'
    )
    if q.question_type == 'choice' and q.options:
        text += '\n\n<b>Варианты ответа:</b>\n'
        for i, opt in enumerate(q.options, 1):
            text += f'  {i}. {opt}\n'
    await call.message.edit_text(text, reply_markup=kb_admin_event.question_detail(qid, q.is_active))
    await call.answer()


# ---- Add question ----

async def add_question_start(call: CallbackQuery, state: FSMContext):
    """Start adding a new question: ask for text."""
    await call.message.edit_text(
        '<b>Введите текст нового вопроса:</b>',
        reply_markup=kb_admin_event.cancel_fsm,
    )
    await state.set_state(FsmAddQuestion.wait_text)
    await call.answer()


async def add_question_text(message: Message, state: FSMContext):
    """Received question text, ask for type."""
    await message.delete()
    await state.update_data(new_question_text=message.text)
    data = await state.get_data()
    menu_msg = data.get('fsm_menu')
    if menu_msg:
        try:
            await menu_msg.delete()
        except TelegramAPIError:
            ...
    menu = await message.answer(
        f'<b>Текст вопроса:</b> {message.text}\n\n<b>Выберите тип ответа:</b>',
        reply_markup=kb_admin_event.question_type_select,
    )
    await state.update_data(fsm_menu=menu)
    await state.set_state(FsmAddQuestion.wait_type)


async def add_question_type(call: CallbackQuery, state: FSMContext):
    """Received type selection."""
    q_type = call.data.split(':')[1]
    await state.update_data(new_question_type=q_type)

    if q_type == 'choice':
        await call.message.edit_text(
            '<b>Введите варианты ответа через запятую:</b>\n\n'
            '<i>Пример: Вариант 1, Вариант 2, Вариант 3</i>',
            reply_markup=kb_admin_event.cancel_fsm,
        )
        await state.set_state(FsmAddQuestion.wait_options)
    else:
        # Text type — save immediately
        data = await state.get_data()
        questions = DB.EventQuestion.select(all_scalars=True) or []
        max_order = max((q.order for q in questions), default=0)
        DB.EventQuestion.add(
            question_text=data['new_question_text'],
            question_type='text',
            order=max_order + 1,
        )
        await call.message.edit_text('<b>✅ Вопрос добавлен!</b>', reply_markup=kb_admin_event.back_to_questions)
        await state.clear()
    await call.answer()


async def add_question_options(message: Message, state: FSMContext):
    """Received options for choice question."""
    await message.delete()
    options = [opt.strip() for opt in message.text.split(',') if opt.strip()]
    if len(options) < 2:
        await message.answer(
            '<b>Нужно минимум 2 варианта. Введите варианты через запятую:</b>',
            reply_markup=kb_admin_event.cancel_fsm,
        )
        return

    data = await state.get_data()
    questions = DB.EventQuestion.select(all_scalars=True) or []
    max_order = max((q.order for q in questions), default=0)
    DB.EventQuestion.add(
        question_text=data['new_question_text'],
        question_type='choice',
        options=options,
        order=max_order + 1,
    )
    menu_msg = data.get('fsm_menu')
    if menu_msg:
        try:
            await menu_msg.delete()
        except TelegramAPIError:
            ...
    await message.answer('<b>✅ Вопрос добавлен!</b>', reply_markup=kb_admin_event.back_to_questions)
    await state.clear()


# ---- Edit question ----

async def edit_question_text_start(call: CallbackQuery, state: FSMContext):
    """Start editing question text."""
    qid = int(call.data.split(':')[1])
    await state.set_state(FsmEditQuestion.wait_text)
    await state.update_data(edit_question_id=qid)
    await call.message.edit_text(
        '<b>Введите новый текст вопроса:</b>',
        reply_markup=kb_admin_event.cancel_fsm,
    )
    await call.answer()


async def edit_question_text_done(message: Message, state: FSMContext):
    """Save new question text."""
    await message.delete()
    data = await state.get_data()
    qid = data['edit_question_id']
    DB.EventQuestion.update(mark=qid, question_text=message.text)
    await message.answer('<b>✅ Текст вопроса обновлён!</b>', reply_markup=kb_admin_event.back_to_questions)
    await state.clear()


async def edit_question_opts_start(call: CallbackQuery, state: FSMContext):
    """Start editing question options."""
    qid = int(call.data.split(':')[1])
    q = DB.EventQuestion.select(mark=qid)
    if not q or q.question_type != 'choice':
        return await call.answer('Этот вопрос не имеет вариантов ответа', show_alert=True)
    await state.set_state(FsmEditQuestion.wait_options)
    await state.update_data(edit_question_id=qid)
    current = ', '.join(q.options) if q.options else 'нет'
    await call.message.edit_text(
        f'<b>Текущие варианты:</b> {current}\n\n'
        '<b>Введите новые варианты через запятую:</b>',
        reply_markup=kb_admin_event.cancel_fsm,
    )
    await call.answer()


async def edit_question_opts_done(message: Message, state: FSMContext):
    """Save new options."""
    await message.delete()
    options = [opt.strip() for opt in message.text.split(',') if opt.strip()]
    if len(options) < 2:
        await message.answer(
            '<b>Нужно минимум 2 варианта. Введите варианты через запятую:</b>',
            reply_markup=kb_admin_event.cancel_fsm,
        )
        return
    data = await state.get_data()
    qid = data['edit_question_id']
    DB.EventQuestion.update(mark=qid, options=options)
    await message.answer('<b>✅ Варианты обновлены!</b>', reply_markup=kb_admin_event.back_to_questions)
    await state.clear()


# ---- Toggle / Delete / Reorder ----

async def toggle_question(call: CallbackQuery):
    """Toggle is_active."""
    qid = int(call.data.split(':')[1])
    q = DB.EventQuestion.select(mark=qid)
    if not q:
        return await call.answer('Вопрос не найден', show_alert=True)
    DB.EventQuestion.update(mark=qid, is_active=not q.is_active)
    status = '❌ Выключен' if q.is_active else '✅ Включён'
    await call.answer(f'Статус: {status}', show_alert=True)
    # Refresh view
    call.data = f'admin_eq_view:{qid}'
    await view_question(call)


async def delete_question(call: CallbackQuery):
    """Ask for delete confirmation."""
    qid = int(call.data.split(':')[1])
    await call.message.edit_text(
        '<b>⚠️ Вы уверены, что хотите удалить этот вопрос?</b>',
        reply_markup=kb_admin_event.confirm_delete(qid),
    )
    await call.answer()


async def confirm_delete_question(call: CallbackQuery):
    """Actually delete the question."""
    qid = int(call.data.split(':')[1])
    DB.EventQuestion.remove(mark=qid)
    await call.message.edit_text('<b>✅ Вопрос удалён!</b>', reply_markup=kb_admin_event.back_to_questions)
    await call.answer()


async def reorder_up(call: CallbackQuery):
    """Move question up (decrease order)."""
    qid = int(call.data.split(':')[1])
    questions = DB.EventQuestion.select(all_scalars=True) or []
    questions = sorted(questions, key=lambda q: q.order)
    for i, q in enumerate(questions):
        if q.id == qid and i > 0:
            prev = questions[i - 1]
            DB.EventQuestion.update(mark=qid, order=prev.order)
            DB.EventQuestion.update(mark=prev.id, order=q.order)
            break
    await call.answer('⬆️ Перемещено')
    call.data = f'admin_eq_view:{qid}'
    await view_question(call)


async def reorder_down(call: CallbackQuery):
    """Move question down (increase order)."""
    qid = int(call.data.split(':')[1])
    questions = DB.EventQuestion.select(all_scalars=True) or []
    questions = sorted(questions, key=lambda q: q.order)
    for i, q in enumerate(questions):
        if q.id == qid and i < len(questions) - 1:
            nxt = questions[i + 1]
            DB.EventQuestion.update(mark=qid, order=nxt.order)
            DB.EventQuestion.update(mark=nxt.id, order=q.order)
            break
    await call.answer('⬇️ Перемещено')
    call.data = f'admin_eq_view:{qid}'
    await view_question(call)


def register_handlers_admin_event(dp: Dispatcher):
    dp.callback_query.register(admin_event_questions, F.data == 'admin_event_questions', config.admin_filter)
    dp.callback_query.register(view_question, F.data.startswith('admin_eq_view:'), config.admin_filter)
    dp.callback_query.register(add_question_start, F.data == 'admin_eq_add', config.admin_filter)
    dp.callback_query.register(add_question_type, F.data.startswith('admin_eq_type:'), config.admin_filter)
    dp.callback_query.register(toggle_question, F.data.startswith('admin_eq_toggle:'), config.admin_filter)
    dp.callback_query.register(delete_question, F.data.startswith('admin_eq_delete:'), config.admin_filter)
    dp.callback_query.register(confirm_delete_question, F.data.startswith('admin_eq_confirm_delete:'), config.admin_filter)
    dp.callback_query.register(reorder_up, F.data.startswith('admin_eq_up:'), config.admin_filter)
    dp.callback_query.register(reorder_down, F.data.startswith('admin_eq_down:'), config.admin_filter)
    dp.callback_query.register(edit_question_text_start, F.data.startswith('admin_eq_edit_text:'), config.admin_filter)
    dp.callback_query.register(edit_question_opts_start, F.data.startswith('admin_eq_edit_opts:'), config.admin_filter)
    # FSM handlers for adding/editing questions
    dp.message.register(add_question_text, FsmAddQuestion.wait_text, config.admin_filter)
    dp.message.register(add_question_options, FsmAddQuestion.wait_options, config.admin_filter)
    dp.message.register(edit_question_text_done, FsmEditQuestion.wait_text, config.admin_filter)
    dp.message.register(edit_question_opts_done, FsmEditQuestion.wait_options, config.admin_filter)
