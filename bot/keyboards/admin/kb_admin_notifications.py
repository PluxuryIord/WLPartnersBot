"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

from bot.utils.telegram import create_inline

notifications_buttons = create_inline(
    [
        ['🕹 Уведомления о выходе обновления бота (вкл/выкл)', 'call', 'bot_upgrade_notification'],
        ['🕹 Уведомления о регистрациях (вкл/выкл)', 'call', 'bot_registration_notification'],
        ['🕹 Упоминания в топиках (вкл/выкл)', 'call', 'bot_support_notification'],
        ['🔙 Назад', 'call', 'admin_menu'],
    ], 1)
