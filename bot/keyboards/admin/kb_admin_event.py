from bot.utils.telegram import create_inline


def questions_list(questions: list) -> object:
    """Build keyboard with list of questions + management buttons."""
    buttons = []
    for q in questions:
        status = '✅' if q.is_active else '❌'
        buttons.append([f'{status} {q.question_text[:40]}', 'call', f'admin_eq_view:{q.id}'])
    buttons.append(['➕ Добавить вопрос', 'call', 'admin_eq_add'])
    buttons.append(['🔙 Меню администратора', 'call', 'admin_menu'])
    return create_inline(buttons, 1)


def question_detail(question_id: int, is_active: bool) -> object:
    """Buttons for a single question: edit, toggle, delete, back."""
    toggle_text = '❌ Выключить' if is_active else '✅ Включить'
    return create_inline([
        ['✏️ Редактировать текст', 'call', f'admin_eq_edit_text:{question_id}'],
        ['📝 Редактировать варианты', 'call', f'admin_eq_edit_opts:{question_id}'],
        [toggle_text, 'call', f'admin_eq_toggle:{question_id}'],
        ['🗑 Удалить', 'call', f'admin_eq_delete:{question_id}'],
        ['⬆️ Вверх', 'call', f'admin_eq_up:{question_id}'],
        ['⬇️ Вниз', 'call', f'admin_eq_down:{question_id}'],
        ['🔙 К списку вопросов', 'call', 'admin_event_questions'],
    ], 1)


question_type_select = create_inline([
    ['Текстовый ответ', 'call', 'admin_eq_type:text'],
    ['Выбор из вариантов', 'call', 'admin_eq_type:choice'],
    ['🔙 Отмена', 'call', 'admin_event_questions'],
], 1)

back_to_questions = create_inline([
    ['🔙 К списку вопросов', 'call', 'admin_event_questions'],
], 1)

confirm_delete = lambda qid: create_inline([
    ['✅ Да, удалить', 'call', f'admin_eq_confirm_delete:{qid}'],
    ['🔙 Отмена', 'call', f'admin_eq_view:{qid}'],
], 1)

cancel_fsm = create_inline([
    ['🔙 Отмена', 'call', 'admin_event_questions'],
], 1)
