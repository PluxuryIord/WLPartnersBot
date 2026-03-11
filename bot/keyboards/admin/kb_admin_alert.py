"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""
# Site Company: buy-bot.ru

from bot.utils.telegram import create_inline, create_inline_rows

menu = create_inline(
    [
        ['📜 Создать рассылку', 'call', 'admin_new_alert'],
        ['🗂 История рассылок', 'call', 'admin_alerts'],
        ['🔙 Назад', 'call', 'admin_menu'],
    ], 1)

cancel_new_alert = create_inline(
    [
        ['❌ Отменить рассылку', 'call', 'admin_alert'],
    ], 1)

back_to_files = create_inline(
    [
        ['❌ Отменить рассылку', 'call', 'admin_alert'],
        ['🔙 Назад', 'call', 'alert_back_to_constructor']
    ], 1)

back_to_buttons = create_inline([['🔙 К кнопкам', 'call', 'alert_buttons']], 1)

preload_text = create_inline(
    [
        ['👁 Предпросмотр', 'call', 'alert_preload'],
        ['✔️ Продолжить', 'call', 'alert_buttons'],
        ['❌ Отменить рассылку', 'call', 'admin_alert'],
    ], 1)

preload_files = create_inline(
    [
        ['👁 Предпросмотр', 'call', 'alert_preload'],
        ['✔️ Продолжить', 'call', 'alert_buttons'],
        ['🚫 Удалить все вложения', 'call', 'alert_clear_files'],
        ['❌ Отменить рассылку', 'call', 'admin_alert']
    ], 1)

clear_preload_files = create_inline(
    [
        ['❌ Отменить рассылку', 'call', 'admin_alert']
    ], 1)

cancel_constructor_preload = create_inline(
    [
        ['🔙 Вернуться', 'call', 'alert_constructor_preload_cancel']
    ], 1)

select_buttons = create_inline(
    [
        ['✔️ Закончить редактирование', 'call', 'alert_go_filters'],
        ['📎 Кнопки бота', 'call', 'alert_bot_buttons'],
        ['Кнопка "Прочитано"', 'call', 'alert_button|read'],
        ['➕ Добавить кнопку с URL', 'call', 'alert_new_url_button'],
        ['🔙 Назад', 'call', 'alert_back_to_constructor'],
    ], 1)


def generate_buttons(urls: list):
    buttons = [
        ['✔️ Закончить редактирование', 'call', 'alert_go_filters'],
        ['📎 Кнопки бота', 'call', 'alert_bot_buttons'],
        ['Кнопка "Прочитано"', 'call', 'alert_button|read'],
        ['➕ Добавить кнопку с URL', 'call', 'alert_new_url_button'],
    ]
    markup = [1, 1, 1, 1]
    for url in urls:
        index, url_button = url
        buttons.append(url_button)
        buttons.append(['❌', 'call', f'alert_remove_url|{index}'])
        markup.append(2)
    buttons.append(['🔙 Назад', 'call', 'alert_back_to_constructor'])
    markup.append(1)
    return create_inline_rows(buttons, markup)


select_users = create_inline(
    [
        ['👥 Отправить всем', 'call', 'alert_filter|all'],
        ['⚙️ Отправить администраторам', 'call', 'alert_filter|admins'],
        ['🕶 Только мне (тест)', 'call', 'alert_filter|me'],
        ['🗓 Фильтр по регистрациям', 'call', 'alert_registration_filter'],
        ['🗂 Загрузить ID из файла', 'call', 'alert_input_users'],
        ['🔙 Вложения', 'call', 'alert_back_to_constructor'],
    ], 1)

register_filter = create_inline(
    [
        ['1️⃣: сегодня', 'call', 'alert_filter|reg_today'],
        ['2️⃣: последние 7 дней', 'call', 'alert_filter|reg_7days'],
        ['3️⃣: последние 30 дней', 'call', 'alert_filter|reg_30days'],
        ['🔙 Фильтры', 'call', 'alert_go_filters'],
    ], 1)

back_to_filters = create_inline([['🔙Фильтры', 'call', 'alert_go_filters']], 1)

input_users = create_inline(
    [
        ['✔️ Продолжить', 'call', 'alert_filter|input_users'],
        ['🔙 Фильтры', 'call', 'alert_go_filters'],
    ], 1)

send_alert = create_inline(
    [
        ['✈️ Отправить', 'call', 'alert_send'],
        ['🔙 Фильтры', 'call', 'alert_go_filters'],
    ], 1)

alert_started = create_inline(
    [
        ['🗂 История рассылок', 'call', 'admin_alerts'],
        ['🔙 Назад', 'call', 'admin_menu'],
    ], 1)

history_type = create_inline(
    [
        ['1️⃣: Мои рассылки', 'call', 'admin_alerts_search|my'],
        ['2️⃣: Все рассылки', 'call', 'admin_alerts_search|all'],
        ['🔙 Назад', 'call', 'admin_alert'],
    ], 1)

history = create_inline([
    ['🔎 Поиск', 'inline', ' '],
    ['🔙 Назад', 'call', 'admin_alerts'],
], 1)


def history_task(alert_id: int, end: bool):
    buttons = [['🔄Обновить информацию', 'call', f'admin_alert_info|{alert_id}']] if not end else []
    return create_inline(buttons + [
        ['👀 Посмотреть рассылку', 'call', f'alert_history_preload|{alert_id}'],
        ['ℹ️ Лог отправки', 'call', f'alert_sent_log|{alert_id}'],
        ['🔙 Назад', 'call', 'admin_alerts']], 1)


def cancel_history_preload(task_id: int):
    return create_inline([
        ['🔙 Вернуться', 'call', f'admin_alert_info|{task_id}']
    ], 1)
